# -*- coding: utf-8 -*-
"""从AI地点知识库为名录全部正典地点逐条生成开图提示词，并建立图片与地点的对应关系清单。条数不写死在本文件，以 AI地点知识库 的记录数为准。"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "数据"
PROMPT_DIR = DATA / "开图提示词"
PROMPT_DIR.mkdir(exist_ok=True)

KB = json.loads((DATA / "AI地点知识库.json").read_text(encoding="utf-8"))
PRICING = {r["id"]: r for r in json.loads((DATA / "参考房价租金.json").read_text(encoding="utf-8"))["records"]}
REG = {e["id"]: e for e in json.loads((DATA / "城市空间名录.json").read_text(encoding="utf-8"))["entries"]}

SIZE_BY_TYPE = {
    "标志性建筑": ("1536x1024", "3:2 横幅，按正典容纳建筑体量与场馆、院落空间"),
    "功能区": ("1280x1024", "5:4 近正方，容纳街区尺度与人的活动"),
    "居民区": ("1280x1024", "5:4 近正方，容纳院落群与出入口流线"),
    "城市片区": ("1792x1024", "7:4 横幅，容纳扇区边界与天际线"),
    "产业小镇": ("1792x1024", "7:4 横幅，容纳生产用地与聚落边界"),
    "特色村落": ("1792x1024", "7:4 横幅，容纳地貌与村落肌理"),
}
# 竖幅按形态规则裁定（C91），不再维护手写 ID 清单：2-A 扩名录与 2-B 抬档后，名录里有 41 座名称以
# 「塔/钟楼」结尾的标志性建筑，手写清单必然漏——2-A 前它只剩 5 条，全城第一高 L066 反倒在 3:2 横幅里。
# 判据＝标志性建筑 且 名称以「塔/钟楼」结尾 且 名录 height_m ≥150 米；实测命中 28 条。
TOWER_NAME_SUFFIX = ("塔", "钟楼")
TOWER_MIN_HEIGHT_M = 150
# 规则之外的既有竖幅豁免，逐条给理由，不按数量凑：
# L003/L022/L033/L038 是 150 米以下的细高塔与钟楼，横幅会切掉冠部，沿用开图前的竖幅口径；
# L007 钛湖之脊 368 米是塔形，但名称不含「塔」，规则抓不到，而它已带竖幅成图，改横幅等于作废重出。
TOWER_EXEMPT_IDS = {"L003", "L007", "L022", "L033", "L038"}


def is_portrait(typ, eid, name, height_m):
    return typ == "标志性建筑" and (
        (name.endswith(TOWER_NAME_SUFFIX) and height_m >= TOWER_MIN_HEIGHT_M)
        or eid in TOWER_EXEMPT_IDS
    )


BATCH_ORDER = ["标志性建筑", "功能区", "产业小镇", "特色村落", "居民区", "城市片区"]


def sun_side(rel):
    if rel is None:
        return "取景段未给拍摄朝向，开图前需人工补定朝向"
    a = abs(rel)
    side = "右" if rel > 0 else "左"
    if a <= 25:
        return "正前方低角逆光（%d°相对），轮廓发亮、投影朝向镜头" % round(rel)
    if a < 80:
        return "%s前侧斜射（%d°相对），斜侧光、投影斜向展开" % (side, round(rel))
    if a < 95:
        return "%s侧光（%d°相对），明暗面对比最大" % (side, round(rel))
    if a <= 115:
        return "%s侧偏后（%d°相对），侧后光、擦亮背向镜头一侧的立面边缘" % (side, round(rel))
    if a < 160:
        return "%s后侧（%d°相对），侧后光、朝向镜头的立面偏冷调" % (side, round(rel))
    return "正后方顺光（%d°相对），立面材质与色彩最清楚" % round(rel)


HARD_LABEL = {
    "height_m": "建筑高度米", "floors": "使用楼层", "gross_floor_area_m2": "建筑面积平方米",
    "population": "常住人口", "households": "户数", "area_km2": "占地平方公里",
    "height_limit_m": "限高米", "daily_workers": "日常岗位", "distance_to_lake_center_km": "距湖心千米",
}
TAIL_BY_TYPE = {
    "标志性建筑": "photorealistic architectural photography, building form and composition true to the canon section",
    "功能区": "photorealistic street-level urbanist photography, everyday public space",
    "居民区": "photorealistic street-level residential photography, lived-in not staged",
    "城市片区": "photorealistic high-angle district overview, readable sector edge and skyline",
    "产业小镇": "photorealistic regional landscape photography, production land plus settlement, "
                "no main-city skyline or lake visible through the mountains",
    "特色村落": "photorealistic rural landscape photography, mountain village texture, "
                "no main-city skyline or lake visible through the mountains",
}


# 阶段 3 人群接线（C92）：详档的「人群与生活节奏」段此前被整段丢弃，312 条提示词里关于人只剩
# tail 的一句 everyday people doing everyday things。这里按类型给画面内可见人物的缺省档，
# 并把详档优先权写进同一行——L066 人群段有「周末几乎空场」、L033 有「控制同时停留的人流」，
# 缺省档不得把这些详档写成反的，所以档位只作缺省，冲突时以本条人群段与锁定段为准。
CROWD_BAND_BY_TYPE = {
    "城市片区": "街道层连续人流、人行道上人距1—3米（俯瞰条不作人物计数，但必须能看出地面有人在走）",
    "标志性建筑": "前景与中景合计15—40人，主体人物组3—6人，至少一组正在做具体的事（搬、聊、等、吃）",
    "功能区": "20—60人，含卸货、排队与上下班对流，底商连续营业、灯箱亮着",
    "居民区": "8—25人，含老人带孩、晾晒、遛狗、下棋、买菜归来；晾晒与盆栽不得堵通道",
    "产业小镇": "6—18人，以生产活动为主，不出现主城式人流",
    "特色村落": "6—18人，以生产活动为主，不出现主城式人流",
}
CROWD_PRIORITY = "本条人群段与锁定段的具体描写优先于该缺省档，冲突时按详档，不为凑人数增删人物。"
# 不可校验的热闹词一律不进提示词；详档正文若写进来，生成器在此退出而不是照抄。
CROWD_BANNED = ("人山人海", "热闹繁华", "繁华喧嚣", "摩肩接踵", "人流如织", "熙熙攘攘")

GLOBAL = [
    "虚构城市钛湖城，2013年，当代现实技术，不是赛博朋克",
    "本地坐标：湖心(0,0)，x向东、y向北，单位千米；方位北0°顺时针",
    "中心湖约6.4×4.2千米椭圆，四面环山；清岚河西北入湖，澜川东南外流",
    "默认光照：晚秋，太阳方位255°、高度6°，能见度12至18千米；清晨、夜景、雨后、阴天须显式标注为变体",
    "天际线分层：L066钛心金融主塔458米为全城第一，L007钛湖之脊368米（含针状天线）为第二；200米以上的塔楼在内湖环金融与枢纽片区成簇，逐栋参数以空间名录为准，提示词内不复数",
    "非对称直线斜削冠与细针状天线的组合只属于L007，任何其它塔楼不得复制该冠部；L007与L066均为直线形体，不得扭转",
    "机场只在S02山外，跑道东西向3.2千米；不得出现第二个机场",
    "禁止：湖中高楼、海港、大型人工岛、飞行汽车、把L007的斜削冠与针状天线安到别的塔楼上",
    "山体遮挡：外围村镇通常不能透山看到湖面或主城天际线",
    "正文中的无水印禁则指第三方或模型生成的水印、台标、logo与签名；不得生成可读的凭空文字与招牌字样",
    "平台强制AIGC角标与XMP中的TC260元数据标识不属禁则，须原样保留，不得裁剪、遮盖或修补",
]

manifest = []

# 清单回填是真源；图片、批次、备注按ID保留，验收必须绑定当前生成输入摘要。
# 不得用新摘要自动补绑旧图，否则会把未经复验的图片洗成已验收。
PREV = {}
MANIFEST_PATH = DATA / "开图清单.json"
if MANIFEST_PATH.exists():
    PREV = {it["id"]: it for it in json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["items"]}

NOTES_PATH = DATA / "开图验收备注.json"
MANUAL = json.loads(NOTES_PATH.read_text(encoding="utf-8"))["备注"] if NOTES_PATH.exists() else {}


def review_state(prev, prompt_sha256, manual):
    note = "；".join(manual) if manual else (prev.get("review_note") or "")
    reason = ""
    if not prev.get("image_file"):
        status = "待开图"
        if prev.get("status") and prev["status"] != "待开图":
            reason = "未回填 image_file，无图不能视为已生成或已验收"
    elif not prev.get("image_prompt_sha256"):
        status = "待复验"
        reason = "旧图缺少 image_prompt_sha256，须对照当前提示词实际复验"
    elif prev["image_prompt_sha256"] != (prev.get("generation_input_sha256") or prompt_sha256):
        status = "待复验"
        reason = "图片绑定摘要与实际生成输入不一致，须实际复验"
    elif prev.get("generation_input_sha256") and prev.get("image_base_prompt_sha256") != prompt_sha256:
        status = "待复验"
        reason = "图片对应的基准提示词已变化，须对照当前提示词实际复验"
    else:
        status = prev.get("status") or "待复验"
        if status == "待开图":
            status = "待复验"
    if reason and reason not in note:
        note = "；".join(part for part in (note, reason) if part)
    return status, note


def price_line(price):
    out = []
    for key, label in (("residential", "住宅"), ("office", "办公"),
                       ("retail", "商业"), ("street_retail", "底商")):
        v = price.get(key)
        if not v:
            continue
        if "rent_tt_per_m2_month" in v:
            rent, unit = v["rent_tt_per_m2_month"], "钛币/㎡·月"
        else:
            rent, unit = v.get("rent_tt_per_m2_day"), "钛币/㎡·天"
        out.append("%s%s钛币/㎡、租%s%s" % (label, format(v["sale_tt_per_m2"], ","), rent, unit))
    result = "｜".join(out) if out else "无市场价（自用或生态用地）"
    if price.get("reference_only") or price.get("asset_use") == "公共自用":
        result += "（公共自用物业：仅周边/同地块功能组合参考，不是本建筑交易价）"
    return result


for rec in KB:
    eid, name, typ = rec["id"], rec["name"], rec["type"]
    reg = REG[eid]
    sec = rec["sections"]
    取景 = sec["图像与视频取景"]
    锁定 = sec["锁定项与禁则"]
    位置 = sec["位置与规模"]
    外观 = sec["外观与辨识细节"]
    人群 = sec["人群与生活节奏"]
    不可校验 = [w for w in CROWD_BANNED if w in 人群 or w in 外观 or w in 锁定]
    if 不可校验:
        raise SystemExit("%s 的详档含不可校验的热闹词：%s（先改分卷原稿再重跑，生成器不代改正文）"
                         % (eid, "、".join(不可校验)))
    size, aspect = SIZE_BY_TYPE[typ]
    if is_portrait(typ, eid, name, reg.get("height_m", 0)):
        size, aspect = "1024x1536", "2:3 竖幅，容纳正典塔身与冠部"
    parent_name = "主城区" if rec.get("parent") == "CITY" else (rec.get("parent_name") or "山外围区域")
    rel = rec.get("sun_relative_deg")
    facing = rec.get("camera_facing_deg")
    ring = PRICING[eid]["ring"]
    price = PRICING[eid]
    pricing_reference = price_line(price)
    hard = ["%s %s" % (HARD_LABEL[k], reg[k]) for k in HARD_LABEL if k in reg]
    fname = "%s-%s.txt" % (eid, name)
    lines = []
    lines.append("# 开图提示词｜%s %s" % (eid, name))
    lines.append("")
    lines.append("## 对应关系（生成后请回填 image_file 与 batch）")
    lines.append("")
    lines.append("- 地点ID：%s" % eid)
    lines.append("- 名称：%s" % name)
    lines.append("- 类型：%s" % typ)
    lines.append("- 所属：%s（%s）" % (parent_name, rec.get("parent") or "REGION"))
    lines.append("- 圈层：%s｜距湖心 %s 千米｜方位角 %s°" % (ring, rec.get("distance_to_lake_center_km"), rec.get("bearing_from_lake_center_deg")))
    lines.append("- 中心坐标：(%s, %s) 千米" % tuple(reg["center_km"]))
    lines.append("- 建议尺寸：%s（%s）" % (size, aspect))
    lines.append("- 拍摄朝向：%s°（北0°顺时针）｜太阳相对方位：%s°" % (facing, rel))
    lines.append("- 光照判定：太阳在画面%s" % sun_side(rel))
    if rec.get("lighting_baseline") == "labeled variant":
        lines.append("- 光照说明：本条取景段使用显式标注的光照变体（清晨、夜景、雨后或阴天），上一行的255°侧别只作对照，开图时以正文变体描述为准")
    else:
        lines.append("- 光照说明：本条按默认晚秋255°方位、6°高度开图")
    lines.append("- 经济梯度参照：%s" % pricing_reference)
    lines.append("- 名录硬参数：%s" % "；".join(hard))
    lines.append("- 正典出处：%s ｜ 详档正文 %s 汉字" % (rec["volume"], rec["detail_cjk_count"]))
    lines.append("")
    lines.append("## 提示词正文")
    lines.append("")
    lines.append("【画面定位】%s" % 位置.split("。")[0] + "。")
    lines.append("【取景指令】%s" % 取景)
    lines.append("【外观辨识】%s" % 外观)
    lines.append("【人群与烟火气】%s｜画面内人物密度缺省档：%s。%s"
                 % (人群, CROWD_BAND_BY_TYPE[typ], CROWD_PRIORITY))
    lines.append("【锁定与禁则】%s" % 锁定)
    lines.append("【全局硬设定】%s" % "；".join(GLOBAL))
    lines.append("")
    lines.append("English tail: %s, %s, natural light as the canon section states, true material texture, "
                  "everyday people doing everyday things, no third-party or model-generated watermark, logo or signature, "
                  "preserve mandatory platform AIGC labels and TC260 XMP metadata unchanged, no readable invented signage text, "
                  "no invented landmark, everything above in the Chinese canon sections overrides this line."
                  % (TAIL_BY_TYPE[typ], aspect.split("，")[0]))
    # UTF-8 / LF的完整生成输入：身份、硬参数、原文、价格、尺寸和中英文模板。
    # 状态、摘要自身、图片路径、批次与人工备注在计算后加入，避免自引用与回填漂移。
    prompt_sha256 = hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()
    prev = PREV.get(eid) or {}
    status, review_note = review_state(prev, prompt_sha256, MANUAL.get(eid) or [])
    metadata_at = lines.index("## 提示词正文") - 1
    lines[metadata_at:metadata_at] = [
        "- 状态：%s" % status,
        "- prompt_sha256：%s" % prompt_sha256,
        "- image_prompt_sha256：%s" % (prev.get("image_prompt_sha256") or "未绑定"),
        "- 复验原因/备注：%s" % (review_note or "无"),
    ]
    body = "\n".join(lines) + "\n"
    (PROMPT_DIR / fname).write_text(body, encoding="utf-8")
    manifest.append({
        **prev,  # 保留既有备注及其他人工回填字段，派生字段以下列当前值覆盖。
        "id": eid,
        "name": name,
        "type": typ,
        "parent": rec.get("parent"),
        "parent_name": parent_name,
        "ring": ring,
        "center_km": reg["center_km"],
        "distance_to_lake_center_km": rec.get("distance_to_lake_center_km"),
        "size": size,
        "aspect": aspect,
        "camera_facing_deg": facing,
        "sun_relative_deg": rel,
        "sun_side": sun_side(rel),
        "lighting_baseline": rec.get("lighting_baseline"),
        "pricing_reference": pricing_reference,
        "prompt_file": "数据/开图提示词/" + fname,
        "prompt_sha256": prompt_sha256,
        "image_prompt_sha256": prev.get("image_prompt_sha256"),
        "image_file": prev.get("image_file"),
        "batch": prev.get("batch"),
        "status": status,
        "review_note": review_note,
        "review_note_history": list(MANUAL.get(eid) or []),
        "acceptance": "对照【锁定与禁则】逐条核验；出现扭转曲面、湖面穿帮、把L007的斜削冠与针状天线安到别的塔楼上、可读凭空文字或第三方台标渠道logo即判废；"
                      "平台按AIGC强制标识加的角标与XMP里的TC260元数据标识不属判废项，须原样保留",
    })


manifest.sort(key=lambda m: (BATCH_ORDER.index(m["type"]), int(m["id"][1:])))
out = {
    "version": "1.1",
    "fictional": True,
    "setting_year": 2013,
    "declaration": "提示词由分卷成稿的取景段与锁定段逐字提取，硬参数取自城市空间名录，光照侧别按 rel=(255−拍摄朝向+180)mod360−180 推导。"
                   "生成后回填 image_file 与 batch，保持一图对一点；prompt_sha256 是不含状态、摘要与回填字段的基准生成输入摘要。"
                   "仅在实际验收通过后绑定图片：无补充输入时 image_prompt_sha256=prompt_sha256；有补充输入时另存 generation_input_file 与 generation_input_sha256，"
                   "image_prompt_sha256 绑定实际输入，image_base_prompt_sha256 绑定生成时基准版本；基准变化仍须复验，不得只复制摘要补绑。"
                   "重跑保留图片路径、批次与既有备注；有图但绑定缺失或不一致降为待复验并写 review_note，无图始终待开图。"
                   "generated 仅按非空 image_file 计数，不代表验收通过；accepted、needs_review 分别统计已验收、待复验。"
                   "判废口径见AI创作使用手册第9节：第三方台标与渠道logo判废，平台AIGC强制标识角标与XMP里的TC260元数据标识须原样保留。",
    "prompt_count": len(manifest),
    "pending": sum(1 for m in manifest if m["status"] == "待开图"),
    "generated": sum(1 for m in manifest if m["image_file"]),
    "accepted": sum(1 for m in manifest if m["status"] == "已验收"),
    "needs_review": sum(1 for m in manifest if m["status"] == "待复验"),
    "batch_order": BATCH_ORDER,
    "items": manifest,
}
(DATA / "开图清单.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

md = ["# 钛湖城开图清单（%d条，一图对一点）\n" % out["prompt_count"]]
md.append("每条提示词是 `数据/开图提示词/` 下的独立文件，文件名即“ID-名称”。生图后把图片路径回填到 `数据/开图清单.json` 的 `image_file` 与 `batch` 字段，不要另建对照表，避免两边漂移。\n")
md.append("实际验收通过后再绑定图片：无补充输入时 `image_prompt_sha256=prompt_sha256`；有补充输入时记录 `generation_input_file`、`generation_input_sha256` 与 `image_base_prompt_sha256`，图片绑定实际输入摘要，基准变化仍须复验。不得只复制摘要补绑；图片、批次与既有备注保留。无图始终待开图，有图不代表通过；修改状态后重跑本生成器同步提示词和本表。\n")
md.append("提示词 %d｜待开图 %d｜有图 %d｜已验收 %d｜待复验 %d。有图数仅按非空 `image_file` 统计，不代替人工验收。\n" % (
    out["prompt_count"], out["pending"], out["generated"], out["accepted"], out["needs_review"]))
md.append("## 批次与验收\n")
md.append("- 建议批次顺序：%s。地标先跑，按各自正典核验建筑形态与水体关系，不统一套用单塔；片区最后跑，因其视野最广、最容易把不该看见的湖面塞进背景。" % "→".join(BATCH_ORDER))
md.append("- 验收以条目自身的【锁定与禁则】为准，通用否决项为：曲面扭转塔、湖中建塔、把L007的非对称直线斜削冠与细针状天线安到别的塔楼上、第二个机场、海港或大型人工岛、可读的凭空文字、第三方台标或渠道logo水印（模型侧带出的「LibTV」一类标记）、把湖面强塞进山外村镇背景。200米以上的塔楼在扩容后已成簇，按名录逐栋核对高度与冠部，不再以「第二座超过200米的塔」作否决。平台按AIGC强制标识加的「Qoder AI生成」角标与图片XMP里的TC260元数据标识不属否决项，须原样保留，不得裁剪、遮盖或修补。")
md.append("- 人群核验以条目自身的【人群与烟火气】为准：先看本条详档人群段的具体描写，再看该类型的缺省人数档，二者冲突按详档。画面人物明显低于档位下限（空街、空场）或反过来形成盛大庆典、统一着装团体，均记为待复验；俯瞰与鸟瞰条不逐个数人，但地面必须看得出有人在走动。")
md.append("- 光照默认晚秋255°方位、6°高度；清晨、夜景、雨后、阴天只有在提示词里显式标注为变体时才允许，清单的“光照判定”列已按每条的拍摄朝向算好太阳侧别。\n")
for typ in BATCH_ORDER:
    rows = [m for m in manifest if m["type"] == typ]
    md.append("\n## %s（%d条）\n" % (typ, len(rows)))
    md.append("| ID | 名称 | 所属 | 尺寸 | 朝向° | 太阳相对° | 太阳侧别 | 参照价 | 提示词文件 | 图片 | 状态 | 复验原因/备注 |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for m in rows:
        md.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            m["id"], m["name"], m["parent_name"], m["size"],
            m["camera_facing_deg"], m["sun_relative_deg"], m["sun_side"].split("（")[0],
            m["pricing_reference"], m["prompt_file"], m["image_file"] or "待生成",
            m["status"], m["review_note"].replace("|", "\\|").replace("\n", "<br>") or "—"))
    md.append("")
md.append("人工验收备注只在 数据/开图验收备注.json 里改，重跑后同步进 review_note_history；清单里的 review_note 是「人工末条＋派生原因」的拼接展示值，不手改。")
(ROOT / "数据" / "开图清单.md").write_text("\n".join(md), encoding="utf-8")
print("prompts", len(manifest), "files", len(list(PROMPT_DIR.glob('*.txt'))))
print("no-facing", sum(1 for m in manifest if m["camera_facing_deg"] is None))
print("variant", sum(1 for m in manifest if m["lighting_baseline"] == "labeled variant"))
