#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""追加裁定 C155（收口轮：7 条在册裁定件补出 R12、140 条早期图按 E1 基线重出 R11、312 条全签、不再逐张查缺陷）。

与 append_ruling_c154.py 同构：前置断言现读 154 条／末条 C154，只追加尾部，写盘后重解析对拍前 154 条逐字段未变。
手改这份 155 条数组会同时惊动条数钉与末窗切片。

轮次标签说明：R11／R12 台账里的档串写的是 `C156E1基线重出-v01`／`C156E1基线补出-v01`，
那个 `C156` 是**批次标签**（C155 收口申报之后的一批），裁定依据即本条 C155 与用户 2026-11-27 原话；
判据记录（本文件）只到这里一条，不另立 C156 编号——否则「裁定编号」与「批次编号」两套序号会各说各话。
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / '数据' / '设定裁定记录.json'

RULINGS = [
    {
        "编号": "C155",
        "裁定": "（2026-11-27 收口轮；用户原话①「1 如果是文字的话，就不用检查了，直接过吧。」②「139 张早期图要重新出，之前不是按照E1出也也要重新出，然后把该做的事情都做完，图出完就行，不用检查是否有缺陷，以后遇到了再弄。」③「不要再提qoder了，图和其他任务以后都当前环境处理」④「其他的按照你的建议，做完了就闭合，没做完要处理完才能收口」）四件事。\n\n"
                  "(1) **140 条早期图按 E1 基线重出（R11）**：在册首格分类现读 312 条＝`C154母图重投` 159／`四向` 139／`C154取景…` 13／`C138主向重投` 1，其中 `四向` 139＋`C138主向重投` 1＝**140 条**仍挂 2026-10 首批基准照（母图基线是四向基准照，不是 E1 定档件），与全书中 172 条 E1 基线不同源。用户裁定这批全部重出，故立 R11：正文与送入串沿用现串（一个字不动），只把母图换成 E1 定档池并逐字回绑；发名后缀 `C156E1基线重出-v01`。实投 140 枚全成功、42.00 元，`verify_round_ark --round R11` 140 条全绿（逐字／尺寸／字节／母图四列 True，容器 caBX=1），`backfill_round R11` 140 条整批换格。\n\n"
                  "(2) **7 条 C155 收口件补出（R12）**：C155 收口行的处置写的是「不绑串；须重投一版本串产物方能走 C139 代签」，这 7 条（D06／D09／D10／D11／D12／D15／D20）在册格是取景换档之前的串所出，没有任何投后读数能证明它与今天的串相等。本轮按现串补出 7 枚、2.10 元，`verify_round_ark --round R12` 7 条全绿，`backfill_round R12` 7 条换格，再走 `sign_acceptance --ids …` 代签 7 条；收口件「待重投方能签」这句因此兑现，不是被绕过。\n\n"
                  "(3) **312 条全部已验收**：147 枚新图落盘（R11 140＋R12 7）后，清单 `accepted=312`／`needs_review=0`／绑定 312，格子总数 1125。计数由 `工具/sync_manifest_counts.py` 按 status 现算写入（口径同 `build_prompts.py:696-700`），不手填。\n\n"
                  "(4) **本批不再逐张查缺陷**：用户明示「图出完就行，不用检查是否有缺陷，以后遇到了再弄」。故 R11／R12 的落盘判据只走机械三段（逐字、字节、母图），不做逐张目视分栏；已知的历史缺陷类型（日盘入画、未点名塔群塔吊、可读馆名、楼层量级不符）保留在册（`数据/R10目视结论.json` 与 C154 取景分栏），不因本批而失效，也不据此判废本批任何一枚。",
        "原因": "先说为什么这批必须重出、又为什么这次不查。\n\n"
                "「必须重出」是基线问题，不是质量偏好：全书 172 条的画风基线是 E1 定档件（2026-11-03 之后逐轮以它为母图），而 140 条仍挂 2026-10 的四向基准照。两种母图带出的是两种媒介：四向基准照那一批的笔触密度与色层与 E1 那一批并排看不是一套。此前一直没动它，因为「在册已验收」；一旦把「全书同一基线」当成完成条件，这 140 条就是明确的未完成项——不是缺陷，是断代。\n\n"
                "「这次不查」是因为查了 20 天仍未收口。把收敛路径复盘一遍：判据被反复修订（C99 日盘、C134 CLIP 阈值、C136 容器、C139 代签语义、C153 画风档、C154 取景分栏、C155 收口），每改一次已验收就回滚一批；而图片是概率产物，缺陷是随机的（日盘、塔吊、烤字、楼层数），逐张签的流程遇到随机缺陷就永远在收敛路上。140×0.30＝42.00 元的量，逐张看完要半天以上，看完也不保证下一轮不复发同样的缺陷。用户的选择是「出完即算完成、缺陷留给以后遇到再弄」——这是一次**完成定义的改写**，不是判据放水：机械三段仍然逐枚判，判不绿的不许回填。\n\n"
                "为什么 7 条也要补：它们卡在「在册格不是现串产物」这个缝里。C155 收口把「不绑串」写成处置，等于承认这批暂时无法签；收口要成立，就得有人把现串真投一遍。补出 7 枚花 2.10 元，比继续在清单里挂 7 条永久待复验便宜。\n\n"
                "为什么轮次标签写 C156：R11／R12 的档串在写台账时就用了 `C156E1基线重出-v01`／`C156E1基线补出-v01`，那时是把它当「下一批」的占位号；实际落进判据记录的编号是 C155（本文件 154→155 条）。两套序号并存容易让下一个接手方去翻不存在的 C156 条，故在此写死：**C156 是批次标签，判据依据是 C155 条与用户 2026-11-27 原话**。",
        "影响": "投放面：`工具/reshoot_campaign_2026_11_06/build_send_bodies_r11.py`（`is_legacy`／`members()`／`frozen(ids)`／`build(ids=None)`）→ `send_bodies_r11.json` 140 条＋`_note.json`；`..._r12.py` → `send_bodies_r12.json` 7 条＋`_note.json`；投送器 `.../send_r11_ark.py` 参数化 `--round {R11,R12}`（`ROUNDS` 表切台账／运行日志／note 三处路径）；产物 147 枚落 `vibe_images/`（发名 `…-C156E1基线重出-v01_1795…_xxxxxxxx.png`／`…-C156E1基线补出-v01_…`）。台账 `数据/R11方舟投送记录.json`（140 行）／`数据/R12方舟投送记录.json`（7 行）；废轮 `数据/R11方舟投送记录-双重前导废轮.json`（6 行、1.80 元，产物移入 `vibe_images/_superseded_r11_double_prefix/`）。\n\n"
                "核验面：`.../verify_round_ark.py` 参数化 `--round {R10,R11,R12}` → `round_readings_r11.json`／`ledger_r11.json`、`round_readings_r12.json`／`ledger_r12.json`；`.../backfill_round.py` 新增 `ROUNDS['R11']`／`['R12']` 与 `PROVENANCE` 两条（记委托原话、通道、机械三段、本批不做缺陷检查）。\n\n"
                "闸门面：`工具/verify_round.py` 的 `LATER_ROUND_SUFFIXES` 补 `C156E1基线重出`／`C156E1基线补出`、`HTTP_ROUND_READINGS` 补 r11／r12 两份读数；`工具/test_verify_round.py` 的 `REAL_FILES` 补钉八件；`工具/test_image_assets.py` 的 `ROUNDS` 补两轮、硬编码计数改实测（C2PA 格 162、iTXt 格 310、png 472、live 470、jpg 653）、新增 `declared_members()` 取代已空的 `unreshot_members()`、两处写死 eid 的负测改现算；`工具/sign_acceptance.py` 的 `EXECUTOR` 去掉 Qoder 字样（用户原话「不要再提qoder了」）。\n\n"
                "读数面（本轮实读）：清单 `accepted 312`／`needs_review 0`／绑定 312；格子 1125；`verify_image_assets` 通过 1125/1125 格、提示 0、C2PA 162 格、iTXt 310 格；`build_gallery_manifest` 808 件／2403.9 MB／312 目录；`build_aigc_declaration` 808 件／312 地点／方舟轮 161 枚；成本 R10 6.30＋R11 废轮 1.80＋R11 42.00＋R12 2.10＝**52.20 元**（另体检探针 1.14 元）。\n\n"
                "未纳入本条的：424 页逐页人眼（用户 2026-11-27 裁定「如果是文字的话，就不用检查了，直接过吧」，见交接清单 §55.72；`rendering_verified` 仍是第 29 签）；第二块物理盘（硬件不存在，见 `数据/备份拓扑实测.json`）；图集入仓（1.9GB→2.4GB，`.gitignore` 排除，镜像在 `D:\\bak\\钛湖城图集-镜像`）。",
    },
]


def main():
    raw = P.read_text(encoding='utf-8')
    before = json.loads(raw)
    assert len(before) == 154, '前置断言失败：现读 %d 条，本脚本只负责追加 C155' % len(before)
    assert before[-1]['编号'] == 'C154', '前置断言失败：末条不是 C154'
    sha_before = hashlib.sha256(raw.encode('utf-8')).hexdigest()

    block = ',\n'.join(json.dumps(r, ensure_ascii=False, indent=2) for r in RULINGS)
    block = '\n'.join(('  ' + ln) if ln.strip() else ln for ln in block.split('\n'))
    tail = '  }\n]\n'
    assert raw.endswith(tail), '前置断言失败：文件尾形态与脚本假设不符'
    new_raw = raw[:-len(tail)] + tail[:-len(']\n')] + ',\n' + block + '\n]\n'

    after = json.loads(new_raw)
    assert len(after) == 155, '写盘前校验失败：解析得 %d 条' % len(after)
    assert [r['编号'] for r in after] == [r['编号'] for r in before] + ['C155'], '编号序列变了'
    assert json.dumps(after[:154], ensure_ascii=False, sort_keys=True) == \
        json.dumps(before, ensure_ascii=False, sort_keys=True), '前 154 条内容变了'
    assert new_raw.startswith(raw[:len(raw) - len(tail)]), '前 154 条的原文形态变了'

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
    print('末条编号', re_parsed[-1]['编号'], '／末两条', [r['编号'] for r in re_parsed[-2:]])
    got = re_parsed[154]
    print('C155 与盘上末条逐字段相等：',
          all(got[k] == RULINGS[0][k] for k in RULINGS[0]) and set(got) == set(RULINGS[0]))
    print('前 154 条写盘前后逐字段对拍：未变（同一 json 序列化串相等）')


if __name__ == '__main__':
    main()
