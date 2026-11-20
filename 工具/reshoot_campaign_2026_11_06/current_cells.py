# -*- coding: utf-8 -*-
"""「当前在册重投格」的唯一取法：从 数据/开图验收备注.json 里最后一条占格读数取那一格。

为什么要单独有这一份：重投期的画风读数（clip_style_r1.py）与它的覆盖面对拍闸门
（verify_readout_stance.py 的 K_R1_COVERAGE）原先各写一遍「image_file 里含『C138主向重投』字样的那一格」，
C154 母图臂重投把 310 条的那一格换掉之后，两处命中面同时从 312 塌到 2（2026-11-20 实测判红 2 条）——
按档串字面量筛等于每回填一轮就要人工改一次硬筛，漏改那轮就是静默少读 310 枚。

口径：占格读数行＝抬头形如 `C<NNN><档名><ID>（vNN）投后机械对账读数（`，括号里第一段路径就是本轮新枚；
备注是 append-only，所以「最后一条占格读数」就是当前在册那一轮，不需要维护任何轮次名单。
为什么按行种取而不是 `rows[-1]`：复看补写与人工结论行也会往末尾追加（2026-11-05 那轮 6 条牌面缺口补写、
2026-11-09 那轮 312 条画风目视结论行都是），按位置取会把「这格图在盘」读成「最新那行是读数」。
取到的那枚必须仍在清单 `image_file` 里，否则记入排除并给原因——宁可在覆盖面对拍上判红，
也不让画风读数表悄悄少一枚。

跑法（自检读数，不写盘）：
  python -X utf8 工具/reshoot_campaign_2026_11_06/current_cells.py
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
CELL_HEAD = re.compile(r'^C\d+\S*?（v\d+）投后机械对账读数（([^，]+)，')


def current_cells(root=ROOT):
    """返回 (rows, excluded)。rows 逐条恰 1 格：{id, name, cell, path, 在盘, 档串}；excluded 带原因。"""
    with io.open(os.path.join(root, '数据', '开图清单.json'), encoding='utf-8') as fp:
        q = json.loads(fp.read())
    notes_p = os.path.join(root, '数据', '开图验收备注.json')
    notes = {}
    if os.path.exists(notes_p):
        with io.open(notes_p, encoding='utf-8') as fp:
            notes = json.loads(fp.read()).get('备注') or {}
    rows, excluded = [], []
    for it in q['items']:
        files = it.get('image_file') or []
        if isinstance(files, str):
            files = [files]
        hits = [m.group(1) for m in (CELL_HEAD.search(r) for r in notes.get(it['id'], [])) if m]
        if not hits:
            excluded.append({'id': it['id'], 'status': it['status'], '格数': len(files),
                             '原因': '备注里查不到任何一条占格读数'})
            continue
        cell = hits[-1]
        named = [f for f in files if os.path.basename(f) == os.path.basename(cell)]
        if not named:
            excluded.append({'id': it['id'], 'status': it['status'], '格数': len(files),
                             '原因': '最后一条占格读数点名的格不在清单在册格里'})
            continue
        # 读文件一律走清单登记的那条路径，不走读数里的历史路径：交付落点已搬过三次家
        # （backup/ 镜像 → vibe_images/ → 数据/图集/<ID>/），按原文路径取会在没被本轮替换的两条上判「不在盘」。
        cell = named[0]
        rows.append({'id': it['id'], 'name': it['name'], 'cell': cell, '读数路径': hits[-1],
                     'path': os.path.join(root, cell.replace('/', os.sep)),
                     '在盘': os.path.isfile(os.path.join(root, cell.replace('/', os.sep))),
                     '档串': (re.search(r'[-_](C\d+[^_/]*)[-_]v\d+', os.path.basename(cell)) or
                              re.search(r'(C\d+[^_/]*)', os.path.basename(cell))).group(1)})
    return q, rows, excluded


RULE_TEXT = ('备注里每条 ID 最后一条「投后机械对账读数」抬头括号里点名的那一格（＝当前在册轮次的新枚），'
             '逐条恰 1 格；档串名单不写死，轮次随回填自动跟进')


if __name__ == '__main__':
    q, r, x = current_cells()
    from collections import Counter
    print('清单条目 %d／取到格 %d／排除 %d' % (len(q['items']), len(r), len(x)))
    print('按档串分布 %s' % dict(Counter(i['档串'] for i in r)))
    print('排除原因分布 %s' % dict(Counter(i['原因'] for i in x)))
    print('不在盘 %d' % sum(1 for i in r if not i['在盘']))
    sys.exit(0 if not x and not sum(1 for i in r if not i['在盘']) else 1)
