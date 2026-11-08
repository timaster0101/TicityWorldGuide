#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡面 HTML 渲染器（路线 B：主图全铺 + 文字叠图 + 底部暗黑半透明浮层）。

取代旧的「Pillow 烤 PNG」交付形态：每张卡只交付一张满幅 3:4 主图（80 张 OK 卡＝
`数据/视觉控制资产/卡牌/主图3x4/<ID>.png`，768×1024 原生、进满幅窗零裁切），最终呈现由本渲染器产出的
HTML 把主图 + 标题/副标题/底部文案 + 印章 + 半透明浮层叠出来。文案是运行时注入模板的，不烤进像素。

产物（全部落 `数据/卡面HTML/`，该目录不在 .gitignore 内、可版本化；3:4 主图落在 gitignored 的
`数据/视觉控制资产/` 里，与 manifest 同一条口径）：
  - card.css        共享样式（印章落点比例从 `card_geometry.SEAL_LANDING_B` 生成，不在此另抄数字；
                    画幅/浮层口径见规范第八节）
  - template.html   单卡 HTML 模板骨架（占位符注释，供页面程序镜像）
  - cards.json      逐卡数据（纯数据，无样式）
  - index.html      画廊：用 JS 把 cards.json 注入模板，渲染全部 124 张双版

数据真源：`数据/视觉控制资产/卡牌/768x1024/manifest.json`（title/subtitle/bottom 已是派生后的
渲染值）。无主图的卡渲染占位窗：模板背面／模板正面（档 A）给模板面标签，其余 MISSING 给「实景待投」。
"""
import json
import os
import re

import card_geometry as G

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "数据", "视觉控制资产", "卡牌", "768x1024", "manifest.json")
SEAL_SRC = os.path.join(ROOT, "数据", "运行时资产", "印章-已获得-酒红.png")
OUT_DIR = os.path.join(ROOT, "数据", "卡面HTML")

# 与 build_card_faces.py 对齐的观感常量（颜色取自其真源，浮层为用户 2026-11-08 拍板值）
INK_TITLE = "#F6ECD6"
INK_SUB = "#e7d8b6"
INK_BOTTOM = "#F6ECD6"
GOLD = "#B8965E"
GOLD_SOFT = "rgba(216,182,120,.3)"
PANEL_BG = "rgba(0,0,0,.3)"          # 暗黑色 70% 透明浮层
# 浮层不加 backdrop-filter：主图右下角的平台强制「AI生成」角标就在台标带里（实测上沿最靠内 971.4 px，
# 浮层上沿 973.5 px），6px 模糊会把它糊成不可读＝遮盖 AIGC 标识。去掉模糊后角标逐笔清晰，
# 而浮层带亮度读数与带模糊时相同（4 张抽样均值差 ≤0.2、文字最亮 236 不变），文案可读性没有代价。


TEMPLATE_FACES = ("模板背面", "模板正面")


def pct(r):
    """把落点比例换算成 CSS 百分数字面量。"""
    return "%g" % (r * 100)


def rel(url_path):
    """输出目录到目标文件的相对路径，正斜杠，供 HTML 引用。"""
    p = os.path.relpath(url_path, OUT_DIR).replace("\\", "/")
    return p


def main_image(card):
    """OK 卡返回主图相对路径；MISSING/BACK 返回 None（渲染占位窗）。"""
    if card["status"] != "OK" or not card.get("source"):
        return None
    return rel(os.path.join(ROOT, card["source"]))


def title_lines(card):
    """district 系列名(金) + 片区名(亮) 两行；其余单行。返回 [(text, cls)]。"""
    title = card.get("title") or ""
    if card["template"] == "district" and "·" in title:
        prefix, _, rest = title.partition("·")
        return [(prefix + "·", "gold"), (rest, "bright")]
    return [(title, "bright")] if title else []


def build_card_records(manifest):
    seal_rel = rel(SEAL_SRC)
    records = []
    for c in manifest["cards"]:
        records.append({
            "idx": c["idx"],
            "code": c["code"],
            "card_type": c["card_type"],
            "template": c["template"],
            "status": c["status"],
            "title": c.get("title") or "",
            "subtitle": c.get("subtitle") or "",
            "bottom": c.get("bottom") or "",
            "main_image": main_image(c),
            "template_face": c["card_type"] in TEMPLATE_FACES,
            "seal": seal_rel,
            "file": c.get("file") or "",
        })
    return records


def render_card_html(rec, variant, prefix=""):
    """把一条记录渲染成一张卡的 HTML（variant: 有文案/无文案）。供 index.html 的 JS 镜像，
    这里同时用于 template.html 的真实样本。
    prefix：图片 src 相对本文件所在目录的补前缀；cards/ 下的单卡深一层须传 "../"。"""
    lines = title_lines(rec)
    title_html = "".join(
        '<div class="tline %s">%s</div>' % (cls, esc(t)) for t, cls in lines) or ""
    sub_html = '<div class="subtitle">%s</div>' % esc(rec["subtitle"]) if rec["subtitle"] else ""
    deco = {"landmark": '<div class="gold-rule"></div>',
            "info": '<div class="gold-dash"></div>',
            "district": '<div class="gold-rule"></div>'}.get(rec["template"], "")

    if rec["main_image"]:
        media = '<img class="bg" src="%s%s" alt="">' % (prefix, rec["main_image"])
        seal = '<img class="seal" src="%s%s" alt="">' % (prefix, rec["seal"])
    else:
        label = ("卡背" if rec["card_type"] == "模板背面"
                 else "模板正面" if rec["card_type"] == "模板正面" else "实景待投")
        media = '<div class="placeholder">%s</div>' % esc(label)
        seal = ""

    panel = ""
    if variant == "有文案" and rec["bottom"]:
        panel = '<div class="panel"><div class="bottom">%s</div></div>' % esc(rec["bottom"])

    return (
        '<div class="card %s %s">' % (rec["template"], "noimg" if not rec["main_image"] else "")
        + media
        + '<div class="top">%s%s%s</div>' % (
            '<div class="title">%s</div>' % title_html if title_html else "", sub_html, deco)
        + seal + panel
        + "</div>"
    )


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


CSS = """/* 卡面 HTML 渲染器样式（路线 B）。画幅/浮层/印章落点口径见《卡面标准样式规范》第八节，印章几何单一真源 card_geometry.py。 */
:root{--ink-title:%(INK_TITLE)s;--ink-sub:%(INK_SUB)s;--ink-bottom:%(INK_BOTTOM)s;
  --gold:%(GOLD)s;--gold-soft:%(GOLD_SOFT)s;--panel-bg:%(PANEL_BG)s;
  --radius:22px}
*{box-sizing:border-box}
body{margin:0;background:#1c1a17;color:#e8e2d6;
  font-family:"Alibaba PuHuiTi 3.0","Microsoft YaHei",system-ui,sans-serif;padding:28px 20px 48px}
h1{font-size:20px;font-weight:600;margin:0 0 6px}
.legend{font-size:13px;color:#a89c88;max-width:1000px;line-height:1.7;margin:0 0 24px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:26px}
.pair{display:flex;flex-direction:column;gap:8px}
.pair .cap{font-size:12px;color:#b8965e;letter-spacing:.4px}
.pair .cap b{color:#fff}

/* 满幅主图卡：图铺满整张，字叠图上，底部暗黑半透明浮层 */
.card{position:relative;aspect-ratio:3/4;width:100%%;border-radius:var(--radius);overflow:hidden;
  background:#2a2620;box-shadow:0 12px 36px rgba(0,0,0,.55)}
.card .bg{position:absolute;inset:0;width:100%%;height:100%%;object-fit:cover}
.card .placeholder{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  background:repeating-linear-gradient(45deg,#efe7d8,#efe7d8 14px,#e6dcc8 14px,#e6dcc8 28px);
  color:#a89c88;font-size:15px;letter-spacing:2px}
.card .top{position:absolute;left:0;right:0;top:0;padding:16px 14px 30px;
  background:linear-gradient(180deg,rgba(18,14,8,.72),rgba(18,14,8,.28) 55%%,transparent)}
.card .title{text-align:center;line-height:1.28;text-shadow:0 1px 8px rgba(0,0,0,.7)}
.card .tline{font-size:18px;font-weight:700}
.card .tline.bright{color:var(--ink-title)}
.card .tline.gold{color:var(--gold);font-size:15px;font-weight:600}
.card .subtitle{margin-top:5px;text-align:center;color:var(--ink-sub);font-size:12px;
  letter-spacing:2px;text-shadow:0 1px 5px rgba(0,0,0,.6)}
.card .gold-rule{margin:8px auto 0;width:56%%;height:2px;
  background:linear-gradient(90deg,transparent,var(--gold),transparent)}
.card .gold-dash{margin:8px auto 0;width:34px;height:2px;background:var(--gold)}
.card .seal{position:absolute;width:%(SEAL_W)s%%;aspect-ratio:1;right:%(SEAL_RIGHT)s%%;bottom:%(SEAL_BOTTOM)s%%;
  filter:drop-shadow(0 2px 4px rgba(0,0,0,.5))}
.card .panel{position:absolute;left:0;right:0;bottom:0;padding:16px 14px 14px;
  background:var(--panel-bg);border-top:1px solid var(--gold-soft)}
.card .bottom{text-align:center;color:var(--ink-bottom);font-size:13px;letter-spacing:.5px;
  line-height:1.5;text-shadow:0 1px 4px rgba(0,0,0,.5)}
""" % {"INK_TITLE": INK_TITLE, "INK_SUB": INK_SUB, "INK_BOTTOM": INK_BOTTOM,
      "GOLD": GOLD, "GOLD_SOFT": GOLD_SOFT, "PANEL_BG": PANEL_BG,
      "SEAL_W": pct(G.SEAL_LANDING_B["size_r"]),
      "SEAL_RIGHT": pct(G.SEAL_LANDING_B["right_r"]),
      "SEAL_BOTTOM": pct(G.SEAL_LANDING_B["bottom_r"])}

TEMPLATE_DOC = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<link rel="stylesheet" href="card.css"><title>单卡模板骨架</title></head>
<body>
<!-- 单张卡模板。页面程序按 cards.json 逐字段注入；文案运行时叠加、不烤进像素。
     .card 的 template 类 ∈ landmark|district|info|back；无主图时 .placeholder 顶替 .bg。 -->
<div class="card landmark">
  <img class="bg" src="{{main_image}}" alt="">
  <div class="top">
    <div class="title"><div class="tline bright">{{title}}</div></div>
    <div class="subtitle">{{subtitle}}</div>
    <div class="gold-rule"></div>
  </div>
  <img class="seal" src="{{seal}}" alt="">
  <div class="panel"><div class="bottom">{{bottom}}</div></div>
</div>
</body></html>
"""


def render_index(records):
    data = json.dumps(records, ensure_ascii=False)
    cards_html = []
    for rec in records:
        with_text = render_card_html(rec, "有文案")
        no_text = render_card_html(rec, "无文案")
        label = rec["code"] or rec["file"].split("-")[0]
        cards_html.append(
            '<div class="pair"><div class="cap"><b>%s</b> · %s · %s</div>%s%s</div>'
            % (esc(label), esc(rec["card_type"]), esc(rec["status"]), with_text, no_text))
    n_img = sum(1 for r in records if r["main_image"])
    n_face = sum(1 for r in records if r["template_face"])
    n_pending = sum(1 for r in records if not r["main_image"] and not r["template_face"])
    return """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>钛湖城卡面 · HTML 渲染画廊</title>
<link rel="stylesheet" href="card.css"></head>
<body>
<h1>钛湖城卡面 · HTML 渲染画廊（路线 B：主图全铺 + 文字叠图 + 半透明浮层）</h1>
<p class="legend">每格左=有文案版、右=无文案版。主图取 manifest.source（现 __NIMG__ 张，全部 3:4 原生 768×1024 满幅、零裁切，由 card3x4_R1／R2 两轮投出）；
模板背面＋模板正面共 __NFACE__ 张走程序模板面（用户 2026-11-08 拍板档 A、不投实景），其余 __NPENDING__ 张 MISSING 显占位窗。文案与印章由 HTML 运行时叠加、不烤进像素。共 <span id="n"></span> 张。
数据真源 <code>cards.json</code>，样式 <code>card.css</code>，单卡骨架 <code>template.html</code>。</p>
<div class="grid">
__CARDS__
</div>
<script>
  var records = __DATA__;
  document.getElementById('n').textContent = records.length;
</script>
</body></html>
""".replace("__NIMG__", str(n_img)).replace("__NFACE__", str(n_face)) \
   .replace("__NPENDING__", str(n_pending)) \
   .replace("__CARDS__", "\n".join(cards_html)).replace("__DATA__", data)


def main(argv=None):
    with open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)
    records = build_card_records(manifest)
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(OUT_DIR, "cards"), exist_ok=True)

    with open(os.path.join(OUT_DIR, "card.css"), "w", encoding="utf-8") as fh:
        fh.write(CSS)
    with open(os.path.join(OUT_DIR, "template.html"), "w", encoding="utf-8") as fh:
        fh.write(TEMPLATE_DOC)
    with open(os.path.join(OUT_DIR, "cards.json"), "w", encoding="utf-8") as fh:
        json.dump(records, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(render_index(records))

    # 逐卡 HTML（有文案版），供页面程序直接取用单张
    for rec in records:
        code = rec["code"] or ("idx%03d" % rec["idx"])
        doc = ('<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">'
               '<link rel="stylesheet" href="../card.css"><title>%s</title></head>'
               '<body>%s</body></html>' % (esc(code), render_card_html(rec, "有文案", "../")))
        with open(os.path.join(OUT_DIR, "cards", "%s.html" % code), "w", encoding="utf-8") as fh:
            fh.write(doc)

    ok = sum(1 for r in records if r["status"] == "OK")
    print("产出目录", rel(OUT_DIR))
    print("卡数 %d（OK %d / 非 OK %d）" % (len(records), ok, len(records) - ok))
    print("有主图 %d / 占位窗 %d" % (sum(1 for r in records if r["main_image"]),
                                  sum(1 for r in records if not r["main_image"])))
    print("模板面 %d（背面 %d / 正面 %d） / 实景待投 %d" % (
        sum(1 for r in records if r["template_face"]),
        sum(1 for r in records if r["card_type"] == "模板背面"),
        sum(1 for r in records if r["card_type"] == "模板正面"),
        sum(1 for r in records if not r["main_image"] and not r["template_face"])))
    print("文件：card.css / template.html / cards.json / index.html / cards/*.html(%d)" % len(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
