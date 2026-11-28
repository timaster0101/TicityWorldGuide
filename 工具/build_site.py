# -*- coding: utf-8 -*-
"""生成钛湖城设定集介绍网站（网站/index.html、atlas.html、locations.html）。

设计稿与版式在 网站/tokens.css、网站/site.css（手写，不由本脚本产出）；
本脚本只负责把 数据/城市空间名录.json、数据/开图清单.json、数据/图集OSS.json
里的真实条目渲染成页面，避免手抄 312 条。

用法：
    python -X utf8 工具/build_site.py
    python -X utf8 工具/build_site.py --check     # 只校验盘上页面与现渲染一致
"""

from __future__ import annotations

import argparse
import html
import io
import json
import re
import shutil
import sys
import urllib.parse
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "网站"
DATA = ROOT / "数据"

MANIFEST = DATA / "开图清单.json"
REGISTRY = DATA / "城市空间名录.json"
OSS_LINKS = DATA / "图集OSS.json"
WORD_CHECK = DATA / "Word核验结果.json"
RULINGS = DATA / "设定裁定记录.json"
KNOWLEDGE = DATA / "AI地点知识库.json"

SITE_VERSION = "v0.3.6"

# 分卷正文的在线阅读地址（站内不复制 11 卷正文，链到仓库）
REPO_BLOB = "https://github.com/timaster0101/TicityWorldGuide/blob/main/"

# 站点图标：暗底 + 绿塔 + 湖面弧线，内联成 data URI，不额外落文件
FAVICON = "data:image/svg+xml," + urllib.parse.quote(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="14" fill="#25292d"/>'
    '<rect x="29" y="11" width="6" height="27" rx="1" fill="#3eb182"/>'
    '<ellipse cx="32" cy="45" rx="18" ry="6.5" fill="none" stroke="#3ec58c" stroke-width="3"/>'
    "</svg>",
    safe="",
)

# 仓内三张 SVG 地图（相对 网站/ 的路径 + 标题 + 说明）
MAPS = [
    ("全域卫星聚落图.svg", "全域卫星与聚落", "24 个外围聚落、湖面与环山的关系，含湖心原点与四圈层分界。"),
    ("主城区空间索引图.svg", "主城区空间索引", "主城区的道路、岸线与扇区划分，按 D／F／L 编号标位。"),
    ("产业空间图层图.svg", "产业空间图层", "产业小镇与功能区叠加：一镇一链、货运通道与班车动线。"),
]

TYPE_ORDER = ["城市片区", "功能区", "标志性建筑", "居民区", "产业小镇", "特色村落"]
TYPE_META = {
    "城市片区": ("D", "一个片区＝一张自洽的街区断面：用地、人口、产业、通勤与观感都在同一条里写定。"),
    "功能区": ("F", "片区之下的功能组团：一条街干什么、谁在这里上班、几点最挤，都按功能分格。"),
    "标志性建筑": ("L", "单体建筑：层数、高度、建筑面积、外观材质与内部流线，逐座登记。"),
    "居民区": ("R", "住的地方：户数、人口、房租档、到最近锚点的距离，以及夜里亮灯的窗。"),
    "产业小镇": ("S", "山外台地上的产业聚落：一条产业链、几座厂、一批通勤班车。"),
    "特色村落": ("S", "保留旧肌理的村落：以农业、文旅与手工为主，尺度小、节奏慢。"),
}
RING_ORDER = ["内湖环", "外城环", "产业小镇", "特色村落"]
RING_DESC = {
    "内湖环": "湖岸十公里内的主城，行政、金融、文教与高密度居住集中在这里。",
    "外城环": "主城之外的近郊带，生态、产业外溢与中低密居住交错。",
    "产业小镇": "沿对外通道的山外台地，一镇一链，重货运与班车通勤。",
    "特色村落": "保留旧村肌理的低密度聚落，农业、文旅与手工为主。",
}

# 首页挑图：id -> 说明；顺序即展示顺序
HERO_ID = "D08"
GALLERY_IDS = ["D18", "D03", "L007", "R061", "F021", "S13"]


def load_json(path: Path):
    with io.open(path, encoding="utf-8") as fp:
        return json.load(fp)


def num(value, digits=0):
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        if digits == 0:
            return "{:,}".format(int(round(value)))
        return "{:,.{d}f}".format(value, d=digits)
    return str(value)


def esc(text):
    return html.escape(str(text), quote=True)


class Site:
    def __init__(self):
        self.manifest = load_json(MANIFEST)
        self.registry = load_json(REGISTRY)
        self.oss = load_json(OSS_LINKS)
        self.items = self.manifest["items"]
        self.entries = {e["id"]: e for e in self.registry["entries"]}
        self.by_id = {it["id"]: it for it in self.items}
        self.type_counts = Counter(it["type"] for it in self.items)
        self.ring_counts = Counter(it["ring"] for it in self.items)
        self.img_total = self.oss["统计"]["件数"]
        self.word = load_json(WORD_CHECK)
        self.rulings = load_json(RULINGS)
        self.volumes = sorted(p for p in (ROOT / "分卷").glob("*.md"))
        self.kb = {row["id"]: row for row in load_json(KNOWLEDGE)}
        self.pages = (self.word.get("段落数") and None) or None
        self.docx_pages = self._docx_pages()

    # ---------- 读数 ----------
    def _docx_pages(self):
        try:
            doc = load_json(DATA / "Word渲染目视.json")
            for key in ("目视记录", "记录", "signs"):
                node = doc.get(key) if isinstance(doc, dict) else None
                if isinstance(node, list) and node:
                    node = node[-1]
                if isinstance(node, dict):
                    readings = node.get("实测读数") or {}
                    if readings.get("页数"):
                        return int(readings["页数"])
        except Exception:
            pass
        return 424

    def hero_item(self):
        return self.by_id.get(HERO_ID) or self.items[0]

    def url_of(self, eid):
        """在册图直链：image_url 与 image_file 逐格对齐，第 0 格即最新一轮那枚。"""
        it = self.by_id.get(eid)
        if not it:
            return None
        urls = it.get("image_url") or []
        return urls[0] if urls else None

    def versions_of(self, eid):
        """同一地点在册的全部格（越靠前越新），用于图集灯箱的版本条。"""
        it = self.by_id.get(eid) or {}
        return [u for u in (it.get("image_url") or []) if u]

    def volume_of(self, eid):
        """该地点所属的分卷成稿（相对仓库根的路径，如 分卷/02-城市片区.md）。"""
        row = self.kb.get(eid) or {}
        vol = row.get("volume") or ""
        return vol if vol.startswith("分卷/") else ""

    def entry_text(self, eid):
        e = self.entries.get(eid, {})
        return e.get("focus") or "", e.get("visual") or ""

    # ---------- 骨架 ----------
    NAV = OrderedDict(
        [
            ("index.html", "世界"),
            ("locations.html", "地点"),
            ("map.html", "地图"),
            ("atlas.html", "图集"),
            ("index.html#howto", "怎么用"),
        ]
    )

    def shell(self, title, desc, body, current=None, extra_class="", script=None, og_image=None):
        nav = []
        for href, label in self.NAV.items():
            cur = ' aria-current="page"' if href == current else ""
            nav.append('<a href="%s"%s>%s</a>' % (href, cur, label))
        og = og_image or self.url_of(HERO_ID) or ""
        head_meta = (
            '<meta charset="utf-8" />\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1" />\n'
            "<title>%(title)s</title>\n"
            '<meta name="description" content="%(desc)s" />\n'
            '<link rel="icon" href="%(icon)s" />\n'
            '<meta name="theme-color" content="#25292d" />\n'
            '<meta property="og:type" content="website" />\n'
            '<meta property="og:site_name" content="钛湖城城市设定集" />\n'
            '<meta property="og:locale" content="zh_CN" />\n'
            '<meta property="og:title" content="%(title)s" />\n'
            '<meta property="og:description" content="%(desc)s" />\n'
            '<meta property="og:image" content="%(og)s" />\n'
            '<meta property="og:image:alt" content="钛湖城 · 城市设定集封面" />\n'
            '<meta name="twitter:card" content="summary_large_image" />\n'
            '<meta name="twitter:title" content="%(title)s" />\n'
            '<meta name="twitter:description" content="%(desc)s" />\n'
            '<meta name="twitter:image" content="%(og)s" />\n'
            '<link rel="stylesheet" href="tokens.css" />\n'
            '<link rel="stylesheet" href="site.css" />\n'
        ) % {
            "title": esc(title),
            "desc": esc(desc),
            "icon": FAVICON,
            "og": esc(og),
        }
        rest = (
            "</head>\n<body class=\"%s\">\n"
            '<header class="topbar"><div class="wrap topbar__inner">'
            '<a class="brand" href="index.html"><span class="brand__mark">钛湖城</span>'
            '<span class="brand__sub">URBAN CANON</span></a>'
            '<nav class="nav">%s</nav>'
            '<span class="tag-ver">%s</span>'
            "</div></header>\n"
            "<main>\n%s</main>\n%s\n%s\n</body>\n</html>\n"
        ) % (
            extra_class, "".join(nav), SITE_VERSION, body, self.footer(),
            ('<script src="%s" defer></script>' % esc(script)) if script else "",
        )
        return "<!DOCTYPE html>\n" '<html lang="zh-CN">\n<head>\n' + head_meta + rest

    def footer(self):
        return (
            '<footer class="footer"><div class="wrap">'
            '<div class="footer__grid">'
            "<div>"
            '<h4>钛湖城 · 城市设定集</h4>'
            "<p style=\"margin:0;max-width:32em\">一座 2013 年基准年的原创虚构城市。"
            "所有地点、数字与规则均为设定产物，与现实城市无关。</p>"
            "</div>"
            "<div><h4>内容</h4><ul>"
            '<li><a href="index.html">世界总览</a></li>'
            '<li><a href="locations.html">312 个地点</a></li>'
            '<li><a href="map.html">地图</a></li>'
            '<li><a href="atlas.html">图集</a></li>'
            "</ul></div>"
            "<div><h4>授权</h4><ul>"
            '<li>正文与数据 CC BY-NC-SA 4.0</li>'
            '<li>名称标识保留，二创须标「非官方」</li>'
            "<li>生成图带 C2PA 元数据，不得去除</li>"
            "</ul></div>"
            "</div>"
            '<div class="footer__note">'
            "<span>版本 %s · 第 %d 条裁定为最新 · %d 页合订本</span>"
            "<span>页面由 工具/build_site.py 从 数据/ 生成；图在 OSS</span>"
            "</div>"
            "</div></footer>"
        ) % (SITE_VERSION, len(self.rulings), self.docx_pages)

    # ---------- 首页 ----------
    def index(self):
        hero = self.hero_item()
        total_pop = 3574200
        figures = [
            (num(self.registry.get("region_area_km2", 4608)), "km²", "区域陆域面积"),
            (num(total_pop), "", "区域人口"),
            (num(len(self.items)), "", "已命名地点"),
            (num(len(self.volumes)), "卷", "分卷正文"),
            (num(self.docx_pages), "页", "合订本"),
            (num(self.img_total), "张", "配图与过程图"),
        ]
        fig_html = "".join(
            '<div class="figure"><div class="figure__num">%s<small>%s</small></div>'
            '<div class="figure__label">%s</div></div>' % (n, u, label)
            for n, u, label in figures
        )

        ring_rows = []
        ring_total = sum(self.ring_counts.values()) or 1
        for ring in RING_ORDER:
            n = self.ring_counts.get(ring, 0)
            pct = n / ring_total * 100
            ring_rows.append(
                '<div class="ring"><span class="ring__name">%s</span>'
                '<span class="ring__bar"><i style="width:%.1f%%"></i></span>'
                '<span class="ring__num">%d 处</span>'
                '<span class="ring__desc">%s</span></div>' % (ring, pct, n, RING_DESC[ring])
            )

        type_cards = []
        for t in TYPE_ORDER:
            prefix, blurb = TYPE_META[t]
            sample = [it for it in self.items if it["type"] == t][:3]
            names = "、".join("<b>%s</b>" % esc(s["name"]) for s in sample)
            type_cards.append(
                '<a class="type" href="locations.html#%s" data-count="%d">'
                '<div class="type__prefix">%s · %s</div>'
                '<div class="type__name">%s</div>'
                '<div class="type__sample">%s<br />%s</div></a>'
                % (esc(t), self.type_counts.get(t, 0), prefix, num(self.type_counts.get(t, 0)), esc(t), blurb, names)
            )

        shots = []
        for eid in GALLERY_IDS:
            it = self.by_id.get(eid)
            url = self.url_of(eid)
            if not it or not url:
                continue
            shots.append(
                '<a class="shot" href="%s" target="_blank" rel="noopener">'
                '<img src="%s" alt="%s" />'
                '<span class="shot__cap">%s<span>%s</span></span></a>'
                % (esc(url), esc(url), esc(it["name"]), esc(it["name"]), esc(it["id"]))
            )

        hero_url = self.url_of(HERO_ID) or ""
        body = (
            '<section class="hero">'
            '<div class="hero__media"><img src="%s" alt="钛湖城 %s" /></div>'
            '<div class="wrap"><div class="hero__inner">'
            '<div class="eyebrow">2013 · 原创虚构城市正典</div>'
            "<h1>钛湖城</h1>"
            '<p class="hero__lede">中心有湖，河流延展，四面环山。'
            "这里的一城一街一楼都<b>写进了同一套坐标、同一条口径</b>："
            "三百一十二个地点、四圈层、六类地点，读起来是一座城市，用起来是一份可以直接拿去做故事的底稿。</p>"
            '<div class="hero__cta">'
            '<a class="btn btn--primary" href="locations.html">看 312 个地点</a>'
            '<a class="btn btn--ghost" href="atlas.html">翻图集</a>'
            "</div>"
            '<div class="hero__meta"><span>%s</span><span>%d 个地点</span><span>%d 条设定裁定</span></div>'
            "</div></div></section>"
            '<div class="wrap"><div class="figures">%s</div></div>'
            "%s"
        ) % (
            esc(hero_url),
            esc(hero["name"]),
            esc(hero["name"]),
            len(self.items),
            len(self.rulings),
            fig_html,
            self._sections(ring_rows, type_cards, shots),
        )
        return self.shell(
            "钛湖城 · 城市设定集",
            "2013 年原创虚构城市「钛湖城」的完整设定集：312 个地点、四圈层结构、物价通勤与就业口径、图集与写作规则。",
            body,
            current="index.html",
        )

    def _sections(self, ring_rows, type_cards, shots):
        ridge = (
            '<section class="section" id="what">'
            '<div class="wrap">'
            '<div class="section__head">'
            "<div><div class=\"eyebrow\">01 · 这是一座什么城</div>"
            '<h2 class="h-display">以湖心为原点，向外长出的四道圈层</h2></div>'
            '<p class="section__lead">所有坐标都写在 <strong>THC-LOCAL-2013</strong> 这套本地坐标系里：'
            "千米为单位，湖心为 (0,0)，x 向东、y 向北。地点之间的距离、朝向、日照角度都能直接算出来。</p>"
            "</div>"
            '<div class="split">'
            '<div class="prose">'
            "<p>钛湖城是一座<strong>单中心城市</strong>：湖面占据中央，主城沿湖岸铺开十公里，"
            "再往外是近郊带、山外产业台地与保留旧肌理的村落。四道圈层不是装饰，"
            "它们决定同一件商品在不同圈层的价格系数、一次通勤能走多远、一个岗位要熬几年。</p>"
            "<p>城市运行按<strong>2013 年</strong>为基准年写定：物价、工资、房租、班次与通勤时间"
            "都对齐这一年，不随现实时间推移而变。设定里没有魔法，也没有超技术，"
            "只有一座普通城市该有的预算、人力与排班。</p>"
            '<blockquote class="pullquote">“路网、楼群与人的作息互为约束：改一条线的班次，'
            '会改掉沿线三万户的起床时间。”<cite>城市总纲 · 运行原则</cite></blockquote>'
            "</div>"
            '<div class="rings">%s</div>'
            "</div></div></section>"
        ) % "".join(ring_rows)

        run = (
            '<section class="section" id="run">'
            '<div class="wrap">'
            '<div class="section__head">'
            '<div><div class="eyebrow">02 · 城市怎么运转</div>'
            '<h2 class="h-display">物价、通勤、岗位，三本可以互相验算的账</h2></div>'
            '<p class="section__lead">写故事最怕数字对不上。这里的三本账共用同一套圈层口径，'
            "任何一笔钱、一段路、一个职级，都能被另一本账反推出来。</p>"
            "</div>"
            '<div class="cards3">'
            '<div class="card"><div class="card__kicker">PRICE</div><h3>物价与生活成本</h3>'
            "<p>一百二十个品类、六个消费域，按圈层系数折算；家庭篮子按户均 2.47 人计。</p>"
            '<div class="kv">'
            "<div><span>圈层系数</span><b>1.00·0.92·0.85·0.79</b></div>"
            "<div><span>家庭篮子</span><b>2,790.1 元/月</b></div>"
            "<div><span>户均人口</span><b>2.47 人</b></div>"
            "</div></div>"
            '<div class="card"><div class="card__kicker">TRANSIT</div><h3>通勤与可达</h3>'
            "<p>每个圈层有锚点可达半径上限，超过就得换一次车或干脆搬家。</p>"
            '<div class="kv">'
            "<div><span>可达半径</span><b>3·6·14·14 km</b></div>"
            "<div><span>缆车 CB-01</span><b>10 分钟</b></div>"
            "<div><span>隧道 TN-01</span><b>10 分钟</b></div>"
            "</div></div>"
            '<div class="card"><div class="card__kicker">WORK</div><h3>岗位与就业</h3>'
            "<p>五个岗位层，各有准入年限；公司按三档规模登记在册，岗位卡带薪级带与名额。</p>"
            '<div class="kv">'
            "<div><span>岗位层</span><b>LVL1–LVL5</b></div>"
            "<div><span>晋升准入</span><b>1 / 3 / 8 年</b></div>"
            "<div><span>公司档</span><b>T1–T3</b></div>"
            "</div></div>"
            "</div></div></section>"
        )

        places = (
            '<section class="section" id="places">'
            '<div class="wrap">'
            '<div class="section__head">'
            '<div><div class="eyebrow">03 · 城市里有什么</div>'
            '<h2 class="h-display">六类地点，三百一十二处，逐条写定</h2></div>'
            '<p class="section__lead">编号前缀就是类型：<strong>D</strong> 片区、<strong>F</strong> 功能区、'
            "<strong>L</strong> 地标建筑、<strong>R</strong> 居民区、<strong>S</strong> 聚落（产业小镇与特色村落）。"
            "同一条目里同时写着位置、量级、观感与谁在用。</p>"
            "</div>"
            '<div class="types">%s</div>'
            "</div></section>"
        ) % "".join(type_cards)

        gallery = (
            '<section class="section" id="gallery">'
            '<div class="wrap">'
            '<div class="section__head">'
            '<div><div class="eyebrow">04 · 图集</div>'
            '<h2 class="h-display">同一座城，从不同的高度看</h2></div>'
            '<p class="section__lead">百分之百按设定里的机位、朝向与日照角度生成：'
            "画面里的楼层数、塔群与湖岸线，都要和名录对得上。共 <strong>%s</strong> 张图，其中在册 %s 张。</p>"
            "</div>"
            '<div class="gallery">%s</div>'
            '<div style="margin-top:var(--s6)"><a class="btn btn--ghost" href="atlas.html">看全部图集 →</a></div>'
            "</div></section>"
        ) % (num(self.img_total), num(self.oss["统计"].get("图集", 808)), "".join(shots))

        howto = (
            '<section class="section" id="howto">'
            '<div class="wrap">'
            '<div class="section__head">'
            '<div><div class="eyebrow">05 · 怎么用它</div>'
            '<h2 class="h-display">读世界、写故事、出画面</h2></div>'
            '<p class="section__lead">设定集不是百科，是底稿：给作者一套不会自相矛盾的事实，'
            "给画师一套能落地的机位，给读者一条可以走进去的街。</p>"
            "</div>"
            '<div class="steps">'
            "<div class=\"step\"><div><h3>读：从地点索引进，从分卷出</h3>"
            "<p>先看 <a href=\"locations.html\" style=\"color:var(--green-bright)\">312 个地点</a> 找场景，"
            "再读对应分卷正文。每个地点都有编号、坐标、量级与「谁在这里」。</p></div></div>"
            "<div class=\"step\"><div><h3>写：按六步造一个人</h3>"
            "<p>选工作锚点与居住锚点 → 查 <code>住所锚[ID]</code> 定房租 → 户均 2.47 人折算家庭人口 → "
            "按岗位层准入年限定职级 → 用量可达半径卡住通勤 → 最后才写收入与开销。"
            "示例见仓内 <code>示例/角色卡-周敏.md</code>。</p></div></div>"
            "<div class=\"step\"><div><h3>画：机位、朝向、日照都可复算</h3>"
            "<p>清单里每条都带相机朝向、太阳相对角、机位高度与画幅。"
            "生成图上云，直链写在 <code>数据/图集OSS.json</code>，可直接取用。</p></div></div>"
            "</div></div></section>"
        )

        edges = (
            '<section class="section" id="edges">'
            '<div class="wrap">'
            '<div class="section__head">'
            '<div><div class="eyebrow">06 · 边界</div>'
            '<h2 class="h-display">哪些是定死的，哪些随你写</h2></div>'
            '<p class="section__lead">硬正典只有地名、坐标、量级、口径与已裁定的 %d 条规则；'
            "其余都是软区。改动硬正典会让整座城的数字失去支点。</p>"
            "</div>"
            '<div class="notes">'
            "<div class=\"note\"><h3>可以自由写</h3><p>人物、对白、日常细节、局部剧情、"
            "未被命名的小店与巷子——只要不越过已登记的量级与口径。</p></div>"
            "<div class=\"note\"><h3>不能随手改</h3><p>地点编号与名称、中心坐标、层数与高度、"
            "区域人口与面积、圈层系数、可达半径、岗位层准入年限。</p></div>"
            "<div class=\"note\"><h3>授权</h3><p>正文与数据采用 CC BY-NC-SA 4.0：署名、非商业、"
            "相同方式共享；名称标识保留，二创须标注「非官方」。</p></div>"
            "<div class=\"note\"><h3>图与元数据</h3><p>生成图随附图集 AIGC 声明与 C2PA 元数据，"
            "转载时须一并保留，不得裁掉或遮盖。</p></div>"
            "</div></div></section>"
        ) % len(self.rulings)

        return ridge + run + places + gallery + howto + edges

    # ---------- 地点索引 ----------
    def locations(self):
        rows = []
        ordered = sorted(
            self.items,
            key=lambda it: (TYPE_ORDER.index(it["type"]) if it["type"] in TYPE_ORDER else 99, it["id"]),
        )
        for it in ordered:
            e = self.entries.get(it["id"], {})
            ring = it.get("ring") or "—"
            pop = e.get("population")
            area = e.get("area_km2")
            dist = it.get("distance_to_lake_center_km")
            vol = self.volume_of(it["id"])
            has_img = bool(self.url_of(it["id"]))
            id_cell = (
                '<a href="atlas.html#t-%s" title="在图集中查看 %s">%s</a>' % (esc(it["id"]), esc(it["name"]), esc(it["id"]))
                if has_img
                else esc(it["id"])
            )
            name_cell = (
                '<a href="%s%s" target="_blank" rel="noopener" '
                'title="读分卷正文（GitHub 上的 Markdown 原文）">%s</a>' % (REPO_BLOB, esc(vol), esc(it["name"]))
                if vol
                else esc(it["name"])
            )
            rows.append(
                '<tr data-type="%s" data-search="%s">'
                '<td class="id">%s</td><td class="name">%s</td>'
                '<td>%s</td><td><span class="pill%s">%s</span></td>'
                '<td class="num">%s</td><td class="num">%s</td><td class="num">%s</td></tr>'
                % (
                    esc(it["type"]),
                    esc((it["id"] + " " + it["name"]).lower()),
                    id_cell,
                    name_cell,
                    esc(it["type"]),
                    " pill--ring0" if ring == "内湖环" else "",
                    esc(ring),
                    num(area, 2),
                    num(pop) if pop else "—",
                    num(dist, 2) if dist is not None else "—",
                )
            )
        chips = ['<button class="chip" data-filter="all" aria-pressed="true">全部 %d</button>' % len(self.items)]
        for t in TYPE_ORDER:
            chips.append(
                '<button class="chip" data-filter="%s" aria-pressed="false">%s %d</button>'
                % (esc(t), esc(t), self.type_counts.get(t, 0))
            )
        body = (
            '<section class="pagehead"><div class="wrap">'
            '<div class="eyebrow">INDEX · 312 LOCATIONS</div>'
            "<h1>地点索引</h1>"
            "<p>每一行都来自 <code style=\"font-family:var(--font-mono);font-size:13px\">"
            "数据/城市空间名录.json</code> 的登记条目：面积、人口、圈层与到湖心的距离均按正典口径。"
            "点编号看该地点的图，点名称读分卷正文。</p>"
            "</div></section>"
            '<section><div class="wrap">'
            '<div class="filters" id="filters" role="group" aria-label="按类型筛选与搜索">'
            '<label class="filters__search">'
            '<input id="q" type="search" placeholder="搜编号或名称，如 D08 / 西湖" '
            'aria-label="搜索地点" autocomplete="off" />'
            "</label>%s"
            '<span class="filters__count" id="count" aria-live="polite">%d 处</span>'
            "</div>"
            '<div class="tablewrap"><table class="loc"><thead><tr>'
            "<th>编号</th><th>名称</th><th>类型</th><th>圈层</th>"
            '<th class="num">面积 km²</th><th class="num">人口</th><th class="num">距湖心 km</th>'
            "</tr></thead><tbody id=\"rows\">%s</tbody></table></div>"
            '<p style="margin:var(--s4) 0 var(--s8);font-size:var(--text-xs);color:var(--text-faint)">'
            "人口栏仅对登记了人口的片区／居民区／聚落有值；「—」表示该条目按其他量级登记（如建筑面积、层数）。</p>"
            "</div></section>"
            "<script>%s</script>"
            % ("".join(chips), len(self.items), "".join(rows), FILTER_JS)
        )
        return self.shell(
            "地点索引 · 钛湖城",
            "钛湖城 312 个地点的索引表：编号、类型、圈层、面积、人口与到湖心的距离。",
            body,
            current="locations.html",
        )

    # ---------- 图集 ----------
    def atlas(self):
        groups = []
        nav = []
        for t in TYPE_ORDER:
            members = [it for it in self.items if it["type"] == t and self.url_of(it["id"])]
            if not members:
                continue
            anchor = "g-%s" % (TYPE_ORDER.index(t))
            nav.append('<a class="chip" href="#%s">%s %d</a>' % (anchor, esc(t), len(members)))
            tiles = []
            for it in members:
                urls = self.versions_of(it["id"])
                url = urls[0]
                vers = ' data-versions="%s"' % esc("|".join(urls)) if len(urls) > 1 else ""
                tiles.append(
                    '<button type="button" class="tile" id="t-%s" data-full="%s" data-cap="%s" data-id="%s"%s>'
                    '<img src="%s" alt="%s" loading="lazy" />'
                    '<span class="tile__cap"><b class="tile__name">%s</b><span>%s</span></span></button>'
                    % (esc(it["id"]), esc(url), esc(it["name"]), esc(it["id"]), vers,
                       esc(url), esc(it["name"]), esc(it["name"]), esc(it["id"]))
                )
            groups.append(
                '<section class="group" id="%s"><div class="wrap">'
                "<h2>%s <span>%d 处 · 前缀 %s</span></h2>"
                '<div class="grid4">%s</div></div></section>'
                % (anchor, esc(t), len(members), TYPE_META[t][0], "".join(tiles))
            )
        stats = self.oss["统计"]
        body = (
            '<section class="pagehead"><div class="wrap">'
            '<div class="eyebrow">ATLAS · 312 PLACES</div>'
            "<h1>图集</h1>"
            "<p>在册成品 %s 张，全部按设定里的机位与日照角度生成，托管在 OSS 并带 C2PA 元数据。"
            "点开大图可放大、按 ← → 翻页；同一地点若有多轮成果，弹层底部会列出历代版本，点一下就切过去。</p>"
            "</div></section>"
            '<nav class="atlasnav"><div class="wrap" style="display:flex;gap:8px;flex-wrap:wrap">%s</div></nav>'
            "%s"
            '<section class="group"><div class="wrap">'
            "<h2>关于这些图 <span>口径</span></h2>"
            '<div class="notes">'
            '<div class="note"><h3>为什么楼层数要对</h3><p>图不是插画，是按名录里的层数、高度与'
            "建筑面积生成的：一栋登记 17 层的楼不能画成 6 层，否则房价、天际线与通勤都会失支点。</p></div>"
            '<div class="note"><h3>图在哪儿</h3><p>全部直链见 <code>数据/图集OSS.json</code>；'
            "人读版在 <code>数据/图集直链.md</code>。母图池、历史归档与过程图一并在册，"
            "共 %s 件、%s GB。</p></div>"
            "</div></div></section>"
            + LIGHTBOX_HTML
        ) % (
            num(stats.get("图集", 808)),
            "".join(nav),
            "".join(groups),
            num(stats["件数"]),
            "%.2f" % (stats["合计字节"] / 1024 ** 3),
        )
        return self.shell(
            "图集 · 钛湖城",
            "钛湖城 312 个地点的在册配图，按类型陈列，直链托管在 OSS。",
            body,
            current="atlas.html",
            script="lightbox.js",
        )

    # ---------- 地图 ----------
    def map(self):
        # 把仓内三张 SVG 复制进站点目录：站点根就是 网站/，引用 .. 之外的路径在静态托管上会 404
        maps_dir = SITE / "地图"
        maps_dir.mkdir(exist_ok=True)
        figs = []
        for name, title, note in MAPS:
            src = ROOT / name
            if src.is_file():
                shutil.copyfile(src, maps_dir / name)
            figs.append(
                '<section class="group" id="map-%s"><div class="wrap">'
                "<h2>%s</h2>"
                '<figure class="mapfig"><img src="地图/%s" alt="%s" loading="lazy" />'
                "<figcaption>%s</figcaption></figure>"
                "</div></section>" % (esc(name.split(".")[0]), esc(title), esc(name), esc(title), esc(note))
            )
        body = (
            '<section class="pagehead"><div class="wrap">'
            '<div class="eyebrow">MAPS · THC-LOCAL-2013</div>'
            "<h1>地图</h1>"
            "<p>三张按正典坐标画的图：湖心为原点 (0,0)，单位千米，x 向东、y 向北，方位角自北顺时针。"
            "都是 SVG 矢量图，放大器不会糊，窗口多宽就铺多宽。</p>"
            "</div></section>"
            + "".join(figs)
            + '<section class="group"><div class="wrap">'
            "<h2>怎么用这三张图 <span>口径</span></h2>"
            '<div class="notes">'
            '<div class="note"><h3>先看全域</h3><p>搞清湖、环山与 24 个外围聚落的关系，'
            "再决定故事发生在城里还是山外台地。</p></div>"
            '<div class="note"><h3>再定位片区</h3><p>主城区图按 D／F／L 编号标位：'
            "一个片区、一条街、一栋楼都能指到图上。</p></div>"
            '<div class="note"><h3>产业看第三张</h3><p>产业小镇与功能区叠在一张图上，'
            "货运通道与班车动线就在那一层。</p></div>"
            '<div class="note"><h3>坐标能算</h3><p>任意两点距离与朝向都能用中心坐标直接算，'
            "不必目测；正典口径见 CANON.md。</p></div>"
            "</div></div></section>"
        )
        return self.shell(
            "地图 · 钛湖城",
            "钛湖城的三张空间图：全域卫星聚落、主城区索引、产业空间图层，均为 SVG。",
            body,
            current="map.html",
        )

    # ---------- 落盘 ----------
    def build(self):
        pages = {
            "index.html": self.index(),
            "locations.html": self.locations(),
            "map.html": self.map(),
            "atlas.html": self.atlas(),
        }
        return pages


FILTER_JS = """
(function () {
  var chips = document.querySelectorAll('#filters .chip');
  var rows = document.querySelectorAll('#rows tr');
  var input = document.getElementById('q');
  var count = document.getElementById('count');
  var total = rows.length;
  var state = { type: 'all', q: '' };
  function apply() {
    var q = state.q.trim().toLowerCase();
    var shown = 0;
    rows.forEach(function (tr) {
      var byType = state.type === 'all' || tr.getAttribute('data-type') === state.type;
      var byText = !q || (tr.getAttribute('data-search') || '').indexOf(q) !== -1;
      var hit = byType && byText;
      tr.style.display = hit ? '' : 'none';
      if (hit) shown++;
    });
    chips.forEach(function (c) {
      c.setAttribute('aria-pressed', String(c.getAttribute('data-filter') === state.type));
    });
    if (count) {
      count.textContent = shown === total ? total + ' 处' : shown + ' / ' + total + ' 处';
    }
  }
  chips.forEach(function (c) {
    c.addEventListener('click', function () {
      state.type = c.getAttribute('data-filter');
      apply();
    });
  });
  if (input) {
    input.addEventListener('input', function () {
      state.q = input.value;
      apply();
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { input.value = ''; state.q = ''; apply(); }
    });
  }
  if (location.hash) {
    var t = decodeURIComponent(location.hash.slice(1));
    var known = false;
    chips.forEach(function (c) { if (c.getAttribute('data-filter') === t) known = true; });
    if (t && known) { state.type = t; }
  }
  apply();
})();
"""


LIGHTBOX_HTML = """
<div class="lb" id="lb" role="dialog" aria-modal="true" aria-label="图集大图查看" hidden>
  <div class="lb__bar">
    <div class="lb__meta"><b class="lb__name"></b><span class="lb__id"></span></div>
    <div class="lb__tools">
      <span class="lb__count" aria-live="polite"></span>
      <a class="lb__orig" href="#" target="_blank" rel="noopener">原图 ↗</a>
      <button type="button" class="lb__btn" data-lb="close" aria-label="关闭（Esc）">✕</button>
    </div>
  </div>
  <button type="button" class="lb__nav lb__nav--prev" data-lb="prev" aria-label="上一张（←）">‹</button>
  <figure class="lb__fig">
    <img class="lb__img" alt="" />
    <figcaption class="lb__hint">← → 翻页 · Esc 关闭 · 滚轮缩放 · 双击复位或放大</figcaption>
    <div class="lb__versions" id="lb-vers" hidden>
      <span class="lb__vlabel">同地点历代版本</span>
      <div class="lb__vlist"></div>
    </div>
  </figure>
  <button type="button" class="lb__nav lb__nav--next" data-lb="next" aria-label="下一张（→）">›</button>
</div>
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成钛湖城设定集介绍网站")
    ap.add_argument("--check", action="store_true", help="只核对盘上页面与现渲染是否一致")
    args = ap.parse_args(argv)

    site = Site()
    pages = site.build()
    stale = []
    for name, text in pages.items():
        path = SITE / name
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old != text:
            stale.append(name)
            if not args.check:
                path.write_text(text, encoding="utf-8", newline="\n")
                print("写入 %s（%.1f KB）" % (path.relative_to(ROOT), len(text.encode("utf-8")) / 1024))
    if args.check:
        if stale:
            print("页面与现渲染不一致：%s" % "、".join(stale))
            return 1
        print("页面与现渲染一致：%d 个页面" % len(pages))
        return 0
    if not stale:
        print("无变化：%d 个页面已是最新" % len(pages))
    return 0


if __name__ == "__main__":
    sys.exit(main())
