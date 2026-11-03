import colorsys
import html
import json
import math
from pathlib import Path

from anchors import RINGS, entry_ring

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT/'数据'/'城市空间名录.json').read_text(encoding='utf-8'))
ENTRIES = DATA['entries']
ECON = json.loads((ROOT/'数据'/'产业就业正典.json').read_text(encoding='utf-8'))
COLORS = ['#d8e5df','#e3e9cf','#d7e2eb','#ede0cd','#d8e8e5','#eee6d5','#e9d9d3','#e2ded4','#d7e5e6','#dfebd7']

class Map:
    def __init__(self, title, subtitle, scale, cx, cy, width=1800, height=1500):
        self.scale,self.cx,self.cy=scale,cx,cy
        self.parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#faf8f2"/><style>text{{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;fill:#263c41}}.small{{font-size:13px}}.label{{paint-order:stroke;stroke:#faf8f2;stroke-width:3px;stroke-linejoin:round}}</style>']
        self.text(65,65,title,34)
        self.text(65,103,subtitle,17)
    def xy(self,p): return self.cx+p[0]*self.scale,self.cy-p[1]*self.scale
    def text(self,x,y,t,size=16,fill=None,anchor='start',cls=''):
        self.parts.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}" class="{cls}"'+(f' style="fill:{fill}"' if fill else '')+'>'+html.escape(str(t))+'</text>')
    def line(self,points,color='#87948a',width=1,dash=None):
        s=' '.join(f'{self.xy(p)[0]:.2f},{self.xy(p)[1]:.2f}' for p in points)
        self.parts.append(f'<polyline points="{s}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>')
    def circle(self,p,r,fill='none',stroke='#6d837b',width=1):
        x,y=self.xy(p)
        self.parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r*self.scale:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')
    def polygon(self,points,fill,stroke='#ffffff',width=1):
        s=' '.join(f'{self.xy(p)[0]:.2f},{self.xy(p)[1]:.2f}' for p in points)
        self.parts.append(f'<polygon points="{s}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')
    def water(self, clip_radius=None):
        if clip_radius:
            self.parts.append(f'<defs><clipPath id="water-clip"><circle cx="{self.cx}" cy="{self.cy}" r="{clip_radius*self.scale}"/></clipPath></defs><g clip-path="url(#water-clip)">')
        for r in DATA['rivers']: self.line(r['centerline_km'],'#75a9bd',max(3,self.scale*(.19 if r['id']=='W01' else .36)))
        if clip_radius:
            self.parts.append('</g>')
        x,y=self.xy([0,0]);self.parts.append(f'<ellipse cx="{x}" cy="{y}" rx="{3.2*self.scale}" ry="{2.1*self.scale}" fill="#bedbe3" stroke="#568b9c" stroke-width="1.8"/>')
        self.text(x,y-4,'钛 湖',25,anchor='middle');self.text(x,y+22,'21.1115 km²',13,anchor='middle')
    def compass_scale(self,x,y,length):
        self.text(x,y-23,'N',18,anchor='middle');self.parts.append(f'<path d="M{x},{y-15} l-8,27 l8,-7 l8,7 Z" fill="#284b50"/>')
        pixels=length*self.scale
        self.parts.append(f'<path d="M90,1390 h{pixels:.1f} M90,1385 v10 M{90+pixels:.1f},1385 v10" stroke="#284b50" stroke-width="3"/>')
        self.text(90,1376,f'{length} km',14)
    def save(self,name):
        self.text(65,1448,'THC-LOCAL-2013 · x东 / y北 · 单位千米 · 原创虚构设定 · 锚点与规划边界示意，不是宗地测绘或工程图',15)
        self.parts.append('</svg>');(ROOT/name).write_text(''.join(self.parts),encoding='utf-8')

def polar(r,a):
    t=math.radians(a);return [r*math.sin(t),r*math.cos(t)]

regional=Map('钛湖城 / 全域与卫星聚落','24个重点村镇 · 四面环山 · 清岚河入湖，澜川出城 · 山体带为示意范围',15.5,640,735)
for x in range(-35,36,5): regional.line([[x,-32],[x,32]],'#e5e7df',.7)
for y in range(-30,31,5): regional.line([[-36,y],[36,y]],'#e5e7df',.7)
regional.polygon([[-36,-32],[36,-32],[36,32],[-36,32]],'none','#9aa69c',1.5)
for name,pts,at in [
('北屏山 / 900—1450m',[[-13,12],[-10,18],[5,18],[11,13],[8,11],[-5,12]],[-3,14.7]),
('东岚山 / 650—1180m',[[12,12],[18,9],[18,-8],[13,-12],[11,-8],[12,5]],[15,-1]),
('南原诸岭 / 560—980m',[[-13,-12],[-8,-18],[5,-18],[12,-13],[6,-11],[-6,-12]],[-2,-14.9]),
('西岭 / 780—1320m',[[-12,11],[-18,8],[-18,-8],[-13,-12],[-11,-6],[-12,6]],[-15,1])]:
    regional.polygon(pts,'#dce6d4','#c4d2be',1)
    xx,yy=regional.xy(at);regional.text(xx,yy,name,13,anchor='middle',cls='label')
regional.circle([0,0],10.2,'#f0e7d4','#ae9e7c',2)
regional.water()
regional.text(640,795,'主城区 326.85 km²',14,anchor='middle')
for e in ENTRIES:
    if not e['id'].startswith('S'):continue
    x,y=regional.xy(e['center_km']);color='#b67640' if e['type']=='产业小镇' else '#54826b'
    regional.circle(e['center_km'],.35,color,'#ffffff',1.5)
    regional.text(x+10,y-7,e['id'],14,color,cls='label')
regional.text(1250,200,'卫星小镇与特色村落',23)
for i,e in enumerate(e for e in ENTRIES if e['id'].startswith('S')):
    y=239+i*39
    regional.text(1250,y,f"{e['id']}  {e['name']}",17)
    regional.text(1250,y+17,f"({e['center_km'][0]}, {e['center_km'][1]}) km · {e['area_km2']} km²",12,'#617475')
regional.text(1250,1220,'棕点：产业小镇（16）  绿点：村落（8）',14)
regional.text(1250,1247,'坐标锚点不等于聚落的完整用地边界。',14)
regional.text(1250,1274,'清岚河：西北 → 钛湖；澜川：钛湖 → 东南。',14)
regional.compass_scale(1140,190,10)
regional.save('全域卫星聚落图.svg')

def _n(*types):
    return sum(1 for e in ENTRIES if e['type'] in types)

urban=Map('钛湖城 / 主城区空间索引',f"{_n('城市片区')}片区 + {_n('功能区')}功能区 + {_n('标志性建筑')}地标 + {_n('居民区')}著名居民区 · ID与详档、数据名录一一对应",54,665,745)
for i in range(20):
    e=next(e for e in ENTRIES if e['id']==f'D{i+1:02d}');s=e['sector'];a=s['angle_center_deg']
    r1,r2=s['inner_radius_km'],s['outer_radius_km']
    points=[polar(r2,a-18+j*.6) for j in range(61)]+([polar(r1,a+18-j*.6) for j in range(61)] if r1 else [[0,0]])
    urban.polygon(points,COLORS[i%10],'#faf8f2',1.8)
for v in range(-10,11,2):
    urban.line([[v,-10.6],[v,10.6]],'#b8c6be',.5)
    urban.line([[-10.6,v],[10.6,v]],'#b8c6be',.5)
    x,y=urban.xy([v,-10.9]);urban.text(x,y,str(v),12,anchor='middle')
    x,y=urban.xy([-10.9,v]);urban.text(x,y+4,str(v),12,anchor='end')
for r in [5.7,9.9]:urban.circle([0,0],r,'none','#b99e79',1.4)
urban.water(10.8)
for e in ENTRIES:
    if e['id'][0] not in 'FLR':continue
    x,y=urban.xy(e['center_km']);p=e['id'][0]
    color={'F':'#246d73','L':'#ab5e2d','R':'#526777'}[p]
    if p=='L':urban.polygon([[e['center_km'][0],e['center_km'][1]+.10],[e['center_km'][0]-.09,e['center_km'][1]-.07],[e['center_km'][0]+.09,e['center_km'][1]-.07]],color,'#fff',.6)
    else:urban.circle(e['center_km'],.075 if p=='F' else .043,color,'#ffffff',.5)
    urban.text(x+5,y-5,e['id'],10 if p=='R' else 11,color,cls='label')
for e in (e for e in ENTRIES if e['id'].startswith('D')):
    x,y=urban.xy(polar(5 if e['ring']=='内湖环' else 8.92,e['sector']['angle_center_deg']))
    urban.text(x,y,e['id'],17,'#2c4c48',anchor='middle',cls='label')
urban.text(1285,195,'片区导航',25)
for i,e in enumerate(e for e in ENTRIES if e['id'].startswith('D')):
    y=232+i*45
    urban.text(1285,y,f"{e['id']}  {e['name']}",17)
    urban.text(1285,y+18,f"{e['ring']} · {e['area_km2']:.2f} km² · {e['population']:,}人",12,'#617475')
urban.text(1285,1170,'F  功能区   L  地标建筑   R  居民区',16)
urban.text(1285,1202,'D01—D10：内湖环；D11—D20：外城环。',14)
urban.text(1285,1227,'所有坐标以湖心为原点，不是真实经纬度。',14)
urban.text(1285,1252,'圆形规划边界与道路是概念基准，需地形落图。',14)
urban.text(1285,1277,'湖内不布置建筑；建筑锚点并非精确建筑基底。',14)
urban.compass_scale(1190,170,2)
urban.save('主城区空间索引图.svg')

# ——— 产业空间图层 ———
# 一份图层，三个出口：SVG 示意、机器可读 数据/产业空间图层.json、人读 数据/产业空间图层总表.md。
# 数字只从 数据/产业就业正典.json 现算，不在这里留任何手填常量；闸门第 31 条按同一口径独立重算并对账。
BY_ID={e['id']:e for e in ENTRIES}
CLASSES=ECON['行业']['大类']
CLASS_NAME={c['id']:c['名称'] for c in CLASSES}
CLASS_ATTR={c['id']:c['经济属性'] for c in CLASSES}
CLASS_COLOR={c['id']:'#%02x%02x%02x'%tuple(round(255*v) for v in colorsys.hls_to_rgb(i/len(CLASSES),.60,.42))
             for i,c in enumerate(CLASSES)}
SCALE,CX,CY=15.5,640,735

per_anchor={}
for comp in ECON['公司']:
    a=per_anchor.setdefault(comp['锚点'],{'公司数':0,'岗位卡数':0,'雇员数':0,'分布':{}})
    a['公司数']+=1
    a['岗位卡数']+=len(comp['岗位卡'])
    a['雇员数']+=comp['雇员数']
    d=a['分布'].setdefault(comp['大类'],{'公司数':0,'雇员数':0,'岗位卡数':0})
    d['公司数']+=1
    d['雇员数']+=comp['雇员数']
    d['岗位卡数']+=len(comp['岗位卡'])

def dominant(a):
    return max(a['分布'].items(),key=lambda kv:(kv[1]['雇员数'],kv[1]['公司数'],kv[0]))[0]

max_emp=max(a['雇员数'] for a in per_anchor.values())
anchor_rows=[]
for zid in sorted(per_anchor):
    a=per_anchor[zid];e=BY_ID[zid];ring=entry_ring(e,BY_ID)
    dom=dominant(a)
    anchor_rows.append({'锚点':zid,'名称':e['name'],'类型':e['type'],'圈层':ring,
        'center_km':e['center_km'],'公司数':a['公司数'],'岗位卡数':a['岗位卡数'],'雇员数':a['雇员数'],
        '气泡半径km':round(.28+1.05*math.sqrt(a['雇员数']/max_emp),3),
        '主导大类':dom,'主导大类名称':CLASS_NAME[dom],'主导大类色':CLASS_COLOR[dom],
        '主导雇员占比':round(a['分布'][dom]['雇员数']/a['雇员数'],3),
        '大类分布':{k:dict(v) for k,v in sorted(a['分布'].items())},
        '落大类数':len(a['分布'])})

class_rows=[]
for c in CLASSES:
    hits=[r for r in anchor_rows if c['id'] in r['大类分布']]
    class_rows.append({'id':c['id'],'名称':c['名称'],'经济属性':c['经济属性'],'色':CLASS_COLOR[c['id']],
        '公司数':sum(r['大类分布'][c['id']]['公司数'] for r in hits),
        '岗位卡数':sum(r['大类分布'][c['id']]['岗位卡数'] for r in hits),
        '雇员数':sum(r['大类分布'][c['id']]['雇员数'] for r in hits),
        '落点数':len(hits),'主导落点数':sum(1 for r in anchor_rows if r['主导大类']==c['id']),
        '落点':[r['锚点'] for r in hits]})

ring_rows=[]
for ring in RINGS:
    hits=[r for r in anchor_rows if r['圈层']==ring]
    ring_rows.append({'圈层':ring,'锚点数':len(hits),'公司数':sum(r['公司数'] for r in hits),
        '岗位卡数':sum(r['岗位卡数'] for r in hits),'雇员数':sum(r['雇员数'] for r in hits)})

LAYER={'version':1,'fictional':True,'来源':'数据/产业就业正典.json + 数据/城市空间名录.json',
    '图幅':'产业空间图层图.svg',
    '口径':'按岗位锚点聚合正典里的公司与岗位卡：气泡面积正比于该锚点雇员数（半径＝0.28＋1.05×√(雇员数/最大锚点雇员数) 千米），'
           '颜色取该锚点雇员最多的主导大类，平局依次比公司数与大类 ID。锚点坐标直接引用名录 center_km，不是新增坐标。'
           '逐大类与逐圈层的小计由同一批锚点行加总而来。本图只表达规模与行业主导，不表达用地边界、楼宇体量或通勤流向；'
           '逐锚点数字看 数据/产业空间图层总表.md，机器可读看本文件。门禁第 31 条按正典独立重算本文件的全部计数。',
    '投影':{'px_per_km':SCALE,'cx':CX,'cy':CY,'原点':'湖心','轴向':'x 东 / y 北','单位':'千米'},
    '汇总':{'岗位锚点数':len(anchor_rows),'公司数':sum(r['公司数'] for r in anchor_rows),
        '岗位卡数':sum(r['岗位卡数'] for r in anchor_rows),'雇员总数':sum(r['雇员数'] for r in anchor_rows),
        '大类数':len(class_rows),'最大单锚雇员数':max_emp,
        '气泡半径km':[round(.28,3),round(.28+1.05,3)],
        '逐圈层':{r['圈层']:[r['锚点数'],r['公司数'],r['雇员数']] for r in ring_rows}},
    '大类':class_rows,'圈层':ring_rows,'锚点':anchor_rows}
(ROOT/'数据'/'产业空间图层.json').write_text(json.dumps(LAYER,ensure_ascii=False,indent=2),encoding='utf-8')

industry=Map('钛湖城 / 产业空间图层',
    f"{LAYER['汇总']['岗位锚点数']} 个岗位锚点 · {LAYER['汇总']['公司数']} 家公司 · {LAYER['汇总']['雇员总数']} 个岗位 · "
    f"气泡面积正比雇员数，颜色取主导大类 · 落点坐标引用名录",SCALE,CX,CY)
for x in range(-35,36,5): industry.line([[x,-32],[x,32]],'#e9ebe2',.6)
for y in range(-30,31,5): industry.line([[-36,y],[36,y]],'#e9ebe2',.6)
for i in range(20):
    e=next(x for x in ENTRIES if x['id']==f'D{i+1:02d}');s=e['sector']
    a=s['angle_center_deg'];r1,r2=s['inner_radius_km'],s['outer_radius_km']
    pts=[polar(r2,a-18+j*.6) for j in range(61)]+([polar(r1,a+18-j*.6) for j in range(61)] if r1 else [[0,0]])
    industry.polygon(pts,'#f2efe4','#e2ddcd',.8)
industry.circle([0,0],10.2,'none','#ae9e7c',1.6)
industry.water()
for r in anchor_rows:
    color=r['主导大类色'];rad=r['气泡半径km']
    industry.circle(r['center_km'],rad,color,'#ffffff',1.1)
    x,y=industry.xy(r['center_km'])
    industry.text(x,y-rad*SCALE-2,r['锚点'],8.5 if r['锚点'][0]=='F' else 11,'#33555c',anchor='middle',cls='label')
industry.text(1250,200,'主导大类图例',23)
for i,c in enumerate(class_rows):
    y=243+i*44
    industry.parts.append(f'<rect x="1250" y="{y-13}" width="20" height="13" fill="{c["色"]}" stroke="#8c9a92" stroke-width=".6"/>')
    industry.text(1278,y,f"{c['id']}  {c['名称']}",16)
    industry.text(1278,y+17,f"{c['经济属性']} · {c['公司数']} 家 / {c['雇员数']:,} 岗 · 落 {c['落点数']} 锚点（主导 {c['主导落点数']}）",12,'#617475')
industry.text(1250,1215,'圈层小计（锚点／公司／岗位）',17)
for i,r in enumerate(ring_rows):
    industry.text(1250,1244+i*22,f"{r['圈层']}：{r['锚点数']} ／ {r['公司数']} ／ {r['雇员数']:,}",14,'#617475')
industry.text(1250,1350,'气泡只比面积，不比对用地范围；锚点坐标引用名录 center_km。',14)
industry.text(1250,1374,'逐锚点与逐大类明细见 数据/产业空间图层总表.md。',14)
industry.text(1250,1398,'颜色由大类序号均分色相派生，与正典无独立色值真源。',14)
industry.compass_scale(1140,190,10)
industry.save('产业空间图层图.svg')

tbl=['# 钛湖城 / 产业空间图层总表','',
     '本表由 `python 工具/build_maps.py` 从 `数据/产业就业正典.json` 与 `数据/城市空间名录.json` 现算展开，不可手改。',
     '图幅：`产业空间图层图.svg`；机器可读：`数据/产业空间图层.json`。门禁第 31 条按同一口径独立重算本表全部计数。','',
     f"口径：{LAYER['口径']}",'',
     f"汇总：岗位锚点 {LAYER['汇总']['岗位锚点数']} 个 · 公司 {LAYER['汇总']['公司数']} 家 · 岗位卡 {LAYER['汇总']['岗位卡数']} 张 · 雇员 {LAYER['汇总']['雇员总数']} 人 · 大类 {LAYER['汇总']['大类数']} 个；最大单锚雇员 {max_emp:,} 人，气泡半径 {LAYER['汇总']['气泡半径km'][0]}—{LAYER['汇总']['气泡半径km'][1]} 千米。",
     f"投影：{LAYER['投影']['px_per_km']} 像素／千米，原点湖心，x 东 / y 北。",'',
     '## 逐圈层小计','','| 圈层 | 锚点数 | 公司数 | 岗位卡数 | 雇员数 |','|---|---|---|---|---|']
for r in ring_rows:
    tbl.append(f"| {r['圈层']} | {r['锚点数']} | {r['公司数']} | {r['岗位卡数']} | {r['雇员数']:,} |")
tbl+=['','## 逐大类汇总','','| 大类 | 名称 | 经济属性 | 公司数 | 岗位卡数 | 雇员数 | 落点数 | 作为主导的锚点数 |','|---|---|---|---|---|---|---|---|']
for c in class_rows:
    tbl.append(f"| {c['id']} | {c['名称']} | {c['经济属性']} | {c['公司数']} | {c['岗位卡数']} | {c['雇员数']:,} | {c['落点数']} | {c['主导落点数']} |")
tbl+=['','## 逐锚点明细','','| 锚点 | 名称 | 类型 | 圈层 | x,y (km) | 公司数 | 岗位卡数 | 雇员数 | 主导大类 | 落大类数 | 主导雇员占比 | 大类分布（公司数/雇员数） |','|---|---|---|---|---|---|---|---|---|---|---|---|']
for r in anchor_rows:
    dist='、'.join(f"{k} {v['公司数']}/{v['雇员数']:,}" for k,v in r['大类分布'].items())
    tbl.append(f"| {r['锚点']} | {r['名称']} | {r['类型']} | {r['圈层']} | {r['center_km'][0]}, {r['center_km'][1]} | {r['公司数']} | {r['岗位卡数']} | {r['雇员数']:,} | {r['主导大类']} {r['主导大类名称']} | {r['落大类数']} | {r['主导雇员占比']} | {dist} |")
tbl+=['','## 说明','',
      '- 气泡与颜色是同一批正典计数的两种编码，图上不做用地边界推断。',
      '- A01 全类为公共部门背景在册，岗位卡不可申请，但雇员数仍守恒进锚点规模，因此图层里会出现且只按同一口径计数。',
      '- T1 个体户统计口径的公司无名称，仍计入公司数与雇员数。',
      '- 聚落岗位数不等于常住人口。','']
(ROOT/'数据'/'产业空间图层总表.md').write_text('\n'.join(tbl),encoding='utf-8')
print(f"Generated 3 SVG maps and the industry layer from the canonical registry: "
      f"{len(anchor_rows)} 锚点 / {len(class_rows)} 大类 / {LAYER['汇总']['公司数']} 公司 / {LAYER['汇总']['雇员总数']} 雇员")
