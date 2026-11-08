# -*- coding: utf-8 -*-
"""订正 C148：把 §55.29 那轮真正落地的几何接线、台标带重测、规范改口径、`状态` 字段与测试面读数补进裁定。

手法与 `_scratch_cardref/fix_c147.py` 同源（对 raw JSON 做片段级字符串手术，不整份 re-dump，
以免重排前 147 条的字节），三点差别：
  1. 片段以**解码后**文本书写，脚本内部用 `json.dumps(...)[1:-1]` 取 JSON 转义形态再匹配，避免手写引号转义；
  2. 读写都带 `newline=''`，保住盘上 CRLF（fix_c147 用 read_text/write_text 把整份文件归一成 LF，
     于是留下「LF 318063／盘上 318952」两条口径）；本脚本改完盘上仍是 CRLF，只报盘上那一条，LF 只作参考；
  3. `工具/append_ruling_c148.py` 里的 `RULING` 是跨行 Python 字符串字面量，片段级替换匹配不到，
     改为**整块重生成**（15..75 行 → `RULING = ` + 订正后 C148 的 JSON 字面量，JSON 对象语法即合法 Python 字面量），
     再 exec 该模块断言 `RULING` 与盘上 C148 四字段逐字相等。
"""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PJSON = ROOT / "数据" / "设定裁定记录.json"
PPY = ROOT / "工具" / "append_ruling_c148.py"

# (解码后的 old, new) —— 只动 C148，片段本身不含换行
PAIRS = [
    (
        "修掉单卡文件里主图与印章 src 少一层目录的断链（图片引用实扫 241 串、断链 0）。",
        "修掉单卡文件里主图与印章 src 少一层目录的断链（图片引用实扫 241 串、断链 0）。"
        "(5) **几何口径接线**——印章几何单一真源 `工具/card_geometry.py` 重写为路线 B 口径"
        "（`CANVAS` 768×1024、`SEAL_LANDING_B` 0.24/0.04/0.19、`seal_box_canvas()`／`seal_visible_box_canvas()`），"
        "删掉该文件里与 `build_card_faces.py` 重复且本轮 grep 零消费方的烤 PNG 常量；"
        "渲染器 `.card .seal` 的三个百分数由 `pct(G.SEAL_LANDING_B[...])` 派生、实发值与旧手抄字面量相同"
        "（零视觉变化，改的是抄第二份的隐患）；台标带按满幅口径全量重测"
        "（`工具/measure_aigc_badge.py --full-bleed`，80 张逐张非抽样：检出 23／未检出 57，"
        "可检出台标上沿距实景下沿 max 43.9／min 10.9）并替换真源 `数据/台标带实测.json`，"
        "`SEAL_BADGE_BAND=44` 仍覆盖，C145 那句 43.8 属烤 PNG 窗带口径、已被取代。"
        "落点取渲染真值实测 5 张（playwright `channel=\"chrome\"`、`.card` 强制 768×1024）："
        "章框 (553,645)-(737,829) 边长 184.3、可见章面 (564,654)-(727,818)、主图包围盒恒等 (0,0,768,1024)、"
        "浮层上沿 y=973.5、占位窗与模板面不叠章。",
    ),
    (
        "测试面：`test_build_card_html.py` 9→**12** 条、新增 `test_build_card_main_prompts.py` **6** 条，"
        "本轮单跑 `Ran 18 in 0.400s／OK`、渲染器单模块 `Ran 12 in 0.261s／OK`。",
        "测试面：`test_build_card_html.py` 9→**14** 条、新增 `test_build_card_main_prompts.py` **6** 条，"
        "本轮单跑 `Ran 20 in 0.421s／OK`（14＋6）、渲染器单模块 `Ran 14 in 0.280s／OK`；"
        "§55.29 那轮再补两条几何接线负测 `test_seal_css_percentages_are_derived_not_recopied`"
        "（CSS 字面量必须等于 `pct(G.SEAL_LANDING_B[k])`）与 `test_seal_landing_clears_badge_band_at_measured_box`"
        "（逐边对回实测框并断言可见下沿 ≤ 1024−44），并对 `SEAL_LANDING_B[\"bottom_r\"]` 做变异："
        "改 0.0 时 failures=2 判红、改回后文件指纹与改前一致。",
    ),
    (
        "本轮在该台账补 `状态` 字段声明它是 C146 时代烤 PNG 还原点的冻结记录、"
        "不再由已退役的 `backup_card_faces.py` 维护",
        "本轮在该台账补 `状态` 字段声明它是 C146 时代烤 PNG 还原点的冻结记录、"
        "不再由已退役的 `backup_card_faces.py` 维护（该字段与下面「规范第八节改口径」同在移交清单 §55.29 "
        "那轮真正落地——C148 首发文本只写了主张、没做动作，此处如实订正；同时删掉 "
        "`数据/视觉控制资产/卡牌/768x1024/{无文案,有文案}` 两个 0 文件的空目录）",
    ),
    (
        "文档面：`设计/2026-10-31-分期路线图.md` 第 30 行现值句同步 148 条／C148；",
        "文档面：`设计/2026-10-31-分期路线图.md` 第 30 行现值句同步 148 条／C148；"
        "`设计/2026-10-31-卡面标准样式规范.md` 第八节的交付形态／取图分档／投放形态／落点与版本化／"
        "运行时印章落点／机器判据／台标带来历／目视八条由烤 PNG 口径改为路线 B 口径"
        "（用户原话与叠字数据源两条不动）；",
    ),
    (
        "就地停手。画风侧仍是照片侧（C 路线明付",
        "就地停手。章径口径差未拍板（路线 B 印章框 184.3 px 对烤 PNG 时代裁定的 212 px 小 27.6%，"
        "一行开关 `SEAL_LANDING_B[\"size_r\"]=0.276` 可回到旧视觉尺寸、改后逐边断言会当场判红一次，"
        "沿移交清单 §55.29 偏差①）；画风侧仍是照片侧（C 路线明付",
    ),
]


def esc(s):
    """取该串在 JSON 文本里的转义形态（不含外层引号）。"""
    return json.dumps(s, ensure_ascii=False)[1:-1]


def rebuild_py(entry):
    """把 append_ruling_c148.py 的 RULING 整块换成订正后条目的字面量。"""
    raw = PPY.read_text(encoding="utf-8", newline="")
    lines = raw.split("\n")
    starts = [i for i, l in enumerate(lines) if l == "RULING = {"]
    assert len(starts) == 1, "RULING 起点不唯一：%d" % len(starts)
    i0 = starts[0]
    closes = [i for i in range(i0 + 1, len(lines)) if lines[i] == "}"]
    assert len(closes) >= 1, "找不到 RULING 收尾的 }"
    i1 = closes[0]
    body = "RULING = " + json.dumps(entry, ensure_ascii=False, indent=4)
    new = "\n".join(lines[:i0] + body.split("\n") + lines[i1 + 1:])
    PPY.write_text(new, encoding="utf-8", newline="")
    return i0 + 1, i1 + 1, len(body.split("\n"))


def main():
    raw = PJSON.read_text(encoding="utf-8", newline="")
    before = json.loads(raw)
    assert len(before) == 148 and before[-1]["编号"] == "C148", "起点不是 148 条／末条 C148"
    sha_b = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    bytes_b = len(raw.encode("utf-8"))

    patched = raw
    for old, new in PAIRS:
        e_old = esc(old)
        n = patched.count(e_old)
        assert n == 1, "片段命中 %d 次（应恰 1）：%r" % (n, old[:28])
        patched = patched.replace(e_old, esc(new))
    PJSON.write_text(patched, encoding="utf-8", newline="")

    disk_raw = PJSON.read_text(encoding="utf-8", newline="")
    after = json.loads(disk_raw)
    assert len(after) == 148 and after[-1]["编号"] == "C148"
    assert json.dumps(after[:147], ensure_ascii=False, sort_keys=True) == \
        json.dumps(before[:147], ensure_ascii=False, sort_keys=True), "前 147 条内容变了"

    a, b, nb = rebuild_py(after[-1])
    spec = importlib.util.spec_from_file_location("ar", str(PPY))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for k in ("编号", "裁定", "原因", "影响"):
        assert mod.RULING[k] == after[-1][k], "脚本与盘上 %s 字段不等" % k

    crlf = disk_raw.count("\r\n")
    lf = disk_raw.replace("\r\n", "\n")
    print("订正前 148 条／%d 字节（盘上 CRLF）／%s" % (bytes_b, sha_b))
    print("订正后 148 条／%d 字节（盘上 CRLF，行尾数 %d）／%s"
          % (len(disk_raw.encode("utf-8")), crlf,
             hashlib.sha256(disk_raw.encode("utf-8")).hexdigest()[:12]))
    print("LF 口径参考（非盘上真值）%d 字节／%s"
          % (len(lf.encode("utf-8")), hashlib.sha256(lf.encode("utf-8")).hexdigest()[:12]))
    print("前 147 条逐字段对拍：未变（序列化串相等）")
    print("append_ruling_c148.py 的 RULING 块第 %d..%d 行重生成（%d 行），与盘上 C148 四字段逐字相等：True"
          % (a, b, nb))


if __name__ == "__main__":
    main()
