# -*- coding: utf-8 -*-
"""重投放量·发图串构造（R2 绑定关口组 + R1 主向格组，逐条目单格）。

串只允许来自 数据/开图提示词/*.txt 的「## 提示词正文」之后正文段逐字截取，且逐条与
数据/提示词基准冻结.json 的 prompt_sha256 对拍——这正是 C133 冻结的意义：
放量的每一串都必须打在快照上，跑这一脚本时若快照已漂移，当场停而不是投出去再发现作废。

档位串（文件名后缀）两组分开：R2 沿用 `C133冻结重投-v01`，R1 用 `C138主向重投-v01`。
提示词模板本身没换（prompt_sha256 未变），换的是「分带依据」——§54 靠档串后缀区分投次，历史同名串四轮撞档只能靠
FLOOR 时间戳切；本轮起 数据/提示词基准冻结.json 的 frozen_at_ms 就是那把尺，后缀同时写进台账，两套编号不再互相顶。
264 条 R1 全量统一加后缀，不挑那 19 条 R1∩R2 交集单改——按条目分支会让「这条属于哪一轮」重新变成要靠历史猜的事。
R1 后缀里刻意不含「C133冻结重投」子串：`container_profile.py` 与 `clip_style.py` 都按 `*C133冻结重投*.png` 通配取组，
含进去等于把 264 格静默灌进 R2 那 3 枚的历史实验样本面（`negtest_old_backfill_assert.py` 对该组枚数钉了恰为 D03/L061/L066）。
新档串要进容器画像就得在同文件 patterns 里显式登记，不登记就是静默漏计。

两组走同一条取格口径（C137／C138）：
  R2 绑定关口组 —— 替换对象是「带毫秒时间戳的那一枚定档后格」，同条目挂着的定档前四向格属 R1、本组不动；
                   台账仍是 send_bodies_r1.json（verify_round.py 读它，字段面保持不动）。
  R1 画风判废组 —— 四向挂载条目每条目只投 1 格，那一格＝主向格。指针不抄第二份：现调
                   pick_primary_cell.locate() 从 数据/开图清单.json 推出，再与 queue.json 登记的「主向格」
                   对拍（两处不一致＝真源与队列分叉，当场停）。定位并列（ambiguous）、指针缺失、
                   四向格不足 4 枚，一律停而不猜。台账另立 send_bodies_r1_primary.json，不与 R2 台账混写
                   ——混了会把已投过的条目重复送进发送面。
  R3 补投组 —— 成员面不抄名单：现算自清单，image_file 里一枚 C138主向重投 格都没有的条目就是本组
                   （用户 2026-11-07「只要不是新画风生成的或者缺少的，都开」＝本轮花钱放行的范围）。
                   档串沿用 C138主向重投-v01（补投出来的就是主向格，另起档串会让容器画像／CLIP／代签／复看
                   四处读取面各多一份登记，而它们认的本来就是这枚子串），投次靠独立台账
                   send_bodies_r1_catchup.json 与落盘毫秒时间戳分。取格两条路：挂 1 枚带时间戳定档格＝替换它，
                   一枚都没有＝新增首格；挂满四向（归 R1）或已带新画风格（重复投放）停手。

用法：
  python 工具/reshoot_campaign_2026_11_06/build_send_bodies.py D03 D08 L061 L066   R2 组（逐条点，出 paste_*.txt）
  python 工具/reshoot_campaign_2026_11_06/build_send_bodies.py --r1-all            R1 组全量（只出台账，不出 paste 副本）
  python 工具/reshoot_campaign_2026_11_06/build_send_bodies.py --r1 L001 L002      R1 组逐条点（台账 + paste_r1/）
  python 工具/reshoot_campaign_2026_11_06/build_send_bodies.py --r3-all            R3 补投组全量（成员面清单现算，只出台账）
  python 工具/reshoot_campaign_2026_11_06/build_send_bodies.py --negtest           违例注入自证（仓库外临时目录）
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
SUFFIX = {'R2': 'C133冻结重投-v01', 'R1': 'C138主向重投-v01', 'R3': 'C138主向重投-v01'}
# 「新画风」判据＝格文件名带 C138 主向组档串（与 工具/verify_readout_stance.py 的 R1_CELL_TOKEN 同一把尺）。
# R3 刻意沿用该档串而不是另起一枚：补投出来的就是主向格，档串换了会让容器画像、CLIP、代签与复看四条读取面
# 各多一份「新组」登记，而那些面认的本来就是这枚子串；投次靠台账文件与落盘毫秒时间戳分，不靠档串分。
NEW_STYLE_TOKEN = 'C138主向重投'
sys.path.insert(0, HERE)

from pick_primary_cell import locate, four_way_cells  # noqa: E402  主向口径唯一实现，不在本文件复制一份

LEDGER = {'R2': 'send_bodies_r1.json', 'R1': 'send_bodies_r1_primary.json',
          'R3': 'send_bodies_r1_catchup.json'}
QUEUE_KEY = {'R2': 'R2_绑定关口', 'R1': 'R1_画风判废', 'R3': 'R3_补投非新画风'}
PASTE_SUB = {'R2': None, 'R1': 'paste_r1', 'R3': 'paste_r1'}
PREFIX = 'send_bodies_neg_'


def txt_sha(src):
    """剥掉会随状态漂移的元数据行后对 txt 全文取摘要——与清单 prompt_sha256 同一算法。"""
    lines = [l for l in src.split('\n')[:-1]
             if not re.match(r'^- (?:状态|prompt_sha256|image_prompt_sha256|复验原因/备注)：', l)]
    return hashlib.sha256(('\n'.join(lines) + '\n').encode('utf-8')).hexdigest()


def body_of(root, eid):
    """逐字截「## 提示词正文」之后正文段，返回 (提示词文件名, 正文串)。"""
    hits = [f for f in os.listdir(os.path.join(root, '数据', '开图提示词'))
            if f.startswith(eid + '-')]
    assert len(hits) == 1, (eid, hits)
    src = io.open(os.path.join(root, '数据', '开图提示词', hits[0]), encoding='utf-8').read()
    heads = [m.start() for m in re.finditer(r'^## 提示词正文$', src, re.M)]
    assert len(heads) == 1, (eid, heads)
    return hits[0], src, src[heads[0] + len('## 提示词正文'):].strip()


def primary_pointers(root):
    """现读清单跑 locate()，返回 ({id: 定位行}, items)。定位有违例就停：指针不齐时绝不放行。"""
    man = json.load(io.open(os.path.join(root, '数据', '开图清单.json'), encoding='utf-8'))
    rows, viol, _ = locate(man['items'])
    assert not viol, '主向定位违例 %d 条（先修 pick_primary_cell 的口径再谈投放）：%s' % (len(viol), viol[:5])
    return {r['id']: r for r in rows}, man['items']


def catchup_ids(items):
    """R3 成员面＝清单现算「没有一枚新画风主向格」的条目（用户 2026-11-07「只要不是新画风生成的或者缺少的，都开」）。
    不手抄 ID 名单，也不写死条数：名单由 image_file 派生，条数只作打印读数。"""
    return sorted(it['id'] for it in items
                  if not any(NEW_STYLE_TOKEN in (c or '') for c in (it.get('image_file') or [])))


def pick_cell(group, eid, item, row, queue_ref):
    """返回替换格（本组唯一可投的那一格）。各组的放行路径互不重叠，其余一律停而不猜。"""
    cells = list(item.get('image_file') or [])
    if group == 'R3':
        # 补投面：一条要么挂着 1 枚带时间戳的旧画风定档格（替换它），要么一枚格都没有（新增首格）。
        # 挂满四向或已带新画风格的条目不属本组——前者归 R1 主向口径，后者已经投过，重复投就是同带重发。
        assert not any(NEW_STYLE_TOKEN in (c or '') for c in cells), \
            (eid, '本条已挂新画风主向格，重复投放会造出同条目同档串的两枚格')
        assert not four_way_cells(item), (eid, '四向条目归 R1 主向口径，不在补投面')
        ts_cells = [c for c in cells if re.search(r'_(1\d{12})_', os.path.basename(c))]
        assert len(ts_cells) <= 1, (eid, '补投条目挂 %d 枚带时间戳格（应为 0 或 1）：%s'
                                        % (len(ts_cells), [os.path.basename(c) for c in ts_cells]))
        cell = ts_cells[0] if ts_cells else None
        return cell, [c for c in cells if c != cell], None
    if group == 'R2':
        ts_cells = [c for c in cells if re.search(r'_(1\d{12})_', os.path.basename(c))]
        assert len(ts_cells) == 1, (eid, 'R2 应恰为单枚带时间戳格，实测 %d 枚（全格 %d 枚）：%s'
                                        % (len(ts_cells), len(cells), [os.path.basename(c) for c in ts_cells]))
        return ts_cells[0], [c for c in cells if c != ts_cells[0]], None
    fw = four_way_cells(item)
    assert len(fw) >= 4, (eid, '四向挂载不足 4 枚（实测 %d），不属 C138 每条目 1 格的口径' % len(fw))
    assert row is not None, (eid, 'locate() 未把这条计入定位流程：清单里没有该 ID，或该条目未挂满四向')
    assert row['way'] != 'ambiguous', (eid, '主向定位并列（两格与 camera_facing_deg 同角最近），交人工点，不猜')
    cell = row['cell']
    assert cell, (eid, '主向指针缺失：locate() 没给出格子')
    assert cell in fw, (eid, '主向指针不在该条目的四向格集合里：定位结果与真源分叉')
    qcell = (queue_ref or {}).get('主向格')
    if qcell is not None:
        assert qcell == cell, (eid, '队列登记的「主向格」%s ≠ pick_primary_cell 现读指针 %s：两处口径分叉'
                                    % (qcell, cell))
    return cell, [c for c in cells if c != cell], row


def build(ids, group, root, here, emit_paste=True, queue_entries=None):
    """逐条构造实际送入串并落台账。emit_paste=False 只出台账（串已在台账 body 字段里，不复制 264 份文件）。"""
    assert ids, '至少点一条 ID'
    assert group in LEDGER, group
    ptrs, items = primary_pointers(root)
    by_id = {i['id']: i for i in items}
    snap = json.load(io.open(os.path.join(root, '数据', '提示词基准冻结.json'), encoding='utf-8'))
    base = {e['id']: e['prompt_sha256'] for e in snap['entries']}
    if queue_entries is None:
        if group == 'R3':
            queue_entries = [{'id': i, '主向格': None} for i in catchup_ids(items)]
        else:
            queue_entries = _json_load(os.path.join(here, 'queue.json'))[QUEUE_KEY[group]]['entries']
    by_q = {e['id']: e for e in queue_entries}
    paste_dir = here
    if PASTE_SUB[group]:
        paste_dir = os.path.join(here, PASTE_SUB[group])
        if emit_paste:
            os.makedirs(paste_dir, exist_ok=True)
    out = {}
    pend = []
    for eid in ids:
        assert eid in by_id, (eid, '清单里没有这条 ID')
        assert eid in by_q, (eid, '不在 %s 队列里：本脚本只投队列点名的条目（口径见 设计/2026-11-03-待办移交清单.md §55）'
                             % QUEUE_KEY[group])
        item = by_id[eid]
        name, src, body = body_of(root, eid)
        assert body.startswith('【画风锚点】'), eid
        sha = txt_sha(src)
        assert sha == item['prompt_sha256'], (eid, 'txt 去元数据摘要 ≠ 清单 prompt_sha256，真源与清单已分叉')
        assert sha == base[eid], (eid, '清单 prompt_sha256 ≠ 冻结快照：基准在冻结后变过，先跑 verify_prompt_baseline 再谈投放')
        cell, others, row = pick_cell(group, eid, item, ptrs.get(eid), by_q.get(eid))
        rec = {
            'file': '数据/开图提示词/' + name,
            'send_name': '%s-%s' % (name[:-4], SUFFIX[group]),
            'size': item['size'],
            'chars': len(body),
            'sha256': sha,
            'replaced_cell': cell,
            'untouched_cells': others,
            'status_before': item['status'],
            'body': body,
        }
        if group == 'R1':
            rec['group'] = QUEUE_KEY[group]
            rec['主向格定位方式'] = row['way']
            rec['主向格角差'] = row['delta_deg']
            rec['四向其余三格'] = [c for c in four_way_cells(item) if c != cell]
            # 两组共用同一条串的条目（R1∩R2＝19 条）：各投一次、各换一格，靠组别后缀把发名分开。
            # 后缀已不含「C133冻结重投」子串，故不会落进 R2 那批历史实验样本的通配里。
            rec['同条目R2组在队'] = eid in _other_group_ids(here, group)
        if group == 'R3':
            rec['group'] = QUEUE_KEY['R3']
            rec['占格口径'] = '替换定档格' if cell else '新增首格（该条此前零图）'
        if emit_paste:
            pend.append((eid, os.path.join(paste_dir, 'paste_%s.txt' % eid)))
        out[eid] = rec
    _assert_names_disjoint(here, group, out)
    for eid, path in pend:   # 判据全过才动盘：停手的那一轮不留半成品 paste
        with io.open(path, 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(out[eid]['body'] + '\n')
    with io.open(os.path.join(here, LEDGER[group]), 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1, sort_keys=True)
        fp.write('\n')
    return out, snap


def _assert_names_disjoint(here, group, out):
    """另一组台账若在盘，逐枚比 send_name；撞名就是后缀回退或档串写错，写盘前先停。"""
    other = 'R2' if group == 'R1' else 'R1'
    p = os.path.join(here, LEDGER[other])
    if not os.path.exists(p):
        return
    clash = sorted({r['send_name'] for r in out.values()} & {r['send_name'] for r in _json_load(p).values()})
    assert not clash, ('发名撞档：%d 枚与 %s 台账同名（两组档串必须分开，否则同一轮里各投一次会触发'
                       'verify_round「按名恰 1 次」判红）：%s' % (len(clash), LEDGER[other], clash[:6]))


def summarize(group, out, snap, limit=None):
    print('%s：%d 条｜档串 %s｜frozen_at %s' % (LEDGER[group], len(out), SUFFIX[group], snap['frozen_at']))
    for i, eid in enumerate(sorted(out)):
        if limit and i >= limit:
            print('  …其余 %d 条见台账' % (len(out) - limit))
            break
        r = out[eid]
        print('  %s｜%s｜%d 字｜sha %s｜替换旧格 %s' % (eid, r['size'], r['chars'], r['sha256'][:12], r['replaced_cell']))


def _json_load(p):
    return json.load(io.open(p, encoding='utf-8'))


def _other_group_ids(here, group):
    """从 queue.json 读另一组的条目 ID 集合；夹具缺失时返回空集（只影响同名提醒，不影响放行判据）。"""
    other = 'R2_绑定关口' if group == 'R1' else 'R1_画风判废'
    p = os.path.join(here, 'queue.json')
    if not os.path.exists(p):
        return set()
    try:
        return {e['id'] for e in _json_load(p)[other]['entries']}
    except (KeyError, TypeError, ValueError):
        return set()


def _json_dump(obj, p):
    with io.open(p, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(obj, fp, ensure_ascii=False)


def negtest():
    """十条违例注入，各打一条停手通道；夹具在仓库外临时目录，被守护仓库零写入。"""
    tmp = tempfile.mkdtemp(prefix=PREFIX)
    root, here = os.path.join(tmp, 'root'), os.path.join(tmp, 'here')
    lines, rc = [], 0
    L001 = ['backup/数据/图集/四向/L001/四向00-主向-朝北-r01.jpg',
            'backup/数据/图集/四向/L001/四向180-背向-朝南-r01.jpg',
            'backup/数据/图集/四向/L001/四向270-逆向-朝西-r01.jpg',
            'backup/数据/图集/四向/L001/四向90-顺向-朝东-r01.jpg']
    R057 = ['backup/数据/图集/四向/R057/R057-岚风家庭苑-四向外-R057方向-朝东-r01.jpg',
            'backup/数据/图集/四向/R057/R057-岚风家庭苑-四向外-R057方向-朝北-r01.jpg',
            'backup/数据/图集/四向/R057/R057-岚风家庭苑-四向外-R057方向-朝南-r01.jpg',
            'backup/数据/图集/四向/R057/R057-岚风家庭苑-四向外-R057方向-朝西-r01.jpg']
    D03 = ['backup/数据/图集/D03/D03-东湖金融片区-B3样本-v01_1793000000000_aabbccdd.png']
    D03_2 = D03[0].replace('_1793000000000_aabbccdd', '_1793000000001_eeff0011')
    try:
        os.makedirs(os.path.join(root, '数据', '开图提示词'))
        os.makedirs(here)

        def fresh():
            for g in LEDGER.values():   # 上一枚注入写的台账不能留给下一枚当「另一组在盘」
                p = os.path.join(here, g)
                if os.path.exists(p):
                    os.remove(p)
            items = [
                {'id': 'L001', 'name': '钛湖市民议事厅', 'type': '标志性建筑', 'size': '1536x1024',
                 'status': '待复验', 'camera_facing_deg': 0.0, 'image_file': list(L001)},
                {'id': 'R057', 'name': '岚风家庭苑', 'type': '居民区', 'size': '1536x1024',
                 'status': '待复验', 'camera_facing_deg': 0.0, 'image_file': list(R057)},
                {'id': 'D03', 'name': '东湖金融片区', 'type': '城市片区', 'size': '1792x1024',
                 'status': '待复验', 'camera_facing_deg': 252.0, 'image_file': list(D03)},
            ]
            for it in items:
                p = os.path.join(root, '数据', '开图提示词', '%s-%s.txt' % (it['id'], it['name']))
                io.open(p, 'w', encoding='utf-8', newline='\n').write(
                    '# 开图提示词｜%s %s\n\n- 地点ID：%s\n- 状态：待复验\n- prompt_sha256：（本行随状态漂移）\n\n'
                    '## 提示词正文\n【画风锚点】fixture body for %s\n' % (it['id'], it['name'], it['id'], it['id']))
                it['prompt_sha256'] = txt_sha(io.open(p, encoding='utf-8').read())
            _json_dump({'items': items}, os.path.join(root, '数据', '开图清单.json'))
            _json_dump({'frozen_at': 'fixture', 'frozen_at_ms': 0,
                        'entries': [{'id': i['id'], 'prompt_sha256': i['prompt_sha256']} for i in items]},
                       os.path.join(root, '数据', '提示词基准冻结.json'))
            ptrs, _ = primary_pointers(root)
            _json_dump({'R1_画风判废': {'entries': [{'id': i, '主向格': ptrs[i]['cell']} for i in ('L001', 'R057')]},
                        'R2_绑定关口': {'entries': [{'id': 'D03', '主向格': None},
                                                     {'id': 'L001', '主向格': ptrs['L001']['cell']}]}},
                       os.path.join(here, 'queue.json'))

        def items_now():
            return _json_load(os.path.join(root, '数据', '开图清单.json'))['items']

        def put_items(items):
            _json_dump({'items': items}, os.path.join(root, '数据', '开图清单.json'))

        fresh()
        base_r1 = build(['L001', 'R057'], 'R1', root, here, emit_paste=False)[0]
        base_r2 = build(['D03'], 'R2', root, here, emit_paste=False)[0]
        lines.append('对照（夹具原样）：R1 放行 %s ／ R2 放行 %s ／ 同名标记 %s'
                     % (sorted(base_r1), sorted(base_r2),
                        {k: v['同条目R2组在队'] for k, v in sorted(base_r1.items())}))
        if sorted(base_r1) != ['L001', 'R057'] or sorted(base_r2) != ['D03'] \
                or [base_r1['L001']['同条目R2组在队'], base_r1['R057']['同条目R2组在队']] != [True, False]:
            print('\n'.join(lines) + '\n✗ 夹具本底不干净')
            return 1

        def inj_queue_diverge():
            return 'R1', ['L001'], [{'id': 'L001', '主向格': L001[1]}]

        def inj_ambiguous():
            items = items_now()
            items[1]['camera_facing_deg'] = 45.0   # 落在「朝北 0°」与「朝东 90°」两格正中
            put_items(items)
            return 'R1', ['R057'], None

        def inj_three_cells():
            items = items_now()
            items[0]['image_file'] = L001[:3]
            put_items(items)
            return 'R1', ['L001'], None

        def inj_snapshot():
            snap = _json_load(os.path.join(root, '数据', '提示词基准冻结.json'))
            snap['entries'][0]['prompt_sha256'] = 'f' * 64
            _json_dump(snap, os.path.join(root, '数据', '提示词基准冻结.json'))
            return 'R1', ['L001'], None

        def inj_body_drift():
            io.open(os.path.join(root, '数据', '开图提示词', 'L001-钛湖市民议事厅.txt'),
                    'a', encoding='utf-8', newline='\n').write('被手改追加的一句\n')
            return 'R1', ['L001'], None

        def inj_two_ts():
            items = items_now()
            items[2]['image_file'] = D03 + [D03_2]
            put_items(items)
            return 'R2', ['D03'], None

        def inj_suffix_clash():
            # 给 L001 补一枚带时间戳格，让它两组都能投；先落 R2 台账，再把 R1 后缀回退成不带组别那版
            items = items_now()
            items[0]['image_file'] = L001 + ['backup/数据/图集/L001/'
                                             'L001-钛湖市民议事厅-B3样本-v01_1793000000000_aabbccdd.png']
            put_items(items)
            build(['L001'], 'R2', root, here, emit_paste=False)
            SUFFIX['R1'] = SUFFIX['R2']
            return 'R1', ['L001'], None

        def inj_r3_newstyle():
            items = items_now()
            items[2]['image_file'] = [D03[0], 'backup/数据/图集/D03/D03-东湖金融片区-C138主向重投-v01.png']
            put_items(items)
            return 'R3', ['D03'], [{'id': 'D03', '主向格': None}]

        def inj_r3_fourway():
            return 'R3', ['L001'], [{'id': 'L001', '主向格': None}]

        def inj_r3_two_ts():
            items = items_now()
            items[2]['image_file'] = D03 + [D03_2]
            put_items(items)
            return 'R3', ['D03'], [{'id': 'D03', '主向格': None}]

        suffix0 = dict(SUFFIX)
        for name, fn in [('①队列登记主向格 ≠ 现读指针', inj_queue_diverge),
                         ('②主向并列（ambiguous，不猜）', inj_ambiguous),
                         ('③四向挂载不足 4 枚', inj_three_cells),
                         ('④冻结快照 prompt_sha256 漂移', inj_snapshot),
                         ('⑤开图提示词正文被改', inj_body_drift),
                         ('⑥R2 条目挂两枚带时间戳格（真源 S02/S18 实测形态）', inj_two_ts),
                         ('⑦档串不带组别 → 与 R2 台账撞发名', inj_suffix_clash),
                         ('⑧R3 条目已挂新画风主向格（重复投放＝同带重发）', inj_r3_newstyle),
                         ('⑨R3 条目挂满四向（应归 R1 主向口径）', inj_r3_fourway),
                         ('⑩R3 条目挂两枚带时间戳格（替换对象不唯一）', inj_r3_two_ts)]:
            fresh()
            SUFFIX.update(suffix0)
            group, ids, qe = fn()
            try:
                build(ids, group, root, here, emit_paste=False, queue_entries=qe)
                hit, why = False, '静默放行（无停手）'
            except AssertionError as e:
                hit, why = True, str(e)[:130]
            rc |= 0 if hit else 1
            lines.append('%s %s → %s' % ('✓' if hit else '✗', name, why))
            if name.startswith('⑦'):
                # ⑦的正检面：同一 L001 先投 R2 再投 R1，档串按组分开后必须放行（否则分档是把判据写死成永远红）
                fresh()
                SUFFIX.update(suffix0)
                items = items_now()
                items[0]['image_file'] = L001 + ['backup/数据/图集/L001/'
                                                 'L001-钛湖市民议事厅-B3样本-v01_1793000000000_aabbccdd.png']
                put_items(items)
                r2out = build(['L001'], 'R2', root, here, emit_paste=False)[0]
                r1 = build(['L001'], 'R1', root, here, emit_paste=False)[0]['L001']
                ok = r1['send_name'] != r2out['L001']['send_name']
                rc |= 0 if ok else 1
                lines.append('%s ⑦正检：同一 L001 两组各投一次，R2 发名 %s ／ R1 发名 %s → %s'
                             % ('✓' if ok else '✗', r2out['L001']['send_name'], r1['send_name'],
                                '不撞档' if ok else '仍撞档'))

        # R3 的正检面：零图条目必须放行且记为「新增首格」；成员面现算只认没有新画风格的条目——
        # 已投过的四向条目不得出现在里面（少了这条派生面判据，⑨ 那种「队列里手点四向条目」只能靠 pick_cell 兜）。
        fresh()
        items = items_now()
        items[0]['image_file'] = [L001[0].replace('四向00-主向-朝北-r01', 'C138主向重投-v01')]
        items[1]['image_file'] = [R057[0].replace('四向外-R057方向-朝东-r01', 'C138主向重投-v01')]
        items[2]['image_file'] = []
        put_items(items)
        face = catchup_ids(items_now())
        r3 = build(face, 'R3', root, here, emit_paste=False)[0]
        ok = face == ['D03'] and sorted(r3) == ['D03'] and r3['D03']['replaced_cell'] is None \
            and r3['D03']['占格口径'].startswith('新增首格')
        rc |= 0 if ok else 1
        lines.append('%s R3正检：成员面 %s（已投过的 L001/R057 不在面内）→ 放行 %s，'
                     'replaced_cell=%s，占格口径=%s'
                     % ('✓' if ok else '✗', face, sorted(r3), r3['D03']['replaced_cell'],
                        r3['D03']['占格口径']))

        residue = [p.name for p in Path(ROOT).rglob('*') if PREFIX in p.name]
        lines.append('仓库内 %s 残留 %d' % (PREFIX, len(residue)))
        if residue:
            rc = 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        lines.append('临时目录已删：%s 存在=%s' % (os.path.basename(tmp), os.path.isdir(tmp)))
    print('\n'.join(lines))
    print('%s 送入串构造负测（10 条注入须全部停手；⑦ 带回「分档后必须放行」、R3 块带回「零图条目新增首格」两条正检面）'
          % ('✅' if rc == 0 else '❌'))
    return rc


def main():
    ap = argparse.ArgumentParser(description='重投放量·发图串构造（位置参数＝R2 绑定关口组 ID）')
    ap.add_argument('ids', nargs='*', help='R2 绑定关口组条目 ID')
    ap.add_argument('--r1', nargs='*', metavar='ID', help='R1 主向格组条目 ID（出台账 + paste_r1/）')
    ap.add_argument('--r1-all', action='store_true', help='R1 组全量：队列点名的每条 1 格主向（只出台账，不出 paste 副本）')
    ap.add_argument('--r3-all', action='store_true',
                    help='R3 补投组全量：清单现算「没有一枚新画风主向格」的条目，每条 1 格（只出台账）')
    ap.add_argument('--negtest', action='store_true', help='违例注入自证，须在仓库外临时目录跑')
    args = ap.parse_args()
    if args.negtest:
        return negtest()
    if args.r3_all:
        man = json.load(io.open(os.path.join(ROOT, '数据', '开图清单.json'), encoding='utf-8'))
        ids = catchup_ids(man['items'])
        out, snap = build(ids, 'R3', ROOT, HERE, emit_paste=False)
        summarize('R3', out, snap, limit=8)
        kinds = {}
        for r in out.values():
            kinds[r['占格口径']] = kinds.get(r['占格口径'], 0) + 1
        st = {}
        for r in out.values():
            st[r['status_before']] = st.get(r['status_before'], 0) + 1
        print('  档串 %s（与 R1 同枚，投次靠台账文件＋落盘毫秒时间戳分）｜占格口径 %s｜投放前状态 %s'
              % (SUFFIX['R3'], kinds, st))
        print('  成员面现算自 image_file（不含 %s 子串），不手抄名单；本轮 %d 条' % (NEW_STYLE_TOKEN, len(ids)))
        return 0
    if args.r1_all:
        ids = [e['id'] for e in _json_load(os.path.join(HERE, 'queue.json'))[QUEUE_KEY['R1']]['entries']]
        out, snap = build(ids, 'R1', ROOT, HERE, emit_paste=False)
        summarize('R1', out, snap, limit=8)
        kinds = {}
        for r in out.values():
            kinds[r['主向格定位方式']] = kinds.get(r['主向格定位方式'], 0) + 1
        print('  主向定位方式分布 %s｜四向其余三格合计 %d 枚（另立四向控制资产缺项，不进本轮队列）'
              % (kinds, sum(len(r['四向其余三格']) for r in out.values())))
        dup = sorted(eid for eid, r in out.items() if r['同条目R2组在队'])
        print('  档串 %s（R2 用 %s）｜R1∩R2 交集 %d 条两组各投一次、发名已按组分开：%s'
              % (SUFFIX['R1'], SUFFIX['R2'], len(dup), ' '.join(dup)))
        return 0
    if args.r1:
        out, snap = build(args.r1, 'R1', ROOT, HERE)
        summarize('R1', out, snap)
        return 0
    out, snap = build(args.ids, 'R2', ROOT, HERE)
    summarize('R2', out, snap)
    return 0


if __name__ == '__main__':
    sys.exit(main())
