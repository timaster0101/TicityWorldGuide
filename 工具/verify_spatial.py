# -*- coding: utf-8 -*-
"""空间闸门：河流锚点缓冲专项＋第5期通行构件十八判。构件侧只读落盘正典与源表，几何与耗时全部另抄一份算式复核。

跑法：python 工具/verify_spatial.py。任一判红即非零退出，compile_book.py 会因此停住汇编。
"""
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))
ENTRIES = data['entries']
BY_ID = {e['id']: e for e in ENTRIES}
BOX = data['region_boundary_km']
LAKE = data['lake']
RIVERS = {r['id']: r for r in data['rivers']}
SP_PATH = ROOT / '数据' / '空间通行正典.json'
if not SP_PATH.exists():
    raise SystemExit('缺少 数据/空间通行正典.json：第5期构件清单未生成，先跑 python 工具/build_spatial_lists.py')
SPCANON = json.loads(SP_PATH.read_text(encoding='utf-8'))
SPSRC = json.loads((ROOT / '数据' / '空间通行源表.json').read_text(encoding='utf-8'))
PRMSRC = json.loads((ROOT / '数据' / '运行参数源表.json').read_text(encoding='utf-8'))
from anchors import entry_ring, pair_key


def distance_to_segment(p, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    t = max(0, min(1, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / (vx * vx + vy * vy)))
    return math.hypot(p[0] - a[0] - t * vx, p[1] - a[1] - t * vy)


results = []
for e in ENTRIES:
    if e['type'] not in ['标志性建筑', '居民区']:
        continue
    constraints = []
    for river in data['rivers']:
        points = river['centerline_km']
        d = min(distance_to_segment(e['center_km'], a, b) for a, b in zip(points, points[1:])) * 1000
        required = river['width_m'][1] / 2 + 30
        constraints.append(dict(river=river['id'], distance_to_centerline_m=round(d, 2),
                                required_m=required, passes_anchor_buffer=d >= required))
    results.append(dict(id=e['id'], center_km=e['center_km'], constraints=constraints))
failures = [r for r in results if any(not c['passes_anchor_buffer'] for c in r['constraints'])]


def straight(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def azimuth(a, b):
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])) % 360.0


def acute(a, b):
    r = abs(a - b) % 360.0
    if r > 180.0:
        r = 360.0 - r
    return r if r <= 90.0 else 180.0 - r


def lake_norm(p):
    return (p[0] / LAKE['east_west_semiaxis_km']) ** 2 + (p[1] / LAKE['north_south_semiaxis_km']) ** 2


def mid(a, b):
    return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]


def walk_at(river, s):
    pts = river['centerline_km']
    cum = [0.0]
    for i in range(len(pts) - 1):
        cum.append(cum[-1] + straight(pts[i], pts[i + 1]))
    total = cum[-1]
    s = max(0.0, min(total, s))
    for i in range(len(pts) - 1):
        if s <= cum[i + 1] or i == len(pts) - 2:
            a, b = pts[i], pts[i + 1]
            t = (s - cum[i]) / (cum[i + 1] - cum[i])
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def project(river, p):
    """返回 (离轴km, 投影弧km, 投影点km, 局部流向°, 沿程水宽m)。局部流向取投影弧前后各 0.5 千米的弦向。"""
    pts = river['centerline_km']
    cum = [0.0]
    for i in range(len(pts) - 1):
        cum.append(cum[-1] + straight(pts[i], pts[i + 1]))
    best = None
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        vx, vy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(vx, vy)
        t = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / (L * L)))
        foot = (a[0] + t * vx, a[1] + t * vy)
        d = straight(p, foot)
        if best is None or d < best[0]:
            best = (d, cum[i] + L * t, foot)
    lo, hi = river['width_m']
    width = lo + (best[1] / cum[-1]) * (hi - lo)
    flow = azimuth(walk_at(river, best[1] - 0.5), walk_at(river, best[1] + 0.5))
    return best[0], best[1], best[2], flow, width


def bank(river, p, arc, foot):
    """点相对河道轴线的左右符号，基准线取投影弧前后各 0.5 千米的弦。"""
    deg = math.radians(azimuth(walk_at(river, arc - 0.5), walk_at(river, arc + 0.5)))
    ux, uy = math.sin(deg), math.cos(deg)
    return (p[0] - foot[0]) * uy - (p[1] - foot[1]) * ux


def fixed_minutes(km, speed, wait, step):
    return math.ceil((km / speed * 60 + wait) / step) * step


def box_exit(a, b):
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
    return min(cands)[1] if cands else None


def inside_box(p):
    return BOX[0] <= p[0] <= BOX[2] and BOX[1] <= p[1] <= BOX[3]


def spatial_issues(canon, src, prm):
    out = []
    t = src['参数']['容差']
    brid, whar, routes, passes = canon['桥梁'], canon['渡位'], canon['轮渡航线'], canon['山口通道']
    # 1 行数与编号：正典四表必须与源表逐行对应，编号唯一且格式统一
    rows_by_name = [('桥梁', brid, r'^BR-\d{2}$', src['参数']['桥梁']),
                    ('渡位', whar, r'^WH-\d{2}$', src['参数']['轮渡']['渡位']),
                    ('航线', routes, r'^FR-\d{2}$', src['参数']['轮渡']['航线']),
                    ('山口', passes, r'^PA-\d{2}$', src['参数']['山口通道']['通道'])]
    for nm, rows, pat, want in rows_by_name:
        if len(rows) != len(want):
            out.append(f'行数: {nm} 正典 {len(rows)} 行，源表 {len(want)} 行')
        codes = [r['码'] for r in rows]
        if len(set(codes)) != len(codes):
            out.append(f'行数: {nm} 编号重复')
        bad = [c for c in codes if not re.match(pat, c)]
        if bad:
            out.append(f'行数: {nm} 编号格式不合 {bad[:3]}')
        if sorted(codes) != sorted(x['码'] for x in want):
            out.append(f'行数: {nm} 正典编号集与源表不符')
    # 2 锚点引用与可达复算：连接／服务／门户锚点须在名录内，且构件到锚点距离不超该圈层上限
    reach = t['锚点可达半径上限千米']
    whm = {r['码']: r for r in whar}
    for r in brid:
        for k, aid, pos in (('连接A', r['连接A'], mid(r['桥头A_km'], r['桥头B_km'])),
                            ('连接B', r['连接B'], mid(r['桥头A_km'], r['桥头B_km']))):
            if aid not in BY_ID:
                out.append(f'引用: {r["码"]} 的{k} {aid} 不在名录内')
                continue
            ring = entry_ring(BY_ID[aid], BY_ID)
            if ring not in reach:
                out.append(f'引用: {r["码"]} {k} 的圈层 {ring} 没有可达半径口径')
                continue
            got = straight(pos, BY_ID[aid]['center_km'])
            if got > reach[ring]:
                out.append(f'可达: {r["码"]} 桥位到 {aid} {got:.2f} 千米，超过{ring}上限 {reach[ring]} 千米')
    for r in routes:
        a, b = whm.get(r['渡位A']), whm.get(r['渡位B'])
        if a is None or b is None:
            out.append(f'引用: {r["码"]} 引用了不存在的渡位')
            continue
        for k, aid, pos in (('服务A', r['服务A'], a['坐标km']), ('服务B', r['服务B'], b['坐标km'])):
            if aid not in BY_ID:
                out.append(f'引用: {r["码"]} 的{k} {aid} 不在名录内')
                continue
            ring = entry_ring(BY_ID[aid], BY_ID)
            if ring not in reach:
                out.append(f'引用: {r["码"]} {k} 的圈层 {ring} 没有可达半径口径')
            elif straight(pos, BY_ID[aid]['center_km']) > reach[ring]:
                out.append(f'可达: {r["码"]} 渡位到 {aid} 超过{ring}上限 {reach[ring]} 千米')
    for r in passes:
        if r['门户'] not in BY_ID:
            out.append(f'引用: {r["码"]} 的门户 {r["门户"]} 不在名录内')
    # 3 桥跨度复算
    for r in brid:
        got = round(straight(r['桥头A_km'], r['桥头B_km']) * 1000, 1)
        if abs(got - r['跨度m']) > 0.2:
            out.append(f'桥跨度: {r["码"]} 正典 {r["跨度m"]} m，复算 {got} m')
    # 4 桥位跨轴与左右岸异侧
    for r in brid:
        river = RIVERS.get(r['跨越'])
        if river is None:
            out.append(f'桥水系: {r["码"]} 跨越 {r["跨越"]} 不在名录水地里')
            continue
        c = mid(r['桥头A_km'], r['桥头B_km'])
        d, arc, foot, _, _ = project(river, c)
        if d * 1000 > t['轴线距上限米']:
            out.append(f'桥位: {r["码"]} 中点离轴 {d * 1000:.0f} m 超过 {t["轴线距上限米"]} m')
        if bank(river, r['桥头A_km'], arc, foot) * bank(river, r['桥头B_km'], arc, foot) >= 0:
            out.append(f'桥位: {r["码"]} 两桥头在 {r["跨越"]} 同侧，不是跨河构件')
    # 5 桥轴正交
    for r in brid:
        river = RIVERS.get(r['跨越'])
        if river is None:
            continue
        d, arc, foot, flow, _ = project(river, mid(r['桥头A_km'], r['桥头B_km']))
        if acute(azimuth(r['桥头A_km'], r['桥头B_km']), flow) < 90.0 - t['桥轴与流向正交容差度']:
            out.append(f'桥正交: {r["码"]} 桥轴与局部流向交角不足 {90 - t["桥轴与流向正交容差度"]:.0f}°')
    # 6 跨度对水宽倍数
    for r in brid:
        river = RIVERS.get(r['跨越'])
        if river is None:
            continue
        _, _, _, _, width = project(river, mid(r['桥头A_km'], r['桥头B_km']))
        ratio = straight(r['桥头A_km'], r['桥头B_km']) * 1000 / width
        if not t['跨度下限倍数水宽'] <= ratio <= t['跨度上限倍数水宽']:
            out.append(f'桥倍数: {r["码"]} 跨度是水宽的 {ratio:.2f} 倍，不在 [{t["跨度下限倍数水宽"]}, '
                       f'{t["跨度上限倍数水宽"]}] 内')
    # 7 零穿湖：桥线段任何采样点都不得进湖椭圆
    for r in brid:
        a, b = r['桥头A_km'], r['桥头B_km']
        fmin = min(lake_norm([a[0] + (b[0] - a[0]) * i / 100, a[1] + (b[1] - a[1]) * i / 100]) for i in range(101))
        if fmin < t['湖内判据下限']:
            out.append(f'桥穿湖: {r["码"]} 线段最小归一化值 {fmin:.2f}，湖心不架桥')
    # 8 渡位贴岸：临湖看椭圆贴合，临河看离轴余量区间
    lo_m, hi_m = t['渡位贴岸余量区间米']
    for r in whar:
        if r['临'] == '湖':
            if abs(lake_norm(r['坐标km']) - 1.0) > t['湖岸椭圆贴合容差']:
                out.append(f'渡位岸线: {r["码"]} 临湖但归一化值 {lake_norm(r["坐标km"]):.4f} 不贴岸线')
        else:
            river = RIVERS.get(r['临'])
            if river is None:
                out.append(f'渡位水系: {r["码"]} 临 {r["临"]} 不在名录水地里')
                continue
            d, arc, foot, _, width = project(river, r['坐标km'])
            over = d * 1000 - width / 2
            if not lo_m <= over <= hi_m:
                out.append(f'渡位贴岸: {r["码"]} 贴岸余量 {over:.0f} m 不在 [{lo_m}, {hi_m}] 内')
    # 9 航线过水：两端同水且线段确实跨过水面
    for r in routes:
        a, b = whm.get(r['渡位A']), whm.get(r['渡位B'])
        if a is None or b is None:
            continue
        if a['临'] != b['临'] or a['临'] != r['临']:
            out.append(f'航线渡位: {r["码"]} 两端渡位或水系不一致（{a["临"]}/{b["临"]}/{r["临"]}）')
            continue
        if a['临'] == '湖':
            if lake_norm(mid(a['坐标km'], b['坐标km'])) >= t['湖内判据下限']:
                out.append(f'航线过水: {r["码"]} 湖航线中点不在水面上')
        else:
            river = RIVERS[a['临']]
            _, arc, foot, _, _ = project(river, mid(a['坐标km'], b['坐标km']))
            if bank(river, a['坐标km'], arc, foot) * bank(river, b['坐标km'], arc, foot) >= 0:
                out.append(f'航线过水: {r["码"]} 两端渡位在 {a["临"]} 同侧')
    # 10 航线耗时复算
    c = src['参数']['轮渡']['系数与常数']
    for r in routes:
        a, b = whm.get(r['渡位A']), whm.get(r['渡位B'])
        if a is None or b is None:
            continue
        km = round(straight(a['坐标km'], b['坐标km']) * c['航道系数'], 3)
        mins = fixed_minutes(km, c['航速km_h'], c['候船分钟'], c['取整分钟'])
        if abs(km - r['航段km']) > 0.002 or mins != r['耗时分钟']:
            out.append(f'航线耗时: {r["码"]} 正典 {r["航段km"]} km／{r["耗时分钟"]} 分，复算 {km} km／{mins} 分')
    # 11 山口山外性：讫点须在盆界外且离任一名录锚点有下限距离
    for r in passes:
        if inside_box(r['讫点km']):
            out.append(f'山口盆界: {r["码"]} 山外讫点落在盆界矩形内')
        near = min(straight(r['讫点km'], e['center_km']) for e in ENTRIES)
        if near < t['山外讫点离任一锚点下限千米']:
            out.append(f'山口盆界: {r["码"]} 讫点离最近锚点 {near:.2f} 千米，低于 '
                       f'{t["山外讫点离任一锚点下限千米"]} 千米')
    # 12 盆界交点复算
    for r in passes:
        p = BY_ID.get(r['门户'])
        if p is None:
            continue
        ex = box_exit(p['center_km'], r['讫点km'])
        if ex is None or straight(ex, r['盆界交点km']) > t['盆界交点声明容差千米']:
            out.append(f'山口交点: {r["码"]} 实算交点与正典登记不符，容差 {t["盆界交点声明容差千米"]} 千米')
    # 13 载客与班线口径
    kinds = {k['码']: k for k in src['参数']['山口通道']['六类']}
    for r in passes:
        k = kinds.get(r['类'])
        if k is None:
            out.append(f'山口类别: {r["码"]} 的类 {r["类"]} 不在六类字典内')
            continue
        if bool(r['载客']) != bool(k['载客']):
            out.append(f'山口类别: {r["码"]} 载客标志与 {r["类"]} 字典不符')
        if not k['载客'] and (r['班线每日'] or r['票价_钛币']):
            out.append(f'山口班线: {r["码"]} 不载客却登记了班线或票价')
        if k['载客'] and r['班线每日'] <= 0:
            out.append(f'山口班线: {r["码"]} 载客类班线每日必须大于 0')
    for code in kinds:
        if code not in {r['类'] for r in passes}:
            out.append(f'山口类别: 字典类 {code} 没有实例')
    # 14 山口耗时复算
    cc = src['参数']['山口通道']['接驳常数']
    for r in passes:
        p = BY_ID.get(r['门户'])
        if p is None:
            continue
        km = round(straight(p['center_km'], r['讫点km']) * cc['山路系数'], 2)
        if abs(km - r['里程km']) > 0.02:
            out.append(f'山口耗时: {r["码"]} 正典里程 {r["里程km"]} km，复算 {km} km')
        if kinds.get(r['类'], {}).get('载客'):
            mins = fixed_minutes(km, cc['速度km_h'], cc['站前等候分钟'], cc['取整分钟'])
            if mins != r['耗时分钟']:
                out.append(f'山口耗时: {r["码"]} 正典 {r["耗时分钟"]} 分，复算 {mins} 分')
        elif r['耗时分钟'] is not None:
            out.append(f'山口耗时: {r["码"]} 不载客却有耗时分钟 {r["耗时分钟"]}')
    # 15 跨水覆盖：湖必须有客渡，两条河各自既有桥也有渡
    if not [r for r in routes if r['临'] == '湖']:
        out.append('跨水覆盖: 钛湖没有任何客渡航线')
    for wid in RIVERS:
        if not [r for r in brid if r['跨越'] == wid]:
            out.append(f'跨水覆盖: {wid} 没有桥梁构件')
        if not [r for r in routes if r['临'] == wid]:
            out.append(f'跨水覆盖: {wid} 没有渡线，桥渡两套清单不对齐')
    # 16 圈层覆盖：四个圈层都要有构件服务，否则外围聚落只能靠公路出圈
    served = {x for r in brid for x in (r['A圈层'], r['B圈层'])}
    served |= {x for r in routes for x in (r['A圈层'], r['B圈层'])}
    served |= {r['门户圈层'] for r in passes}
    missing = [k for k in ('内湖环', '外城环', '产业小镇', '特色村落') if k not in served]
    if missing:
        out.append(f'圈层覆盖: {missing} 没有任何通行构件服务')
    # 17 与第4期同源：延后方式只剩机场班机，轮渡与山外接驳登记为矩阵外方式且不进矩阵
    sp = prm['参数']['交通']
    deferred = [m['码'] for m in sp['延后方式']]
    outside = [m['码'] for m in sp.get('矩阵外方式', [])]
    if deferred != ['TR-AIR']:
        out.append(f'第4期同源: 延后方式应只剩 TR-AIR，实得 {deferred}')
    if sorted(outside) != ['TR-FERRY', 'TR-SHUTTLE']:
        out.append(f'第4期同源: 矩阵外方式码集不合，实得 {sorted(outside)}')
    for m in sp.get('矩阵外方式', []):
        if m.get('真源') != '数据/空间通行源表.json':
            out.append(f'第4期同源: {m["码"]} 的真源没指向空间通行源表')
    cell_modes = {x['码'] for x in sp['方式']}
    if cell_modes & (set(outside) | set(deferred)):
        out.append('第4期同源: 矩阵外或延后方式同时进了矩阵方式列表')
    # 18 汇总读数与逐行一致
    s = canon['汇总']
    if (s['桥梁数'], s['渡位数'], s['航线数'], s['山口数']) != (len(brid), len(whar), len(routes), len(passes)):
        out.append('汇总: 计数与四表行数不一致')
    if s['最长跨度m'] != max(r['跨度m'] for r in brid):
        out.append('汇总: 最长跨度与桥表不符')
    if s['穿湖桥数'] != sum(1 for r in brid if r['穿湖']):
        out.append('汇总: 穿湖桥数与桥表不符')
    if s['最长航线km'] != max(r['航段km'] for r in routes):
        out.append('汇总: 最长航线与航线表不符')
    bad_pair = [r['码'] for r in brid + routes if r['圈层对'] != pair_key(r['A圈层'], r['B圈层'])]
    if bad_pair:
        out.append(f'汇总: 圈层对键名不规范 {bad_pair[:4]}')
    return out


spatial = spatial_issues(SPCANON, SPSRC, PRMSRC)
output = dict(checked=len(results), rule='锚点距离河流折线>=最大水宽/2+30米；不替代完整地块缓冲审查',
              failures=failures, results=results,
              构件=dict(判据数=18, 桥梁=len(SPCANON['桥梁']), 渡位=len(SPCANON['渡位']),
                       航线=len(SPCANON['轮渡航线']), 山口=len(SPCANON['山口通道']),
                       失败=len(spatial), 失败明细=spatial,
                       rule='第5期通行构件十八判：几何、水宽、耗时与第4期同源性由本闸门独立复算，不引用生成器'))
(ROOT / '数据' / '河岸锚点核验.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(checked=len(results), 构件={k: v for k, v in output['构件'].items() if k != '失败明细'}),
                  ensure_ascii=False, indent=2))
for line in spatial:
    print('FAIL ' + line)
if failures or spatial:
    raise SystemExit(1)
print(f'全绿：河流缓冲 {len(results)} 条零违例，第5期构件十八判 0 失败')
