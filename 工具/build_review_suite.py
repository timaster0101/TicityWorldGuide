# -*- coding: utf-8 -*-
"""B5 人工复看套件：把 264 条既有图排成可直接翻看的联络表与工作单，供人工逐条打表。

产物是工作 aids，不是结论：本脚本不写 status、不绑 image_prompt_sha256、不判通过。
人工结论的唯一可编辑源是 数据/开图验收备注.json，本套件只回显它，重跑覆盖工作单不丢结论。
"""
import csv
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "数据"
OUT = DATA / "人工复看套件"
SHEETS = OUT / "联络表"
PAGE_ITEMS = 8
MANIFEST = json.loads((DATA / "开图清单.json").read_text(encoding="utf-8"))
NOTES = json.loads((DATA / "开图验收备注.json").read_text(encoding="utf-8"))["备注"]

# 十条判据与出处。每条都是「看图能判」的客观项，脚本只列不改判。
CHECKS = (
    ("画风", "半写实数字绘画、平滑过渡在位（C122 起不以笔触为准）；出成照片质感或干净CG渲染或描边平涂动画档即判废重出"),
    ("双层接触", "科技层与老城层同图且有可见接触边（C93／D4）；只有一层或被广场绿地切断即记待复验"),
    ("生活痕迹", "画面痕迹实体≥3 项（晾晒、盆栽、修车、下棋、遛狗、外卖箱等）；不足三项即记待复验"),
    ("招牌与文字", "招牌、店招、灯箱或门牌必须存在且为不可读笔画；出现可辨字形、凭空文字或类签名笔画即判废"),
    ("年代锁", "不得出现飞行汽车、全息投影、人形机器人等近未来符号；出现即判废"),
    ("日面可纳性", "按 C99：太阳相对方位与本条焦距的半视锥比对；须画外却画出日面圆盘／落日辉光／镜头眩光即判废"),
    ("远景可纳性", "按 C101／C123：背景天际线只许本条取景段逐一点名的独立远景；正文里写作「远景」的主体自身构件不算背景授权；凭空天际线、超高层冠部或塔吊即判废"),
    ("远景塔形来源", "按 C106：背景塔按本正典自己的几何画；描摹现实天际线（陆家嘴／香港／深圳湾／曼哈顿／迪拜／芝加哥）或借用现实超高层的冠部、扭转、开洞即判废"),
    ("形体与硬参数", "高度与冠部形态同名录真值一致即过关；把 L007 的斜削冠＋针状天线安到别的塔上即判废；画面可读层数与锁定层数不符只记备注、不单独判废（C124：层数只活在中文段，tail 无计数词）"),
    ("人数落档", "可见人物落在本条人群段的缺省档内（详档优先，不为凑人数增删人物）"),
)

BLANK = "＿＿"
HEADER_KEYS = ("建议尺寸", "拍摄朝向", "光照判定", "状态", "prompt_sha256", "image_prompt_sha256", "复验原因/备注")


def parse_prompt(rel):
    """从提示词文件取「实际投喂过什么」：尺寸、光判、人数档与锁定段一律以产物为准，不另抄常量。"""
    text = (ROOT / rel).read_text(encoding="utf-8")
    head = {}
    for line in text.split("## 提示词正文", 1)[0].splitlines():
        m = re.match(r"- (建议尺寸|拍摄朝向|光照判定|状态|prompt_sha256|image_prompt_sha256|复验原因/备注)：(.*)", line)
        if m:
            head[m.group(1)] = m.group(2).strip()
    body = text.split("## 提示词正文", 1)[1]
    def section(mark):
        for line in body.splitlines():
            if line.startswith(mark):
                return line[len(mark):].strip()
        return ""
    人群 = section("【人群与烟火气】")
    锁定 = section("【锁定与禁则】")
    band = 人群.split("｜")[-1] if "｜" in 人群 else ""
    m = re.search(r"(\d+(?:\.\d+)?)°（北0°顺时针）｜太阳相对方位：(-?\d+(?:\.\d+)?)°", head.get("拍摄朝向", ""))
    sun = (float(m.group(2)), m.group(1)) if m else (None, None)
    focal = re.search(r"(\d+(?:\.\d+)?)\s*毫米", section("【取景指令】"))
    return dict(head=head, 人群=人群, 锁定=锁定, band=band,
                size=head.get("建议尺寸", ""), sun_deg=sun[0], facing=sun[1],
                focal_mm=float(focal.group(1)) if focal else None)


def sun_expect(info):
    """闸门侧独立复算一遍 C99：可纳＝|rel| ≤ atan(18/焦距)。套件要把期望写在页面上，
    否则复核者只能凭感觉判「太阳该不该在画面里」。"""
    import math
    if info["sun_deg"] is None or not info["focal_mm"]:
        return "本条为时段变体或焦距不可解析，不套默认光算式"
    half = math.degrees(math.atan(18.0 / info["focal_mm"]))
    side = "右" if info["sun_deg"] > 0 else "左"
    if abs(info["sun_deg"]) <= half:
        return "可入画（rel %+.0f°／半视锥 %.1f°，日面应在画面%s侧带内）" % (info["sun_deg"], half, side)
    return "须画外（rel %+.0f° 超出半视锥 %.1f°，不得画日面圆盘、落日辉光与镜头眩光）" % (info["sun_deg"], half)


def img_src(rel):
    """联络表在 数据/人工复看套件/联络表/ 下，回到仓库根要三级 ../，再按 URL 编码拼本地路径。"""
    return "../../../" + quote(rel)


def blocks(items):
    out = []
    for it in items:
        info = it["info"]
        lines = ["### %s %s｜%s" % (it["id"], it["name"], it["type"])]
        lines.append("")
        lines.append("- 画幅：%s｜机位朝向 %s°｜本条焦距实算：%s"
                     % (info["size"] or "未见", info["facing"] or "未见", sun_expect(info)))
        lines.append("- 人数档：%s" % (info["band"] or "未见"))
        lines.append("- 本条锁定与禁则：%s" % (info["锁定"] or "未见"))
        lines.append("- 当前摘要：%s｜绑定：%s｜状态：%s"
                     % (info["head"].get("prompt_sha256", "")[:12],
                        (info["head"].get("image_prompt_sha256") or "未绑定")[:12], it["status"]))
        for p in it["image_file"]:
            lines.append("- 图格：%s" % p)
        if NOTES.get(it["id"]):
            lines.append("- 已记人工结论（回显自 数据/开图验收备注.json，本套件不承接新结论）：")
            for row in NOTES[it["id"]]:
                lines.append("  - %s" % row)
        lines.append("- 打表（结论请写进 数据/开图验收备注.json，勿在本单落笔——本单每次重跑会被覆盖）：")
        for label, rule in CHECKS:
            lines.append("  - %s：%s｜%s" % (label, BLANK, rule))
        lines.append("  - 结论：%s（通过／判废重出／待重出）｜备注：%s" % (BLANK, BLANK))
        lines.append("")
        out.extend(lines)
    return out


def sheet_html(page_no, items):
    parts = ["<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\">",
             "<title>B5 复看联络表 第%d页</title>" % page_no,
             "<style>body{font-family:sans-serif;background:#111;color:#eee;margin:16px}",
             ".item{border-top:2px solid #444;padding-top:8px;margin-bottom:20px}",
             ".grid{display:flex;flex-wrap:wrap;gap:10px}",
             ".cell{width:340px}.cell img{width:100%;display:block}",
             ".cap{font-size:12px;color:#bbb;word-break:break-all}",
             "h3{margin:4px 0}ul{margin:4px 0;font-size:13px}</style></head><body>",
             "<p><a href=\"index.html\">返回目录</a>｜第 %d 页｜本页 %d 条｜"
             "结构合规不等于视觉验收：本页只排图与判据，不写通过。</p>" % (page_no, len(items))]
    for it in items:
        info = it["info"]
        parts.append("<div class=\"item\"><h3>%s %s｜%s｜%s</h3>" % (it["id"], it["name"], it["type"], info["size"]))
        parts.append("<ul>")
        parts.append("<li>日面可纳性（C99 复算）：%s</li>" % sun_expect(info))
        parts.append("<li>人数档：%s</li>" % (info["band"] or "未见"))
        parts.append("<li>背景天际线只许取景段逐一点名的独立远景，主体构件写作「远景」不算授权（C101／C123）；层数不符只记备注（C124）；画风按 C122 判平滑过渡在位、不以笔触为准。</li>")
        parts.append("<li>本条锁定与禁则：%s</li>" % (info["锁定"] or "未见"))
        parts.append("</ul><div class=\"grid\">")
        for p in it["image_file"]:
            parts.append("<div class=\"cell\"><img loading=\"lazy\" src=\"%s\"><div class=\"cap\">%s</div></div>"
                         % (img_src(p), p.split("/")[-1]))
        parts.append("</div></div>")
    parts.append("</body></html>")
    return "\n".join(parts)


items = []
for it in MANIFEST["items"]:
    if not it.get("image_file"):
        continue
    info = parse_prompt(it["prompt_file"])
    items.append(dict(id=it["id"], name=it["name"], type=it["type"], status=it["status"],
                      batch=it.get("batch") or "", image_file=it["image_file"], info=info))

if OUT.exists():
    shutil.rmtree(OUT)
SHEETS.mkdir(parents=True)

md = ["# B5 人工复看工作单（%d 条既有图）" % len(items), "",
      "生成物，禁止手改：本单由 `python 工具/build_review_suite.py` 从 `数据/开图清单.json`、"
      "`数据/开图验收备注.json` 与 `数据/开图提示词/*.txt` 派生。",
      "**本套件只排工作与判据，不写结论**：不改 `status`、不绑 `image_prompt_sha256`、不判通过；"
      "人工结论的唯一可编辑源是 `数据/开图验收备注.json`，重跑本单不丢结论。",
      "重跑说明：本单每次重跑会被覆盖，`工作单.md` 与 `打表汇总.csv` 里手写的结论都会丢；"
      "要留结论就写进 `数据/开图验收备注.json`，那里是人工复验的唯一源，也是本单的回显来源。",
      "判据十条的出处：C100（首句画风锚点）、C93／D4（双层接触）、C92（人群档）、D3（招牌豁免）、"
      "C97（标识容器，角标与 TC260 不属判废项）、C99（日面可纳性）、C101／C123（远景可纳性与背景授权唯一入口）、"
      "C106（远景塔形来源）、C124（层数不符只记备注）、"
      "C89／C90（高度分层与 L007 塔冠唯一）。",
      "联络表：`数据/人工复看套件/联络表/index.html`（每页 %d 条，图按懒加载；图片文件不版本化，"
      "换机打不开属预期）。" % PAGE_ITEMS, ""]
md += blocks(items)
(OUT / "工作单.md").write_text("\n".join(md) + "\n", encoding="utf-8")

with (OUT / "打表汇总.csv").open("w", encoding="utf-8-sig", newline="") as fh:
    writer = csv.writer(fh)
    writer.writerow(["ID", "名称", "类型", "图格数", "状态", "批次", "已记人工结论", "prompt_sha256前12"])
    for it in items:
        writer.writerow([it["id"], it["name"], it["type"], len(it["image_file"]), it["status"],
                         it["batch"], "有" if NOTES.get(it["id"]) else "无",
                         it["info"]["head"].get("prompt_sha256", "")[:12]])

pages = [items[i:i + PAGE_ITEMS] for i in range(0, len(items), PAGE_ITEMS)]
index = ["<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\"><title>B5 复看联络表目录</title>",
         "<style>body{font-family:sans-serif;background:#111;color:#eee;margin:16px}li{margin:2px 0}</style>",
         "</head><body>",
         "<p>共 %d 条既有图｜每页 %d 条｜%d 页。结构合规不等于视觉验收，本页不写通过。</p>"
         % (len(items), PAGE_ITEMS, len(pages)), "<ul>"]
for no, page in enumerate(pages, 1):
    fname = "页-%02d.html" % no
    (SHEETS / fname).write_text(sheet_html(no, page), encoding="utf-8")
    ids = "%s—%s" % (page[0]["id"], page[-1]["id"])
    index.append("<li><a href=\"%s\">第 %d 页</a>｜%s｜%d 条</li>" % (fname, no, ids, len(page)))
index.append("</ul></body></html>")
(SHEETS / "index.html").write_text("\n".join(index), encoding="utf-8")

print("suite items %d cells %d pages %d notes %d"
      % (len(items), sum(len(i["image_file"]) for i in items), len(pages), len(NOTES)))
