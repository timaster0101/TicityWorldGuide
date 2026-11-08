# -*- coding: utf-8 -*-
"""卡面 3:4 满幅主图 114 枚的画风侧 CLIP 读数（C134 口径：只出读数，不判废）。

覆盖面真源是 `数据/卡面主图提示词3x4/主图3x4落点.json`（114 键 → 仓内相对路径），
不在本脚本里 glob 目录——glob 会把「落点件没登记但盘上多了一张」读成有读数。
判据模板 M／PHOTO_T／PAINT_T／SET／sep 直接从 clip_style.py 导入，不另抄一份。
正典表 clip_style_scores.tsv（75 行）与 style_sep_final.tsv 一字不动，产物是独立新表。

    python -X utf8 工具/reshoot_campaign_2026_11_06/clip_style_card3x4.py
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
LANDING = os.path.join(SET, '数据', '卡面主图提示词3x4', '主图3x4落点.json')
CANON = os.path.join(HERE, 'clip_style_scores.tsv')
OUT_TSV = os.path.join(HERE, 'clip_style_scores_card3x4.tsv')
OUT_JSON = os.path.join(HERE, 'clip_style_card3x4_readings.json')


def card_cells():
    """落点件逐键 → 绝对路径；键名即卡号（L009／D01／'7' 两种形态都原样留作 label 列）。"""
    d = json.loads(io.open(LANDING, encoding='utf-8').read())
    rows = []
    for idx, rel in sorted(d.items()):
        p = os.path.join(SET, rel.replace('/', os.sep))
        rows.append({'idx': idx, 'rel': rel, 'path': p, '在盘': os.path.exists(p)})
    return d, rows


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
    land, rows = card_cells()
    canon = canon_threshold()
    missing = [r for r in rows if not r['在盘']]
    if missing:
        print('❌ 落点件有 %d 键取不到文件，先修落点再跑：%s' % (
            len(missing), [r['rel'] for r in missing][:5]))
        return 1

    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    print('loading clip on %s；卡面主图 %d 枚' % (dev, len(rows)), flush=True)
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
        size = im.size
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
        out.append((r, size, float(sims.max()), sp, spa, float(pr[0])))
        if n % 40 == 0 or n == len(rows):
            print('  已读 %d/%d' % (n, len(rows)), flush=True)

    with io.open(OUT_TSV, 'w', encoding='utf-8', newline='\n') as f:
        f.write('label\tidx\tfile\twh\tmax_sim\tphoto\tpaint\tp_photo\n')
        for r, size, ms, sp, spa, pp in out:
            f.write('\t'.join(['CARD', r['idx'], os.path.basename(r['rel']),
                               '%dx%d' % size,
                               '%.6f' % ms, '%.6f' % sp, '%.6f' % spa, '%.6f' % pp]) + '\n')

    pp = np.array([o[5] for o in out])
    thr = canon['正典阈值']
    photo_side = [o[0]['idx'] for o in out if thr is not None and o[5] > thr]
    readings = {
        '口径': 'C134：只作读数、不作判废依据；画风判废权在人工目视。本脚本不写 accepted、不改 status、不动 manifest。',
        '统计面': {
            '真源': '数据/卡面主图提示词3x4/主图3x4落点.json',
            '真源sha256_12': hashlib.sha256(io.open(LANDING, 'rb').read()).hexdigest()[:12],
            '落点件键数': len(land),
            '选取规则': '落点件全部键（键即卡号），逐键恰 1 个 PNG',
            '读到的枚数': len(rows),
            '取不到的键数': len(missing),
            '尺寸分布': {},
            '正典两表是否改动': '否，clip_style_scores.tsv 与 style_sep_final.tsv 均未写入',
        },
        '正典对照': canon,
        '判据模板': {'照片侧': PHOTO_T, '绘画侧': PAINT_T, '来源': 'clip_style.py 导入，未另抄'},
        '模型': {'目录': M, '权重字节': os.path.getsize(os.path.join(M, 'pytorch_model.bin')),
                 'device': dev, 'torch': torch.__version__},
        '卡面读数': {
            '行数': len(out),
            'P(photo)均值': float(pp.mean()), 'P(photo)中位数': float(np.median(pp)),
            'P(photo)最小': float(pp.min()), 'P(photo)最大': float(pp.max()),
            'P(photo)标准差': float(pp.std()),
            '落在正典阈值照片侧的枚数': len(photo_side),
            '落在正典阈值绘画侧的枚数': len(out) - len(photo_side),
            '照片侧名单_供人工目视优先排序': sorted(photo_side),
            'photo相似度均值': float(np.mean([o[3] for o in out])),
            'paint相似度均值': float(np.mean([o[4] for o in out])),
            '最像绘画的10枚_P_photo升序': [[o[0]['idx'], round(o[5], 6)] for o in
                                          sorted(out, key=lambda x: x[5])[:10]],
            '最像照片的10枚_P_photo降序': [[o[0]['idx'], round(o[5], 6)] for o in
                                         sorted(out, key=lambda x: -x[5])[:10]],
        },
        '产物': {'tsv': os.path.basename(OUT_TSV),
                 'tsv字节': os.path.getsize(OUT_TSV),
                 'tsv_sha256_12': hashlib.sha256(io.open(OUT_TSV, 'rb').read()).hexdigest()[:12]},
    }
    dist = {}
    for _, size, *_ in out:
        dist['%dx%d' % size] = dist.get('%dx%d' % size, 0) + 1
    readings['统计面']['尺寸分布'] = dist

    with io.open(OUT_JSON, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(readings, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('\n== 卡面 3:4 主图 %d 枚（C134：只作读数，不判废）==' % len(out))
    print('正典阈值 %.6f（正典 %d 行，最小错分 %d）' % (thr, canon['正典表行数'], canon['正典最小错分']))
    print('P(photo) 均值 %.4f／中位 %.4f／区间 %.4f—%.4f' % (pp.mean(), np.median(pp), pp.min(), pp.max()))
    print('落在照片侧 %d 枚／绘画侧 %d 枚' % (len(photo_side), len(out) - len(photo_side)))
    print('尺寸分布', dist)
    print('产物 %s（%d 字节）＋ %s' % (os.path.basename(OUT_TSV), os.path.getsize(OUT_TSV),
                                     os.path.basename(OUT_JSON)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
