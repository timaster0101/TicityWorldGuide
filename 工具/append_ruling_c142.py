#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""追加裁定 C142（卡面按 E1 重做）到 数据/设定裁定记录.json。

为什么要脚本而不是手改：本文件是 141 条、282KB 的 JSON 数组，手改一处缩进或引号就会让
test_doc_drift 与四处条数钉一起红；脚本先解析、校验前 141 条写盘前后逐字未变，再只在
数组尾部插入新条目，最后重新解析确认条数与末条编号。
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / '数据' / '设定裁定记录.json'

RULING = {
    "编号": "C142",
    "裁定": "（2026-11-08 卡面重做裁定，用户原话逐字）「卡面 124 张按 E1 重做，卡面右上角的编号去掉。"
            "然后卡面需要出两张，一个是有下面文字的，一个是没有的。因为之后用的时候下面的文字都是页面通过程序写上去的」"
            "＋三项点单「副标题里的编号一起去掉」「只出 124 张无文案版＋程序叠字（推荐）」「改判据为 768×1024（推荐）」，"
            "合成本条三块口径："
            "(1) 画风——124 张卡面按 E1 正典画风重做，《卡面标准样式规范》第一节第 5 条的「CG 超写实建筑可视化实景」作废；"
            "实景窗不再由卡面 Prompt 现生成，直接取 数据/图集/<条目ID>/ 当前定档格裁进窗内，"
            "图集无对应格的条目才按 E1 投新实景，且投无框主图。"
            "(2) 编号——卡面不出现任何条目编号。实测 4 张代表卡顶部区（裁 0～0.30H 全宽、1.2 倍放大目视："
            "L009／D03／A16／T2纪念）右上角均无编号徽章，编号实际长在副标题行，"
            "故按点单把副标题里的编号段一起去掉；规范第二节表的两行模板同步改表。"
            "边界：兑换卡主标题 T1—T5 是第二节所定「档位」名本身、不是条目编号，不在本条撤除范围；"
            "职业卡副标题本来就不带编号。"
            "(3) 双版与尺寸——每张卡出「无文案版」与「有文案版」两个终稿，但只投 124 张无文案版实景，"
            "有文案版由程序把 bottom_text 叠上去，两版共用同一模板跑两遍，出图量与版数无关；"
            "卡面画幅唯一出处《卡面标准样式规范》第七节的现行判据由 1020×1360 改判为 768×1024（3:4 原生档），"
            "旧值降为历史读数保留。",
    "原因": "三块口径各有各的实测根据，不是措辞偏好。"
            "画风：C93 起 E1 是唯一开图正典画风，photorealistic／写实渲染词只许以否定式出现在 NEGATIVE_TAG 里，"
            "正向段出现即由生成器判红——卡面规范第一节却还写着「CG 超写实建筑可视化实景」，"
            "两条正典并存等于任何一侧都能自证合规；把实景窗改为直接取图集定档格，"
            "卡面画风与场景图从此共用同一张图，不存在第二套画风口径。"
            "编号：用户说的是「右上角的编号」，实测右上角没有徽章，编号在副标题行——"
            "若照字面只删右上角会删到一个不存在的东西、真源那处原样留下，故先取顶部区读数再按点单执行。"
            "双版：底部文案此前只长在 124 张卡面的像素里，全仓 grep 零命中，程序叠字没有数据源，"
            "所以本条的前置是先完成取文（工具/extract_card_text.py 抽取＋工具/build_card_text_review.py 拼版目视＋"
            "工具/apply_card_transcription.py 回写＋工具/verify_card_text.py 独立反查），"
            "读数与执行人登记在 数据/卡面文案底稿.json 的 transcribed_by。"
            "尺寸：1020×1360 不落在出图通道任何一档上，且实测仓库文本层里它只有一处散文标注、代码常量为零，"
            "即没有任何脚本能再生成它（第七节「来历与可复现性」原读数）；"
            "改 768×1024 后画幅由合成器写死，卡面丢失从此可重跑找回。",
    "影响": "规范面：设计/2026-10-31-卡面标准样式规范.md 改四处——第一节第 5 条实景换 E1 并改为取图集定档格、"
            "第一节新增第 7 条无编号原则、第二节表两行副标题去编号段并加映射说明、"
            "第七节现行判据改 768×1024（旧 1020×1360 降为历史读数，含 2026-11-08 归档面复测 PNG 105＋JPEG 19＝124），"
            "另新增第八节「双版卡面与程序叠字」登记交付形态、取图分档、投放形态、叠字数据源与落点。"
            "第一节前的「基准」行同步订正：样式基准口径（版式／底色／配色／字体／无章）不变，"
            "画风、编号与尺寸三项已改判据，按基准卡像素反推新卡面会同时踩这三条。"
            "判据面：工具/test_prompts.py 的 test_manual_states_the_three_aspect_tiers_and_hands_the_card_ratio_to_the_spec "
            "把第七节现值钉改为 768×1024 并加「- **比例与现值**」反向压制；"
            "新增 test_card_spec_c142_three_changes_are_present 钉三处新口径与四条作废措辞。"
            "两条闸门的字面量可达性本轮实测：9 条 keep 各恰 1 次命中、4 条 gone 各 0 次命中，"
            "即钉不是恒绿空钉。设计/ 不进合订本入盘面（compile_book 只收 数据/ 与手册），"
            "故本条不触发 docx 重导、也不作废第 18 次 Word 目视的绑定。"
            "投放面：卡面实景窗分档本轮实测（统计面＝数据/卡面文案底稿.json 的 124 条 card_type/code × 盘上 "
            "数据/图集/<code>/ 是否存在 png）＝可复用图集格 80 张（景群地标卡 60＋板块卡 20，零投放）"
            "／需新出 44 张（职业 20、兑换 5、模板正面 5、模板背面 5、景群地标卡 3、物品 3、能力 3）；"
            "模板背面无需实景，故需投放 39 张。这组数会随补投完成而变，正典只写判据与统计面、不抄第二份。"
            "取文面：124 张卡面底部文案已取成文本真源，读数＝目视转录有文案 114 张／模板卡空文案 5 张／"
            "模板背面判空 5 张（共 124），回写后非空 bottom_text 114 条，存疑 1 条（L023 末字非规范字形、"
            "全量 CJK 字形 IoU 最近仅 0.662，以 □ 占位待人工定字）；"
            "独立反查 工具/verify_card_text.py 读数＝参与对拍 114 条（空文案 10 条不参与）、"
            "字符级相似度 min/median/max 0.00/0.87/1.00、低于 0.50 需回看图 13 条且已逐条目视确认。"
            "OCR 全程只作提示列与反查器、不作结论（同音/形近替换实测存在）。"
            "未收口面：本条只裁定口径，卡面本体尚未重做——合成器 工具/build_card_faces.py、"
            "39 张补投、卡面闸门与负测、L023 定字均为待办；"
            "新卡面落点 数据/视觉控制资产/卡牌/ 仍在 .gitignore 里，属本机资产不随 git 版本化，需另行备份。"
            "文档面：设计/2026-10-31-分期路线图.md 第 30 行末处现值句改为 142 条／C142，由 test_doc_drift 对账；"
            "裁定计数钉同步的处数与全量单测读数只写在移交清单 §57 一处，本条不抄第二份。",
}


def main():
    raw = P.read_text(encoding='utf-8')
    before = json.loads(raw)
    assert len(before) == 141, '前置断言失败：现读 %d 条，本脚本只负责追加 C142' % len(before)
    assert before[-1]['编号'] == 'C141', '前置断言失败：末条不是 C141'
    sha_before = hashlib.sha256(raw.encode('utf-8')).hexdigest()

    entry = json.dumps(RULING, ensure_ascii=False, indent=2)
    # json.dumps 给的是 0 缩进的对象，本文件主体是数组内 2 空格缩进的对象，逐行补一级
    entry = '\n'.join(('  ' + ln) if ln.strip() else ln for ln in entry.split('\n'))
    tail = '  }\n]\n'
    assert raw.endswith(tail), '前置断言失败：文件尾形态与脚本假设不符'
    new_raw = raw[:-len(tail)] + tail[:-len(']\n')] + ',\n' + entry + '\n]\n'

    after = json.loads(new_raw)
    assert len(after) == 142, '写盘前校验失败：解析得 %d 条' % len(after)
    assert [r['编号'] for r in after[:141]] == [r['编号'] for r in before], '前 141 条编号序列变了'
    assert json.dumps(after[:141], ensure_ascii=False, sort_keys=True) == \
        json.dumps(before, ensure_ascii=False, sort_keys=True), '前 141 条内容变了'
    assert new_raw.startswith(raw[:len(raw) - len(tail)]), '前 141 条的原文形态变了'

    P.write_text(new_raw, encoding='utf-8')
    written = P.read_text(encoding='utf-8')
    re_parsed = json.loads(written)
    print('追加前 %d 条／%d 字节／%s' % (len(before), len(raw.encode('utf-8')), sha_before[:12]))
    print('追加后 %d 条／%d 字节／%s' % (len(re_parsed), len(written.encode('utf-8')),
                                     hashlib.sha256(written.encode('utf-8')).hexdigest()[:12]))
    print('末条编号', re_parsed[-1]['编号'])
    print('前 141 条写盘前后逐字段对拍：未变（同一 json 序列化串相等）')


if __name__ == '__main__':
    main()
