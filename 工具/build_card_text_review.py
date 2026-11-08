"""把 `数据/卡面文案底稿.json` 的 OCR 初值按可信度分流，只把不可信的拼成目视版给我逐张转录。

为什么要分流：124 张底部文案只有像素、没有文本真源（实测 grep 全仓 0 命中），而 tesseract 对
8—16 字对句大体可用、对长句和带分隔符的效果文字会碎（实测 4 条已知真值错 3 条）。全量目视要 21 版
拼版图，全量直取又会把错字写进叠字真源——所以按可机读的三条硬信号判可信，判不过的才进目视面，
每张最终都带 `取文方式`（OCR 直读／目视转录）入底稿，来源可追。

判据（任一命中即判不可信）：
1. 清洗后长度不在 6—24 字（模板背面类无文案的除外，那类由卡类直接判空）；
2. 含明显噪声形态：孤立单字加空格串（`一 站 迎 客` 这种逐字分开是正常渲染，但单字占比 >0.6 视为碎）、
   竖线/问号/连续标点、ASCII 与控制符；
3. 与卡类应然形态不符：兑换卡档位卡应含「积分」或「门槛」，职业/能力/物品卡应含「·」或数字。

跑法：python -X utf8 工具/build_card_text_review.py [--per 10] [--trust-ocr]
输出：`_scratch_cardref/review_XX.png` ＋ 底稿里新增 `可信度`/`需目视` 两列。

默认全量目视，不分流。实测教训：OCR 的错法是同音替换（「产业兴城」读成「产业兴起」、
「典藏级别」读成「嵌壮级列」里的形近字），长度与字符集类启发式对这类错完全不敏感，
所以「看起来干净」不等于「可信」。分流通道 `--trust-ocr` 保留给别处，但卡面文案真源不许用它——
错字一旦进 `bottom_text`，程序叠字会把同一个错字印到全部有文案版上，比图错更难发现。
"""
import argparse
import io
import json
import os
import re
import sys

from PIL import Image
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
CARDS = os.path.join(ROOT, 'backup', '数据', '视觉控制资产', '卡牌')
WORKSPACE = os.path.abspath(os.path.join(ROOT, '..'))
SHEET_DIR = os.path.join(WORKSPACE, '_scratch_cardref')
DRAFT = os.path.join(ROOT, '数据', '卡面文案底稿.json')

NOISE = re.compile(r'[|？?~^_|]{1,}')
CJK = re.compile(r'[一-鿿]')


def clean(s):
    s = re.sub(r'\s+', '', s or '')
    return s


def score(kind, ocr):
    """返回 (可信, 原因)。判不出就一律判不可信，宁多目视不可少目视。"""
    if kind in ('模板背面',):
        return True, '卡类无底部文案'
    t = clean(ocr)
    if not t:
        return False, 'OCR 空'
    if NOISE.search(t):
        return False, '含噪声符'
    if not CJK.search(t):
        return False, '无中文'
    if len(t) < 6 or len(t) > 24:
        return False, '长度 %d 越出 6—24' % len(t)
    cjk = len(CJK.findall(t))
    if cjk / float(len(t)) < 0.55:
        return False, '中文字符占比 %.2f 过低' % (cjk / float(len(t)))
    if kind in ('兑换卡',) and not re.search(r'积分|门槛|级别', t):
        return False, '兑换卡缺档位要素'
    if kind in ('职业卡', '能力卡', '物品卡') and not re.search(r'[·/]|[\d+]', t):
        return False, '效果文字缺结构符'
    return True, 'OCR 直读可用'


def _panel_top(g, H):
    """底部浅米杏文案面板的上沿：连续 ≥25 行「高均值+低方差」的第一段。

    实测教训：面板下沿不能当裁剪终点——文字行本身把 std 抬到 40 以上，
    取「第一段亮行的结束点」会正好停在文字上方，把要读的那行裁掉（L037 即此例）。
    """
    off = int(H * 0.60)
    rows = g[off:]
    light = (rows.mean(axis=1) > 195) & (rows.std(axis=1) < 28)
    i, n = 0, len(light)
    while i < n:
        if light[i]:
            j = i
            while j < n and light[j]:
                j += 1
            if j - i >= 25:
                return off + i
            i = j
        else:
            i += 1
    return None


def _text_rows(g, y0, y1):
    """面板内暗字投影，返回文字行的上下沿（含边距）；取不到就退成面板首 120 行。"""
    seg = g[y0:y1]
    dark = (seg < 150).sum(axis=1)
    on = np.nonzero(dark > max(3, int(dark.max() * 0.05)))[0] if dark.max() else []
    if len(on) == 0:
        return y0, min(y1, y0 + 120)
    return max(y0, y0 + int(on[0]) - 8), min(y1, y0 + int(on[-1]) + 10)


def bottom_rows(img, scale=1.6):
    """返回底部文案的紧裁条（一行或整段），放大 scale 倍供目视。

    旧版按「条带里第 42% 之后的投影段」挑文字，实测 124 张里 24 张整带全暗、
    另有若干张文字行落在阈值前被滤空后回退成实景照片（#002/#003 即此），
    目视版上出现「只有照片没有字」的假缺文。改为先定位浅色面板再在面板内投影。
    """
    W, H = img.size
    g = np.asarray(img.convert('L'), dtype=np.int16)
    p = _panel_top(g, H)
    if p is None:
        # 深色底卡（实测 4 张：L050/D10/A08/A18）没有浅色面板，退回固定底部 30%
        y0, y1 = int(H * 0.70), H
    else:
        y0, y1 = _text_rows(g, p, H)
    strip = img.convert('RGB').crop((0, y0, W, y1))
    if scale != 1:
        strip = strip.resize((int(W * scale), max(1, int(strip.height * scale))), Image.LANCZOS)
    return [strip]


def main(per, trust_ocr):
    with io.open(DRAFT, encoding='utf-8') as fh:
        draft = json.load(fh)
    ok = bad = 0
    todo = []
    for pos, it in enumerate(draft['items'], 1):
        it['_idx'] = pos
        trust, why = score(it['card_type'], it['ocr_bottom'])
        if trust_ocr and trust:
            it['可信度'] = why
            it['需目视'] = False
            it['bottom_text'] = clean(it['ocr_bottom'])
            it['bottom_source'] = 'OCR 直读'
            ok += 1
            continue
        # 默认档：只有「卡类本就没有底部文案」那 5 张免目视，其余一律进目视面
        if it['card_type'] == '模板背面':
            it['可信度'] = why
            it['需目视'] = False
            it['bottom_text'] = ''
            it['bottom_source'] = '卡类无底部文案'
            ok += 1
        else:
            it['可信度'] = '全量目视（默认档，OCR 只作提示）'
            it['需目视'] = True
            bad += 1
            todo.append(it)
    if not os.path.isdir(SHEET_DIR):
        os.makedirs(SHEET_DIR)
    n = 0
    from PIL import ImageDraw, ImageFont
    for s in range(0, len(todo), per):
        chunk = todo[s:s + per]
        strips = []
        for it in chunk:
            img = Image.open(os.path.join(CARDS, it['file']))
            for r in bottom_rows(img):
                strips.append((it, r))
        w = max(x[1].width for x in strips)
        gap = 8
        tag = 44
        h = sum(x[1].height + tag + gap for x in strips)
        sheet = Image.new('RGB', (w, h), (250, 250, 250))
        y = 0
        dr = ImageDraw.Draw(sheet)
        for it, r in strips:
            # PIL 默认位图字体不画中文（实测渲染成方块），标签只用 ASCII：全局序号＋文件名里的编号/卡类段。
            # 全局序号对 `数据/卡面文案底稿.json` 的 items 下标，转录按这个号回填。
            code = re.sub(r'[^A-Za-z0-9\-]', '', it['code'] or '')
            if not code:
                m = re.search(r'[A-Za-z]+\d+', it['file'])
                code = m.group(0) if m else 'NOCODE'
            dr.text((6, y + 2), '#%03d  %s' % (it['_idx'], code), fill=(170, 0, 0))
            dr.text((6, y + 22), 'OCR: %s' % (it['ocr_bottom'][:70] or '空'), fill=(0, 80, 170))
            sheet.paste(r, (0, y + tag))
            y += r.height + tag + gap
        p = os.path.join(SHEET_DIR, 'review_%02d.png' % (s // per + 1))
        sheet.save(p)
        n += 1
    with io.open(DRAFT, 'w', encoding='utf-8') as fh:
        json.dump(draft, fh, ensure_ascii=False, indent=1)
    # 序号→文件对照，转录时按 # 号回填，避免靠肉眼数版面行
    with io.open(os.path.join(SHEET_DIR, 'index.tsv'), 'w', encoding='utf-8') as fh:
        for it in draft['items']:
            fh.write('%d\t%s\t%s\t%s\n' % (it['_idx'], it['card_type'], it['code'], it['file']))
    print('免目视 %d 张／需目视 %d 张（共 %d）' % (ok, bad, len(draft['items'])))
    print('目视拼版 %d 版（每版 ≤%d 张）→ %s' % (n, per, SHEET_DIR))



if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--per', type=int, default=10)
    ap.add_argument('--trust-ocr', action='store_true',
                    help='允许 OCR 直读免目视；卡面文案真源不许用（同音替换型错字看不见）')
    a = ap.parse_args()
    sys.exit(main(a.per, a.trust_ocr))
