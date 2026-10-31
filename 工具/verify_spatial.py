import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
data=json.loads((ROOT/'数据'/'城市空间名录.json').read_text(encoding='utf-8'))


def distance_to_segment(p,a,b):
    vx,vy=b[0]-a[0],b[1]-a[1]
    t=max(0,min(1,((p[0]-a[0])*vx+(p[1]-a[1])*vy)/(vx*vx+vy*vy)))
    return math.hypot(p[0]-a[0]-t*vx,p[1]-a[1]-t*vy)


results=[]
for e in data['entries']:
    if e['type'] not in ['标志性建筑','居民区']:continue
    constraints=[]
    for river in data['rivers']:
        points=river['centerline_km']
        d=min(distance_to_segment(e['center_km'],a,b)for a,b in zip(points,points[1:]))*1000
        required=river['width_m'][1]/2+30
        constraints.append(dict(river=river['id'],distance_to_centerline_m=round(d,2),required_m=required,passes_anchor_buffer=d>=required))
    results.append(dict(id=e['id'],center_km=e['center_km'],constraints=constraints))
failures=[r for r in results if any(not c['passes_anchor_buffer']for c in r['constraints'])]
output=dict(checked=len(results),rule='锚点距离河流折线>=最大水宽/2+30米；不替代完整地块缓冲审查',failures=failures,results=results)
(ROOT/'数据'/'河岸锚点核验.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(checked=len(results),failures=failures),ensure_ascii=False,indent=2))
if failures:raise SystemExit(1)
