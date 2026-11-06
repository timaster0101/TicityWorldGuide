# -*- coding: utf-8 -*-
"""G 裁定：景群成员可校验表 生成器
派生自 数据/城市空间名录.json
- 基线：5 条人工命名景群线（成员一字不动，来自 2026-10-31 设计文档 + C131）
- 派生：L061—L108 及全部标志性建筑按 focus 主题归群（C131 口径）
真源表落地为 数据/景群成员可校验表.json
"""
import json, io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
base = r"C:\Users\TIMASTER\Documents\Qoder\2026-10-29\c8c10ff8\钛湖城城市设定集"
data = os.path.join(base, "数据")

with open(os.path.join(data, "城市空间名录.json"), encoding="utf-8") as f:
    ml = json.load(f)
entries = ml.get("entries", [])
by_id = {e["id"]: e for e in entries}

# 全部标志性建筑
landmarks = [e for e in entries if e.get("type") == "标志性建筑"]
landmarks.sort(key=lambda e: e["id"])
l_ids = [e["id"] for e in landmarks]
print(f"名录标志性建筑总数: {len(l_ids)}")
# 校验连续无空号 L001-L108
import re
nums = sorted(int(re.sub(r'\D','',i)) for i in l_ids if i.startswith('L'))
nums = [n for n in nums if n <= 108]
expect = list(range(1,109))
missing = [f"L{n:03d}" for n in expect if n not in set(nums)]
extra = [n for n in nums if n not in expect]
print(f"L 编号: min={min(nums)} max={max(nums)}，缺号: {missing or '无'}，越界: {extra or '无'}")

# ---- 人工命名景群线（基线，一字不动）----
named_lines = [
    {"线": "JQ-L01", "线名": "钛湖八景", "归群依据": "人工命名(基线)", "成员": ["L001","L002","L003","L004","L005","L006","L007","L008"], "简介": "议事厅/司法馆/档案塔/大学图书馆/科学博物馆/青年交流馆/钛湖之脊/金融博物馆"},
    {"线": "JQ-L02", "线名": "湖湾生活线", "归群依据": "人工命名(基线)", "成员": ["L012","L016","L017","L018"], "简介": "沿湖湾生活服务主题地标"},
    {"线": "JQ-L03", "线名": "文教知识线", "归群依据": "人工命名(基线)", "成员": ["L003","L004","L005","L046"], "简介": "文教知识主题连线"},
    {"线": "JQ-L04", "线名": "文体活力线", "归群依据": "人工命名(基线)", "成员": ["L028","L029","L030","L047"], "简介": "文体活力主题连线"},
    {"线": "JQ-L05", "线名": "生态科普线", "归群依据": "人工命名(基线)", "成员": ["L031","L032","L033","L059","L060"], "简介": "生态科普主题连线"},
]

# ---- focus 主题派生景群线 ----
from collections import OrderedDict
focus_lines = OrderedDict()
for e in landmarks:
    f = e.get("focus") or "(未标注)"
    focus_lines.setdefault(f, []).append(e["id"])
derived_lines = []
for i, (focus, ids) in enumerate(focus_lines.items(), 1):
    derived_lines.append({
        "线": f"JQ-F{i:02d}",
        "线名": focus,
        "归群依据": "focus 主题派生(C131)",
        "成员": sorted(ids),
        "简介": f"{len(ids)} 条地标 · {focus}"
    })

table = {
    "version": "1.0",
    "fictional": True,
    "setting_year": 2013,
    "declaration": "本表是地点打卡景群套系的成员真源，派生自 数据/城市空间名录.json 的标志性建筑 focus 字段。JQ-L01—L05 为人工命名基线线（C131 裁定成员一字不动）；JQ-F 序列为按 focus 主题归群（L061—L108 全部并入景群维度）。成员 id 须真实存在于名录且 L 编号连续（L001—L108）。",
    "口径": "同一地标可同属人工命名线（展示用）与 focus 派生线（归群用），打卡一次两套并记；景群线奖励为整档固定分，不随对象数变；打卡仅登记事实、跨轮保留、不占卡牌继承名额、不设排名不影响数值判定。",
    "基线人工命名线数": len(named_lines),
    "focus主题线数": len(derived_lines),
    "景群线总数": len(named_lines)+len(derived_lines),
    "地标覆盖数": len(l_ids),
    "地标缺号": missing,
    "人工命名线": named_lines,
    "focus派生线": derived_lines,
}
out = os.path.join(data, "景群成员可校验表.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(table, f, ensure_ascii=False, indent=2)
print(f"\n已生成: {out}")
print(f"人工命名线 {len(named_lines)} 条, focus 派生线 {len(derived_lines)} 条, 共 {len(named_lines)+len(derived_lines)} 条")
print(f"地标覆盖 {len(l_ids)} 条, 缺号 {missing or '无'}")
print("\nfocus 派生线清单:")
for d in derived_lines:
    print(f"  {d['线']} [{d['线名']}] {len(d['成员'])}条: {d['成员']}")