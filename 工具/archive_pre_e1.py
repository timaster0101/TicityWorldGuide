# -*- coding: utf-8 -*-
"""早于 E1 定档的图整体归档进 backup/（用户 2026-11-06 点单：按字面移全部 187 张＋同步改引用）。

口径与 2026-11-06 的 B 裁定迁移一致：归档＝move，原位置移除，backup 下镜像原相对路径。
定档下界不写死成猜测值，而是现场取证「文件名带 E1定档 且含 13 位毫秒时间戳」这批图里最早的一枚，
并把它钉死为 §52.5 记录的那个时刻——哪天定档图集合变了，脚本直接崩，不静默换界。
分域计数同样钉死为移交清单 §52.5 的表，对不上就不许执行。

用法：
    python 工具/archive_pre_e1.py            # dry-run，只统计与对账
    python 工具/archive_pre_e1.py --exec     # 真正移动，并写 backup/归档明细_早于定档_20261106.json
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMG_EXT = ('.png', '.jpg', '.jpeg')
SCAN_DIRS = ('数据/视觉控制资产', '数据/影像作品')
TS = re.compile(r'_(17\d{11})_[0-9a-f]{8}\.(png|jpg|jpeg)$')
CUTOFF_EXPECT = datetime(2026, 11, 3, 1, 50, 2, 152000)
DETAIL = ROOT / 'backup' / '归档明细_早于定档_20261106.json'
EXPECTED_DOMAIN = {'卡牌': 124, '影像工程': 16, 'L007': 13, 'R043': 12,
                   '品牌LOGO': 11, 'E1半写实厚涂': 7, '登录界面': 4}
EXPECTED_TOTAL = 187
EXPECTED_MB = 178.9  # §52.5 记到 0.1 MB


def produced(p):
    """年代取证：文件名里的 13 位毫秒时间戳优先，缺时间戳退回 mtime（明细里逐条记来源）。"""
    m = TS.search(p.name)
    if m:
        return datetime.fromtimestamp(int(m.group(1)) / 1000), '文件名'
    return datetime.fromtimestamp(p.stat().st_mtime), 'mtime'


def cutoff():
    """下界＝「E1定档」文件名图里最早的一枚时间戳；取证面只有文件名可证的这批，不接受 mtime。"""
    stamps = []
    for p in ROOT.rglob('*'):
        if p.is_file() and p.suffix.lower() in IMG_EXT and 'E1定档' in p.name:
            m = TS.search(p.name)
            if m:
                stamps.append(datetime.fromtimestamp(int(m.group(1)) / 1000))
    if not stamps:
        raise SystemExit('取证失败：没有任何「E1定档」文件名带时间戳的图，下界无从确立')
    got = min(stamps)
    if got != CUTOFF_EXPECT:
        raise SystemExit('定档下界漂移：取证 %s ≠ §52.5 记录的 %s，先复核定档图集合再动文件'
                         % (got.isoformat(sep=' '), CUTOFF_EXPECT.isoformat(sep=' ')))
    return got, len(stamps)


def domain_of(rel):
    """分域口径与移交清单 §52.5 的表逐字对齐（影像工程＝数据/影像作品 整棵树）。"""
    if rel.startswith('数据/影像作品/'):
        return '影像工程'
    part = rel[len('数据/视觉控制资产/'):].split('/')[0]
    if part not in EXPECTED_DOMAIN:
        raise SystemExit('出现未登记的分域：%s（先补 §52.5 的表与 EXPECTED_DOMAIN，再执行）' % part)
    return part


def plan():
    cut, evidence = cutoff()
    items = []
    for rel_dir in SCAN_DIRS:
        base = ROOT / rel_dir
        if not base.is_dir():
            continue
        for p in sorted(base.rglob('*')):
            if not p.is_file() or p.suffix.lower() not in IMG_EXT:
                continue
            rel = p.relative_to(ROOT).as_posix()
            when, source = produced(p)
            if when >= cut:
                continue
            items.append({'rel': rel, 'dst': 'backup/' + rel, 'bytes': p.stat().st_size,
                          'sha256_12': hashlib.sha256(p.read_bytes()).hexdigest()[:12],
                          'produced': when.isoformat(sep=' '), 'time_source': source,
                          'domain': domain_of(rel)})
    return cut, evidence, items


def reconcile(items):
    dom = Counter(i['domain'] for i in items)
    bad = ['%s：实测 %d ≠ §52.5 %d' % (k, dom.get(k, 0), v) for k, v in EXPECTED_DOMAIN.items()
           if dom.get(k, 0) != v]
    if len(items) != EXPECTED_TOTAL:
        bad.append('总数：实测 %d ≠ §52.5 %d' % (len(items), EXPECTED_TOTAL))
    mb = sum(i['bytes'] for i in items) / 1048576.0
    if abs(mb - EXPECTED_MB) > 0.5:
        bad.append('体积：实测 %.1f MB ≠ §52.5 %.1f MB（容差 0.5）' % (mb, EXPECTED_MB))
    return dom, mb, bad


def main(argv=None):
    ap = argparse.ArgumentParser(description='早于 E1 定档的图整体归档进 backup/')
    ap.add_argument('--exec', action='store_true', help='真正移动（缺省只 dry-run 统计）')
    args = ap.parse_args(argv)
    cut, evidence, items = plan()
    dom, mb, bad = reconcile(items)
    print('定档下界 %s（取证面 %d 枚「E1定档」文件名时间戳，取最早一枚）' % (cut.isoformat(sep=' '), evidence))
    print('分域：', '，'.join('%s %d' % (k, dom[k]) for k in EXPECTED_DOMAIN))
    print('合计 %d 张 / %.1f MB，时间来源：文件名 %d 张、mtime %d 张'
          % (len(items), mb, sum(1 for i in items if i['time_source'] == '文件名'),
             sum(1 for i in items if i['time_source'] == 'mtime')))
    if bad:
        print('\n与移交清单 §52.5 对账不上，拒绝执行：')
        for b in bad:
            print('  ✗', b)
        return 1
    print('与 §52.5 逐域对账：一致')
    if not args.exec:
        print('\n（dry-run，未移动任何文件；要执行加 --exec）')
        return 0
    def dump(status):
        DETAIL.write_text(json.dumps({'状态': status,
                                      '归档时间': datetime.now().isoformat(timespec='seconds'),
                                      '定档下界': cut.isoformat(sep=' '), '下界取证枚数': evidence,
                                      '口径': '早于 E1 定档下界的图片整体 move 进 backup/，镜像原相对路径',
                                      '张数': len(items), '字节': sum(i['bytes'] for i in items),
                                      '分域': dict(dom), '明细': items},
                                     ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    for i in items:  # 预检先跑完再动手，避免半途撞车留下无明细的半迁移态
        if (ROOT / i['dst']).exists():
            raise SystemExit('目标已存在，拒绝覆盖：%s（未移动任何文件）' % i['dst'])
    dump('执行中')  # 计划先落盘：真在移动中途崩了，这份明细就是恢复依据
    for i in items:
        src, dst = ROOT / i['rel'], ROOT / i['dst']
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    moved = 0
    for i in items:
        src, dst = ROOT / i['rel'], ROOT / i['dst']
        if src.exists() or not dst.is_file() or dst.stat().st_size != i['bytes']:
            raise SystemExit('移动后自证失败（状态仍是 执行中，按明细回滚或续做）：%s → %s' % (i['rel'], i['dst']))
        moved += 1
    dump('完成')
    print('已移动 %d 张，明细写入 %s' % (moved, DETAIL.relative_to(ROOT)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
