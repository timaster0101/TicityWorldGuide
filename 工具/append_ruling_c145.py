#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""追加裁定 C145（收口 C144 未收口面①②③／移交清单 §55.25 偏差①②③）。

与 append_ruling_c144.py 同构：先解析并断言前 144 条写盘前后逐字未变，再只在数组尾部插入，
最后重新解析确认条数与末条编号。手改这份 144 条、约 302KB 的数组会同时惊动多处条数钉。
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / '数据' / '设定裁定记录.json'

RULING = {
    "编号": "C145",
    "裁定": "（2026-11-08 收口 C144「未收口面」第 ①②③ 条与移交清单 §55.25 偏差①②③）"
            "三块落地："
            "(1) **台标带从样本上界 35 px 改为全量扫描实测下界 44 px**——`工具/measure_aigc_badge.py` "
            "逐张扫 manifest status=OK 的 80 张源图（非抽样），取可检出台标上沿距实景下沿的最大值上圆整；"
            "`工具/verify_card_faces.py` 的 `SEAL_BADGE_BAND` 由 35 改 44，第 7 条判据随之收紧。"
            "(2) **印章渲染真源入仓并加素材漂移闸门**——720 素材渲染件版本化为 "
            "`数据/运行时资产/印章-已获得-酒红.png`（该目录不在 `.gitignore` 内），"
            "`工具/verify_seal_asset.py` 把它的非透明外接框占比逐边对回 `SEAL_VIS`（容差 0.01），"
            "素材被改（viewBox／环径／字位）即判红；生成器 `card-lab/seal.html` 仍在仓外属 §A4 遗留件，"
            "但本仓从此有可版本化、受守护的渲染真源。"
            "(3) **运行时叠章接上参考消费方**——`工具/stamp_seal.py` 的落点只从 "
            "`verify_card_faces.seal_boxes()` 取、不另抄第三份坐标，整张 720 素材缩到落点框边长、"
            "按框左上角 alpha 合成；背面与 OVERFLOW 不叠章（119 张），页端／程序叠章应镜像此取法。",
    "原因": "三块都有本轮实测读数，不是措辞偏好。"
            "(1) 台标带：全量 80 张 OCR 检出 24／未检出 56，可检出台标上沿距实景下沿 max 43.8／min 15.1 px"
            "（真源 `数据/台标带实测.json`），ceil(43.8)＝44；印章可见下沿到实景下沿净距三档实测均 47.0 px，"
            "故 band 合法整数窗口 [44,47]、取最小覆盖值 44（对台标侧余 0.2、对印章侧余 3.0）。"
            "C144 的 35 只是 4/80 样本上界，被全量扫描里 L002 的 43.8 推翻——35 会在那 6 张"
            "（L002/D01/D02/L004/L048/L044）上让印章压到台标。"
            "(2) 素材：入仓件与仓外 `vibe_images/印章-已获得-酒红.png` 逐字节 cmp 相等、sha256 前 12 位同为"
            "`641bf85f2047`、266546 字节；alpha 外接框 (42,34,682,677)、可见占比 (0.0583,0.0472,0.9472,0.9403)，"
            "与 `SEAL_VIS` (0.058,0.049,0.946,0.939) 逐边最大偏差 0.0018（≈1.3 px），容差 0.01（≈7.2 px）"
            "留约 5.5 倍抖动余量、环径/字位级改动远超此值。"
            "(3) 消费方：落点框/可见章面/实景下沿三组读数与闸门 `seal_boxes()` 逐档相等（单测断言），"
            "真仓应叠章 119 张与闸门统计面一致；CLI 实叠 119 张到仓外预览目录、背面 5 张排除。",
    "影响": "判据面：`工具/verify_card_faces.py` 第 7 条台标带 35→44，真仓实跑 119 张违例 0、EXIT=0；"
            "`工具/verify_seal_asset.py` 真仓通过（违例 0）。单测面：`工具/test_card_faces.py` 11 条仍 OK"
            "（内缩退 0.02 时 119 张全翻「进入台标带」的非退化负测随 band 44 仍成立）；新增 "
            "`工具/test_seal_asset.py` 5 条（真仓/干净夹具判绿，缺失/外接框漂移/全透明判红）与 "
            "`工具/test_stamp_seal.py` 5 条（落点单一真源/背面与放不下排除/真仓 119/章贴进落点框且框外不变/"
            "叠章后可见章面不进台标带）。"
            "交付面：本轮零投放、零新卡面像素，248 张双版卡面与 manifest 未改一个字节；叠章预览 119 张写在"
            "仓外 `_scratch_cardref/seal_check/stamped/`，属本机证据、不随 git 版本化，也不进交付件本体。"
            "目视面：2026-11-08 由主会话（受托执行，委托来源＝用户「继续处理待办 #47 和 §55.25 的偏差」）"
            "在 3 张代表卡叠章预览上逐张看过——`东湖金融线-L009`（3:2）／`板块套系-D01`（7:4）／"
            "`兑换卡-T1轻量`（占位窗），结论章面完整落在实景内、不压任何文字；D01 那张可见「AI生成／TC260」"
            "角标在章的下方未被遮盖，band 44 的几何在像素上兑现。"
            "规范面：第八节「运行时印章落点」条仍是坐标口径唯一出处，台标带 44 的来历与残留缺口、素材入仓与"
            "消费方都只更新在那一条；C144 写在该节的「35 是样本上界」证据缺口注已被取代。"
            "文档面：设计/2026-10-31-分期路线图.md 第 30 行末处现值句改为 145 条／C145，由 test_doc_drift 对账；"
            "裁定计数钉同步处数与全量单测读数只写在移交清单 §55.26 一处，本条不抄第二份。"
            "未收口面：56/80 张台标 OCR 未检出（多为单行小标），43.8 是可检出最大值而非 80 张全部实测上界，"
            "若检出更靠内台标须抬 band（≤47）或内缩；§55.25 偏差④所指 §55.24 的②③⑤⑦ 仍在挂"
            "（39 张 MISSING 等补投＝待办 #47、5 张卡面专用横幅图落点未定、L023 末字仍 □、新卡面在 .gitignore 内"
            "无备份方案）；`card-lab/seal.html` 生成器留删未拍板（§A4）。",
}


def main():
    raw = P.read_text(encoding='utf-8')
    before = json.loads(raw)
    assert len(before) == 144, '前置断言失败：现读 %d 条，本脚本只负责追加 C145' % len(before)
    assert before[-1]['编号'] == 'C144', '前置断言失败：末条不是 C144'
    sha_before = hashlib.sha256(raw.encode('utf-8')).hexdigest()

    entry = json.dumps(RULING, ensure_ascii=False, indent=2)
    entry = '\n'.join(('  ' + ln) if ln.strip() else ln for ln in entry.split('\n'))
    tail = '  }\n]\n'
    assert raw.endswith(tail), '前置断言失败：文件尾形态与脚本假设不符'
    new_raw = raw[:-len(tail)] + tail[:-len(']\n')] + ',\n' + entry + '\n]\n'

    after = json.loads(new_raw)
    assert len(after) == 145, '写盘前校验失败：解析得 %d 条' % len(after)
    assert [r['编号'] for r in after[:144]] == [r['编号'] for r in before], '前 144 条编号序列变了'
    assert json.dumps(after[:144], ensure_ascii=False, sort_keys=True) == \
        json.dumps(before, ensure_ascii=False, sort_keys=True), '前 144 条内容变了'
    assert new_raw.startswith(raw[:len(raw) - len(tail)]), '前 144 条的原文形态变了'

    P.write_text(new_raw, encoding='utf-8')
    written = P.read_text(encoding='utf-8')
    re_parsed = json.loads(written)
    print('追加前 %d 条／%d 字节／%s' % (len(before), len(raw.encode('utf-8')), sha_before[:12]))
    print('追加后 %d 条／%d 字节／%s' % (len(re_parsed), len(written.encode('utf-8')),
                                     hashlib.sha256(written.encode('utf-8')).hexdigest()[:12]))
    print('末条编号', re_parsed[-1]['编号'])
    print('前 144 条写盘前后逐字段对拍：未变（同一 json 序列化串相等）')


if __name__ == '__main__':
    main()