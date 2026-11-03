# -*- coding: utf-8 -*-
"""开图图片资产核验：对 数据/开图清单.json 的每个 image_file 判标识在不在位。

两条被接受的容器（C97）：JPEG 走 APP1 XMP·TC260＋AIGC 字样；PNG 走 caBX 内 C2PA 清单＋生成式来源声明。
两条各自成档，新增容器不放松原 JPEG 路径；既不属 JPEG 也不属 PNG 的字节头直接判红。

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
# C2PA 在 PNG 里用 caBX 块承载 jumb 清单；生成式来源声明取 IPTC 的 trainedAlgorithmicMedia 或 claim 里的 Generated with AI。
C2PA_CONTAINER = (b'c2pa', b'jumb')
AIGC_DECLARATION = (b'trainedAlgorithmicMedia', b'Generated with AI')


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


def png_caBX(data):
    """取出 PNG 里所有 caBX 块的负载；块长度取自块首 4 字节，遇到 IEND 即止。"""
    boxes, pos = [], 8
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], 'big')
        kind = data[pos + 4:pos + 8]
        if length < 0 or pos + 12 + length > len(data):
            break
        if kind == b'caBX':
            boxes.append(data[pos + 8:pos + 8 + length])
        if kind == b'IEND':
            break
        pos += 12 + length
    return boxes


def sniff(path):
    info = {'存在': False, '字节数': 0, '魔数': '', 'JPEG': False, 'PNG': False, 'XMP': False,
            'TC260': False, 'AIGC': False, 'C2PA': False, 'caBX': False, 'AIGC声明': False,
            '标识容器': '', '扩展名': path.suffix.lower()}
    if not path.exists():
        return info
    data = path.read_bytes()
    info.update({'存在': True, '字节数': len(data)})
    info['魔数'] = data[:4].hex()
    info['JPEG'] = data[:3] == JPEG_MAGIC
    info['PNG'] = data[:8] == PNG_MAGIC
    if info['PNG']:
        boxes = png_caBX(data)
        info['caBX'] = bool(boxes)
        if boxes:
            blob = b''.join(boxes)
            info['C2PA'] = all(mark in blob for mark in C2PA_CONTAINER)
            info['AIGC声明'] = any(mark in blob for mark in AIGC_DECLARATION)
            if info['C2PA'] and info['AIGC声明']:
                info['标识容器'] = 'C2PA(caBX)'
        return info
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
        if marker == 0xEB:                       # C2PA 在 JPEG 里用 jumb 盒；实测 1056 格全为 False，缺位属预期
            info['C2PA'] = seg[:4] == b'jumb'
        if marker == 0xDA:                       # 压缩数据开始，元数据只可能在段前
            break
        pos += 2 + size
    if info['XMP']:
        info['TC260'] = b'TC260' in payload
        info['AIGC'] = b'AIGC' in payload or b'aigc' in payload
        if info['TC260'] and info['AIGC']:
            info['标识容器'] = 'XMP·TC260'
    return info


def verdict(info):
    """按容器分档给判红原因；None 表示该格两条判据都过。"""
    if not info['存在']:
        return '文件缺失'
    if info['PNG']:
        return ('PNG缺caBX标识块' if not info['caBX'] else
                'caBX缺C2PA清单' if not info['C2PA'] else
                'caBX缺生成式AI标识' if not info['AIGC声明'] else None)
    if not info['JPEG']:
        return '字节头既非JPEG亦非PNG'
    return ('缺XMP段' if not info['XMP'] else
            'XMP缺TC260标识' if not info['TC260'] else
            'XMP缺AIGC标识' if not info['AIGC'] else None)


def check(items, root=ROOT):
    """返回逐格结论。`失败` 只收两条容器的硬判据；扩展名与字节不符只进提示。"""
    rows, fails, notes = [], [], []
    for it in items:
        for rel in (it.get('image_file') or []):
            info = sniff(root / rel)
            reason = verdict(info)
            row = {'id': it['id'], '路径': rel, **info, '判定': '通过' if not reason else '失败',
                   '原因': reason or ''}
            rows.append(row)
            if reason:
                fails.append(dict(row, 原因=reason))
            else:
                want = '.png' if info['标识容器'] == 'C2PA(caBX)' else ('.jpg', '.jpeg')
                ext = info['扩展名']
                if ext not in want:
                    notes.append({'id': it['id'], '路径': rel,
                                  '提示': f'扩展名 {ext} 与字节容器不符，只作提示不判红'})
    return {'文件格数': len(rows), '通过格数': len(rows) - len(fails), '失败格数': len(fails),
            '提示格数': len(notes), 'C2PA在位格数': sum(1 for r in rows if r['C2PA']),
            '容器计数': {'XMP·TC260': sum(1 for r in rows if r['标识容器'] == 'XMP·TC260'),
                        'C2PA(caBX)': sum(1 for r in rows if r['标识容器'] == 'C2PA(caBX)')},
            '失败明细': fails[:40], '失败总数': len(fails), '提示明细': notes[:40],
            '逐格': rows,
            '判据': '两条被接受的标识容器（C97）：JPEG 须有 JPEG 魔数＋APP1 XMP 段＋XMP 内 TC260 与 AIGC 标识；'
                    'PNG 须有 PNG 魔数＋caBX 块＋块内 C2PA 清单（c2pa 与 jumb 同在）＋生成式来源声明'
                    '（trainedAlgorithmicMedia 或 Generated with AI）。字节头既非 JPEG 也非 PNG 直接判红；'
                    '新增容器不放松原 JPEG 路径，图集 1056 格仍按 XMP·TC260 判，其 C2PA 缺位属预期、既不判红也不列待办。',
            'C2PA口径': 'C83 定「C2PA 不属交付判据」，适用于本平台只写 XMP·TC260 的 JPEG 资产，'
                        '缺位不判红也不催办；C97 起 PNG 资产走 caBX 内 C2PA 清单，'
                        '该容器在 PNG 上是 accepted 形态而不是加分项——无 caBX 或清单里没有生成式来源声明的 PNG 一律判红。'
                        '任何情况下都不得由脚本给图片补写元数据过闸，那是伪造合规标识。',
            '提示口径': '图集 1056 个文件已按 C82 归一为 .jpg，改名由 工具/rename_gallery_ext.py 完成——'
                        '只改文件名、逐文件比对改名前后 sha256，字节一个没动，也不是重新出图；'
                        'E1 批次出图是真 PNG，C97 起按 caBX·C2PA 容器进 image_file，扩展名与字节本就一致、不改名。'
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
          '**结构合规不等于视觉验收**：下表「结构核验」只回答文件存在与标识容器在不在位（JPEG 走 APP1 XMP·TC260＋AIGC，PNG 走 caBX 内 C2PA 清单＋生成式来源声明），',
          '「视觉复验」列一律留 `待人工复验`，不得由脚本代签 `image_prompt_sha256`，也不得由本单宣称任何一条已验收。', '',
          '合计 %d 格｜结构通过 %d｜结构失败 %d｜扩展名提示 %d｜C2PA 在位 %d（容器分布 XMP·TC260 %d／C2PA(caBX) %d）。' % (
              report['文件格数'], report['通过格数'], report['失败格数'], report['提示格数'], report['C2PA在位格数'],
              report['容器计数']['XMP·TC260'], report['容器计数']['C2PA(caBX)']),
          '图集那批 JPEG 的 C2PA 缺位不是待办：本平台对它们只写 XMP·TC260，缺位不判红也不催办（C83，PNG 侧容器按 C97 判）。',
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
