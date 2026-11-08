"""把 124 张旧卡面里只存在于像素中的三段文字取成可编辑真源，供「程序叠字」的新卡面使用。

为什么需要这一步：新卡面按用户裁定只投 124 张无底部文案版，有文案版由程序叠字生成——
叠字要有文本，而旧卡面的标题、副标题、达成语从来没有文本层（实测 grep 全仓 0 命中，
文案只长在 PNG 像素里）。所以先把像素里的字取出来，否则「有文字版」这一支根本没有数据源。

三段取法各不同，不是一条 OCR 通吃：
- 标题与副标题按 `设计/2026-10-31-卡面标准样式规范.md` 第二节的卡类表 + 文件名三段
  （`{线名}-{编号}-{卡名}-实际卡`）直接推出，不认 OCR——文件名是逐张实存、机读、零错字的；
- 底部文案（达成语/效果文字）只能从像素取，OCR 出初值，真值由目视逐张转录覆盖
  （实测 4 条已知真值 OCR 错 3 条，所以 OCR 只作对照列，不许当结论）。

拼版目视件落在仓库外工作区 `_scratch_cardref/`，是取文过程的工作底稿、不入仓；
入仓的只有 JSON 底稿（含每张的 OCR 对照与目视状态），因为它是叠字生成器的输入面。

跑法：python -X utf8 工具/extract_card_text.py [--rows 6]
"""
import argparse
import collections
import io
import json
import os
import re
import subprocess
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
CARDS = os.path.join(ROOT, 'backup', '数据', '视觉控制资产', '卡牌')
WORKSPACE = os.path.abspath(os.path.join(ROOT, '..'))
SHEET_DIR = os.path.join(WORKSPACE, '_scratch_cardref')
OUT = os.path.join(ROOT, '数据', '卡面文案底稿.json')
TESSERACT = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
TESSDATA = r'C:\Program Files\Tesseract-OCR\tessdata'

# 规范第二节：卡类 → 主标题式样 / 副标题式样。本轮按用户裁定去掉副标题里的编号，
# 所以这里同时记「旧卡面实存副标题」与「新卡面目标副标题」两列，旧列只作取文对照，
# 新列才是叠字生成器要写的——两套并存才看得出「去编号」这条改动到底动了哪 73 张。
SUBTITLE_WITHOUT_CODE = {
    '景群地标卡': '景群套系',
    '板块卡': '板块套系',
    '能力卡': '能力卡',
    '职业卡': '职业卡',
    '物品卡': '物品卡',
    '兑换卡': '兑换卡',
    '成就卡': '成就卡',
    '模板正面': '',
    '模板背面': '',
}


def card_type(stem):
    """按文件名首段与正/背面标记判卡类，判不出即抛错让人来看，不猜。"""
    head = stem.split('-')[0]
    if head == '钛湖八景':
        return '景群地标卡', head
    if head.startswith('板块套系'):
        return '板块卡', '板块套系'
    if head.endswith('线'):
        return '景群地标卡', head
    if head in ('全城地标巡礼', '钛湖之脊', '生态科普'):
        return '景群地标卡', head
    m = re.match(r'(职业卡|兑换卡|物品卡|能力卡|成就卡)', head)
    if m:
        kind = m.group(1)
        if '-正面-' in stem:
            return '模板正面', kind
        if '-背面-' in stem:
            return '模板背面', kind
        return {'职业卡': '职业卡', '兑换卡': '兑换卡', '物品卡': '物品卡',
                '能力卡': '能力卡', '成就卡': '成就卡'}[kind], kind
    raise ValueError('卡类判不出：%s' % stem)


def parse_name(stem):
    """文件名 → (编号, 卡名)。实际卡是 `{线名}-{编号}-{卡名}-实际卡` 四段；模板卡没有编号与卡名。"""
    parts = stem.split('-')
    if stem.endswith('实际卡'):
        body = parts[:-1]
    else:
        body = parts
    code = name = ''
    if len(body) >= 3:
        cand = body[1]
        if re.fullmatch(r'[A-Z]{1,3}-?\d{1,3}[A-Za-z]?', cand) or re.fullmatch(r'T\d', cand):
            code, name = cand, '-'.join(body[2:])
        else:
            name = '-'.join(body[1:])
    elif len(body) == 2:
        name = body[1]
    return code, name


def title_of(kind, group, code, name):
    if kind == '板块卡':
        return '城市片区·%s' % name
    if kind == '模板背面':
        return ''
    if kind == '模板正面':
        return group
    if kind in ('景群地标卡',):
        return '%s·%s' % (group, name) if group not in ('全城地标巡礼', '钛湖之脊') else group
    return name or group


def subtitle_of(kind, group, code, name):
    """旧卡面实存的副标题（带编号），只作取文对照；新卡面目标副标题见 SUBTITLE_WITHOUT_CODE。"""
    if kind == '景群地标卡' and code:
        return '景群套系·%s' % code
    if kind == '板块卡' and code:
        return '板块套系·%s' % code
    if kind == '职业卡' and name:
        return '职业卡·%s' % name
    if kind == '兑换卡':
        return '兑换卡·%s' % (code or name)
    return SUBTITLE_WITHOUT_CODE.get(kind, '')


def ocr_band(img, box, env, tmp):
    crop = img.crop(box)
    if crop.height < 8:
        return ''
    crop = crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS)
    path = os.path.join(tmp, '_band.png')
    crop.save(path)
    r = subprocess.run([TESSERACT, path, 'stdout', '-l', 'chi_sim', '--psm', '7'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)
    return re.sub(r'\s+', ' ', (r.stdout or '')).strip()


def dark_rows(img, min_h=18):
    import numpy as np
    a = np.asarray(img, dtype=np.int16)
    dark = (a < 140).sum(axis=1)
    thr = max(3, int(dark.max() * 0.06)) if dark.size else 3
    on = dark > thr
    out, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            if j - i > min_h:
                out.append((i, j))
            i = j
        else:
            i += 1
    return out


def main(rows):
    files = sorted(f for f in os.listdir(CARDS) if f.lower().endswith(('.png', '.jpg', '.jpeg')))
    if not os.path.isdir(SHEET_DIR):
        os.makedirs(SHEET_DIR)
    env = dict(os.environ, TESSDATA_PREFIX=TESSDATA)
    items = []
    for idx, f in enumerate(files):
        stem = os.path.splitext(f)[0]
        kind, group = card_type(stem)
        code, name = parse_name(stem)
        im = Image.open(os.path.join(CARDS, f))
        size = im.size
        gray = im.convert('L')
        W, H = size
        top = ocr_band(gray, (0, int(H * 0.04), W, int(H * 0.20)), env, SHEET_DIR)
        sub = ocr_band(gray, (0, int(H * 0.20), W, int(H * 0.30)), env, SHEET_DIR)
        band = gray.crop((0, int(H * 0.78), W, H))
        bottoms = []
        for (y0, y1) in dark_rows(band):
            bottoms.append(ocr_band(band, (0, max(0, y0 - 8), W, min(band.height, y1 + 8)), env, SHEET_DIR))
        items.append({
            'file': f, 'card_type': kind, 'group': group, 'code': code, 'name': name,
            'size': list(size),
            'title_expected': title_of(kind, group, code, name),
            'subtitle_old': subtitle_of(kind, group, code, name),
            'subtitle_new': SUBTITLE_WITHOUT_CODE.get(kind, ''),
            'ocr_title': top, 'ocr_subtitle': sub, 'ocr_bottom': ' / '.join(x for x in bottoms if x),
            'bottom_text': '', 'bottom_source': '待目视转录',
        })
    # 拼版目视件：每张只裁底部条带，按 rows 张一版竖排，左侧留 4px 序号色标便于逐张定位
    sheets = []
    per = max(1, rows)
    for s in range(0, len(items), per):
        chunk = items[s:s + per]
        strips = []
        for it in chunk:
            im = Image.open(os.path.join(CARDS, it['file'])).convert('RGB')
            W, H = im.size
            strips.append(im.crop((0, int(H * 0.76), W, H)))
        w = max(x.width for x in strips)
        h = sum(x.height for x in strips) + 8 * len(strips)
        sheet = Image.new('RGB', (w, h), (255, 255, 255))
        y = 0
        for it, st in zip(chunk, strips):
            sheet.paste(st, (0, y))
            y += st.height + 8
        p = os.path.join(SHEET_DIR, 'bottom_%02d.png' % (s // per + 1))
        sheet.save(p)
        sheets.append({'sheet': os.path.basename(p), 'files': [it['file'] for it in chunk]})
    out = {'generated_from': os.path.relpath(CARDS, ROOT), 'cards': len(items),
           'ocr_note': 'OCR 只作对照列，真值取目视转录；实测 4 条已知达成语 OCR 错 3 条，不许以 OCR 结论入正源。',
           'subtitle_note': 'subtitle_old 是旧卡面实存（带编号），subtitle_new 是本轮裁定去编号后的目标值。',
           'sheets': sheets, 'items': items}
    with io.open(OUT, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    by = collections.Counter(i['card_type'] for i in items)
    print('卡面 %d 张 → %s' % (len(items), os.path.relpath(OUT, ROOT)))
    print('卡类分布 %s' % dict(by))
    print('目视拼版 %d 版（每版 %d 张）→ %s' % (len(sheets), per, SHEET_DIR))
    print('底部文案已转录 %d / %d' % (sum(1 for i in items if i['bottom_text']), len(items)))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--rows', type=int, default=6)
    a = ap.parse_args()
    sys.exit(main(a.rows))
