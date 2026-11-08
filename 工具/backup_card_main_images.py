#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡面 3:4 满幅主图的本机还原点（同盘 zip + 入库台账 + 可选异盘副本）。

口径沿用 C146 时代的 数据/卡面备份台账.json：图本体不入库（gitignored），台账入库；
同盘防误删，异盘副本由 --offdisk 显式指定目标目录后代做（C151 起，目标盘由会话代理选定），
脚本不猜目标盘、也不在没有该参数时写任何仓外副本。与退役的 backup_card_faces.py 的差别只有一处：
现役交付不再是烤 PNG，而是 数据/视觉控制资产/卡牌/主图3x4/ 的满幅主图，覆盖面以
数据/卡面主图提示词3x4/主图3x4落点.json 的键现算——落点件有而盘上没有，或盘上有而落点件没登记，
都当场退出非零，不产出半批还原点。

    python 工具/backup_card_main_images.py                        建/验还原点并写台账
    python 工具/backup_card_main_images.py --verify               只把 zip 内条目逐字节对回盘上，不写盘
    python 工具/backup_card_main_images.py --offdisk D:/bak/钛湖城卡面主图
                                                                  把 zip 与台账整件拷到异盘并逐字节对拍，
                                                                  读数写进台账的 异盘副本 段
    python 工具/backup_card_main_images.py --offdisk-verify DIR   只复查异盘副本，不写盘、不改台账
"""
import argparse
import datetime
import hashlib
import io
import json
import os
import shutil
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


def sha256_full(path):
    h = hashlib.sha256()
    with io.open(path, 'rb') as f:
        for blk in iter(lambda: f.read(1 << 20), b''):
            h.update(blk)
    return h.hexdigest()


def copy_verified(src, dst):
    """整件流式拷到 .part，先比全文件 sha256 再 os.replace——半途崩或截断都不会留下冒充成功的副本。"""
    os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
    tmp = dst + '.part'
    with io.open(src, 'rb') as a, io.open(tmp, 'wb') as b:
        for blk in iter(lambda: a.read(1 << 20), b''):
            b.write(blk)
    if sha256_full(tmp) != sha256_full(src):
        os.remove(tmp)
        raise SystemExit('✗ 副本写入后 sha256 与源不符，已删除 .part：%s' % src)
    os.replace(tmp, dst)
    return sha256_full(dst), os.path.getsize(dst)


def offdisk_state(dest_dir, only_zip=False):
    """异盘副本现读：逐文件比整件 sha256，zip 另开一次取成员数与逐枚 sha12 对回源 zip。"""
    pairs = [(ZIP_PATH, os.path.join(dest_dir, os.path.basename(ZIP_PATH)))]
    if not only_zip:
        pairs.append((LEDGER, os.path.join(dest_dir, os.path.basename(LEDGER))))
    rows, ok = [], True
    for src, dst in pairs:
        if not os.path.exists(dst):
            ok = False
            rows.append({'文件': os.path.basename(dst), '在盘': False})
            continue
        same = sha256_full(dst) == sha256_full(src)
        ok = ok and same
        row = {'文件': os.path.basename(dst), '在盘': True, '字节': os.path.getsize(dst)}
        row['sha256_12'] = sha256_full(dst)[:12]
        row['整件sha256与源相同'] = same
        rows.append(row)
    zsrc = zip_members(ZIP_PATH)
    dst_zip = os.path.join(dest_dir, os.path.basename(ZIP_PATH))
    try:
        zdst = zip_members(dst_zip)
        opened = True
    except (zipfile.BadZipFile, OSError):
        zdst, opened = {}, False
    zip_member_equal = opened and zsrc == zdst
    ok = ok and zip_member_equal
    return ok, rows, {'源zip成员数': len(zsrc), '副本zip成员数': len(zdst),
                      '副本zip可打开': opened,
                      '逐枚sha12与源zip全等': zip_member_equal,
                      '副本zip多余/缺失': sorted(set(zdst) ^ set(zsrc))[:5]}


def carry_offdisk_block(prev, zsha):
    """不带 --offdisk 重建 zip 时，异盘副本段照旧带过去，但 与当前还原点一致 按新 zip 摘要现算——
    副本没跟着重建就会在这里留下 false，而不是悄悄留着上一次的 true。"""
    if not prev:
        return None
    prev['与当前还原点一致'] = prev.get('zip_sha256_12') == zsha
    return prev


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--verify', action='store_true', help='只把 zip 内条目逐字节对回盘上，不写盘')
    ap.add_argument('--offdisk', metavar='DIR', help='把 zip 与台账整件拷到异盘目录并逐字节对拍')
    ap.add_argument('--offdisk-verify', metavar='DIR', help='只复查异盘目录里的副本，不写盘')
    args = ap.parse_args()

    if args.offdisk_verify:
        dest = os.path.abspath(args.offdisk_verify)
        ok, rows, zinfo = offdisk_state(dest)
        print('异盘副本复查 %s' % dest)
        for r in rows:
            print('  %s' % json.dumps(r, ensure_ascii=False))
        print('  %s' % json.dumps(zinfo, ensure_ascii=False))
        print('结论：%s' % ('副本与源逐字节相同' if ok else '副本与源不符或不在盘'))
        return 0 if ok else 1

    if args.offdisk:
        dest = os.path.abspath(args.offdisk)
        if os.path.normcase(os.path.splitdrive(dest)[0]) == os.path.normcase(os.path.splitdrive(ROOT)[0]):
            print('❌ 目标目录与仓库在同一盘（%s），异盘副本的意义就没了，停手' % dest)
            return 1
        if not os.path.exists(ZIP_PATH):
            print('❌ 同盘还原点还没建，先不带参数跑一次：%s' % ZIP_PATH)
            return 1
        # 先拷 zip、再写台账、最后拷台账：台账里记的是「写完那一刻的」zip 摘要，
        # 而台账自身的副本只能在它定稿之后拷，否则副本与仓内件永远差一个 异盘副本 段。
        zsha, zbytes = sha12(ZIP_PATH)
        dst_zip = os.path.join(dest, os.path.basename(ZIP_PATH))
        csha, cbytes = copy_verified(ZIP_PATH, dst_zip)
        print('✓ zip 整件写入并逐字节对拍通过：%s（%d 字节／%s，源 %s）'
              % (dst_zip, cbytes, csha[:12], zsha))
        ok, rows, zinfo = offdisk_state(dest, only_zip=True)
        if not ok or not zinfo['逐枚sha12与源zip全等']:
            print('❌ 写完复查不过：%s %s' % (json.dumps(rows, ensure_ascii=False), json.dumps(zinfo, ensure_ascii=False)))
            return 1
        usage = shutil.disk_usage(dest)
        ledger = json.loads(io.open(LEDGER, encoding='utf-8').read())
        ledger['异盘副本'] = {
            '目标目录': dest.replace(os.sep, '/'),
            '目标盘符': os.path.splitdrive(dest)[0],
            '该盘容量GB': round(usage.total / 2 ** 30, 1),
            '该盘剩余GB': round(usage.free / 2 ** 30, 1),
            '写入时间': datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(),
            'zip字节': cbytes,
            'zip_sha256_12': csha[:12],
            'zip整件sha256': csha,
            '对拍': zinfo,
            '口径': '整件流式拷 .part → 全文件 sha256 与源相同才 os.replace；写完再开一次副本 zip，逐枚 sha12 对回源 zip。'
                    '本段只记 zip 的摘要，台账自身的副本在这段写盘之后才拷，故本段不含台账副本的摘要。'
                    '不带 --offdisk 重建 zip 时，本段的 与当前还原点一致 会转 false，提示重跑 --offdisk。',
            '与当前还原点一致': csha[:12] == zsha,
        }
        io.open(LEDGER, 'w', encoding='utf-8', newline='\n').write(
            json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')
        lsha, lbytes = sha12(LEDGER)
        dst_ledger = os.path.join(dest, os.path.basename(LEDGER))
        copy_verified(LEDGER, dst_ledger)
        print('✓ 台账整件写入并逐字节对拍通过：%s（%d 字节／%s）' % (dst_ledger, lbytes, lsha))
        print('台账已写入 异盘副本 段（%d 字节／%s，zip 成员 %d 枚全等）'
              % (lbytes, lsha, zinfo['副本zip成员数']))
        return 0

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
        '口径': '卡面 3:4 满幅主图的本机还原点；图本体不入库（gitignored），台账入库；同盘防误删，异盘副本由 --offdisk 显式指定目录后代做（读数见 异盘副本 段）。覆盖面以 数据/卡面主图提示词3x4/主图3x4落点.json 的键现算。',
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
    prev = None
    if os.path.exists(LEDGER):
        try:
            prev = json.loads(io.open(LEDGER, encoding='utf-8').read()).get('异盘副本')
        except ValueError:
            prev = None
    carried = carry_offdisk_block(prev, zsha)
    if carried:
        ledger['异盘副本'] = carried
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
