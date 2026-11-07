import argparse
import collections
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TAGS=['位置与规模','规划与空间组织','外观与辨识细节','人群与生活节奏','关联与地方性','图像与视频取景','锁定项与禁则']
_REGISTRY=json.loads((ROOT/'数据'/'城市空间名录.json').read_text(encoding='utf-8'))
# 分卷表真源在 build_registry.py，随名录一并带出；此处不再另立一份，改分卷只改那一处。
VOLUMES=[tuple(v) for v in _REGISTRY['volumes']]
_covered=[e['id'] for _,_,kind,lo,hi in VOLUMES for e in _REGISTRY['entries'] if e['id'][0]==kind and lo<=int(e['id'][1:])<=hi]
assert len(_covered)==len(_REGISTRY['entries']), '名录条目与分卷表不闭合，先重跑 build_registry.py --rebuild'
PATTERN=re.compile(r'^##\s+([SDFLR]\d{2,3})\s+([^\n]+)\n',re.M)


def split_entries(text):
    matches=list(PATTERN.finditer(text))
    return [(m.group(1),m.group(2).strip(),text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)].strip()) for i,m in enumerate(matches)]


COORD=re.compile(r'[\(\（]\s*(-?\d+(?:\.\d+)?)\s*[,，、]\s*(-?\d+(?:\.\d+)?)\s*[\)\）]')
NUMBER=r'(?<![\d.,+\-])([+\-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(?![\d.,])'
NEARDIST=re.compile(r'([SDFLR]\d{2,3})[^。；\n]{0,24}?(?:相距|距离|相隔|距)[^。；\n]{0,8}?'+NUMBER+r'\s*千米')
FIELD_PATTERNS={
    'area_km2': [NUMBER+r'\s*平方公里'],
    'gross_floor_area_m2': [r'建筑面积\s*'+NUMBER+r'\s*平方米'],
    'height_m': [r'(?<!限)高\s*'+NUMBER+r'\s*米(?![方])', r'(?:\d+层|单层)\s*'+NUMBER+r'\s*米(?![方])'],
    'floors': [NUMBER+r'\s*层'],
    'population': [r'(?:常住(?:人口)?|人口|居住)\s*'+NUMBER+r'(?=\s*(?:人(?!次)|名(?:常住)?居民|[，、；。\n]|$))', NUMBER+r'\s*(?:人(?!为|是|次)|名(?:常住)?居民)'],
    'daily_workers': [r'日常岗位(?:规模)?(?:为)?\s*'+NUMBER+r'\s*人', NUMBER+r'\s*人(?:为|是)(?:园区)?日常岗位'],
    'households': [NUMBER+r'\s*户', r'户数\s*'+NUMBER],
    'height_limit_m': [r'(?:限高|最高高度|不得超过|不超过|不超|禁止超(?:过)?)\s*'+NUMBER+r'\s*米', NUMBER+r'\s*米(?:为统一|为|是|只是|只作)?(?:限高|高度上限|高度控制|控制上限|上限|最高限制)'],
}


def numeric_declarations(field,sections):
    if field in ('area_km2','gross_floor_area_m2'):
        tags=['位置与规模']
    elif field in ('height_m','floors'):
        tags=['位置与规模','锁定项与禁则']
    elif field=='height_limit_m':
        tags=['位置与规模','规划与空间组织','外观与辨识细节','锁定项与禁则']
    else:
        tags=['位置与规模','人群与生活节奏']
    text='\n'.join(sections.get(tag,'') for tag in tags)
    return {float(match.group(1).replace(',','')) for pattern in FIELD_PATTERNS[field] for match in re.finditer(pattern,text)}


def check_numeric_fidelity(eid,e,body,sections,registry):
    issues=[];claims=0
    position=sections.get('位置与规模','')
    pairs=[(float(x),float(y)) for x,y in COORD.findall(position)]
    target=e['center_km']
    if not any(abs(x-target[0])<=.006 and abs(y-target[1])<=.006 for x,y in pairs):
        issues.append('position paragraph states no coordinate pair matching the registry anchor')
    for field in FIELD_PATTERNS:
        if field not in e:continue
        values=numeric_declarations(field,sections)
        if not values or any(abs(value-e[field])>1e-8 for value in values):
            issues.append(f'{field}: expected labeled value {e[field]}, found {sorted(values)}')
    for ref,claim in NEARDIST.findall(body):
        if ref==eid or ref not in registry:continue
        claims+=1
        ax,ay=e['center_km'];bx,by=registry[ref]['center_km']
        actual=math.hypot(ax-bx,ay-by)
        if abs(actual-float(claim.replace(',','')))>.4:
            issues.append(f'claims {claim} km to {ref}, geometry gives {actual:.3f} km')
    return issues,claims


BASE={'北':0.0,'东北':45.0,'东':90.0,'东南':135.0,'南':180.0,'西南':225.0,'西':270.0,'西北':315.0}
DIRECTION='东北|东南|西南|西北|北|东|南|西'
FACNUM=re.compile(r'(?:朝|向)\s*(\d{2,3})\s*°')
FACE=re.compile(r'(?:朝|向|面向)\s*('+DIRECTION+')(?:偏('+DIRECTION+'))?')
LIGHT_VARIANT=re.compile(r'[\u4e00-\u9fff]{0,4}变体')
LIGHT_KEYWORD=re.compile(r'255\s*°|夕阳|夕照|夕光|低阳|落日|天光')
FRAME_POSITION=[('后方偏左','range',-180,-90),('后方偏右','range',90,180),('前方偏左','range',-90,0),('前方偏右','range',0,90),
    ('画面左后','range',-180,-90),('画面右后','range',90,180),('画面左前','range',-90,0),('画面右前','range',0,90),
    ('右侧偏后','range',90,180),('右侧偏前','range',0,90),('左侧偏后','range',-180,-90),('左侧偏前','range',-90,0),
    ('左前方','range',-90,0),('右前方','range',0,90),('左前侧','range',-90,0),('右前侧','range',0,90),
    ('左后方','range',-180,-90),('右后方','range',90,180),('左后侧','range',-180,-90),('右后侧','range',90,180),
    ('相机背后','behind',0,0),('摄影机后','behind',0,0),('相机后方','behind',0,0),('相机后侧','behind',0,0),
    ('镜头后','behind',0,0),('背后','behind',0,0),('后侧','behind',0,0),('正后','behind',0,0),
    ('画面左','range',-180,0),('画面右','range',0,180),('左侧','range',-180,0),('右侧','range',0,180),
    ('逆光','near',0,0),('顺光','far',0,0)]
FRAME_POSITION.sort(key=lambda item:-len(item[0]))
POSITION_RANGE={item[0]:(item[1],item[2],item[3])for item in FRAME_POSITION}
POSITION_MATCH=re.compile('|'.join(re.escape(item[0])for item in FRAME_POSITION))


def camera_facing(segment):
    numeric=FACNUM.search(segment)
    if numeric:return float(numeric.group(1))
    word=FACE.search(segment)
    if not word:return None
    angle=BASE[word.group(1)]
    return angle if not word.group(2)else (2*angle+BASE[word.group(2)])/3


def position_ok(kind,low,high,relative):
    if kind=='range':return low<=relative<=high
    if kind=='behind':return abs(relative)>120
    if kind=='near':return abs(relative)<45
    return abs(relative)>135


def check_light_baseline(eid,segment):
    if not segment:return 'framing section missing',{}
    facing=camera_facing(segment)
    if facing is None:return 'framing section states no camera facing direction',{}
    relative=(255-facing+180)%360-180
    meta={'camera_facing_deg':round(facing,1),'sun_relative_deg':round(relative,1)}
    if LIGHT_VARIANT.search(segment):
        meta['lighting_baseline']='labeled variant'
        return None,meta
    keyword=LIGHT_KEYWORD.search(segment)
    if not keyword:return 'default-light entry never mentions the 255° baseline or any sun term',meta
    window=segment[keyword.end():keyword.end()+34]
    position=POSITION_MATCH.search(window)
    if not position:return f'states {round(relative)}° sun relative to camera but gives no frame position near it',meta
    kind,low,high=POSITION_RANGE[position.group(0)]
    if not position_ok(kind,low,high,relative):
        return f'camera faces {round(facing)}° so 255° sun is at relative {round(relative)}°, but the text says "{position.group(0)}"',meta
    meta['lighting_baseline']='255 deg / 6 deg'
    return None,meta


def card(e):
    rows=[('类别 / 归属',e['type']+' / '+e.get('parent_name',e['parent'])),('中心坐标',f"({e['center_km'][0]}, {e['center_km'][1]}) km；x东正、y北正"),('占地 / 范围面积',f"{e['area_km2']} km²（{e['area_km2']*100:.2f}公顷）")]
    if 'gross_floor_area_m2'in e:rows.append(('建筑面积',f"{e['gross_floor_area_m2']:,} m²"))
    if 'population'in e:rows.append(('常住人口',f"{e['population']:,}人"))
    if 'households'in e:rows.append(('设定户数',f"{e['households']:,}户"))
    if 'height_m'in e:rows.append(('建筑总高 / 地上楼层',f"{e['height_m']} m / {e['floors']}层"))
    if 'height_limit_m'in e:rows.append(('建筑限高',f"{e['height_limit_m']} m"))
    if 'floor_area_ratio'in e:rows.append(('设定容积率',str(e['floor_area_ratio'])))
    if 'daily_workers'in e:rows.append(('日常岗位规模',f"{e['daily_workers']:,}人；不是常住人口"))
    if 'built_up_ratio'in e:rows.append(('建设用地参考比例',f"{e['built_up_ratio']*100:.0f}%；余地含生产用地与生态空间"))
    if 'spatial_note'in e:rows.append(('区位特别约束',e['spatial_note']))
    if 'sector'in e:
        s=e['sector'];rows.append(('规划分区边界',f"方位中心{s['angle_center_deg']}°±18°；半径{s['inner_radius_km']}—{s['outer_radius_km']} km；"+('剔除钛湖水面' if s['exclude_lake'] else '不直接临中心湖')))
    return '| 空间卡 | 正典参数 |\n|---|---|\n'+'\n'.join(f'| {k} | {v} |' for k,v in rows)+'\n'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--audit-only',action='store_true');args=parser.parse_args()
    data=json.loads((ROOT/'数据'/'城市空间名录.json').read_text(encoding='utf-8'))
    byid={e['id']:e for e in data['entries']}
    # 计数一律从名录派生：扩容后不再手改正文里的 264/60 这类数字，避免第二份口径。
    total_entries=len(data['entries'])
    type_counts=collections.Counter(e['type'] for e in data['entries'])
    settlement_count=type_counts['产业小镇']+type_counts['特色村落']
    interior_count=type_counts['功能区']+type_counts['标志性建筑']
    errors=[];warnings=[];drafts={};stats=[];para_seen={};references=[];numeric_claims=0;light_checked=0;light_variants=0
    for path in sorted((ROOT/'分卷'/'原稿').glob('*.md')):
        text=path.read_text(encoding='utf-8-sig')
        for eid,name,body in split_entries(text):
            if eid in drafts:errors.append(f'{eid}: duplicate entry in {path.name}')
            if eid not in byid:errors.append(f'{eid}: unknown ID');continue
            e=byid[eid]
            if name!=e['name']:errors.append(f'{eid}: name mismatch {name} / {e["name"]}')
            count=len(re.findall(r'[\u4e00-\u9fff]',body))
            if count<600:errors.append(f'{eid}: only {count} CJK characters')
            if count>1000:warnings.append(f'{eid}: {count} CJK characters exceeds planned 1000; retained for detail')
            missing=[t for t in TAGS if f'**{t}**' not in body]
            if missing:errors.append(f'{eid}: missing sections {missing}')
            if re.search(r'TODO|TBD|待补充|此处省略|\u2026|\ufffd',body,re.I):errors.append(f'{eid}: placeholder or damaged character')
            for ref in re.findall(r'(?<![A-Za-z0-9])[SDFLR]\d{2,3}(?!\d)',body):
                if ref not in byid:errors.append(f'{eid}: invalid referenced ID {ref}')
                else:references.append((eid,ref))
            for paragraph in body.split('\n\n'):
                normalized=re.sub(r'\s+','',paragraph)
                if len(normalized)>130:
                    h=hashlib.sha256(normalized.encode()).hexdigest()
                    if h in para_seen:errors.append(f'{eid}: duplicated long paragraph from {para_seen[h]}')
                    para_seen[h]=eid
            sections={}
            for i,t in enumerate(TAGS):
                marker=f'**{t}**';start=body.find(marker)
                if start>=0:
                    end=body.find(f'**{TAGS[i+1]}**',start) if i+1<len(TAGS) else len(body)
                    sections[t]=body[start+len(marker):end].strip('：: \n')
            drafts[eid]=dict(name=name,body=body,source=path.name,sections=sections)
            found,measured=check_numeric_fidelity(eid,e,body,sections,byid)
            numeric_claims+=measured
            errors.extend(f'{eid}: {issue}'for issue in found)
            light_issue,light_meta=check_light_baseline(eid,sections.get('图像与视频取景',''))
            drafts[eid]['camera']=light_meta
            if light_meta.get('lighting_baseline')=='labeled variant':light_variants+=1
            else:light_checked+=1
            if light_issue:errors.append(f'{eid}: {light_issue}')
            stats.append(dict(id=eid,cjk_count=count,source=path.name))
    missing_ids=sorted(set(byid)-set(drafts))
    if missing_ids:errors.append('Missing IDs: '+', '.join(missing_ids))
    # 定档量级：阶段1 人口反推 + 阶段2 天际线分层扩容（L 60→108）；改数须同步方案稿的裁定条目。
    expected={'S':24,'D':20,'F':40,'L':108,'R':120}
    counts=collections.Counter(e['id'][0] for e in data['entries'])
    if dict(counts)!=expected:errors.append('Registry count mismatch')
    if len(byid)!=total_entries or len({e['name'] for e in byid.values()})!=total_entries:errors.append('Registry IDs or names not unique')
    area=sum(e['area_km2'] for e in byid.values() if e['type']=='城市片区')
    if abs(area+data['lake']['area_km2']-data['urban_gross_area_km2'])>.001:errors.append('District area ledger mismatch')
    isl=data['lake'].get('island')
    isl_rule=(f"中心湖6.4×4.2千米，湖内有一座钛马岛（示意椭圆{isl['east_west_semiaxis_km']}×{isl['north_south_semiaxis_km']}千米、"
              f"{isl['area_km2']}平方千米、岛面高程{isl['surface_elevation_m']}米，岛与城市无桥，"
              f"只走客渡／湖底隧道／高空缆车）；清岚河西北入湖、澜川东南外流"
              if isl else '中心湖6.4×4.2千米；清岚河西北入湖、澜川东南外流')
    if isl:
        ia,ib=isl['east_west_semiaxis_km'],isl['north_south_semiaxis_km'];ic=isl['center_km']
        if abs(isl['area_km2']-math.pi*ia*ib)>.0001:errors.append('Island area not ellipse-consistent')
        if abs(data['lake']['open_water_km2']-(data['lake']['area_km2']-isl['area_km2']))>.0001:errors.append('Open water ledger mismatch')
        if max(((ic[0]+ia*math.cos(t*math.pi/180))/3.2)**2+((ic[1]+ib*math.sin(t*math.pi/180))/2.1)**2 for t in range(360))>=1:errors.append('Island pokes out of the lakeshore')
        if any(((e['center_km'][0]-ic[0])/ia)**2+((e['center_km'][1]-ic[1])/ib)**2<1 for e in byid.values()):errors.append('A registry anchor sits on the island')
    for e in byid.values():
        if e['parent'] not in byid:continue
        parent=byid[e['parent']];s=parent['sector'];x,y=e['center_km'];r=math.hypot(x,y)
        a=math.degrees(math.atan2(x,y))%360;da=(a-s['angle_center_deg']+180)%360-180
        if abs(da)>18.02 or r<s['inner_radius_km']-.002 or r>s['outer_radius_km']+.002:errors.append(f'{e["id"]}: outside parent sector')
        if x*x/(3.2**2)+y*y/(2.1**2)<=1:errors.append(f'{e["id"]}: anchor inside lake')
    for d in (e for e in byid.values() if e['type']=='城市片区'):
        pop=sum(e['population'] for e in byid.values() if e['type']=='居民区' and e['parent']==d['id'])
        if pop>d['population']:errors.append(f'{d["id"]}: featured resident population exceeds district population')
    pop=data['population']
    if pop['regional_total']!=pop['city_core']+pop['satellite_settlements']+pop['dispersed_rural']:errors.append('Population ledger mismatch')
    occ_path=ROOT/'数据'/'产业就业正典.json'; gate_path=ROOT/'数据'/'产业就业核验.json'
    occ=json.loads(occ_path.read_text(encoding='utf-8'))['汇总'] if occ_path.exists() else None
    gate=json.loads(gate_path.read_text(encoding='utf-8')) if gate_path.exists() else None
    adm_path=ROOT/'数据'/'岗位准入正典.json'
    adm=json.loads(adm_path.read_text(encoding='utf-8'))['汇总'] if adm_path.exists() else None
    sp_canon_path=ROOT/'数据'/'空间通行正典.json'
    sp=json.loads(sp_canon_path.read_text(encoding='utf-8'))['汇总'] if sp_canon_path.exists() else None
    sp_gate_path=ROOT/'数据'/'河岸锚点核验.json'
    sp_gate=json.loads(sp_gate_path.read_text(encoding='utf-8')) if sp_gate_path.exists() else None
    fl_path=ROOT/'数据'/'流程制度正典.json'; fl_gate_path=ROOT/'数据'/'流程制度核验.json'
    fl_canon=json.loads(fl_path.read_text(encoding='utf-8')) if fl_path.exists() else None
    fl=fl_canon['汇总'] if fl_canon else None
    season_name={f['SEA']:f['季节名'] for f in (fl_canon['节庆年历'] if fl_canon else [])}
    fl_gate=json.loads(fl_gate_path.read_text(encoding='utf-8')) if fl_gate_path.exists() else None
    if occ and gate:
        if gate['失败数']:errors.append(f"产业就业门禁失败 {gate['失败数']} 条")
        if occ['雇员总数']!=occ['名录岗位总数']:errors.append('雇员总数与名录岗位总数不闭合')
    if fl and fl_gate:
        if fl_gate['失败数']:errors.append(f"流程制度门禁失败 {fl_gate['失败数']} 条")
        if fl['节庆占天次']!=sum(f['日期跨度天'] for f in fl_canon['节庆年历']):errors.append('节庆占天次与逐条跨度不闭合')
    result=dict(entry_count=len(drafts),category_counts=dict(collections.Counter(eid[0]for eid in drafts)),total_cjk=sum(s['cjk_count']for s in stats),min_cjk=min((s['cjk_count']for s in stats),default=0),max_cjk=max((s['cjk_count']for s in stats),default=0),errors=errors,warnings=warnings,entries=stats,referenced_id_count=len(references),numeric_distance_claims=numeric_claims,light_direction_checked=light_checked,light_variant_entries=light_variants,occupation_summary=occ,occupation_gate={'检查项数':gate['检查项数'],'失败数':gate['失败数']} if gate else None,admission_summary=adm,spatial_summary=sp,spatial_gate={'检查项数':sp_gate['checked'],'失败数':len(sp_gate['failures'])} if sp_gate else None,flow_summary=fl,flow_gate={'检查项数':fl_gate['检查项数'],'失败数':fl_gate['失败数']} if fl_gate else None)
    (ROOT/'数据'/'质量核验结果.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='entries'},ensure_ascii=False,indent=2))
    if errors:raise SystemExit('Compilation stopped: fix the listed errors before delivery.')
    if args.audit_only:return
    subprocess.run([sys.executable,str(ROOT/'工具'/'verify_spatial.py')],check=True)
    subprocess.run([sys.executable,str(ROOT/'工具'/'verify_flows.py')],check=True)
    chapters=[];entry_volume={}
    for prefix,title,kind,lo,hi in VOLUMES:
        ids=sorted((eid for eid in drafts if eid[0]==kind and lo<=int(eid[1:])<=hi),key=lambda x:int(x[1:]))
        volume=f'# {title}\n\n本卷{len(ids)}个独立详档。坐标、数字与面积口径以空间卡为准；所有内容属于钛湖城原创虚构设定。\n\n'
        for eid in ids:
            e=byid[eid];d=drafts[eid]
            volume+=f'## {eid} {e["name"]}\n\n'+card(e)+'\n'+d['body']+'\n\n'
            entry_volume[eid]=f'{prefix}-{title}.md'
        (ROOT/'分卷'/f'{prefix}-{title}.md').write_text(volume,encoding='utf-8')
        chapters.append(volume)
    overview=(ROOT/'00-城市总纲.md').read_text(encoding='utf-8')
    manual=(ROOT/'AI创作使用手册.md').read_text(encoding='utf-8')
    rules=(ROOT/'城市运行规则索引.md').read_text(encoding='utf-8')
    occupations=(ROOT/'产业与就业设定.md').read_text(encoding='utf-8')
    costs=(ROOT/'物价与生活设定.md').read_text(encoding='utf-8')
    params=(ROOT/'运行参数设定.md').read_text(encoding='utf-8')
    book=f'# 钛湖城城市设定集｜完整合订本\n\n2013年原创虚构城市正典 · {settlement_count}个村镇 · {type_counts["城市片区"]}个片区 · {interior_count}项功能区与地标 · {type_counts["居民区"]}个著名居民区\n\n'
    book+=f'本文共{total_entries}个独立地点详档。请先阅读总纲的面积、人口、位置与精度口径，再调用具体地点；城市运行与居民生活模拟规则以卷末的运行规则索引速查，产业与就业的对象、编号、层级与薪酬口径见《产业与就业设定》，物价、保障与住房库存口径见《物价与生活设定》，运行参数（技能成长与退化、通勤固定耗时、天气画面演进、事件冷却与检查点）见《运行参数设定》，规则原文见交付包内的规则确认稿。\n\n'+overview+'\n\n'+'\n\n'.join(chapters)+'\n\n'+manual+'\n\n'+occupations+'\n\n'+costs+'\n\n'+params+'\n\n'+rules
    (ROOT/'钛湖城城市设定集-完整合订本.md').write_text(book,encoding='utf-8')
    knowledge=[]
    for eid,e in byid.items():
        knowledge.append({**e,'sections':drafts[eid]['sections'],'detail_cjk_count':next(s['cjk_count']for s in stats if s['id']==eid),'volume':'分卷/'+entry_volume[eid],**drafts[eid].get('camera',{}),'derived_field_note':'camera_facing_deg与sun_relative_deg由取景段的朝向措辞按北0°顺时针推导，sun_relative_deg=(255−camera_facing_deg+180)mod360−180，负值为画面左侧、正值为右侧、绝对值大于120为相机正后；这是正文推导值，不是测绘机位坐标。','global_rules':['虚构本地坐标，x东y北，单位千米',isl_rule,'太阳默认255°方位6°高度；无水印','L066为458米全城第一、L007为368米第二且斜削冠与针状天线组合唯一；外部村镇通常不能透山看湖','文字与锚点不保证宗地或多镜头几何精确，连续镜头需控制资产']})
    (ROOT/'数据'/'AI地点知识库.json').write_text(json.dumps(knowledge,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'数据'/'AI地点知识库.jsonl').write_text('\n'.join(json.dumps(k,ensure_ascii=False)for k in knowledge)+'\n',encoding='utf-8')
    index=f'# 钛湖城城市设定集｜阅读入口\n\n## 建议先读\n\n- [城市总纲](00-城市总纲.md)\n- [完整合订本 Markdown](钛湖城城市设定集-完整合订本.md)\n- [完整合订本 Word](钛湖城城市设定集-完整合订本.docx)\n- [AI创作使用手册](AI创作使用手册.md)\n- [城市运行规则索引](城市运行规则索引.md)\n- [城市运行与居民生活模拟规则确认稿（40主题原文）](城市运行与居民生活模拟-待确认大纲.md)\n- [产业与就业设定](产业与就业设定.md)\n- [物价与生活设定](物价与生活设定.md)\n- [物价与生活总表](数据/物价与生活总表.md)\n- [运行参数设定](运行参数设定.md)\n- [运行参数总表](数据/运行参数总表.md)\n- [产业与就业总表](数据/产业与就业总表.md)\n- [空间通行总表](数据/空间通行总表.md)\n- [流程与制度总表](数据/流程制度总表.md)\n- [全域卫星聚落图](全域卫星聚落图.svg)\n- [主城区空间索引图](主城区空间索引图.svg)\n- [产业空间图层图](产业空间图层图.svg)\n- [质量核验报告](质量核验报告.md)\n\n## 全部{total_entries}个地点\n\n| ID | 名称 | 类型 | 所属 | 中心坐标 km | 面积 km² |\n|---|---|---|---|---|---|\n'
    for prefix,title,kind,lo,hi in VOLUMES:
        for eid in sorted((k for k in byid if k[0]==kind and lo<=int(k[1:])<=hi),key=lambda x:int(x[1:])):
            e=byid[eid];anchor=eid.lower()+'-'+e['name']
            index+=f'| {eid} | [{e["name"]}](分卷/{entry_volume[eid]}#{anchor}) | {e["type"]} | {e.get("parent_name","外围") if e["parent"]!="CITY" else "主城区"} | {tuple(e["center_km"])} | {e["area_km2"]} |\n'
    index+='\n## 机器可读资料\n\n[空间名录](数据/城市空间名录.json)用于硬参数；[完整AI知识库](数据/AI地点知识库.json)和[逐条JSONL](数据/AI地点知识库.jsonl)含全部七段正文，适合按ID检索。知识库另带正文推导的 `camera_facing_deg`（拍摄朝向，北0°顺时针）、`sun_relative_deg`（255°来光相对画面的角度，负值在画面左侧、绝对值大于120在相机正后）和 `lighting_baseline`（`255 deg / 6 deg` 或 `labeled variant`）；它们是推导值，不是测绘机位坐标。\n\n## 经济与开图资料\n\n[参考房价租金总表](数据/参考房价租金总表.md)给出{total_entries}条的虚构房价与租金梯度，[逐条数据](数据/参考房价租金.json)含每条的系数来源，[模型说明](数据/房价模型说明.md)解释算法与口径；这些是设定参数，不是真实市场数据。[开图清单](数据/开图清单.md)与[逐条清单数据](数据/开图清单.json)把每张待生成的图与地点ID一一对应，提示词按“ID-名称”存放在[数据/开图提示词](数据/开图提示词)目录，生成后回填 `image_file` 与 `batch`；对照当前提示词实际验收通过后，绑定 `image_prompt_sha256=prompt_sha256`（C135：绑定一律是冻结基准串，实际送入串只作 `generation_input_*` 备案）并设置已验收。缺少绑定或基准摘要变化的旧图保留为待复验，不自动沿用验收结果。**已验收的语义边界（C139）**：`accepted` 只表示机械判据验收通过（容器标识、逐字回绑、格数与档串、尺寸对回声明），不表示人工逐张目视通过、也不表示画风已过关；受用户明确委托代签的每条都在 `数据/开图验收备注.json` 留一行 `C139代签验收<ID>：`，写明执行人、委托来源原句、依据读数、「人工逐张目视未执行」与绑定摘要前12位，缺任一要素即判红——守卫是「没申报不许签」，不是「不许签」。\n\n## 岗位准入与核验资料\n\n[岗位准入总表](数据/岗位准入总表.md)展开标签、场景、合同类型、卡牌族与释放状态五套字典；正典门禁实测见[产业就业核验](数据/产业就业核验.json)；图片交付核验见[图片资产核验](数据/图片资产核验.json)与[图片复验清单](数据/图片复验清单.md)，后两者的结构判据只回答文件存在与标识容器在不在位（JPEG 走 APP1 XMP·TC260＋AIGC；PNG 走 caBX 内 C2PA 清单＋生成式来源声明，caBX 缺位时认 iTXt 里的 TC260／AIGC 字样，C136），「视觉复验」列自 C139 起按条目真实签署状态派生（判据与 `工具/signing_declaration.py` 共用一份）：已验收且代签申报合规格写「已验收（机械代签）／人工目视未执行」，仍待复验写「待人工复验」，无图写「无图，待开图」，申报不合规格则直接把闸门结论写进该列；本单不承接人工结论，也不由结构合规宣称目视通过。\n'
    index+=f'\n## 第5期空间构件与流程制度（第7期补钛马岛）\n\n[空间通行总表](数据/空间通行总表.md)列桥梁 {sp["桥梁数"]} 座（公路 {sp["公路桥数"]}／铁路 {sp["铁路桥数"]}／人行 {sp["人行桥数"]}）、渡位 {sp["渡位数"]} 处、轮渡航线 {sp["航线数"]} 条、山口通道 {sp["山口数"]} 条，另列第7期钛马岛的岛上场地 {sp["岛上场地数"]} 处、湖底隧道 {sp["湖底隧道数"]} 条、高空缆车 {sp["高空缆车数"]} 条；七张表只回答「能不能到」，不改第4期交通矩阵的中位直线耗时。岛与城市之间没有任何桥，进出岛只认 {sp["进岛通路数"]} 条通路——客渡 {sp["进岛通路分钟"]["客渡"]} 分钟、湖底隧道 {sp["进岛通路分钟"]["湖底隧道"]} 分钟、高空缆车 {sp["进岛通路分钟"]["高空缆车"]} 分钟，岛上观演容量上限取草地广场的 {sp["岛内容量人"]} 人；锚点与河流折线的距离实测见[河岸锚点核验](数据/河岸锚点核验.json)。[流程与制度总表](数据/流程制度总表.md)给出节庆与纪念日 {fl["节庆条数"]} 档（占 {fl["节庆占天次"]} 天次，逐季 {"／".join(season_name.get(s,s)+" "+str(n) for s,n in sorted(fl["节庆逐季占天"].items()))}）、机构 {fl["机构数"]} 个（含第7期两家公社，按性质字典登记为公共教育组织、不进公职表）与背景公职 {fl["公职条目数"]} 条、新条目登记对象 {fl["登记对象数"]} 类与门禁项 {fl["门禁项数"]} 条、共创转永久 {fl["共创步骤数"]} 步、删除字段 {fl["删除字段数"]} 项与 {fl["删除步骤数"]} 步、调解主体 {fl["调解主体数"]} 家与争议类别 {fl["争议类别数"]} 类、事件模板 {fl["事件模板数"]} 条、合同存续 {fl["合同存续数"]} 条，另含税种、采购分档、关系与文化阈值、界面层级、导出格式、AI 自由层与版本兼容矩阵。公职只作背景登记，不进岗位名录、招聘、合同与账本；任何流程都不中断供给、封闭路线或增加交通耗时。门禁实测见[流程制度核验](数据/流程制度核验.json)，违例自检跑 `python 工具/negtest_flows.py`。\n' if sp and fl else ''
    index+=f'\n## 第6期具名、职业条目与产业图层\n\n[公司具名名录](数据/公司具名名录.md)按锚点列出 {occ["具名公司数"]} 家逐家具名公司的四段拼接名称，另 {occ["公司数"]-occ["具名公司数"]} 条为 T1 个体户统计口径、名称为空。[职业条目总表](数据/职业条目总表.md)把 {gate["职业条目汇总"]["正典条目数"]} 条 `OCC-` 条目按大类与小类展开，覆盖 {gate["职业条目汇总"]["源表小类行数"]} 个可出卡小类，正文只住在手填真源 `数据/职业条目源表.json` 里。[产业空间图层总表](数据/产业空间图层总表.md)与[产业空间图层图](产业空间图层图.svg)把同一份数据画成 {gate["图层汇总"]["锚点数"]} 个锚点的比例符号图：气泡面积正比雇员数（半径 {gate["图层汇总"]["气泡半径km"][0]}—{gate["图层汇总"]["气泡半径km"][1]}km）、颜色取该锚点主导大类（{gate["图层汇总"]["大类数"]} 档色由大类序号派生），落点坐标直接引用名录。图层只表达规模与主导行业，不表达用地归属。门禁实测见[产业就业核验](数据/产业就业核验.json) 的 `图层汇总` 与 `职业条目汇总` 两节，违例自检跑 `python 工具/negtest_occupations.py`。\n' if occ and gate and '职业条目汇总' in gate and '图层汇总' in gate else '\n## 第6期具名与职业条目\n\n职业条目或产业图层尚未生成：先运行 `python 工具/build_occupations.py` 与 `python 工具/build_maps.py`，再重新汇编本节。\n'
    (ROOT/'阅读入口.md').write_text(index,encoding='utf-8')
    flows_line=f'- 第5期空间构件与流程制度独立核验：`数据/河岸锚点核验.json` {sp_gate["checked"]} 项锚点—河道距离实测零违例；`数据/流程制度核验.json` {fl_gate["检查项数"]}条判据实测{fl_gate["失败数"]}失败，含 {fl["节庆条数"]} 档节庆按 2013 公共日历复算、排期零双订（占 {fl["节庆占天次"]} 天次）、{fl["机构数"]} 个机构与 {fl["公职条目数"]} 条公职不越锚点岗位规模且不进岗位名录、{fl["事件模板数"]} 条事件的冷却与预告天逐条等于第4期口径、{fl["合同存续数"]} 条合同存续与合同类型字典一一对应、{fl["版本兼容行数"]} 行版本兼容逐行等于盘上实际 version、两家登记为不可挂公职的机构名下零公职、挂岛上场地的档期峰值人数不越草地广场容量。第7期湖岛侧另由 `数据/河岸锚点核验.json` 的 构件 节独立复算：{sp_gate["构件"]["判据数"]} 判实测 {sp_gate["构件"]["失败"]} 失败，含湖岛几何同源（净水面＝湖椭圆减岛面）、进岛三通路齐备与岛城无桥。违例自检 `python 工具/negtest_flows.py` 与 `python 工具/negtest_spatial.py` 逐条要求对应判据判红且夹具零残留，其当次运行输出不在本报告预填。\n' if fl and fl_gate and sp else '- 第5期空间构件或流程制度尚未生成：先运行 `python 工具/build_spatial_lists.py`、`python 工具/build_flows.py` 与两道 verify，再重新汇编本节。\n'
    occ_line=f'- 产业与就业层独立核验：`数据/产业就业核验.json` {gate["检查项数"]}条判据实测{gate["失败数"]}失败；{occ["岗位锚点数"]}个岗位锚点逐区守恒误差为0，公司{occ["公司数"]}家（具名{occ["具名公司数"]}、T5恰好{occ["T5数"]}家），岗位卡{occ["岗位卡数"]}张，雇员{occ["雇员总数"]}人等于名录岗位总数。违例自检 `python 工具/negtest_occupations.py` 逐条要求对应判据判红且夹具零残留，其当次运行输出不在本报告预填。{'' if not adm else f'岗位准入字典实测标签{adm["标签数"]}、场景{adm["场景数"]}、合同类型{adm["合同类型数"]}、卡牌族{adm["卡牌族数"]}、释放状态{adm["释放状态数"]}。'}{"职业条目 " + str(gate["职业条目汇总"]["正典条目数"]) + " 条／" + str(gate["职业条目汇总"]["源表小类行数"]) + " 个可出卡小类，名称唯一数与之相等；产业图层 " + str(gate["图层汇总"]["锚点数"]) + " 锚点／" + str(gate["图层汇总"]["大类数"]) + " 大类，逐锚点公司数、岗位卡数与雇员数按正典独立复算逐格对账，落点坐标逐条对回名录。" if "职业条目汇总" in gate and "图层汇总" in gate else ""}{'岗位准入字典尚未生成：先运行 python 工具/build_admission.py，再重新汇编本节。' if occ and gate and not adm else ''}\n' if occ and gate else '- 产业与就业层尚未生成：先运行 `python 工具/build_occupations.py` 与 `python 工具/verify_occupations.py`，再重新汇编本节。\n'
    relief_g=gate.get("救助汇总",{})if gate else{}
    opening_g=gate.get("开局汇总",{})if gate else{}
    dic_g=adm if adm else gate.get("字典汇总",{})if gate else{}
    band=opening_g.get("开局区间")or[0,0]
    report=f'# 钛湖城设定集质量核验报告\n\n版本1.0；基准年2013；虚构设定。\n\n## 自动核验实测\n\n- 独立条目：{len(drafts)}。\n- 分类：外围聚落{settlement_count}；片区{type_counts["城市片区"]}；功能区{type_counts["功能区"]}；地标{type_counts["标志性建筑"]}；居民区{type_counts["居民区"]}。\n- 详档正文汉字合计：{result["total_cjk"]:,}；每条最少{result["min_cjk"]}、最多{result["max_cjk"]}字。统计不含空间卡、阿拉伯数字和标点。\n- {total_entries}个ID和名称唯一，标题与空间名录完全一致。\n- 每条七个必需段落完整；未发现占位符、U+2026省略号、替换乱码或完全重复的长段落。\n- 片区面积与中心湖面积（含湖内钛马岛占位）闭合到主城区毛面积，四舍五入误差低于0.001平方公里；净水面按湖椭圆面积扣除岛面积独立复算。\n- 所有内部地点锚点在所属扇区范围内，既不落入中心湖水面，也不落在钛马岛上；湖岛只由空间通行构件层的场地与通路承载。\n- 精选住区人口不超过父片区人口；全域人口总账闭合，无重复累加。\n- 正文中的{len(references)}次标准ID引用均指向现有条目。\n- 逐条比对正文声明与空间名录：{total_entries}条位置段的中心坐标符合0.006千米容差；面积与建筑面积从位置段提取，层数与高度从位置及锁定段提取，人口、户数及岗位从位置与人群段提取，限高从位置、规划、外观及锁定段提取。识别到的完整数值及相应字段或单位均与名录一致，缺项或相互矛盾会阻止汇编；这不等于穷尽全文所有自然语言数字声明。{numeric_claims}处跨地点距离声明与名录几何的误差均控制在0.4千米以内。\n- 逐条校验光照基准：{light_checked}条默认光条目的拍摄朝向从取景段措辞推导，255°来光相对画面的方向与 rel=(255−朝向+180)mod360−180 的判定全部一致，无左右或前后写反；{light_variants}条显式标注的夜间、入夜、清晨、晴日、雨后阴天变体不参与该校验，也不回填黄昏光。朝向与相对方位作为推导字段写入AI地点知识库，并标注为正文推导值而非测绘机位坐标。\n- 开图与画风侧的口径闸门独立于本段执行，本段只登记入口、不预填读数：`python 工具/verify_prompt_baseline.py`（逐条对拍 `数据/提示词基准冻结.json`，C133；图生图格按 C135 绑冻结串、实际送入串另存为第二字段。其中「冻结后落盘的格绑到过期基准」自 2026-11-07 起只认占格备注里逐字复述了前 12 位的「维持原绑定」申报作免红通道，未申报照旧判红，撤销或重绑归人工；C139 代签那轮已把当时命中该通道的条目全部重绑到冻结串并撤其申报，条数取该轮登记，通道本身保留给后续轮次）、`python 工具/verify_readout_stance.py`（C134：细尺度方差地板与日面分档线只作读数、不作判废依据，判据措辞复活／标注丢失／实验产物缺件或分组不符／R1 画风读数覆盖面与清单现算格集或读数 JSON 对不上即判红；R1 那支守的是 C139 代签轮未收口偏差的举证面，阈值不在闸门重搜、改为钉正典表 sha12 加声明阈值复算错分）、`python -X utf8 工具/reshoot_campaign_2026_11_06/container_profile.py`（C136：PNG 容器画像不按出图通道成立）、`python -X utf8 工具/reshoot_campaign_2026_11_06/pick_primary_cell.py`（C138：四向挂载里逐条指认要投的主向格并派生 primary_cells.json，重投面按每条 1 格、其余三向另立四向控制资产缺项，`build_queue.py` 复用同一份定位规则不另写一套）。四者的判红类别、扫描文件数与产物件数以各自本轮输出为准，另有各自的 `--negtest` 违例注入自证。画风判废权一律在人工目视，这些核验脚本本身都不写 `accepted`；C139 起 `accepted` 只表示机械判据验收通过，受委托代签由单独的签署工具执行并逐条留申报行，机检读数（含 CLIP 画风分离度）仍只作读数、不得写成判废依据。画风侧对 R1 组的重读另出独立产物 `工具/reshoot_campaign_2026_11_06/clip_style_scores_r1.tsv` 与 `clip_style_r1_readings.json`（由 `clip_style_r1.py` 生成，导入 `clip_style.py` 的同一套模板与阈值算法而不重跑正典实验），正典 `clip_style_scores.tsv` 与 `style_sep_final.tsv` 一字未动；该轮照片侧枚数与未收口偏差以裁定登记为准，本报告不抄第二份。\n- 投出去之后的三段同属本段登记、同样不预填读数：`python -X utf8 工具/reshoot_campaign_2026_11_06/verify_round.py <回绑源> [R1|R2]` 做投后核验（实发串与 transcript 逐字相等、按 `frozen_at_ms` 分带且落盘面恒为 1 枚、容器按 C136 至少其一在位、尺寸对回清单声明；发起次数本身是判据维度，回绑源可给单份 jsonl、逗号分隔的多份，或指向 transcripts_r1.json／transcripts_r2.json 这类登记件，登记件缺份或所指 transcript 不在盘一律显式判红）；`python -X utf8 工具/reshoot_campaign_2026_11_06/backfill_round.py <R1|R2>` 只把判绿条目替换上台账 replaced_cell 那一格并写机械对账读数，脚本不写也不撤 `image_prompt_sha256`、不改 `status`、不签 `acceptance`；签署是另一条通道：`python 工具/sign_acceptance.py`（C139）只在用户明确委托代签时运行，按冻结快照绑 `image_prompt_sha256=prompt_sha256`、置 `status=已验收`，并往 `数据/开图验收备注.json` 逐条追加代签申报行（执行人／委托来源原句／依据读数／「人工逐张目视未执行」／绑定摘要前12位／该枚画风读数），历史回填读数行一律不改写；申报判据只有一份真源 `工具/signing_declaration.py`，闸门侧 `工具/test_image_assets.py` 与产物侧「视觉复验」列共用它，没申报或申报缺要素的已验收照旧判红；产物过期另由两道对拍闸门管——`python 工具/verify_asset_report_freshness.py` 把 `数据/图片资产核验.json` 与 `数据/图片复验清单.md` 逐字段对回现算（口径散文单独成一类判据，专治数字新旧相同而判据已换档那类假绿），`python 工具/verify_review_freshness.py` 把 `数据/人工复看套件/` 的工作单与联络表逐格对回 `数据/开图清单.json`，两者都只读盘上真实产物、按内容对拍、不按 mtime 猜、不修文件。三者的判红类别与条数以各自本轮输出为准，`--negtest` 各自注入自证。\n{occ_line}{flows_line}\n## 交付件核验\n\nWord保真核验独立执行：导出后运行 `python 工具/verify_docx.py`，实测结果见[Word核验结果](数据/Word核验结果.json)。该结果记录源Markdown和DOCX的SHA-256，只有两个摘要均与当前文件一致且passed为true时，才表示当前Word通过了包结构、XML、按顺序的正文及表格内容核验；数字和负号均参与比对。编译成功不等于Word同步，旧结果不能用于新文件。表格、单元格、标题、分页和目录域数量以实测JSON为准，不在本报告里预填通过数字。官方XSD模式校验未做。渲染级目视不由脚本代签：人工结论的唯一可编辑源是 `数据/Word渲染目视.json`，`数据/Word核验结果.json` 的 `rendering_verified` 只在该记录绑定当前 DOCX 摘要、五项范围（封面计数／目录页码／分卷首页／表格页／末页截断）齐全、结论为通过且无未收口问题时才为真；docx 一旦重导，摘要变化即令该结论自动失效，分页观感与目录页码须重新人工确认。\n\n## 核验边界\n\n以上自动测试不等于每句自然语言均已经过专家审定，不证明道路、防洪、净空或建筑设计达到工程标准。地图展示锚点，不含精确宗地多边形；河流缓冲与建筑完整基底仍需场景落图核验。产业与就业层的薪酬带由参数公式展开，红线取「住所锚÷0.40」与「住所锚＋本圈层基本篮子」的大值并对所有岗位层生效：本期物价与生活成本包已把篮子接入该红线，全城 {gate.get("物价汇总",{}).get("被顶起卡数",0)} 张岗位卡的下限被新线顶起，涉及 {gate.get("物价汇总",{}).get("被顶起名额数",0)} 个名额，集中在产业小镇与特色村落，两个城市圈层仍按住所四成线；低毛利行业的起薪带宽因此收窄。薪酬带仍是参数区间，不构成对每户支出的逐笔核算；公司逐家具名标记已展开 {occ["具名公司数"]} 家（另 {occ["公司数"]-occ["具名公司数"]} 条为个体户统计口径），名称文本已按源表「命名」块四段拼接逐户填充，见 `数据/公司具名名录.md`；逐条职业内容已按 `OCC-` 编号展开 {gate.get("职业条目汇总",{}).get("正典条目数",0)} 条、覆盖 {gate.get("职业条目汇总",{}).get("源表小类行数",0)} 个可出卡小类，见 `数据/职业条目总表.md`；产业空间图层另出 `数据/产业空间图层.json` 与 `产业空间图层图.svg`，气泡面积正比雇员数、颜色取主导大类，只表达规模与主导行业，不表达用地归属。第9期已把手填真源 `数据/卡牌实例源表.json` 的逐张卡牌实例展开 {dic_g.get("卡牌实例数",0)} 张（{dic_g.get("已展开族数",0)} 族已展开／{dic_g.get("未展开族数",0)} 族未展开，未展开族数为 0 即十二族齐观），开局背景卡逐张有名 {dic_g.get("背景卡实例数",0)} 张；两个读数取自 数据/岗位准入正典.json 的 汇总，不在本报告里预填。岗位准入字典本期只给出口径、ID 与层级绑定：标签升阶与退化阈值已由第4期运行参数包落定（0／12／24／48／96 月），生活保障标准与押金、初始资金、欠费宽限已由第3期物价与生活成本包挂到圈层篮子上，失业救助三列金额已由第8期落到同一张篮子（内湖环全额月 {relief_g.get("逐圈层全额月",{}).get("内湖环",0)}／递减月 {relief_g.get("逐圈层递减月",{}).get("内湖环",0)}／连发总额 {relief_g.get("逐圈层连发总额",{}).get("内湖环",0)} 钛币，全额 {relief_g.get("全额月数",0)} 月转递减 {relief_g.get("递减月数",0)} 月、最长连发 {relief_g.get("最长连发月数",0)} 月，按登记失业者本人发放、不乘户均规模），五维开局区间 {band[0]}—{band[1]} 与背景卡权重五类占比也已在第8期落为查表值（权重和 {opening_g.get("权重和",0)}、候选组合数 {opening_g.get("候选组合数",0)}），调解受理主体、争议类别、拉黑后合同存续、公共采购与税种、关系与文化阈值、界面与导出、AI 自由层与版本兼容矩阵已由第5期流程与制度包落为查表值，逐张卡牌实例按第9期分期展开、当前读数 {dic_g.get("卡牌实例数",0)} 张。语义一致性另做针对性抽查，不将抽样宣称为全文逐字人工复核。连续影像须配套平面、模型或深度控制图，不能仅凭文字保证几何一致。\n\n## 可复核数据\n\n详见[逐项核验结果](数据/质量核验结果.json)。原稿在分卷/原稿中保留供编辑追溯，最终阅读应以分卷成稿和完整合订本为准。\n'
    if warnings:report+='\n## 篇幅提示\n\n'+ '\n'.join('- '+w for w in warnings)+'\n'
    (ROOT/'质量核验报告.md').write_text(report,encoding='utf-8')

if __name__=='__main__':main()
