# -*- coding: utf-8 -*-
"""复看套件生成物对拍闸门：逐格比对 数据/人工复看套件/{工作单.md,联络表/} 与真源 数据/开图清单.json。

为什么要这条闸门：`build_review_suite.py` 的产物是 C 项人工复看的唯一入口，但它只在自己被重跑时
才更新；清单侧改一次 `image_file`（例如 2026-11-06 的 backup 归档挂法），产物不会跟着变，
而全量单测跑的是生成器在临时目录里现算的那份——仓库里这份已经过期，闸门全绿也看不见断链。
本闸门读的是仓库里真实落盘的生成物，判据全部按内容对拍，不按 mtime 猜。

用法：
    python 工具/verify_review_freshness.py            # 正检，rc=0 表示生成物与真源一致
    python 工具/verify_review_freshness.py --negtest  # 违例注入自证，八类判据必须全部被检出
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

ITEM_HEAD = re.compile(r'^### (\S+) ')
CELL_LINE = re.compile(r'^- 图格：(\S+)')
SRC_ATTR = re.compile(r'src\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)

REL_SHEET = '数据/人工复看套件/工作单.md'
REL_PAGES = '数据/人工复看套件/联络表'
REL_MANIFEST = '数据/开图清单.json'

# 判据名做成常量：违例文本以此为前缀，负测按名字精确匹配，改文案不会让注入静默失效。
K_SHEET_MISSING = '清单有格而工作单无此条目'
K_SHEET_EXTRA = '工作单出现清单没有的条目'
K_SEQ_DRIFT = '逐格序列与清单不一致'
K_TOTAL_DIFF = '总格数不等'
K_HTML_INERT = '联络表一条 src 也没解析出来'
K_HTML_SET = '联络表 src 集合与清单格集合不一致'
K_SHEET_DEAD = '工作单图格指向的文件不在盘上'
K_HTML_DEAD = '联络表 src 指向的文件不在盘上'
ALL_KINDS = (K_SHEET_MISSING, K_SHEET_EXTRA, K_SEQ_DRIFT, K_TOTAL_DIFF,
             K_HTML_INERT, K_HTML_SET, K_SHEET_DEAD, K_HTML_DEAD)


def manifest_cells(root=ROOT):
    """真源：开图清单里每条在册图的格序列，只取有 image_file 的条目。"""
    data = json.loads((root / REL_MANIFEST).read_text(encoding='utf-8'))
    return {it['id']: list(it['image_file']) for it in data['items'] if it.get('image_file')}


def sheet_cells(text):
    out = {}
    current = None
    for line in text.splitlines():
        head = ITEM_HEAD.match(line)
        if head:
            current = head.group(1)
            out[current] = []
            continue
        if current is not None:
            cell = CELL_LINE.match(line)
            if cell:
                out[current].append(cell.group(1))
    return out


def html_refs(pages_dir):
    """联络表按三级 ../ 回到仓库根再拼本地路径，这里统一还原成仓库根相对写法。"""
    refs = []
    for page in sorted(pages_dir.glob('*.html')):
        for m in SRC_ATTR.finditer(page.read_text(encoding='utf-8', errors='ignore')):
            ref = unquote(m.group(1))
            if ref.startswith(('http', 'data:', '#', 'mailto')):
                continue
            refs.append(re.sub(r'^(\.\./)+', '', ref.lstrip('/')))
    return refs


def compare(cells, sheet, refs, root=ROOT):
    """返回 (读数, 违例)。违例是 (判据名, 人话) 成对，判据名取自本文件顶部常量，负测按名字精确匹配。"""
    pages_dir = root / REL_PAGES
    readings = {
        '清单在册条目': len(cells),
        '清单格数': sum(len(v) for v in cells.values()),
        '工作单条目': len(sheet),
        '工作单格数': sum(len(v) for v in sheet.values()),
        '联络表引用数': len(refs),
        '联络表页面数': len(list(pages_dir.glob('*.html'))) if pages_dir.is_dir() else 0,
    }
    bad = []
    missing = sorted(set(cells) - set(sheet))
    extra = sorted(set(sheet) - set(cells))
    if missing:
        bad.append((K_SHEET_MISSING, '%s（生成物落后）：%d 条，例 %s' % (K_SHEET_MISSING, len(missing), ','.join(missing[:3]))))
    if extra:
        bad.append((K_SHEET_EXTRA, '%s：%d 条，例 %s' % (K_SHEET_EXTRA, len(extra), ','.join(extra[:3]))))
    drift = {}
    for eid, seq in cells.items():
        got = sheet.get(eid)
        if got is not None and got != seq:
            drift[eid] = (len(seq), len(got))
    if drift:
        bad.append((K_SEQ_DRIFT, '%s（缺格/多格/换了路径）：%d 条，例 %s' % (
            K_SEQ_DRIFT, len(drift), ','.join('%s(清单%d/工作单%d)' % (k, v[0], v[1]) for k, v in list(drift.items())[:3]))))
    if readings['工作单格数'] != readings['清单格数']:
        bad.append((K_TOTAL_DIFF, '%s：工作单 %d vs 清单 %d' % (K_TOTAL_DIFF, readings['工作单格数'], readings['清单格数'])))
    refset, cellset = set(refs), {p for seq in cells.values() for p in seq}
    if not refs:
        bad.append((K_HTML_INERT, '%s（引用侧判据本身失效，不得当作通过）' % K_HTML_INERT))
    elif refset != cellset:
        bad.append((K_HTML_SET, '%s（缺 %d / 多 %d）' % (K_HTML_SET, len(cellset - refset), len(refset - cellset))))
    dead_sheet = [p for seq in sheet.values() for p in seq if not (root / p).is_file()]
    if dead_sheet:
        bad.append((K_SHEET_DEAD, '%s：%d 格，例 %s' % (K_SHEET_DEAD, len(dead_sheet), dead_sheet[0][:70])))
    dead_html = [r for r in refs if not (root / r).is_file()]
    if dead_html:
        bad.append((K_HTML_DEAD, '%s：%d 处，例 %s' % (K_HTML_DEAD, len(dead_html), dead_html[0][:70])))
    return readings, bad


def run_negtest():
    """八类判据逐条注入违例，判据名必须精确命中；再拿原样数据对照，证明不是判据本身失效。"""
    cells = manifest_cells()
    sheet = {k: list(v) for k, v in cells.items()}
    refs = sorted({p for seq in cells.values() for p in seq})
    cases = []
    one = sorted(cells)[0]

    stripped = {k: list(v) for k, v in sheet.items()}
    del stripped[one]
    cases.append((K_SHEET_MISSING, stripped, list(refs)))

    short = {k: list(v) for k, v in sheet.items()}
    short[one] = short[one][:-1] if len(short[one]) > 1 else []
    cases.append((K_SEQ_DRIFT, short, list(refs)))

    dead = {k: list(v) for k, v in sheet.items()}
    keep = list(dead[one])
    dead[one] = keep[:1]
    dead[one][0] = 'backup/数据/图集/四向/不存在-用于自证.jpg'
    cases.append((K_SHEET_DEAD, dead, list(refs)))

    refs_short = list(refs)
    refs_short.pop()
    cases.append((K_HTML_SET, {k: list(v) for k, v in sheet.items()}, refs_short))

    refs_dead = list(refs)
    refs_dead[0] = 'backup/数据/图集/四向/联络表用不存在-自证.jpg'
    cases.append((K_HTML_DEAD, {k: list(v) for k, v in sheet.items()}, refs_dead))

    cases.append((K_HTML_INERT, {k: list(v) for k, v in sheet.items()}, []))

    ghost = {k: list(v) for k, v in sheet.items()}
    ghost['ZZ-自证条目'] = ['backup/数据/图集/四向/不存在-用于自证.jpg']
    cases.append((K_SHEET_EXTRA, ghost, list(refs)))

    grow = {k: list(v) for k, v in sheet.items()}
    grow[one] = grow[one] + [grow[one][0]]
    cases.append((K_TOTAL_DIFF, grow, list(refs)))

    injected = {kind for kind, _, _ in cases}
    if injected != set(ALL_KINDS):
        print('注入面缺口（有判据没被注入，闸门不算自证）：%s' % ', '.join(sorted(set(ALL_KINDS) - injected)))
        return 1
    baseline, baseline_bad = compare(cells, sheet, refs)
    print('对照（原样数据）：违例 %d 条%s' % (len(baseline_bad), '' if not baseline_bad else ' ← ' + str(baseline_bad[:1][1])))
    caught = 0
    for kind, fake_sheet, fake_refs in cases:
        _, bad = compare(cells, fake_sheet, fake_refs)
        hit = next((b for b in bad if b[0] == kind), None)
        caught += bool(hit)
        print('  [%s] %s: %s' % ('负测' if hit else '假绿', kind, hit[1][:72] if hit else '该判据未被检出（其余违例 %d 条）' % len(bad)))
    print('判据总数: %d，注入并命中: %d' % (len(ALL_KINDS), caught))
    if len(baseline_bad) or caught != len(ALL_KINDS):
        print('\n负测结论: 不合格（对照 %d 违例，检出 %d/%d）' % (len(baseline_bad), caught, len(ALL_KINDS)))
        return 1
    print('\n负测结论: 八类判据全部捕获')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='复看套件生成物与开图清单逐格对拍')
    ap.add_argument('--negtest', action='store_true', help='注入八类违例自证判据有效')
    ap.add_argument('--root', default=str(ROOT), help='对拍根目录（跨副本比对时用，生成物与真源都按此根读）')
    args = ap.parse_args(argv)
    if args.negtest:
        return run_negtest()
    root = Path(args.root).resolve()
    sheet_path, pages_dir = root / REL_SHEET, root / REL_PAGES
    if not sheet_path.is_file() or not pages_dir.is_dir():
        print('生成物缺失：%s / %s' % (sheet_path, pages_dir))
        return 1
    readings, bad = compare(manifest_cells(root), sheet_cells(sheet_path.read_text(encoding='utf-8')),
                            html_refs(pages_dir), root=root)
    for k, v in readings.items():
        print('%s: %s' % (k, v))
    if bad:
        print('\n生成物过期或与真源不一致（%d 条）：' % len(bad))
        for _, text in bad:
            print('  ✗', text)
        print('\n修法：python 工具/build_review_suite.py 重跑生成物后复对本脚本。')
        return 1
    print('\n生成物与真源逐格一致，联络表全部引用落盘。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
