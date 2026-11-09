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
SESSION = os.path.expanduser('~') + r'/.qoder-cn/projects/C--Users-TIMASTER-Documents-Qoder-2026-10-29-c8c10ff8/6b39cfae-e2ed-48a8-81fd-0af6e4887eda'
SUBDIR = os.path.join(SESSION, 'subagents')
NAMES = os.path.join(WORKSPACE, '_scratch_cardref', 'r4_dispatch_names.json')
CARD_OUT = os.path.join(ROOT, '数据', '卡面主图提示词3x4', '派单登记R4.json')
MAIN_OUT = os.path.join(ROOT, '工具', 'reshoot_campaign_2026_11_06', 'transcripts_r4.json')


def find(name):
    """按 invocationName 反查 agentId 与 transcript 路径；同名多份（重试过）全部列出，取 max mtime 由消费方决定。"""
    hits = []
    for meta in sorted(glob.glob(os.path.join(SUBDIR, '*.meta.json'))):
        try:
            d = json.load(io.open(meta, encoding='utf-8'))
        except ValueError:
            continue
        if d.get('invocationName') == name:
            stem = os.path.basename(meta)[:-len('.meta.json')]
            path = os.path.join(SUBDIR, stem + '.jsonl')
            hits.append({'agentId': stem[len('agent-'):] if stem.startswith('agent-') else stem,
                         'transcript': os.path.abspath(path).replace('\\', '/'),
                         '在盘': os.path.isfile(path),
                         '字节': os.path.getsize(path) if os.path.isfile(path) else 0,
                         'sha256_12': hashlib.sha256(open(path, 'rb').read()).hexdigest()[:12]
                         if os.path.isfile(path) else ''})
    return hits


def main():
    if not os.path.isfile(NAMES):
        print('✗ 派单名单缺失 %s：先在本文件里逐片登记 invocationName 再跑登记' % NAMES)
        return 1
    doc = json.load(io.open(NAMES, encoding='utf-8'))
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
    with io.open(MAIN_OUT, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump({'declaration': 'R4 主链放量（310 条画风母图臂，档串 C154母图重投-v01）逐字回绑的正源清单：'
                                  '各分片子代理 transcript ＋ 主会话 jsonl。路径按派单名（invocationName）'
                                  '在会话区 *.meta.json 反查得到，跨会话不保证还在；verify_round.py 对缺失份数'
                                  '显式判红，补投前要重新登记当轮路径。',
                   'group': 'R4', 'suffix': 'C154母图重投-v01',
                   'registered_at': doc.get('登记时刻', ''),
                   '派单名数': len(doc['主链']), '反查到 agentId 数': len({h['agentId'] for r in main for h in r['命中']}),
                   'transcripts': transcripts,
                   '主会话jsonl': os.path.abspath(SESSION + '.jsonl').replace('\\', '/')},
                  fh, ensure_ascii=False, indent=1)
        fh.write('\n')
    with io.open(CARD_OUT, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump({'declaration': 'card3x4_R4（85 枚画风判废母图臂重投）的派单登记：分片→派单名→agentId→transcript，'
                                  '由 工具/register_r4_transcripts.py 现算，bind_check_card_r4.py 按本件扫逐字回绑。',
                   '登记时刻': doc.get('登记时刻', ''), '放行原话': doc.get('放行原话', ''),
                   '覆盖面': '成员面＝数据/卡面主图提示词3x4/投放台账R4.json 的 85 键',
                   '分片数': len(card), '卡面分片': card, '主链分片': main},
                  fh, ensure_ascii=False, indent=1)
        fh.write('\n')
    print('登记件落盘：主链 transcript 在盘 %d 份 → %s；卡面分片明细 → %s'
          % (len(transcripts), MAIN_OUT.replace('\\', '/'), CARD_OUT.replace('\\', '/')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
