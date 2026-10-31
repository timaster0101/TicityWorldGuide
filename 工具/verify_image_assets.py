# -*- coding: utf-8 -*-
"""开图图片资产核验：对 数据/开图清单.json 的每个 image_file 判四件事——文件在不在、是不是 JPEG 字节、
APP1 XMP 段在不在、XMP 里 TC260 与 AIGC 标识在不在。

不生成图片、不改图片、不解码像素、不做视觉验收，也不写 status 或绑定 image_prompt_sha256。
跑法：python 工具/verify_image_assets.py [--out-dir DIR]
"""
import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XMP_NS = b'http://ns.adobe.com/xap/1.0/'
JPEG_MAGIC = b'\xff\xd8\xff'
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
IMG_EXT = ('.png', '.jpg', '.jpeg')


def sweep_extensions(root=ROOT):
    """图集外的扩展名体检：只数「扩展名与字节不符」，一律提示不判红。

    这批文件不参与 image_file 核验，改名要同步动视频工程 JSON 与文档引用，所以只报不办；
    没有这一段，图集外的问题会因为「没人核验」而永久隐形。
    """
    counts, bad = {}, []
    base = root / '数据'
    if not base.is_dir():
        return {'扫描数': 0, '不一致数': 0, '判红数': 0, '按目录': {}, '明细': []}
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(base):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        if rel_dir == '数据/图集' or rel_dir.startswith('数据/图集/'):
            dirnames[:] = []
            continue
        for name in sorted(filenames):
            ext = os.path.splitext(name)[1].lower()
            if ext not in IMG_EXT:
                continue
            scanned += 1
            with open(os.path.join(dirpath, name), 'rb') as fh:
                head = fh.read(8)
            is_jpeg, is_png = head[:3] == JPEG_MAGIC, head == PNG_MAGIC
            mismatch = (ext == '.png' and is_jpeg and not is_png) or \
                       (ext in ('.jpg', '.jpeg') and is_png and not is_jpeg)
            if mismatch:
                key = '/'.join(rel_dir.split('/')[0:2])
                counts[key] = counts.get(key, 0) + 1
                bad.append(rel_dir + '/' + name)
    counts['合计'] = len(bad)
    return {'扫描数': scanned, '不一致数': len(bad), '判红数': 0, '按目录': counts, '明细': bad[:60]}


def sniff(path):
    info = {'存在': False, '字节数': 0, '魔数': '', 'JPEG': False, 'XMP': False,
            'TC260': False, 'AIGC': False, 'C2PA': False, '扩展名': path.suffix.lower()}
    if not path.exists():
        return info
    data = path.read_bytes()
    info.update({'存在': True, '字节数': len(data)})
    info['魔数'] = data[:4].hex()
    info['JPEG'] = data[:3] == b'\xff\xd8\xff'
    pos, payload = 2, b''
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            break
        marker = data[pos + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        size = int.from_bytes(data[pos + 2:pos + 4], 'big')
        if size < 2 or pos + 2 + size > len(data):
            break
        seg = data[pos + 4:pos + 2 + size]
        if marker == 0xE1 and seg.startswith(XMP_NS):
            info['XMP'] = True
            payload = seg
        if marker == 0xEB:                       # C2PA 用 jumb 盒；实测 1056 格全为 False，缺位属预期
            info['C2PA'] = seg[:4] == b'jumb'
        if marker == 0xDA:                       # 压缩数据开始，元数据只可能在段前
            break
        pos += 2 + size
    if info['XMP']:
        info['TC260'] = b'TC260' in payload
        info['AIGC'] = b'AIGC' in payload or b'aigc' in payload
    return info


def check(items, root=ROOT):
    """返回逐格结论。`失败` 只收四类硬判据；扩展名与字节不符只进提示。"""
    rows, fails, notes = [], [], []
    for it in items:
        for rel in (it.get('image_file') or []):
            info = sniff(root / rel)
            reason = ('文件缺失' if not info['存在'] else
                      '非JPEG字节头' if not info['JPEG'] else
                      '缺XMP段' if not info['XMP'] else
                      'XMP缺TC260标识' if not info['TC260'] else
                      'XMP缺AIGC标识' if not info['AIGC'] else None)
            row = {'id': it['id'], '路径': rel, **info, '判定': '通过' if not reason else '失败',
                   '原因': reason or ''}
            rows.append(row)
            if reason:
                fails.append(dict(row, 原因=reason))
            elif info['扩展名'] not in ('.jpg', '.jpeg'):
                notes.append({'id': it['id'], '路径': rel,
                              '提示': f'扩展名 {info["扩展名"]} 与 JPEG 字节不符，只作提示不判红'})
    return {'文件格数': len(rows), '通过格数': len(rows) - len(fails), '失败格数': len(fails),
            '提示格数': len(notes), 'C2PA在位格数': sum(1 for r in rows if r['C2PA']),
            '失败明细': fails[:40], '失败总数': len(fails), '提示明细': notes[:40],
            '逐格': rows,
            '判据': '文件存在＋JPEG 魔数＋APP1 XMP 段＋XMP 内 TC260 与 AIGC 标识四项缺一即判红；'
                    'C2PA（0xEB jumb 盒）不是交付判据：本平台只写 XMP·TC260，实测 1056 格全部缺位，'
                    '缺位既不判红也不列待办，将来若在位也只计数记录、不改变判定；'
                    '扩展名与字节类型不符只记提示。',
            '提示口径': '图集 1056 个文件已按 C82 归一为 .jpg，改名由 工具/rename_gallery_ext.py 完成——'
                        '只改文件名、逐文件比对改名前后 sha256，字节一个没动，也不是重新出图；'
                        '真 PNG 只有 5 个且都不在 image_file 引用里，保持 .png 不改。'
                        '扩展名与字节再不符时只记提示、不判红。',
            '图集外扩展名体检': dict(sweep_extensions(root), **{
                '不改名口径': '图集外的图片文件名被 数据/影像作品/工程文件/**/项目文件/*.json（如 shots_login_tour.json、'
                              'shots_logo_anim.json）与《卡面标准样式规范》《成就卡打卡套系-设计》按文件名引用，'
                              '改名要同步改工程 JSON 与文档引用，否则素材会脱链；'
                              '这批文件又都不在 image_file 交付判据内，所以本期只体检、只报数，判红数固定 0、不催办、不改名。'}),
            '声明': '结构合规不等于视觉验收。本核验不判构图、不判穿帮、不判水印，'
                    '不得由脚本代签 image_prompt_sha256；人工复验结论只能由人写进验收备注。'}


def render_worksheet(report, items):
    rows = {id(r['id']) and (r['id'], r['路径']): r['判定'] for r in report['逐格']}
    bad_ids = {f['id'] for f in report['逐格'] if f['判定'] == '失败'}
    sw = report['图集外扩展名体检']
    by_dir = '／'.join('%s %d' % (k, v) for k, v in sw['按目录'].items() if k != '合计')
    sweep_line = ('图集外扩展名体检：扫 %d 个图片文件，扩展名与字节不符 %d 个（%s），判红 %d。'
                  '这批文件不在 `image_file` 交付判据内、且被视频工程 JSON 与文档按文件名引用，只报不办、不改名（C84）。'
                  % (sw['扫描数'], sw['不一致数'], by_dir, sw['判红数']))
    md = ['# 钛湖城开图图片复验工作单', '',
          '生成物，禁止手改：本单由 `python 工具/verify_image_assets.py` 从 `数据/开图清单.json` 的 `image_file` 逐格派生。',
          '**结构合规不等于视觉验收**：下表「结构核验」只回答文件存在、JPEG 字节头、XMP 段与 TC260·AIGC 标识四件事，',
          '「视觉复验」列一律留 `待人工复验`，不得由脚本代签 `image_prompt_sha256`，也不得由本单宣称任何一条已验收。', '',
          '合计 %d 格｜结构通过 %d｜结构失败 %d｜扩展名提示 %d｜C2PA 在位 %d。' % (
              report['文件格数'], report['通过格数'], report['失败格数'], report['提示格数'], report['C2PA在位格数']),
          '「C2PA 在位 0」不是待办：本平台只写 XMP·TC260，C2PA 不属交付判据，缺位不判红也不催办（C83）。',
          sweep_line,
          '',
          '| ID | 名称 | 类型 | 四向图 | 结构核验 | 视觉复验 | 备注 |',
          '|---|---|---|---|---|---|---|']
    for it in items:
        paths = it.get('image_file') or []
        verdicts = {rows.get((it['id'], p), '无图') for p in paths}
        if not paths:
            struct = '无图'
        elif '失败' in verdicts:
            struct = '失败：' + '／'.join(sorted({f['原因'] for f in report['失败明细']
                                                 if f['id'] == it['id']})) if len(report['失败明细']) == report['失败总数'] else '失败（见核验 JSON 明细）'
        else:
            struct = '通过' if verdicts == {'通过'} else '／'.join(sorted(verdicts))
        note = (it.get('acceptance') or '').replace('|', '｜').replace('\n', ' ')[:40]
        md.append('| %s | %s | %s | %s | %s | %s | %s |' % (
            it['id'], it['name'], it['type'], '<br>'.join(paths), struct, '待人工复验', note or '—'))
    md.append('')
    md.append('人工复验结论写在 `数据/开图验收备注.json`，重跑后同步进清单的 `review_note_history`；本单不承接人工结论。')
    return '\n'.join(md) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default=str(ROOT / '数据'))
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    manifest = json.loads((ROOT / '数据' / '开图清单.json').read_text(encoding='utf-8'))
    report = check(manifest['items'])
    worksheet = render_worksheet(report, manifest['items'])
    persisted = {k: v for k, v in report.items() if k != '逐格'}
    (out_dir / '图片资产核验.json').write_text(
        json.dumps(persisted, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out_dir / '图片复验清单.md').write_text(worksheet, encoding='utf-8')
    print('通过 %d/%d 格，提示 %d 条，C2PA 在位 %d 格' % (
        report['通过格数'], report['文件格数'], report['提示格数'], report['C2PA在位格数']))
    if report['失败格数']:
        for f in report['失败明细']:
            print('判红：%s %s ← %s' % (f['id'], f['路径'], f['原因']))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
