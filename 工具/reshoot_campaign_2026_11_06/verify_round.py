# -*- coding: utf-8 -*-
"""重投放量·投后核验：逐字回绑 → 落盘取证 → 测量 → 台账，任何一环不等即停，不写任何真源。

四道历史教训写死在这里：
1. §32.4 发送侧字符损坏：实发串必须与会话 jsonl 里 tool_use 的 prompt 逐字相等，只看「投过了」不算。
2. §54 关口B 的分带依据换成 C133 的 frozen_at_ms：同一个 ID 现在挂着多枚同名/异名历史文件，
   不带内闸门就会把往轮产物当成本轮「已投」。带内多于 1 张直接停。
3. 测量口径唯一实现仍是 工具/reinject_2026_11_05/measure_images.py 的 measure()（importlib 复用，不复制粘贴一份阈值）。
4. C136：容器画像不按出图通道成立。本轮真图实测 caBX=0／iTXt=1（见 ledger.json 第 1 轮 rows），
   所以占格只要求「AIGC 标识至少其一在位」——旧的 `cabx == 1` 会把合规图判红。

用法：python 工具/reshoot_campaign_2026_11_06/verify_round.py <回绑源> [R1|R2|R4]
     回绑源两种形态：① 单份会话 jsonl 路径（老调用）；② 逗号分隔的多份 jsonl；
     ③ 指向 transcript 登记件（*.json，含 transcripts 字典）——登记件里在盘的逐份扫，
     不在盘的只报「回绑源缺失 N 份」，不拿缺失当通过。
     ④ 逗号分隔的混合清单（登记件与 jsonl 混写）：R1 组现在的发送面是「264 主向 ＋ 48 补投」两轮，
     回绑源就是两份登记件并列（transcripts_r1.json,transcripts_r3.json）——只给一份会把另一轮的
     实发串当没投过，与只读主台账是同一类假绿。
     R4 组（画风母图臂）的 body 存的是「前导声明一行＋现串正文逐字」整串，逐字判据比的就是这一整串；
     正文摘要在台账 sha256 字段（绑定按 C135 用它的），两者必然不同，不许拿正文摘要去核盘面串。
     组别不写＝R2，沿用老调用。两组的送入串台账、读数与轮次台账分档，
     免得 R1 一轮把 R2 的 round_readings.json／ledger.json 覆写掉。
     R2 的送入串面是「试点 4 条 + 全量并集」两份台账合成，缺全量那份直接停手——
     「闸门看不见全量串」正是并轨要消灭的状态，不许静默降级成只读试点。
"""
import datetime
import io
import json
import os
import re
import sys
import importlib.util
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
WORKSPACE = os.path.abspath(os.path.join(ROOT, '..'))
IMG_DIR = os.path.join(WORKSPACE, 'vibe_images')

# 档串与送入串台账一一对应；build_send_bodies.py 的 SUFFIX/LEDGER 是本表的前置口径。
# bodies_extra＝该组的并集补充台账（仓内新文件，不动被逐字节钉住的试点那份）。写成列表是因为 R1 组的
# 发送面已经有三份：试点/证据那份（逐字节钉）＋ 264 主向全量 ＋ 48 条补投（C139 后用户「都开」那一轮）。
# 少读一份就是把补投过的条目当没投过——并轨口径同 §55.17，缺文件当场停手，不静默降级。
GROUPS = {
    'R2': {'suffix': 'C133冻结重投-v01', 'bodies': 'send_bodies_r1.json',
           'bodies_extra': ['send_bodies_r2_full.json'],
           'readings': 'round_readings.json', 'ledger': 'ledger.json'},
    'R1': {'suffix': 'C138主向重投-v01', 'bodies': 'send_bodies_r1_primary.json',
           'bodies_extra': ['send_bodies_r1_evidence.json', 'send_bodies_r1_catchup.json'],
           'readings': 'round_readings_r1.json', 'ledger': 'ledger_r1.json'},
    # R4＝画风母图臂（图生图）：送入串多一行前导声明，body 存的是「前导＋正文」整串，
    # 台账里 sha256 仍是冻结基准的正文摘要（绑定按 C135 用它的），send_sha256 才是盘面真实发出去那串的摘要。
    'R4': {'suffix': 'C154母图重投-v01', 'bodies': 'send_bodies_r4.json',
           'bodies_extra': ['send_bodies_r4_evidence.json'],
           'readings': 'round_readings_r4.json', 'ledger': 'ledger_r4.json'},
}
LEDGER_DECL = {
    'R2': '重投放量逐轮台账（R2 绑定关口组）。每轮一条，只追加不改写历史；'
          '判废结论由人工目视给出，本台账只登记机械取证项与人工结论字段（人工结论为空即未给）。',
    'R1': '重投放量逐轮台账（R1 画风判废组，每条目只投主向 1 格）。每轮一条，只追加不改写历史；'
          '判废结论由人工目视给出，本台账只登记机械取证项与人工结论字段（人工结论为空即未给）。',
    'R4': '重投放量逐轮台账（R4 画风母图臂组，每条目主向 1 格＋1 张跨题材画风母图）。每轮一条，'
          '只追加不改写历史；判废结论由人工目视给出，本台账只登记机械取证项与人工结论字段'
          '（人工结论为空即未给）。本组的「母图相符」核的是 ImageGen 实调里 images 那一路文件名，'
          '漏传母图＝投成了裸串，逐字串面照样对得上，只有这一列能判红。',
}


def load_measure(root=ROOT):
    spec = importlib.util.spec_from_file_location(
        'm', os.path.join(root, '工具', 'reinject_2026_11_05', 'measure_images.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def sent_prompts(jsonl):
    """扫会话 jsonl，收全部 ImageGen 的 tool_use input（含 name/prompt/size）。"""
    out = []

    def walk(o):
        if isinstance(o, dict):
            if o.get('type') == 'tool_use' and o.get('name') == 'ImageGen':
                out.append(o.get('input') or {})
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for line in io.open(jsonl, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        walk(rec)
    return out


def resolve_sources(arg):
    """回绑源展开：逗号分隔的清单，每一项既可以是 transcript 登记件（*.json，取其 transcripts 字典），
    也可以是单份会话 jsonl；两种形态可以混着写（R1 一轮的登记件 ＋ 补投一轮的登记件）。

    返回 (在盘路径列表, 缺失路径列表)。登记件的形态是本轮并轨的前提——放量改子代理分片投放后，
    逐字回绑的正源不再是单份主会话 jsonl，缺失必须显式计数，不能静默少扫。
    """
    paths = set()
    for token in [t.strip() for t in str(arg).split(',') if t.strip()]:
        if token.endswith('.json'):
            paths.update(sorted(set(json.load(io.open(token, encoding='utf-8'))['transcripts'].values())))
        else:
            paths.add(token)
    paths = sorted(paths)
    hit = [p for p in paths if os.path.exists(p)]
    gone = [p for p in paths if p not in hit]
    return hit, gone


def merge_bodies(here, cfg, group):
    """主台账 + 全部并集补充台账合成读取面；同 ID 两边都在时正文必须逐字相同。"""
    bodies = json.load(io.open(os.path.join(here, cfg['bodies']), encoding='utf-8'))
    extra_names = cfg.get('bodies_extra') or []
    if isinstance(extra_names, str):   # 历史形态：单份字符串仍按一份补充台账处理
        extra_names = [extra_names]
    merged_from = [cfg['bodies']]
    for extra_name in extra_names:
        p = os.path.join(here, extra_name)
        assert os.path.exists(p), ('%s 组缺并集补充台账 %s：本组的实发串面在 %d 份文件里，'
                                   '只读主台账等于把补充条目当没投过（并轨口径见 设计/2026-11-03-待办移交清单.md §55.17；'
                                   'R1 的 evidence 补双发条目的投次、catchup 补 C139 后 48 条「非新画风／缺图」补投；'
                                   'R4 的 evidence 补 D13 那次 images 形态校验失败的双发投次）'
                                   % (group, extra_name, 1 + len(extra_names)))
        extra = json.load(io.open(p, encoding='utf-8'))
        clash = sorted(set(bodies) & set(extra))
        for eid in clash:
            assert bodies[eid]['body'] == extra[eid]['body'], (
                eid, '两份台账同 ID 正文分叉：串面出现第二条真源，先定谁是正源再谈核验')
            assert bodies[eid]['send_name'] == extra[eid]['send_name'], (eid, '两份台账同 ID 发名分叉')
        for eid, rec in extra.items():
            merged = dict(bodies[eid]) if eid in bodies else dict(rec)
            merged.update({k: v for k, v in rec.items() if k in ('投次', '作废发起', '作废删除', '点单', '复投')})
            merged.setdefault('投次', 1)
            bodies[eid] = merged
        merged_from.append(extra_name)
    for rec in bodies.values():
        rec.setdefault('投次', 1)
    return bodies, merged_from


def run(group, jsonl, here=HERE, root=ROOT, img_dir=IMG_DIR, measure=None):
    cfg = GROUPS[group]
    if measure is None:
        measure = load_measure(root).measure
    bodies, merged_from = merge_bodies(here, cfg, group)
    wrong = sorted(k for k, v in bodies.items() if not v['send_name'].endswith('-' + cfg['suffix']))
    assert not wrong, ('%s 组台账 %s 里有 %d 条发名不带本组档串 %s（示例 %s）：'
                       '读错组会把别组的落盘算成本轮「已投」'
                       % (group, cfg['bodies'], len(wrong), cfg['suffix'], wrong[:3]))
    snap = json.load(io.open(os.path.join(root, '数据', '提示词基准冻结.json'), encoding='utf-8'))
    floor = int(snap['frozen_at_ms'])

    sources, missing = resolve_sources(jsonl)
    prompts = []
    for p in sources:
        prompts.extend(sent_prompts(p))
    by_name = {}
    for p in prompts:
        by_name.setdefault(p.get('name'), []).append(p)

    rows = []
    rc = 0
    for eid, ref in sorted(bodies.items()):
        name = ref['send_name']
        sends = int(ref['投次'])
        uses = by_name.get(name, [])
        if len(uses) != sends:
            print('✗ %s 回绑源里按名 %s 找到 %d 次发起（台账投次=%d%s）'
                  % (eid, name, len(uses), sends,
                     '，另有缺失回绑源 %d 份' % len(missing) if missing else ''))
            rc = 1
            continue
        verbatim_uses = [u for u in uses if (u.get('prompt') or '') == ref['body']]
        drifted = len(uses) - len(verbatim_uses)
        # 「作废发起」只数串面不符的发次。images 形态被工具校验挡下那种作废（prompt 仍逐字相等、零产物）
        # 由「投次」与「冻结带内落盘恒 1 枚」承载，往这一列填数会让 drifted(0)≠known_drift(1) 判红（D13 实测）。
        known_drift = int(ref.get('作废发起', 0))
        verbatim = len(verbatim_uses) >= 1 and drifted == known_drift
        # 母图臂的第二道判据：逐字串对了不代表投的就是本轮那条路线——漏传 images 会投成裸串（探针实测出照片），
        # 而裸串那次的 prompt 与本轮逐字串只差前导一行，前导在的逐枚必然带 images，所以按文件名核 images。
        ref_base = os.path.basename(str(ref.get('ref_image') or ''))
        ref_ok = True
        if ref_base:
            ref_ok = any(any(os.path.basename(str(x.get('source') if isinstance(x, dict) else x)) == ref_base
                             for x in (u.get('images') or [])) for u in verbatim_uses)
        files = []
        if os.path.isdir(img_dir):
            for f in os.listdir(img_dir):
                if not f.startswith(name + '_'):
                    continue
                m = re.match(r'^(.+)_(1\d{12})_[0-9a-f]{8}\.png$', f)
                if m and int(m.group(2)) >= floor:
                    files.append((int(m.group(2)), f))
        if len(files) != 1:
            print('✗ %s 冻结带内（ts ≥ %d）落盘 %d 张（投次=%d；被作废的枚必须逐条登记进「作废删除」，'
                  '落盘面恒为 1 枚）：%s' % (eid, floor, len(files), sends, [f for _, f in files]))
            rc = 1
            continue
        ts, fname = files[0]
        r = measure(Path(os.path.join(img_dir, fname)))
        declared = ref['size']
        size_match = r['dims'] == declared
        cont = r['container']
        container_ok = cont['cabx'] >= 1 or cont['itxt'] >= 1
        row = {
            'id': eid, 'file': fname, 'ts_ms': ts,
            'ts_text': datetime.datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            '逐字相等': verbatim, 'dims': r['dims'], 'declared_size': declared, 'size_match': size_match,
            'bytes': r['bytes'], 'sha256_12': r['sha256_12'], 'container': cont,
            'p99_lum': r['p99_lum'], 'fine_var_full': r['fine_var_full'], 'sun_blob_px': r['sun_blob_px'],
            'replaced_cell': ref['replaced_cell'], 'status_before': ref['status_before'],
            '投次': sends, '逐字发起数': len(verbatim_uses), '非逐字发起数': drifted,
            '登记作废发起数': known_drift,
            '母图相符': ref_ok,
            '作废删除': ref.get('作废删除', []),
        }
        rows.append(row)
        flag = '✓' if (verbatim and size_match and container_ok and ref_ok) else '✗'
        if flag == '✗':
            rc = 1
        print('%s %s｜%s｜%s｜逐字相等=%s 投次=%d（逐字%d／非逐字%d，登记作废发起%d）尺寸符=%s caBX=%s／iTXt=%s 母图相符=%s sha12=%s'
              % (flag, eid, row['ts_text'], r['dims'], verbatim, sends,
                 len(verbatim_uses), drifted, known_drift, size_match, cont['cabx'], cont['itxt'],
                 ref_ok, r['sha256_12']))

    if missing:
        print('✗ 回绑源缺失 %d 份（登记件里有名、在盘找不到）：%s' % (len(missing), missing[:5]))
        rc = 1

    out = {'frozen_at': snap['frozen_at'], 'frozen_at_ms': floor, 'rows': rows,
           '统计面': {'组别': group, '档串': cfg['suffix'], '送入串台账': cfg['bodies'],
                      '送入串台账并集': merged_from,
                      '本轮发图串条数': len(bodies),
                      '投次合计': sum(int(v['投次']) for v in bodies.values()),
                      '复投条目数': sum(1 for v in bodies.values() if int(v['投次']) > 1),
                      '登记作废发起合计': sum(int(v.get('作废发起', 0)) for v in bodies.values()),
                      '实测非逐字发起合计': sum(x['非逐字发起数'] for x in rows),
                      '作废删除枚数合计': sum(len(v.get('作废删除', [])) for v in bodies.values()),
                      '回绑成功条数': sum(1 for x in rows if x['逐字相等']),
                      '母图相符条数': sum(1 for x in rows if x['母图相符']),
                      '落盘在冻结带内条数': len(rows),
                      '回绑源形态': 'transcript登记件' if str(jsonl).endswith('.json') else 'jsonl清单',
                      '回绑源在盘份数': len(sources),
                      '回绑源缺失份数': len(missing),
                      '回绑源缺失清单': missing,
                      '会话jsonl': jsonl}}
    with io.open(os.path.join(here, cfg['readings']), 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
        fp.write('\n')

    # 台账：逐轮追加，不覆盖历史
    ledger_path = os.path.join(here, cfg['ledger'])
    ledger = json.load(io.open(ledger_path, encoding='utf-8')) if os.path.exists(ledger_path) else {
        'declaration': LEDGER_DECL[group], 'rounds': []}
    ts_now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    seq = len(ledger['rounds']) + 1
    ledger['rounds'].append({
        '轮次': seq, '登记时刻': ts_now, '组别': group, '档串': cfg['suffix'],
        'frozen_at_ms': floor, '本轮发起条目': sorted(bodies),
        '送入串台账并集': merged_from,
        '投次合计': sum(int(v['投次']) for v in bodies.values()),
        '复投条目': sorted(k for k, v in bodies.items() if int(v['投次']) > 1),
        '回绑源形态': 'transcript登记件' if str(jsonl).endswith('.json') else 'jsonl清单',
        '回绑源在盘份数': len(sources), '回绑源缺失份数': len(missing),
        '落盘与回绑': rows,
        '人工目视结论': {}, '判废': [], '回填': False,
    })
    with io.open(ledger_path, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(ledger, fp, ensure_ascii=False, indent=1)
        fp.write('\n')
    print('台账第 %d 轮登记完成：%s｜rows %d｜条数 %d（投次合计 %d／复投 %d）｜回绑源在盘 %d 份、缺失 %d 份｜%s 与 %s 已写'
          % (seq, HERE, len(rows), len(bodies), sum(int(v['投次']) for v in bodies.values()),
             sum(1 for v in bodies.values() if int(v['投次']) > 1), len(sources), len(missing),
             cfg['readings'], cfg['ledger']))
    return rc


def main():
    if len(sys.argv) not in (2, 3):
        print('用法：verify_round.py <回绑源> [R1|R2|R4]（不写＝R2）；'
              '回绑源＝单份会话 jsonl／逗号分隔多份／transcript 登记件 *.json')
        return 2
    group = sys.argv[2] if len(sys.argv) == 3 else 'R2'
    if group not in GROUPS:
        print('组别只认 %s，实测 %s' % ('／'.join(sorted(GROUPS)), group))
        return 2
    try:
        return run(group, sys.argv[1])
    except AssertionError as e:
        print('✗ 投后核验停手：%s' % e)
        return 1


if __name__ == '__main__':
    sys.exit(main())
