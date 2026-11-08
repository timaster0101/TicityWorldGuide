#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""追加裁定 C149（34 张实景待投投放收口／印章回 212 px 档／待投名单口径单源化）。

与 append_ruling_c148.py 同构：先解析并断言前 148 条写盘前后逐字未变，再只在数组尾部插入，
最后重新解析确认条数与末条编号。手改这份 148 条数组会同时惊动 13 处条数钉。
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / '数据' / '设定裁定记录.json'

RULING = {
    "编号": "C149",
    "裁定": "（2026-11-08 卡面 3:4 待投 34 张投放收口＋印章回 212 px 档＋待投名单口径单源化）承 C148 的两条未收口面，用户原话「① 章径口径差 184.3 px vs 烤图时代 212 px，一行开关 SEAL_LANDING_B[\"size_r\"]=0.276 可回，已记为偏差①供推翻；② 34 张实景待投未投＝11 张产品方向未点（#64）＋23 张须先新写 3:4 正文（#49/#50/#51），花钱调用下轮要重新放行；③ 本轮未提交也未推送，需要的话我先报提交范围再动。都做」落地四块。(1) **章径回 212 px 档**——`工具/card_geometry.py` 的 `SEAL_LANDING_B[\"size_r\"]` 由路线 B 转档时顺手抄的 0.24 改回烤 PNG 时代 C144 裁定的 0.276（768×0.276＝211.97≈212 px），该文件现 2739 字节／`741e7cf98272`；渲染真值实测（playwright `channel=\"chrome\"`、`.card` 强制 768×1024、5 张）章框 (525,618)-(737,829) 边长 212.0×212.0（`seal_box_canvas()` 换算框 (525,617)-(737,829)，y0 差 1 px 是浏览器对 211.968 的取整）、按 `SEAL_VIS` 折算可见章面 (537,627)-(726,816)＝189×189、主图包围盒恒等 (0,0,768,1024)、浮层上沿 y=973.5、可见章面下沿距画布底 208 px 扣台标带 44 后净空 164 px、右沿距画布右 42 px。§55.29 偏差① 就此推翻。(2) **34 张实景待投正文与投放**——正文真源 `数据/卡面主图正文待投.json`（158109 字节／`74480310ee93`，items 34、带方向备选 11、骨架五段指纹 画风锚点 493 字／`b664631db5ba`、全局硬设定 999 字／`3c68e9975054`、English tail 风格前缀 279 字／`45702797c46d`、禁则后缀 1614 字／`1ea290f20a34`、画幅句／`c68bbbb6602d`）由 `工具/merge_pending_specs.py`（11806 字节／`92f3762abe34`）合并三个分片代理件产出；`工具/build_card_main_prompts.py`（11375 字节／`68f215701bb0`）现读 条数 114＝派生 80＋待投 34、字数区间 [5575, 7376]、OK 114／OVERFLOW 0／实景待投 0，`数据/卡面主图提示词3x4/*.txt` 114 份逐文件与投放前 `cmp` 差异 0、缺失 0，`台账.json` 46701 字节／`3246198b9036` 逐字段对拍除 34 行 `manifest_status` MISSING→OK 外全等。投放＝探针 idx007 1 张＋其余 33 张＝**34 次 ImageGen 调用、零 `403 code 112`**；`投放台账R2.json`（14215 字节／`66c53b9d5a6d`）条数 34、底串字节 9459–10623；三分片回执各 11 行、唯一 id 34、同带重复 0、status 全 ok。接线 `python 工具/wire_card_main_images.py --round r2` 现读 应投 34／合规格 34／不合规格 0，`主图3x4落点.json`（7381 字节／`558f66f8f681`）写旧 80＋本轮 34＝并集 114 键、旧 80 键逐键未变。manifest 重生成 `python 工具/build_card_faces.py --manifest-only --sources 数据/卡面主图提示词3x4/主图3x4落点.json`（52896 字节／`65722f7d6278`）现读 **OK 114／MISSING 5（模板正面）／BACK 5**、`源尺寸分档` 单档 `{\"768x1024\": 114}`、`放不下源 []`、状态流转恰 34 条 MISSING→OK。渲染器 `python 工具/build_card_html.py` 现读 卡数 124（OK 114／非 OK 10）、有主图 114／占位窗 10、模板面 10（背面 5／正面 5）／**实景待投 0**，`数据/卡面HTML/cards/*.html` 124 个文件里含印章 114、含占位窗标签 10。(3) **待投名单口径单源化**——`工具/build_card_main_prompts.py` 新增 `pending_indices(man)` 结构判（`code` 空 ∧ `card_type != 模板正面` ∧ `template != back`，现读恰 34），`merge_pending_specs.py` 改为 import 同一函数；C148 时代两处各写一份 `status == \"MISSING\"`，34 张回填转 OK 的当轮就会让待投名单归零、拼装支路被静默关掉而生成器仍产 80 条串不报错。(4) **拼串与图例缺陷订正**——tail 四截改「逐截剥尾逗号 + `\", \".join`」，消掉 34 条串的 `text,, Foreground` 双逗号（全 114 txt 复扫 `\",,\"` 命中 0）；`工具/build_card_html.py`（13547 字节／`fb9a2375cdca`）index 图例三个数改由记录派生，不再硬写 80／10／34。",
    "原因": "四块都有本轮实跑读数与变异负测，不是措辞偏好。(1) 212 是 C144 对烤 PNG 时代裁定的视觉尺寸（章径＝本体宽 1/3），路线 B 转档时抄成 0.24 未拍板；本轮用户「都做」即推翻，回档后逐边判据 `test_seal_diameter_is_the_ruling_backed_212px` 与 `test_seal_landing_clears_badge_band_at_measured_box` 钉住 212/189/净空，`size_r 0.276→0.24` 变异判红 3 条、`bottom_r 0.19→0.0` 判红 2 条（`_scratch_cardref/mutate_seal212.py`→`.log`），还原后 `工具/card_geometry.py` 回到 2739 字节／`741e7cf98272`＝基准，该模块与本轮全量套件均判绿。(2) 待投名单是本次唯一「改了数据、代码不报错但少产一半串」的隐患：回填前后各跑一次才暴露——回填当轮生成器实跑仍是 114 条只因已改结构判，若沿用状态判会产 80 条且 `条数` 与正文清单判不平。四组变异（`_scratch_cardref/mutate_pending_branch.py`→`.log`，每轮删 `.pyc`、整份原始字节还原并复核 sha）读数：双逗号拼回 退出码 1／红项 1、相等断言作废 1／1、名单换回状态判 1／红项 7（含两条新判据）、骨架指纹对拍作废 1／1，还原后基线 `Ran 12／OK in 0.703s`、`build_card_main_prompts.py` 回到 11375 字节／`68f215701bb0`＝基准。合并器重跑前后 `数据/卡面主图正文待投.json` 逐字节相同（两侧同 158109 字节／`74480310ee93`），骨架五段指纹逐段相等，证明「口径单源化」这一步没动过正文一个字。(3) 投放侧的半批保护与逐张核验沿用 R1 那套：`wire_card_main_images.py` 只在合规格数==应投数时写落点件，本轮 34/34 一次过；分片纪律（第 0 节「已投不许重投、只补落盘差集」＋四查校验＋403 就地停手＋禁止任何图像后处理与 AIGC 标识改动）见 `_scratch_cardref/card3x4_r2/投放规程.md`，3 片 agentId 与 transcript 登记在同目录 `派单登记.json`；shard1 回执上报了工具输出里夹带的指令并拒绝执行，本轮未采纳。(4) C148 未收口面那句「11 张方向未点＋23 张须先新写 3:4 正文」本轮实测**不准确**，如实订正：34 张全部须新写正文（它们 `code` 全空、标题在 `数据/开图提示词/` 312 份正文里总命中 0），11 张只是在此之外还多一道产品方向前置；方向本轮已按档 A 之外的口径定完并写进正文真源的「方向备选」字段（11 条）。测试面：`工具/test_build_card_html.py`（17 条）与 `工具/test_build_card_main_prompts.py`（现 12 条）的用例条数与计时是随改动漂移的计数，规范第八节按轮取现值、本条不抄第二份。",
    "影响": "判据面：待投名单的唯一口径现在是 `build_card_main_prompts.pending_indices()`，`merge_pending_specs.py` 从它 import（旧的两份 `status == \"MISSING\"` 已删）；谁把它换回投放状态判，`test_pending_indices_is_structural_not_status_based`（合成夹具结构判 vs 状态判差两条）与 `test_pending_queue_survives_the_resend_flipping_status_to_ok`（34 张现全为 OK）当场判红。交付面：卡面实景队列从「80 有图＋34 待投」变为 **114 张满幅 3:4 主图全部落地**，占位窗只剩 10 张模板面（档 A），叠章范围随之从 80 张改为 **114 张**；`数据/视觉控制资产/卡牌/主图3x4/` 现 114 个 PNG（gitignored，与 314 个图集源目录同一条未定备份口径，沿 C147 偏差⑦）。闸门面：本轮 34 张新主图落在 `数据/` 图集外，使 `数据/图片资产核验.json` 的「图集外扩展名体检」过期（盘 131／现算 165），`python 工具/verify_image_assets.py` 重导两份产物后 `test_asset_report_freshness`＋`test_image_assets` 复跑 **Ran 46／OK in 7.945s**，扫描数现读 165、不一致 0、判红 0，通过 1125/1125 格。文档面：`设计/2026-10-31-分期路线图.md` 第 30 行现值句同步 149 条／C149；`设计/2026-10-31-卡面标准样式规范.md` 第八节「运行时印章落点」的叠章范围 80→114、占位窗 44→10、实景待投 34→0，「机器判据」两条测试件指纹与条数按本轮重取；条数钉同步 148→149 共 13 处（test_costs 4／test_occupations 5／test_image_assets 2／test_params 2；`test_occupations.py` 里 `summary['cases'] == 148` 那条是违例注入用例数、与裁定条数无关，本轮不动）。本条不进合订本、不触发 docx 重导、也不作废第 18 签（未动原稿／手册／总纲）。未收口面：**画风侧仍读起来像实拍**（C 路线明付，CLIP R1 重读 247 枚落照片侧＝最大未收口，判废权未委托，沿 C139；本轮 34 张新图与 5 张目视件同样落在此侧，且用户已声明「图不用检验，全出完我自己检验」，故 34 张的目视验收在用户侧、未由脚本代签画风）；114 张满幅主图与图集源的 gitignored 备份口径未定；`card-lab/seal.html` 印章生成器留删未拍板（§A4）；`build_card_faces.py` 残余 manifest 职责是否并入渲染器另议；本轮提交范围需先报再提交、**推送未获授权**。"
}


def main():
    raw = P.read_text(encoding='utf-8')
    before = json.loads(raw)
    assert len(before) == 148, '前置断言失败：现读 %d 条，本脚本只负责追加 C149' % len(before)
    assert before[-1]['编号'] == 'C148', '前置断言失败：末条不是 C148'
    sha_before = hashlib.sha256(raw.encode('utf-8')).hexdigest()

    entry = json.dumps(RULING, ensure_ascii=False, indent=2)
    entry = '\n'.join(('  ' + ln) if ln.strip() else ln for ln in entry.split('\n'))
    tail = '  }\n]\n'
    assert raw.endswith(tail), '前置断言失败：文件尾形态与脚本假设不符'
    new_raw = raw[:-len(tail)] + tail[:-len(']\n')] + ',\n' + entry + '\n]\n'

    after = json.loads(new_raw)
    assert len(after) == 149, '写盘前校验失败：解析得 %d 条' % len(after)
    assert [r['编号'] for r in after[:148]] == [r['编号'] for r in before], '前 148 条编号序列变了'
    assert json.dumps(after[:148], ensure_ascii=False, sort_keys=True) == \
        json.dumps(before, ensure_ascii=False, sort_keys=True), '前 148 条内容变了'
    assert new_raw.startswith(raw[:len(raw) - len(tail)]), '前 148 条的原文形态变了'

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
    print('盘上 CRLF 行数', disk.count(b'\r\n'), '裸 LF 字节', disk.count(b'\n') - disk.count(b'\r\n'))
    print('末条编号', re_parsed[-1]['编号'])
    print('RULING 与盘上末条逐字段相等：',
          all(re_parsed[-1][k] == RULING[k] for k in RULING) and set(re_parsed[-1]) == set(RULING))
    print('前 148 条写盘前后逐字段对拍：未变（同一 json 序列化串相等）')


if __name__ == '__main__':
    main()
