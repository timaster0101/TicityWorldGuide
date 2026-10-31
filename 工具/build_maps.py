import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT/'数据'/'城市空间名录.json').read_text(encoding='utf-8'))
ENTRIES = DATA['entries']
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

urban=Map('钛湖城 / 主城区空间索引','20片区 + 40功能区 + 60地标 + 120著名居民区 · ID与详档、数据名录一一对应',54,665,745)
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
print('Generated 2 SVG maps from the canonical registry.')
