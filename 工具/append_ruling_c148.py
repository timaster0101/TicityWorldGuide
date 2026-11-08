#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""追加裁定 C148（卡面 3:4 满幅主图接线收口／档 A 模板面定性／OVERFLOW 语义改判）。

与 append_ruling_c147.py 同构：先解析并断言前 147 条写盘前后逐字未变，再只在数组尾部插入，
最后重新解析确认条数与末条编号。手改这份 147 条数组会同时惊动多处条数钉。
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / '数据' / '设定裁定记录.json'

RULING = {
    "编号": "C148",
    "裁定": "（2026-11-08 卡面 3:4 满幅主图接线收口：档 A 模板面定性／80 条 3:4 串与放量／OVERFLOW 语义改判）承 C147 的 (a) 未收口面，用户「这些都做」＋本轮两次点单（档 A、先写串后探针再只投零争议批次）落地四块：(1) **档 A 定性**——16 张产品决策 MISSING 里的「模板正面」5 张不投实景，与「模板背面」5 张同走程序模板面；分类落在渲染器（`工具/build_card_html.py` 的 `TEMPLATE_FACES` 按 `card_type` 判），不改 manifest `status` 数据真源。付费重投口径随之从 C147 的 119 张（80 实景＋39 MISSING）改 **114 张＝80 实景图卡＋34 实景待投**；仍待拍板的是 兑换 5／物品 3／能力 3＝11 张（模板正面 5 已归入档 A）。(2) **3:4 满幅串与放量**——新增 `工具/build_card_main_prompts.py`：从 `数据/开图提示词/` 正文（【画风锚点】起）派生 80 条 3:4 串，只在【取景指令】前挂横幅→竖幅构图约束、正典段逐字保留；口径＝满幅 768×1024 不裁切、顶部 14% 文字安全区、底部 22% 暗部安全区、竖幅只是同一机位的画幅变化不因此获得新的背景授权。产物落 `数据/卡面主图提示词3x4/`（不在 `.gitignore` 内、可版本化）：80 条 txt（字数区间 6157–7376）＋`台账.json`＋`投放台账.json`（逐条 prompt_sha256／bytes／landing）＋`主图3x4落点.json`（纯 {code:path} 80 键）＋`投放核验.json`。探针 1 张（L022）确认后放量 80 张＝**81 次 ImageGen 调用、零 `403 code 112`**，落点 `数据/视觉控制资产/卡牌/主图3x4/<ID>.png` **80/80**，逐张 PIL 实读尺寸 **(768, 1024)**、逐条送入串 sha256 与投放台账对平。(3) **接线正典命令改指**——`python 工具/build_card_faces.py --manifest-only --sources 数据/卡面主图提示词3x4/主图3x4落点.json` 现读 **OK 80／MISSING 39／BACK 5／OVERFLOW 0**、`源尺寸分档` 单档 `{\"768x1024\": 80}`、烤 PNG 0／0；`python 工具/build_card_html.py` 现读 **卡数 124（OK 80／非 OK 44）、有主图 80／占位窗 44、模板面 10（背面 5／正面 5）／实景待投 34**。(4) **OVERFLOW 语义改判＋单卡断链缺陷订正**——满幅路线下 `status` 分类判据从烤 PNG 时代的窗带判据 `window_box(body_rect(), size) is None` 改为 `full_bleed_fit(size, tol=0.002)`（源画幅==画布画幅 768:1024 才不裁切），OVERFLOW 现义＝该源进满幅窗必被裁切、须按 3:4 原生重投；渲染器 `render_card_html(rec, variant, prefix=\"\")` 新增前缀参数，`cards/*.html` 传 `\"../\"`，修掉单卡文件里主图与印章 src 少一层目录的断链（图片引用实扫 241 串、断链 0）。(5) **几何口径接线**——印章几何单一真源 `工具/card_geometry.py` 重写为路线 B 口径（`CANVAS` 768×1024、`SEAL_LANDING_B` 0.24/0.04/0.19、`seal_box_canvas()`／`seal_visible_box_canvas()`），删掉该文件里与 `build_card_faces.py` 重复且本轮 grep 零消费方的烤 PNG 常量；渲染器 `.card .seal` 的三个百分数由 `pct(G.SEAL_LANDING_B[...])` 派生、实发值与旧手抄字面量相同（零视觉变化，改的是抄第二份的隐患）；台标带按满幅口径全量重测（`工具/measure_aigc_badge.py --full-bleed`，80 张逐张非抽样：检出 23／未检出 57，可检出台标上沿距实景下沿 max 43.9／min 10.9）并替换真源 `数据/台标带实测.json`，`SEAL_BADGE_BAND=44` 仍覆盖，C145 那句 43.8 属烤 PNG 窗带口径、已被取代。落点取渲染真值实测 5 张（playwright `channel=\"chrome\"`、`.card` 强制 768×1024）：章框 (553,645)-(737,829) 边长 184.3、可见章面 (564,654)-(727,818)、主图包围盒恒等 (0,0,768,1024)、浮层上沿 y=973.5、占位窗与模板面不叠章。",
    "原因": "四块都有本轮实跑读数，不是措辞偏好。(1) 档 A 是渲染器侧分类不是数据侧改写，故 manifest 仍如实记 5 条 `status==MISSING` 的模板正面；负测 `test_template_faces_are_not_counted_as_pending_scene` 钉住「模板面不计入实景待投」（`实景待投 == sum(MISSING|OVERFLOW) - 5`）与 `index.html` 占位窗数 == 实景待投×2（双版），`test_template_face_card_is_labeled_as_template_not_pending` 钉住模板正面不许显示「实景待投」，否则它永远挂在待投队列里。(2) 探针暴露两处串文缺陷并当场订正入常：竖幅若不点明「不因此获得新的背景授权」会把未点名的现代高层群/塔吊带进背景，底部暗部安全区若不点明「不放人群正面与可读招牌」会在浮层下透出人脸；订正后放量批零驳回、零 sha 不符。补投 L026/L027 第一次派单回执整段幻觉（自称完成、盘上无证据文件无落点图），按盘上证伪后重派并要求先建证据件再逐张追加，第二条路线落盘 2/2。(3) 半批保护由接线闸门实测：`工具/wire_card_main_images.py` 只在「合规格数 == 应投数」时才写 `主图3x4落点.json`，首轮 78/80 实跑判红（`应投 80／合规格 78／不合规格 2`、落点件未写、EXIT=1），补投后复跑 80/80 才写 80 键、EXIT=0。(4) 首次接线曾因此回归：manifest 直指 3:4 源后 80 张全被旧窗带判据报 OVERFLOW、渲染器塌成有主图 0／实景待投 114；根因是退役的烤 PNG 交付判据仍参与状态分类，非源文件问题。作废的旧断言同步纠正：C147 里「23 张可派生（职业 20／景群地标 3）按 C143 从既有开图提示词取正文」本轮实测**不成立**——这 23 条 manifest `code` 全空（无 ID 可查），且其标题在 `数据/开图提示词/` 312 份正文里总命中 **0** 个文件，须新写正文而非派生；另 C143 的 5 张 3:2 横幅专用图（`数据/运行时资产/卡面专用图/`，字节 3005760/2418082/2700399/2701242/3068937）已被 3:4 原生源取代、现无代码消费方，保留作 C143/C146 投放证据。测试面：`工具/test_build_card_html.py` 与 `工具/test_build_card_main_prompts.py` 的用例条数与计时属会漂移的计数，**只写在移交清单 §55.29 ④ 一处，本条不抄第二份**。本轮新增的三条判据是`test_seal_css_percentages_are_derived_not_recopied`（CSS 字面量必须等于 `pct(G.SEAL_LANDING_B[k])`）、`test_seal_landing_clears_badge_band_at_measured_box`（逐边对回 Chrome 实测框并断言可见下沿 ≤ 1024−`SEAL_BADGE_BAND`）与 `test_badge_band_is_the_minimal_cover_of_the_full_bleed_measurement`（台标带常数双向钉住满幅实测上界：调小判压台标、调大判白丢净空）；变异负测见 §55.29 ④。",
    "影响": "判据面：卡面 manifest 的 OVERFLOW 含义与实现改绑满幅判据 `full_bleed_fit`（`工具/build_card_faces.py:159`），旧 `window_box` 窗带判据退出状态分类；`数据/卡面HTML/cards/*.html` 的图片 src 基准从输出目录改为**本文件所在目录**，消费单卡文件的页面程序若自拼路径须按此对齐。交付面：80 张实景图卡满幅主图从「复用 gitignored 图集源＋cover 裁切」改为「3:4 原生 768×1024 零裁切」，源落在 gitignored 的 `数据/视觉控制资产/卡牌/主图3x4/`（与图集源同一条备份风险，沿 C147 偏差⑦）；串文真源 `数据/卡面主图提示词3x4/` 与 `主图3x4落点.json` 可版本化、随本轮入库。正典命令变更：卡面 manifest 重生成从 `--sources 数据/卡面专用提示词/卡面专用图落点.json` 改指 `--sources 数据/卡面主图提示词3x4/主图3x4落点.json`；`数据/卡面备份台账.json` 的 `配方.重生成命令` 随之过期，本轮在该台账补 `状态` 字段声明它是 C146 时代烤 PNG 还原点的冻结记录、不再由已退役的 `backup_card_faces.py` 维护（该字段与下面「规范第八节改口径」同在移交清单 §55.29 那轮真正落地——C148 首发文本只写了主张、没做动作，此处如实订正；同时删掉 `数据/视觉控制资产/卡牌/768x1024/{无文案,有文案}` 两个 0 文件的空目录）。文档面：`设计/2026-10-31-分期路线图.md` 第 30 行现值句同步 148 条／C148；`设计/2026-10-31-卡面标准样式规范.md` 第八节的交付形态／取图分档／投放形态／落点与版本化／运行时印章落点／机器判据／台标带来历／目视八条由烤 PNG 口径改为路线 B 口径（用户原话与叠字数据源两条不动）；条数钉同步 147→148 共 13 处（test_costs 4／test_occupations 5／test_image_assets 2／test_params 2）。本条不进合订本、不触发 docx 重导、也不作废第 18 签（未动原稿／手册／总纲）。未收口面：**34 张实景待投本轮未投**——其中 11 张（兑换 5／物品 3／能力 3）实景方向属产品决策待拍板，23 张（职业 20／景群地标 3）须先新写 3:4 正文（C147「可派生」断言作废）；花钱调用须逐轮重新放行＋探针＋遇 `403 code 112` 就地停手。章径口径差未拍板（路线 B 印章框 184.3 px 对烤 PNG 时代裁定的 212 px 小 27.6%，一行开关 `SEAL_LANDING_B[\"size_r\"]=0.276` 可回到旧视觉尺寸、改后逐边断言会当场判红一次，沿移交清单 §55.29 偏差①）；画风侧仍是照片侧（C 路线明付，CLIP R1 重读 247 枚落照片侧＝最大未收口，沿 C139）；`card-lab/seal.html` 生成器留删未拍板（§A4）；`build_card_faces.py` 残余 manifest 职责是否并入渲染器另议；80 张 3:4 主图与 314 个图集源目录同属 gitignored、异地/异盘备份口径未定（沿 C147 偏差⑦）。"
}


def main():
    raw = P.read_text(encoding='utf-8')
    before = json.loads(raw)
    assert len(before) == 147, '前置断言失败：现读 %d 条，本脚本只负责追加 C148' % len(before)
    assert before[-1]['编号'] == 'C147', '前置断言失败：末条不是 C147'
    sha_before = hashlib.sha256(raw.encode('utf-8')).hexdigest()

    entry = json.dumps(RULING, ensure_ascii=False, indent=2)
    entry = '\n'.join(('  ' + ln) if ln.strip() else ln for ln in entry.split('\n'))
    tail = '  }\n]\n'
    assert raw.endswith(tail), '前置断言失败：文件尾形态与脚本假设不符'
    new_raw = raw[:-len(tail)] + tail[:-len(']\n')] + ',\n' + entry + '\n]\n'

    after = json.loads(new_raw)
    assert len(after) == 148, '写盘前校验失败：解析得 %d 条' % len(after)
    assert [r['编号'] for r in after[:147]] == [r['编号'] for r in before], '前 147 条编号序列变了'
    assert json.dumps(after[:147], ensure_ascii=False, sort_keys=True) == \
        json.dumps(before, ensure_ascii=False, sort_keys=True), '前 147 条内容变了'
    assert new_raw.startswith(raw[:len(raw) - len(tail)]), '前 147 条的原文形态变了'

    P.write_text(new_raw, encoding='utf-8')
    written = P.read_text(encoding='utf-8')
    re_parsed = json.loads(written)
    disk = P.read_bytes()
    print('追加前 %d 条／%d 字节／%s' % (len(before), len(raw.encode('utf-8')), sha_before[:12]))
    print('追加后 %d 条／内存口径 %d 字节／%s' % (
        len(re_parsed), len(written.encode('utf-8')),
        hashlib.sha256(written.encode('utf-8')).hexdigest()[:12]))
    print('追加后 盘上口径 %d 字节／%s（write_text 译 CRLF）' % (
        len(disk), hashlib.sha256(disk).hexdigest()[:12]))
    print('末条编号', re_parsed[-1]['编号'])
    print('RULING 与盘上末条逐字段相等：',
          all(re_parsed[-1][k] == RULING[k] for k in RULING) and set(re_parsed[-1]) == set(RULING))
    print('前 147 条写盘前后逐字段对拍：未变（同一 json 序列化串相等）')


if __name__ == '__main__':
    main()
