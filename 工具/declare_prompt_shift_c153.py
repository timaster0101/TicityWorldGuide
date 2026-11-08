# -*- coding: utf-8 -*-
"""给 312 条逐一登记 C153 画风换档的摘要过期申报行（一次性脚本，重钉基准前后各跑一次都会当场报错）。

为什么要这 312 行：C153 把画风段三处措辞从 C122 平滑档回退到 C105 强媒介档，基准一换，
312 条的 `image_prompt_sha256` 不再是「当前串的摘要」而只是「换档前那版基准的摘要」。
`数据/提示词基准冻结.json` 的 declaration 与 `工具/build_prompts.py` 的 review_state 早就把这一格写死成
「降回待复验、不得复制摘要补绑」，生成器只把状态改了、没在人工源留字；
`工具/test_image_assets.py:204` 那条判据要的是「占格了但还没签的条目必须逐条申报摘要过期并复述被维持的那串前 12 位」，
C139 全量代签之后 312 条都是已验收、这一支从未落地过，换档把它整支激活。
没有这 312 行，下一轮读清单的人只能看到「待复验」而看不到它是被哪一次换档降下来的、
维持的是哪一串、要怎样才能重绑——那正是这条判据防的事。

口径与 C139 代签申报一致：抬头点名条目 ID、复述被维持的绑定前 12 位、写明执行人与委托来源原句，
并且如实写「本轮既没重投也没人工目视」。摘要串一律现读，不手抄。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTES_REL = '数据/开图验收备注.json'
MANIFEST_REL = '数据/开图清单.json'
BASELINE_REL = '数据/提示词基准冻结.json'

PREV_BASELINE_12 = 'b74127f6079e'      # 换档前基准总摘要：重钉之后本脚本必须拒跑
HEAD = re.compile(r'^C153画风换档申报([A-Za-z0-9]+)：')
TEMPLATE = (
    'C153画风换档申报{eid}：本条画风段三处（【画风锚点】首句、【全局硬设定】画风句、English tail 风格前缀）'
    '按 C153 由 C122 平滑档回退到 C105 强媒介档，基准随之换档；prompt_sha256 前12位由 {bound12} 变为 {new12}，'
    'image_prompt_sha256 维持原绑定 {bound12}（那是换档前基准 {prev_base} 的串摘要，本轮不撤销、不补绑新串），该绑定已过期。'
    '状态由生成器降回待复验，重绑只能按新串重投或人工逐张复验后再做，本轮两者都未做——'
    '重投属花钱调用、待用户重新放行，人工逐张目视未执行。'
    '范围读数＝312/312（全清单绑定摘要与旧基准快照逐条相等，不等 0 条）。'
    '执行人＝会话代理（受用户 2026-11-09「按甲走」委托登记机械申报，非人工目视；'
    '代价条款为用户所选路线原文「312 条主链提示词全部换档、11-07 已投 264 张的复看结论连带作废重看」）。'
)


def main():
    notes_path = ROOT / NOTES_REL
    raw = notes_path.read_text(encoding='utf-8')
    notes = json.loads(raw)['备注']
    manifest = json.loads((ROOT / MANIFEST_REL).read_text(encoding='utf-8'))
    baseline = json.loads((ROOT / BASELINE_REL).read_text(encoding='utf-8'))

    # 前置断言：本脚本只认「已换档、尚未重钉基准」这一个中间态
    assert baseline['baseline_sha256_12'] == PREV_BASELINE_12, \
        '基准快照已是 %s，本脚本只登记 %s 那次换档，拒跑' % (baseline['baseline_sha256_12'], PREV_BASELINE_12)
    old = {e['id']: e['prompt_sha256'] for e in baseline['entries']}
    items = {i['id']: i for i in manifest['items']}
    assert len(items) == 312 and len(old) == 312, '条数不是 312：清单=%d 快照=%d' % (len(items), len(old))
    already = [eid for eid, rows in notes.items() if any(HEAD.match(r) for r in rows)]
    assert not already, '已存在 C153 申报行 %d 条（%s…），本脚本不重复追加' % (len(already), already[:5])
    mismatched = sorted(eid for eid, it in items.items() if it.get('image_prompt_sha256') != old.get(eid))
    assert not mismatched, '绑定摘要与旧基准快照不一致 %d 条：%s' % (len(mismatched), mismatched[:10])
    not_pending = sorted(eid for eid, it in items.items() if it['status'] != '待复验')
    assert not not_pending, '状态未全部降回待复验 %d 条：%s——先重跑 build_prompts.py' % (len(not_pending), not_pending[:10])

    before_rows = sum(len(v) for v in notes.values())
    for eid, it in items.items():
        notes[eid].append(TEMPLATE.format(
            eid=eid, bound12=it['image_prompt_sha256'][:12], new12=it['prompt_sha256'][:12],
            prev_base=PREV_BASELINE_12))

    # 自证只加了 312 行：把新行剥掉再序列化，必须与原文逐字相同。
    # read_text 走 universal newlines，所以比的是 LF 口径；写盘后另按盘上字节复核 CRLF 译法没多出别的改动。
    stripped = json.loads(raw)
    stripped['备注'] = {eid: [r for r in rows if not HEAD.match(r)] for eid, rows in stripped['备注'].items()}
    assert json.dumps(stripped, ensure_ascii=False, indent=2) + '\n' == raw, \
        '剥掉新行后与原文不逐字相同，说明本脚本动了不该动的字节'
    payload = json.loads(raw)
    payload['备注'] = notes
    new_text = json.dumps(payload, ensure_ascii=False, indent=2) + '\n'
    notes_path.write_text(new_text, encoding='utf-8')
    assert notes_path.read_bytes() == new_text.replace('\n', '\r\n').encode('utf-8'), \
        '盘上字节与序列化结果（CRLF 口径）不符'

    written = json.loads(notes_path.read_text(encoding='utf-8'))['备注']
    after_rows = sum(len(v) for v in written.values())
    assert after_rows == before_rows + 312, '行数增量不是 312：%d → %d' % (before_rows, after_rows)
    for eid, it in items.items():
        row = [r for r in written[eid] if HEAD.match(r)]
        assert len(row) == 1, '%s 的 C153 行不是恰一条' % eid
        assert '维持原绑定 ' + it['image_prompt_sha256'][:12] in row[0], '%s 未复述被维持的绑定前12位' % eid
        assert it['prompt_sha256'][:12] in row[0], '%s 未写明换档后的新摘要前12位' % eid
        assert '图片对应的基准提示词已变化' not in row[0], '%s 的申报行混入了派生原因句' % eid

    print('追加前 %d 键／%d 行／%d 字节' % (len(notes), before_rows, len(raw.encode('utf-8'))))
    print('追加后 %d 键／%d 行／%d 字节' % (len(written), after_rows,
          len(notes_path.read_text(encoding='utf-8').encode('utf-8'))))
    print('盘上字节', notes_path.stat().st_size)
    print('逐条复述绑定前12位：312/312 通过；派生原因句混入：0 条')
    return 0


if __name__ == '__main__':
    sys.exit(main())
