# -*- coding: utf-8 -*-
"""住所锚与圈层的唯一推导。

住所锚＝整户月租（钛币）：D 取下属 R 的户均月租中位数，F 继承所属 D，S 用每平米月租×户均面积代理。
圈层：只有 20 个片区带 ring 字段，功能区继承父片区，聚落的 type 本身即圈层名。
被 build_costs.py 与 build_occupations.py 共用；产业就业正典里 64 个锚点必须与 dwelling_anchors() 逐项相等。
"""
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))['entries']
PRICING = json.loads((ROOT / '数据' / '参考房价租金.json').read_text(encoding='utf-8'))['records']
BY_ID = {e['id']: e for e in REGISTRY}
PRICE_BY_ID = {r['id']: r for r in PRICING}


def household_area_proxy():
    values = [r['typical_dwelling']['avg_unit_gross_floor_area_m2'] for r in PRICING if 'typical_dwelling' in r]
    return statistics.median(values)


def entry_ring(entry, by_id=None):
    if entry['type'] == '城市片区':
        return entry['ring']
    if entry['type'] == '功能区':
        return entry_ring(by_id[entry['parent']], by_id)
    return entry['type']


def district_anchors():
    """全部锚点：D 取其下属 R 的户均月租中位数；F 继承所属 D；S 用每平方米月租×户均面积代理。"""
    anchors = {}
    for d in [e for e in REGISTRY if e['type'] == '城市片区']:
        rents = [r['typical_dwelling']['monthly_rent_tt'] for r in PRICING
                 if r.get('parent') == d['id'] and 'typical_dwelling' in r]
        anchors[d['id']] = round(statistics.median(rents), 1)
    for f in [e for e in REGISTRY if e['type'] == '功能区']:
        anchors[f['id']] = anchors[f['parent']]
    proxy = household_area_proxy()
    for s in [e for e in REGISTRY if e['id'].startswith('S')]:
        anchors[s['id']] = round(PRICE_BY_ID[s['id']]['residential']['rent_tt_per_m2_month'] * proxy, 1)
    return anchors


def dwelling_anchors():
    """只保留可作为岗位锚点的 64 区（40F＋24S）；D 键只作继承，不对外暴露。"""
    return {k: v for k, v in district_anchors().items() if k[0] in 'FS'}


RINGS = ('内湖环', '外城环', '产业小镇', '特色村落')


def pair_key(a, b):
    """无序圈层对的规范键名，按 RINGS 下标定先后，避免 A|B 与 B|A 两份键。"""
    return f'{a}|{b}' if RINGS.index(a) <= RINGS.index(b) else f'{b}|{a}'


def ring_pair_stats():
    """64 个 F／S 锚点两两直线距离的逐圈层对统计。交通固定耗时由它派生，门禁也按它复核。"""
    coords = {e['id']: e['center_km'] for e in REGISTRY if e['id'][0] in 'FS'}
    buckets = {}
    for key in coords:
        buckets.setdefault(entry_ring(BY_ID[key], BY_ID), []).append(key)
    out = {}
    for i, a in enumerate(RINGS):
        for b in RINGS[i:]:
            ds = []
            for x in buckets[a]:
                for y in buckets[b]:
                    if a != b and x >= y:
                        continue          # 跨圈层只取一份（400／320／160／128）
                    if x == y:
                        continue          # 同圈层保留 (x,y) 与 (y,x) 两份（380／240／56）
                    dx = coords[x][0] - coords[y][0]
                    dy = coords[x][1] - coords[y][1]
                    ds.append(math.hypot(dx, dy))
            med = statistics.median(ds)
            out[pair_key(a, b)] = {'锚点对数': len(ds), '中位直线km': round(med, 3),
                                   '最小km': round(min(ds), 3), '最大km': round(max(ds), 3),
                                   '最大偏差km': round(max(abs(d - med) for d in ds), 3)}
    return out
