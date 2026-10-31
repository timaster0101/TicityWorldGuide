# -*- coding: utf-8 -*-
"""从分卷/原稿的取景段解析机位、朝向与镜头，核验本片区下属地标是否真的落在水平视锥内。

取景段是提示词与清单里【取景指令】和 camera_facing_deg 的唯一真源，所以本闸门直接读原稿，
不读派生的AI地点知识库与开图清单，避免正文改了而派生字段还绿。
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))
BYID = {e['id']: e for e in REG['entries']}
LAKE = REG['lake']
SENSOR_W = 36.0

ENTRY = re.compile(r'^##\s+([SDFLR]\d{2,3})\s+([^\n]+)\n', re.M)
SECTION = re.compile(r'^\*\*([^*\n]+)\*\*：(.*)$', re.M)
COORD = re.compile(r'[\(\（]\s*(-?\d+(?:\.\d+)?)\s*[,，、]\s*(-?\d+(?:\.\d+)?)\s*[\)\）]')
LENS = re.compile(r'(\d{2,3})\s*毫米')
ALT = re.compile(r'离地\s*(\d+(?:\.\d+)?)\s*米')
BASE = {'北': 0.0, '东北': 45.0, '东': 90.0, '东南': 135.0, '南': 180.0, '西南': 225.0, '西': 270.0, '西北': 315.0}
DIRECTION = '东北|东南|西南|西北|北|东|南|西'
FACNUM = re.compile(r'(?:朝|向)\s*(\d{2,3})\s*°')
FACE = re.compile(r'(?:朝|向|面向)\s*(' + DIRECTION + r')(?:偏(' + DIRECTION + '))?')
WATER = re.compile(r'(?:机位|相机|架机|设机|镜头)[^。；]{0,14}(?:湖面|水面|水上|船上|浮台)'
                   r'|(?:湖面|水面|水上|船上|浮台)[^。；]{0,10}(?:架机|设机|机位)')


def sections_of(body):
    return {m.group(1): m.group(2).strip() for m in SECTION.finditer(body)}


def camera_facing(segment):
    numeric = FACNUM.search(segment)
    if numeric:
        return float(numeric.group(1))
    word = FACE.search(segment)
    if not word:
        return None
    angle = BASE[word.group(1)]
    return angle if not word.group(2) else (2 * angle + BASE[word.group(2)]) / 3


def bearing(src, dst):
    return math.degrees(math.atan2(dst[0] - src[0], dst[1] - src[1])) % 360


def offset(b, facing):
    return (b - facing + 540) % 360 - 180


def in_lake(p):
    return (p[0] / LAKE['east_west_semiaxis_km']) ** 2 + (p[1] / LAKE['north_south_semiaxis_km']) ** 2 <= 1


def in_sector(p, sector):
    r = math.hypot(*p)
    a = bearing((0, 0), p)
    delta = offset(a, sector['angle_center_deg'])
    return (abs(delta) <= sector['angle_half_width_deg'] + 0.05
            and sector['inner_radius_km'] - 0.05 <= r <= sector['outer_radius_km'] + 0.05)


drafts = {}
for path in sorted((ROOT / '分卷' / '原稿').glob('*.md')):
    text = path.read_text(encoding='utf-8-sig')
    matches = list(ENTRY.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        drafts[m.group(1)] = sections_of(text[m.end():end])

parser = argparse.ArgumentParser()
parser.add_argument('--all', action='store_true', help='把非片区条目也纳入判红范围')
args = parser.parse_args()

results = []
for eid, entry in sorted(BYID.items()):
    seg = drafts.get(eid, {}).get('图像与视频取景', '')
    coord = COORD.search(seg)
    cam = [float(coord.group(1)), float(coord.group(2))] if coord else None
    facing = camera_facing(seg)
    lens = LENS.search(seg)
    lens = float(lens.group(1)) if lens else None
    alt = ALT.search(seg)
    alt = float(alt.group(1)) if alt else None
    half_fov = math.degrees(math.atan(SENSOR_W / 2 / lens)) if lens else None

    if entry['type'] == '城市片区':
        own = [e for e in REG['entries'] if e.get('parent') == eid and e['type'] == '标志性建筑']
    else:
        own = [entry]
    subjects = []
    for s in own:
        if cam is None or facing is None or half_fov is None:
            subjects.append(dict(id=s['id'], in_fov=None))
            continue
        b = bearing(cam, s['center_km'])
        d = offset(b, facing)
        subjects.append(dict(id=s['id'], bearing_deg=round(b, 1), offset_deg=round(d, 1),
                             distance_km=round(math.hypot(s['center_km'][0] - cam[0], s['center_km'][1] - cam[1]), 3),
                             in_fov=abs(d) <= half_fov))
    visible = [s['id'] for s in subjects if s.get('in_fov')]

    issues = []
    if cam is None:
        issues.append('取景段无可解析的机位坐标')
    if facing is None:
        issues.append('取景段无可解析的拍摄朝向')
    if lens is None:
        issues.append('取景段未给镜头焦距，无法算水平视锥')
    if cam is not None and in_lake(cam) and not WATER.search(seg):
        issues.append('机坐标落在钛湖水面内，但取景段未说明是水面或船上机位')
    if cam is not None and entry['type'] == '城市片区':
        if not in_sector(cam, entry['sector']):
            issues.append('机位不在本片区扇区内')
    if entry['type'] == '城市片区' and cam is not None and facing is not None and half_fov is not None:
        missing = [s['id'] for s in subjects if s.get('in_fov') is False]
        if missing:
            issues.append('本片区下属地标未全部入画，缺' + ','.join(missing) + '，画面拍不到完整的片区辨识度')
        tight = [s['id'] for s in subjects if s.get('in_fov') and abs(s['offset_deg']) > half_fov - 3]
        if tight:
            issues.append('地标偏角距视锥边缘不足3°余量，构图会切边：' + ','.join(tight))
        if alt is None:
            issues.append('片区俯瞰口径要求写明机位离地高度')
        elif alt < 20:
            issues.append(f'片区俯瞰口径要求机位离地不低于20米，现为{alt}米')

    results.append(dict(id=eid, name=entry['name'], type=entry['type'], framing_found=bool(seg),
                        camera_km=cam,
                        facing_deg=facing, lens_mm=lens, half_fov_deg=round(half_fov, 1) if half_fov else None,
                        camera_height_m=alt, own_subjects=[s['id'] for s in subjects],
                        visible_in_fov=visible, issues=issues))

districts = [r for r in results if r['type'] == '城市片区']
others = [r for r in results if r['type'] != '城市片区']
district_fail = [r for r in districts if r['issues']]
other_fail = [r for r in others if r['issues']]
gated = district_fail + other_fail if args.all else district_fail

output = dict(
    rule='城市片区取景段须给出机位坐标、镜头焦距与离地高度：机位在本片区扇区角与半径带内、不无说明落水、'
         '离地不低于20米、本片区全部下属标志性建筑落在按 atan(36/2/焦距) 算出的水平视锥内且留3°余量；'
         '默认只判红城市片区，--all 把其余244条一并纳入。',
    checked=len(results),
    framing_parsed=sum(1 for r in results if r['framing_found']),
    districts=len(districts),
    districts_pass=len(districts) - len(district_fail),
    districts_fail=len(district_fail),
    non_district_fail=len(other_fail),
    district_subject_coverage=dict(
        total_landmarks=sum(len(r['own_subjects']) for r in districts),
        visible=sum(len(r['visible_in_fov']) for r in districts)),
    failures=gated,
    results=results)
(ROOT / '数据' / '取景几何核验.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')

for r in districts:
    print('%s %s 机位%s 朝向%s° 镜头%s 半视锥%s° 下属%s 入画%s %s' % (
        r['id'], r['name'], r['camera_km'], r['facing_deg'], r['lens_mm'], r['half_fov_deg'],
        ','.join(r['own_subjects']), ','.join(r['visible_in_fov']) or '无',
        '｜' + '；'.join(r['issues']) if r['issues'] else ''))
print(json.dumps(dict(checked=output['checked'], districts=output['districts'],
                      districts_pass=output['districts_pass'], districts_fail=output['districts_fail'],
                      non_district_fail=output['non_district_fail'],
                      subject_coverage=output['district_subject_coverage'],
                      gated=len(gated)), ensure_ascii=False))
if not gated:
    # 计数对账：取景段必须逐条从原稿读到，否则是解析器空转而不是全都合格
    if output['framing_parsed'] != len(REG['entries']) or output['districts'] != 20:
        print('!! 解析计数与名录不符（读到取景段=%d 名录=%d，districts=%d），闸门判红而非判绿' % (
            output['framing_parsed'], len(REG['entries']), output['districts']))
        sys.exit(1)
    if output['district_subject_coverage']['visible'] != output['district_subject_coverage']['total_landmarks']:
        print('!! 片区地标入画数与名录下属地标总数不等，闸门判红')
        sys.exit(1)
    print('取景几何闸门通过：%d/%d 片区合格，%d/%d 座下属地标入画，解析计数与名录一致' % (
        output['districts'], output['districts'], output['district_subject_coverage']['visible'],
        output['district_subject_coverage']['total_landmarks']))
sys.exit(1 if gated else 0)
