# -*- coding: utf-8 -*-
"""第5期空间通行清单派生器：读 空间通行源表.json ＋ 名录水系几何，产出桥梁／渡位／航线／山口通道四张实算表。

手填只有构件端点坐标、渡位坐标、山门口与班线常数；跨度、方位、交角、水宽、湖内判定、
圈层对、盆界交点与固定耗时一律由本文件从 数据/城市空间名录.json 的湖椭圆与两条河流折线实算派生。
跑法：python 工具/build_spatial_lists.py [--out-dir DIR] [--print-checks]
"""
import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / '数据' / '空间通行源表.json'
if not SRC_PATH.exists():
    raise SystemExit('缺少 数据/空间通行源表.json：本期构件清单全部从它派生，不允许手填正典')
SOURCE = json.loads(SRC_PATH.read_text(encoding='utf-8'))
REGISTRY = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))
PARAMS_SRC = json.loads((ROOT / '数据' / '运行参数源表.json').read_text(encoding='utf-8'))

from anchors import entry_ring, pair_key

P = SOURCE['参数']
TOL = P['容差']
BY_ID = {e['id']: e for e in REGISTRY['entries']}
LAKE = REGISTRY['lake']
RIVERS = {r['id']: r for r in REGISTRY['rivers']}
BOX = REGISTRY['region_boundary_km']
FLOW_WINDOW_KM = 0.5


def ring_of(aid, where):
    e = BY_ID.get(aid)
    if e is None:
        raise SystemExit(f'{where} 引用了名录里没有的锚点 {aid}')
    return entry_ring(e, BY_ID), e


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def bearing(a, b):
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])) % 360.0


def acute_angle(x, y):
    r = abs(x - y) % 360.0
    if r > 180.0:
        r = 360.0 - r
    return r if r <= 90.0 else 180.0 - r


def lake_f(point):
    x, y = point
    return (x / LAKE['east_west_semiaxis_km']) ** 2 + (y / LAKE['north_south_semiaxis_km']) ** 2


class Polyline:
    """名录河流折线的弧长参数化：投影、局部流向与沿程水宽都由它实算。"""

    def __init__(self, river):
        self.river = river
        self.pts = river['centerline_km']
        self.cum = [0.0]
        for i in range(len(self.pts) - 1):
            self.cum.append(self.cum[-1] + dist(self.pts[i], self.pts[i + 1]))
        self.total = self.cum[-1]

    def project(self, point):
        best = None
        for i in range(len(self.pts) - 1):
            a, b = self.pts[i], self.pts[i + 1]
            vx, vy = b[0] - a[0], b[1] - a[1]
            t = max(0.0, min(1.0, ((point[0] - a[0]) * vx + (point[1] - a[1]) * vy) / (vx * vx + vy * vy)))
            d = dist((point[0], point[1]), (a[0] + t * vx, a[1] + t * vy))
            if best is None or d < best[0]:
                best = (d, self.cum[i] + math.hypot(vx, vy) * t, (a[0] + t * vx, a[1] + t * vy))
        return best

    def at(self, arc):
        s = max(0.0, min(self.total, arc))
        for i in range(len(self.pts) - 1):
            seg = self.cum[i + 1] - self.cum[i]
            if s <= self.cum[i + 1] or i == len(self.pts) - 2:
                a, b = self.pts[i], self.pts[i + 1]
                t = (s - self.cum[i]) / seg
                return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    def width_m(self, arc):
        lo, hi = self.river['width_m']
        return lo + (arc / self.total) * (hi - lo)

    def local_flow_deg(self, arc):
        return bearing(self.at(max(0.0, arc - FLOW_WINDOW_KM)), self.at(min(self.total, arc + FLOW_WINDOW_KM)))


POLYS = {k: Polyline(v) for k, v in RIVERS.items()}


def river_at(poly, code, point):
    d, arc, foot = poly.project(point)
    if d * 1000 > TOL['轴线距上限米']:
        raise SystemExit(f'{code} 桥头中点离 {poly.river["id"]} 轴线 {d * 1000:.0f} 米，'
                         f'超过容差 {TOL["轴线距上限米"]} 米——桥位没跨在河道上')
    return dict(轴线距m=round(d * 1000, 1), 投影弧km=round(arc, 3), 投影点km=[round(x, 3) for x in foot],
                实测水宽m=round(poly.width_m(arc), 1), 局部流方位deg=round(poly.local_flow_deg(arc), 1))


def bank_side(poly, arc, foot, point):
    deg = math.radians(poly.local_flow_deg(arc))
    ux, uy = math.sin(deg), math.cos(deg)
    return (point[0] - foot[0]) * uy - (point[1] - foot[1]) * ux


def check_unique(codes, what):
    if len(set(codes)) != len(codes):
        raise SystemExit(f'{what}编号重复：{sorted(c for c in set(codes) if codes.count(c) > 1)}')


def check_params_同源():
    sp = PARAMS_SRC['参数']['交通']
    deferred = [m['码'] for m in sp['延后方式']]
    outside = {m['码']: m for m in sp.get('矩阵外方式', [])}
    for code in ('TR-FERRY', 'TR-SHUTTLE'):
        if code in deferred:
            raise SystemExit(f'第4期延后方式里还有 {code}：本期清单已落定，应改登记进 矩阵外方式')
        if code not in outside:
            raise SystemExit(f'第4期矩阵外方式缺 {code}：轮渡与山口接驳的耗时由本表逐构件给出，必须挂上来源')
    if 'TR-AIR' not in deferred:
        raise SystemExit('TR-AIR 不在延后方式里：名录内没有城内机场构件，本期不推翻这条读数')


def build_bridges():
    rows = []
    for br in P['桥梁']:
        code = br['码']
        if br['跨越'] not in RIVERS:
            raise SystemExit(f'{code} 跨越的水系码 {br["跨越"]} 不在名录水地里')
        poly = POLYS[br['跨越']]
        a, b = br['桥头A_km'], br['桥头B_km']
        mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
        geo = river_at(poly, code, mid)
        span_km = dist(a, b)
        axis = bearing(a, b)
        cross = acute_angle(axis, geo['局部流方位deg'])
        if cross < 90.0 - TOL['桥轴与流向正交容差度']:
            raise SystemExit(f'{code} 桥轴 {axis:.1f}° 与局部流向 {geo["局部流方位deg"]:.1f}° 的交角只有 '
                             f'{cross:.1f}°，斜穿河道')
        ratio = span_km * 1000 / geo['实测水宽m']
        if not TOL['跨度下限倍数水宽'] <= ratio <= TOL['跨度上限倍数水宽']:
            raise SystemExit(f'{code} 跨度 {span_km * 1000:.0f} 米是实测水宽 {geo["实测水宽m"]:.1f} 米的 '
                             f'{ratio:.2f} 倍，不在 [{TOL["跨度下限倍数水宽"]}, {TOL["跨度上限倍数水宽"]}] 内')
        sa, ta = br['连接A'], br['连接B']
        ring_a, ea = ring_of(sa, f'{code} 连接A')
        ring_b, eb = ring_of(ta, f'{code} 连接B')
        reach = (dist(mid, ea['center_km']), dist(mid, eb['center_km']))
        for nm, ring, got in ((sa, ring_a, reach[0]), (ta, ring_b, reach[1])):
            if got > TOL['锚点可达半径上限千米'][ring]:
                raise SystemExit(f'{code} 桥位到 {nm} 中心 {got:.2f} 千米，超过{ring}可达上限 '
                                 f'{TOL["锚点可达半径上限千米"][ring]} 千米——这座桥服务不到它声称的锚点')
        fmin = min(lake_f([a[0] + (b[0] - a[0]) * i / 200, a[1] + (b[1] - a[1]) * i / 200]) for i in range(201))
        if fmin < TOL['湖内判据下限']:
            raise SystemExit(f'{code} 构件线段进入钛湖椭圆内部（最小归一化值 {fmin:.3f}）：湖心不架桥，跨湖只走客渡')
        arc, foot = geo['投影弧km'], geo['投影点km']
        sides = bank_side(poly, arc, foot, a) * bank_side(poly, arc, foot, b) < 0
        if not sides:
            raise SystemExit(f'{code} 两个桥头落在 {br["跨越"]} 轴线同侧，不是跨河构件')
        rows.append(dict(码=code, 名=br['名'], 类=br['类'], 跨越=br['跨越'], 水系名=RIVERS[br['跨越']]['name'],
                         桥头A_km=a, 桥头B_km=b, 跨度km=round(span_km, 3), 跨度m=round(span_km * 1000, 1),
                         桥轴方位deg=round(axis, 1), 湖内最小f=round(fmin, 2), 穿湖=False,
                         连接A=sa, 连接A名=ea['name'], A圈层=ring_a, 连接B=ta, 连接B名=eb['name'], B圈层=ring_b,
                         圈层对=pair_key(ring_a, ring_b), 可达A_km=round(reach[0], 2), 可达B_km=round(reach[1], 2),
                         **geo, 跨度水宽倍数=round(ratio, 2), 车道=br['车道'], 说明=br['说明']))
    check_unique([r['码'] for r in rows], '桥梁')
    return rows


def build_wharves():
    f = P['轮渡']
    rows = []
    for w in f['渡位']:
        code, near = w['码'], w['临']
        p = w['坐标km']
        row = dict(码=code, 名=w['名'], 临=near, 坐标km=p)
        if near == '湖':
            fv = lake_f(p)
            if abs(fv - 1.0) > TOL['湖岸椭圆贴合容差']:
                raise SystemExit(f'{code} 临湖渡位的湖椭圆归一化值 {fv:.4f}，偏离岸线超过 '
                                 f'{TOL["湖岸椭圆贴合容差"]}——码头得长在湖岸线上')
            row.update(湖岸f=round(fv, 4))
        else:
            if near not in RIVERS:
                raise SystemExit(f'{code} 临的水系码 {near} 不在名录水地里')
            poly = POLYS[near]
            d, arc, foot = poly.project(p)
            half = poly.width_m(arc) / 2
            over = d * 1000 - half
            lo, hi = TOL['渡位贴岸余量区间米']
            if not lo <= over <= hi:
                raise SystemExit(f'{code} 离 {near} 轴线 {d * 1000:.0f} 米，水宽一半 {half:.1f} 米，'
                                 f'贴岸余量 {over:.0f} 米不在 [{lo}, {hi}] 内——要么落进航道，要么退上滩地')
            row.update(离轴m=round(d * 1000, 1), 实测水宽m=round(poly.width_m(arc), 1),
                       半宽m=round(half, 1), 贴岸余量m=round(over, 1))
        rows.append(row)
    check_unique([r['码'] for r in rows], '渡位')
    return rows


def build_routes(wharves):
    f = P['轮渡']
    c = f['系数与常数']
    wh = {r['码']: r for r in wharves}
    rows = []
    for fr in f['航线']:
        code = fr['码']
        for k in ('渡位A', '渡位B'):
            if fr[k] not in wh:
                raise SystemExit(f'{code} 的{k} {fr[k]} 不在渡位表内')
        a, b = wh[fr['渡位A']], wh[fr['渡位B']]
        if a['临'] != b['临']:
            raise SystemExit(f'{code} 两端渡位一临湖、一临河，不是一条航线')
        line = dist(a['坐标km'], b['坐标km'])
        seg_km = line * c['航道系数']
        step = c['取整分钟']
        minutes = math.ceil((seg_km / c['航速km_h'] * 60 + c['候船分钟']) / step) * step
        mid = [(a['坐标km'][0] + b['坐标km'][0]) / 2, (a['坐标km'][1] + b['坐标km'][1]) / 2]
        if a['临'] == '湖':
            if lake_f(mid) >= TOL['湖内判据下限']:
                raise SystemExit(f'{code} 湖航线中点不在钛湖椭圆内（f={lake_f(mid):.3f}）——航线没有走水面')
            过水 = '湖面'
        else:
            poly = POLYS[a['临']]
            _, arc, foot = poly.project(mid)
            if bank_side(poly, arc, foot, a['坐标km']) * bank_side(poly, arc, foot, b['坐标km']) >= 0:
                raise SystemExit(f'{code} 两端渡位在 {a["临"]} 同侧，不构成为跨河摆渡')
            过水 = RIVERS[a['临']]['name']
        ra, ea = ring_of(fr['服务A'], f'{code} 服务A')
        rb, eb = ring_of(fr['服务B'], f'{code} 服务B')
        reach = (dist(a['坐标km'], ea['center_km']), dist(b['坐标km'], eb['center_km']))
        for nm, ring, got in ((fr['服务A'], ra, reach[0]), (fr['服务B'], rb, reach[1])):
            if got > TOL['锚点可达半径上限千米'][ring]:
                raise SystemExit(f'{code} 渡位到服务锚点 {nm} {got:.2f} 千米，超过{ring}可达上限 '
                                 f'{TOL["锚点可达半径上限千米"][ring]} 千米')
        rows.append(dict(码=code, 名=fr['名'], 渡位A=fr['渡位A'], 渡位A名=a['名'], 渡位B=fr['渡位B'],
                         渡位B名=b['名'], 临=a['临'], 过水=过水, 直线km=round(line, 3), 航段km=round(seg_km, 3),
                         耗时分钟=minutes, 班次每日=fr['班次每日'],
                         服务A=fr['服务A'], 服务A名=ea['name'], A圈层=ra,
                         服务B=fr['服务B'], 服务B名=eb['name'], B圈层=rb, 圈层对=pair_key(ra, rb),
                         可达A_km=round(reach[0], 2), 可达B_km=round(reach[1], 2), 说明=fr['说明']))
    check_unique([r['码'] for r in rows], '航线')
    if not rows:
        raise SystemExit('轮渡航线为空：第6主题要求跨水靠既有桥梁与客渡，两者不能同时缺')
    return rows


def box_exit(a, b):
    """门户到山外讫点的射线首次穿出盆界矩形的落点。"""
    cands = []
    for j, (lo, hi) in enumerate(((BOX[0], BOX[2]), (BOX[1], BOX[3]))):
        for lim in (lo, hi):
            dj = b[j] - a[j]
            if abs(dj) < 1e-12:
                continue
            t = (lim - a[j]) / dj
            if 0.0 < t <= 1.0 + 1e-9:
                pt = [a[k] + (b[k] - a[k]) * t for k in range(2)]
                if BOX[0] - 1e-9 <= pt[0] <= BOX[2] + 1e-9 and BOX[1] - 1e-9 <= pt[1] <= BOX[3] + 1e-9:
                    cands.append((t, pt))
    if not cands:
        raise SystemExit('盆界交点算不出来：讫点没有从盆界内往外走')
    return min(cands)[1]


def build_passes():
    sp = P['山口通道']
    c = sp['接驳常数']
    kinds = {k['码']: k for k in sp['六类']}
    rows = []
    for pa in sp['通道']:
        code = pa['码']
        if pa['类'] not in kinds:
            raise SystemExit(f'{code} 的通道类 {pa["类"]} 不在六类字典内')
        kind = kinds[pa['类']]
        ring, gate = ring_of(pa['门户'], f'{code} 门户')
        p, q = gate['center_km'], pa['讫点km']
        if BOX[0] <= q[0] <= BOX[2] and BOX[1] <= q[1] <= BOX[3]:
            raise SystemExit(f'{code} 山外讫点 {q} 落在盆界矩形内，不是山外')
        near = min(dist(q, e['center_km']) for e in REGISTRY['entries'])
        if near < TOL['山外讫点离任一锚点下限千米']:
            raise SystemExit(f'{code} 山外讫点离最近名录锚点只有 {near:.2f} 千米：山外只给集散场称谓，不许造地点')
        line = dist(p, q)
        km = line * c['山路系数']
        step = c['取整分钟']
        minutes = math.ceil((km / c['速度km_h'] * 60 + c['站前等候分钟']) / step) * step if kind['载客'] else None
        ex = box_exit(p, q)
        dev = dist(ex, pa['声明盆界交点km'])
        if dev > TOL['盆界交点声明容差千米']:
            raise SystemExit(f'{code} 声明盆界交点 {pa["声明盆界交点km"]} 与实算 {tuple(round(x, 3) for x in ex)} '
                             f'相差 {dev:.3f} 千米，超过 {TOL["盆界交点声明容差千米"]} 千米——改名录盆界后须重测本行')
        if not kind['载客'] and (pa['班线每日'] or pa['票价_钛币']):
            raise SystemExit(f'{code} 属不载客类 {pa["类"]}，却登记了班线或票价')
        if kind['载客'] and pa['班线每日'] <= 0:
            raise SystemExit(f'{code} 属载客类 {pa["类"]}，班线每日必须大于 0')
        rows.append(dict(码=code, 名=pa['名'], 类=pa['类'], 类名=kind['名'], 载客=kind['载客'],
                         门户=pa['门户'], 门户名=gate['name'], 门户圈层=ring,
                         山外讫点=pa['山外讫点'], 讫点km=q, 直线km=round(line, 2), 里程km=round(km, 2),
                         耗时分钟=minutes, 盆界交点km=[round(x, 3) for x in ex],
                         声明盆界交点km=pa['声明盆界交点km'], 交点偏差km=round(dev, 3),
                         讫点离最近锚点km=round(near, 2), 班线每日=pa['班线每日'], 票价_钛币=pa['票价_钛币'],
                         说明=pa['说明']))
    check_unique([r['码'] for r in rows], '山口通道')
    for code in kinds:
        if code not in {r['类'] for r in rows}:
            raise SystemExit(f'六类山口字典里的 {code} 没有任何实例：第6主题承诺的六类通道不能只挂在字典上')
    return rows


def build_canon():
    check_params_同源()
    bridges = build_bridges()
    wharves = build_wharves()
    routes = build_routes(wharves)
    passes = build_passes()
    span_max = max(bridges, key=lambda r: r['跨度m'])
    canon = dict(SOURCE)
    canon['桥梁'] = bridges
    canon['渡位'] = wharves
    canon['轮渡航线'] = routes
    canon['山口通道'] = passes
    canon['汇总'] = {
        '桥梁数': len(bridges), '公路桥数': sum(1 for r in bridges if r['类'] == '公路'),
        '铁路桥数': sum(1 for r in bridges if r['类'] == '铁路'),
        '人行桥数': sum(1 for r in bridges if r['类'] == '人行'),
        '渡位数': len(wharves), '湖渡位数': sum(1 for r in wharves if r['临'] == '湖'),
        '河渡位数': sum(1 for r in wharves if r['临'] != '湖'),
        '航线数': len(routes), '山口数': len(passes), '山口类数': len(P['山口通道']['六类']),
        '载客山口数': sum(1 for r in passes if r['载客']),
        '最长跨度m': span_max['跨度m'], '最长跨度桥': span_max['码'],
        '最长航线km': max(r['航段km'] for r in routes),
        '最短航线km': min(r['航段km'] for r in routes),
        '航线耗时区间分钟': [min(r['耗时分钟'] for r in routes), max(r['耗时分钟'] for r in routes)],
        '山口里程区间km': [min(r['里程km'] for r in passes), max(r['里程km'] for r in passes)],
        '载客山口耗时区间分钟': [min(r['耗时分钟'] for r in passes if r['耗时分钟'] is not None),
                          max(r['耗时分钟'] for r in passes if r['耗时分钟'] is not None)],
        '穿湖桥数': sum(1 for r in bridges if r['穿湖']),
        '口径': '桥梁／渡位／航线／山口是通行构件事实，只参与「能不能到」的判定，不参与耗时覆写、天气降速或'
                '随机延误；耗时一律是零随机的固定查表值。四张表都不进第4期交通矩阵：矩阵按圈层对中位直线口径，'
                '与点对点构件的量级不可比。轮渡与山口接驳在第4期登记为矩阵外方式，逐构件读数看本表。',
    }
    return canon


def _cell(v):
    if v is None:
        return '—'
    if isinstance(v, bool):
        return '是' if v else '否'
    if isinstance(v, list):
        return '、'.join(str(x) for x in v)
    return str(v)


def _md(v):
    """圈层对键名里的 `|` 是表格分隔符，落到 markdown 单元格必须转义，否则一格被拆成两列。"""
    return _cell(v).replace('|', '\\|')


def render_table(canon):
    t = canon['参数']['容差']
    lines = ['# 空间通行总表', '',
             f'本文件由 `工具/build_spatial_lists.py` 生成，基准年 {canon["setting_year"]}，'
             '货币 钛币（TT），禁止手改。', '',
             f'规模：桥梁 {canon["汇总"]["桥梁数"]} 座（公路 {canon["汇总"]["公路桥数"]}、'
             f'铁路 {canon["汇总"]["铁路桥数"]}、人行 {canon["汇总"]["人行桥数"]}）；'
             f'渡位 {canon["汇总"]["渡位数"]} 个（湖 {canon["汇总"]["湖渡位数"]}、河 {canon["汇总"]["河渡位数"]}）；'
             f'航线 {canon["汇总"]["航线数"]} 条；山口通道 {canon["汇总"]["山口数"]} 处'
             f'（{canon["汇总"]["山口类数"]} 类，载客 {canon["汇总"]["载客山口数"]} 处）。', '']

    lines += ['## 一、桥梁（跨度与交角实算自名录水系折线）', '',
              '| 码 | 名 | 类 | 跨越 | 跨度 m | 水宽 m | 倍数 | 桥轴 ° | 局部流向 ° | 交角 ° | 轴线距 m | 湖内最小 f | 圈层对 | 可达 km |',
              '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in canon['桥梁']:
        lines.append(f'| {r["码"]} | {r["名"]} | {r["类"]} | {r["跨越"]} {r["水系名"]} | {r["跨度m"]} | '
                     f'{r["实测水宽m"]} | {r["跨度水宽倍数"]} | {r["桥轴方位deg"]} | {r["局部流方位deg"]} | '
                     f'{acute_angle(r["桥轴方位deg"], r["局部流方位deg"]):.1f} | {r["轴线距m"]} | {r["湖内最小f"]} | '
                     f'{_md(r["圈层对"])} | {r["可达A_km"]}／{r["可达B_km"]} |')
    lines += ['', '| 码 | 连接 A | 连接 B | 车道 | 说明 |', '| --- | --- | --- | --- | --- |']
    for r in canon['桥梁']:
        lines.append(f'| {r["码"]} | {r["连接A"]} {r["连接A名"]}（{r["A圈层"]}） | '
                     f'{r["连接B"]} {r["连接B名"]}（{r["B圈层"]}） | {r["车道"]} | {r["说明"]} |')

    lines += ['', '## 二、渡位（贴岸与湖岸贴合实算）', '',
              '| 码 | 名 | 临 | 坐标 km | 湖岸 f | 离轴 m | 水宽 m | 半宽 m | 贴岸余量 m |',
              '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in canon['渡位']:
        lines.append(f'| {r["码"]} | {r["名"]} | {r["临"]} | ({r["坐标km"][0]}, {r["坐标km"][1]}) | '
                     f'{_cell(r.get("湖岸f"))} | {_cell(r.get("离轴m"))} | {_cell(r.get("实测水宽m"))} | '
                     f'{_cell(r.get("半宽m"))} | {_cell(r.get("贴岸余量m"))} |')

    lines += ['', '## 三、轮渡航线（固定耗时零随机）', '',
              '| 码 | 名 | 渡位 A | 渡位 B | 过水 | 直线 km | 航段 km | 耗时分钟 | 班次每日 | 圈层对 | 可达 km |',
              '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in canon['轮渡航线']:
        lines.append(f'| {r["码"]} | {r["名"]} | {r["渡位A"]} | {r["渡位B"]} | {r["过水"]} | {r["直线km"]} | '
                     f'{r["航段km"]} | {r["耗时分钟"]} | {r["班次每日"]} | {_md(r["圈层对"])} | '
                     f'{r["可达A_km"]}／{r["可达B_km"]} |')
    lines += ['', '| 码 | 服务 A | 服务 B | 票价（客／自行车／机动车装载） | 说明 |', '| --- | --- | --- | --- | --- |']
    fare = canon['参数']['轮渡']['系数与常数']['票价_钛币']
    for r in canon['轮渡航线']:
        lines.append(f'| {r["码"]} | {r["服务A"]} {r["服务A名"]} | {r["服务B"]} {r["服务B名"]} | '
                     f'{fare["客"]}／{fare["自行车"]}／{fare["小型机动车装载"]} | {r["说明"]} |')

    lines += ['', '## 四、山口通道与对外班线（盆界交点实算自名录矩形）', '',
              '| 码 | 名 | 类 | 载客 | 门户 | 门户圈层 | 山外讫点 | 直线 km | 里程 km | 耗时分钟 | 盆界交点 km | 声明偏差 km | 离最近锚点 km |',
              '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in canon['山口通道']:
        lines.append(f'| {r["码"]} | {r["名"]} | {r["类"]} | {_cell(r["载客"])} | {r["门户"]} {r["门户名"]} | '
                     f'{r["门户圈层"]} | {r["山外讫点"]} | {r["直线km"]} | {r["里程km"]} | {_cell(r["耗时分钟"])} | '
                     f'({r["盆界交点km"][0]}, {r["盆界交点km"][1]}) | {r["交点偏差km"]} | {r["讫点离最近锚点km"]} |')
    lines += ['', '| 类 | 名 | 载客 | 口径 |', '| --- | --- | --- | --- |']
    for k in canon['参数']['山口通道']['六类']:
        lines.append(f'| {k["码"]} | {k["名"]} | {_cell(k["载客"])} | {k["口径"]} |')

    lines += ['', '## 五、判据与实测余量', '',
              '| 判据 | 登记值 | 实测区间 |', '| --- | --- | --- |']
    b = canon['桥梁']
    lines.append(f'| 桥头中点离轴上限 | {t["轴线距上限米"]} m | {min(r["轴线距m"] for r in b)}—'
                 f'{max(r["轴线距m"] for r in b)} m |')
    lines.append(f'| 桥轴与流向最小交角 | ≥ {90 - t["桥轴与流向正交容差度"]:.0f}° | '
                 f'{min(acute_angle(r["桥轴方位deg"], r["局部流方位deg"]) for r in b):.1f}°—'
                 f'{max(acute_angle(r["桥轴方位deg"], r["局部流方位deg"]) for r in b):.1f}° |')
    lines.append(f'| 跨度／水宽倍数 | {t["跨度下限倍数水宽"]}—{t["跨度上限倍数水宽"]} | '
                 f'{min(r["跨度水宽倍数"] for r in b)}—{max(r["跨度水宽倍数"] for r in b)} |')
    lines.append(f'| 桥位穿湖最小 f | ≥ {t["湖内判据下限"]} | {min(r["湖内最小f"] for r in b)}（穿湖桥 '
                 f'{canon["汇总"]["穿湖桥数"]} 座）|')
    wv = [r for r in canon['渡位'] if r['临'] != '湖']
    lines.append(f'| 河渡位贴岸余量 | {t["渡位贴岸余量区间米"][0]}—{t["渡位贴岸余量区间米"][1]} m | '
                 f'{min(r["贴岸余量m"] for r in wv)}—{max(r["贴岸余量m"] for r in wv)} m |')
    lines.append(f'| 湖渡位岸线偏差 \\|f−1\\| | ≤ {t["湖岸椭圆贴合容差"]} | '
                 f'{max(abs(r["湖岸f"] - 1.0) for r in canon["渡位"] if "湖岸f" in r):.4f} |')
    lines.append(f'| 构件锚点可达半径 | 内湖环 {t["锚点可达半径上限千米"]["内湖环"]}／外城环 '
                 f'{t["锚点可达半径上限千米"]["外城环"]}／外围 {t["锚点可达半径上限千米"]["产业小镇"]} km | '
                 f'实得最大 {max(max(r["可达A_km"], r["可达B_km"]) for r in b)} km（桥）、'
                 f'{max(max(r["可达A_km"], r["可达B_km"]) for r in canon["轮渡航线"])} km（渡） |')
    lines.append(f'| 盆界交点声明容差 | {t["盆界交点声明容差千米"]} km | '
                 f'{max(r["交点偏差km"] for r in canon["山口通道"])} km |')
    lines.append(f'| 山外讫点离任一锚点下限 | {t["山外讫点离任一锚点下限千米"]} km | '
                 f'{min(r["讫点离最近锚点km"] for r in canon["山口通道"])} km |')

    lines += ['', '## 六、禁则与口径', '']
    for k, v in canon['参数']['禁则'].items():
        lines.append(f'- **{k}**：{v}' if k != '口径' else f'- 口径：{v}')
    lines += ['', f'- 桥梁侧：{t["口径"]}',
              f'- 锚点可达：{t["锚点可达口径"]}',
              f'- 轮渡：{canon["参数"]["轮渡"]["系数与常数"]["口径"]}',
              f'- 山口：{canon["参数"]["山口通道"]["接驳常数"]["口径"]}',
              f'- 汇总：{canon["汇总"]["口径"]}']
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default=str(ROOT / '数据'))
    ap.add_argument('--print-checks', action='store_true')
    args = ap.parse_args()
    canon = build_canon()
    if args.print_checks:
        for r in canon['桥梁']:
            print([r['码'], r['跨度m'], r['跨度水宽倍数'], round(acute_angle(r['桥轴方位deg'], r['局部流方位deg']), 1),
                   r['轴线距m'], r['湖内最小f']])
        for r in canon['山口通道']:
            print([r['码'], r['里程km'], r['耗时分钟'], r['交点偏差km']])
        return
    out = Path(args.out_dir)
    (out / '空间通行正典.json').write_bytes(
        (json.dumps(canon, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    (out / '空间通行总表.md').write_text(render_table(canon), encoding='utf-8')
    print(json.dumps(canon['汇总'], ensure_ascii=False))


if __name__ == '__main__':
    main()
