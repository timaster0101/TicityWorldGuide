# -*- coding: utf-8 -*-
"""为钛湖城名录全部正典地点生成参考房价与参考租金（虚构设计参数，非真实市场数据）。条数不写死在本文件，以城市空间名录为准。"""
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
REG = json.loads((ROOT / "数据" / "城市空间名录.json").read_text(encoding="utf-8"))
ENTRIES = REG["entries"]
BYID = {e["id"]: e for e in ENTRIES}

BASE_HOME = 10000.0
BASE_OFFICE = 11500.0
BASE_SHOP = 12800.0
RING_HOME = {"内湖环": 1.32, "外城环": 0.82, "产业小镇": 0.40, "特色村落": 0.30}
RING_OFFICE = {"内湖环": 1.30, "外城环": 0.84, "产业小镇": 0.44, "特色村落": 0.32}
YIELD_HOME = {"内湖环": 0.0215, "外城环": 0.0255, "产业小镇": 0.0310, "特色村落": 0.0350}
YIELD_OFFICE = 0.0450
YIELD_SHOP = 0.0520
INNER_R = 5.8
OUTER_R = 10.2

# focus -> (居住吸引, 办公, 零售)
FOCUS = {
    "公共治理、法务与市民服务": (1.00, 1.02, 0.96),
    "大学、人文教育与公共知识": (1.04, 0.98, 1.02),
    "金融、专业服务与总部办公": (1.08, 1.16, 1.08),
    "会议、展览、旅游与商务接待": (1.00, 1.10, 1.10),
    "综合医疗、康复与健康研究": (1.02, 1.00, 0.98),
    "大众消费、家庭生活与社区服务": (1.06, 0.94, 1.12),
    "表演、电影、设计与夜间文化": (1.00, 1.02, 1.08),
    "地方历史、传统商业与手工艺": (1.02, 0.96, 1.10),
    "软件、人工智能应用与数字内容": (1.04, 1.12, 1.00),
    "竞技体育、全民运动与户外休闲": (1.02, 0.90, 0.98),
    "森林门户、自然教育与低密居住": (1.08, 0.86, 0.92),
    "基础科研、精密实验与人才生活": (1.00, 1.06, 0.92),
    "铁路换乘、区域商务与物流调度": (0.96, 1.08, 1.04),
    "精密制造、工业设计与清洁装配": (0.94, 0.98, 0.92),
    "城市应急、维修、回收与生活保障": (0.90, 0.88, 0.90),
    "大规模成熟居住与基础公共服务": (1.05, 0.92, 1.06),
    "食品研发、城市农业与生鲜供应": (0.98, 0.92, 1.00),
    "批零贸易、修配与区域商贸": (0.95, 1.00, 1.08),
    "清洁能源调度、储能研发与绿色生活": (0.94, 0.96, 0.90),
    "水资源管理、净水、监测与滨水教育": (0.92, 0.90, 0.88),
    "水稻、种业与农业服务": (1.00, 0.86, 0.96),
    "民用航空、维修培训与区域机场": (0.92, 1.04, 0.94),
    "半导体测试、传感器与机器人研发": (1.02, 1.10, 0.92),
    "高山茶、茶器与茶文化旅游": (1.04, 0.86, 1.06),
    "竹木材料、家具与低碳构件": (0.98, 0.88, 0.94),
    "温泉康复、养老与护理培训": (1.06, 0.90, 1.00),
    "光伏、储能维护与能源培训": (0.94, 0.96, 0.88),
    "影视拍摄、布景与后期制作": (1.00, 1.00, 1.04),
    "山地运动、救援与自然导览": (1.02, 0.84, 0.98),
    "陶瓷、玻璃工艺与小型工作室": (0.98, 0.94, 1.02),
    "花卉苗木、景观培育与园艺教育": (1.02, 0.86, 0.96),
    "粮油加工、冷链与食品质量检测": (0.96, 0.98, 1.00),
    "功能纺织、服装设计与再生纤维": (0.96, 0.96, 1.02),
    "区域贸易、仓配与维修服务": (0.98, 1.02, 1.10),
    "上游水源保护、仪器监测与环境教育": (0.94, 0.88, 0.88),
    "再制造、材料回收与维修教育": (0.90, 0.92, 0.90),
    "小规模淡水养殖、渔食与湿地管护": (1.00, 0.80, 0.96),
    "果园、蜂业与季节采摘": (1.02, 0.80, 0.98),
    "古道服务、杉木修复与山地客栈": (1.04, 0.82, 1.04),
    "小规模山地乳畜、草地维护与乳品直售": (0.98, 0.80, 0.94),
    "河运记忆、艇修与水岸手作": (1.02, 0.82, 1.02),
    "食用菌、林下经济与山货合作社": (0.98, 0.80, 0.96),
    "天文教育、气象观测与暗夜民宿": (1.02, 0.86, 1.00),
    "湿地保育、芦苇编织与生态导览": (1.00, 0.80, 0.98),
}

# 地标可交易用途仅按显式 ID 裁定；其余为公共自用，绝不按名称猜用途。
USE_BY_ID = {
    "L007": "办公", "L009": "办公", "L025": "办公", "L034": "办公",
    "L038": "办公", "L040": "办公", "L055": "办公",
    "L010": "商业", "L011": "商业", "L012": "商业", "L016": "商业",
    "L017": "商业", "L023": "商业", "L052": "商业",
    # 天际线扩容的 48 条同样逐个显式裁定，其余 14 条按默认走公共自用。
    "L061": "办公", "L063": "办公", "L066": "办公", "L067": "办公", "L068": "办公",
    "L069": "办公", "L070": "办公", "L071": "办公", "L072": "办公", "L073": "办公",
    "L076": "办公", "L080": "办公", "L082": "办公", "L083": "办公", "L084": "办公",
    "L085": "办公", "L086": "办公", "L091": "办公", "L092": "办公", "L093": "办公",
    "L096": "办公", "L102": "办公", "L103": "办公", "L107": "办公",
    "L065": "商业", "L074": "商业", "L075": "商业", "L079": "商业", "L081": "商业",
    "L089": "商业", "L094": "商业", "L101": "商业", "L104": "商业", "L105": "商业",
}
COMMERCIAL_ZONE_IDS = {"F008", "F016"}


def ring_key(entry):
    t = entry["type"]
    if t == "产业小镇":
        return "产业小镇"
    if t == "特色村落":
        return "特色村落"
    if entry.get("ring"):
        return entry["ring"]
    p = BYID.get(entry.get("parent"))
    if p and p.get("ring"):
        return p["ring"]
    return "内湖环" if entry["distance_to_lake_center_km"] <= INNER_R else "外城环"


def lake_factor(entry, rk):
    if rk in ("产业小镇", "特色村落"):
        return 1.0, "外围村镇与主城之间有山体遮挡，按设定不透山见湖，不计湖景溢价"
    d = entry["distance_to_lake_center_km"]
    if rk == "内湖环":
        f = 1 + 0.42 * max(0.0, 1 - d / INNER_R)
        note = "内湖环湖景衰减，距湖心%.2f千米" % d
    else:
        f = 1 + 0.18 * max(0.0, 1 - (d - INNER_R) / (OUTER_R - INNER_R))
        note = "外城环远湖衰减，距湖心%.2f千米" % d
    return round(f, 4), note


def far_band(far):
    if far is None:
        return 1.0, "无容积率"
    for hi, f in ((0.45, 1.10), (0.75, 1.05), (1.05, 1.00), (1.40, 0.96), (9.9, 0.92)):
        if far < hi:
            return f, "容积率%.3f分档" % far
    return 1.0, "无容积率"


def height_band(h):
    if not h:
        return 1.0
    if h >= 90:
        return 1.04
    if h >= 60:
        return 1.02
    if h <= 18:
        return 1.03
    return 1.0


def kids(pid):
    return [e for e in ENTRIES if e.get("parent") == pid]


def district_features(d):
    """片区直接子项岗位与总建筑量、片区人口：就业0.90—1.18，成熟度1.00—1.10。"""
    jobs = sum(k.get("daily_workers") or 0 for k in kids(d["id"]))
    gfa = sum(k.get("gross_floor_area_m2") or 0 for k in kids(d["id"]))
    pop = d.get("population") or 0
    return jobs, gfa, pop


ALL_JOBS = {}
ALL_GFA = {}
ALL_POP = {}
for _d in [e for e in ENTRIES if e["type"] == "城市片区"]:
    _j, _g, _p = district_features(_d)
    ALL_JOBS[_d["id"]] = _j
    ALL_GFA[_d["id"]] = _g
    ALL_POP[_d["id"]] = _p
MAXJ = max(ALL_JOBS.values())
MINJ = min(ALL_JOBS.values())
MAXG = max(ALL_GFA.values())
MING = min(ALL_GFA.values())
MAXP = max(ALL_POP.values())
MINP = min(ALL_POP.values())
VPOP = [e.get("population") or 0 for e in ENTRIES if e["type"] in ("产业小镇", "特色村落")]
MINV, MAXV = min(VPOP), max(VPOP)


def norm(v, lo, hi, a, b):
    if hi == lo:
        return round((a + b) / 2, 4)
    return round(a + (v - lo) / (hi - lo) * (b - a), 4)


def parent_of(entry):
    pid = entry.get("parent")
    return BYID.get(pid) if pid not in (None, "CITY", "REGION") else None


def money(v, step=50):
    return int(round(v / step) * step)


def r1(v):
    return round(v, 1)


records = []
far_all = [e["floor_area_ratio"] for e in ENTRIES if e.get("floor_area_ratio")]
MED_FAR = median(far_all)

for e in ENTRIES:
    rk = ring_key(e)
    lf, lnote = lake_factor(e, rk)
    fam, offm, retm = FOCUS[e["focus"]]
    p = parent_of(e)
    pid = p["id"] if p else e["id"]
    jobs = ALL_JOBS.get(pid) or 0
    gfa = ALL_GFA.get(pid) or 0
    pop = ALL_POP.get(pid) or 0
    # D 使用自身汇总特征，R/F/L 使用所属 D；S 仍走聚落分支。
    if pid in ALL_JOBS:
        job_f = norm(jobs, MINJ, MAXJ, 0.90, 1.18)
        scale_f = 1 + 0.06 * norm(gfa, MING, MAXG, 0.0, 1.0) + 0.04 * norm(pop, MINP, MAXP, 0.0, 1.0)
        scale_f = round(scale_f, 4)
    else:
        job_f = 1.0
        scale_f = 1.0
    basis = {
        "基准单价_钛币每平方米": {"住宅": BASE_HOME, "办公": BASE_OFFICE, "商业": BASE_SHOP},
        "毛租金收益率": {"住宅": YIELD_HOME[rk], "办公": YIELD_OFFICE, "商业": YIELD_SHOP},
        "圈层": rk,
        "圈层系数_home": RING_HOME[rk],
        "圈层系数_office": RING_OFFICE[rk],
        "湖景系数": lf,
        "湖景说明": lnote,
        "功能系数": {"居住": fam, "办公": offm, "零售": retm},
        "就业拉力系数": job_f,
        "片区成熟度系数": scale_f,
        "距湖心千米": e["distance_to_lake_center_km"],
    }
    if e["type"] in ("产业小镇", "特色村落"):
        vpop = e.get("population") or 0
        basis["聚落规模系数"] = norm(vpop, MINV, MAXV, 0.94, 1.10)
        basis["建成率"] = e.get("built_up_ratio")
    rec = {
        "id": e["id"],
        "name": e["name"],
        "type": e["type"],
        "parent": e.get("parent"),
        "parent_name": e.get("parent_name") or ("主城区" if e.get("parent") == "CITY" else "山外围区域"),
        "ring": rk,
        "focus": e["focus"],
        "center_km": e["center_km"],
        "area_km2": e["area_km2"],
    }

    if e["type"] == "居民区":
        df, dnote = far_band(e.get("floor_area_ratio"))
        hf = height_band(e.get("height_limit_m"))
        v = BASE_HOME * RING_HOME[rk] * lf * fam * job_f * scale_f * df * hf
        if e["type"] == "居民区" and rk in ("产业小镇", "特色村落"):
            v *= basis.get("聚落规模系数", 1.0)
        sale = money(v)
        rent = r1(sale * YIELD_HOME[rk] / 12)
        g_per_hh = e["gross_floor_area_m2"] / e["households"]
        rec["residential"] = {
            "sale_tt_per_m2": sale,
            "rent_tt_per_m2_month": rent,
            "gross_yield": YIELD_HOME[rk],
            "caliber": "建筑面积口径的梯度参考均价；住宅只登记使用权益，售价不开放产权、买卖、过户与税费，运行层可执行口径只有租赁",
        }
        shop_sale = money(BASE_SHOP * RING_HOME[rk] * lf * retm * job_f * 0.92)
        rec["street_retail"] = {
            "sale_tt_per_m2": shop_sale,
            "rent_tt_per_m2_day": r1(shop_sale * YIELD_SHOP / 365),
            "caliber": "底层临街商铺，40至80平方米开间，按建筑面积计",
        }
        rec["typical_dwelling"] = {
            "households": e["households"],
            "avg_unit_gross_floor_area_m2": round(g_per_hh),
            "total_price_tt": money(v * g_per_hh, 10000),
            "monthly_rent_tt": int(round(rent * g_per_hh, 0)),
            "note": "以名录总建筑面积作户均面积代理估算，未剔除配套等非住宅面积；不定义套内面积与得房率。户均总价只作地段梯度叙事，住宅不逐套分配、不开放买卖，可执行口径只有月租金",
        }
        basis["底商系数"] = 0.92
        basis["密度系数"] = df
        basis["密度说明"] = dnote
        basis["限高系数"] = hf
        basis["限高_m"] = e.get("height_limit_m")

    elif e["type"] in ("产业小镇", "特色村落"):
        vf = basis["聚落规模系数"]
        sale = money(BASE_HOME * RING_HOME[rk] * fam * vf)
        rent = r1(sale * YIELD_HOME[rk] / 12)
        rec["residential"] = {
            "sale_tt_per_m2": sale,
            "rent_tt_per_m2_month": rent,
            "gross_yield": YIELD_HOME[rk],
            "caliber": "聚落规划边界内的成套住宅梯度参考均价（含自建房改造、集体宿舍与小型院落住宅混合口径）；售价只作地段梯度叙事，住宅只登记使用权益",
        }
        shop_sale = money(BASE_SHOP * RING_HOME[rk] * retm * vf * 0.90)
        rec["street_retail"] = {
            "sale_tt_per_m2": shop_sale,
            "rent_tt_per_m2_day": r1(shop_sale * YIELD_SHOP / 365),
            "caliber": "镇区主街一层铺面，含前店后宅与文旅手作铺位",
        }
        basis["底商系数"] = 0.90
        basis["湖景系数"] = 1.0

    else:
        # 办公、商业独立按模型计算；D 住宅待所有 R 定价完成后汇总。
        basis["办公湖景系数"] = 1 + (lf - 1) * 0.5
        basis["办公高度系数"] = 1.0
        basis["办公地标系数"] = 1.0
        off_sale = money(BASE_OFFICE * RING_OFFICE[rk] * (1 + (lf - 1) * 0.5) * offm * job_f * scale_f)
        if e["type"] == "标志性建筑" and (e.get("height_m") or 0) >= 90:
            off_sale = money(off_sale * 1.10)
            basis["办公高度系数"] = 1.10
        if e["id"] == "L007":
            off_sale = money(off_sale * 1.25)
            basis["办公地标系数"] = 1.25
        rec["office"] = {
            "sale_tt_per_m2": off_sale,
            "rent_tt_per_m2_day": r1(off_sale * YIELD_OFFICE / 365),
            "caliber": "办公模型基准参考价，建筑面积口径，含公摊；未按真实甲乙级物业组合加权",
        }
        ret_sale = money(BASE_SHOP * RING_HOME[rk] * lf * retm * job_f * scale_f)
        rec["retail"] = {
            "sale_tt_per_m2": ret_sale,
            "rent_tt_per_m2_day": r1(ret_sale * YIELD_SHOP / 365),
            "caliber": "首层商业模型基准参考价，建筑面积口径；未按真实物业组合加权",
        }
        if e["type"] == "功能区":
            df, dnote = far_band(e.get("floor_area_ratio"))
            z_sale = money(BASE_HOME * RING_HOME[rk] * lf * fam * job_f * scale_f * df)
            rec["residential"] = {
                "sale_tt_per_m2": z_sale,
                "rent_tt_per_m2_month": r1(z_sale * YIELD_HOME[rk] / 12),
                "gross_yield": YIELD_HOME[rk],
                "caliber": "功能区内配套住宅模型参考价，非样本加权；纯产业与市政型功能区仅供周边居住对照，住宅只登记使用权益",
            }
            basis["密度系数"] = df
            basis["密度说明"] = dnote
        if e["type"] == "标志性建筑":
            use = USE_BY_ID.get(e["id"], "公共自用")
        else:
            use = "商业" if e["id"] in COMMERCIAL_ZONE_IDS else "混合"
        rec["asset_use"] = use
        rec["reference_only"] = use == "公共自用"
        rec["note"] = (
            "自用公共物业，产权不进入市场交易；表内价格为同一地块功能组合下的可交易物业参考价"
            if rec["reference_only"]
            else "按主要可交易用途取对应模型参考价，不代表真实物业组合均价"
        )
        basis["岗位规模"] = e.get("daily_workers")
    rec["basis"] = basis
    records.append(rec)

# 只对已列精选住区样本加权：名录总 GFA 是代理权重，不假定未知住宅净面积。
PRICE_BY_ID = {r["id"]: r for r in records}
for rec in records:
    if rec["type"] == "城市片区":
        samples = sorted((e for e in kids(rec["id"]) if e["type"] == "居民区"), key=lambda e: e["id"])
        total_gfa = sum(e["gross_floor_area_m2"] for e in samples)
        if total_gfa > 0:
            sale = money(sum(PRICE_BY_ID[e["id"]]["residential"]["sale_tt_per_m2"]
                             * e["gross_floor_area_m2"] for e in samples) / total_gfa)
            rec["residential"] = {
                "sale_tt_per_m2": sale,
                "rent_tt_per_m2_month": r1(sale * YIELD_HOME[rec["ring"]] / 12),
                "gross_yield": YIELD_HOME[rec["ring"]],
                "sample_ids": [e["id"] for e in samples],
                "sample_weight_gfa_m2": total_gfa,
                "caliber": "已列精选住区住宅样本参考价，以名录 gross_floor_area_m2 总建筑面积作代理权重；"
                           "未拆分住宅净面积，非全片区住宅普查均价，不直接定价单栋；"
                           "住宅只登记社区配额与使用权益，售价不进入交易",
            }
    rec["scope"] = [label for key, label in (("office", "办公"), ("retail", "商业"),
                                             ("residential", "住宅"), ("street_retail", "底商")) if key in rec]

out = {
    "version": "1.0",
    "fictional": True,
    "setting_year": 2013,
    "currency": "TT",
    "currency_name": "钛币",
    "declaration": (
        "本文件是虚构城市钛湖城的定价设计参数，用于让AI在生成图片、视频与文字时保持同一地理与经济梯度。"
        "全城唯一计价单位为虚构货币“钛币”（缩写TT），不与任何现实货币挂钩、不设兑换比率，表内数字一律按钛币读。"
        "它不是真实房地产市场数据，不构成任何估价、投资或交易依据。"
        "住宅列只登记使用权益，运行层不开放住宅产权、买卖、过户、税费与产权继承；"
        "住宅“售价”仅用于呈现地段梯度与生活水平叙事，不是可执行动作。"
    ),
    "caliber": {
        "计价单位": "钛币（TT）每平方米建筑面积，表内数字省略单位后缀",
        "住宅售价": "钛币每平方米建筑面积，毛坯口径均价，运行层不可执行",
        "住宅租金": "钛币每平方米建筑面积每月",
        "办公售价": "钛币每平方米建筑面积，独立模型基准参考，非真实物业等级组合加权",
        "办公租金": "钛币每平方米建筑面积每天",
        "商业售价": "钛币每平方米建筑面积，首层模型基准参考，非真实物业组合加权",
        "商业租金": "钛币每平方米建筑面积每天",
        "面积口径": "一律为建筑面积；住区总 GFA 用作样本权重与户均面积代理，不定义未知住宅净面积",
    },
    "model": {
        "住宅基准": BASE_HOME,
        "办公基准": BASE_OFFICE,
        "商业基准": BASE_SHOP,
        "圈层系数": RING_HOME,
        "办公圈层系数": RING_OFFICE,
        "毛租金收益率": {"住宅_内湖环": YIELD_HOME["内湖环"], "住宅_外城环": YIELD_HOME["外城环"],
                          "住宅_产业小镇": YIELD_HOME["产业小镇"], "住宅_特色村落": YIELD_HOME["特色村落"],
                          "办公": YIELD_OFFICE, "商业": YIELD_SHOP},
        "湖景衰减": "内湖环 1+0.42*(1-d/5.8)，外城环 1+0.18*(1-(d-5.8)/4.4)，外围村镇恒为1.0",
        "就业拉力": "片区直接子项岗位总数线性映射到0.90—1.18；D自身与所属R/F/L共用，S不用",
        "成熟度": "片区直接子项总建筑量与片区人口映射到1.00—1.10；D自身与所属R/F/L共用，S不用",
        "密度分档": "容积率低于0.45得1.10，依次递减到1.40以上的0.92",
        "限高分档": "居民区限高90米及以上1.04，60米及以上1.02，18米及以下1.03",
        "片区住宅": "所有R定价后按名录gross_floor_area_m2加权已列精选住区售价，再按50钛币取整；非全片区住宅普查均价",
        "办公加成": "先将模型办公价按50钛币取整，L实际高度>=90米再乘1.10并取整，L007再乘1.25并取整",
        "取整": "沿用Python round最近偶数规则；售价50钛币一档，租金保留一位小数",
    },
    "record_count": len(records),
    "records": records,
}
(ROOT / "数据" / "参考房价租金.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def band(rows, key, sub):
    v = sorted(r[key][sub] for r in rows if r.get(key))
    return v[0], v[len(v) // 2], v[-1]


groups = [
    ("居民区", [r for r in records if r["type"] == "居民区"]),
    ("写字楼（可交易办公资产，专项检索）", [r for r in records if r.get("asset_use") == "办公"]),
    ("商业区（购物中心、街区商业与临街铺面，专项检索）",
     [r for r in records if r.get("asset_use") == "商业"]),
    ("城市功能区（混合用途整体参考）", [r for r in records if r["type"] == "功能区"]),
    ("城市片区（住宅为精选住区样本，办公商业为模型参考）", [r for r in records if r["type"] == "城市片区"]),
    ("自用公共物业（参考价，不进入交易）",
     [r for r in records if r.get("asset_use") == "公共自用"]),
    ("外围产业小镇", [r for r in records if r["type"] == "产业小镇"]),
    ("外围特色村落", [r for r in records if r["type"] == "特色村落"]),
]
md = ["# 钛湖城参考房价与租金总表（虚构设定，2013年基准，钛币计价）\n"]
md.append("全部数字为AI生成用的经济梯度设计参数，不是真实市场数据，不可用于估价或交易。计价单位为虚构货币钛币（缩写TT），全城唯一，不与任何现实货币换算。住宅为钛币每平方米建筑面积（售价、每月租金），办公与商业为钛币每平方米建筑面积（售价、每天租金）。\n")
md.append("住宅只有租赁与保障分配两种取得方式，运行层只登记社区配额与使用权益：不开放住宅产权、买卖、过户、税费与产权继承，因此表内住宅“售价”只用于呈现地段梯度与生活水平叙事，不是可执行动作。办公与商业资产按卡牌登记，可交易。\n")
md.append("城市片区住宅价仅按已列精选住区的总GFA代理权重汇总，不是全片区住宅普查均价，也未拆分未知住宅净面积；样本ID和权重总面积见逐条JSON。办公与商业为独立模型基准参考，不按真实物业等级组合加权。\n")
_type_counts = {}
for _r in records:
    _type_counts[_r["type"]] = _type_counts.get(_r["type"], 0) + 1
md.append("标注“专项检索”的两节按主要可交易用途从全表中挑出，与后面的功能区、片区全量表存在交叉，不是把条目数加总。%d条的正体分组为：%s。" % (
    len(records), "、".join("%s%d" % (t, _type_counts[t]) for t in ("居民区", "标志性建筑", "功能区", "城市片区", "产业小镇", "特色村落"))))
for title, rows in groups:
    if not rows:
        continue
    md.append("\n## %s（%d条）\n" % (title, len(rows)))
    md.append("| ID | 名称 | 类型 | 所属 | 距湖心 km | 住宅售价 | 住宅租金 钛币/㎡/月 | 办公售价 | 办公租金 钛币/㎡/天 | 商业售价 | 商业租金 钛币/㎡/天 |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: -(x.get("residential") or x.get("office"))["sale_tt_per_m2"]):
        h = r.get("residential") or {}
        o = r.get("office") or {}
        s = r.get("retail") or r.get("street_retail") or {}
        md.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["id"], r["name"], r["type"], r["parent_name"], r["basis"]["距湖心千米"],
            h.get("sale_tt_per_m2", "—"), h.get("rent_tt_per_m2_month", "—"),
            o.get("sale_tt_per_m2", "—"), o.get("rent_tt_per_m2_day", "—"),
            s.get("sale_tt_per_m2", "—"), s.get("rent_tt_per_m2_day", "—")))
    md.append("")
allh = [r for r in records if r.get("residential")]
lo, mid, hi = band(allh, "residential", "sale_tt_per_m2")
md.append("\n## 分布校验\n")
md.append("- 住宅售价覆盖%d条：最低%d、中位%d、最高%d 钛币每平方米。" % (len(allh), lo, mid, hi))
for rk in ("内湖环", "外城环", "产业小镇", "特色村落"):
    rows = [r for r in allh if r["ring"] == rk]
    a, b, c = band(rows, "residential", "sale_tt_per_m2")
    md.append("- %s：%d条，%d—%d 钛币每平方米，中位 %d。" % (rk, len(rows), a, c, b))
mo = [r for r in records if r.get("office")]
a, b, c = band(mo, "office", "sale_tt_per_m2")
md.append("- 办公售价覆盖%d条：%d—%d 钛币每平方米，中位 %d。最高价为钛湖之脊L007（368米地标溢价）。" % (len(mo), a, c, b))
ms = [r for r in records if r.get("retail")]
a, b, c = band(ms, "retail", "sale_tt_per_m2")
md.append("- 商业售价覆盖%d条：%d—%d 钛币每平方米，中位 %d。" % (len(ms), a, c, b))
md.append("- 外围24个村镇一律不计湖景溢价，因正典设定村镇与主城之间有山体遮挡、不能透山看到湖面。\n")
(ROOT / "数据" / "参考房价租金总表.md").write_text("\n".join(md), encoding="utf-8")
print("records", len(records), "home", len(allh), "office", len(mo), "retail", len(ms))
print("home band", lo, mid, hi)
print("L007", json.dumps([r for r in records if r["id"] == "L007"][0], ensure_ascii=False)[:400])
