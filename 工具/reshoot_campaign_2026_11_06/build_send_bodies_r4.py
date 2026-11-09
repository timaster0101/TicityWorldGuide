# -*- coding: utf-8 -*-
"""R4 主链放量（画风目视判废的 310 条）·实际送入串台账：现串正文逐字 + 一句「图1 只借媒介」+ 画风母图。

成员面现算，不手抄：真源 `数据/开图验收备注.json` 里带「画风目视」的末条汇总行，
行内含「｜达标」的是达标白名单（本轮实测 2 条 F012／L095），参与目视的 ID 减白名单就是本轮 310 条。
串面按 工具/build_prompts.py 的既有口径逐字截「## 提示词正文」之后正文，
并两头对拍摘要（txt 去元数据摘要 == 清单 prompt_sha256 == 冻结快照 prompt_sha256）——
任一头分叉就停手，这轮的钱不花在没对齐的串上。

占格口径与 R1 不同一处：本轮不跑 pick_primary_cell.locate()。上一轮 264 枚主向格回填后，
清单里那条「主向指针」已经被替换成带时间戳的新格，locate() 现读返回 0 行，
沿用 R1 支路的「四向≥4＋主向指针」断言会当场判红且判得没错——所以本轮的替换对象按档串现读：
该条 image_file 里恰有一枚文件名带 C138主向重投-v01 的格，替换的就是它。
实测 310 条里 291 条只挂 1 枚带时间戳格、19 条同时挂一枚 C133冻结重投（R2 绑定关口组的格，本轮不动），
逐条断言「主向档串格恰 1 枚」，多于或少于都停。

母图臂与前导声明的逐字、母图池与分配都在 工具/r4_style_ref.py，卡面侧共用同一份，不在此复制。
"""
import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
WORKSPACE = os.path.abspath(os.path.join(ROOT, '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, '工具'))
sys.path.insert(0, HERE)   # pick_primary_cell 与 build_send_bodies 是同目录兄弟模块
import r4_style_ref as REF  # noqa: E402
from build_send_bodies import body_of, txt_sha  # noqa: E402

OUT = os.path.join(HERE, 'send_bodies_r4.json')
NOTE = os.path.join(HERE, 'send_bodies_r4_note.json')
PASTE_DIR = os.path.join(WORKSPACE, '_scratch_cardref', 'reshoot_r4', 'paste')
SUFFIX = 'C154母图重投-v01'
PRIMARY_TOKEN = 'C138主向重投-v01'
RELEASE_QUOTE = ("用户 2026-11-09 逐字「卡面 85 枚＋R1 310 枚判废后的重投（花钱调用，方向已锁死"
                 "「无框主图＋不烤文案」） 去做」")
TS = re.compile(r'_(1\d{12})_')


def reviewed_ids():
    """现读目视真源，返回 (参与目视的 ID, 达标 ID, 本轮待重投 ID)。"""
    notes = json.load(io.open(os.path.join(ROOT, '数据', '开图验收备注.json'), encoding='utf-8'))['备注']
    reviewed = sorted(i for i, v in notes.items() if any('画风目视' in s for s in v))
    passed = []
    for i in reviewed:
        tail = [s for s in notes[i] if '画风目视' in s][-1]
        hit = re.search(r'｜(达标|判废)', tail)
        if hit is None:
            raise SystemExit('%s 的目视汇总行缺「｜达标／｜判废」标记，成员面取不出来' % i)
        if hit.group(1) == '达标':
            passed.append(i)
    return reviewed, passed, [i for i in reviewed if i not in passed]


def primary_cell(item):
    """该条本轮要替换的那一格＝档串恰为 C138主向重投-v01 的仓内格，必须恰 1 枚。"""
    cells = list(item.get('image_file') or [])
    hit = [c for c in cells if PRIMARY_TOKEN in os.path.basename(str(c))
           and not str(c).replace('\\', '/').startswith('backup/')]
    if len(hit) != 1:
        raise SystemExit('%s 的 %s 格实测 %d 枚（应恰 1 枚）：%s'
                         % (item['id'], PRIMARY_TOKEN, len(hit), [os.path.basename(str(c)) for c in hit]))
    return hit[0], [c for c in cells if c != hit[0]]


def main():
    reviewed, passed, todo = reviewed_ids()
    man = json.load(io.open(os.path.join(ROOT, '数据', '开图清单.json'), encoding='utf-8'))
    snap = json.load(io.open(os.path.join(ROOT, '数据', '提示词基准冻结.json'), encoding='utf-8'))
    base = {e['id']: e['prompt_sha256'] for e in snap['entries']}
    by_id = {it['id']: it for it in man['items']}
    land = REF.check_pool(REF.LANDSCAPE, '主链横向母图')
    port = REF.check_pool(REF.PORTRAIT, '主链竖向母图')
    out, sizes, reuse = {}, {}, {}
    seq = {'port': 0, 'land': 0}   # 母图轮转位序：按方向各自从 0 起，成员面按 id 升序遍历
    for eid in todo:
        item = by_id.get(eid)
        assert item, (eid, '清单里没有这条 ID')
        name, src, body = body_of(ROOT, eid)
        assert body.startswith('【画风锚点】'), eid
        sha = txt_sha(src)
        assert sha == item['prompt_sha256'], (eid, 'txt 去元数据摘要 ≠ 清单 prompt_sha256，真源与清单已分叉')
        assert sha == base.get(eid), (eid, '清单 prompt_sha256 ≠ 冻结快照：基准在冻结后变过，先跑 verify_prompt_baseline')
        cell, others = primary_cell(item)
        size = item['size']
        assert size in ('1024x1536', '1280x1024', '1536x1024', '1792x1024'), (eid, size)
        kind = 'port' if size == '1024x1536' else 'land'
        pool = port if kind == 'port' else land
        ref_rel, ref_dims = REF.assign(pool, seq[kind], size)
        seq[kind] += 1
        send = REF.send_body(body)
        out[eid] = {
            'group': 'R4_画风母图重投',
            'file': '数据/开图提示词/' + name,
            'send_name': '%s-%s' % (name[:-4], SUFFIX),
            'size': size,
            'chars': len(send),
            'body_chars': len(body),
            'sha256': sha,
            'send_sha256': hashlib.sha256(send.encode('utf-8')).hexdigest(),
            'replaced_cell': cell,
            'untouched_cells': others,
            'status_before': item['status'],
            'body': send,
            'ref_image': ref_rel,
            'ref_dims': ref_dims,
            '占格口径': '替换 %s 那一格（本轮目视判废的主向枚）' % PRIMARY_TOKEN,
            '投次': 1,
        }
        sizes[size] = sizes.get(size, 0) + 1
        reuse[ref_rel] = reuse.get(ref_rel, 0) + 1
        if os.path.basename(str(cell)).startswith(eid) and ref_rel.endswith(os.path.basename(str(cell))):
            raise SystemExit('%s 的母图就是被替换的那枚判废图，池子选错' % eid)

    # paste 文件写的是「逐字节即送入串」：不带结尾换行，落盘后立刻按台账 send_sha256 自证。
    # 探针那两张的拼接形态差一个换行（99+1+6586 与 99+2+5998），代价就是逐字回绑会判红——
    # 所以把「文件字节 sha == send_sha256」写死在这里，投放侧只准读文件、不准手抄。
    os.makedirs(PASTE_DIR, exist_ok=True)
    paste_ok = 0
    for eid, rec in out.items():
        p = os.path.join(PASTE_DIR, '%s.txt' % eid)
        with io.open(p, 'w', encoding='utf-8', newline='') as fp:
            fp.write(rec['body'])
        got = hashlib.sha256(open(p, 'rb').read()).hexdigest()
        assert got == rec['send_sha256'], (eid, got, rec['send_sha256'])
        paste_ok += 1
    assert paste_ok == len(out), (paste_ok, len(out))
    # 两份文件而不是合成一份：verify_round 的 merge_bodies 把送入串台账当「{ID: 记录}」扁平字典读，
    # 顶层混进任何非记录键（本轮的口径说明就是）会让它拿字符串去取 ['send_name'] 当场崩。
    # 所以台账面保持与 R1/R2/R3 逐字同构，轮次级说明另落 note 件。
    meta = {
        'declaration': ('R4 主链放量（画风目视判废 %d 条）实际送入串台账见 %s，本件是轮次级口径说明。'
                        '台账 body 字段＝ImageGen 真实送入的整串（前导声明一行 + 现串正文逐字），'
                        'verify_round 的逐字回绑比的就是这一串；sha256 字段＝冻结基准里该条的 prompt_sha256，'
                        '按 C135 写进绑定的是它，不是 send_sha256。' % (len(out), os.path.basename(OUT))),
        '臂': '现串正文逐字＋跨题材画风母图（图生图，前导只借媒介不借构图）',
        '放行原话': RELEASE_QUOTE,
        '前导声明': REF.PREFIX_LINE,
        '成员面': {'目视参与': len(reviewed), '达标白名单': sorted(passed), '本轮待重投': len(todo)},
        '母图池': {'横向': land, '竖向': port},
        '母图复用': {'最高复用': max(reuse.values()), '池内枚数': len(reuse),
                     '明细': dict(sorted(reuse.items(), key=lambda kv: -kv[1]))},
        '画幅分布': sizes,
        '统计面': ('成员面＝数据/开图验收备注.json 末条「画风目视」汇总行现算；串面＝数据/开图提示词/<ID>-*.txt '
                   '逐字截正文段；摘要两头对拍清单与 数据/提示词基准冻结.json；占格＝image_file 里档串 '
                   '%s 恰 1 枚的仓内格。达标白名单只作母图、不重投。' % PRIMARY_TOKEN),
        '条数': len(out),
    }
    with io.open(NOTE, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(meta, fp, ensure_ascii=False, indent=1)
        fp.write('\n')
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1, sort_keys=True)
        fp.write('\n')
    print('R4 主链台账 %d 条｜目视参与 %d／达标 %d｜档串 %s｜frozen_at %s'
          % (len(out), len(reviewed), len(passed), SUFFIX, snap['frozen_at']))
    print('  画幅分布 %s' % sizes)
    print('  母图池 %d 枚／最高复用 %d 次' % (len(reuse), max(reuse.values())))
    print('  送入串字数区间 %d—%d（正文 %d—%d）'
          % (min(v['chars'] for v in out.values()), max(v['chars'] for v in out.values()),
             min(v['body_chars'] for v in out.values()), max(v['body_chars'] for v in out.values())))
    print('  paste 落盘 %d 份 → %s' % (len(out), PASTE_DIR.replace('\\', '/')))
    print('  台账 %s %d 字节' % (OUT.replace('\\', '/'), os.path.getsize(OUT)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
