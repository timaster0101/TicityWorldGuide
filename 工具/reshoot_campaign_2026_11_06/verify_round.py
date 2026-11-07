# -*- coding: utf-8 -*-
"""重投放量·投后核验：逐字回绑 → 落盘取证 → 测量 → 台账，任何一环不等即停，不写任何真源。

四道历史教训写死在这里：
1. §32.4 发送侧字符损坏：实发串必须与会话 jsonl 里 tool_use 的 prompt 逐字相等，只看「投过了」不算。
2. §54 关口B 的分带依据换成 C133 的 frozen_at_ms：同一个 ID 现在挂着多枚同名/异名历史文件，
   不带内闸门就会把往轮产物当成本轮「已投」。带内多于 1 张直接停。
3. 测量口径唯一实现仍是 工具/reinject_2026_11_05/measure_images.py 的 measure()（importlib 复用，不复制粘贴一份阈值）。
4. C136：容器画像不按出图通道成立。本轮真图实测 caBX=0／iTXt=1（见 ledger.json 第 1 轮 rows），
   所以占格只要求「AIGC 标识至少其一在位」——旧的 `cabx == 1` 会把合规图判红。

用法：python 工具/reshoot_campaign_2026_11_06/verify_round.py <会话jsonl路径> [R1|R2]
     组别不写＝R2，沿用老调用。两组的送入串台账、读数与轮次台账分档，
     免得 R1 一轮把 R2 的 round_readings.json／ledger.json 覆写掉。
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
GROUPS = {
    'R2': {'suffix': 'C133冻结重投-v01', 'bodies': 'send_bodies_r1.json',
           'readings': 'round_readings.json', 'ledger': 'ledger.json'},
    'R1': {'suffix': 'C138主向重投-v01', 'bodies': 'send_bodies_r1_primary.json',
           'readings': 'round_readings_r1.json', 'ledger': 'ledger_r1.json'},
}
LEDGER_DECL = {
    'R2': '重投放量逐轮台账（R2 绑定关口组）。每轮一条，只追加不改写历史；'
          '判废结论由人工目视给出，本台账只登记机械取证项与人工结论字段（人工结论为空即未给）。',
    'R1': '重投放量逐轮台账（R1 画风判废组，每条目只投主向 1 格）。每轮一条，只追加不改写历史；'
          '判废结论由人工目视给出，本台账只登记机械取证项与人工结论字段（人工结论为空即未给）。',
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


def run(group, jsonl, here=HERE, root=ROOT, img_dir=IMG_DIR, measure=None):
    cfg = GROUPS[group]
    if measure is None:
        measure = load_measure(root).measure
    bodies = json.load(io.open(os.path.join(here, cfg['bodies']), encoding='utf-8'))
    wrong = sorted(k for k, v in bodies.items() if not v['send_name'].endswith('-' + cfg['suffix']))
    assert not wrong, ('%s 组台账 %s 里有 %d 条发名不带本组档串 %s（示例 %s）：'
                       '读错组会把别组的落盘算成本轮「已投」'
                       % (group, cfg['bodies'], len(wrong), cfg['suffix'], wrong[:3]))
    snap = json.load(io.open(os.path.join(root, '数据', '提示词基准冻结.json'), encoding='utf-8'))
    floor = int(snap['frozen_at_ms'])

    prompts = sent_prompts(jsonl)
    by_name = {}
    for p in prompts:
        by_name.setdefault(p.get('name'), []).append(p.get('prompt') or '')

    rows = []
    rc = 0
    for eid, ref in sorted(bodies.items()):
        name = ref['send_name']
        uses = by_name.get(name, [])
        if len(uses) != 1:
            print('✗ %s 会话里按名 %s 找到 %d 次发起（必须恰 1 次）' % (eid, name, len(uses)))
            rc = 1
            continue
        verbatim = uses[0] == ref['body']
        files = []
        if os.path.isdir(img_dir):
            for f in os.listdir(img_dir):
                if not f.startswith(name + '_'):
                    continue
                m = re.match(r'^(.+)_(1\d{12})_[0-9a-f]{8}\.png$', f)
                if m and int(m.group(2)) >= floor:
                    files.append((int(m.group(2)), f))
        if len(files) != 1:
            print('✗ %s 冻结带内（ts ≥ %d）落盘 %d 张：%s' % (eid, floor, len(files), [f for _, f in files]))
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
        }
        rows.append(row)
        flag = '✓' if (verbatim and size_match and container_ok) else '✗'
        if flag == '✗':
            rc = 1
        print('%s %s｜%s｜%s｜逐字相等=%s 尺寸符=%s caBX=%s／iTXt=%s sha12=%s'
              % (flag, eid, row['ts_text'], r['dims'], verbatim, size_match, cont['cabx'], cont['itxt'],
                 r['sha256_12']))

    out = {'frozen_at': snap['frozen_at'], 'frozen_at_ms': floor, 'rows': rows,
           '统计面': {'组别': group, '档串': cfg['suffix'], '送入串台账': cfg['bodies'],
                      '本轮发图串条数': len(bodies), '回绑成功条数': sum(1 for x in rows if x['逐字相等']),
                      '落盘在冻结带内条数': len(rows),
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
        '落盘与回绑': rows,
        '人工目视结论': {}, '判废': [], '回填': False,
    })
    with io.open(ledger_path, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(ledger, fp, ensure_ascii=False, indent=1)
        fp.write('\n')
    print('台账第 %d 轮登记完成：%s｜rows %d｜%s 与 %s 已写'
          % (seq, HERE, len(rows), cfg['readings'], cfg['ledger']))
    return rc


def main():
    if len(sys.argv) not in (2, 3):
        print('用法：verify_round.py <会话jsonl路径> [R1|R2]（不写＝R2）')
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
