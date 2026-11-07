# -*- coding: utf-8 -*-
"""提示词基准冻结闸门：重投期每轮放量前后都跑它，核心判据是「基准漂移条数必须为 0」。

判据口径见 工具/freeze_prompt_baseline.py 的文件头：prompt_sha256 = 整份提示词 txt 去掉四行元数据后的文本摘要。
本闸门同时读三份真源并三方对拍：数据/提示词基准冻结.json（快照）、数据/开图清单.json（当前基准与回填）、
数据/开图提示词/*.txt（逐字原文）。任何一份单独绿都不算绿。

用法：
    python 工具/verify_prompt_baseline.py            # 正检，rc=0 表示基准仍冻结、冻结后落盘的格逐枚具备绑定资格
    python 工具/verify_prompt_baseline.py --negtest  # 违例注入自证：全部判据必须被检出，且在仓库外临时目录里做

绑到过期基准那一类有一条免红通道（2026-11-07）：占格备注逐字申报「维持原绑定 <前12位>」的条目只出读数、
不判红——撤绑/改绑是人工验收动作，闸门不许把它当成自己的违例去逼脚本改库；未申报的照旧判红。
"""
import argparse
import datetime
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REL_BASELINE = '数据/提示词基准冻结.json'
REL_MANIFEST = '数据/开图清单.json'
REL_PROMPT_DIR = '数据/开图提示词'
REL_I2I_DIR = '数据/图生图送入串'

META_LINE = re.compile(r'^- (?:状态|prompt_sha256|image_prompt_sha256|复验原因/备注)：')
MS_TS = re.compile(r'_(1\d{12})_')
RESIDUE_PREFIX = 'prompt_baseline_gate_'

K_FILE_MISSING = '冻结快照不在盘'
K_INERT = '快照解析出零条目'
K_COUNT = '条数三方不符'
K_ID_SET = '快照与清单ID集合不符'
K_DRIFT = '基准漂移'
K_TXT_DRIFT = '提示词txt与快照断链'
K_AFTER_UNQUALIFIED = '冻结后落盘的格不具备绑定资格'
K_AFTER_STALE_BIND = '冻结后落盘的格绑到过期基准'
K_ACCEPT_UNBOUND = '已验收却未绑定当前基准'
K_TIME_FLOOR = '冻结时刻不可解析或自相矛盾'
K_BASE_TOTAL = '基准总摘要与逐条重建不符'
K_IMG2IMG_PROVENANCE = '图生图格备案不完整'
K_I2I_BIND_MODE = '图生图格绑到送入串'
ALL_KINDS = (K_FILE_MISSING, K_INERT, K_COUNT, K_ID_SET, K_DRIFT, K_TXT_DRIFT,
             K_AFTER_UNQUALIFIED, K_AFTER_STALE_BIND, K_ACCEPT_UNBOUND, K_TIME_FLOOR, K_BASE_TOTAL,
             K_IMG2IMG_PROVENANCE, K_I2I_BIND_MODE)


def base_sha(text):
    keep = [l for l in text.split('\n')[:-1] if not META_LINE.match(l)]
    return hashlib.sha256(('\n'.join(keep) + '\n').encode('utf-8')).hexdigest()


def cell_ts(name):
    m = MS_TS.search(Path(name).name)
    return int(m.group(1)) if m else None


def load(root=ROOT):
    bp = root / REL_BASELINE
    snap = None
    if bp.exists():
        snap = json.loads(bp.read_text(encoding='utf-8'))
    data = json.loads((root / REL_MANIFEST).read_text(encoding='utf-8'))
    txts = {p.name.split('-', 1)[0]: p for p in sorted((root / REL_PROMPT_DIR).glob('*.txt'))}
    return snap, data, txts


def check(root=ROOT):
    """返回 (违例列表, 读数dict)。统计面：清单 items 全量、提示词目录 *.txt 全量、快照 entries 全量。"""
    viol = []
    readings = {}
    snap, data, txts = load(root)
    items = data['items']
    by_id = {it['id']: it for it in items}

    if snap is None:
        viol.append('%s：%s 不在盘，先跑 工具/freeze_prompt_baseline.py' % (K_FILE_MISSING, REL_BASELINE))
        return viol, readings

    entries = snap.get('entries') or []
    readings['快照条数'] = len(entries)
    readings['清单items条数'] = len(items)
    readings['清单声明条数'] = data.get('prompt_count')
    readings['提示词txt枚数'] = len(txts)
    if not entries:
        viol.append('%s：快照 entries 解析出 0 条（正则/键名读空也会打印通过，那类假绿由本条兜住）' % K_INERT)
        return viol, readings

    # 冻结时刻必须可解析，且 ISO 文本与毫秒数互推一致——否则「冻结后落盘」这条判据的分界线本身就是猜的。
    try:
        frozen_ms = int(snap['frozen_at_ms'])
        parsed = datetime.datetime.strptime(snap['frozen_at'], '%Y-%m-%d %H:%M:%S.%f')
        if abs(int(parsed.timestamp() * 1000) - frozen_ms) > 50:
            viol.append('%s：frozen_at=%s 与 frozen_at_ms=%d 互推差 %d 毫秒（>50 即判红）'
                        % (K_TIME_FLOOR, snap['frozen_at'], frozen_ms,
                           abs(int(parsed.timestamp() * 1000) - frozen_ms)))
    except Exception as exc:
        viol.append('%s：冻结时刻不可解析（%r）' % (K_TIME_FLOOR, exc))
        return viol, readings
    readings['frozen_at'] = snap['frozen_at']

    snap_map = {e['id']: e['prompt_sha256'] for e in entries}
    if len(snap_map) != len(entries):
        viol.append('%s：快照 entries 有重复 ID（%d 条 vs %d 个唯一 ID）' % (K_INERT, len(entries), len(snap_map)))

    # 1) 条数三方
    if not (len(entries) == len(items) == data.get('prompt_count')):
        viol.append('%s：快照 %d / 清单items %d / 清单prompt_count %s'
                    % (K_COUNT, len(entries), len(items), data.get('prompt_count')))
    # 2) ID 集合
    miss = sorted(set(snap_map) - set(by_id))
    extra = sorted(set(by_id) - set(snap_map))
    if miss or extra:
        viol.append('%s：快照多 %s / 清单多 %s' % (K_ID_SET, miss[:10], extra[:10]))
    # 3) 基准漂移（核心）
    drift = sorted(k for k in set(snap_map) & set(by_id) if snap_map[k] != by_id[k]['prompt_sha256'])
    readings['基准漂移条数'] = len(drift)
    readings['基准漂移清单'] = drift[:20]
    if drift:
        viol.append('%s：%d 条 prompt_sha256 自冻结以来变化（重投期改基准=已投格全部失去绑定资格，须追加裁定后 --force 换档）：%s'
                    % (K_DRIFT, len(drift), drift[:20]))
    # 4) txt 断链：txt 现算摘要 vs 快照（快照绿但 txt 被手改，正是这种对拍才看得见）
    txt_bad = []
    for eid, want in sorted(snap_map.items()):
        p = txts.get(eid)
        if p is None:
            txt_bad.append('%s(无文件)' % eid)
        elif base_sha(p.read_text(encoding='utf-8')) != want:
            txt_bad.append(eid)
    readings['txt断链条数'] = len(txt_bad)
    readings['txt断链清单'] = txt_bad[:20]
    if txt_bad:
        viol.append('%s：%d 条提示词 txt 去掉四行元数据后的现算摘要 ≠ 快照，即 txt 或清单有一侧未随生成器重跑：%s'
                    % (K_TXT_DRIFT, len(txt_bad), txt_bad[:20]))
    # 5) 基准总摘要自证：逐条重建再比对，防「entries 在但被局部改过而逐条判据恰好绕过」
    rebuilt = hashlib.sha256(('\n'.join('%s %s' % (k, v) for k, v in sorted(snap_map.items())) + '\n').encode('utf-8')).hexdigest()[:12]
    if rebuilt != snap.get('baseline_sha256_12'):
        viol.append('%s：逐条重建 %s ≠ 快照 baseline_sha256_12 %s' % (K_BASE_TOTAL, rebuilt, snap.get('baseline_sha256_12')))

    # 6) 冻结后落盘的格逐枚具备绑定资格
    #    注意判的是「资格」而不是「已绑」：本闸门只读不写，绑定与签署由 工具/sign_acceptance.py 执行
    #    （C139 起受用户明确委托可代签，但须逐条留代签申报行，判据在 工具/signing_declaration.py），
    #    所以「未绑定」在这里只报数不判红；判红的是「这枚格投出去之后基准又变了」——
    #    那才是 §54 关口B 把 60 枚打成 0/60 的那个失效形态，代签也不能补绑换档后的格。
    after_ids = []
    pre_after = 0
    for it in items:
        cells = list(it.get('image_file') or [])
        ts = [t for t in (cell_ts(c) for c in cells) if t is not None]
        post = [t for t in ts if t >= frozen_ms]
        pre_after += len(ts) - len(post)
        if post:
            post_cells = [c for c in cells if (cell_ts(c) or 0) >= frozen_ms]
            after_ids.append({'id': it['id'], 'n': len(post_cells),
                              'bind': it.get('image_prompt_sha256'), 'status': it['status'],
                              'cells': post_cells, 'prov': it.get('image_cell_provenance') or {}})
    cells_all = sum(len(list(it.get('image_file') or [])) for it in items)
    cells_ts = sum(len([t for t in (cell_ts(c) for c in (it.get('image_file') or [])) if t is not None]) for it in items)
    readings['格总数'] = cells_all
    readings['带毫秒时间戳的格数'] = cells_ts
    readings['无时间戳的格数'] = cells_all - cells_ts
    readings['冻结前落盘的带时间戳格数'] = pre_after
    readings['冻结后落盘的格数'] = sum(r['n'] for r in after_ids)
    readings['冻结后涉及条目数'] = len(after_ids)

    # 6b) 图生图通道备案（C135）：绑定摘要一律仍是冻结串＝快照基准，实际送入串只作第二字段；
    #     代价是必须逐格留可回查的送入串原文、其摘要与母图；缺任一项判红，绑到送入串摘要另判一类红。
    i2i_ok = set()
    i2i_bind_bad = []
    i2i_bad = []
    for r in after_ids:
        for c in r['cells']:
            rec = r['prov'].get(c)
            if not rec:
                continue
            ch = rec.get('通道')
            if ch == '文本生图':
                continue
            if ch != '图生图':
                i2i_bad.append('%s/%s 通道=%r（只认 图生图/文本生图）' % (r['id'], c, ch))
                continue
            sp = rec.get('送入串')
            ss = rec.get('送入串sha256')
            mt = rec.get('母图')
            if not sp or not (root / sp).exists():
                i2i_bad.append('%s/%s 送入串文件不在盘：%s' % (r['id'], c, sp))
                continue
            if not ss:
                i2i_bad.append('%s/%s 缺 送入串sha256 字段' % (r['id'], c))
                continue
            if base_sha((root / sp).read_text(encoding='utf-8')) != ss:
                i2i_bad.append('%s/%s 送入串现算摘要 ≠ 备案 送入串sha256' % (r['id'], c))
                continue
            if not mt or not (root / mt).exists():
                i2i_bad.append('%s/%s 母图不在盘：%s' % (r['id'], c, mt))
                continue
            i2i_ok.add((r['id'], c))
            # 备案是否可回查与绑定是否按冻结串，是两件事：前者红了后者仍要给读数，否则一类违例会顶掉另一类
            if r['bind'] and r['bind'] != snap_map.get(r['id']):
                i2i_bind_bad.append('%s/%s 绑定摘要 %s ≠ 冻结基准 %s（C135 口径：按冻结串绑）' % (r['id'], c, (r['bind'] or '')[:12], (snap_map.get(r['id']) or '')[:12]))

    readings['图生图格绑到送入串违例数'] = len(i2i_bind_bad)
    readings['图生图备案合规格数'] = len(i2i_ok)
    readings['图生图备案违例数'] = len(i2i_bad)
    if i2i_bad:
        viol.append('%s：%d 项 %s' % (K_IMG2IMG_PROVENANCE, len(i2i_bad), i2i_bad[:20]))
    if i2i_bind_bad:
        viol.append('%s：%d 枚 %s' % (K_I2I_BIND_MODE, len(i2i_bind_bad), i2i_bind_bad[:20]))

    unqualified = [(r['id'], r['n']) for r in after_ids if snap_map.get(r['id']) != by_id[r['id']]['prompt_sha256']]
    bad_ids = {u[0] for u in unqualified}
    readings['冻结后具备绑定资格格数'] = sum(r['n'] for r in after_ids if r['id'] not in bad_ids)
    readings['冻结后未绑定待人工签收格数'] = sum(r['n'] for r in after_ids if not r['bind'])
    unbound_wait = [r['id'] for r in after_ids if not r['bind'] and r['id'] not in bad_ids]
    if unbound_wait:
        readings['冻结后未绑定条目名单_不判红只待人工签收'] = unbound_wait[:20]
    if unqualified:
        viol.append('%s：%d 枚格的文件名毫秒时间戳 ≥ frozen_at 但其条目基准在冻结后又变过，涉及条目 %s（这批只能重投，不能补绑）'
                    % (K_AFTER_UNQUALIFIED, sum(n for _, n in unqualified), [i for i, _ in unqualified][:20]))
    # 过期绑定的豁免口子（2026-11-07「1 回填」裁定「全部 264 都占格」）：占格可以，撤绑/改绑归签署通道。
    # 所以备注里逐字申报了「维持原绑定 <该串前12位>」的条目不再判红，改出一条待撤销的读数；
    # 没申报（或申报了却没复述前 12 位＝挂的是另一串）照旧判红——豁免只认申报与绑定摘要能对上这一件事。
    # C139 代签那轮把当时命中本通道的条目全部重绑到冻结串并撤其申报，通道保留给后续轮次；
    # 本闸门仍只读不写，不会为了转绿去改库。
    # 统计面：清单 items[].review_note（生成器从 数据/开图验收备注.json 逐条镜像的当前备注串）。
    stale, stale_declared = [], []
    for r in after_ids:
        if r['bind'] and r['bind'] != snap_map.get(r['id']):
            if '维持原绑定 %s' % str(r['bind'])[:12] in (by_id[r['id']].get('review_note') or ''):
                stale_declared.append(r['id'])
            else:
                stale.append(r['id'])
    readings['过期绑定已申报待人工撤销条数'] = len(stale_declared)
    if stale_declared:
        readings['过期绑定已申报条目名单_不判红只待人工撤销'] = stale_declared[:20]
    if stale:
        viol.append('%s：冻结后落盘的格绑到了 ≠ 快照基准的摘要，且其 review_note 里没有'
                    '「维持原绑定 <前12位>」申报（C135 口径：按冻结串绑，送入串只作第二字段；'
                    '2026-11-07 起占格备注的申报是这类绑定唯一的免红通道），涉及条目 %s'
                    % (K_AFTER_STALE_BIND, stale[:20]))
    # 7) 签收与绑定的矛盾：已验收必须绑当前基准，否则就是「复制摘要补绑」被洗成验收
    def bind_ok(it):
        b = it.get('image_prompt_sha256') or ''
        if not b:
            return False
        return b == snap_map.get(it['id'])  # C135：图生图也不放过，绑定摘要必须是冻结串

    acc_bad = [it['id'] for it in items if it['status'] == '已验收' and not bind_ok(it)]
    readings['已验收条数'] = sum(1 for it in items if it['status'] == '已验收')
    if acc_bad:
        viol.append('%s：%d 条 status=已验收 但绑定摘要 ≠ 快照基准 %s' % (K_ACCEPT_UNBOUND, len(acc_bad), acc_bad[:20]))
    # 历史面（只报数不判红）：冻结前落盘且绑定为空的条目——这批只能靠重投出清，不能靠补绑出清
    readings['冻结前格数_绑定为空的历史面'] = sum(
        1 for it in items if (it.get('image_file') and not it.get('image_prompt_sha256')))
    readings['当前绑定条数'] = sum(1 for it in items if it.get('image_prompt_sha256'))
    return viol, readings


# ---------- 违例注入自证 ----------

def build_fixture(tmp):
    """在仓库外临时目录搭一棵最小可用的树：3 条在册条目；X01 带一枚冻结后落盘的文本生图格（逐字回绑），X03 带一枚冻结后落盘的图生图格（image_prompt_sha256 仍是冻结串，实际送入串摘要只记在 image_cell_provenance）。"""
    (tmp / REL_PROMPT_DIR).mkdir(parents=True, exist_ok=True)
    (tmp / '数据').mkdir(exist_ok=True)
    body = '# 开图提示词｜X01 甲\n\n## 对应关系\n\n- 地点ID：X01\n\n## 提示词正文\n\n【画风锚点】text\n'
    body2 = '# 开图提示词｜X02 乙\n\n## 对应关系\n\n- 地点ID：X02\n\n## 提示词正文\n\n【画面定位】text2\n'
    (tmp / REL_PROMPT_DIR / 'X01-甲.txt').write_text(body, encoding='utf-8')
    (tmp / REL_PROMPT_DIR / 'X02-乙.txt').write_text(body2, encoding='utf-8')
    body3 = '# 开图提示词｜X03 丙\n\n## 对应关系\n\n- 地点ID：X03\n\n## 提示词正文\n\n【画面定位】text3\n'
    i2i_body = '# 开图提示词｜X03 丙\n\n## 对应关系\n\n- 地点ID：X03\n\n## 提示词正文\n\n【画面定位】text3（图生图实际送入版）\n'
    (tmp / REL_PROMPT_DIR / 'X03-丙.txt').write_text(body3, encoding='utf-8')
    (tmp / REL_I2I_DIR).mkdir(parents=True, exist_ok=True)
    i2i_rel = REL_I2I_DIR + '/X03-丙-送入串.txt'
    (tmp / REL_I2I_DIR / 'X03-丙-送入串.txt').write_text(i2i_body, encoding='utf-8')
    (tmp / '数据' / '图集').mkdir(exist_ok=True)
    mother_rel = '数据/图集/X03-母图.png'
    (tmp / '数据' / '图集' / 'X03-母图.png').write_bytes(b'\x89PNG\r\n\x1a\n')
    sha1, sha2 = base_sha(body), base_sha(body2)
    sha3, sha3b = base_sha(body3), base_sha(i2i_body)
    frozen_ms = 1700000000000
    i2i_cell = 'X03-丙-v01_' + str(frozen_ms + 30000) + '_cafebabe.png'
    items = [
        {'id': 'X01', 'name': '甲', 'type': '地标', 'prompt_sha256': sha1,
         'image_file': ['X01-甲-E1重出-v09_%d_deadbeef.png' % (frozen_ms + 60000)],
         'image_prompt_sha256': sha1, 'status': '待复验'},
        {'id': 'X02', 'name': '乙', 'type': '地标', 'prompt_sha256': sha2, 'image_file': [], 'status': '待开图'},
        {'id': 'X03', 'name': '丙', 'type': '地标', 'prompt_sha256': sha3,
         'image_file': [i2i_cell], 'image_prompt_sha256': sha3, 'status': '待复验',
         'image_cell_provenance': {i2i_cell: {'通道': '图生图', '送入串': i2i_rel,
                                             '送入串sha256': sha3b, '母图': mother_rel}}},
    ]
    with (tmp / REL_MANIFEST).open('w', encoding='utf-8') as fh:
        json.dump({'prompt_count': 3, 'items': items}, fh, ensure_ascii=False)
    snap = {
        'frozen_at': '2023-11-15 06:13:20.000',
        'frozen_at_ms': frozen_ms,
        'baseline_sha256_12': hashlib.sha256(('\n'.join(['X01 ' + sha1, 'X02 ' + sha2, 'X03 ' + sha3]) + '\n').encode('utf-8')).hexdigest()[:12],
        'entries': [
            {'id': 'X01', 'prompt_sha256': sha1, 'cell_ts_ms': []},
            {'id': 'X02', 'prompt_sha256': sha2, 'cell_ts_ms': []},
            {'id': 'X03', 'prompt_sha256': sha3, 'cell_ts_ms': []},
        ],
    }
    with (tmp / REL_BASELINE).open('w', encoding='utf-8') as fh:
        json.dump(snap, fh, ensure_ascii=False)
    return {'sha1': sha1, 'sha2': sha2, 'sha3': sha3, 'sha3b': sha3b, 'frozen_ms': frozen_ms,
            'i2i_cell': i2i_cell, 'i2i_rel': i2i_rel, 'mother_rel': mother_rel}


def negtest():
    tmp = Path(tempfile.mkdtemp(prefix=RESIDUE_PREFIX))
    lines = []
    rc = 0
    try:
        base = build_fixture(tmp)
        viol, _ = check(tmp)
        lines.append('对照（夹具原样）：%d 违例 %s' % (len(viol), [v.split('：')[0] for v in viol]))
        if viol:
            rc = 1
            lines.append('✗ 夹具本底不干净，后续注入读数全部不可用')
            print('\n'.join(lines))
            return 1

        def mutate(what):
            # 每个 case 从干净夹具重建，避免上一条违例掩盖下一条
            shutil.rmtree(tmp / '数据')
            build_fixture(tmp)
            mp = tmp / REL_MANIFEST
            bp = tmp / REL_BASELINE
            md = json.loads(mp.read_text(encoding='utf-8'))
            sd = json.loads(bp.read_text(encoding='utf-8'))
            if what == K_FILE_MISSING:
                bp.unlink()
            elif what == K_INERT:
                sd['entries'] = []
                bp.write_text(json.dumps(sd, ensure_ascii=False), encoding='utf-8')
            elif what == K_COUNT:
                md['prompt_count'] = 7
                mp.write_text(json.dumps(md, ensure_ascii=False), encoding='utf-8')
            elif what == K_ID_SET:
                md['items'] = md['items'][:1]
                mp.write_text(json.dumps(md, ensure_ascii=False), encoding='utf-8')
            elif what == K_DRIFT:
                p = tmp / REL_PROMPT_DIR / 'X01-甲.txt'
                t = p.read_text(encoding='utf-8')
                new = base_sha(t + '【追加】换档\n')
                p.write_text(t + '【追加】换档\n', encoding='utf-8')
                md['items'][0]['prompt_sha256'] = new
                mp.write_text(json.dumps(md, ensure_ascii=False), encoding='utf-8')
            elif what == K_TXT_DRIFT:
                p = tmp / REL_PROMPT_DIR / 'X01-甲.txt'
                p.write_text(p.read_text(encoding='utf-8') + '【手改正文但没重跑生成器】\n', encoding='utf-8')
            elif what == K_AFTER_UNQUALIFIED:
                # 注入形态＝冻结之后该条基准又换过档：快照里 X01 的摘要与当前清单不一致
                sd['entries'][0]['prompt_sha256'] = 'a' * 64
                bp.write_text(json.dumps(sd, ensure_ascii=False), encoding='utf-8')
            elif what == K_AFTER_STALE_BIND:
                md['items'][0]['image_prompt_sha256'] = 'f' * 64
                mp.write_text(json.dumps(md, ensure_ascii=False), encoding='utf-8')
            elif what == '申报在位':
                md['items'][0]['image_prompt_sha256'] = 'f' * 64
                md['items'][0]['review_note'] = '占格读数：image_prompt_sha256 维持原绑定 %s（本轮不撤不签）' % ('f' * 12)
                mp.write_text(json.dumps(md, ensure_ascii=False), encoding='utf-8')
            elif what == '申报没复述前12位':
                md['items'][0]['image_prompt_sha256'] = 'f' * 64
                md['items'][0]['review_note'] = '占格读数：image_prompt_sha256 维持原绑定（本轮不撤不签）'
                mp.write_text(json.dumps(md, ensure_ascii=False), encoding='utf-8')
            elif what == K_ACCEPT_UNBOUND:
                md['items'][0]['status'] = '已验收'
                md['items'][0]['image_prompt_sha256'] = 'e' * 64
                mp.write_text(json.dumps(md, ensure_ascii=False), encoding='utf-8')
            elif what == K_TIME_FLOOR:
                sd['frozen_at_ms'] = sd['frozen_at_ms'] + 86400000
                bp.write_text(json.dumps(sd, ensure_ascii=False), encoding='utf-8')
            elif what == K_IMG2IMG_PROVENANCE:
                rec = md['items'][2]['image_cell_provenance'][base['i2i_cell']]
                rec['送入串sha256'] = 'd' * 64
                mp.write_text(json.dumps(md, ensure_ascii=False), encoding='utf-8')
            elif what == K_I2I_BIND_MODE:
                md['items'][2]['image_prompt_sha256'] = base['sha3b']
                mp.write_text(json.dumps(md, ensure_ascii=False), encoding='utf-8')
            elif what == K_BASE_TOTAL:
                sd['baseline_sha256_12'] = '0' * 12
                bp.write_text(json.dumps(sd, ensure_ascii=False), encoding='utf-8')
            return check(tmp)

        hit = {}
        for kind in ALL_KINDS:
            viol, _ = mutate(kind)
            names = [v.split('：')[0] for v in viol]
            hit[kind] = kind in names
            if not hit[kind]:
                rc = 1
            lines.append('%s %s → %d 违例 %s' % ('✓' if hit[kind] else '✗', kind, len(viol), names[:4]))
        lines.append('命中 %d/%d' % (sum(hit.values()), len(ALL_KINDS)))
        # 免红通道自证（2026-11-07 加）：两头各钉一次——只钉正向等于把判据关掉，只钉反向等于让真申报也红。
        for case, want_red in (('申报在位', False), ('申报没复述前12位', True)):
            viol, readings = mutate(case)
            names = [v.split('：')[0] for v in viol]
            fired = K_AFTER_STALE_BIND in names
            ok = (fired == want_red)
            if case == '申报在位':
                ok = ok and readings.get('过期绑定已申报待人工撤销条数') == 1
            if not ok:
                rc = 1
            lines.append('%s 免红通道「%s」→ %s判红、申报在位读数=%s %s'
                         % ('✓' if ok else '✗', case, '照' if fired else '未',
                            readings.get('过期绑定已申报待人工撤销条数'), names[:4]))
        # 残留口径：连被守护脚本自己的临时前缀一起数，仓库内不得出现任何 gate 产物
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
        print('❌ 提示词基准冻结闸门判红 %d 条：' % len(viol))
        for v in viol:
            print('   ✗ %s' % v)
        return 1
    print('✅ 提示词基准冻结闸门通过：漂移 0 条、txt 断链 0 条、冻结后落盘 %s 枚逐枚具备绑定资格（涉及 %s 条，其中 %s 枚待签收填绑定）'
          % (readings.get('冻结后落盘的格数'), readings.get('冻结后涉及条目数'),
             readings.get('冻结后未绑定待人工签收格数')))
    if readings.get('过期绑定已申报待人工撤销条数'):
        print('   （附读数，非违例）已申报「维持原绑定」的过期绑定 %s 条 %s：占格本身合规，'
              '但那串摘要绑的是被替换前的旧文件、已过期，撤销或重绑走签署通道（C139 起可受委托代执行）。'
              % (readings['过期绑定已申报待人工撤销条数'],
                 readings.get('过期绑定已申报条目名单_不判红只待人工撤销')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
