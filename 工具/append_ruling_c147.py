#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""追加裁定 C147（卡面交付从「Pillow 烤 PNG」改为「满幅主图 + HTML 叠字」的架构转档）。

与 append_ruling_c146.py 同构：先解析并断言前 146 条写盘前后逐字未变，再只在数组尾部插入，
最后重新解析确认条数与末条编号。手改这份 146 条数组会同时惊动多处条数钉。
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / '数据' / '设定裁定记录.json'

RULING = {
    "编号": "C147",
    "裁定": "（2026-11-08 卡面交付架构转档：烤 PNG → 满幅主图 + HTML 叠字）"
            "用户判定「当前出卡片的思路不对，应每个卡片出一个纯主图，再出 HTML 文件展示主图后的最终呈现」，"
            "并拍板路线 B（主图满幅 3:4 全铺整卡、文字叠图上、底部内容垫暗黑色 70% 透明浮层）。落地四块："
            "(1) **渲染器正式化**——新增 `工具/build_card_html.py`：读 `数据/视觉控制资产/卡牌/768x1024/manifest.json`，"
            "产出 `数据/卡面HTML/`（该目录不在 `.gitignore` 内、可版本化）：`card.css`（几何/配色对齐真源、"
            "浮层 `rgba(0,0,0,.3)+blur`）、`template.html`（单卡骨架占位）、`cards.json`（124 条纯数据）、"
            "`index.html`（全量画廊 248 张＝124×双版，文案运行时注入不烤像素）、`cards/*.html`（124 单卡）。"
            "正负测 `工具/test_build_card_html.py` 9 条（夹具走 tempfile、monkeypatch OUT_DIR、不写被守护仓库）。"
            "(2) **删历史烤图卡面**——`数据/视觉控制资产/卡牌/768x1024/{无文案,有文案}/` 的 248 张 PNG（124×2）删除；"
            "删前核验还原点 `../钛湖城卡面备份/卡面768x1024.zip` 完好（实读 sha256 前 16 位 829f3921d851bf3b＝台账"
            "`归档sha256`、81470884 字节、zip 内 248 PNG＋manifest）。保留 `manifest.json`（渲染器数据真源）与 "
            "`数据/图集/` 314 个 ID 源目录（80 张有实景图卡的满幅主图即取此＝75 张 landscape 已回填 `source`＋5 张 portrait 塔卡的竖幅源在图集但 `source` 未回填，零重投）。"
            "(3) **退役 PNG 交付闸门**——删除 `verify_card_faces.py`／`stamp_seal.py`／`backup_card_faces.py` 及其单测 "
            "`test_card_faces.py`／`test_stamp_seal.py`／`test_backup_card_faces.py`／`test_build_card_faces.py`（共 7 件）；"
            "被 HTML 侧仍要消费的印章口径（SEAL_VIS 等）与 `body_rect` 抽到新 `工具/card_geometry.py` 作单一真源，"
            "`verify_seal_asset.py` 由 `import verify_card_faces` 改 `import card_geometry`（仍守护入仓印章素材漂移）。"
            "`build_card_faces.py` 退为 manifest 生成器，新增 `--manifest-only`（只刷 manifest、不烤 PNG）。"
            "(4) **(a) 80 张实景图卡按 3:4 重投定档**——满幅 3:4 下 75 张 landscape 源（1536/1792×1024）被 `object-fit:cover` "
            "裁掉左右、5 张 portrait 塔卡（1024×1536）裁掉上下；用户「都做」＝批准按 3:4 原生重投。重投范围 80（75 landscape＋5 portrait，均→3:4 原生、消裁切）＋39 MISSING＝119 张，BACK 5 属程序模板不需实景，"
            "属花钱调用，本轮未投、未取得本轮放行。",
    "原因": "四块都有本轮实测读数，不是措辞偏好。"
            "(1) 渲染器实跑：卡数 124（按 manifest `status`＝OK 75／OVERFLOW 5／MISSING 39／BACK 5）、有主图 75／占位窗 49；`有主图` 只认 `status==OK` 且有 `source`，故 5 张 OVERFLOW 竖幅塔卡因 `source` 未回填暂渲染占位窗（接线缺口）；"
            "index.html DOM 实数 248 张卡；装帧分派对——landmark 单行亮标题＋金线、district 金色系列名＋亮片区名两行、"
            "info 短划线、MISSING/BACK 占位窗。`test_build_card_html.py` 9 条本轮 OK。"
            "(2) 删后复核：无文案 PNG 0／有文案 PNG 0／manifest 在／图集 314 目录未动。"
            "(3) 删除 7 件后存活引用扫描：仅 `verify_seal_asset.py` 需 SEAL_VIS（已 repoint），"
            "`append_ruling_c14x.py` 与 `build_card_html.py` 只在正文提旧闸门名、非代码依赖；"
            "`--manifest-only` 实跑不重烤（无文案 0／有文案 0）、manifest 在。"
            "(4) 删除令「图集外扩展名体检」扫描数 299→51（248 张卡牌 PNG 属图集外，299−248=51），"
            "据此重生成 `数据/图片资产核验.json`／`图片复验清单.md` 到当前盘态，令首轮诊断全量套件 "
            "`Ran 470 tests／FAILED(failures=4)` 的 4 条（`test_asset_report_freshness` 3＋"
            "`test_image_assets.test_out_of_gallery_extension_sweep_is_advisory` 1）复跑转绿（Ran 5／OK）。"
            "诊断套件 470＝本轮改动前 491（C146 后）−退役 4 个测试文件的 30 条（test_card_faces 11＋"
            "test_stamp_seal 5＋test_backup_card_faces 10＋test_build_card_faces 4）＋新增 test_build_card_html 9＝"
            "491−30+9=470，与本轮实跑逐条对平；条数钉同步 146→147 实测 13 处＝"
            "test_costs 4（方法名 test_rulings_are_147、len==147、末条 C147、末 12 条窗口 C136…C147）＋"
            "test_occupations 5＋test_image_assets 2＋test_params 2。",
    "影响": "判据面：卡面交付判据从「248 张烤 PNG 的像素几何闸门」换成「HTML 渲染器结构/数据自洽闸门」"
            "（`test_build_card_html.py` 9 条）＋保留的印章素材漂移闸门（`verify_seal_asset.py`，改读 card_geometry）。"
            "旧烤图几何闸门（verify_card_faces/stamp_seal/backup_card_faces）退役删除。"
            "交付面：`数据/卡面HTML/` 全套产物入库（可版本化）；248 张烤 PNG 从盘上删除、还原点在仓外备份 zip；"
            "现有 80 张实景图卡的满幅主图复用图集源图（gitignored）、零重投；其中 5 张 OVERFLOW 竖幅塔卡待回填 `source` 才在渲染器出图。"
            "文档面：`设计/2026-10-31-卡面标准样式规范.md` 第八节「运行时印章落点」的坐标口径出处由 "
            "`verify_card_faces.py` 改指 `card_geometry.py`；`设计/2026-10-31-分期路线图.md` 第 30 行现值句同步 147 条／C147。"
            "本条不进合订本、不触发 docx 重导、也不作废第 18 签（未动原稿／手册／总纲）。"
            "未收口面：**(a) 80 张实景图卡＋39 MISSING＝119 张 3:4 主图重投本轮未投**、**渲染器接线缺口＝5 张 OVERFLOW 竖幅塔卡的 `source` 未回填**——花钱调用须逐轮重新放行＋探针＋遇 `403 code 112` "
            "就地停手；**(c) 16 张产品决策 MISSING（兑换5／模板正面5／物品3／能力3）的实景方向本轮只出建议清单、待拍板**，"
            "23 张可派生（职业20／景群地标3）按 C143 取正文；画风侧仍是照片侧（C 路线明付，CLIP R1 重读 247 枚落照片侧＝"
            "最大未收口，沿 C139）；`card-lab/seal.html` 生成器留删未拍板（§A4）；旧烤 PNG 通道退役后 `build_card_faces.py` "
            "仅余 manifest 生成职责，是否进一步并入渲染器另议。",
}


def main():
    raw = P.read_text(encoding='utf-8')
    before = json.loads(raw)
    assert len(before) == 146, '前置断言失败：现读 %d 条，本脚本只负责追加 C147' % len(before)
    assert before[-1]['编号'] == 'C146', '前置断言失败：末条不是 C146'
    sha_before = hashlib.sha256(raw.encode('utf-8')).hexdigest()

    entry = json.dumps(RULING, ensure_ascii=False, indent=2)
    entry = '\n'.join(('  ' + ln) if ln.strip() else ln for ln in entry.split('\n'))
    tail = '  }\n]\n'
    assert raw.endswith(tail), '前置断言失败：文件尾形态与脚本假设不符'
    new_raw = raw[:-len(tail)] + tail[:-len(']\n')] + ',\n' + entry + '\n]\n'

    after = json.loads(new_raw)
    assert len(after) == 147, '写盘前校验失败：解析得 %d 条' % len(after)
    assert [r['编号'] for r in after[:146]] == [r['编号'] for r in before], '前 146 条编号序列变了'
    assert json.dumps(after[:146], ensure_ascii=False, sort_keys=True) == \
        json.dumps(before, ensure_ascii=False, sort_keys=True), '前 146 条内容变了'
    assert new_raw.startswith(raw[:len(raw) - len(tail)]), '前 146 条的原文形态变了'

    P.write_text(new_raw, encoding='utf-8')
    written = P.read_text(encoding='utf-8')
    re_parsed = json.loads(written)
    print('追加前 %d 条／%d 字节／%s' % (len(before), len(raw.encode('utf-8')), sha_before[:12]))
    print('追加后 %d 条／%d 字节／%s' % (len(re_parsed), len(written.encode('utf-8')),
                                     hashlib.sha256(written.encode('utf-8')).hexdigest()[:12]))
    print('末条编号', re_parsed[-1]['编号'])
    print('前 146 条写盘前后逐字段对拍：未变（同一 json 序列化串相等）')


if __name__ == '__main__':
    main()
