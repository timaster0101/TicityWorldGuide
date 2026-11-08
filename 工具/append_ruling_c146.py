#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""追加裁定 C146（收口 C145「未收口面」中四项零额度本地工作／移交清单 §55.24 偏差③⑤⑦＋⑥生成器侧出处核验）。

与 append_ruling_c145.py 同构：先解析并断言前 145 条写盘前后逐字未变，再只在数组尾部插入，
最后重新解析确认条数与末条编号。手改这份 145 条数组会同时惊动多处条数钉。
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / '数据' / '设定裁定记录.json'

RULING = {
    "编号": "C146",
    "裁定": "（2026-11-08 收口 C145「未收口面」四项零额度本地工作／移交清单 §55.24 偏差③⑤⑦＋⑥生成器侧出处核验）"
            "用户「都做」委托下落地四块，花钱项（#47 补投）不在本轮放行范围："
            "(1) **5 张卡面专用横幅图进仓落点定档**——从仓外 `_scratch_cardref/card_sources/` 迁入 "
            "`数据/运行时资产/卡面专用图/{L003,L007,L022,L033,L038}.png`（该目录不在 `.gitignore` 内、可版本化），"
            "落点映射写成纯 {code:path} 的 `数据/卡面专用提示词/卡面专用图落点.json`"
            "（消费方 `build_card_faces.py` 把每个 JSON 键都当源映射，故不掺元数据键）；"
            "正典重生成命令 `python 工具/build_card_faces.py --sources 数据/卡面专用提示词/卡面专用图落点.json`，"
            "5 张在 manifest 里 source 全为仓相对路径、status 全 OK。解 C143 的落点未定遗留。"
            "(2) **L023 末字代人工定字＝禄**——`数据/卡面文案底稿.json` 的 L023（_idx22）bottom_text 由"
            "「商旅云集，埠通富□」改「商旅云集，埠通富禄」、需目视转 false，存疑字段写明委托来源（用户「都做」）"
            "与定字依据（OCR 整行读禄＋「富禄」连贯古典词同指禄，本会话代理目视 backup 原卡确认末字为 malformed 礻旁字），"
            "并标「供推翻」；有文案版重生成。"
            "(3) **248 张活跃卡面本机备份口径定档并执行**——活跃卡面是确定性派生物，但 80 张 OK 里 75 张依赖 "
            "gitignored 图集、纯配方重生成不自足，故做像素归档：`工具/backup_card_faces.py` 把 "
            "`数据/视觉控制资产/卡牌/768x1024/` 的 248 张双版 PNG＋manifest 打成 sha256 校验 zip 落仓外 "
            "`../钛湖城卡面备份/卡面768x1024.zip`，台账 `数据/卡面备份台账.json` 入库（逐文件 sha256/bytes＋配方），"
            "图本体不入库；活跃卡面不进 `backup/`（那按 C133/§52 只收被替换旧图、MOVE 不 COPY）。"
            "异地副本与图集源备份属用户 infra、本轮不代决。"
            "(4) **card-lab/seal.html 渲染复现入仓印章真源（出处核验、非永久闸门）**——仓外渲染重跑 "
            "`card-lab/seal.html` 的 #s-red（默认 distress）于 720×720，与入仓 "
            "`数据/运行时资产/印章-已获得-酒红.png` 逐字节 cmp 相等、pixel_diff 0、alpha 外接框逐边偏差 0；"
            "HTTP 服务端口 8901 用完即 shutdown 并打印 SERVER_CLOSED。证入仓素材确由该生成器产出，"
            "§A4 生成器留删仍未拍板。",
    "原因": "四块都有本轮实测读数，不是措辞偏好。"
            "(1) 5 图字节 L003 3005760／L007 2418082／L022 2700399／L033 2701242／L038 3068937；"
            "落点 JSON 302 字节；manifest 124 张（OK 80／MISSING 39／BACK 5），5 张专用图 source 全仓相对、status 全 OK。"
            "(2) L023 bottom_text 现读「商旅云集，埠通富禄」、需目视 false；卡面闸门 `工具/verify_card_faces.py` "
            "本轮 119 张叠章判据覆盖、违例 0、EXIT=0（有文案版底部墨迹判据含 L023）。"
            "(3) 备份 `--verify` 本轮通过：归档 81470884 字节、sha256 前 12 位 829f3921d851bf3b、249 文件"
            "（248 PNG＋1 manifest）、卡面总字节 82410819、违例 0、EXIT=0；台账 45167 字节。"
            "新增 `工具/test_backup_card_faces.py` 10 条本轮全 OK：干净夹具判绿（闸门非恒红）＋8 处违例注入全判红"
            "（归档缺失/sha256 不符/字节不符/损坏/条目不符/逐文件 sha256 不符/盘上漂移/盘上缺失）＋已入库台账结构自洽"
            "（文件数==len(逐文件)、配方含正典命令、不依赖仓外归档与 gitignored 卡面目录，fresh clone 可跑）；"
            "夹具建在 tempfile、monkeypatch 模块 ROOT，不往被守护仓库写一个字节。"
            "(4) 复现报告 `_scratch_cardref/seal_check/seal_rerender_report.json`：byte_identical true、"
            "pixel_diff_count 0、max_channel_diff 0、dev_vs_committed [0,0,0,0]、fresh bbox (42,34,682,677)、"
            "server_closed true。",
    "影响": "判据面：本轮除 L023 定字＋5 源仓相对重生成外零新卡面像素——248 张双版卡面 manifest 仍 124 张"
            "（OK 80／MISSING 39／BACK 5）；卡面闸门 119 张违例 0、印章素材闸门违例 0（沿 C145）、"
            "备份闸门 --verify 违例 0、备份正负测 10 条 OK。"
            "交付面：5 张专用图＋落点 JSON＋备份台账＋备份工具＋备份正负测入库（可版本化），248 张活跃卡面像素"
            "归档落仓外、图本体仍 gitignored；异地副本与图集源（75 张 OK 依赖）的备份属用户 infra，本轮只给本机还原点。"
            "文档面：设计/2026-10-31-分期路线图.md 第 30 行现值句改 146 条／C146，由 test_doc_drift 对账；"
            "裁定计数钉同步处数与全量单测读数只写移交清单 §55.27 一处，本条不抄第二份；"
            "本条不进合订本、不触发 docx 重导、也不作废第 18 签（未动原稿／手册／总纲）。"
            "未收口面：§55.24 偏差②（39 张 MISSING 等补投＝待办 #47）仍在挂——本轮 manifest 实测 39 张 MISSING "
            "按类型分为 模板正面 5／职业卡 20／景群地标卡 3／物品卡 3／能力卡 3／兑换卡 5；其中可派生写串与属产品决策"
            "待拍板的分档按移交清单 §55.26 偏差③（职业 20／景群地标 3 可从既有开图提示词按 C143 派生路径取正文，"
            "兑换 5／模板正面 5／物品 3／能力 3 的实景方向正典沉默、属产品决策），未拍板前不写串不投；#47/#50 属花钱调用，"
            "须用户逐轮重新放行＋探针＋遇 403 code 112 就地停手，本轮未投、未花额度。画风侧仍是照片侧"
            "（C 路线明付，CLIP R1 重读 247 枚落照片侧＝最大未收口，沿 C139）。`card-lab/seal.html` 生成器留删"
            "未拍板（§A4）。异地备份 infra 与图集源备份待用户定。",
}


def main():
    raw = P.read_text(encoding='utf-8')
    before = json.loads(raw)
    assert len(before) == 145, '前置断言失败：现读 %d 条，本脚本只负责追加 C146' % len(before)
    assert before[-1]['编号'] == 'C145', '前置断言失败：末条不是 C145'
    sha_before = hashlib.sha256(raw.encode('utf-8')).hexdigest()

    entry = json.dumps(RULING, ensure_ascii=False, indent=2)
    entry = '\n'.join(('  ' + ln) if ln.strip() else ln for ln in entry.split('\n'))
    tail = '  }\n]\n'
    assert raw.endswith(tail), '前置断言失败：文件尾形态与脚本假设不符'
    new_raw = raw[:-len(tail)] + tail[:-len(']\n')] + ',\n' + entry + '\n]\n'

    after = json.loads(new_raw)
    assert len(after) == 146, '写盘前校验失败：解析得 %d 条' % len(after)
    assert [r['编号'] for r in after[:145]] == [r['编号'] for r in before], '前 145 条编号序列变了'
    assert json.dumps(after[:145], ensure_ascii=False, sort_keys=True) == \
        json.dumps(before, ensure_ascii=False, sort_keys=True), '前 145 条内容变了'
    assert new_raw.startswith(raw[:len(raw) - len(tail)]), '前 145 条的原文形态变了'

    P.write_text(new_raw, encoding='utf-8')
    written = P.read_text(encoding='utf-8')
    re_parsed = json.loads(written)
    print('追加前 %d 条／%d 字节／%s' % (len(before), len(raw.encode('utf-8')), sha_before[:12]))
    print('追加后 %d 条／%d 字节／%s' % (len(re_parsed), len(written.encode('utf-8')),
                                     hashlib.sha256(written.encode('utf-8')).hexdigest()[:12]))
    print('末条编号', re_parsed[-1]['编号'])
    print('前 145 条写盘前后逐字段对拍：未变（同一 json 序列化串相等）')


if __name__ == '__main__':
    main()