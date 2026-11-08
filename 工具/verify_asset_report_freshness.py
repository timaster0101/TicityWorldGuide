# -*- coding: utf-8 -*-
"""图片资产核验生成物对拍闸门：把 数据/图片资产核验.json 与 数据/图片复验清单.md 逐字段对回现算。

为什么要这条闸门：2026-11-07 那次假绿的现场是——判据代码已经按 C136 补了 iTXt 档，
但盘上产物还停在 2026-11-06 20:59 的旧判据读数（失败 0、C2PA 在位 60），而 `test_image_assets.py:690`
读的就是这份盘上产物；同一时刻现算给出 通过 1058／失败 58。两边同时成立，全量单测照常全绿，
人眼看到的却是「1116/1116 全通过」。本闸门把「现算」与「落盘」并排逐字段对拍，任一侧改动没同步就判红。

统计面：现算侧扫 数据/开图清单.json 里全部 image_file 格（逐枚读字节，不排除任何容器），
落盘侧只读那两份生成物，不读 mtime、不按 mtime 猜；清单直数格数独立于核验器，用来兜「判据本身失效」。
口径散文（判据／C2PA口径／提示口径／声明／不改名口径）单独成一类判据：本轮改 C136 时
文件格数／通过格数／失败格数 三个数新旧完全相同（1116／1116／0），只数数字抓不到，必须让文本也进对拍面。

本闸门不修文件、不重跑生成器、不给产物补写任何读数。
修法只有一条：python 工具/verify_image_assets.py 重跑后复对本脚本。

跑法：
    python 工具/verify_asset_report_freshness.py            # 正检，rc=0 表示产物与现算逐字段一致
    python 工具/verify_asset_report_freshness.py --negtest  # 六类判据逐条注入自证
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REL_JSON = '数据/图片资产核验.json'
REL_MD = '数据/图片复验清单.md'
REL_MANIFEST = '数据/开图清单.json'

K_JSON_MISSING = '核验产物 JSON 不在盘上'
K_MD_MISSING = '复验工作单不在盘上'
K_COUNT_DRIFT = '核验产物的数字读数与现算不一致'
K_CRITERION_STALE = '核验产物的口径文本仍出自旧版判据'
K_MD_STALE = '复验工作单与现渲染文本不一致'
K_VERIFIER_INERT = '现算格数与清单直数格数不等（核验器没数到格，不得当作通过）'
ALL_KINDS = (K_JSON_MISSING, K_MD_MISSING, K_COUNT_DRIFT, K_CRITERION_STALE, K_MD_STALE, K_VERIFIER_INERT)

# 这几段是从判据代码里写出来的散文，改判据必然改它们；数字没变时只有它们能证明产物属于哪一版判据。
CRITERION_FIELDS = ('判据', 'C2PA口径', '提示口径', '声明', '图集外扩展名体检.不改名口径')


def _brief(value):
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return text[:70] + ('…' if len(text) > 70 else '')


def direct_cells(root=ROOT):
    """清单直数格数：自己扫 image_file，不借核验器的遍历，作为「判据本身失效」的对照面。"""
    data = json.loads((root / REL_MANIFEST).read_text(encoding='utf-8'))
    return [p for it in data['items'] if it.get('image_file') for p in it['image_file']]


def read_disk(root=ROOT):
    json_path, md_path = root / REL_JSON, root / REL_MD
    report = json.loads(json_path.read_text(encoding='utf-8')) if json_path.is_file() else None
    md = md_path.read_text(encoding='utf-8') if md_path.is_file() else None
    return report, md


def compute(root=ROOT):
    """现算侧：直接调 verify_image_assets 的 check/render，与生成器共用同一份判据代码。

    落盘 JSON 不带 逐格（verify_image_assets.main 写前剔掉），这里同样剔掉，否则每次对拍都差一整块。
    """
    import verify_image_assets as va
    items = json.loads((ROOT / REL_MANIFEST).read_text(encoding='utf-8'))['items']
    report = va.check(items)
    md = va.render_worksheet(report, items)
    return {k: v for k, v in report.items() if k != '逐格'}, md


def diff_fields(disk, new):
    """逐字段对拍（嵌套 dict 按子键展开，整块字典里一处不同不能只报一行）。"""
    out = []
    for key in sorted(set(disk) | set(new)):
        if key not in disk:
            out.append((key, '（产物缺该键）', _brief(new[key])))
        elif key not in new:
            out.append((key, _brief(disk[key]), '（现算无该键）'))
        elif isinstance(disk[key], dict) and isinstance(new[key], dict):
            for sub in sorted(set(disk[key]) | set(new[key])):
                dv, nv = disk[key].get(sub), new[key].get(sub)
                if dv != nv:
                    out.append(('%s.%s' % (key, sub), _brief(dv), _brief(nv)))
        elif disk[key] != new[key]:
            out.append((key, _brief(disk[key]), _brief(new[key])))
    return out


def first_diff_line(disk_md, new_md):
    for n, (a, b) in enumerate(zip(disk_md.splitlines(), new_md.splitlines()), 1):
        if a != b:
            return n, a[:60], b[:60]
    return max(len(disk_md.splitlines()), len(new_md.splitlines())), '', ''


def compare(disk_report, disk_md, new_report, new_md, direct_n):
    """返回 (读数, 违例)。违例首项是判据名（本文件顶部常量），负测按名字精确匹配。"""
    readings = {
        '清单直数格数': direct_n,
        '现算文件格数': new_report['文件格数'],
        '现算通过格数': new_report['通过格数'],
        '现算失败格数': new_report['失败格数'],
        '产物文件格数': disk_report['文件格数'] if disk_report else 0,
        '产物失败格数': disk_report['失败格数'] if disk_report else 0,
        '对拍字段数': len(new_report),
    }
    bad = []
    if disk_report is None:
        bad.append((K_JSON_MISSING, '%s：%s' % (K_JSON_MISSING, REL_JSON)))
    if disk_md is None:
        bad.append((K_MD_MISSING, '%s：%s' % (K_MD_MISSING, REL_MD)))
    if direct_n != new_report['文件格数']:
        bad.append((K_VERIFIER_INERT, '%s：清单 %d 格，现算 %d 格' % (
            K_VERIFIER_INERT, direct_n, new_report['文件格数'])))
    if disk_report is not None:
        diffs = diff_fields(disk_report, new_report)
        counts = [d for d in diffs if d[0] not in CRITERION_FIELDS]
        texts = [d for d in diffs if d[0] in CRITERION_FIELDS]
        readings['数字漂移字段数'] = len(counts)
        readings['口径漂移字段数'] = len(texts)
        if counts:
            bad.append((K_COUNT_DRIFT, '%s：%d 个字段，例 %s' % (
                K_COUNT_DRIFT, len(counts), '；'.join('%s 盘=%s 现=%s' % c for c in counts[:3]))))
        if texts:
            bad.append((K_CRITERION_STALE, '%s：%s ← 产物挂的是旧判据的文本，重跑生成器才会换过来' % (
                K_CRITERION_STALE, '、'.join(c[0] for c in texts))))
    if disk_md is not None:
        readings['工作单行数'] = len(disk_md.splitlines())
        readings['现渲染行数'] = len(new_md.splitlines())
        if disk_md != new_md:
            n, a, b = first_diff_line(disk_md, new_md)
            bad.append((K_MD_STALE, '%s：第 %d 行起不同（盘「%s」／现「%s」）' % (K_MD_STALE, n, a, b)))
    return readings, bad


def run_negtest():
    """六类判据逐条注入：在内存里造违例，产物与图片一个都不动；原样数据必须 0 违例。"""
    new_report, new_md = compute()
    disk_report, disk_md = read_disk()
    direct_n = len(direct_cells())
    baseline, baseline_bad = compare(disk_report, disk_md, new_report, new_md, direct_n)
    cases = [
        (K_JSON_MISSING, None, disk_md, new_report, new_md, direct_n),
        (K_MD_MISSING, disk_report, None, new_report, new_md, direct_n),
        (K_COUNT_DRIFT, dict(disk_report, 失败格数=disk_report['失败格数'] + 1), disk_md,
         new_report, new_md, direct_n),
        (K_CRITERION_STALE, dict(disk_report, 判据=disk_report['判据'] + '旧版尾巴'), disk_md,
         new_report, new_md, direct_n),
        (K_MD_STALE, disk_report, disk_md.replace('结构合规不等于视觉验收', '结构合规＝视觉验收', 1),
         new_report, new_md, direct_n),
        (K_VERIFIER_INERT, disk_report, disk_md, new_report, new_md, direct_n + 1),
    ]
    # 整块键缺失走数字支路（容器计数不是口径字段）；删掉 失败明细 会让整块明细在盘上不见，
    # 但那条只证明「少一块」抓得到，不能证明「同一块里的数变了」抓得到，所以两条都留。
    cases.append((K_COUNT_DRIFT, {k: v for k, v in disk_report.items() if k != '容器计数'},
                  disk_md, new_report, new_md, direct_n))
    cases.append((K_COUNT_DRIFT, {k: v for k, v in disk_report.items() if k != '失败明细'},
                  disk_md, new_report, new_md, direct_n))
    # 口径字段整块缺失单独算 K_CRITERION_STALE，不能因为「缺键」就退到数字支路——
    # 2026-11-06 那份过期产物恰恰是数字全对、只有口径文本是旧版。
    cases.append((K_CRITERION_STALE, {k: v for k, v in disk_report.items() if k != 'C2PA口径'},
                  disk_md, new_report, new_md, direct_n))

    injected = {kind for kind, *_ in cases}
    if injected != set(ALL_KINDS):
        print('注入面缺口（有判据没被注入，闸门不算自证）：%s' % ', '.join(sorted(set(ALL_KINDS) - injected)))
        return 1
    print('对照（原样数据）：违例 %d 条%s' % (
        len(baseline_bad), '' if not baseline_bad else ' ← ' + str(baseline_bad[0][1])))
    hit_kinds = set()
    for kind, dr, dm, nr, nm, dn in cases:
        _, bad = compare(dr, dm, nr, nm, dn)
        hit = next((b for b in bad if b[0] == kind), None)
        if hit:
            hit_kinds.add(kind)
        print('  [%s] %s: %s' % ('负测' if hit else '假绿', kind,
                                 hit[1][:90] if hit else '该判据未被检出（其余违例 %d 条）' % len(bad)))
    # 按「命中过的判据」计数而不是按用例条数：一条判据可以有多条注入用例（数字漂移就有改值/缺块两种形态），
    # 拿用例数比判据数会永远对不上，等于把自证写死成一个不可能成立的条件。
    print('判据总数: %d，注入并命中: %d' % (len(ALL_KINDS), len(hit_kinds)))
    if len(baseline_bad) or hit_kinds != set(ALL_KINDS):
        print('\n负测结论: 不合格（对照 %d 违例，漏报 %s）' % (
            len(baseline_bad), '、'.join(sorted(set(ALL_KINDS) - hit_kinds)) or '无'))
        return 1
    print('\n负测结论: 六类判据全部捕获')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='图片资产核验生成物与现算判据逐字段对拍')
    ap.add_argument('--negtest', action='store_true', help='注入六类违例自证判据有效')
    ap.add_argument('--root', default=str(ROOT), help='读产物的根目录（跨副本对拍用；现算侧始终按仓库真源）')
    args = ap.parse_args(argv)
    if args.negtest:
        return run_negtest()
    disk_report, disk_md = read_disk(Path(args.root).resolve())
    new_report, new_md = compute()
    readings, bad = compare(disk_report, disk_md, new_report, new_md, len(direct_cells()))
    for k, v in readings.items():
        print('%s: %s' % (k, v))
    if bad:
        print('\n生成物过期或与现算不一致（%d 条）：' % len(bad))
        for _, text in bad:
            print('  ✗', text)
        print('\n修法：python 工具/verify_image_assets.py 重跑两份产物后复对本脚本。')
        return 1
    print('\n两份生成物与现算逐字段一致，产物未过期。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
