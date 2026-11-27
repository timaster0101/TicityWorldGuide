#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""追加裁定 C157（基版一致性：39 座地标层数与高度以此为准，正文外观段对齐名录；docx 第 30 签）。"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / '数据' / '设定裁定记录.json'

RULINGS = [
    {
        "编号": "C157",
        "裁定": "（2026-11-27 基版共享轮；用户对「39 座地标名录与正文读数不一致」的回答原话：「A 正文对齐名录（推荐）」）**数值真源是 `数据/城市空间名录.json`，正文外观段的层数与高度一律向它对齐**。\n\n"
                  "(1) **对齐面**：`工具/build_registry.py` 的阶段 2-B 中高层分层（`MID_RISE_BY_ID`，`build_registry.py:106-120`）把 108 座地标中的 39 座抬进 60—99 米档，只改 `height_m` 与 `floors`；原稿两卷（`分卷/原稿/02-D01-D10.md`、`02-D11-D20.md`）里这 39 句外观段仍是抬升前的旧数。实测例：L001 议事厅名录 17 层 74 米／正文 6 层 32 米；L021 风帆设计工坊 15 层 66 米／10 层 46 米；L025 云栈协作中心 22 层 96 米／6 层 40 米。开图提示词吃的是名录（`数据/开图提示词/L021-风帆设计工坊.txt` 写 `15层`/`66米`），故图集、房价、天际线与名录一致，只有读者看的正文是旧数。\n\n"
                  "(2) **处置**：改 39 句（39 座地标，两卷），层数与高度按名录写入；随后 `工具/compile_book.py` 重生成 `分卷/02-城市片区.md`、`数据/AI地点知识库.json/jsonl`、合订本 md，`工具/export_docx.cjs` 重导 docx（596787 字节／sha12 `f311387cdc2e`／424 页）。\n\n"
                  "(3) **未动**：`数据/开图提示词/` 0 处变化（`git status` 实测），312 条 `prompt_sha256` 与绑定摘要全部不变——本轮改的是正文读数，不是提示词。\n\n"
                  "(4) **docx 第 30 签**：`数据/Word渲染目视.json` 换绑新摘要。机检：424 页中空白 0／整页发暗 0／内容压边 0／稀疏 2 页（p003、p226，节末页）；PDF 文本层逐条复核 39 句改后读数全部命中原文所在页（20 页，40—63）。逐页人眼按用户同日原话「如果是文字的话，就不用检查了，直接过吧」不执行，签内不声称做过人眼。",
        "原因": "基版要共享给他人二创时，读者正文与机器读取的名录必须是同一份数。此前两处并存的原因是「改名录不改正文」的历史操作只保证机器侧一致；而图集与开图提示词都吃名录，唯独合订本正文停在旧数，形成只有读者会踩到的矛盾。三种处置里：改名录回退会推翻阶段 2-B 的天际线分层（60—99 米档 40 条）并连带重算房价与产业读数；先发布后修会把矛盾随基版一起分发；故取「正文对齐名录」——一处真源，其余全部派生。",
        "影响": "39 座地标的正文外观段读数变更（层数与高度）；合订本 md/docx 与分卷 02 重生成；`数据/AI地点知识库` 同步；开图提示词、图集、绑定摘要、图片验收一律不受影响。此后任何派生文本（故事、卡面、视频脚本）的层数与高度以名录为准，正文不再另立一套数。",
    },
]


def main():
    raw = P.read_text(encoding='utf-8')
    before = json.loads(raw)
    assert len(before) == 155, '前置断言失败：现读 %d 条，本脚本只负责追加 C157' % len(before)
    assert before[-1]['编号'] == 'C155', '前置断言失败：末条不是 C155（C156 是批次标签，不是裁定编号）'
    sha_before = hashlib.sha256(raw.encode('utf-8')).hexdigest()

    block = ',\n'.join(json.dumps(r, ensure_ascii=False, indent=2) for r in RULINGS)
    block = '\n'.join(('  ' + ln) if ln.strip() else ln for ln in block.split('\n'))
    tail = '  }\n]\n'
    assert raw.endswith(tail), '前置断言失败：文件尾形态与脚本假设不符'
    new_raw = raw[:-len(tail)] + tail[:-len(']\n')] + ',\n' + block + '\n]\n'

    after = json.loads(new_raw)
    assert len(after) == 156, '写盘前校验失败：解析得 %d 条' % len(after)
    assert [r['编号'] for r in after] == [r['编号'] for r in before] + ['C157'], '编号序列变了'
    assert json.dumps(after[:155], ensure_ascii=False, sort_keys=True) == \
        json.dumps(before, ensure_ascii=False, sort_keys=True), '前 155 条内容变了'

    P.write_text(new_raw, encoding='utf-8')
    written = P.read_text(encoding='utf-8')
    re_parsed = json.loads(written)
    disk = P.read_bytes()
    print('追加前 %d 条／%d 字节／%s' % (len(before), len(raw.encode('utf-8')), sha_before[:12]))
    print('追加后 %d 条／内存口径 %d 字节／%s' % (
        len(re_parsed), len(written.encode('utf-8')),
        hashlib.sha256(written.encode('utf-8')).hexdigest()[:12]))
    print('追加后 盘上口径 %d 字节／%s' % (len(disk), hashlib.sha256(disk).hexdigest()[:12]))
    print('末两条', [r['编号'] for r in re_parsed[-2:]])
    got = re_parsed[155]
    print('C157 与盘上末条逐字段相等：',
          all(got[k] == RULINGS[0][k] for k in RULINGS[0]) and set(got) == set(RULINGS[0]))


if __name__ == '__main__':
    main()
