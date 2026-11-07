# -*- coding: utf-8 -*-
"""C134 机检口径闸门：细尺度方差地板与日面 1500px 分档线必须是「只作读数、不作判据」。

判红五类：
  机检判据措辞复活      —— 7 份测量脚本里再次出现「视作非油画／数值越高越油画／疑似日面圆盘/强光源阈值／
                            视作疑似日面圆盘」这类把读数写成判据的原句；
  C134 读数口径标注缺失 —— 7 份脚本任一份丢了 C134 标注，或标注行数低于该文件的应得行数；
  判据实验产物不在盘    —— 工具/reshoot_campaign_2026_11_06/ 的 CAMPAIGN 那批产物缺件（件数以该清单本轮长度为准）；
  判据实验读数表行数或分组数不符 —— 正典读数表不是 75 行／照片侧 45／绘画侧 30，或正典 CLIP 表行数与像素表不等；
  R1 画风读数覆盖面对不上 —— R1 表与清单现算的 C138 格集逐枚对不上（缺枚／多枚／重枚），
                            或读数 JSON 的计数、正典表 sha12、声明阈值在正典列上复算的错分与真源不符。
                            这一类守的是 C139 代签那轮未收口偏差的举证面：表被截短或图换了读数没换，
                            偏差申报就成了无证据的散文。阈值不在本闸门重搜（那是 clip_style.sep 的活、导入要拉 torch），
                            改为钉正典表 sha12＋用声明阈值复算声明错分，两边都对得上才认。

统计面（每个读数都自带）：扫描的是下面 FILES 这 7 个文件的全文，不排除任何行；
产物面是 CAMPAIGN 那批文件（件数随登记增长，正检读数里直接打印实数）；
R1 覆盖面现算自 数据/开图清单.json 里含 C138主向重投 字样的格（basename 逐枚比，不抄第二份枚数）。
本闸门只读，不写任何真源。

用法：
  python 工具/verify_readout_stance.py            正检（仓库真树）
  python 工具/verify_readout_stance.py --negtest  违例注入自证（仓库外临时目录）
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESIDUE_PREFIX = 'readout_stance_gate_'

# 相对仓库根的受检文件；标注行数下限按「该文件里有几处被降级的量」逐文件给，不取统一值
FILES = [
    ('工具/parallel_batch_2026_11_03/measure_images.py', 3),
    ('工具/reinject_2026_11_05/measure_images.py', 3),
    ('工具/batch9c_2026_11_05/measure_batch9c.py', 5),
    ('工具/batch9d_2026_11_05/measure_batch9d.py', 5),
    ('工具/batch9e_2026_11_05/measure_batch9e.py', 5),
    ('工具/batch9f_2026_11_06/measure_batch9f.py', 5),
    ('工具/batch9g_2026_11_06/measure_batch9g.py', 5),
]
LEGACY_PHRASES = [
    '整图细尺度方差低于此视作非油画',
    '数值越高越油画；极轻档地板读数',
    '疑似日面圆盘/强光源阈值',
    '视作疑似日面圆盘或强光源',
    '够判「疑似日面圆盘／强光源」',
    '二者互斥关系按通道成立',
]
CAMPAIGN = ['style_sep_final.py', 'style_sep_final.tsv', 'clip_style.py', 'clip_style_scores.tsv',
            'container_profile.py', 'container_profile.json', 'negtest_old_backfill_assert.py',
            'pick_primary_cell.py', 'primary_cells.json',
            'clip_style_r1.py', 'clip_style_scores_r1.tsv', 'clip_style_r1_readings.json']
REL_CAMPAIGN = '工具/reshoot_campaign_2026_11_06'
# R1 画风读数的覆盖面真源：清单里含该档串字样的那一格。不抄 264 这个数——
# 数由真源现算，抄一份就会在下一轮换档时把「覆盖面缺了」读成「行数对不上」。
R1_CELL_TOKEN = 'C138主向重投'
R1_TSV = 'clip_style_scores_r1.tsv'
R1_JSON = 'clip_style_r1_readings.json'

K_LEGACY_PHRASE = '机检判据措辞复活'
K_STANCE_MARK_MISSING = 'C134 读数口径标注缺失'
K_ARTIFACT_MISSING = '判据实验产物不在盘'
K_ARTIFACT_COUNT = '判据实验读数表行数或分组数不符'
K_R1_COVERAGE = 'R1 画风读数覆盖面对不上'
ALL_KINDS = (K_LEGACY_PHRASE, K_STANCE_MARK_MISSING, K_ARTIFACT_MISSING, K_ARTIFACT_COUNT, K_R1_COVERAGE)


def r1_cells(root):
    """从清单现算 R1 那一格的 basename 集合；清单不在盘返回 None（由调用方判缺件，不静默当空集）。"""
    p = root / '数据' / '开图清单.json'
    if not p.exists():
        return None
    items = json.loads(p.read_text(encoding='utf-8'))['items']
    out = set()
    for it in items:
        files = it.get('image_file') or []
        if isinstance(files, str):
            files = [files]
        out.update(os.path.basename(f) for f in files if R1_CELL_TOKEN in f)
    return out


def check(root=ROOT):
    viol = []
    readings = {'扫描文件数': 0, '扫描文件清单': [], 'C134 标注行数合计': 0,
                '判据原句命中数': 0, '产物在盘数': 0,
                '像素读数表行数': 0, '像素表照片侧': 0, '像素表绘画侧': 0, 'CLIP读数表行数': 0}
    texts = {}
    for rel, _ in FILES:
        p = root / rel
        if not p.exists():
            viol.append('%s：受检文件不在盘 %s' % (K_STANCE_MARK_MISSING, rel))
            continue
        texts[rel] = p.read_text(encoding='utf-8').replace('\r\n', '\n')
        readings['扫描文件数'] += 1
        readings['扫描文件清单'].append(rel)
        hits = [ph for ph in LEGACY_PHRASES if ph in texts[rel]]
        if hits:
            readings['判据原句命中数'] += len(hits)
            viol.append('%s：%s 命中 %s' % (K_LEGACY_PHRASE, rel, hits))
        marks = sum(1 for line in texts[rel].split('\n') if 'C134' in line)
        readings['C134 标注行数合计'] += marks
        need = dict(FILES)[rel]
        if marks < need:
            viol.append('%s：%s 标注行 %d < 应得 %d' % (K_STANCE_MARK_MISSING, rel, marks, need))

    for name in CAMPAIGN:
        p = root / REL_CAMPAIGN / name
        if not p.exists():
            viol.append('%s：缺件 %s/%s' % (K_ARTIFACT_MISSING, REL_CAMPAIGN, name))
            continue
        readings['产物在盘数'] += 1

    tsv = root / REL_CAMPAIGN / 'style_sep_final.tsv'
    clip = root / REL_CAMPAIGN / 'clip_style_scores.tsv'
    if tsv.exists():
        rows = [l for l in tsv.read_text(encoding='utf-8').split('\n') if l.strip()]
        body = rows[1:]
        ph = sum(1 for r in body if r.split('\t')[0] == 'PHOTO')
        pa = sum(1 for r in body if r.split('\t')[0] == 'PAINT')
        readings['像素读数表行数'] = len(body)
        readings['像素表照片侧'] = ph
        readings['像素表绘画侧'] = pa
        bad = []
        if len(body) != 75:
            bad.append('总行数 %d ≠ 75' % len(body))
        if (ph, pa) != (45, 30):
            bad.append('分组 照片%d/绘画%d ≠ 45/30' % (ph, pa))
        if len(body) != ph + pa:
            bad.append('有 %d 行的标签列不是 PHOTO/PAINT' % (len(body) - ph - pa))
        cols = rows[0].split('\t')
        if cols[:4] != ['label', 'core', 'name', 'file']:
            bad.append('表头前四列 %s ≠ label/core/name/file' % cols[:4])
        readings['像素表特征列数'] = len(cols) - 4
        if len(cols) - 4 != 14:
            bad.append('特征列 %d ≠ 14' % (len(cols) - 4))
        if bad:
            viol.append('%s：像素表 %s' % (K_ARTIFACT_COUNT, bad))
    if clip.exists():
        crows = [l for l in clip.read_text(encoding='utf-8').split('\n') if l.strip()]
        readings['CLIP读数表行数'] = len(crows) - 1
        if tsv.exists() and (len(crows) - 1) != readings['像素读数表行数']:
            viol.append('%s：CLIP 表 %d 行与像素表 %d 行不等，两次实验不同集'
                        % (K_ARTIFACT_COUNT, len(crows) - 1, readings['像素读数表行数']))
    # R1 画风读数的覆盖面：C139 代签那轮的未收口偏差（照片侧枚数远多于绘画侧）全靠这张表举证，
    # 表被删空、截短或图换了而读数没跟着换，偏差申报就成了无证据的散文。故按文件名逐枚对回清单现算的格集，
    # 并把读数 JSON 里的计数拿表重算——JSON 与表各说各话时，读 JSON 的人会把偏差读小。
    # 阈值不在本闸门里重搜一遍（那是 clip_style.sep 的活，且导入它要拉 torch）：改为钉正典表 sha12＋
    # 用声明阈值在正典列上复算声明的最小错分，两边都对得上才认这个阈值，R1 两侧再按它现分。
    r1t = root / REL_CAMPAIGN / R1_TSV
    r1j = root / REL_CAMPAIGN / R1_JSON
    want = r1_cells(root)
    readings['R1清单格数'] = len(want) if want is not None else 0
    readings['R1画风表行数'] = 0
    if want is None:
        viol.append('%s：清单不在盘，R1 覆盖面无法现算（不许当空集判绿）' % K_R1_COVERAGE)
    elif r1t.exists():
        rr = [l for l in r1t.read_text(encoding='utf-8').split('\n') if l.strip()]
        cols = rr[0].split('\t')
        body = [r.split('\t') for r in rr[1:]]
        readings['R1画风表行数'] = len(body)
        got = [r[2] for r in body if len(r) > 6]
        bad = []
        if cols[:3] != ['label', 'name', 'file']:
            bad.append('表头前三列 %s ≠ label/name/file' % cols[:3])
        if len(got) != len(body):
            bad.append('有 %d 行取不出 file/p_photo 列' % (len(body) - len(got)))
        if len(set(got)) != len(got):
            bad.append('file 列有重枚（%d 行 %d 枚）' % (len(got), len(set(got))))
        miss, extra = sorted(want - set(got)), sorted(set(got) - want)
        if miss:
            bad.append('清单有格而表无读数 %d 枚：%s' % (len(miss), miss[:5]))
        if extra:
            bad.append('表有读数而清单无此格 %d 枚：%s' % (len(extra), extra[:5]))
        if bad:
            viol.append('%s：%s' % (K_R1_COVERAGE, bad))
        if r1j.exists() and clip.exists() and len(got) == len(body):
            j = json.loads(r1j.read_text(encoding='utf-8'))
            canon = j.get('正典对照') or {}
            declared = j.get('R1读数') or {}
            cbody = [l.split('\t') for l in
                     [x for x in clip.read_text(encoding='utf-8').split('\n') if x.strip()][1:]]
            clabs = [r[0] for r in cbody]
            csc = [float(r[6]) for r in cbody]
            drift = []
            if canon.get('正典表sha256_12') != hashlib.sha256(clip.read_bytes()).hexdigest()[:12]:
                drift.append('正典表 sha12 声明 %s ≠ 现算 %s'
                             % (canon.get('正典表sha256_12'), hashlib.sha256(clip.read_bytes()).hexdigest()[:12]))
            for k, v in (('正典表行数', len(cbody)),
                         ('正典照片侧', sum(1 for x in clabs if x == 'PHOTO')),
                         ('正典绘画侧', sum(1 for x in clabs if x == 'PAINT'))):
                if canon.get(k) != v:
                    drift.append('%s 声明 %s ≠ 正典表现算 %s' % (k, canon.get(k), v))
            thr = canon.get('正典阈值')
            if not isinstance(thr, (int, float)):
                drift.append('正典阈值缺失或非数：%r' % thr)
            else:
                err = min(sum(1 for s, l in zip(csc, clabs) if (s > thr) != (l == 'PHOTO')),
                          sum(1 for s, l in zip(csc, clabs) if (s > thr) != (l == 'PAINT')))
                if err != canon.get('正典最小错分'):
                    drift.append('声明阈值在正典列上复算错分 %d ≠ 声明 %s' % (err, canon.get('正典最小错分')))
                ph = sum(1 for r in body if float(r[6]) > thr)
                readings['R1画风表照片侧'] = ph
                readings['R1画风表绘画侧'] = len(body) - ph
                for k, v in (('行数', len(body)),
                             ('落在正典阈值照片侧的枚数', ph),
                             ('落在正典阈值绘画侧的枚数', len(body) - ph)):
                    if declared.get(k) != v:
                        drift.append('%s 声明 %s ≠ R1 表现算 %s' % (k, declared.get(k), v))
            if (j.get('统计面') or {}).get('选中格数') != len(want):
                drift.append('统计面.选中格数 %s ≠ 清单现算 %d'
                             % ((j.get('统计面') or {}).get('选中格数'), len(want)))
            if drift:
                viol.append('%s：读数 JSON 与表/清单不符 %s' % (K_R1_COVERAGE, drift))
    return viol, readings


# ---------- 夹具与违例注入 ----------
R1_FIXTURE_N = 4          # R1 表行数（夹具面，与真树的 264 无关：真树那个数由清单现算）
R1_FIXTURE_PHOTO = 3      # 其中落在阈值照片侧的枚数


def build_fixture(tmp):
    """仓库外最小树：7 份测量脚本（标注行数恰达 FILES 下限）＋ CAMPAIGN 全件＋一份最小清单。
    正典两表各 75 行、45/30 分组；正典 CLIP 表的 p_photo 必须两侧分开（0.9／0.1），
    否则 sep 找不到任何相邻异值对、阈值为 None，R1 那支的阈值复算就没有承载。
    R1 表与最小清单的 C138 格逐枚同名，读数 JSON 的三个计数按表现算填，本底才干净。"""
    need = dict(FILES)
    for rel, marks in need.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('# -*- coding: utf-8 -*-\n' + ''.join('X%d = %d  # C134 读数\n' % (i, i) for i in range(marks)),
                     encoding='utf-8')
    camp = tmp / REL_CAMPAIGN
    camp.mkdir(parents=True, exist_ok=True)
    hdr = 'label\tcore\tname\tfile\t' + '\t'.join('f%02d' % i for i in range(14))
    body = '\n'.join(['%s\t1\tN%d\tF%d.png\t' % ('PHOTO' if i < 45 else 'PAINT', i, i) + '\t'.join('1.0' for _ in range(14))
                      for i in range(75)])
    (camp / 'style_sep_final.tsv').write_text(hdr + '\n' + body + '\n', encoding='utf-8')
    chdr = 'label\tname\tfile\tmax_sim\tphoto\tpaint\tp_photo'
    cbody = '\n'.join(['%s\tN%d\tF%d.png\t0.2\t0.2\t0.2\t%s'
                       % ('PHOTO' if i < 45 else 'PAINT', i, i, '0.9' if i < 45 else '0.1') for i in range(75)])
    canon_path = camp / 'clip_style_scores.tsv'
    canon_path.write_text(chdr + '\n' + cbody + '\n', encoding='utf-8')
    # 最小清单：R1_FIXTURE_N 条各占一格 C138，另 1 条无该档格（走排除支路，证明覆盖面对拍不是恒等式）
    cells = ['R%d-C138主向重投-v01_1.png' % i for i in range(R1_FIXTURE_N)]
    items = [{'id': 'T%d' % i, 'image_file': ['vibe_images/' + c]} for i, c in enumerate(cells)]
    items.append({'id': 'TX', 'image_file': ['vibe_images/TX-别的档-v01_1.png']})
    data = tmp / '数据'
    data.mkdir(parents=True, exist_ok=True)
    (data / '开图清单.json').write_text(json.dumps({'items': items}, ensure_ascii=False), encoding='utf-8')
    rbody = '\n'.join(['R1\tT%d\t%s\t0.2\t0.2\t0.2\t%s'
                       % (i, c, '0.9' if i < R1_FIXTURE_PHOTO else '0.1') for i, c in enumerate(cells)])
    (camp / R1_TSV).write_text(chdr + '\n' + rbody + '\n', encoding='utf-8')
    thr = 0.5
    r1j = {'统计面': {'选中格数': R1_FIXTURE_N},
           '正典对照': {'正典表行数': 75, '正典照片侧': 45, '正典绘画侧': 30,
                        '正典最小错分': 0, '正典阈值': thr,
                        '正典表sha256_12': hashlib.sha256(canon_path.read_bytes()).hexdigest()[:12]},
           'R1读数': {'行数': R1_FIXTURE_N, '落在正典阈值照片侧的枚数': R1_FIXTURE_PHOTO,
                      '落在正典阈值绘画侧的枚数': R1_FIXTURE_N - R1_FIXTURE_PHOTO}}
    (camp / R1_JSON).write_text(json.dumps(r1j, ensure_ascii=False), encoding='utf-8')
    # 产物清单再登记新件时不必改夹具：按 CAMPAIGN 补占位，缺谁补谁（已写好的表与 JSON 跳过）
    for name in CAMPAIGN:
        if not (camp / name).exists():
            (camp / name).write_text('print(1)\n', encoding='utf-8')
    return {'hdr': hdr}


def negtest():
    tmp = Path(tempfile.mkdtemp(prefix=RESIDUE_PREFIX))
    lines = []
    rc = 0
    try:
        build_fixture(tmp)
        viol, _ = check(tmp)
        lines.append('对照（夹具原样）：%d 违例 %s' % (len(viol), [v.split('：')[0] for v in viol]))
        if viol:
            rc = 1
            lines.append('✗ 夹具本底不干净，后续注入读数全部不可用')
            print('\n'.join(lines))
            return 1

        def mutate(what):
            shutil.rmtree(tmp / '工具')
            build_fixture(tmp)
            f = tmp / '工具/parallel_batch_2026_11_03/measure_images.py'
            t = f.read_text(encoding='utf-8')
            if what == K_LEGACY_PHRASE:
                t = t.replace('X0 = 0  # C134 读数\n', 'X0 = 0  # 整图细尺度方差低于此视作非油画\n')
            elif what == K_STANCE_MARK_MISSING:
                t = t.replace('X1 = 1  # C134 读数\n', 'X1 = 1\n')
            elif what == K_ARTIFACT_MISSING:
                os.remove(tmp / REL_CAMPAIGN / 'clip_style_scores.tsv')
            elif what == K_ARTIFACT_COUNT:
                p = tmp / REL_CAMPAIGN / 'style_sep_final.tsv'
                rows = [l for l in p.read_text(encoding='utf-8').split('\n') if l.strip()]
                p.write_text('\n'.join(rows[:2]) + '\n', encoding='utf-8')
            elif what == K_R1_COVERAGE:
                # 真实会犯的错：R1 表被截短一行（偏差举证少一枚），JSON 计数没跟着改。
                # 这一注入同时打覆盖面与 JSON 对拍两支，只测其中一支会漏掉另一支接线断掉。
                p = tmp / REL_CAMPAIGN / R1_TSV
                rows = [l for l in p.read_text(encoding='utf-8').split('\n') if l.strip()]
                p.write_text('\n'.join(rows[:-1]) + '\n', encoding='utf-8')
            f.write_text(t, encoding='utf-8')
            return check(tmp)

        hit = {}
        for kind in ALL_KINDS:
            v, _ = mutate(kind)
            names = [x.split('：')[0] for x in v]
            hit[kind] = kind in names
            if not hit[kind]:
                rc = 1
            lines.append('%s %s → %d 违例 %s' % ('✓' if hit[kind] else '✗', kind, len(v), names[:4]))
        lines.append('命中 %d/%d' % (sum(hit.values()), len(ALL_KINDS)))
        residue = [p.name for p in ROOT.rglob('*') if RESIDUE_PREFIX in p.name]
        lines.append('仓库内 %s 残留 %d' % (RESIDUE_PREFIX, len(residue)))
        if residue:
            rc = 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        lines.append('临时目录已删：%s 存在=%s' % (tmp.name, tmp.exists()))
    print('\n'.join(lines))
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--negtest', action='store_true', help='违例注入自证，须在仓库外临时目录跑')
    args = ap.parse_args()
    if args.negtest:
        return negtest()
    viol, readings = check()
    print(json.dumps(readings, ensure_ascii=False, indent=2))
    if viol:
        print('❌ 机检读数口径闸门判红 %d 条：' % len(viol))
        for v in viol:
            print('   ✗ %s' % v)
        return 1
    print('✅ 机检读数口径闸门通过：判据原句 0 处、C134 标注 %d 行 / 扫描 %d 份、实验产物 %d/%d 件在盘、'
          '读数表 %d 行（照片 %d／绘画 %d）与 CLIP 表 %d 行同集；'
          'R1 画风表 %d 行逐枚覆盖清单 %d 格（照片侧 %d／绘画侧 %d，按正典阈值现分、只作读数不判废）'
          % (readings['C134 标注行数合计'], readings['扫描文件数'], readings['产物在盘数'], len(CAMPAIGN),
             readings['像素读数表行数'], readings['像素表照片侧'], readings['像素表绘画侧'],
             readings['CLIP读数表行数'], readings['R1画风表行数'], readings['R1清单格数'],
             readings.get('R1画风表照片侧', 0), readings.get('R1画风表绘画侧', 0)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
