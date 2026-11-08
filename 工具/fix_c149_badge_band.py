#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C149 补记台标带 44→53（C149 首发只写了投放与章径，漏了同轮抬带）。

与 fix_c148_readouts.py 同族：锚点必须在 raw JSON 里命中恰 1 次、不整份 re-dump，
改后断言条数 149／末条 C149／前 148 条 JSON 序列化逐字段未变，并复核行尾数不变。
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / '数据' / '设定裁定记录.json'

EDITS = [
    (
        "可见章面下沿距画布底 208 px 扣台标带 44 后净空 164 px",
        # 首发把 (1) 的净空按当时 80 张实测的 44 档写死了；同轮 114 张重测抬到 53 后这句话就自相矛盾，
        # 就地订正并指向 (5)，不改动句中其余渲染真值。
        "可见章面下沿距画布底 208 px 扣台标带 44 后净空 164 px（此句系本条首发按当时 80 张实测的 44 档写成，"
        "同轮 114 张全量重测后台标带抬至 53、净空随之为 155 px，见下文 (5)）",
    ),
    (
        "index 图例三个数改由记录派生，不再硬写 80／10／34。",
        "index 图例三个数改由记录派生，不再硬写 80／10／34。(5) **台标带随 114 张全量重测抬到 53 px**——"
        "`工具/measure_aigc_badge.py --full-bleed` 的统计面跟着 manifest `status==OK` 走，回填后从 80 张自然扩到 "
        "**114 张逐张全量、非抽样**（检出 38／未检出 76，可检出台标上沿距实景下沿 max 52.6／min 10.9，最靠内的"
        "正是本轮新投的 `职业卡-光伏运维实训-A16`）；`SEAL_BADGE_BAND` 随之由 44 抬到 **53**"
        "（`工具/card_geometry.py` 现 2794 字节／`0ecbac92b5bf`，真源 `数据/台标带实测.json` 39473 字节／"
        "`ae4822d02859`）。抬带前后各跑一次 `工具/test_build_card_html.py`：44 档 **FAILED (failures=1)**、报 "
        "`44 not greater than or equal to 52.6 ：台标带低于实测最靠内的台标上沿`，53 档 **Ran 17／OK**——"
        "§55.29 预留的那条「日后检出更靠内的台标就抬 `SEAL_BADGE_BAND`、逐边判据会跟着把关」实测真会把关。",
    ),
    (
        "扫描数现读 165、不一致 0、判红 0，通过 1125/1125 格。",
        "扫描数现读 165、不一致 0、判红 0，通过 1125/1125 格。几何面：`SEAL_BADGE_BAND` 44→53 只动净空约束、"
        "不动 CSS 三数（`.card .seal` 仍 `27.6%/4%/19%`、渲染真值章框 212.0×212.0、可见章面 (537,627)-(726,816)），"
        "可见章面下沿 816 距画布底 208 px、扣台标带 53 后净空 **155 px**，`test_seal_landing_clears_badge_band_at_measured_box` "
        "的 `vis[3] ≤ 1024−band` 在 53 档仍判绿（816 ≤ 971）。",
    ),
]


def main():
    # 读写都必须带 newline=''：这份真源在盘上是 CRLF，read_text 的通用换行会把 \r\n 译成 \n，
    # 再按 newline='' 写回去就整份降成 LF（§55.29 ⑦ 踩过的那条），所以直接按字节解码。
    raw = P.read_bytes().decode('utf-8')
    before = json.loads(raw)
    assert len(before) == 149 and before[-1]['编号'] == 'C149', '起点不是 149 条／末条 C149'
    disk_before = P.read_bytes()
    crlf_before = disk_before.count(b'\r\n')

    text = raw
    for old, new in EDITS:
        n = text.count(old)
        assert n == 1, '锚点在盘上命中 %d 次，放弃本轮订正：%s' % (n, old[:40])
        text = text.replace(old, new)

    after = json.loads(text)
    assert len(after) == 149 and after[-1]['编号'] == 'C149'
    assert json.dumps(after[:148], ensure_ascii=False, sort_keys=True) == \
        json.dumps(before[:148], ensure_ascii=False, sort_keys=True), '前 148 条内容变了'
    changed = [k for k in ('裁定', '原因', '影响')
               if after[148][k] != before[148][k]]
    assert set(changed) == {'裁定', '影响'}, changed

    with open(P, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)
    disk_after = P.read_bytes()
    print('字节 %d → %d' % (len(disk_before), len(disk_after)))
    print('sha12 %s → %s' % (hashlib.sha256(disk_before).hexdigest()[:12],
                             hashlib.sha256(disk_after).hexdigest()[:12]))
    print('CRLF 行数 %d → %d' % (crlf_before, disk_after.count(b'\r\n')))
    print('C149 改动字段', changed, '／条数 149 末条 C149 前 148 条逐字段未变')


if __name__ == '__main__':
    main()
