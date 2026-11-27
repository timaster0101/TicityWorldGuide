# -*- coding: utf-8 -*-
"""把合订本 docx 渲成逐页 PNG，并对每页做一遍机检，产出一份「哪几页值得人眼看」的体检单。

为什么要它：全书 424 页从未逐页人眼过（12 页单看、其余靠与对照版同页位图逐字节等值承载）。
这份脚本不解「人眼」这件事，它做的是把 424 页压成几十页：空白页、内容压边、整页发暗、
异常稀疏（图没渲出来或版面塌了）逐页标出来，人只需要看被标记的那些。

**口径与局限（必须写进报告，不许含糊）**：
  - 渲染器是 LibreOffice（headless，独立 profile），不是 Word。LibreOffice 的分页与 Word 不同，
    本机实测 412 页 vs Word 424 页；所以页号**不能**当作 Word 第 N 页的依据，本单只作版面体检的
    第二意见，不能替代 Word 渲染目视（`数据/Word渲染目视.json` 那份 424 页的签署仍然是唯一凭据）。
  - 机检只认像素：它判不出「图不对」「字错了」，只能判版面。

跑法：
    python 工具/inspect_print_pages.py                     渲全部页并体检
    python 工具/inspect_print_pages.py --dpi 80 --limit 40  小样试跑
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DOCX = ROOT / '钛湖城城市设定集-完整合订本.docx'
PAGES = ROOT / '数据' / 'Word页图'
REPORT = ROOT / '数据' / 'Word页体检.json'
REPORT_MD = ROOT / '数据' / 'Word页体检报告.md'
SOFFICE = Path(r'C:\Program Files\LibreOffice\program\soffice.exe')

INK_THRESHOLD = 240      # 灰度低于此值算有墨
BLANK_INK = 0.0015       # 全页有墨比例低于此值判空白页
SPARSE_INK = 0.02        # 低于此值判稀疏页（章末页正常，需人眼扫一眼）
EDGE_MM = 5.0            # 内容离页边小于此值判压边
DARK_MEAN = 170          # 整页平均灰度低于此值判发暗


def convert(docx=DOCX, workdir=None):
    """docx → pdf（LibreOffice headless，独立 profile，避免抢用户正在用的实例）。"""
    workdir = Path(workdir or tempfile.mkdtemp(prefix='printpdf_'))
    workdir.mkdir(parents=True, exist_ok=True)
    src = workdir / 'book.docx'
    shutil.copy2(docx, src)
    profile = workdir / 'profile'
    args = [str(SOFFICE),
            '-env:UserInstallation=file:///' + str(profile).replace('\\', '/'),
            '--headless', '--norestore', '--convert-to', 'pdf',
            '--outdir', str(workdir), str(src)]
    subprocess.run(args, check=True, timeout=1800,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    pdf = workdir / 'book.pdf'
    if not pdf.exists():
        raise RuntimeError('LibreOffice 没产出 PDF：%s' % pdf)
    return pdf


def page_metrics(img):
    """单页像素体征：有墨比例、平均灰度、内容 bbox、四边留白（毫米）。"""
    g = img.convert('L')
    w, h = g.size
    px = g.load()
    dpi = 100.0  # 由调用方按实际 dpi 覆盖
    ink = 0
    total = 0
    minx, miny, maxx, maxy = w, h, -1, -1
    step = max(1, int(min(w, h) / 800))  # 大步长采样，够判空白与边缘
    for y in range(0, h, step):
        for x in range(0, w, step):
            total += 1
            if px[x, y] < INK_THRESHOLD:
                ink += 1
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
    ratio = ink / float(total or 1)
    return {
        'px': [w, h],
        'ink_ratio': round(ratio, 5),
        'mean_gray': round(sum(g.resize((64, 64)).tobytes()) / 4096.0, 1),
        'bbox': None if maxx < 0 else [minx, miny, maxx, maxy],
    }


def flags_for(m, dpi, page_mm):
    out = []
    if m['ink_ratio'] < BLANK_INK:
        out.append('空白页')
    elif m['ink_ratio'] < SPARSE_INK:
        out.append('稀疏页')
    if m['mean_gray'] < DARK_MEAN:
        out.append('整页发暗')
    bb = m['bbox']
    if bb:
        mm_per_px = 25.4 / dpi
        left, top = bb[0] * mm_per_px, bb[1] * mm_per_px
        right = page_mm[0] - bb[2] * mm_per_px
        bottom = page_mm[1] - bb[3] * mm_per_px
        if min(left, top, right, bottom) < EDGE_MM:
            out.append('内容压边')
        m['margins_mm'] = {'left': round(left, 1), 'top': round(top, 1),
                           'right': round(right, 1), 'bottom': round(bottom, 1)}
    return out


def run(docx=DOCX, out_dir=PAGES, dpi=100, limit=None, quiet=False):
    import fitz
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = convert(docx)
    doc = fitz.open(str(pdf))
    zoom = dpi / 72.0
    rows = []
    n = doc.page_count if not limit else min(doc.page_count, limit)
    for i in range(n):
        pg = doc[i]
        page_mm = (pg.rect.width / 72.0 * 25.4, pg.rect.height / 72.0 * 25.4)
        pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        name = 'p%03d.png' % (i + 1)
        img.save(out_dir / name)
        m = page_metrics(img)
        m['dpi'] = dpi
        m['flags'] = flags_for(m, dpi, page_mm)
        m['file'] = name
        rows.append(m)
        if not quiet and (i + 1) % 50 == 0:
            print('  渲染 %d/%d' % (i + 1, n))
    doc.close()
    shutil.rmtree(pdf.parent, ignore_errors=True)
    return rows


def summarize(rows, pages_in_word=424):
    flagged = [r for r in rows if r['flags']]
    by_flag = {}
    for r in flagged:
        for f in r['flags']:
            by_flag.setdefault(f, []).append(r['file'])
    return {
        '口径': 'LibreOffice 渲染 + 像素机检；只判版面，不判图文内容',
        '局限': 'LibreOffice 分页与 Word 不同（本机 %d 页 vs Word %d 页），页号不作为 Word 页号依据；'
                '本单是版面体检的第二意见，不替代 Word 渲染目视签署' % (len(rows), pages_in_word),
        '统计': {'页数': len(rows), '被标记页数': len(flagged),
                 '空白页': len(by_flag.get('空白页', [])),
                 '稀疏页': len(by_flag.get('稀疏页', [])),
                 '整页发暗': len(by_flag.get('整页发暗', [])),
                 '内容压边': len(by_flag.get('内容压边', []))},
        '按标记归组': by_flag,
        '逐页': rows,
    }


def write_report(rep, json_path=REPORT, md_path=REPORT_MD):
    with io.open(json_path, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(json.dumps(rep, ensure_ascii=False, indent=2) + '\n')
    s = rep['统计']
    lines = ['# 合订本逐页版面体检', '',
             '> %s' % rep['口径'], '>', '> %s' % rep['局限'], '',
             '共 **%d** 页，被标记 **%d** 页：空白 %d／稀疏 %d／发暗 %d／压边 %d。'
             % (s['页数'], s['被标记页数'], s['空白页'], s['稀疏页'], s['整页发暗'], s['内容压边']), '']
    for flag, files in rep['按标记归组'].items():
        lines.append('## %s（%d 页）' % (flag, len(files)))
        lines.append('')
        lines.append('、'.join(f.replace('.png', '') for f in files[:80]) + ('…' if len(files) > 80 else ''))
        lines.append('')
    with io.open(md_path, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write('\n'.join(lines) + '\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dpi', type=int, default=100)
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--no-report', action='store_true')
    args = ap.parse_args()
    rows = run(dpi=args.dpi, limit=args.limit)
    if args.no_report:
        print('渲染 %d 页，未写报告' % len(rows))
        return 0
    rep = summarize(rows)
    write_report(rep)
    print(json.dumps(rep['统计'], ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
