#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C149 补记第六块：浮层 backdrop-filter 遮盖平台 AIGC 角标（目视查出、同日修掉）。

与 fix_c149_badge_band.py 同族：锚点在 raw JSON 里必须命中恰 1 次、不整份 re-dump；
读写按字节解码后以 newline='' 落盘，避免把这份盘上 CRLF 的真源静默降级成 LF。
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / '数据' / '设定裁定记录.json'

EDITS = [
    ('实测真会把关。',
     '实测真会把关。(6) **浮层 `backdrop-filter` 遮盖平台 AIGC 角标——目视查出、同日修掉**——R2 回填后的 '
     'HTML 叠字目视（6 张整页 clip 截图 768×1024；挑样面＝台标带全量实测最靠内的 3 张 idx091／idx086／idx074'
     '＋本轮由占位窗转为叠章的兑换卡 idx007＋模板正面对照 idx012＋老实景卡 L009）发现：`.card .panel` 的 '
     '`blur(6px)` 把主图右下角平台强制「AI生成」角标糊成三团亮斑、不可辨认（该卡角标实测上沿 1024−52.6＝**971.4 px**，'
     '浮层上沿 **973.5 px**，正压在角标上），属遮盖 AIGC 标识的合规红线。修法＝从渲染器 CSS 删掉 `backdrop-filter` 与 '
     '`--panel-blur`，浮层保持用户点单的 `rgba(0,0,0,.3)`（暗黑色 70% 透明）；改后 `工具/build_card_html.py` 现 13785 字节／'
     '`34d208757df2`，`python 工具/build_card_html.py` 重生成读数 卡数 124（OK 114／非 OK 10）、有主图 114／占位窗 10、'
     '模板面 10／实景待投 0，`card.css`／`index.html`／`template.html` 与 124 个 `cards/*.html` 的 `backdrop-filter` 命中 **0**；'
     '同一裁区改前 `cmp_asis_zoom.png` 角标不可读、改后 `r2_after_zoom.png` 逐笔清晰，浮层带亮度均值差 ≤0.2、文案最亮像素同为 '
     '236（去模糊对文案可读性没有代价）。新判据 `test_panel_does_not_blur_over_the_aigc_badge` 让 `工具/test_build_card_html.py` '
     '到 **18 条／13487 字节／`8da937eee60a`**；上文 (5) 的「53 档 Ran 17／OK」是抬带那一轮当时的读数，本条落地后同一文件基线为 18 条。'),
    ('规范第八节按轮取现值、本条不抄第二份。',
     '规范第八节按轮取现值、本条不抄第二份。(5) 浮层的 `backdrop-filter` 是渲染器正式化时我自己加上去的，不在用户点单里'
     '（用户只点了「暗黑色的70%透明」），而它恰好落在合规红线上——平台强制的 AIGC 角标不得裁剪、遮盖或修补。**为什么机械判据'
     '全绿仍然漏掉它**：那一轮取到的全是几何与尺寸读数（`.bg` 包围盒恒等 (0,0,768,1024)、`.seal` 框逐边相等、PIL 逐张 (768,1024)），'
     '没有一条看像素内容；角标可读性只有整页截图＋裁区放大才看得见，而元素级 `query_selector().screenshot()` 在 `backdrop-filter` '
     '上还会自己产出假黑块，必须用整页 clip 截图才是可信证据（本轮据此复核过一轮）。两组变异各自当场判红一次（加回 blur／把底色 '
     '`.3` 改成 `.85` 不透明），且逐行核对挂名确为这条新用例本身、不是别的用例顺带挂。'),
    ('本轮提交范围需先报再提交、**推送未获授权**。',
     '交付面：有文案版 114 张的浮层观感由「磨砂玻璃」变为「纯半透明」（角标清晰、文案读数不变），`数据/卡面HTML/` 五件产物全部'
     '重生成——`card.css` 2653 字节／`360c827c5c4e`、`index.html` 161929／`4a7e5896c416`、`template.html` 765／`0e03c629b5f6`、'
     '`cards.json` 60079／`9e77c402ea58`、`cards/*.html` 124 个；任何自行拼这套叠层的消费方同样不许给浮层加背景模糊，判据钉在 '
     '`test_panel_does_not_blur_over_the_aigc_badge`。本轮提交范围需先报再提交、**推送未获授权**。'),
]


def main():
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
    changed = [k for k in ('裁定', '原因', '影响') if after[148][k] != before[148][k]]
    assert set(changed) == {'裁定', '原因', '影响'}, changed

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
