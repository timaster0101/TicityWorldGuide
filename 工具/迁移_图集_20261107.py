# -*- coding: utf-8 -*-
"""把清单登记的定档格从 ImageGen 默认落点 `vibe_images/` 迁入 `数据/图集/<ID>/`。

动机：C138 起每条目只投主向 1 格，回填时挂的是仓外默认落点的仓内镜像路径 `vibe_images/…`，
图集目录因此被掏空成 264 个空壳；`test_image_assets.py:986` 那句「303 条重投后还要整体切回
数据/图集/」等的就是这一轮。迁入后按 ID 分文件夹，交付图与归档图（`backup/数据/图集/四向/<ID>/`）
同构，冷启动的人一眼能在图集里找到某条目的正典格。

姿势照 §50 归档的先例，不发明新流程：copy → 两侧 sha256 逐字节对拍 → 才删源 →
逐条「原路径→新路径＋字节/sha256」登记件入仓。文件名一律不改，因为档名里的毫秒时间戳带与
sha256 尾巴是投次回绑（`verify_round.py`）与复验清单的证据键。

跑法（工作目录＝设定集根）：
    python 工具/迁移_图集_20261107.py --dry     # 只出计划与对账，不落盘
    python 工具/迁移_图集_20261107.py           # 执行迁移并改写 数据/开图清单.json
    python 工具/迁移_图集_20261107.py --rollback # 按登记件原路搬回（仅在登记件在盘时可用）
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, '数据', '开图清单.json')
DETAIL = os.path.join(ROOT, '数据', '图集迁移明细_20261107.json')
GALLERY = '数据/图集'
OLD_PREFIX = 'vibe_images/'
SEP = os.sep


def rel(posix):
    """登记件里一律存仓内相对 POSIX 路径；磁盘操作时再换成平台分隔符。"""
    return posix.replace('/', SEP)


def leaves(node, out=None):
    out = [] if out is None else out
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for v in node.values():
            leaves(v, out)
    elif isinstance(node, list):
        for v in node:
            leaves(v, out)
    return out


def sha12(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for block in iter(lambda: fh.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()[:12]


def build_plan(items):
    """待迁格＝image_file 里以 vibe_images/ 开头的登记路径；图集内的与 backup 内的不动。"""
    plan = []
    for entry in items:
        for cell in leaves(entry.get('image_file')):
            if not cell.startswith(OLD_PREFIX):
                continue
            plan.append((entry['id'], cell,
                         '%s/%s/%s' % (GALLERY, entry['id'], cell.split('/')[-1])))
    return plan


def load_ledger():
    with io.open(LEDGER, encoding='utf-8') as fp:
        raw = fp.read()
    data = json.loads(raw)
    # 只有这一种写法能逐字节还原真源，改表才敢用 json.dumps 落盘
    assert json.dumps(data, ensure_ascii=False, indent=2) + '\n' == raw or \
        json.dumps(data, ensure_ascii=False, indent=2) == raw, '清单不是 indent=2/ensure_ascii=False 的写法，拒改'
    return data, raw


def write_ledger(data, old_raw):
    # 逐字节还原已在 load 时验过，这里按同一写法落盘即可；真源不以换行结尾，就别补换行
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if old_raw.endswith('\n') and not text.endswith('\n'):
        text += '\n'
    with io.open(LEDGER, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


def migrate(dry):
    data, old_raw = load_ledger()
    plan = build_plan(data['items'])
    missing = [c for _, c, _ in plan if not os.path.exists(rel(c))]
    occupied = [t for _, _, t in plan if os.path.exists(rel(t))]
    names = {}
    collide = []
    for _, src, dst in plan:
        if dst in names and names[dst] != src:
            collide.append(dst)
        names[dst] = src
    print('待迁格 %d，涉及条目 %d，源缺失 %d，目标已占 %d，目标重名 %d'
          % (len(plan), len({i for i, _, _ in plan}), len(missing), len(occupied), len(collide)))
    print('字节合计 %.1f MB' % (sum(os.path.getsize(rel(s)) for _, s, _ in plan
                                   if os.path.exists(rel(s))) / 1048576.0))
    if dry:
        for row in plan[:2] + plan[-1:]:
            print('  例', row)
        return 0
    if missing or occupied or collide:
        print('前置对账不干净，拒迁。缺失 %s 占用 %s 重名 %s' % (missing[:3], occupied[:3], collide[:3]))
        return 2

    rows = []
    for eid, src, dst in plan:
        s, t = rel(src), rel(dst)
        os.makedirs(os.path.dirname(t), exist_ok=True)
        before = sha12(s)
        shutil.copyfile(s, t)
        after = sha12(t)
        if before != after or os.path.getsize(s) != os.path.getsize(t):
            print('逐字节对拍不符，停手不删源：%s %s→%s' % (src, before, after))
            return 3
        os.remove(s)
        rows.append({'id': eid, 'from': src, 'to': dst,
                     'bytes': os.path.getsize(t), 'sha256_12': after})

    moved = {(src, dst) for _, src, dst in plan}
    changed = 0
    for entry in data['items']:
        cell = entry.get('image_file')
        if isinstance(cell, list):
            new = []
            for c in cell:
                hit = [d for s, d in moved if s == c]
                new.append(hit[0] if hit else c)
                changed += bool(hit)
            entry['image_file'] = new
    assert changed == len(plan), '清单改写格数 %d 与计划 %d 不等' % (changed, len(plan))
    write_ledger(data, old_raw)

    detail = {'状态': '完成', '口径': '定档格按 ID 分文件夹迁入 数据/图集/，档名不改（毫秒时间戳带＋sha256 尾巴是投次回绑证据）',
              '张数': len(rows), '字节': sum(r['bytes'] for r in rows),
              '明细': rows}
    with io.open(DETAIL, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(detail, fh, ensure_ascii=False, indent=2)
        fh.write('\n')
    print('迁成 %d 格／%.1f MB，清单改写 %d 格，登记件 %s'
          % (len(rows), detail['字节'] / 1048576.0, changed, os.path.basename(DETAIL)))
    return 0


def rollback():
    if not os.path.exists(DETAIL):
        print('登记件不在盘，无法回滚')
        return 2
    with io.open(DETAIL, encoding='utf-8') as _fh:
        detail = json.load(_fh)
    data, old_raw = load_ledger()
    back = {r['to']: r['from'] for r in detail['明细']}
    done = 0
    for r in detail['明细']:
        s, t = rel(r['to']), rel(r['from'])
        if not os.path.exists(s):
            print('回滚缺件，停手：', r['to'])
            return 3
        if sha12(s) != r['sha256_12']:
            print('回滚对拍不符，停手不删：', r['to'])
            return 3
        os.makedirs(os.path.dirname(t), exist_ok=True)
        shutil.copyfile(s, t)
        if sha12(t) != r['sha256_12']:
            print('回滚落点校验失败，停手保留两侧：', r['to'])
            return 3
        os.remove(s)
        done += 1
    for entry in data['items']:
        entry['image_file'] = [back.get(c, c) for c in entry.get('image_file', [])]
    write_ledger(data, old_raw)
    print('回滚 %d 格，清单已指回 vibe_images/' % done)
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--rollback', action='store_true')
    args = ap.parse_args()
    sys.exit(rollback() if args.rollback else migrate(args.dry))
