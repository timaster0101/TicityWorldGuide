# -*- coding: utf-8 -*-
"""早于 E1 定档图片的归档落地闸门：逐张核对 backup/ 明细与盘上文件，并核对 backup 外的引用是否同步。

为什么要有这条闸门：187 张图片（178.9 MB）走的是 move，`数据/图集/`、`数据/影像作品/`、`数据/视觉控制资产/`、
`backup/` 全在 `.gitignore` 排除范围内，图片本体和本次改写的视频工程 JSON、影像归档说明都不进版本库——
git 既看不见搬迁，也看不见搬迁后引用脱链。全量单测跑的是临时目录里的合成夹具，仓库里这份真图只要被谁删了、
截断了、或者引用还停在旧路径，闸门全绿也照样不知道。本闸门读的是盘上真实字节和盘上真实文本，判据全部按内容对拍。

口径来源：定档下界与分域表沿用 工具/archive_pre_e1.py（即移交清单 §52.5），不在此另抄一份数字。
豁免口径（两条，各带理由，命中 0 即判红）：`数据/生成输入记录/` 按 `AI创作使用手册.md` 第 93 行「历史留档，不得改写、不得重生成」保留旧路径原文；`设计/2026-11-03-待办移交清单.md` 是按日留档的裁定台账，引述旧路径属取证记录而非取文件。

用法：
    python 工具/verify_pre_e1_archive.py              # 正检，rc=0 表示归档与引用一致
    python 工具/verify_pre_e1_archive.py --negtest    # 违例注入自证，每类判据必须各自被抓到
    python 工具/verify_pre_e1_archive.py --root DIR   # 对拍另一份仓库副本（负测用的临时夹具）
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive_pre_e1 as ARCH  # 下界取证、分域表、时间戳正则只有一份，闸门不另立口径

ROOT = Path(__file__).resolve().parents[1]
DETAIL_REL = 'backup/归档明细_早于定档_20261106.json'
TEXT_EXT = ('.json', '.md', '.py', '.txt', '.html', '.csv', '.cjs')
SKIP_DIRS = ('.git', '__pycache__', 'node_modules', 'backup')
ITEM_FIELDS = ('rel', 'dst', 'bytes', 'sha256_12', 'domain')
SHOT_GLOB = '数据/影像作品/工程文件/*/*/shots*.json'
PROJECT_ROOT = '数据/影像作品/工程文件'

# 判据名做成常量，违例文本一律以判据名为前缀：改散文措辞不会把负测悄悄改成假绿。
K_DETAIL_MISSING = '归档明细不在盘上或不可解析'
K_DETAIL_EMPTY = '归档明细条目为零'
K_FIELD_MISSING = '归档明细条目缺字段'
K_SRC_PRESENT = '已归档图片在原路径仍占位'
K_DST_MISSING = '已归档图片在 backup 不在盘上'
K_BYTE_DIFF = 'backup 图片字节数与明细不符'
K_SHA_DIFF = 'backup 图片摘要与明细不符'
K_DOMAIN_DIFF = '归档明细顶层读数与逐条不自洽'
K_DOMAIN_UNREGISTERED = '归档明细出现未登记分域'
K_CUTOFF_DRIFT = '定档下界取证与 §52.5 常量不一致'
K_LIVE_REF = 'backup 外文本仍按旧完整路径引用已归档图片'
K_EXEMPT_INERT = '豁免面一条也没命中'
K_SCAN_INERT = '引用扫描面内没有任何文本文件'
K_MATERIAL_UNARCHIVED = '视频工程素材路径未随归档改写'
K_MATERIAL_UNRESOLVED = '视频工程素材路径在盘上取不到'
K_MATERIALS_INERT = '视频工程素材一条也没解析出来'
ALL_KINDS = (K_DETAIL_MISSING, K_DETAIL_EMPTY, K_FIELD_MISSING, K_SRC_PRESENT, K_DST_MISSING,
             K_BYTE_DIFF, K_SHA_DIFF, K_DOMAIN_DIFF, K_DOMAIN_UNREGISTERED, K_CUTOFF_DRIFT,
             K_LIVE_REF, K_EXEMPT_INERT, K_SCAN_INERT, K_MATERIAL_UNARCHIVED,
             K_MATERIAL_UNRESOLVED, K_MATERIALS_INERT)

LIVE_REF_EXEMPT = (
    ('数据/生成输入记录/', 'AI创作使用手册.md:93「历史留档，不得改写、不得重生成」，旧路径是当时的投喂事实'),
    ('设计/2026-11-03-待办移交清单.md',
     '按日留档的裁定台账：正文引述旧路径是「当时闸门报了什么」的取证记录，不用于取文件。'
     '代价同记于 §53——该文件内今后若混入真活引用会被一起豁免，只能靠每轮复核「豁免命中」读数是否新增'),
)


def load_detail(root):
    """读明细；返回 (条目, 顶层读数, 违例)。零条目单列一条判据，不让空台账读起来像「无需搬迁」。"""
    p = root / DETAIL_REL
    bad = []
    if not p.is_file():
        return [], {}, [(K_DETAIL_MISSING, '%s：盘上找不到 %s' % (K_DETAIL_MISSING, DETAIL_REL))]
    try:
        doc = json.loads(p.read_text(encoding='utf-8'))
    except Exception as exc:
        return [], {}, [(K_DETAIL_MISSING, '%s：%s 解析失败 %s' % (K_DETAIL_MISSING, DETAIL_REL, exc))]
    items = doc.get('明细') or []
    if not items:
        bad.append((K_DETAIL_EMPTY, '%s：%s 的「明细」为空，无归档可自证' % (K_DETAIL_EMPTY, DETAIL_REL)))
    for i, it in enumerate(items):
        miss = [f for f in ITEM_FIELDS if f not in it]
        if miss:
            bad.append((K_FIELD_MISSING, '%s：第 %d 条缺字段 %s（%s）'
                        % (K_FIELD_MISSING, i, '／'.join(miss), it.get('rel', '?'))))
    top = {'状态': doc.get('状态'), '定档下界': doc.get('定档下界'), '张数': doc.get('张数'),
           '字节': doc.get('字节'), '分域': doc.get('分域') or {}}
    return items, top, bad


def check_files(items, root, top):
    """逐张三查：原路径必须空、backup 必须在、字节与 sha256-12 必须与明细一致。"""
    bad, present, absent = [], 0, 0
    for it in items:
        rel, dst = it.get('rel', ''), it.get('dst', '')
        if not rel or not dst:
            continue
        src, tgt = root / rel, root / dst
        if src.exists():
            bad.append((K_SRC_PRESENT, '%s：原路径仍占位 %s（归档是 move，不该两边都有）' % (K_SRC_PRESENT, rel)))
        if not tgt.is_file():
            bad.append((K_DST_MISSING, '%s：backup 不在盘上 %s' % (K_DST_MISSING, dst)))
            absent += 1
            continue
        raw = tgt.read_bytes()
        if 'bytes' in it and len(raw) != it['bytes']:
            bad.append((K_BYTE_DIFF, '%s：%s 实 %d 字节 ≠ 明细 %d' % (K_BYTE_DIFF, dst, len(raw), it['bytes'])))
            continue
        if 'sha256_12' in it:
            got = hashlib.sha256(raw).hexdigest()[:12]
            if got != it['sha256_12']:
                bad.append((K_SHA_DIFF, '%s：%s 摘要 %s ≠ 明细 %s'
                            % (K_SHA_DIFF, dst, got, it['sha256_12'])))
        present += 1
    dom = Counter(it.get('domain') for it in items if it.get('domain'))
    for k, v in dom.items():
        if k not in ARCH.EXPECTED_DOMAIN:
            bad.append((K_DOMAIN_UNREGISTERED, '%s：分域 %s 未登记在 archive_pre_e1.EXPECTED_DOMAIN'
                        % (K_DOMAIN_UNREGISTERED, k)))
        elif top.get('分域', {}).get(k) != v:
            bad.append((K_DOMAIN_DIFF, '%s：分域 %s 明细实数 %d ≠ 顶层 %s'
                        % (K_DOMAIN_DIFF, k, v, top.get('分域', {}).get(k))))
    if top.get('张数') != len(items):
        bad.append((K_DOMAIN_DIFF, '%s：顶层张数 %s ≠ 明细条数 %d' % (K_DOMAIN_DIFF, top.get('张数'), len(items))))
    total = sum(it.get('bytes', 0) for it in items)
    if top.get('字节') not in (None, total):
        bad.append((K_DOMAIN_DIFF, '%s：顶层字节 %s ≠ 明细求和 %d' % (K_DOMAIN_DIFF, top.get('字节'), total)))
    return bad, present, absent, dict(dom)


def ref_pattern(items):
    """旧完整路径的两种分隔符形态合成一条正则；只认「路径 + 文件名」，裸文件名不算脱链。"""
    olds = set()
    for it in items:
        rel = it.get('rel')
        if rel:
            olds.add(rel)
            olds.add(rel.replace('/', chr(92)))
    if not olds:
        return None
    return re.compile('|'.join(re.escape(o) for o in sorted(olds, key=len, reverse=True)))


def scan_refs(items, root):
    """backup 外文本里，未被 backup/ 前缀的旧完整路径＝未同步的活引用；豁免面单独计数并自证非空转。"""
    rx = ref_pattern(items)
    bad, scanned, hits = [], 0, []
    exempt = {p: 0 for p, _ in LIVE_REF_EXEMPT}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS]
        for name in sorted(filenames):
            if os.path.splitext(name)[1].lower() not in TEXT_EXT:
                continue
            p = Path(dirpath) / name
            r = p.relative_to(root).as_posix()
            scanned += 1
            text = p.read_text(encoding='utf-8', errors='ignore')
            for m in (rx.finditer(text) if rx else []):
                before = text[max(0, m.start() - 8):m.start()]
                if 'backup' in before:
                    continue  # 已同步成归档路径，属正确形态
                for pref, why in LIVE_REF_EXEMPT:
                    if r.startswith(pref):
                        exempt[pref] += 1
                        break
                else:
                    hits.append((r, m.group(0)))
    if scanned == 0:
        bad.append((K_SCAN_INERT, '%s：扫描面内 0 个文本文件，引用无从对拍（多半是根路径或忽略清单变了）'
                    % K_SCAN_INERT))
    for pref, why in LIVE_REF_EXEMPT:
        if exempt[pref] == 0:
            bad.append((K_EXEMPT_INERT, '%s：豁免前缀 %s 命中 0 处（%s）——豁免项若已无对应引用应删掉这条，'
                                        '若是引用被改写则不属本闸门范围，都不许留成空转'
                    % (K_EXEMPT_INERT, pref, why)))
    for r, v in hits[:20]:
        bad.append((K_LIVE_REF, '%s：%s 仍写旧路径 %s' % (K_LIVE_REF, r, v)))
    if len(hits) > 20:
        bad.append((K_LIVE_REF, '%s：另有 %d 处同类未逐条列出' % (K_LIVE_REF, len(hits) - 20)))
    return bad, scanned, len(hits), exempt


def check_materials(root):
    """视频工程 JSON 的 materials／scene_anchor 必须解析得到；属归档集却仍是旧形态的单列一条。"""
    bad, cells, unresolved, stale = [], 0, [], 0
    archived = set()
    detail = root / DETAIL_REL
    if detail.is_file():
        try:
            for it in (json.loads(detail.read_text(encoding='utf-8')).get('明细') or []):
                if it.get('rel'):
                    archived.add(Path(it['rel']).stem)
        except Exception:
            pass
    for p in sorted(root.glob(SHOT_GLOB)):
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
        except Exception as exc:
            bad.append((K_MATERIAL_UNRESOLVED, '%s：%s 解析失败 %s' % (K_MATERIAL_UNRESOLVED,
                        p.relative_to(root).as_posix(), exc)))
            continue
        for shot in (data if isinstance(data, list) else []):
            vals = list(shot.get('materials') or [])
            anchor = (shot.get('continuity_context') or {}).get('scene_anchor')
            if anchor:
                vals.append(anchor)
            for v in vals:
                cells += 1
                from_root = (root / v).is_file()
                from_proj = (root / PROJECT_ROOT / v).is_file()
                if from_root or from_proj:
                    continue
                if Path(v).stem in archived:
                    stale += 1
                    bad.append((K_MATERIAL_UNARCHIVED, '%s：%s 的素材 %s 属归档集却未加 backup/ 前缀'
                                % (K_MATERIAL_UNARCHIVED, p.relative_to(root).as_posix(), v)))
                else:
                    unresolved.append(v)
                    bad.append((K_MATERIAL_UNRESOLVED, '%s：%s 的素材 %s 从仓库根与工程根都取不到'
                                % (K_MATERIAL_UNRESOLVED, p.relative_to(root).as_posix(), v)))
    if cells == 0:
        bad.append((K_MATERIALS_INERT, '%s：%s 面内解析出 0 枚素材路径，检查是否等于把这一段判据废掉'
                    % (K_MATERIALS_INERT, SHOT_GLOB)))
    return bad, cells, stale, len(unresolved)


def check_cutoff(root):
    """下界按传入根现算，判据与 archive_pre_e1 同一条常量；取证崩掉本身就是一条违例。"""
    try:
        return [], *_cutoff(root)
    except SystemExit as exc:
        return [(K_CUTOFF_DRIFT, '%s：%s' % (K_CUTOFF_DRIFT, exc))], None, 0


def _cutoff(root):
    """与 archive_pre_e1.cutoff 同式，但按传入根扫描，好让负测在临时目录里跑。"""
    stamps = []
    for p in root.rglob('*'):
        if p.is_file() and p.suffix.lower() in ARCH.IMG_EXT and 'E1定档' in p.name:
            m = ARCH.TS.search(p.name)
            if m:
                stamps.append(datetime.fromtimestamp(int(m.group(1)) / 1000))
    if not stamps:
        raise SystemExit('取证失败：没有任何「E1定档」文件名带时间戳的图，下界无从确立')
    got = min(stamps)
    if got != ARCH.CUTOFF_EXPECT:
        raise SystemExit('定档下界漂移：取证 %s ≠ §52.5 记录的 %s'
                         % (got.isoformat(sep=' '), ARCH.CUTOFF_EXPECT.isoformat(sep=' ')))
    return got, len(stamps)


def run(root):
    items, top, bad = load_detail(root)
    file_bad, present, absent, dom = check_files(items, root, top)
    ref_bad, scanned, live_hits, exempt = scan_refs(items, root)
    mat_bad, cells, stale, unresolved = check_materials(root)
    cut_bad, cut, evidence = check_cutoff(root)
    readings = {'明细条数': len(items), '明细状态': top.get('状态'), '原路径仍占位': sum(
        1 for b in file_bad if b[0] == K_SRC_PRESENT), 'backup 在盘': present, 'backup 缺失': absent,
        '分域': dom, '文本扫描数': scanned, '活引用违例': live_hits,
        '豁免命中': dict(exempt), '素材枚数': cells, '素材未同步': stale, '素材取不到': unresolved,
        '下界': cut.isoformat(sep=' ') if cut else None, '下界取证枚数': evidence}
    return readings, bad + file_bad + ref_bad + mat_bad + cut_bad


def main(argv=None):
    ap = argparse.ArgumentParser(description='早于 E1 定档图片归档与引用同步闸门')
    ap.add_argument('--root', default=str(ROOT), help='对拍的仓库根（缺省本仓库）')
    ap.add_argument('--negtest', action='store_true', help='违例注入自证')
    args = ap.parse_args(argv)
    if args.negtest:
        return run_negtest()
    readings, bad = run(Path(args.root).resolve())
    print(json.dumps(readings, ensure_ascii=False, indent=2))
    if bad:
        print('\n违例 %d 条：' % len(bad))
        for kind, text in bad:
            print('  ✗', text)
        return 1
    print('\n归档落地与引用同步对账：一致（判据 %d 类，违例 0）' % len(ALL_KINDS))
    return 0


def build_fixture(root):
    """负测夹具：两真两假的最小可信归档现场，全部落在临时目录，不碰被守护的仓库。"""
    ms = int(ARCH.CUTOFF_EXPECT.timestamp() * 1000)
    stamp = '%013d' % ms
    (root / '数据' / '视觉控制资产' / '卡牌').mkdir(parents=True, exist_ok=True)
    (root / '数据' / '生成输入记录').mkdir(parents=True, exist_ok=True)
    (root / PROJECT_ROOT / '钛湖城城市介绍片' / '项目文件').mkdir(parents=True, exist_ok=True)
    body_a, body_b = b'PNG' + bytes(9), b'PNG' + bytes(11)
    items = [{'rel': '数据/视觉控制资产/卡牌/A.png', 'bytes': len(body_a),
              'sha256_12': hashlib.sha256(body_a).hexdigest()[:12], 'domain': '卡牌'},
             {'rel': '数据/视觉控制资产/卡牌/B.png', 'bytes': len(body_b),
              'sha256_12': hashlib.sha256(body_b).hexdigest()[:12], 'domain': '卡牌'}]
    for it, body in zip(items, (body_a, body_b)):
        dst = root / 'backup' / it['rel']
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(body)
        it['dst'] = 'backup/' + it['rel']
    detail = root / DETAIL_REL
    detail.write_text(json.dumps({'状态': '完成', '定档下界': ARCH.CUTOFF_EXPECT.isoformat(sep=' '),
                                  '张数': 2, '字节': len(body_a) + len(body_b), '分域': {'卡牌': 2},
                                  '明细': items}, ensure_ascii=False, indent=2), encoding='utf-8')
    # 下界取证枚数：文件名时间戳正好等于下界的那枚，算 1 枚
    (root / '数据' / '视觉控制资产' / ('E1定档-甲_%s_deadbeef.png' % stamp)).write_bytes(b'X' * 5)
    # 豁免面：历史留档保留旧路径原文
    (root / '数据' / '生成输入记录' / '画风诊断.txt').write_text(
        '母图取 %s\n' % items[0]['rel'], encoding='utf-8')
    (root / '设计').mkdir(exist_ok=True)
    (root / '设计' / '2026-11-03-待办移交清单.md').write_text(
        '闸门当轮报「仍写旧路径 %s」——留原文取证，不改写。\n' % items[1]['rel'], encoding='utf-8')
    # 活引用（工程 JSON）：已同步成从仓库根可解析的 backup/ 路径
    (root / PROJECT_ROOT / '钛湖城城市介绍片' / '项目文件' / 'shots.json').write_text(
        json.dumps([{'materials': [items[0]['dst']]},
                    {'continuity_context': {'scene_anchor': items[1]['dst']}}], ensure_ascii=False),
        encoding='utf-8')
    return items


INJECT = {}


def inject(name):
    def deco(fn):
        INJECT[name] = fn
        return fn
    return deco


@inject(K_DETAIL_MISSING)
def _i1(root, items):
    (root / DETAIL_REL).unlink()


@inject(K_DETAIL_EMPTY)
def _i2(root, items):
    (root / DETAIL_REL).write_text(json.dumps({'状态': '完成', '张数': 0, '字节': 0, '分域': {},
                                               '明细': []}, ensure_ascii=False), encoding='utf-8')
    (root / '数据' / '生成输入记录' / '画风诊断.txt').unlink()


@inject(K_FIELD_MISSING)
def _i3(root, items):
    doc = json.loads((root / DETAIL_REL).read_text(encoding='utf-8'))
    doc['明细'][0]['dst'] = 'backup/' + items[0]['rel']
    doc['明细'][0].pop('sha256_12')
    _rewrite(root, doc)


@inject(K_SRC_PRESENT)
def _i4(root, items):
    p = root / items[0]['rel']
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b'STILL HERE')


@inject(K_DST_MISSING)
def _i5(root, items):
    (root / items[0]['dst']).unlink()


@inject(K_BYTE_DIFF)
def _i6(root, items):
    p = root / items[0]['dst']
    p.write_bytes(p.read_bytes() + b'X')


@inject(K_SHA_DIFF)
def _i7(root, items):
    p = root / items[0]['dst']
    p.write_bytes(b'JPG' + bytes(9))  # 与明细同长度、不同内容：只有摘要判据能抓到


@inject(K_DOMAIN_DIFF)
def _i8(root, items):
    doc = json.loads((root / DETAIL_REL).read_text(encoding='utf-8'))
    doc['分域']['卡牌'] = 1
    _rewrite(root, doc)


@inject(K_DOMAIN_UNREGISTERED)
def _i9(root, items):
    doc = json.loads((root / DETAIL_REL).read_text(encoding='utf-8'))
    doc['明细'][1]['domain'] = '未登记域'
    doc['分域'] = {'卡牌': 1, '未登记域': 1}
    _rewrite(root, doc)


@inject(K_CUTOFF_DRIFT)
def _i10(root, items):
    for p in root.rglob('E1定档*.png'):
        p.rename(p.with_name(p.name.replace('_17', '_16', 1)))


@inject(K_LIVE_REF)
def _i11(root, items):
    (root / '设计').mkdir(exist_ok=True)
    (root / '设计' / '活引用.md').write_text('基准：`%s`\n' % items[0]['rel'], encoding='utf-8')


@inject(K_EXEMPT_INERT)
def _i12(root, items):
    for rel in ('数据/生成输入记录/画风诊断.txt', '设计/2026-11-03-待办移交清单.md'):
        p = root / rel
        if p.is_file():
            p.unlink()


@inject(K_SCAN_INERT)
def _i13(root, items):
    for dp, dn, fn in os.walk(root):
        if 'backup' in Path(dp).relative_to(root).as_posix():
            continue
        for f in fn:
            if os.path.splitext(f)[1].lower() in TEXT_EXT:
                (Path(dp) / f).unlink()


@inject(K_MATERIAL_UNARCHIVED)
def _i14(root, items):
    p = root / PROJECT_ROOT / '钛湖城城市介绍片' / '项目文件' / 'shots.json'
    p.write_text(json.dumps([{'materials': ['钛湖城城市介绍片/设定库/%s' % Path(items[0]['rel']).name]},
                             {'continuity_context': {'scene_anchor': items[1]['dst']}}],
                            ensure_ascii=False), encoding='utf-8')


@inject(K_MATERIAL_UNRESOLVED)
def _i15(root, items):
    p = root / PROJECT_ROOT / '钛湖城城市介绍片' / '项目文件' / 'shots.json'
    p.write_text(json.dumps([{'materials': ['钛湖城城市介绍片/设定库/根本不存在.png']},
                             {'continuity_context': {'scene_anchor': items[1]['dst']}}],
                            ensure_ascii=False), encoding='utf-8')


@inject(K_MATERIALS_INERT)
def _i16(root, items):
    p = root / PROJECT_ROOT / '钛湖城城市介绍片' / '项目文件' / 'shots.json'
    p.write_text(json.dumps([{'materials': []}], ensure_ascii=False), encoding='utf-8')


def _rewrite(root, doc):
    (root / DETAIL_REL).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')


def run_negtest():
    missing = [k for k in ALL_KINDS if k not in INJECT]
    extra = [k for k in INJECT if k not in ALL_KINDS]
    if missing or extra:
        print('负测注入面与判据表不一致：未注入 %s，多余 %s' % (missing or '无', extra or '无'))
        return 1
    base = Path(tempfile.mkdtemp(prefix='pre_e1_gate_'))
    caught, failures = {}, []
    try:
        build_fixture(base)
        readings, bad = run(base)
        if bad:
            failures.append('原样夹具应 0 违例，实得 %d 条：%s' % (len(bad), bad[0][1]))
            print('  ✗', failures[-1])
        else:
            print('原样夹具（临时目录 %s）：0 违例，读数 %s' % (base.name, json.dumps(
                {k: readings[k] for k in ('明细条数', '文本扫描数', '素材枚数', '下界取证枚数')},
                ensure_ascii=False)))
        for kind in ALL_KINDS:
            work = base.parent / (base.name + '_inj')
            if work.exists():
                shutil.rmtree(work)
            shutil.copytree(base, work)
            INJECT[kind](work, json.loads((work / DETAIL_REL).read_text(encoding='utf-8')).get('明细')
                         if (work / DETAIL_REL).is_file() else [])
            _, bad = run(work)
            kinds = {k for k, _ in bad}
            caught[kind] = kind in kinds
            if kind not in kinds:
                failures.append('%s：注入后未判红（违例 %s）' % (kind, [k for k, _ in bad] or '空'))
            print('  %s %s ← 注入后命中判据 %s' % ('✓' if kind in kinds else '✗', kind,
                                                  '／'.join(sorted(kinds)) or '无'))
            shutil.rmtree(work)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    hit = sum(1 for v in caught.values() if v)
    print('\n判据总数: %d，注入并命中: %d' % (len(ALL_KINDS), hit))
    residue = sorted(str(p) for p in base.parent.glob('pre_e1_gate_*') if p.exists())
    print('临时夹具残留复核: %d（按本脚本临时前缀 pre_e1_gate_* 整片数，不只数本轮那一个）' % len(residue))
    if failures or residue:
        print('负测结论: 有 %d 类未被抓到或残留未清（%s）——假绿风险，必须补'
              % (len(failures), residue[:3]))
        return 1
    print('负测结论: %d 类判据全部捕获，临时夹具零残留' % len(ALL_KINDS))
    return 0


if __name__ == '__main__':
    sys.exit(main())
