# -*- coding: utf-8 -*-
"""从AI地点知识库为名录全部正典地点逐条生成开图提示词，并建立图片与地点的对应关系清单。条数不写死在本文件，以 AI地点知识库 的记录数为准。"""
import hashlib
import json
import math
import re
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


# C99：日面可纳性。第8节与第10节的目视打表里，D08／D11／D14／F012／L083 五张成图都把太阳画进了画面，
# 而按 35mm 全幅的水平半视锥（atan(18/焦距)）算，这几条的太阳相对方位都在画框之外——只有 D03（3°）在框内。
# 原文只写 natural light as the canon section states，等于把「侧别」交给模型自由发挥，模型于是把
# 「暖色夕光」理解成「画面里要有落日」。这里按本条的 rel 与焦距算一次，把结论写成 tail 的硬约束。
def focal_mm(取景):
    m = re.search(r"(\d+(?:\.\d+)?)\s*毫米", 取景 or "")
    return float(m.group(1)) if m else None


def sun_frame_phrase(rel, focal, size, variant=False):
    # 时段变体条（C96／B6）的 255°侧别只作对照，光照以正文变体描述为准，因此不套默认光的可纳性算式，
    # 否则会给「清晨」条写进「落日不得入画」这种与本体矛盾的字。C111 把这一刀收窄到「取景段自己换掉了太阳」的条：
    # variant 实参由 variant_exempt_from_sun_math() 给，沿用255°基准的 6 条照样实算。
    if variant or rel is None or not focal:
        return "natural light as the canon section states"
    half = frame_half_angle(focal, size)
    side = "right" if rel > 0 else "left"
    if abs(rel) <= half:
        # 可纳分支也必须写侧别：L066 v02 的日面落在画面左侧，而该条 rel=+15°、正文写「右前侧掠入」，
        # 旧写法只给「off the camera axis」不带左右，等于让模型自己猜一侧，猜错就与正文相反。
        return ("the sun sits inside this frame as the canon section states (%.0f degrees to the %s of the camera axis, "
                "inside the %.0f degree half-angle), low and backlit with rims lit and shadows running toward the lens"
                % (abs(rel), side, half))
    return ("the sun is %.0f degrees to the %s of the camera axis and outside this frame's %.0f degree half-angle, "
            "so keep the sun disc, the setting-sun glow and any lens flare out of the picture entirely; paint only "
            "the light direction, the lit surfaces and the shadows the canon section describes"
            % (abs(rel), side, half))


# C111：R054 连两版都在画面左画出日面圆盘（旧串 v02 与 C109／C110 新串首投同一落点），逐字查下来不是
# 「句子埋在尾部被题材压倒」，而是它的串里根本没有日面可纳性这句话——C99 以「变体的光照以正文变体描述为准」
# 把 16 条时段变体整体豁免了算式，可其中 6 条的取景段明写「255°…照入／进入／落在／擦亮／掠入」，
# 实际光照仍是默认黄昏太阳，豁免对它们不成立；R054 的取景段只给「从画面左侧掠入」，既没写日面可纳与否，
# 模型于是把「雨后晴日、左侧来光」读成画面里该有一个太阳。
# 于是按「取景段有没有自己把太阳换掉」重新分档：换掉了的（清晨／入夜／阴天／漫射／西南偏西的低阳，以及
# S23 那种 255° 只出现在「若改拍黄昏」假设句里的）继续走静态句；沿用 255° 基准的按 C99 算式实算 tail；
# 算得须画外的三条再按 C105／C107 口径把禁令连侧别与度数复述进本条【锁定与禁则】段末。
# 默认光的 237 条一律不动：F012／S02／S18／L083 按 tail 算句重出的读数都是「日面不入画」通过，
# 把段内复述一次性铺到 237 条属无证据扩大；若它们之中再出现按 C99 尾部句重出仍画日面的，届时另立裁定。
# 分档表逐条由 check_variant_sun_keeps() 核回取景段措辞——原稿给某条换了太阳而表没跟着改，生成器直接退出。
VARIANT_KEEPS_DEFAULT_SUN = ("R006", "R015", "R034", "R054", "R063", "R066")
# 取景段把太阳换成别的光源的说法，与「夜景／清晨／阴天」这类本就没有日面的基线一起作豁免凭据。
SUN_REPLACED_TOKENS = ("不沿用", "不套用", "不套入", "不调用", "而非", "不额外放入")
SUN_ABSENT_BASELINE_TOKENS = ("夜景", "夜间", "入夜", "清晨", "阴天")


# C132：画框半幅宽不再按画幅写档位，改由本条实际画幅从一个定标派生。
# 定标：三档横幅与一档竖幅共用的那一边都是 1024 像素，它对应 35 毫米全幅的短边 24 毫米，
# 于是 半幅宽 = 12 毫米 ×（水平边像素 ÷ 1024）。四档实测：1536→18、1280→15、1792→21、竖幅 1024→12。
# 竖幅那一档与 C118 已裁的 12 毫米逐字相同，3:2 那一档与 C99／C101 立案起的 18 毫米逐字相同，
# 所以这次只把 C118 当时登记为「在案待裁」的 5:4 与 7:4 两档收进同一条算式，不新增档位、不否决 C104 的三档分工。
# 范围纪律：C118 的「没有成图证据就一并改等于无判据地翻摘要」这一顾虑由本条裁定承接——
# 翻的是 tail 里那个半角读数（5:4 与 7:4 共 189 条），入画／画外分支实测零翻转，画幅像素与 SIZE_BY_TYPE 一字不动。
FRAME_SHORT_EDGE_MM = 24.0
FRAME_BASE_PX = 1024


def frame_half_angle(focal, size):
    width_px = int(str(size).split("x")[0])
    half_width = FRAME_SHORT_EDGE_MM / 2 * width_px / FRAME_BASE_PX
    return math.degrees(math.atan(half_width / focal))


def variant_exempt_from_sun_math(eid, lighting_baseline):
    """C111 的分档唯一入口：只有「标了变体且取景段自己换掉了太阳」的条才跳过 C99 算式。"""
    return lighting_baseline == "labeled variant" and eid not in VARIANT_KEEPS_DEFAULT_SUN


def sun_out_lock_clause(rel, focal, size):
    half = frame_half_angle(focal, size)
    return ("本条沿用255°黄昏太阳：太阳相对本条机位偏%s%d°，在%g毫米镜头的±%.1f°水平半视锥之外，"
            "日面、落日辉光与镜头光斑一律不入画，只画取景段所述的光向、受光面与投影"
            % ("左" if rel < 0 else "右", round(abs(rel)), focal, half))


# C101：远景可纳性。B3 的 F039（机位朝北）与 R009（取景段「远景止于凸出的砖楼梯间」）都在远景画出了整片
# 主城天际线，其中还有一根扭转曲面超高层；L066 的 v01／v02 两版把 L007 的斜削冠＋细针天线安到了背景塔上。
# 按方位算，这两根超高层在 F039／R009 的机位背后或侧后，根本进不了画框。
# 第一版实现改成「逐条点名全部框内塔」，实测不可用：24 毫米街景的水平半视锥有 36.9°，按纯角度算，
# L066 本条会列出 38 根塔（它们角度在框内，但被 160 米外的 458 米主塔本身挡住），等于把禁则放开。
# 正典里被逐根命名、且因冠部形态专属而反复穿帮的只有两根超高层，于是只按几何管这两根，
# 其余远景一律交还给本条取景段点名的内容；取景段没给可解析机位的条目不硬算角度，只写不得凭空造天际线。
CAMERA_COORD = re.compile(r'[\(\（]\s*(-?\d+(?:\.\d+)?)\s*[,，、]\s*(-?\d+(?:\.\d+)?)\s*[\)\）]')

# 全城只有这两根超高层在正典里以冠部形态互相区分，穿帮也集中在这里（D03 v03、L066 v01／v02、R009 v01）。
NAMED_SUPERTALLS = ("L007", "L066")

# C109：C106 钉住了「形体来源」，L083 的两版仍各塌一处（v06 塌侧别、v07 把 L007 画成平顶＋居中细针，塌冠部形制）。
# 「按本正典自己的几何画」是泛指——模型读得到 straight shafts／flat or stepped crowns，读不到「这一根具体是什么冠」。
# 于是点名句必须带该塔自己的形制。形制串逐字取自各地标自己的【外观与辨识细节】与【锁定项与禁则】，
# 由下面的守卫逐字核回：原稿改了冠部措辞而这里没跟着改，生成器直接退出，不允许带着旧形制继续出图。
# 没被点名的远景塔一律只画体量不画冠部（剪影兜底写在 SKYLINE_SOURCE_RULE 末句）。
SUPERTALL_FORM = {
    "L007": (("非对称直线斜削冠", "细针状天线"),
             "a deep blue-grey straight shaft closed by an asymmetric straight-cut sloped crown whose high side "
             "carries a slender needle antenna (非对称直线斜削冠＋细针状天线), and this crown belongs to L007 alone"),
    "L066": (("四角小切角", "禁止加塔冠天线"),
             "a straight shaft whose section has small cut corners at the four corners and whose roof carries no "
             "crown antenna at all (四角小切角轮廓、禁止加塔冠天线)"),
}

_SECTIONS_BY_ID = {rec["id"]: (rec.get("sections") or {}) for rec in KB}


def check_supertall_form():
    drift = []
    for sid, (pins, _phrase) in SUPERTALL_FORM.items():
        body = "".join(_SECTIONS_BY_ID.get(sid, {}).values())
        drift += [sid + "「" + pin + "」" for pin in pins if pin not in body]
    if drift:
        raise SystemExit("远景形制点名的正典出处对不上：%s——原稿改了冠部措辞就跟着改 SUPERTALL_FORM，生成器不代改正稿"
                         % "、".join(drift))


check_supertall_form()


def check_variant_sun_keeps():
    """C111 的载入守卫：分档表必须与取景段的光照措辞逐条对得上，两个方向都核。"""
    drift = []
    keeps = set(VARIANT_KEEPS_DEFAULT_SUN)
    seen = set()
    for rec in KB:
        eid = rec["id"]
        seen.add(eid)
        取景 = (rec.get("sections") or {}).get("图像与视频取景") or ""
        is_variant = rec.get("lighting_baseline") == "labeled variant"
        replaced = [t for t in SUN_REPLACED_TOKENS if t in 取景]
        absent = [t for t in SUN_ABSENT_BASELINE_TOKENS if t in 取景]
        if eid in keeps:
            if not is_variant:
                drift.append("%s 不是时段变体却进了沿用255°的分档表" % eid)
            if "255°" not in 取景:
                drift.append("%s 取景段已不写255°" % eid)
            if replaced or absent:
                drift.append("%s 取景段出现换光凭据%s，应从 VARIANT_KEEPS_DEFAULT_SUN 移出"
                             % (eid, "、".join(replaced + absent)))
            if focal_mm(取景) is None or rec.get("sun_relative_deg") is None:
                drift.append("%s 取景段解析不出焦距或名录没有太阳相对方位，算式落不了地" % eid)
        elif is_variant and not (replaced or absent):
            drift.append("%s 是时段变体、取景段又没有换光凭据，需人工判定后补进分档表" % eid)
    missing = sorted(keeps - seen)
    if missing:
        drift.append("、".join(missing) + " 已不在知识库里")
    if drift:
        raise SystemExit("时段变体的日面可纳性分档对不上正典：%s——取景段改了光照措辞就跟着改 "
                         "VARIANT_KEEPS_DEFAULT_SUN，生成器不代改正稿" % "；".join(drift))


check_variant_sun_keeps()


# C118：未点名远景塔的屋顶禁则要住进段内。第12轮两条投放 2/2 栽在同一处——L083 的 L066 屋面起了一处短小
# 竖向构件、L061 的两栋背景楼屋顶起了细桅，而当时这条禁令只住在 tail 的 SKYLINE_SOURCE_RULE 里
# （"no invented crown, antenna or aperture"）。这与 C111 的发现同构：只写在尾部的禁令压不住模型，
# 投喂串是「中文段＋尾部英文串」两段，模型按中文段定画面结构。于是按 C111 的同一路子把禁令复述进
# 本条【锁定与禁则】段末。名单只收有读数凭据的两条，不铺到全部竖幅——无证据扩大是 C111 明确否掉的写法。
MAST_RECAP_IDS = ("L061", "L083")
MAST_RECAP_CLAUSE = ("本条远景里凡【取景指令】未点名的塔一律只画体量，屋顶不得起桅杆、天线、细竖杆或任何"
                     "冠部构件；取景段点名的塔才按它写明的形制画")
# 原稿自己写了这条禁则时，段内复述就是重复；守卫用这句的特征片段判「已自写」。
MAST_RECAP_PROBE = "屋顶不得起桅杆"


def check_mast_recap_ids():
    """C118 的载入守卫：段内复述的凭据名单必须与知识库和原稿禁则现状对得上，两个方向都核。"""
    drift = []
    seen = {rec["id"] for rec in KB}
    for eid in MAST_RECAP_IDS:
        if eid not in seen:
            drift.append("%s 已不在知识库里" % eid)
            continue
        rec = next(r for r in KB if r["id"] == eid)
        if not is_portrait(rec["type"], eid, rec["name"], REG[eid].get("height_m", 0)):
            drift.append("%s 已不是竖幅条，C118 的段内复述只裁竖幅小景别，应移出 MAST_RECAP_IDS" % eid)
        if MAST_RECAP_PROBE in (_SECTIONS_BY_ID[eid].get("锁定项与禁则") or ""):
            drift.append("%s 的原稿禁则已自写远景桅杆禁令，段内复述多余，应移出 MAST_RECAP_IDS" % eid)
    if drift:
        raise SystemExit("远景桅杆禁令的段内复述名单对不上正典：%s——原稿自写了这条就把它从 "
                         "MAST_RECAP_IDS 移出，生成器不代改正稿" % "；".join(drift))


check_mast_recap_ids()


def camera_km(取景):
    m = CAMERA_COORD.search(取景 or "")
    return [float(m.group(1)), float(m.group(2))] if m else None


def bearing(src, dst):
    return math.degrees(math.atan2(dst[0] - src[0], dst[1] - src[1])) % 360


def offset(b, facing):
    return (b - facing + 540) % 360 - 180


# C123：C101 的总则此前把授权宾语写成「取景段点名为『远景』的内容」，而第9批 48 条里 44 条的
# `【取景指令】远景为…` 宾语是主体自身的构件（L088 是整墙斜拉索上段、L100 是内凹小平台与屋顶菜园箱），
# 真正指外部远景的只有 L068／L103 两条——这条 tail 禁则约束的那个「远景」压根不是背景，对建筑条的背景天际线整个空转。
# 于是把授权宾语换成不受主体构件占位的「the background skyline beyond the main subject」，并显式收回「远景」二字的授权力；
# 同一句话在【全局硬设定】里也说一遍（见 GLOBAL 的天际线分层条），因为 C111／C118 已量过：只管画面的中文段压倒 tail。
FAR_VIEW_RULE = ("the background skyline beyond the main subject may contain only the distant objects the Chinese "
                 "framing section names one by one; the word 远景 inside the Chinese sections usually points at a part "
                 "of the main subject itself and never licenses a second city, so do not add a distant downtown "
                 "skyline, a supertall cluster or a tower crane that the framing section does not name")
# C106：远景「有没有资格出现」归 C101 管，但 C101 不管「出现的那几栋长什么样」。L083 的 C105 换档重出 v05
# 把远景侧别画对了（两座超高层落在左侧，与 tail 的偏左10°／偏左3° 一致），轮廓却是上海陆家嘴三件套的
# 现成剪影——模型在「允许画远景」时默认去抄现实天际线。本条把形体来源也钉住：背景塔按本正典自己的几何画。
SKYLINE_SOURCE_RULE = ("background towers are composed from this canon's own geometry (straight shafts, louver "
                       "bands and the flat or stepped crowns the Chinese sections name); any far tower this line "
                       "does not name a crown form for stays a plain mass with a flat or stepped top and no invented "
                       "crown, antenna or aperture; do not trace a real "
                       "city's skyline and do not borrow a real supertall's crown, twist or aperture")


def background_phrase(eid, 取景, facing, size):
    cam, focal = camera_km(取景), focal_mm(取景)
    parts = [FAR_VIEW_RULE, SKYLINE_SOURCE_RULE]
    for sid in NAMED_SUPERTALLS:
        if sid == eid:
            continue
        sup = REG[sid]
        form = SUPERTALL_FORM[sid][1]
        if cam is None or facing is None or not focal:
            # 静态句刻意不写高度：这 244 条并没有几何依据，把名录高度串进来只会让 L007／L066 一改高度
            # 就连带翻掉它们的摘要，使「改硬参数只动该动的条」这条隔离判据失效。
            parts.append("%s %s may appear only if the Chinese framing section names it, and then painted as %s; "
                         "its crown must not be reused on any other tower" % (sid, sup["name"], form))
            continue
        rel = offset(bearing(cam, sup["center_km"]), facing)
        half = frame_half_angle(focal, size)
        side = "right" if rel > 0 else "left"
        if abs(rel) <= half:
            # C118：几何可纳≠授权入画。旧写法 "so it may read in the far view" 让 tail 的点名句自己成了入画凭证，
            # 与同一段开头的 FAR_VIEW_RULE（远景只许取景段点名的内容）撞车——第12轮的 L083 按 tail 画出两栋、
            # L061 按 tail 未画出两栋，两种读法都能自证合规。这一句改成只给形制，入画与否归取景段独裁。
            # 措辞刻意不用分号：闸门侧按 "; " 切分逐塔片段，句内分号会把形制串切到下一段去。
            parts.append("%s %s (%d metres) sits %.0f degrees to the %s of this camera, inside the %.0f degree "
                         "half-angle, which makes it geometrically admissible here, but the Chinese framing "
                         "section stays the only thing that can put it in the picture and only where that section "
                         "names it does the far view paint it as %s"
                         % (sid, sup["name"], sup["height_m"], abs(rel), side, half, form))
        else:
            parts.append("%s %s (%d metres) is %.0f degrees to the %s of this camera and outside this frame's %.0f "
                         "degree half-angle, so neither its silhouette nor its crown may be painted here"
                         % (sid, sup["name"], sup["height_m"], abs(rel), side, half))
    return "; ".join(parts)


HARD_LABEL = {
    "height_m": "建筑高度米", "floors": "使用楼层", "gross_floor_area_m2": "建筑面积平方米",
    "population": "常住人口", "households": "户数", "area_km2": "占地平方公里",
    "height_limit_m": "限高米", "daily_workers": "日常岗位", "distance_to_lake_center_km": "距湖心千米",
}
# 阶段 4 换档（C93）：D2 把开图正典整体切到 E1 半写实厚涂，D4 把「顶级科技 × 中国老城 × 烟火气」
# 写成画面结构判据而不是形容词。六条 tail 逐条重写，每条必须同时给出科技层与老城层的实体词，
# 且二者物理接触。写实词与近未来词只许写在 NEGATIVE_TAG 的否定式里，正向段出现即由生成器判红。
# C122：2026-11-04 三轮单变量诊断把「油画感重」定位到两处，随后裁定皮肤豁免笔触、非金属层降到探底档。
# 第1轮文本生图不同机位，只算旁证；第2轮图生图锁机位（人脸框263→276→255，模板峰0.906/0.850且峰值在(0,0)）
# 证明皮肤媒介子句单独就能复现差值；第3轮把非金属层分五档拉梯（现／中／轻／极轻），极轻档是全串媒介词的地板：
# 人物臂靠「皮肤带笔触」这根柱子没塌成照片，把皮肤一并豁免后就是本档；塔臂则证明无人物时全靠两句媒介声明撑着。
# 风险写明并留在册：极轻档以下再无笔触可撤，画面读作画而非照片，只剩 semi-realistic digital painting 与
# painted illustration rather than a snapshot 两句声明加 NEGATIVE_TAG 的 photograph／3D render／film grain 三禁。
# 因此本档一旦某批出成照片质感或干净CG，处置不是换措辞（措辞已到底），而是按 C105 的强媒介串回退整条锚点与核心，
# 回退串与违例负测都钉在 工具/test_prompts.py 的 MEDIUM_ROLLBACK_PHRASES 上。
# C153（2026-11-09）：上面那句「一旦出成照片就回退」今天真的发生了，回退已执行。证据链见
# 工具/reshoot_campaign_2026_11_06/画风引力源对照-2026-11-09.md 与本轮探针：同一条 D03 在 768×1024／1024×1536／
# 1792×1024 三档画布用平滑档全部出照片；把三处画风句换成 C100 族（只说 visible brushwork）在卡面画布只回到半绘画；
# 换成下面的 C105 强媒介档才逐张读出笔触。油画感与照片感之间没有可达的中间措辞档，故本档取强媒介。
# 代价按 C153 登记：C133 的重投期基准冻结由本档解除，312 条主链与 114 条卡面串同时换档，11-07 已投 264 张的
# 复看结论作废待重看。
STYLE_CORE = ("semi-realistic digital painting, visible brushwork and hand-mixed edges, opaque impasto paint layers "
              "with dry-brush edges, painted surfaces, sky laid in with visible cloud strokes rather than a smooth "
              "blended gradient, warm late-autumn palette, illustrated cityscape rather than a snapshot")
# C100：B3 七张跨类型样本 5 张出成照片质感（L066／L083／F012／F039／R009），只有 S02／S18 保住厚涂；
# 与已定档的 R043 同尺度裁前景人物对比，判废项里最先失效的就是笔触。画风词此前只写在最末的 English tail，
# 而投喂串从【画面定位】开始就是一长串写实题材描述（玻璃幕墙、闸机、街面材质），模型按题材定档、不按尾串改档。
# 锚点提到投喂串首句，材质与人物都点名要笔触，并把「中文段写的是题材不是媒介」写死。
# C105：C100 的锚点仍不足以在竖幅近景压住题材写实度（L083 v04 判废）。同串换 1792×1024 横幅的诊断A 让天空、
# 树叶与金属板读出笔触，但人脸仍是照片质感且五官糊块；同画幅只把首句换成 gouache／oil impasto 强媒介串的诊断B
# 全幅落地。归因是措辞管媒介感、画幅管远景可纳性，两个变量各管一件事，故本条只加媒介强度、不动画幅档位：
# 首句补 opaque impasto 与 dry-brush 两个可画的媒介词，并把 tail 里与 B 冲突的 smooth airbrushed gradient sky 换掉。
# C122：同一锚点里的皮肤媒介子句于 2026-11-04 被撤销。锁机位对照（母图皮肤无笔触、A 皮肤须带笔触在颊鼻额读出成块厚涂、
# B 皮肤豁免后回到平滑）证明油画感差值由皮肤子句单独复现；五档梯又证明非金属层降到极轻档时人物不塌成照片。
# 两条并起来就是本档：皮肤与石材玻璃布料树叶一律平滑过渡，画感由 soft hand-mixed transitions 与勾形而不是厚涂承担。
# C153（2026-11-09）：C122 这一档按上面的在册风险条款回退到 C105 强媒介串。判据是目视，不是 CLIP——
# 平滑档在三种画布、带不带装帧禁令的四种串形态下全部出成照片，而强媒介档 2/2 读出笔触。
STYLE_ANCHOR = ("【画风锚点】medium is a semi-realistic digital painting: opaque impasto brush strokes and dry-brush "
                "edges build every surface, with visible brushwork and hand-mixed edges on faces, glass, stone, "
                "fabric and foliage, and the paint kept readable instead of smoothly blended; painted illustration "
                "rather than a snapshot; the Chinese sections below describe the subject, not the medium")
TAIL_BY_TYPE = {
    "标志性建筑": "painted landmark tower true to the canon section, modern layer (curtain-wall grid, lit "
                  "sky-lobby bands, rooftop telecom and HVAC plant, LED media panel on the podium) rising out of "
                  "old layer (grey-tile roofs, timber eaves, stone steps and a narrow old street touching the tower base)",
    "功能区": "painted street-level urbanist public space, modern layer (glass office fronts, station gates, "
             "smart lamp posts, underground duct covers) meeting old layer (brick-and-tile shopfronts, arcades, "
             "stone paving, an old gateway) on the same pavement",
    "居民区": "painted street-level residential block, lived-in not staged, modern layer (external AC units, "
             "rooftop PV panels, fibre cabinets, video intercom and EV charging posts) welded onto old layer "
             "(grey-tile eaves, shared laundry rig, ground-floor shops with lit lampboxes, pocket courtyard)",
    # C98：原写法把科技层锁成「behind old layer」，等于替每一个片区预先决定纵深次序。D03 实测穿帮
    # 即由此而来——真源取景段要求本片区塔群在中景、灰瓦老城在湖对岸作远景，固定词把塔群推去了对岸。
    # 双层实体词与接触点保留，纵深次序交还给本条中文取景段。
    "城市片区": "painted high-angle district overview with a readable sector edge, modern layer (a cluster of "
               "200-metre-class towers, transit viaduct, cranes on super-tall construction) and old layer "
               "(historic low-rise roof texture, old lanes and a riverside market street kept intact) sharing one "
               "frame with a visible contact edge where the two layers meet; which layer reads near and which reads "
               "far follows the Chinese framing section above, so do not default the tower cluster to the far side "
               "of the water",
    "产业小镇": "painted regional town, production land plus settlement, modern layer (hangars, rooftop PV arrays, "
                "test benches, freight sheds, clean-front workshops) beside old layer (self-built courtyard houses, "
                "old tile roofs and village alleys); no main-city skyline or lake visible through the mountains",
    "特色村落": "painted mountain village, old layer (ancestral hall, timber balconies, stone terraces, drying "
                "racks) carrying a modest modern layer (satellite dish, solar water heater, electric tricycle, "
                "fibre box, greenhouse film); no main-city skyline or lake visible through the mountains",
}
STREET_TRACES = ("street life must read as physical traces, at least three of: hanging laundry, potted plants and "
                 "rooftop planting, market crates mid-unload, steam off a street food stall, lit shop lampboxes, "
                 "parked bicycles and scooters, elders playing chess on backed stools, parents collecting children, "
                 "construction hoarding with a tower crane, rubbish collection point and truck, a dog on a lead, "
                 "puddle reflections after rain")
SIGNAGE_RULE = ("shop signboards, banners, lampboxes and door plates must exist along the street, drawn as blurred "
                "non-readable strokes; they must not spell legible characters or Latin words and must not invent a "
                "readable slogan")
# C108：雨后批四条失手都在同一处——右下角地面浮出淡色字母形笔画簇（R015 v01 落点约(1250,1009)、
# R034 v02 再现、R054 v01 同型，夜光批 R086 v01 也是这一落点）。tail 原有的
# "no third-party or model-generated watermark, logo or signature" 管的是画外水印与台标，
# 模型不把它读成「地面不许有字形」。R015 的单变量实验：同一条串只加一句
# nothing written on the ground or pavement in any corner，v01 的签名在 v02 同一落点消失，
# 只剩湿石高光与笔触。位置只限地面与画面四角，不写墙面与店招——D3／C93 要求招牌实体在位。
GROUND_MARKS_NEG = ("nothing written on the ground or pavement in any corner; no letter-shaped signature cluster, "
                    "monogram or floating glyph strokes on street surfaces, kerbs or in the four corners of the frame")
NEGATIVE_TAG = ("not a photograph, no photorealistic pore detail, no lens grain as the look, not a 3D render, "
                "no cel outline, no flat cel fills, not a cartoon, not an idol illustration; era 2013: no flying cars, "
                "no holograms, no humanoid robots, no cyberpunk, no near-future sci-fi, no autonomous vehicle fleets, "
                "no neon-drenched street replacing street life; no recognizable real-world skyline (Lujiazui, "
                "Hong Kong, Shenzhen Bay, Manhattan, Dubai, Chicago) and no crown, twist or aperture copied from "
                "a real supertall; " + GROUND_MARKS_NEG)
# 正向风格段的禁词。写实档与近未来档只许以否定式出现在 NEGATIVE_TAG 里，
# 所以这里禁的是「被改回正向」，负测通过改写正向常量来触发。
STYLE_BANNED = ("photorealistic", "photorealism", "photograph", "hyperrealistic", "dslr", "hdr photo")
ERA_BANNED = ("flying cars", "flying car", "hologram", "cyberpunk", "humanoid robot",
              "near-future sci-fi", "autonomous vehicle fleet")


def assert_affirmative_style(label, text):
    hit = sorted({w for w in STYLE_BANNED + ERA_BANNED if w in text})
    if hit:
        raise SystemExit("%s 的正向风格段含禁词 %s；写实档与近未来档只许写进 NEGATIVE_TAG 的否定式"
                         % (label, "、".join(hit)))


for _label, _text in (("STYLE_CORE", STYLE_CORE), ("STYLE_ANCHOR", STYLE_ANCHOR),
                      ("TAIL_BY_TYPE", " | ".join(TAIL_BY_TYPE.values())),
                      ("STREET_TRACES", STREET_TRACES), ("SIGNAGE_RULE", SIGNAGE_RULE),
                      ("SKYLINE_SOURCE_RULE", SKYLINE_SOURCE_RULE)):
    assert_affirmative_style(_label, _text)


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

# C107：时段变体条的三条失手都在同一处。B6夜光批四条里，R053 v01 整幅没有一个招牌实体，
# R086 v01 右下角出一串悬浮的拉丁形笔画，S23 v01 与 v02 连续两版把银河带画进夜空——
# 三条判据 GLOBAL 与【锁定与禁则】里都写着，模型仍照画。把同样的话复述进本条锁定段末（串外试投）
# 后，R053 v02 出门牌灯箱、R086 v02 四角干净，即与C105同一条机制：埋在长串尾部的全局句会被题材压倒。
# 只挂变体条：296 条默认光条的提示词逐字不变，摘要绑定不受本轮影响。
VARIANT_LOCK_CLAUSE = ("本条是显式标注的时段变体：门牌、店招或公告灯箱须有实体在画面中可见，"
                       "字形为不可读模糊笔画；画面四角、地面与墙面无字母形签名、台标或悬浮笔画；"
                       "夜景不得画出银河带、密集星场或长曝光星轨，天空以平滑过渡铺成深色，"
                       "星点疏密须与人物曝光相容")

GLOBAL = [
    "虚构城市钛湖城，2013年，当代现实技术；「顶级现代化」按2010年代前沿读：玻璃塔群、LED媒体立面、地下环道与综合管廊、城市轨道与枢纽换乘、光纤到楼、洁净实验室与数据中心、自助闸机、电动大巴、施工围挡与吊装作业；不得用飞行汽车、载人无人机、全息投影、机器人服务员、自动驾驶车队或赛博义体表达现代性，不是赛博朋克",
    "城市定位：顶级现代化科技城市 × 保存完好的中国老城街巷 × 烟火气。同一画面里科技层与老城层必须有物理接触，天上现代、地上生活——高层与设备在画面上半，人流与生活痕迹在画面下半；只有玻璃幕墙或只有仿古街都算不合格",
    # C153（2026-11-09）：本句与上面 STYLE_ANCHOR／STYLE_CORE 三处同档回退到 11-03 定档的厚涂措辞；
    # 平滑档（C122）在三种画布四种串形态下全部出成照片，中间措辞档（只说笔触不说厚涂）也只回到半绘画。
    "画风：半写实数字厚涂，笔触可辨、颜料层次读得出来、表面是画出来的，"
    "不是照片，也不是描边平涂的动画赛璐璐；人物保持真实比例与实际年龄特征",
    "本地坐标：湖心(0,0)，x向东、y向北，单位千米；方位北0°顺时针",
    "中心湖约6.4×4.2千米椭圆，四面环山；清岚河西北入湖，澜川东南外流",
    "默认光照：晚秋，太阳方位255°、高度6°，能见度12至18千米；清晨、夜景、雨后、阴天须显式标注为变体",
    "天际线分层：L066钛心金融主塔458米为全城第一，L007钛湖之脊368米（含针状天线）为第二；200米以上的塔楼在内湖环金融与枢纽片区成簇，逐栋参数以空间名录为准，提示词内不复数；成簇只是正典事实、不构成本条画面的授权，背景天际线只许画【取景指令】逐一点名的独立远景对象，未点名者一律不入画；本条正文里的「远景」二字常指主体自身的远处构件，不构成另画一片城市背景或超高层塔群的许可",
    "非对称直线斜削冠与细针状天线的组合只属于L007，任何其它塔楼不得复制该冠部；L007与L066均为直线形体，不得扭转",
    "机场只在S02山外，跑道东西向3.2千米；不得出现第二个机场",
    "禁止：湖中高楼、海港、大型人工岛、飞行汽车、把L007的斜削冠与针状天线安到别的塔楼上",
    "山体遮挡：外围村镇通常不能透山看到湖面或主城天际线",
    "正文中的无水印禁则指第三方或模型生成的水印、台标、logo与签名；招牌、店招、灯箱与门牌必须存在，但字形须是不可读的模糊笔画，不得形成可拼读的汉字或拉丁词，也不得凭空造出可读标语",
    "平台强制AIGC角标与XMP中的TC260元数据标识不属禁则，须原样保留，不得裁剪、遮盖或修补",
]

# C110：科技层核对串里的词分两类——「具名设施词」指向需要落位的地方（站厅、管廊、数据中心、枢纽…），
# 「表层材质词」只是画面质感（LED媒体立面、光纤到楼箱、屋顶通信设备）。核对项只许列有承载体的具名设施词，
# 否则判据就是在要求画一个正典里不存在的地点。实测：原核对串写「轻轨」时 312 条正文 0 命中——正典的说法是
# L037 钛湖东站的「城市轨道的东侧南北走廊向此接入」；「机场专线」「塔吊与在建超高层」同样 0 命中
# （第5期前提复核已确认城内无机场承载体），本条把它们换成正典实有的词，并让下面的守卫逐词核回名录。
TECH_CARRIER_WORDS = ("玻璃幕墙", "城市轨道", "站厅", "闸机", "地下环道", "管廊", "数据中心", "实验室",
                      "光伏", "大巴", "充电", "围挡", "吊装", "换乘", "枢纽")
TECH_SURFACE_WORDS = ("LED媒体立面", "光纤到楼箱", "屋顶通信设备")


def check_tech_carriers():
    bodies = ["".join(_SECTIONS_BY_ID.get(rec["id"], {}).values()) for rec in KB]
    homeless = [word for word in TECH_CARRIER_WORDS if not any(word in body for body in bodies)]
    if homeless:
        raise SystemExit("科技层核对项在 312 条正文里无承载体：%s——先登记承载体或把核对串改回正典实有的词，"
                         "生成器不代改正典" % "、".join(homeless))


check_tech_carriers()

manifest = []

# 清单回填是真源；图片、批次、备注按ID保留，验收必须绑定当前基准摘要（C135：绑定答「按哪版基准投的」）。
# 不得用新摘要自动补绑旧图，否则会把未经复验的图片洗成已验收。
# C139 起允许受委托代签，但代签只认机械判据，且必须在 数据/开图验收备注.json 留代签申报行
# （执行人／委托来源原句／依据读数／人工逐张目视未执行／绑定摘要前12位），由 test_image_assets 的
# check_sign_declaration 逐条判；没申报的已验收照旧判红。accepted 因此只表示机械验收通过。
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
    elif prev["image_prompt_sha256"] != prompt_sha256:
        # C135：绑定摘要一律是冻结基准串，实际送入串只作 generation_input_* 备案。
        # 原写法取 (generation_input_sha256 or prompt_sha256)，等于给补充输入通道开了第二套基准——
        # 按 C135 绑冻结串的条目会被这里当场降回待复验，与 verify_prompt_baseline 的 bind_ok 判反。
        status = "待复验"
        reason = "图片绑定摘要与当前基准提示词不一致，须实际复验"
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
    # C118：画幅口径要在日面句之前就定下来——水平半视锥对竖幅与横幅取不同的半幅宽，
    # 而竖幅判定（C91 形态规则）在本循环里只算这一次，段内禁句与 tail 必须共用同一个答案。
    portrait = is_portrait(typ, eid, name, reg.get("height_m", 0))
    # C132：半幅宽按本条画幅派生，所以画幅要在第一处算式之前就定下来；C118 当时只需一个竖幅布尔，
    # 现在生成器与 tail、段内禁句共用的是同一个 size 字符串。
    size, aspect = SIZE_BY_TYPE[typ]
    if portrait:
        size, aspect = "1024x1536", "2:3 竖幅，容纳正典塔身与冠部"
    if rec.get("lighting_baseline") == "labeled variant":
        锁定 = "%s。%s。" % (锁定.rstrip("。"), VARIANT_LOCK_CLAUSE)
        if eid in VARIANT_KEEPS_DEFAULT_SUN:
            # C111：沿用255°基准的变体条按本条几何实算，算得须画外的再把禁令复述进段末（可纳的条不写禁句，
            # 否则等于给 D03／R009 这类该画日面的条也套上「不入画」）。守卫已保证这两项都解析得出。
            _rel, _focal = rec.get("sun_relative_deg"), focal_mm(取景)
            if abs(_rel) > frame_half_angle(_focal, size):
                锁定 = "%s。%s。" % (锁定.rstrip("。"), sun_out_lock_clause(_rel, _focal, size))
    if eid in MAST_RECAP_IDS:
        # C118：远景桅杆禁令按 C111 的路子复述进段末（守卫已保证这两条仍在库里、仍是竖幅、原稿没自写这条）。
        锁定 = "%s。%s。" % (锁定.rstrip("。"), MAST_RECAP_CLAUSE)
    位置 = sec["位置与规模"]
    外观 = sec["外观与辨识细节"]
    人群 = sec["人群与生活节奏"]
    不可校验 = [w for w in CROWD_BANNED if w in 人群 or w in 外观 or w in 锁定]
    if 不可校验:
        raise SystemExit("%s 的详档含不可校验的热闹词：%s（先改分卷原稿再重跑，生成器不代改正文）"
                         % (eid, "、".join(不可校验)))
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
    lines.append(STYLE_ANCHOR)
    lines.append("【画面定位】%s" % 位置.split("。")[0] + "。")
    lines.append("【取景指令】%s" % 取景)
    lines.append("【外观辨识】%s" % 外观)
    lines.append("【人群与烟火气】%s｜画面内人物密度缺省档：%s。%s"
                 % (人群, CROWD_BAND_BY_TYPE[typ], CROWD_PRIORITY))
    lines.append("【锁定与禁则】%s" % 锁定)
    lines.append("【全局硬设定】%s" % "；".join(GLOBAL))
    lines.append("")
    lines.append("English tail: %s, %s, %s, %s, %s, painted material texture, "
                  "everyday people doing everyday things, %s, %s, %s, no third-party or model-generated watermark, logo or signature, "
                  "preserve mandatory platform AIGC labels and TC260 XMP metadata unchanged, no invented landmark, "
                  "everything above in the Chinese canon sections overrides this line."
                  % (STYLE_CORE, TAIL_BY_TYPE[typ], aspect.split("，")[0],
                     sun_frame_phrase(rel, focal_mm(取景), size,
                                      variant_exempt_from_sun_math(eid, rec.get("lighting_baseline"))),
                     background_phrase(eid, 取景, facing, size),
                     STREET_TRACES, SIGNAGE_RULE, NEGATIVE_TAG))
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
        "acceptance": "对照【锁定与禁则】逐条核验；出现扭转曲面、湖面穿帮、把L007的斜削冠与针状天线安到别的塔楼上、可读的招牌字形或凭空文字、第三方台标渠道logo即判废；"
                      "出成照片质感（毛孔、镜头噪点、景深颗粒）或干净CG渲染（表面无过渡层次、高光呈均匀塑料感）即判废重出；出现飞行汽车、全息投影、人形机器人等近未来符号即判废；"
                      "画面只有科技层或只有老城层、或两层被广场绿地切断没有接触，即记待复验；生活痕迹实体不足三项即记待复验；"
                      "平台按AIGC强制标识加的角标与XMP里的TC260元数据标识不属判废项，须原样保留",
    })


manifest.sort(key=lambda m: (BATCH_ORDER.index(m["type"]), int(m["id"][1:])))
out = {
    "version": "1.1",
    "fictional": True,
    "setting_year": 2013,
    "declaration": "提示词由分卷成稿的取景段与锁定段逐字提取，硬参数取自城市空间名录，光照侧别按 rel=(255−拍摄朝向+180)mod360−180 推导。"
                   "生成后回填 image_file 与 batch，保持一图对一点；prompt_sha256 是不含状态、摘要与回填字段的基准生成输入摘要。"
                   "仅在实际验收通过后绑定图片：image_prompt_sha256 一律绑当前基准 prompt_sha256（C135）；有补充输入时另存 generation_input_file 与 generation_input_sha256 作实际送入串备案，"
                   "image_base_prompt_sha256 记生成时基准版本；备案与绑定是两件事、谁也不能替谁过关，基准变化仍须复验，不得只复制摘要补绑。"
                   "重跑保留图片路径、批次与既有备注；有图但绑定缺失或不一致降为待复验并写 review_note，无图始终待开图。"
                   "generated 仅按非空 image_file 计数，不代表验收通过；accepted、needs_review 分别统计已验收、待复验。"
                   "C139 起 accepted 只表示机械判据验收通过，不表示人工逐张目视通过：受委托代签的条目必须在 数据/开图验收备注.json 留一行代签申报，"
                   "含执行人、委托来源原句、依据读数、「人工逐张目视未执行」与绑定摘要前12位，缺任一要素即判红（守卫是「没申报不许签」，不是「不许签」）。"
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
md.append("实际验收通过后再绑定图片：`image_prompt_sha256` 一律绑当前基准 `prompt_sha256`（C135）；有补充输入时把实际送入串记进 `generation_input_file`、`generation_input_sha256`，并用 `image_base_prompt_sha256` 记生成时基准版本——备案答「实际喂了什么」、绑定答「按哪版基准投的」，两者不能互相顶替，基准变化仍须复验。不得只复制摘要补绑；图片、批次与既有备注保留。无图始终待开图，有图不代表通过；修改状态后重跑本生成器同步提示词和本表。\n")
md.append("**已验收的语义边界（C139）**：本表「已验收」与本清单 `accepted` 只表示机械判据验收通过（容器标识、逐字回绑、格数与档串、尺寸对回声明），**不表示人工逐张目视通过、也不表示画风已过关**。受委托代签的每条都在 `数据/开图验收备注.json` 留一行 `C139代签验收<ID>：`，写明执行人、委托来源原句、依据读数、「人工逐张目视未执行」与绑定摘要前12位；缺任一要素由 `工具/test_image_assets.py` 的 `check_sign_declaration` 判红。画风侧的反向读数与未收口偏差见该轮登记，不得把 `accepted` 读成目视结论。\n")
md.append("提示词 %d｜待开图 %d｜有图 %d｜已验收 %d｜待复验 %d。有图数仅按非空 `image_file` 统计，不代替人工验收。\n" % (
    out["prompt_count"], out["pending"], out["generated"], out["accepted"], out["needs_review"]))
md.append("## 批次与验收\n")
md.append("- 建议批次顺序：%s。地标先跑，按各自正典核验建筑形态与水体关系，不统一套用单塔；片区最后跑，因其视野最广、最容易把不该看见的湖面塞进背景。" % "→".join(BATCH_ORDER))
md.append("- 验收以条目自身的【锁定与禁则】为准，通用否决项为：曲面扭转塔、湖中建塔、把L007的非对称直线斜削冠与细针状天线安到别的塔楼上、第二个机场、海港或大型人工岛、可读的招牌字形或凭空文字（招牌、灯箱、门牌必须存在，字形须是不可读的模糊笔画，这一项只否决「可读」）、出成照片质感（毛孔、镜头噪点、景深颗粒）或干净CG渲染（表面无过渡层次、高光呈均匀塑料感）、描边加平涂色阶的动画档、飞行汽车或全息投影一类近未来符号、第三方台标或渠道logo水印（模型侧带出的「LibTV」一类标记）、把湖面强塞进山外村镇背景、背景天际线画进本条【取景指令】未逐一点名的塔楼或超高层群。200米以上的塔楼在扩容后已成簇，成簇是正典事实而不是本条画面的授权，按名录逐栋核对高度与冠部，不再以「第二座超过200米的塔」作否决，但未被取景段点名的塔出现在背景里即属越权入画；这一项按能否读出专属形制记号分两档判读（C125）：未点名体量上出现非对称斜削冠、细针状天线、桅杆或斜拉索上段、冠部开洞、扭转塔身任一记号即判废，只读得出平头板楼、阶梯退台或雾中无冠部细节的剪影时记备注、不单独判废——剪影不带记号，人工复看既对不到名录的某一栋，也无从判定它是否本就不该出现。屋面上的细竖杆按 C126 量着判而不是看着判：发丝状直杆且无横档、无格构、无灯球、无斜削面、无开洞，杆高不超过同屏可见塔身的十二分之一，读作避雷带或旗杆类构件、记备注；带上述任一记号，或杆高超过十二分之一，即按记号档判废。杆高与可见塔身一律用源码网格切片在源图像素上量（杆顶y、女儿墙y、前景遮断处y），两个数一并写进读数，不靠目测印象。塔吊同样按 C126 分工：立于街面施工围挡层、不与任何未点名远景塔冠绑定的吊机读作生活痕迹（tail 的生活痕迹清单明列 construction hoarding with a tower crane 为允许项），记备注；立于天际线远景带、与未点名体量同带的吊机判废。画面可读层数与本条锁定的层数不符只记备注、不单独判废：层数与米数只写在中文段，English tail 没有可数的单元，模型无从计数。平台按AIGC强制标识加的「Qoder AI生成」角标与图片XMP里的TC260元数据标识不属否决项，须原样保留，不得裁剪、遮盖或修补。")
md.append("- 人群核验以条目自身的【人群与烟火气】为准：先看本条详档人群段的具体描写，再看该类型的缺省人数档，二者冲突按详档。画面人物明显低于档位下限（空街、空场）或反过来形成盛大庆典、统一着装团体，均记为待复验；俯瞰与鸟瞰条不逐个数人，但地面必须看得出有人在走动。")
md.append("- 画风与双层核验：本批按半写实数字厚涂开图，笔触可辨、颜料层次读得出来、表面是画出来的（C122 曾把本档降到「平滑过渡、皮肤豁免笔触」，2026-11-09 的 C153 按在册风险条款回退到本档）；出成照片质感（毛孔、镜头噪点、景深颗粒）或干净CG渲染（表面无过渡层次、高光呈均匀塑料感、边缘像布尔运算）都不合格。同一张图必须同时读得出科技层与老城层且二者有物理接触——只有玻璃幕墙、只有仿古街、或两层各占一半却被广场绿地切断，一律记待复验。科技层按2010年代前沿的具名设施核对（%s），这些词逐条由生成器核回 312 条正文的承载体；LED媒体立面、光纤到楼箱与屋顶通信设备一类属表层材质词，按画面材质核对、不要求名录承载体。飞行汽车、载人无人机、全息投影、机器人服务员、自动驾驶车队一类近未来符号出现即判废。生活痕迹实体（晾晒、盆栽、卸货筐、摊贩热气、灯箱、非机动车停放、下棋的老人、接送孩子的家长、施工围挡与吊装、垃圾收集点、遛狗、积水倒影）每条至少三项，不足三项记待复验。" % ("、".join(TECH_CARRIER_WORDS),))
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
