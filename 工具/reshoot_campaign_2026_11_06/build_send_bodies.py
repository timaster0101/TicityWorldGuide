# -*- coding: utf-8 -*-
"""重投放量·发图串构造（R2 绑定关口组，逐条目单格）。

串只允许来自 数据/开图提示词/*.txt 的「## 提示词正文」之后正文段逐字截取，且逐条与
数据/提示词基准冻结.json 的 prompt_sha256 对拍——这正是 C133 冻结的意义：
放量的每一串都必须打在快照上，跑这一脚本时若快照已漂移，当场停而不是投出去再发现作废。

档位串（文件名后缀）本轮定为 `C133冻结重投-v01`：提示词模板本身没换（prompt_sha256 未变），
换的是「分带依据」——§54 靠档串后缀区分投次，历史同名串四轮撞档只能靠 FLOOR 时间戳切；
本轮起 数据/提示词基准冻结.json 的 frozen_at_ms 就是那把尺，后缀同时写进台账，两套编号不再互相顶。

用法：python 工具/reshoot_campaign_2026_11_06/build_send_bodies.py D03 D08 L061 L066
"""
import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
SUFFIX = 'C133冻结重投-v01'


def main(ids):
    man = json.load(io.open(os.path.join(ROOT, '数据', '开图清单.json'), encoding='utf-8'))
    by_id = {i['id']: i for i in man['items']}
    snap = json.load(io.open(os.path.join(ROOT, '数据', '提示词基准冻结.json'), encoding='utf-8'))
    base = {e['id']: e['prompt_sha256'] for e in snap['entries']}
    queue = json.load(io.open(os.path.join(HERE, 'queue.json'), encoding='utf-8'))
    r2 = {e['id'] for e in queue['R2_绑定关口']['entries']}

    assert ids, '至少点一条 ID'
    out = {}
    for eid in ids:
        assert eid in by_id, (eid, '清单里没有这条 ID')
        assert eid in r2, (eid, '不在 R2 绑定关口队列里：本脚本只投单格条目，四向多格条目走 pick_primary_cell.py 的主向格指针，'
                                '尚未接入送入串生成（见 设计/2026-11-03-待办移交清单.md §55.13 未做面）')
        item = by_id[eid]
        cells = list(item.get('image_file') or [])
        # R2 的替换对象是「带毫秒时间戳的那一枚定档后格」；同条目挂着的定档前 jpg（四向组）属 R1，本轮不动。
        ts_cells = [c for c in cells if re.search(r'_(1\d{12})_', os.path.basename(c))]
        assert len(ts_cells) == 1, (eid, '本组应恰为单枚带时间戳格，实测 %d 枚（全格 %d 枚）' % (len(ts_cells), len(cells)))
        hits = [f for f in os.listdir(os.path.join(ROOT, '数据', '开图提示词'))
                if f.startswith(eid + '-')]
        assert len(hits) == 1, (eid, hits)
        src = io.open(os.path.join(ROOT, '数据', '开图提示词', hits[0]), encoding='utf-8').read()
        heads = [m.start() for m in re.finditer(r'^## 提示词正文$', src, re.M)]
        assert len(heads) == 1, (eid, heads)
        body = src[heads[0] + len('## 提示词正文'):].strip()
        assert body.startswith('【画风锚点】'), eid
        sha = hashlib.sha256(('\n'.join([l for l in src.split('\n')[:-1]
                                        if not re.match(r'^- (?:状态|prompt_sha256|image_prompt_sha256|复验原因/备注)：', l)])
                               + '\n').encode('utf-8')).hexdigest()
        assert sha == item['prompt_sha256'], (eid, 'txt 去元数据摘要 ≠ 清单 prompt_sha256，真源与清单已分叉')
        assert sha == base[eid], (eid, '清单 prompt_sha256 ≠ 冻结快照：基准在冻结后变过，先跑 verify_prompt_baseline 再谈投放')
        name = hits[0][:-4]
        out[eid] = {
            'file': '数据/开图提示词/' + hits[0],
            'send_name': '%s-%s' % (name, SUFFIX),
            'size': item['size'],
            'chars': len(body),
            'sha256': sha,
            'replaced_cell': ts_cells[0],
            'untouched_cells': [c for c in cells if c != ts_cells[0]],
            'status_before': item['status'],
            'body': body,
        }
        with io.open(os.path.join(HERE, 'paste_%s.txt' % eid), 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(body + '\n')

    path = os.path.join(HERE, 'send_bodies_r1.json')
    with io.open(path, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1, sort_keys=True)
        fp.write('\n')
    print('send_bodies_r1：%d 条｜档串 %s｜frozen_at %s' % (len(out), SUFFIX, snap['frozen_at']))
    for eid in ids:
        r = out[eid]
        print('  %s｜%s｜%d 字｜sha %s｜替换旧格 %s' % (eid, r['size'], r['chars'], r['sha256'][:12], r['replaced_cell']))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
