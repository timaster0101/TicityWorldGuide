# -*- coding: utf-8 -*-
"""R4 放量派单登记：把「我起的分片名」对回 AppData 会话区的 transcript 路径，两份登记件落仓内。

为什么不能凭记忆写路径：子代理的 transcript 文件名是 `agent-<类型>-<16位哈希>.jsonl`，
起的名（invocationName）只在同目录的 `.meta.json` 里。放量一改分片投放，逐字回绑的正源就不再是主会话 jsonl
（§55.17 那条教训），登记晚一轮就得靠 glob 猜——猜错的代价是把没扫到的串当成「未投过」。

两份产物各归各家：
  · 数据/卡面主图提示词3x4/派单登记R4.json —— 卡面侧，bind_check_card_r4.py 按这份扫 transcript；
  · 工具/reshoot_campaign_2026_11_06/transcripts_r4.json —— 主链侧，verify_round.py 的回绑源登记件形态。
不在盘的份数一律显式计数（缺失不等于通过），名单外的 invocationName 不混进来。
"""
import glob
import hashlib
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.abspath(os.path.join(ROOT, '..'))
HOME = os.path.expanduser('~')
# 会话根不钉死：同一个仓库的会话会随 AppData 目录版本分叉（.qoder-cn 与 .qoder 两套工程键，
# 后者还带 workspace slug 后缀），钉单棵树一律判「未反查到」，代价是放量轮的实发串扫不到。
SLUG_GLOBS = [os.path.join(HOME, base, 'projects', pat) for base, pat in (
    ('.qoder-cn', 'C--Users-TIMASTER-Documents-Qoder-2026-10-29-c8c10ff8'),
    ('.qoder', 'C--Users-TIMASTER-Documents-Qoder-2026-10-29-c8c10ff8*'))]
NAMES = os.path.join(WORKSPACE, '_scratch_cardref', 'r4_dispatch_names.json')
CARD_OUT = os.path.join(ROOT, '数据', '卡面主图提示词3x4', '派单登记R4.json')
MAIN_OUT = os.path.join(ROOT, '工具', 'reshoot_campaign_2026_11_06', 'transcripts_r4.json')


def fwd(p):
    return str(p).replace(os.sep, '/')


def session_dirs():
    """会话目录实测派生：项目目录里带 subagents/ 或带同名主会话 jsonl 的那一层才算，
    memory 一类子目录自然落选；不在盘的根直接跳过，不报错也不留空档。"""
    out = []
    for proj in SLUG_GLOBS:
        for d in glob.glob(os.path.join(proj, '*')):
            if not os.path.isdir(d):
                continue
            if os.path.isdir(os.path.join(d, 'subagents')) or os.path.isfile(d + '.jsonl'):
                out.append(os.path.abspath(d))
    return sorted(set(out))


def main_jsonls():
    return sorted(fwd(d + '.jsonl') for d in session_dirs() if os.path.isfile(d + '.jsonl'))


def find(name):
    """按 invocationName 反查 agentId 与 transcript 路径；同名多份（重试过）全部列出，取 max mtime 由消费方决定。"""
    hits = []
    for sub in [os.path.join(d, 'subagents') for d in session_dirs()]:
      for meta in sorted(glob.glob(os.path.join(sub, '*.meta.json'))):
        try:
            with io.open(meta, encoding='utf-8') as fp:
                d = json.load(fp)
        except ValueError:
            continue
        if d.get('invocationName') == name:
            stem = os.path.basename(meta)[:-len('.meta.json')]
            path = os.path.join(sub, stem + '.jsonl')
            with open(path, 'rb') as _fh:
                hits.append({'agentId': stem[len('agent-'):] if stem.startswith('agent-') else stem,
                             'transcript': os.path.abspath(path).replace('\\', '/'),
                             '在盘': os.path.isfile(path),
                             '字节': os.path.getsize(path) if os.path.isfile(path) else 0,
                             'sha256_12': hashlib.sha256(_fh.read()).hexdigest()[:12]
                             if os.path.isfile(path) else ''})
    return hits


def main():
    if not os.path.isfile(NAMES):
        print('✗ 派单名单缺失 %s：先在本文件里逐片登记 invocationName 再跑登记' % NAMES)
        return 1
    with io.open(NAMES, encoding='utf-8') as _fp:
        doc = json.load(_fp)
    card, main = [], []
    for i, name in enumerate(doc['卡面'], 1):
        card.append({'分片': i, '派单名': name, '命中': find(name)})
    for i, name in enumerate(doc['主链'], 1):
        main.append({'分片': i, '派单名': name, '命中': find(name)})
    groups = [('卡面', card), ('主链', main)]
    for label, rows in groups:
        unhit = [r['派单名'] for r in rows if not r['命中']]
        gone = [r['派单名'] for r in rows if r['命中'] and all(not h['在盘'] for h in r['命中'])]
        print('%s 片 %d｜反查到 agentId %d｜未反查到 %d %s｜transcript 不在盘 %d %s'
              % (label, len(rows), len(rows) - len(unhit), len(unhit), ' '.join(unhit) or '—',
                 len(gone), ' '.join(gone) or '—'))
    transcripts = {}
    for r in main:
        for h in r['命中']:
            if h['在盘']:
                transcripts['%s-%s' % (r['分片'], h['agentId'])] = h['transcript']
    # 显式源：单条纠偏复投有时由**没起名的子代理**投出（invocationName 就是 agent 类型名，
    # 按名反查会把几十份历史 transcript 一起拖进来，虚增别的条号投次）。这类份数只能逐条点名进名单。
    explicit = []
    for item in doc.get('主链显式transcript', []):
        p = fwd(os.path.abspath(item['transcript'] if isinstance(item, dict) else item))
        if not os.path.isfile(p):
            print('✗ 显式回绑源不在盘 %s：显式点名不做静默降级，停手' % p)
            return 1
        stem = os.path.basename(p)[:-len('.jsonl')]
        agent_id = stem[len('agent-'):] if stem.startswith('agent-') else stem
        key = 'explicit-%s-%s' % (item.get('派单名') or '', agent_id)
        transcripts[key] = p
        explicit.append(key)
    # 主会话 jsonl 折进 transcripts，而不是只留单值键：verify_round.py 的 resolve_sources 只取
    # transcripts.values()（:115），探针与纠偏复投都由主会话直投，留在单值键里等于没登记。
    mains = main_jsonls()
    for i, p in enumerate(mains, 1):
        transcripts['main-%02d-%s' % (i, os.path.basename(p)[:-5][:8])] = p
    newest = max(mains, key=os.path.getmtime) if mains else ''
    with io.open(MAIN_OUT, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump({'declaration': 'R4 主链放量（310 条画风母图臂，档串 C154母图重投-v01）逐字回绑的正源清单：'
                                  '各分片子代理 transcript ＋ 各会话主 jsonl（键面以 main- 打头）。'
                                  '路径按派单名（invocationName）在会话区 *.meta.json 跨会话根反查得到，'
                                  '会话根实测派生自 SLUG_GLOBS、不钉单棵树；跨会话不保证还在，'
                                  'verify_round.py 对缺失份数显式判红，补投前要重新登记当轮路径。',
                   'group': 'R4', 'suffix': 'C154母图重投-v01',
                   'registered_at': doc.get('登记时刻', ''),
                   '派单名数': len(doc['主链']), '反查到 agentId 数': len({h['agentId'] for r in main for h in r['命中']}),
                   '显式点名份数': len(explicit), '显式点名键': explicit,
                   'transcripts': transcripts,
                   '主会话jsonl': newest, '主会话jsonl清单': mains},
                  fh, ensure_ascii=False, indent=1)
        fh.write('\n')
    with io.open(CARD_OUT, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump({'declaration': 'card3x4_R4（85 枚画风判废母图臂重投）的派单登记：分片→派单名→agentId→transcript，'
                                  '由 工具/register_r4_transcripts.py 现算，bind_check_card_r4.py 按本件扫逐字回绑。'
                                  '主会话jsonl清单 一份不缺地并列进回绑源：主会话直投（分片通道禁用时的补投、'
                                  '探针、纠偏）只发生在主会话 jsonl 里，只钉单份历史会话会把别的会话当成没投过。',
                   '登记时刻': doc.get('登记时刻', ''), '放行原话': doc.get('放行原话', ''),
                   '覆盖面': '成员面＝数据/卡面主图提示词3x4/投放台账R4.json 的 85 键',
                   '分片数': len(card), '卡面分片': card, '主链分片': main,
                   '主会话jsonl': mains[len(mains) - 1] if mains else '', '主会话jsonl清单': mains},
                  fh, ensure_ascii=False, indent=1)
        fh.write('\n')
    print('登记件落盘：主链 transcript 在盘 %d 份 → %s；卡面分片明细 → %s'
          % (len(transcripts), MAIN_OUT.replace('\\', '/'), CARD_OUT.replace('\\', '/')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
