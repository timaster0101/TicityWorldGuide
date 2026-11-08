# -*- coding: utf-8 -*-
"""卡面合成器（C142／C143）：768×1024 双版卡面，按系列分四套模板。

版式真源＝基准卡 backup/数据/视觉控制资产/卡牌/东湖金融线-L009-…-实际卡.png 的本体相对分数。
实测原 124 张并非同一模板（本体包围盒、窗带上下沿、金线形态逐张不同，部分满幅无白边），
故本脚本按 C143 把版式归一：一套几何 + 四套装帧（地标／板块／信息／背面）。
实景窗顶边固定在窗带上沿、高度＝窗宽÷源宽高比，等比不裁切、窗内不留白；
源比放不下（2:3 竖幅）时报 NEEDS_CUSTOM_SOURCE，由 --sources 指定的卡面专用图补位。
"""
import argparse
import collections
import json
import math
import os
import re
import sys
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANVAS_W, CANVAS_H = 768, 1024
SS = 2  # 超采样：圆角与字缘靠 2x 画布降采样抗锯齿，交付判据仍是 768×1024

PAPER_TOP = (0xF4, 0xEC, 0xE2)
PAPER_BOTTOM = (0xF1, 0xE8, 0xDC)
TITLE_INK = (0x27, 0x22, 0x1B)
SUBTITLE_INK = (0x6D, 0x65, 0x5A)
BOTTOM_INK = (0x4D, 0x45, 0x3B)
GOLD = (0xB8, 0x96, 0x5E)
GOLD_HI = (0xF4, 0xE6, 0xCC)
GOLD_LO = (0xDD, 0xCC, 0xB2)
RULE_INK = (0x3A, 0x34, 0x2C)
PLACEHOLDER_FILL = (0xE9, 0xE1, 0xD3)
PLACEHOLDER_INK = (0xA8, 0x9C, 0x88)

MARGIN = {"left": 0.0931, "right": 0.0765, "top": 0.0625, "bottom": 0.0529}
BODY_RADIUS = 0.0826
WIN_X = (0.0153, 0.9646)
WIN_TOP = 0.3200
WIN_BOTTOM = 0.7930
BANDS = {
    "title": (0.098, 0.140),
    "subtitle": (0.186, 0.219),
    "gold_rule": (0.2203, 0.2303),
    "gold_dash": (0.150, 0.162),
    "bottom": (0.872, 0.899),
}
WIDTH_LIMIT = 0.88
FONT_DIR = "C:/Users/TIMASTER/AppData/Local/Microsoft/Windows/Fonts"
FONTS = {"title": "AlibabaPuHuiTi-3-75-SemiBold.ttf",
         "subtitle": "AlibabaPuHuiTi-3-55-Regular.ttf",
         "bottom": "AlibabaPuHuiTi-3-55-Regular.ttf",
         "latin": "AlibabaPuHuiTi-3-65-Medium.ttf"}
BASE_SIZE = {"title": 46, "subtitle": 34, "bottom": 30}

# 系列 → 装帧。板块卡标题拆两行（上行金色系列名、下行深色片区名），信息卡用金色短划线，地标卡通栏金线。
TEMPLATE_BY_TYPE = {"景群地标卡": "landmark", "板块卡": "district", "模板背面": "back"}
INFO_TYPES = {"职业卡", "物品卡", "能力卡", "兑换卡", "成就卡", "模板正面"}


def template_of(card_type):
    if card_type in TEMPLATE_BY_TYPE:
        return TEMPLATE_BY_TYPE[card_type]
    if card_type in INFO_TYPES:
        return "info"
    return "landmark"


def body_rect(scale=None):
    cw, ch = (CANVAS_W * SS, CANVAS_H * SS) if scale is None else scale
    x0 = round(cw * MARGIN["left"])
    x1 = cw - round(cw * MARGIN["right"])
    y0 = round(ch * MARGIN["top"])
    y1 = ch - round(ch * MARGIN["bottom"])
    return x0, y0, x1 - x0, y1 - y0


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def make_canvas():
    cw, ch = CANVAS_W * SS, CANVAS_H * SS
    img = Image.new("RGB", (cw, ch), (255, 255, 255))
    x, y, w, h = body_rect()
    paper = Image.new("RGB", (w, h))
    for row in range(h):
        paper.paste(Image.new("RGB", (w, 1), lerp(PAPER_TOP, PAPER_BOTTOM, row / max(h - 1, 1))), (0, row))
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=round(w * BODY_RADIUS), fill=255)
    img.paste(paper, (x, y), mask.crop((x, y, x + w, y + h)))
    return img


def font_for(role, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, FONTS[role]), size * SS)


def fit_size(role, text, limit_px):
    size = BASE_SIZE[role]
    while size > 12:
        bb = font_for(role, size).getbbox(text)
        if bb[2] - bb[0] <= limit_px:
            return size
        size -= 1
    return size


def draw_line(canvas, band, text, ink, role, anchor_bottom_ratio):
    """把一行字按「墨下沿贴在 anchor 比例」居中画在卡内。"""
    x, y, w, h = band
    if not text:
        return
    d = ImageDraw.Draw(canvas)
    size = fit_size(role, text, w * WIDTH_LIMIT)
    f = font_for(role, size)
    bb = f.getbbox(text)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    bottom = y + round(h * anchor_bottom_ratio)
    d.text((x + (w - tw) // 2 - bb[0], bottom - th - bb[1]), text, font=f, fill=ink)


def draw_gold_rule(canvas, band):
    """地标卡的飞白式装饰线：左细浅金、右粗墨色，两端收尖。"""
    x, y, w, h = band
    lo, hi = BANDS["gold_rule"]
    yc = y + round(h * (lo + hi) / 2)
    x0, x1 = x + round(w * 0.06), x + w - round(w * 0.06)
    d = ImageDraw.Draw(canvas)
    amp, maxth = round(h * 0.007), max(2 * SS, round(h * 0.0033))
    for px in range(x0, x1):
        t = (px - x0) / max(x1 - x0 - 1, 1)
        py = yc + round(amp * (1 - 2 * t) - amp * 0.5 * math.sin(math.pi * t))
        th = max(1, round(maxth * (0.30 + 0.70 * t ** 2) * math.sin(math.pi * t) ** 0.30))
        d.line([(px, py - th // 2), (px, py - th // 2 + th - 1)],
               fill=lerp(GOLD_HI, RULE_INK, t ** 1.6))


def draw_gold_dash(canvas, band):
    x, y, w, h = band
    lo, hi = BANDS["gold_dash"]
    y0, y1 = y + round(h * lo), y + round(h * hi)
    d = ImageDraw.Draw(canvas)
    half = round(w * 0.13)
    cx = x + w // 2
    d.line([(cx - half, (y0 + y1) // 2), (cx + half, (y0 + y1) // 2)], fill=GOLD, width=max(2, round(w * 0.006)))


def draw_flanking_dashes(canvas, band):
    """职业卡标题两侧的短金划。"""
    x, y, w, h = band
    lo, hi = BANDS["title"]
    cy = y + round(h * (lo + hi) / 2)
    d = ImageDraw.Draw(canvas)
    th = max(2 * SS, round(w * 0.0035))
    for x0, x1 in ((0.035, 0.115), (0.885, 0.965)):
        d.line([(x + round(w * x0), cy), (x + round(w * x1), cy)], fill=GOLD, width=th)


def full_bleed_fit(size, tol=0.002):
    """路线 B（C147）满幅主图的装得下判据：主图即整卡，object-fit:cover 不裁切当且仅当
    源画幅等于画布画幅 768:1024。旧的 window_box 窗带判据属烤 PNG 时代，不参与状态分类；
    OVERFLOW 在本路线下的含义＝该源进满幅窗必被裁切，须按 3:4 原生重投。"""
    return abs(size[0] / size[1] - CANVAS_W / CANVAS_H) <= tol


def window_box(band, src_size):
    x, y, w, h = band
    wx0, wx1 = WIN_X
    bx = x + round(w * wx0)
    bw = round(w * (wx1 - wx0))
    top = y + round(h * WIN_TOP)
    limit = y + round(h * WIN_BOTTOM) - top
    if src_size:
        sw, sh = src_size
        bh = round(bw * sh / sw)
        if bh > limit:
            return None
    else:
        bh = limit
    return bx, top, bw, bh


def paste_source(canvas, box, source):
    bx, by, bw, bh = box
    with Image.open(source) as im:
        im = im.convert("RGB")
        sw, sh = im.size
    scale = min(bw / sw, bh / sh)
    im = im.resize((max(round(sw * scale), 1), max(round(sh * scale), 1)), Image.LANCZOS)
    canvas.paste(im, (bx + (bw - im.size[0]) // 2, by + (bh - im.size[1]) // 2))
    return im.size


def draw_placeholder(canvas, box, label):
    bx, by, bw, bh = box
    d = ImageDraw.Draw(canvas)
    d.rectangle([bx, by, bx + bw - 1, by + bh - 1], fill=PLACEHOLDER_FILL)
    f = font_for("subtitle", 24)
    bb = f.getbbox(label)
    d.text((bx + (bw - bb[2] + bb[0]) // 2 - bb[0], by + (bh - bb[3] + bb[1]) // 2 - bb[1]),
           label, font=f, fill=PLACEHOLDER_INK)


def draw_back(canvas, band):
    x, y, w, h = band
    d = ImageDraw.Draw(canvas)
    cx, cy = x + w // 2, y + round(h * 0.46)
    r = round(w * 0.15)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=GOLD, width=round(w * 0.006))
    d.ellipse([cx - round(r * 0.55), cy - round(r * 0.55), cx + round(r * 0.55), cy + round(r * 0.55)],
              outline=GOLD, width=round(w * 0.004))
    f = ImageFont.truetype(os.path.join(FONT_DIR, FONTS["latin"]), round(w * 0.05))
    tw = d.textlength("TITAN LAKE", font=f)
    d.text((cx - tw / 2, cy + r + round(h * 0.03)), "TITAN LAKE", font=f, fill=SUBTITLE_INK)


# 副标题里的「行业／类别／维度／门槛」是卡面真实上屏内容，去编号只去掉尾部的 Axx／Lxx／Dxx 档号。
EXCHANGE_THRESHOLD = {"T1": "50", "T2": "150", "T3": "400", "T4": "1000", "T5": "2500"}
TEMPLATE_FRONT_TEXT = {
    "兑换卡": ("兑换", "积攒卡牌积分兑换现实权益"),
    "成就卡": ("成就", "记录打卡与事件套系的荣誉卡"),
    "物品卡": ("物品", "承载资产与账本的实物卡"),
    "职业卡": ("职业", "推进行业胜任能力进阶的卡"),
    "能力卡": ("能力", "提升五维数值的成长卡"),
}
SUMMARY_LANDMARK = {
    "全城地标巡礼-实际卡.png": ("全城地标巡礼", "全域套系"),
    "生态科普线-实际卡.png": ("生态科普线", "景群套系"),
    "钛湖之脊-八景打卡-实际卡.png": ("钛湖之脊巡礼", "景群套系"),
}


def industry_names():
    with open(os.path.join(ROOT, "数据", "产业就业正典.json"), encoding="utf-8") as fh:
        canon = json.load(fh)
    return {g["id"]: g["名称"] for g in canon["行业"]["大类"]}


def derive_texts(it, industry):
    """返回 (装帧, 标题, 副标题)：按系列规则重建，副标题保留卡面真实描述段。"""
    ctype, name, fname = it["card_type"], it.get("name") or "", it["file"]
    template = template_of(ctype)
    if template == "back":
        return template, "", ""
    if ctype == "景群地标卡":
        if fname in SUMMARY_LANDMARK:
            return template, *SUMMARY_LANDMARK[fname]
        return template, (it.get("title_expected") or "").strip(), "景群套系"
    if ctype == "板块卡":
        return template, (it.get("title_expected") or "").strip(), "板块套系"
    parts = [p for p in name.split("-") if p]
    if ctype == "职业卡":
        code = re.search(r"A\d{2,3}$", parts[-1]).group(0) if parts and re.search(r"A\d{2,3}$", parts[-1]) else ""
        title = "-".join(parts[:-1]) if code else name
        industry_name = industry.get(code, "")
        return template, title, ("职业卡·" + industry_name if industry_name else "职业卡")
    if ctype == "物品卡":
        return template, parts[0], "物品卡·" + parts[1] if len(parts) > 1 else "物品卡"
    if ctype == "能力卡":
        return template, parts[0], "能力卡·" + parts[1] if len(parts) > 2 else "能力卡"
    if ctype == "兑换卡":
        tier = re.match(r"(T\d)", parts[0]) if parts else None
        key = tier.group(1) if tier else ""
        title = parts[0] if parts else name
        sub = "兑换卡·门槛" + EXCHANGE_THRESHOLD[key] + "积分" if key in EXCHANGE_THRESHOLD else "兑换卡"
        return template, title, sub
    if ctype == "模板正面":
        fam = fname.split("-")[0]
        title, sub = TEMPLATE_FRONT_TEXT.get(fam, (fam, ""))
        return template, title, sub
    return template, (it.get("title_expected") or "").strip(), (it.get("subtitle_new") or "").strip()


def load_texts():
    with open(os.path.join(ROOT, "数据", "卡面文案底稿.json"), encoding="utf-8") as fh:
        items = json.load(fh)["items"]
    industry = industry_names()
    for it in items:
        it["template"], it["render_title"], it["render_subtitle"] = derive_texts(it, industry)
        it["render_bottom"] = (it.get("bottom_text") or "").strip()
    return items


def build_source_index():
    with open(os.path.join(ROOT, "数据", "开图清单.json"), encoding="utf-8") as fh:
        entries = json.load(fh)["items"]
    out = {}
    for e in entries:
        pool = [p for p in (e.get("image_file") or [])
                if str(p).startswith("数据/图集/") and "/四向/" not in str(p)]
        if not pool:
            continue
        tail = str(e.get("batch", "")).split(e["id"], 1)
        tail = tail[1] if len(tail) > 1 else ""
        picked = [p for p in pool if tail and tail in os.path.basename(p)]
        out[e["id"]] = picked[0] if picked else pool[0]
    return out


def render(item, source, variant):
    img = make_canvas()
    band = body_rect()
    tpl = item["template"]
    size = None
    if source:
        with Image.open(source) as im:
            size = im.size
    box = window_box(band, size) if tpl != "back" else None
    if tpl == "back":
        draw_back(img, band)
    elif box is None:
        draw_placeholder(img, window_box(band, None), "需卡面专用图")
    elif source:
        draw_gold(img, band, item)
        paste_source(img, box, source)
    else:
        draw_gold(img, band, item)
        draw_placeholder(img, box, "实景待投")
    if tpl != "back":
        draw_text(img, band, item, tpl, variant)
    return img.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)


def draw_gold(canvas, band, item):
    tpl = item["template"]
    if tpl == "landmark":
        draw_gold_rule(canvas, band)
    elif tpl == "info":
        draw_gold_dash(canvas, band)
        if item["card_type"] == "职业卡":
            draw_flanking_dashes(canvas, band)


def draw_text(canvas, band, item, tpl, variant):
    if tpl == "district":
        name = item["render_title"]
        prefix, _, rest = name.partition("·")
        if rest:
            draw_line(canvas, band, prefix + "·", GOLD, "title", BANDS["title"][1] - 0.028)
            draw_line(canvas, band, rest, TITLE_INK, "title", BANDS["title"][1] + 0.028)
        else:
            draw_line(canvas, band, name, TITLE_INK, "title", BANDS["title"][1])
    else:
        draw_line(canvas, band, item["render_title"], TITLE_INK, "title", BANDS["title"][1])
    draw_line(canvas, band, item["render_subtitle"], SUBTITLE_INK, "subtitle", BANDS["subtitle"][1])
    if variant == "有文案":
        draw_line(canvas, band, item["render_bottom"], BOTTOM_INK, "bottom", BANDS["bottom"][1])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join("数据", "视觉控制资产", "卡牌", "768x1024"))
    ap.add_argument("--only", default="", help="逗号分隔的 _idx／code／文件名子串")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--variant", default="both", choices=["both", "plain", "full"])
    ap.add_argument("--sources", default="", help="JSON：{code 或 文件名(不含扩展名) 或 _idx: 卡面专用图路径}，优先于图集定档格；"
                                                  "code 为空的卡（职业/兑换/模板/物品/能力/景群总卡）只能用文件名或 _idx 键")
    ap.add_argument("--dry", action="store_true", help="只报分档与取数，不写图")
    ap.add_argument("--manifest-only", action="store_true",
                    help="只生成/刷新 manifest.json（数据真源），不烤卡面 PNG——"
                         "2026-11-08 交付转 HTML（C147）后，本脚本退为 manifest 生成器")
    args = ap.parse_args(argv)
    if os.path.abspath(os.getcwd()) != os.path.abspath(ROOT):
        os.chdir(ROOT)

    items = load_texts()
    sources = build_source_index()
    if args.sources:
        with open(args.sources, encoding="utf-8") as fh:
            for k, v in json.load(fh).items():
                sources[k] = v
    keys = [k.strip() for k in args.only.split(",") if k.strip()]
    if keys:
        items = [x for x in items if str(x["_idx"]) in keys or x.get("code") in keys
                 or any(k in str(x["file"]) for k in keys)]
    if args.limit:
        items = items[:args.limit]
    variants = ["无文案", "有文案"] if args.variant == "both" else (
        ["无文案"] if args.variant == "plain" else ["有文案"])

    rows, miss, overflow = [], [], []
    for it in items:
        code = it.get("code") or ""
        stem = os.path.splitext(it["file"])[0]
        src = sources.get(code) or sources.get(stem) or sources.get(str(it["_idx"]))
        if src and not os.path.exists(src):
            src = None
        size = None
        if src:
            with Image.open(src) as im:
                size = im.size
            if not full_bleed_fit(size) and it["template"] != "back":
                overflow.append({"code": code, "file": it["file"], "src_size": list(size),
                                 "src_aspect": round(size[0] / size[1], 4)})
                src = None
        status = "OK" if src else ("BACK" if it["template"] == "back" else
                                   ("OVERFLOW" if size else "MISSING"))
        rec = {"idx": it["_idx"], "code": code, "card_type": it["card_type"],
               "template": it["template"], "file": it["file"], "source": src,
               "src_size": list(size) if size else None, "status": status,
               "title": it["render_title"], "subtitle": it["render_subtitle"],
               "bottom": it["render_bottom"]}
        if status == "MISSING":
            miss.append(rec)
        if not args.dry and not args.manifest_only:
            canvas_img = make_canvas()
            for v in variants:
                out_dir = os.path.join(args.out, v)
                os.makedirs(out_dir, exist_ok=True)
                p = os.path.join(out_dir, os.path.splitext(it["file"])[0] + ".png")
                render(it, src, v).save(p)
                rec.setdefault("outputs", {})[v] = p
        rows.append(rec)

    stat = collections.Counter(r["status"] for r in rows)
    print(json.dumps({
        "出图条数": len(rows), "版本": variants, "状态": dict(stat),
        "MISSING按卡型": dict(collections.Counter(m["card_type"] for m in miss)),
        "放不下源": overflow,
        "装帧分布": dict(collections.Counter(r["template"] for r in rows)),
        "源尺寸分档": dict(collections.Counter(
            "%dx%d" % tuple(r["src_size"]) for r in rows if r["src_size"])),
        "本体矩形_输出像素": body_rect((CANVAS_W, CANVAS_H)), "超采样": SS,
    }, ensure_ascii=False, indent=1))
    if not args.dry:
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as fh:
            json.dump({"canvas": [CANVAS_W, CANVAS_H], "variants": variants,
                       "generated_by": os.path.basename(__file__), "cards": rows},
                      fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
