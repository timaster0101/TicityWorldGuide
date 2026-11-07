# -*- coding: utf-8 -*-
"""R1 组（C138主向重投-v01）264 枚的画风侧 CLIP 重读。

C134 口径：本脚本只出读数，不判废、不写 accepted、不改 status。画风判废权在人工目视。
判据模板与分离度算法直接从 clip_style.py 导入，不另抄一份（那份已被 __main__ 守卫挡住，导入不会重跑正典实验）。
产物是独立新表，正典 clip_style_scores.tsv 与 style_sep_final.tsv 一字不动——
verify_readout_stance 钉着那两份各 75 行、照片 45／绘画 30 且两表同集，覆盖即判红。

    python -X utf8 工具/reshoot_campaign_2026_11_06/clip_style_r1.py
"""
import hashlib
import io
import json
import os
import sys

import numpy as np
from PIL import Image
import torch
from transformers import CLIPModel, CLIPProcessor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clip_style import M, PAINT_T, PHOTO_T, SET, sep

HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(SET, '数据', '开图清单.json')
CANON = os.path.join(HERE, 'clip_style_scores.tsv')
OUT_TSV = os.path.join(HERE, 'clip_style_scores_r1.tsv')
OUT_JSON = os.path.join(HERE, 'clip_style_r1_readings.json')
BATCH = 'C138主向重投'


def r1_cells():
    q = json.loads(io.open(QUEUE, encoding='utf-8').read())
    rows, excluded = [], []
    for it in q['items']:
        cells = [c for c in (it.get('image_file') or []) if c]
        hit = [c for c in cells if BATCH in c]
        if not hit:
            excluded.append({'id': it['id'], 'status': it['status'], '格数': len(cells),
                             '原因': '无 C138 主向重投格'})
            continue
        for c in hit:
            p = os.path.join(SET, c.replace('/', os.sep))
            rows.append({'id': it['id'], 'name': it['name'], 'cell': c, 'path': p,
                         '在盘': os.path.exists(p)})
    return q, rows, excluded


def canon_threshold():
    lines = [l for l in io.open(CANON, encoding='utf-8').read().split('\n') if l.strip()]
    body = [l.split('\t') for l in lines[1:]]
    labs = [r[0] for r in body]
    sc = np.array([float(r[6]) for r in body])
    err, thr = sep(labs, sc)
    return {'正典表行数': len(body),
            '正典照片侧': sum(1 for x in labs if x == 'PHOTO'),
            '正典绘画侧': sum(1 for x in labs if x == 'PAINT'),
            '正典最小错分': err, '正典阈值': thr,
            '正典表sha256_12': hashlib.sha256(io.open(CANON, 'rb').read()).hexdigest()[:12]}


def main():
    q, rows, excluded = r1_cells()
    canon = canon_threshold()
    missing = [r for r in rows if not r['在盘']]
    if missing:
        print('❌ 取不到的格 %d 枚，先修清单再跑：%s' % (len(missing), [r['cell'] for r in missing][:5]))
        return 1
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    print('loading clip on %s；R1 格 %d 枚' % (dev, len(rows)), flush=True)
    model = CLIPModel.from_pretrained(M).to(dev).eval()
    proc = CLIPProcessor.from_pretrained(M)
    texts = PHOTO_T + PAINT_T
    with torch.no_grad():
        tx = proc(text=texts, return_tensors='pt', padding=True).to(dev)
        temb = model.get_text_features(**tx)['pooler_output']
        temb = temb / temb.norm(dim=-1, keepdim=True)
    ph = temb[:len(PHOTO_T)].mean(0)
    ph = ph / ph.norm()
    pa = temb[len(PHOTO_T):].mean(0)
    pa = pa / pa.norm()

    out = []
    for n, r in enumerate(rows, 1):
        im = Image.open(r['path']).convert('RGB')
        with torch.no_grad():
            f = proc(images=im, return_tensors='pt').to(dev)
            e = model.get_image_features(**f)['pooler_output']
            e = e / e.norm(dim=-1, keepdim=True)
            sims = (e @ temb.T)[0].cpu().numpy()
        sp = float(e[0] @ ph)
        spa = float(e[0] @ pa)
        logit = 100.0 * np.array([sp, spa])
        pr = np.exp(logit - logit.max())
        pr /= pr.sum()
        out.append((r, float(sims.max()), sp, spa, float(pr[0])))
        if n % 40 == 0 or n == len(rows):
            print('  已读 %d/%d' % (n, len(rows)), flush=True)

    with io.open(OUT_TSV, 'w', encoding='utf-8', newline='\n') as f:
        f.write('label\tname\tfile\tmax_sim\tphoto\tpaint\tp_photo\n')
        for r, ms, sp, spa, pp in out:
            f.write('\t'.join(['R1', r['id'] + '-' + r['name'], os.path.basename(r['cell']),
                               '%.6f' % ms, '%.6f' % sp, '%.6f' % spa, '%.6f' % pp]) + '\n')

    pp = np.array([o[4] for o in out])
    thr = canon['正典阈值']
    photo_side = [o[0]['id'] for o in out if thr is not None and o[4] > thr]
    readings = {
        '口径': 'C134：只作读数、不作判废依据；画风判废权在人工目视。本脚本不写 accepted、不改 status、不动 image_prompt_sha256。',
        '统计面': {
            '真源': '数据/开图清单.json',
            '真源sha256_12': hashlib.sha256(io.open(QUEUE, 'rb').read()).hexdigest()[:12],
            '清单条目数': len(q['items']),
            '选取规则': 'image_file 四向格里含「%s」字样的那一格，逐条恰 1 格' % BATCH,
            '选中格数': len(rows),
            '涉及条目数': len({r['id'] for r in rows}),
            '排除条目数': len(excluded),
            '排除原因分布': {k: sum(1 for e in excluded if e['原因'] == k)
                             for k in sorted({e['原因'] for e in excluded})},
            '排除条目名单': [e['id'] for e in excluded],
            '取不到的格数': len(missing),
            '读取路径面': '仓内 钛湖城城市设定集/vibe_images/（清单真源所指），不读仓外工作区根落点',
            '正典两表是否改动': '否，clip_style_scores.tsv 与 style_sep_final.tsv 均未写入',
        },
        '正典对照': canon,
        '判据模板': {'照片侧': PHOTO_T, '绘画侧': PAINT_T, '来源': 'clip_style.py 导入，未另抄'},
        '模型': {'目录': M, '权重字节': os.path.getsize(os.path.join(M, 'pytorch_model.bin')),
                 'device': dev, 'torch': torch.__version__},
        'R1读数': {
            '行数': len(out),
            'P(photo)均值': float(pp.mean()), 'P(photo)中位数': float(np.median(pp)),
            'P(photo)最小': float(pp.min()), 'P(photo)最大': float(pp.max()),
            'P(photo)标准差': float(pp.std()),
            '落在正典阈值照片侧的枚数': len(photo_side),
            '落在正典阈值绘画侧的枚数': len(out) - len(photo_side),
            '照片侧名单_供人工目视优先排序': sorted(photo_side),
            'photo相似度均值': float(np.mean([o[2] for o in out])),
            'paint相似度均值': float(np.mean([o[3] for o in out])),
        },
        '产物': {'tsv': os.path.basename(OUT_TSV),
                 'tsv字节': os.path.getsize(OUT_TSV),
                 'tsv_sha256_12': hashlib.sha256(io.open(OUT_TSV, 'rb').read()).hexdigest()[:12]},
    }
    with io.open(OUT_JSON, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(readings, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('\n== R1 组 %d 枚（C134：只作读数，不判废）==' % len(out))
    print('正典阈值 %.6f（正典 %d 行，最小错分 %d）' % (thr, canon['正典表行数'], canon['正典最小错分']))
    print('R1 P(photo) 均值 %.4f／中位 %.4f／区间 %.4f—%.4f' % (pp.mean(), np.median(pp), pp.min(), pp.max()))
    print('落在照片侧 %d 枚／绘画侧 %d 枚' % (len(photo_side), len(out) - len(photo_side)))
    print('产物 %s（%d 字节）＋ %s' % (os.path.basename(OUT_TSV), os.path.getsize(OUT_TSV), os.path.basename(OUT_JSON)))
    return 0


if __name__ == '__main__':
    sys.exit(main())