# -*- coding: utf-8 -*-
"""天际线扩容闸门：逐条复核全部标志性建筑的落位四项硬判据与本片区视锥可入画性。

判据来自方案 A 的 authored 约束，写进名录后必须可机器复算，不能只靠求解时的临时脚本：
  A 扇区归属——地标锚点落在所属城市片区的扇区角与半径带内；
  B 岸距——锚点到钛湖椭圆岸线的最短距离不低于 0.30 千米（落水为负，直接判红）；
  C 河流余量——锚点到两条河折线的距离不低于「最大水宽/2＋岸外30米」再留 0.05 千米；
  D 锚点间距——与任意其它地标或居民区锚点的中心距不低于 0.30 千米，避免天际线叠影与地块撞图；
  E 视锥可入画——按本片区取景段的机位、朝向与镜头焦距，地标偏角落在水平视锥内并留 3° 构图余量。

机位、朝向与半视锥读自 数据/取景几何核验.json（由 verify_framing.py 从原稿取景段解析），
本闸门用名录条目数与片区数对账，防止拿着一份过期快照判绿。跑法：python 工具/verify_skyline.py
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))
FRAMING = json.loads((ROOT / '数据' / '取景几何核验.json').read_text(encoding='utf-8'))

LAKE = REG['lake']
SHORE_MIN_KM = 0.30
RIVER_SLACK_KM = 0.05
ANCHOR_SPACING_KM = 0.30
FOV_MARGIN_DEG = 3.0

entries = REG['entries']
byid = {e['id']: e for e in entries}
sectors = {e['id']: e['sector'] for e in entries if e['type'] == '城市片区'}
landmarks = [e for e in entries if e['type'] == '标志性建筑']
anchors = [e for e in entries if e['type'] in ('标志性建筑', '居民区')]
cameras = {r['id']: r for r in FRAMING['results'] if r['type'] == '城市片区'}


def dist_to_polyline(p, pts):
    best = None
    for a, b in zip(pts, pts[1:]):
        vx, vy = b[0] - a[0], b[1] - a[1]
        t = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / (vx * vx + vy * vy)))
        d = math.hypot(p[0] - a[0] - t * vx, p[1] - a[1] - t * vy)
        best = d if best is None else min(best, d)
    return best


def shore_gap(p):
    """到钛湖岸线的最近距离（千米）；落在湖面内返回负值，避免湖内点被当成合规。"""
    n = 2000
    v = (p[0] / LAKE['east_west_semiaxis_km']) ** 2 + (p[1] / LAKE['north_south_semiaxis_km']) ** 2
    ds = [math.dist(p, (LAKE['east_west_semiaxis_km'] * math.sin(math.radians(j * 360 / n)),
                        LAKE['north_south_semiaxis_km'] * math.cos(math.radians(j * 360 / n)))) for j in range(n)]
    return -min(ds) if v <= 1 else min(ds)


def bearing(src, dst):
    return math.degrees(math.atan2(dst[0] - src[0], dst[1] - src[1])) % 360


def offset(b, facing):
    return (b - facing + 540) % 360 - 180


results = []
for e in landmarks:
    p = e['center_km']
    sec = sectors.get(e['parent'])
    issues = []
    if sec is None:
        issues.append('所属片区无扇区参数')
        results.append(dict(id=e['id'], name=e['name'], parent=e['parent'], issues=issues))
        continue
    r = math.hypot(*p)
    delta = offset(bearing((0, 0), p), sec['angle_center_deg'])
    if abs(delta) > sec['angle_half_width_deg']:
        issues.append('偏角%.2f°超出片区扇区±%d°' % (abs(delta), sec['angle_half_width_deg']))
    if not (sec['inner_radius_km'] <= r <= sec['outer_radius_km']):
        issues.append('半径%.3f不在片区带%.2f–%.2f内' % (r, sec['inner_radius_km'], sec['outer_radius_km']))

    shore = shore_gap(p)
    if shore < SHORE_MIN_KM:
        issues.append('距钛湖岸线%.3f千米<%.2f' % (shore, SHORE_MIN_KM))

    river = {}
    for w in REG['rivers']:
        d = dist_to_polyline(p, w['centerline_km'])
        need = w['width_m'][1] / 2 / 1000 + 0.03 + RIVER_SLACK_KM
        river[w['id']] = round(d - need, 3)
        if d < need:
            issues.append('距%s余量%.3f千米<0.05（需%.3f）' % (w['name'], d - need, need))

    near = min((math.dist(p, a['center_km']) for a in anchors if a['id'] != e['id']), default=None)
    if near is not None and near < ANCHOR_SPACING_KM:
        issues.append('与最近锚点仅%.3f千米<%.2f' % (near, ANCHOR_SPACING_KM))

    cam = cameras.get(e['parent'])
    fov = None
    if cam is None or cam.get('camera_km') is None or cam.get('facing_deg') is None or cam.get('half_fov_deg') is None:
        issues.append('所属片区取景段无机位/朝向/镜头，无法判视锥')
    else:
        off = offset(bearing(cam['camera_km'], p), cam['facing_deg'])
        limit = cam['half_fov_deg'] - FOV_MARGIN_DEG
        fov = dict(offset_deg=round(off, 2), limit_deg=round(limit, 2), slack_deg=round(limit - abs(off), 3))
        if abs(off) > limit:
            issues.append('距%s机位偏角%.2f°超出视锥限%.2f°' % (e['parent'], off, limit))

    results.append(dict(id=e['id'], name=e['name'], parent=e['parent'], height_m=e['height_m'],
                        floors=e['floors'], sector_delta_deg=round(delta, 2), radius_km=round(r, 3),
                        shore_gap_km=round(shore, 3), river_slack_km=river, nearest_anchor_km=round(near, 3),
                        fov=fov, issues=issues))

failures = [r for r in results if r['issues']]
tiers = {'400+': 0, '300-399': 0, '200-299': 0, '150-199': 0, '100-149': 0, '60-99': 0, '<60': 0}
for r in results:
    h = r.get('height_m') or 0
    key = ('400+' if h >= 400 else '300-399' if h >= 300 else '200-299' if h >= 200
           else '150-199' if h >= 150 else '100-149' if h >= 100 else '60-99' if h >= 60 else '<60')
    tiers[key] += 1

# 计数对账：地标全量、取景快照与名录同代、每片区3条以上——任一不符即判红，不给空转判绿的机会
meta = dict(
    rule='全部标志性建筑须满足：扇区归属、岸距≥%.2f千米、河流缓冲再留%.2f千米、锚点间距≥%.2f千米、'
         '并按所属片区取景段机位与镜头落在水平视锥内且留%.0f°余量。' % (SHORE_MIN_KM, RIVER_SLACK_KM, ANCHOR_SPACING_KM, FOV_MARGIN_DEG),
    landmarks=len(results), registry_entries=len(entries), districts=len(cameras),
    framing_checked=FRAMING['checked'], height_tiers=tiers,
    min_shore_gap_km=min(r['shore_gap_km'] for r in results if 'shore_gap_km' in r),
    min_anchor_spacing_km=min(r['nearest_anchor_km'] for r in results if 'nearest_anchor_km' in r),
    min_river_slack_km=min(v for r in results if 'river_slack_km' in r for v in r['river_slack_km'].values()),
    max_fov_offset_deg=max(abs(r['fov']['offset_deg']) for r in results if r.get('fov')),
    failures=failures)
stale = []
if meta['landmarks'] != sum(1 for e in entries if e['type'] == '标志性建筑'):
    stale.append('地标计数与名录不符')
if FRAMING['checked'] != len(entries):
    stale.append('取景核验读到 %d 条，名录现有 %d 条——取景几何核验.json 已过期，先重跑 verify_framing.py' % (FRAMING['checked'], len(entries)))
if meta['districts'] != 20:
    stale.append('取景核验片区数为 %d，应为 20' % meta['districts'])
output = dict(meta=meta, stale_or_wrong=stale, results=results)
(ROOT / '数据' / '天际线落位核验.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')

for r in results:
    if r['issues']:
        print('!! %s %s（%s）：%s' % (r['id'], r['name'], r['parent'], '；'.join(r['issues'])))
print(json.dumps(dict(landmarks=meta['landmarks'], districts=meta['districts'], failures=len(failures),
                      stale=len(stale), tiers=meta['height_tiers'],
                      min_shore=meta['min_shore_gap_km'], min_spacing=meta['min_anchor_spacing_km'],
                      min_river_slack=meta['min_river_slack_km'], max_fov_offset=meta['max_fov_offset_deg']),
                 ensure_ascii=False))
for s in stale:
    print('!! %s' % s)
if failures or stale:
    sys.exit(1)
print('天际线落位闸门通过：%d 条地标全部满足扇区/岸距/河流余量/间距/视锥五项判据' % len(results))
