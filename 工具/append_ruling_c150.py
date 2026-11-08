#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""追加裁定 C150（卡面待决项按 C139 代签纪律批量落地／卡面画风侧首份机器读数接闸门／主图同盘还原点／换行口径定档）。

与 append_ruling_c149.py 同构：先解析并断言前 149 条写盘前后逐字未变，再只在数组尾部插入，
最后重新解析确认条数与末条编号。手改这份 150 条数组会同时惊动 13 处条数钉。
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / '数据' / '设定裁定记录.json'

RULING = {
    "编号": "C150",
    "裁定": "（2026-11-08 卡面待决项批量代签＋卡面画风侧首份机器读数＋主图同盘还原点＋换行口径定档）承 C149 未收口面八条与本轮前的三条待决，用户原话「能做的都做，需要我做的你代签」，按 C139 的「没申报不许签」纪律逐条登记。可代签的六项：(1) **11 张实景方向代产品拍板**——兑换 5（idx 7／8／9／10／11＝T1 轻量城市主题壁纸包、T2 纪念典藏明信片套装、T3 典藏文创手办、T4 纪念级联名实物礼盒、T5 顶格专属定制）＋物品 3（idx 70 匠人工坊工具组-生产、idx 72 社区住所卡-居住、idx 74 通勤折叠车-出行）＋能力 3（idx 108 危机谈判-实战-情商、idx 110 深夜自习-学习-智力、idx 112 长跑习惯-习惯-体力）；选定文案与方向依据已在真源 `数据/卡面主图正文待投.json` 的「选定方向」「方向依据」「方向备选」三字段里（带方向备选 11 条、158109 字节／`74480310ee93` 本轮一字未改），图已按这些方向投出并接线，本条只补「产品侧认可」这一步，供推翻。(2) **卡面画风侧第一份机器读数**——新脚本 `工具/reshoot_campaign_2026_11_06/clip_style_card3x4.py`（7751 字节／`72e9e9f6bb69`）导入 `clip_style.py` 同一套模板与 `sep` 算法、不重跑正典实验，覆盖面真源取 `数据/卡面主图提示词3x4/主图3x4落点.json` 的 114 键（不 glob 目录），产物 `clip_style_scores_card3x4.tsv`（7310 字节／`c68e8237c1ae`）与 `clip_style_card3x4_readings.json`（4589 字节／`86747f52407a`）：尺寸分布单档 `{\"768x1024\": 114}`（即 C142「不挤压不留白、单独为卡片生成符合尺寸的图片」在卡面侧首次逐枚机读成立），按正典阈值 0.9023535（正典 75 行／最小错分 14）现分 **P(photo) 落照片侧 103 枚／绘画侧 11 枚**，P(photo) 均值 0.9687／中位 0.9919／区间 0.5078—0.9994／标准差 0.0642；绘画侧名单以读数 JSON 的「最像绘画的10枚_P_photo升序」为准（最靠绘画的是 idx90 0.5078、idx8 0.7465、idx70 0.7465）。据此把「114 张卡面主图的画风目视」代签为**范围与依据都写明的那一种**：目视样本＝§55.30 的 11 张单卡渲染件（`_scratch_cardref/routeB_eye/` 5 张＋`routeB_eye_r2_blur0/` 6 张）＋本轮另取的 3 张主图原件直观（`idx090`／`idx007`／`idx112`，原尺寸读回，非缩略），机器侧＝本读数，二者都只作读数；画风判废权仍在用户侧（用户原话「图不用检验，全出完我自己检验」），本条不写 accepted。本轮 3 张直观的两条结论如实记：`idx007`（水光游客中心檐下自助影像台）与 `idx112`（山湖户外运动中心外连续运动步道、晚秋黄昏、收班跑者与遛狗人）与真源「选定方向」逐要素对得上，且右下角「AI 生成」台标在位清晰（浮层去模糊后不再被糊）；`idx090` 在 CLIP 上落绘画侧（0.5078＝全批最靠绘画），目视却读起来仍是实拍——**故绘画侧那 11 枚不等于画风达标，也不等于方向跑偏，只是这台尺在该枚上的读数**，代签不把它写成通过证据。(3) **浮层去 `backdrop-filter` 的观感变更代签**——亮度均值差 ≤0.2、文案最亮像素 236 不变，合规判据 `test_panel_does_not_blur_over_the_aigc_badge` 已钉住「浮层不许背景模糊」，114 张有文案版观感由磨砂改纯半透明就此定档。(4) **212 px 档的「视觉尺寸相同、换算式不同」口径确认**——判据钉的是渲染真值 212.0×212.0 与可见章面 189×189 这两个读数，不是换算式；烤图时代「章径＝本体宽 1/3」与路线 B「画布宽 27.6%」两条并存、不合并、不再互相回算。(5) **台标带 52.6 是「可检出台标实测最大值」这一天花板确认**——`SEAL_BADGE_BAND` 取 53 覆盖 114 张里 OCR 检出的 38 枚，76 枚未检出多为单行小台标；更靠内的台标一旦出现，`test_badge_band_is_the_minimal_cover_of_the_full_bleed_measurement` 的双向判据自动翻红，不靠人记。(6) **`build_card_faces.py` 的残余 manifest 职责不并入渲染器**——渲染器只消费 manifest、合成器只管 manifest，本轮判为不重构（并入会让两条职责共用一份状态，而它们的过期条件不同）。两项仓外与口径决定：(7) **`card-lab/seal.html` 登记为仓外遗留、不迁不删**——实测在仓同级 `../card-lab`（本仓外，23 项，含 seal.html／card-back.html／fonts／若干探针 png），本仓 `*.py`／`*.md`／`*.json` 里 `card-lab` 字样只长在裁定追加脚本与文档的历史叙述中、零代码消费方；现役印章真源仍是 `数据/运行时资产/印章-已获得-酒红.png`（266546 字节，消费方 `build_card_html.py:28`／`verify_seal_asset.py:19`／`test_seal_asset.py:20`／index.html），删 `../card-lab` 属仓外破坏性动作、不在本轮委托范围，故留而不删并解除「留删未拍板」这条待决。(8) **换行口径定档：`core.autocrlf=true` 不动、不引入 `.gitattributes`**——本轮实测 1020 个跟踪文件里 blob 与工作区字节相同 **422**、不同 **598**（按扩展名 .txt 431／.json 70／.md 44／.html 42／.py 8／.jsonl 1／.csv 1／.css 1，这 598 个全是工作区 CRLF 对 blob LF）；`* -text` + `git add --renormalize .` 会让 598 个 blob 一次性重写、一笔提交动全仓，代价实测在案后判为不值，故本仓文档里写的字节数一律是**工作区（CRLF）口径**，blob 口径另记、不要求两者相等。(9) **gitignored 主图的本机还原点建成**——新脚本 `工具/backup_card_main_images.py`（5958 字节／`d9f0c9a7e333`）沿用 C146 那套「图本体不入库、台账入库、同盘防误删」口径：覆盖面以落点件键现算，缺件或盘上有未登记的图都当场退出非零、不产半批还原点；产出 `钛湖城卡面备份/主图3x4.zip`（166005129 字节／`504ba60d8942`，114 枚，主图合计 165965790 字节）＋入库台账 `数据/卡面主图备份台账.json`（19024 字节／`102f0d326ad8`，逐文件 114 行各带 bytes 与 sha256 前 12）；`--verify` 逐枚对拍 **114/114 相符、zip 内多余 0 枚**、REAL_EXIT=0。**异地/异盘副本不代签**：需要物理介质与目标位置由用户定，本条只把「同盘还原点已有」做实。",
    "原因": "代签的前提是每一项都带本轮读数，而不是把待决项换个说法写一遍——C139 立的就是这条规矩。(1)(2) 这两项此前是「只有目视、无机读」的散文式申报，现在卡面侧有了与 R1 组同一把尺（正典阈值由 `clip_style.sep` 在正典 75 行上现算、闸门还要求两张表的阈值必须相等）的逐枚读数，且 114 枚尺寸单档成立，代签才有一句可核对的依据；读数被 `工具/verify_readout_stance.py`（28760 字节／`1c7a6a310c32`）新增的第六类 `K_CARD_COVERAGE` 守住：卡面表与落点件逐键对平（缺枚／多枚／重枚）、读数 JSON 的 行数/两侧枚数/尺寸分布/落点件键数 由表现算、正典表 sha12 与 R1 表阈值交叉核对——主图重投而 CLIP 表没重跑时，「103/114 落照片侧」这句话当场过期判红，而不是留着当过期证据。正检 REAL_EXIT=0（产物 15/15 件在盘、卡面 114 行逐键覆盖 114 键），`--negtest` 命中 **6/6**、仓库内 `readout_stance_gate_` 残留 0、临时目录已删。(3)(4)(5) 三项都是「我改了／我定了，但没过用户目视或换算式不同源」的申报项，本轮把它们定档：色值与几何读数不变、判据已存在，变更范围可核对。(6) 是职责边界，判据面没有变化，纯不做重构的决定，写出来是为了下轮不再重复讨论。(7) 的「零代码消费方」按本轮 grep 现算：`card-lab` 在仓内的命中全部是裁定追加脚本与四份文档的叙述文本，没有一个 import／open／路径拼接，故它与在产交付无耦合；印章素材本身另有 `verify_seal_asset.py` 逐边偏差 max 0.0018＜容差 0.010 把关。(8) 是量出来的代价：422/598 这个分叉数是本轮 `git ls-files -s` 逐 blob `git cat-file` 与工作区 `open(...,'rb')` 三方对拍取实（第一次用 `git show HEAD:<path>` 全数失败，`<rev>:<path>` 形态在 MSYS 下被吃路径、不可用作证据），renormalize 的收益只是「文档字节数跨平台成立」，而本仓工作区与 blob 都只在这台 Windows 机器上生成与消费，收益不值一笔 598 文件的提交。(9) 沿用 C146 已定的口径而不是新造一条，是为了让「同盘还原点」在两轮里可比；zip 不做增量、逐枚 sha 对平即不重建，重建只走 `.part` 后 `os.replace` 原子替换。不可代签的两项也如实留着：异地/异盘副本要物理介质与位置（用户 infra），画风判废权用户明确自留。",
    "影响": "闸门面：`工具/verify_readout_stance.py` 的判红类别由五类增至六类（新增 `K_CARD_COVERAGE`＝卡面主图画风读数对不上），CAMPAIGN 清单由 12 件增至 15 件（补 `clip_style_card3x4.py`／`clip_style_scores_card3x4.tsv`／`clip_style_card3x4_readings.json`，缺件即判红），夹具面新增最小落点件（`CARD_FIXTURE_N`＝3、照片侧 2）与两张读数件的构造，违例注入按真实错法取「卡面表被截短一行而 JSON 计数没改」，同时打覆盖面与 JSON 对拍两支；`main()` 抬头行同步打印卡面两数，类别数与命中数仍取该脚本本轮输出、文档不抄第二份。数据面：新增入库件 `数据/卡面主图备份台账.json`；`钛湖城卡面备份/` 内新增 166005129 字节 zip（仓外、与既有 `卡面768x1024.zip` 并存互不影响，本轮未动后者）。画风面：卡面侧从此有可核对的照片/绘画读数，C149 偏差①「画风照片侧未收口」在卡面这一支的举证从散文变成 103/114 这个数；R1 组那 312 枚的读数表与本表用同一把正典阈值，闸门交叉核对。文档面：`设计/2026-10-31-分期路线图.md` 第 30 行末处现值句同步 150 条／C150（该句由 `工具/test_doc_drift.py` 的 F 条对回真源）；`设计/2026-10-31-卡面标准样式规范.md` 第八节补机器判据一条（卡面 CLIP 读数与落点件逐键对平）；`设计/2026-11-03-待办移交清单.md` 新增 §55.31 登记本轮，并把 §55.30 的偏差②④⑦⑧四条挂订正。条数钉同步 149→150 共 13 处（`test_costs.py` 4＝方法名＋条数＋末条编号＋末十条清单、`test_occupations.py` 5、`test_image_assets.py` 2、`test_params.py` 2）；与裁定条数无关的同名数字两处继续不动（`test_costs.py:389` 的 24+148+120=292 是 C102 时代封面历史文本、`test_occupations.py` 的 148 是违例注入用例数）。未收口面（本条申报、不判绿）：**114 张卡面主图仍整批落在照片侧**（103/114，判废权在用户）、**异地/异盘备份未做**、**598 个文件的 CRLF/LF 分叉未合**（本轮判为不做并写明理由）、**手册第 9 节与质量核验报告里 `verify_readout_stance` 的判据枚举尚未补「卡面主图」那一支**——补它要连带重导合订本与 Word 并做第 19 次渲染目视，本轮按「严格按范围」留给下一轮合订本重导时一起做，待插句子已写进 §55.31 的遗留清单。本轮提交范围需先报再提交，**推送待网络恢复后按用户此前的「稍后」执行**。"
}


def main():
    raw = P.read_text(encoding='utf-8')
    before = json.loads(raw)
    assert len(before) == 149, '前置断言失败：现读 %d 条，本脚本只负责追加 C150' % len(before)
    assert before[-1]['编号'] == 'C149', '前置断言失败：末条不是 C149'
    sha_before = hashlib.sha256(raw.encode('utf-8')).hexdigest()

    entry = json.dumps(RULING, ensure_ascii=False, indent=2)
    entry = '\n'.join(('  ' + ln) if ln.strip() else ln for ln in entry.split('\n'))
    tail = '  }\n]\n'
    assert raw.endswith(tail), '前置断言失败：文件尾形态与脚本假设不符'
    new_raw = raw[:-len(tail)] + tail[:-len(']\n')] + ',\n' + entry + '\n]\n'

    after = json.loads(new_raw)
    assert len(after) == 150, '写盘前校验失败：解析得 %d 条' % len(after)
    assert [r['编号'] for r in after[:149]] == [r['编号'] for r in before], '前 149 条编号序列变了'
    assert json.dumps(after[:149], ensure_ascii=False, sort_keys=True) == \
        json.dumps(before, ensure_ascii=False, sort_keys=True), '前 149 条内容变了'
    assert new_raw.startswith(raw[:len(raw) - len(tail)]), '前 149 条的原文形态变了'

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
    print('前 149 条写盘前后逐字段对拍：未变（同一 json 序列化串相等）')


if __name__ == '__main__':
    main()
