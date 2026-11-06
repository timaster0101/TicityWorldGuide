# -*- coding: utf-8 -*-
"""C134 机检口径闸门：细尺度方差地板与日面 1500px 分档线必须是「只作读数、不作判据」。

判红四类：
  机检判据措辞复活      —— 7 份测量脚本里再次出现「视作非油画／数值越高越油画／疑似日面圆盘/强光源阈值／
                            视作疑似日面圆盘」这类把读数写成判据的原句；
  C134 读数口径标注缺失 —— 7 份脚本任一份丢了 C134 标注，或标注行数低于该文件的应得行数；
  判据实验产物不在盘    —— 工具/reshoot_campaign_2026_11_06/ 的 CAMPAIGN 那批产物（五份脚本＋两份读数产物＋两份读数表）缺件；
  判据实验读数表行数或分组数不符 —— 读数表不是 75 行／照片侧 45／绘画侧 30，或 CLIP 表行数与像素表不等。

统计面（每个读数都自带）：扫描的是下面 FILES 这 7 个文件的全文，不排除任何行；
产物面是 CAMPAIGN 那批文件（件数随登记增长，正检读数里直接打印实数）。本闸门只读，不写任何真源。

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
            'pick_primary_cell.py', 'primary_cells.json']
REL_CAMPAIGN = '工具/reshoot_campaign_2026_11_06'

K_LEGACY_PHRASE = '机检判据措辞复活'
K_STANCE_MARK_MISSING = 'C134 读数口径标注缺失'
K_ARTIFACT_MISSING = '判据实验产物不在盘'
K_ARTIFACT_COUNT = '判据实验读数表行数或分组数不符'
ALL_KINDS = (K_LEGACY_PHRASE, K_STANCE_MARK_MISSING, K_ARTIFACT_MISSING, K_ARTIFACT_COUNT)


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
    return viol, readings


# ---------- 夹具与违例注入 ----------
def build_fixture(tmp):
    """仓库外最小树：7 份测量脚本（标注行数恰达 FILES 下限）＋ CAMPAIGN 全件（两张读数表各 75 行、45/30 分组，其余按清单补占位）。"""
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
    cbody = '\n'.join(['%s\tN%d\tF%d.png\t0.2\t0.2\t0.2\t0.9' % ('PHOTO' if i < 45 else 'PAINT', i, i) for i in range(75)])
    (camp / 'clip_style_scores.tsv').write_text(chdr + '\n' + cbody + '\n', encoding='utf-8')
    # 产物清单再登记新件时不必改夹具：按 CAMPAIGN 补占位，缺谁补谁（已写好的两张表跳过）
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
          '读数表 %d 行（照片 %d／绘画 %d）与 CLIP 表 %d 行同集'
          % (readings['C134 标注行数合计'], readings['扫描文件数'], readings['产物在盘数'], len(CAMPAIGN),
             readings['像素读数表行数'], readings['像素表照片侧'], readings['像素表绘画侧'],
             readings['CLIP读数表行数']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
