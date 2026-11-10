# -*- coding: utf-8 -*-
"""容器画像实测器：逐枚数 PNG 私有块 caBX 处数与 iTXt 是否含 TC260/AIGC，产物落本目录。

为什么要单独跑：C136 裁定「AIGC 标识容器不按出图通道成立」要靠同通道的两批格互反的画像撑着，
早前各批的 measure.json 只落了 caBX=1 那一侧，本轮重投与画风实验那几枚没有仓内读数文件。

统计面：SAMPLES 里逐枚现读文件字节（仓库外的 vibe_images 与仓内 E1 定档目录都算），不排除任何块；
聚合面来自 MEASURES 这 9 份各批实测 JSON 的 container 字段，只数其中 dict 型的行。
跑法：python 工具/reshoot_campaign_2026_11_06/container_profile.py
"""
import glob
import io
import json
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
SET = os.path.dirname(os.path.dirname(HERE))          # 钛湖城城市设定集
VIBE = os.path.join(os.path.dirname(SET), 'vibe_images')  # 仓库外的出图目录
E1 = os.path.join(SET, '数据', '视觉控制资产', 'E1定档-20261103')
OUT = os.path.join(HERE, 'container_profile.json')

MEASURES = glob.glob(os.path.join(SET, '工具', '*', '*measure*.json'))


def profile(path):
    cabx = itxt = aigc = 0
    with open(path, 'rb') as f:
        if f.read(8) != b'\x89PNG\r\n\x1a\n':
            return None
        while True:
            head = f.read(8)
            if len(head) < 8:
                break
            length, typ = struct.unpack('>I4s', head)
            if length > 10 ** 8:
                break
            body = f.read(length)
            f.read(4)
            if typ == b'caBX':
                cabx += 1
            elif typ == b'iTXt':
                itxt += 1
                if b'TC260' in body or b'AIGC' in body:
                    aigc += 1
    return {'cabx': cabx, 'itxt': itxt, 'aigc_in_itxt': aigc}


def main():
    groups = []
    patterns = [
        ('C133冻结重投', os.path.join(VIBE, '*C133冻结重投*.png')),
        # C138 主向组的档串不带「C133冻结重投」子串，必须显式加组，否则 264 格从容器画像里静默漏计（当前未投＝0 枚）。
        ('C138主向重投', os.path.join(VIBE, '*C138主向重投*.png')),
        ('画风通道实验', os.path.join(VIBE, '*画风通道实验*.png')),
        ('E1定档母图', os.path.join(E1, '*.png')),
    ]
    for gname, pat in patterns:
        files = sorted(glob.glob(pat))
        rows = []
        for p in files:
            pr = profile(p)
            if pr is None:
                continue
            rows.append(dict(file=os.path.basename(p), bytes=os.path.getsize(p), **pr))
        groups.append({'group': gname, 'pattern': pat, '枚数': len(rows),
                       'caBX=1且iTXt=0': sum(1 for r in rows if r['cabx'] == 1 and r['itxt'] == 0),
                       'caBX=0且iTXt≥1': sum(1 for r in rows if r['cabx'] == 0 and r['itxt'] >= 1),
                       '两者都无': sum(1 for r in rows if r['cabx'] == 0 and r['itxt'] == 0),
                       'rows': rows})
    hist = []
    for p in MEASURES:
        try:
            with io.open(p, encoding='utf-8') as fp:
                d = json.load(fp)
        except Exception as e:
            hist.append({'file': os.path.relpath(p, SET), 'err': str(e)})
            continue
        rows = d['rows'] if isinstance(d, dict) and isinstance(d.get('rows'), list) else (d if isinstance(d, list) else [])
        c = [r['container'] for r in rows if isinstance(r, dict) and isinstance(r.get('container'), dict)]
        hist.append({'file': os.path.relpath(p, SET), 'container行数': len(c),
                     'caBX=1且iTXt=0': sum(1 for x in c if x.get('cabx') == 1 and x.get('itxt') == 0),
                     'caBX=0且iTXt≥1': sum(1 for x in c if x.get('cabx') == 0 and (x.get('itxt') or 0) >= 1)})
    out = {'说明': '本文件只读派生，不手抄：容器画像现读 PNG 块，历史面现读各批 measure JSON 的 container 字段。',
           'groups': groups, 'history': hist}
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    for g in groups:
        print('%-14s 枚数=%-3d caBX1/iTXt0=%-3d caBX0/iTXt≥1=%-3d 都无=%d'
              % (g['group'], g['枚数'], g['caBX=1且iTXt=0'], g['caBX=0且iTXt≥1'], g['两者都无']))
    tot = sum(h['container行数'] for h in hist if 'container行数' in h)
    print('历史 measure container 行数合计=%d，其中 caBX=1且iTXt=0 = %d'
          % (tot, sum(h['caBX=1且iTXt=0'] for h in hist if 'caBX=1且iTXt=0' in h)))
    print('产物', OUT)


if __name__ == '__main__':
    # 守卫是必需的：本模块被当库 import（比如只为查 profile() 的实现）时，模块级调用会当场重跑并覆写产物——
    # 2026-11-07 规划期就因此把 container_profile.json 从 6,365 字节静默写成 73,711 字节，且脚本自己零报错。
    main()
