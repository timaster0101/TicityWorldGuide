#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡面 3:4 满幅主图的本机还原点（同盘 zip + 入库台账）。

口径沿用 C146 时代的 数据/卡面备份台账.json：图本体不入库（gitignored），台账入库；
同盘防误删，异地副本属用户 infra、本脚本不做。与退役的 backup_card_faces.py 的差别只有一处：
现役交付不再是烤 PNG，而是 数据/视觉控制资产/卡牌/主图3x4/ 的满幅主图，覆盖面以
数据/卡面主图提示词3x4/主图3x4落点.json 的键现算——落点件有而盘上没有，或盘上有而落点件没登记，
都当场退出非零，不产出半批还原点。

    python 工具/backup_card_main_images.py            建/验还原点并写台账
    python 工具/backup_card_main_images.py --verify   只把 zip 内条目逐字节对回盘上，不写盘
"""
import argparse
import datetime
import hashlib
import io
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANDING = os.path.join(ROOT, '数据', '卡面主图提示词3x4', '主图3x4落点.json')
OUT_DIR = os.path.join(os.path.dirname(ROOT), '钛湖城卡面备份')
ZIP_PATH = os.path.join(OUT_DIR, '主图3x4.zip')
LEDGER = os.path.join(ROOT, '数据', '卡面主图备份台账.json')


def sha12(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for blk in iter(lambda: f.read(1 << 20), b''):
            h.update(blk)
    return h.hexdigest()[:12], os.path.getsize(path)


def disk_rows():
    """落点件逐键 → (卡号, 仓内相对路径, 绝对路径, 字节, sha12)；缺件即报错退出。"""
    land = json.loads(io.open(LANDING, encoding='utf-8').read())
    rows, missing = [], []
    for idx in sorted(land):
        rel = land[idx]
        p = os.path.join(ROOT, rel.replace('/', os.sep))
        if not os.path.exists(p):
            missing.append(rel)
            continue
        s, n = sha12(p)
        rows.append([idx, rel, p, n, s])
    stray = []
    d = os.path.join(ROOT, '数据', '视觉控制资产', '卡牌', '主图3x4')
    if os.path.isdir(d):
        named = {os.path.basename(r[1]) for r in rows}
        stray = sorted(f for f in os.listdir(d) if f.lower().endswith('.png') and f not in named)
    return land, rows, missing, stray


def zip_members(path):
    with zipfile.ZipFile(path) as z:
        return {os.path.basename(i.filename): (i.file_size,
                hashlib.sha256(z.read(i.filename)).hexdigest()[:12]) for i in z.infolist()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--verify', action='store_true', help='只把 zip 内条目逐字节对回盘上，不写盘')
    args = ap.parse_args()

    land, rows, missing, stray = disk_rows()
    if missing:
        print('❌ 落点件有 %d 键取不到文件，先修落点再建还原点：%s' % (len(missing), missing[:5]))
        return 1
    if stray:
        print('❌ 盘上有 %d 张主图未登记进落点件，还原点会漏掉它或混进它：%s' % (len(stray), stray[:5]))
        return 1
    print('落点件键数 %d／盘上取到 %d／未登记 0' % (len(land), len(rows)))

    if args.verify:
        if not os.path.exists(ZIP_PATH):
            print('❌ 还原点不在盘：%s' % ZIP_PATH)
            return 1
        got = zip_members(ZIP_PATH)
        bad = [r[1] for r in rows if got.get(os.path.basename(r[1])) != (r[3], r[4])]
        extra = sorted(set(got) - {os.path.basename(r[1]) for r in rows})
        for m in bad[:10]:
            print('✗ 与盘上不符：%s' % m)
        for m in extra[:10]:
            print('✗ zip 内有而盘上/落点件无：%s' % m)
        print('逐枚对拍：%d/%d 相符，zip 内多余 %d 枚' % (len(rows) - len(bad), len(rows), len(extra)))
        return 1 if (bad or extra) else 0

    changed = True
    if os.path.exists(ZIP_PATH):
        got = zip_members(ZIP_PATH)
        if set(got) == {os.path.basename(r[1]) for r in rows} and \
                all(got[os.path.basename(r[1])] == (r[3], r[4]) for r in rows):
            changed = False
    if changed:
        os.makedirs(OUT_DIR, exist_ok=True)
        tmp = ZIP_PATH + '.part'
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for idx, rel, p, _n, _s in rows:
                z.write(p, os.path.basename(rel))
        os.replace(tmp, ZIP_PATH)
    zsha, zbytes = sha12(ZIP_PATH)
    ledger = {
        '生成者': '工具/backup_card_main_images.py',
        '口径': '卡面 3:4 满幅主图的本机还原点；图本体不入库（gitignored），台账入库；同盘防误删，异地副本属用户 infra。覆盖面以 数据/卡面主图提示词3x4/主图3x4落点.json 的键现算。',
        '归档时间': datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(),
        '本次是否重建zip': '重建' if changed else '已对平、未重建',
        '主图目录': '数据/视觉控制资产/卡牌/主图3x4',
        '归档路径': ZIP_PATH,
        '归档sha256_12': zsha,
        '归档字节': zbytes,
        '文件数': len(rows),
        '主图总字节': sum(r[3] for r in rows),
        '逐文件': [{'idx': idx, 'path': rel, 'bytes': n, 'sha256_12': s} for idx, rel, _p, n, s in rows],
    }
    io.open(LEDGER, 'w', encoding='utf-8', newline='\n').write(
        json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')
    lsha, lbytes = sha12(LEDGER)
    print('还原点 %s（%d 字节／%s，%d 枚）' % (ZIP_PATH, zbytes, zsha, len(rows)))
    print('台账 %s（%d 字节／%s，逐文件 %d 行）' % (LEDGER, lbytes, lsha, len(ledger['逐文件'])))
    print('主图合计 %d 字节' % ledger['主图总字节'])
    if not changed:
        print('zip 内容未变（逐枚 sha 对平），台账按本轮时间重写')
    return 0


if __name__ == '__main__':
    sys.exit(main())
