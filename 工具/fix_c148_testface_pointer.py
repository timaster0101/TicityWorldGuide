# -*- coding: utf-8 -*-
"""把 C148「原因」里的测试面读数改成指向移交清单 §55.29 的指针。

起因：`fix_c148_readouts.py` 刚把条数钉成 9→14、`Ran 20 in 0.421s`，同一轮里又给
`test_build_card_html.py` 加了台标带双向闸门（14→15），那两个数当场又过期。
会漂移的计数不抄第二份，改成指针；条数与计时只在 §55.29 ④ 一处出。
手法同 fix_c148_readouts：raw JSON 片段手术、`newline=''` 保 CRLF、前 147 条序列化对拍、
`append_ruling_c148.py` 的 RULING 整块重生成后 exec 四字段对拍。
"""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PJSON = ROOT / "数据" / "设定裁定记录.json"
PPY = ROOT / "工具" / "append_ruling_c148.py"

OLD = ("测试面：`test_build_card_html.py` 9→**14** 条、新增 `test_build_card_main_prompts.py` **6** 条，"
       "本轮单跑 `Ran 20 in 0.421s／OK`（14＋6）、渲染器单模块 `Ran 14 in 0.280s／OK`；"
       "§55.29 那轮再补两条几何接线负测 `test_seal_css_percentages_are_derived_not_recopied`"
       "（CSS 字面量必须等于 `pct(G.SEAL_LANDING_B[k])`）与 `test_seal_landing_clears_badge_band_at_measured_box`"
       "（逐边对回实测框并断言可见下沿 ≤ 1024−44），并对 `SEAL_LANDING_B[\"bottom_r\"]` 做变异："
       "改 0.0 时 failures=2 判红、改回后文件指纹与改前一致。")
NEW = ("测试面：`工具/test_build_card_html.py` 与 `工具/test_build_card_main_prompts.py` 的用例条数与计时"
       "属会漂移的计数，**只写在移交清单 §55.29 ④ 一处，本条不抄第二份**。本轮新增的三条判据是"
       "`test_seal_css_percentages_are_derived_not_recopied`（CSS 字面量必须等于 `pct(G.SEAL_LANDING_B[k])`）、"
       "`test_seal_landing_clears_badge_band_at_measured_box`（逐边对回 Chrome 实测框并断言可见下沿 "
       "≤ 1024−`SEAL_BADGE_BAND`）与 `test_badge_band_is_the_minimal_cover_of_the_full_bleed_measurement`"
       "（台标带常数双向钉住满幅实测上界：调小判压台标、调大判白丢净空）；"
       "变异负测见 §55.29 ④。")


def esc(s):
    return json.dumps(s, ensure_ascii=False)[1:-1]


def main():
    raw = PJSON.read_text(encoding="utf-8", newline="")
    before = json.loads(raw)
    assert len(before) == 148 and before[-1]["编号"] == "C148"
    sha_b = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    e_old = esc(OLD)
    assert raw.count(e_old) == 1, "片段命中 %d 次（应恰 1）" % raw.count(e_old)
    PJSON.write_text(raw.replace(e_old, esc(NEW)), encoding="utf-8", newline="")

    disk = PJSON.read_text(encoding="utf-8", newline="")
    after = json.loads(disk)
    assert len(after) == 148 and after[-1]["编号"] == "C148"
    assert json.dumps(after[:147], ensure_ascii=False, sort_keys=True) == \
        json.dumps(before[:147], ensure_ascii=False, sort_keys=True), "前 147 条内容变了"

    praw = PPY.read_text(encoding="utf-8", newline="")
    lines = praw.split("\n")
    i0 = [i for i, l in enumerate(lines) if l == "RULING = {"][0]
    i1 = [i for i in range(i0 + 1, len(lines)) if lines[i] == "}"][0]
    body = "RULING = " + json.dumps(after[-1], ensure_ascii=False, indent=4)
    PPY.write_text("\n".join(lines[:i0] + body.split("\n") + lines[i1 + 1:]), encoding="utf-8", newline="")
    spec = importlib.util.spec_from_file_location("ar", str(PPY))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for k in ("编号", "裁定", "原因", "影响"):
        assert mod.RULING[k] == after[-1][k], "脚本与盘上 %s 字段不等" % k

    print("订正前 148 条／%d 字节／%s" % (len(raw.encode("utf-8")), sha_b))
    print("订正后 148 条／%d 字节／%s（行尾数 %d）"
          % (len(disk.encode("utf-8")), hashlib.sha256(disk.encode("utf-8")).hexdigest()[:12],
             disk.count("\r\n")))
    print("前 147 条逐字段对拍：未变；脚本 RULING 与盘上 C148 四字段逐字相等：True")


if __name__ == "__main__":
    main()
