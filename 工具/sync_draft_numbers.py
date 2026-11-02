"""把 分卷/原稿 里带单位的数值声明对齐到 城市空间名录.json。

替换用的正则与段落范围与 compile_book.check_numeric_fidelity 的判据同源，改完
由 test_compile_book.NumericFidelityTests 自证。--before 给一个改名前的名录快照
时，另列“扫描段之外仍见旧值”的清单供人工过目，脚本不动那些位置。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compile_book as compiler

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--before', help='改量级前的名录快照 JSON，用于列残留清单')
parser.add_argument('--dry-run', action='store_true')
args = parser.parse_args()


def sections_of(body):
    result = {}
    for index, tag in enumerate(compiler.TAGS):
        start = body.index(f'**{tag}**') + len(f'**{tag}**')
        end = body.index(f'**{compiler.TAGS[index + 1]}**', start) if index + 1 < len(compiler.TAGS) else len(body)
        result[tag] = body[start:end].strip('：: \n')
    return result


def scan_tags(field):
    if field in ('area_km2', 'gross_floor_area_m2'):
        return ['位置与规模']
    if field in ('height_m', 'floors'):
        return ['位置与规模', '锁定项与禁则']
    if field == 'height_limit_m':
        return ['位置与规模', '规划与空间组织', '外观与辨识细节', '锁定项与禁则']
    return ['位置与规模', '人群与生活节奏']


def fmt(value):
    return ('%g' % value) if isinstance(value, float) else str(value)


def swap(match, want):
    head = match.group(0)[:match.start(1) - match.start(0)]
    tail = match.group(0)[match.end(1) - match.start(0):]
    return head + want + tail


registry = {e['id']: e for e in json.loads((ROOT / '数据/城市空间名录.json').read_text(encoding='utf-8'))['entries']}
before = None
if args.before:
    snap = json.loads((ROOT / args.before).read_text(encoding='utf-8'))
    before = {e['id']: e for e in snap['entries']}

changed, residual = [], []
for path in sorted((ROOT / '分卷/原稿').glob('*.md')):
    text = path.read_text(encoding='utf-8-sig')
    matches = list(compiler.PATTERN.finditer(text))
    spans = [(m.group(1), m.end(), matches[i + 1].start() if i + 1 < len(matches) else len(text)) for i, m in enumerate(matches)]
    pieces = []
    cursor = 0
    for eid, start, end in spans:
        body = text[start:end]
        entry = registry[eid]
        sections = sections_of(body)
        patched = {}
        for field, patterns in compiler.FIELD_PATTERNS.items():
            if field not in entry:
                continue
            want = fmt(entry[field])
            for tag in scan_tags(field):
                base = patched.get(tag, sections.get(tag, ''))
                if not base:
                    continue
                replaced = base
                for pat in patterns:
                    replaced = re.sub(pat, lambda m, w=want: swap(m, w), replaced)
                if replaced != base:
                    patched[tag] = replaced
                    changed.append((eid, field, tag, fmt(before[eid][field]) if before and field in before.get(eid, {}) else '?', want))
        new_body = body
        for tag, replaced in patched.items():
            new_body = new_body.replace(sections[tag], replaced, 1)
        if before:
            for field in compiler.FIELD_PATTERNS:
                if field not in entry or field not in before[eid] or before[eid][field] == entry[field]:
                    continue
                stale = fmt(before[eid][field])
                hit = re.search(r'(?<![\d.])' + re.escape(stale) + r'\s*(?:人(?!为|是|次)|户|平方米|平方公里|米)', new_body)
                if hit:
                    residual.append((eid, field, stale, new_body[max(0, hit.start() - 20):hit.end() + 4].replace('\n', '')))
        pieces.append(text[cursor:start])
        pieces.append(new_body)
        cursor = end
    pieces.append(text[cursor:])
    if not args.dry_run:
        path.write_text(''.join(pieces), encoding='utf-8', newline='')

print(json.dumps(dict(段落改动=len(changed), 涉及条目=len({c[0] for c in changed})), ensure_ascii=False))
for row in changed:
    print(*row, sep='\t')
if residual:
    print('--- 条目正文里仍出现旧数值字面量，需人工确认是否同一含义 ---')
    for row in sorted(set(residual)):
        print(*row, sep='\t')
