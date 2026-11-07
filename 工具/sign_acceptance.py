# -*- coding: utf-8 -*-
"""C139 受委托代签验收：按冻结快照绑定、置已验收，并逐条留代签申报行。

只在用户明确委托代签时运行。默认干跑（只打印计划与读数，不落盘），加 --execute 才写。
守卫是「没申报不许签」，不是「不许签」：申报判据的唯一真源是 工具/signing_declaration.py，
本脚本写出的行必须当场过 check_sign_declaration，过不了就退出非零、不落盘。

签的语义边界（C139）：accepted 自此只表示机械判据验收通过，不表示人工逐张目视通过、
也不表示画风已过关。每条申报行都逐字写明「人工逐张目视未执行」，画风读数只作读数附上。

依据读数一律现取盘上真源，不预填、不抄第二份：
  绑定资格 —— 数据/提示词基准冻结.json 逐条 prompt_sha256（漂移非 0 即退出，换档后的格只能重投）；
  投后核验 —— 工具/reshoot_campaign_2026_11_06/round_readings{,_r1}.json 里 file 与当前格 basename 相等的那一行；
  结构核验 —— 工具/verify_image_assets.py 的 check() 现算（不读可能过期的 图片资产核验.json）；
  画风读数 —— 同目录 clip_style_scores_r1.tsv 按格 basename 取，阈值取 clip_style_r1_readings.json 的正典对照。
当前格在两份投后核验里都查不到时（早于重投期的图集格），依据只写结构核验与绑定资格，
并逐字写明「本轮无该格投后核验读数」——不许拿别轮的读数顶替。

四条过期绑定（占格当时申报过「维持原绑定」的那批）重绑到冻结串，其 generation_input_*／
image_base_prompt_sha256 描述的是被替换前旧格的补充输入、不是当前格，一并清空；
旧值逐字记进申报行，数据/生成输入记录/*.txt 原件不删。名单不手抄：由历史读数里的「维持原绑定」现派生。

历史回填读数行一律不改写：那些行记的是占格当时的事实，代签是其后追加的另一行，两者并存才可追溯。

跑法：
    python 工具/sign_acceptance.py              干跑，打印计划与逐条依据
    python 工具/sign_acceptance.py --execute    落盘（写备注与清单），随后须重跑 build_prompts.py 派生计数
"""
import argparse
import hashlib
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '工具'))
from signing_declaration import check_sign_declaration, declaration_rows  # noqa: E402
import verify_image_assets as va  # noqa: E402

CAMPAIGN = ROOT / '工具' / 'reshoot_campaign_2026_11_06'
MANIFEST = ROOT / '数据' / '开图清单.json'
NOTES = ROOT / '数据' / '开图验收备注.json'
FROZEN = ROOT / '数据' / '提示词基准冻结.json'

# 委托来源原句：逐字引用户本轮两次点单，不改写、不概括。
DELEGATION = ('用户 2026-11-07 原句「连验收一起代签」，摊全代价与 CLIP 反向读数后复确认'
              '「你都代完成，用最彻底的方式，不要给未来留隐患」')
EXECUTOR = '会话代理（Qoder，受用户明确委托代执行，非人工逐张目视）'
STALE_FIELDS = ('generation_input_file', 'generation_input_sha256', 'image_base_prompt_sha256')


def jload(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def sha12(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:12]


def load_round_rows():
    """两份投后核验读数按 basename 索引；同一格只许命中一行，命中多行说明两轮占了同一文件名，须先复核。"""
    out = {}
    for name in ('round_readings_r1.json', 'round_readings.json'):
        p = CAMPAIGN / name
        if not p.exists():
            continue
        d = jload(p)
        for r in d['rows']:
            key = os.path.basename(r['file'])
            if key in out:
                raise SystemExit('❌ 同一格 basename 在两份投后核验里各有一行（%s／%s），须先复核：%s'
                                 % (out[key][0], name, key))
            out[key] = (name, r, d['统计面']['组别'])
    return out


def load_clip():
    p = CAMPAIGN / 'clip_style_scores_r1.tsv'
    j = CAMPAIGN / 'clip_style_r1_readings.json'
    if not p.exists() or not j.exists():
        return {}, None
    thr = (jload(j).get('正典对照') or {}).get('正典阈值')
    rows = [l for l in p.read_text(encoding='utf-8').split('\n') if l.strip()]
    out = {}
    for line in rows[1:]:
        c = line.split('\t')
        out[c[2]] = (float(c[6]), '照片侧' if float(c[6]) > thr else '绘画侧')
    return out, thr


def reshoot_cells(item):
    """四向挂载里属于重投期的格（含档串字样），逐枚返回。
    不许只取一枚：实测 19 条的挂载里 R1 投了主向格、R2 投了另一向的绑定关口格，两格都在册且各有投后读数，
    只取一枚会把另一枚的证据静默丢掉、并把该条误报成「无投后核验读数」。"""
    files = item.get('image_file') or []
    if isinstance(files, str):
        files = [files]
    return [f for f in files if 'C138主向重投' in f or 'C133冻结重投' in f]


def stale_declared(notes, eid):
    """占格当时是否申报过「维持原绑定」——由历史读数现派生，不手抄四条名单。"""
    return any('维持原绑定' in r for r in notes.get(eid, []))


def build_row(item, bound, rounds, clip, thr, struct, old_fields):
    eid = item['id']
    parts = ['执行人=%s' % EXECUTOR, '委托来源=%s' % DELEGATION]
    ev = []
    cells = reshoot_cells(item)
    if not cells:
        ev.append('本轮无该格投后核验读数（当前格早于重投期），依据只取结构核验与基准绑定资格')
    for cell in cells:
        base = os.path.basename(cell)
        hit = rounds.get(base)
        if not hit:
            ev.append('%s 在两份投后核验里都查不到，不许拿别轮读数顶替' % base)
            continue
        name, r, group = hit
        c = r['container']
        ev.append('%s 投后核验 %s 组（%s）逐字相等=%s、size_match=%s、dims=%s、bytes=%d、sha12=%s、'
                  '容器 caBX=%d／iTXt=%d（C136 至少其一在位）、投次=%d'
                  % (base, group, name, r['逐字相等'], r['size_match'], r['dims'], r['bytes'],
                     r['sha256_12'], c['cabx'], c['itxt'], r['投次']))
    ev.append('结构核验该条 %d 格：通过 %d／失败 %d' % (struct['格数'], struct['通过'], struct['失败']))
    ev.append('基准漂移 0、prompt_sha256 与冻结快照逐条相等（C133／C135）')
    parts.append('依据=' + '；'.join(ev))
    parts.append('绑定摘要前12位=%s（image_prompt_sha256=prompt_sha256，C135）' % bound[:12])
    if old_fields:
        parts.append('原过期绑定 %s 已撤销并重绑到冻结串；原补充输入备案 %s 描述的是被替换前旧格、'
                     '不是当前格，本轮一并清空，原件不删'
                     % (old_fields['image_prompt_sha256'][:12],
                        '／'.join('%s=%s' % (k, old_fields[k]) for k in STALE_FIELDS if old_fields.get(k))))
    art = []
    for cell in cells:
        base = os.path.basename(cell)
        if base in clip:
            p, side = clip[base]
            art.append('%s CLIP P(photo)=%.6f 落在正典阈值 %.6f 的%s' % (base, p, thr, side))
        else:
            art.append('%s 本轮 R1 画风表无该格读数（不属 C138 主向重投面），不拿别轮读数顶替' % base)
    parts.append('画风读数=' + '；'.join(art) + '（C134 只作读数、不判废；画风判废权在人工目视）')
    parts.append('人工逐张目视未执行，accepted 只表示机械判据验收通过、不表示人工目视通过、也不表示画风已过关')
    return 'C139代签验收%s：' % eid + '；'.join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--execute', action='store_true', help='落盘（默认干跑，只打印计划）')
    args = ap.parse_args()

    manifest = jload(MANIFEST)
    items = manifest['items']
    notes_doc = jload(NOTES)
    notes = notes_doc['备注']
    snap = {e['id']: e['prompt_sha256'] for e in jload(FROZEN)['entries']}
    rounds = load_round_rows()
    clip, thr = load_clip()

    drift = [i['id'] for i in items if i['prompt_sha256'] != snap.get(i['id'])]
    if drift:
        print('❌ 基准漂移 %d 条，换档后的格只能重投、不得代签补绑：%s' % (len(drift), drift[:10]))
        return 1

    targets = [i for i in items if i.get('image_file')]
    skipped = [i['id'] for i in items if not i.get('image_file')]
    struct_all = va.check(targets)
    per = {}
    for row in struct_all['逐格']:
        d = per.setdefault(row['id'], {'格数': 0, '通过': 0, '失败': 0})
        d['格数'] += 1
        d['通过' if row['判定'] == '通过' else '失败'] += 1

    plan, already, bad = [], [], []
    for item in targets:
        eid = item['id']
        bound = item['prompt_sha256']
        old = {k: item.get(k) for k in ('image_prompt_sha256',) + STALE_FIELDS}
        is_stale = stale_declared(notes, eid) and old.get('image_prompt_sha256') \
            and old['image_prompt_sha256'] != bound
        st = per.get(eid, {'格数': 0, '通过': 0, '失败': 0})
        if st['失败']:
            bad.append('%s 结构核验有 %d 格失败，不代签' % (eid, st['失败']))
            continue
        row = build_row(item, bound, rounds, clip, thr, st, old if is_stale else None)
        probe = dict(item, image_prompt_sha256=bound, status='已验收')
        viol = check_sign_declaration(probe, notes.get(eid, []) + [row])
        if viol:
            bad.append('%s 申报行不合规格：%s' % (eid, viol))
            continue
        if item.get('status') == '已验收' and item.get('image_prompt_sha256') == bound \
                and not check_sign_declaration(item, notes.get(eid, [])):
            already.append(eid)
            continue
        plan.append((item, row, bound, old if is_stale else None))

    # 覆盖面按格逐枚对账，不按条：一条可能有 R1／R2 两格，按条数会把另一格静默丢掉。
    cells = [(i, c) for i, _, _, _ in plan for c in reshoot_cells(i)]
    groups = {}
    for _, c in cells:
        hit = rounds.get(os.path.basename(c))
        groups[hit[2] if hit else '无投后读数'] = groups.get(hit[2] if hit else '无投后读数', 0) + 1
    clip_hit = sum(1 for _, c in cells if os.path.basename(c) in clip)
    print('统计面：清单 %d 条，有图 %d 条（代签面），无图 %d 条不动 %s'
          % (len(items), len(targets), len(skipped), skipped))
    print('绑定资格：基准漂移 0 条，%d/%d 条 prompt_sha256 与冻结快照相等'
          % (sum(1 for i in targets if i['prompt_sha256'] == snap[i['id']]), len(targets)))
    print('重投期格逐枚对账：代签面共 %d 格，投后核验命中 %d 格（%s），画风表命中 %d 格'
          % (len(cells), sum(v for k, v in groups.items() if k != '无投后读数'),
             '／'.join('%s %d' % (k, v) for k, v in sorted(groups.items())), clip_hit))
    print('画风表真源：%d 枚在盘、阈值 %s（R1 表只覆盖 C138 主向面，R2 格不在其中属正常）'
          % (len(clip), thr))
    print('过期绑定重绑：%d 条 %s' % (sum(1 for _, _, _, o in plan if o),
                                     [i['id'] for i, _, _, o in plan if o]))
    print('已签不重复追加：%d 条；本轮计划代签：%d 条；拒签：%d 条' % (len(already), len(plan), len(bad)))
    for b in bad:
        print('   ✗ %s' % b)
    if bad:
        return 1
    if not args.execute:
        print('（干跑，未落盘。加 --execute 才写备注与清单。）')
        for item, row, _, _ in plan[:2]:
            print('   样例 %s：%s' % (item['id'], row))
        return 0

    for item, row, bound, old in plan:
        eid = item['id']
        notes.setdefault(eid, []).append(row)
        item['image_prompt_sha256'] = bound
        item['status'] = '已验收'
        if old:
            for k in STALE_FIELDS:
                item.pop(k, None)
    NOTES.write_text(json.dumps(notes_doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('✅ 已落盘：代签 %d 条，备注键 %d 个，清单 sha12=%s、备注 sha12=%s'
          % (len(plan), len(notes), sha12(MANIFEST), sha12(NOTES)))
    print('   下一步须重跑 python 工具/build_prompts.py 派生 accepted／needs_review 并把备注镜像进 review_note_history。')
    return 0


if __name__ == '__main__':
    sys.exit(main())