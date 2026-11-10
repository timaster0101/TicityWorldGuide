# -*- coding: utf-8 -*-
"""R4 放量投放前的机械前置：paste 逐字节复验＋分片名单落盘（卡面 85／主链 310）。

为什么要有这一步：花钱的调用一旦开跑，取串就只能靠子代理手上那一份文件。台账里 body 与 send_sha256
对不上、或 paste 被上一轮的形态（带结尾换行）留在那儿，都会在投后核验里以「逐字不相等」的面爆发，
而那时钱已经花完了。所以派单前把两份 paste 目录按台账 send_sha256 再复验一遍，并把名单切成 12 条一档。

分片粒度 12 条是 2026-11-09 实测出来的：同一 harness 下 22 条一档有 4/12 整单挂在通用错误上（非 403），
12 条一档才稳定；并发上限 6。名单按 id 升序切，补投时只按落盘差集重切，不重跑整份名单（同带重发）。

只读派生，不写任何真源：产物两份 shard_plan.json 落在仓外证据目录，与台账一一对应。
"""
import hashlib
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.abspath(os.path.join(ROOT, '..'))
CARD_LEDGER = os.path.join(ROOT, "数据", "卡面主图提示词3x4", "投放台账R4.json")
MAIN_LEDGER = os.path.join(ROOT, "工具", "reshoot_campaign_2026_11_06", "send_bodies_r4.json")
CARD_PASTE = os.path.join(WORKSPACE, "_scratch_cardref", "card3x4_r4", "paste")
MAIN_PASTE = os.path.join(WORKSPACE, "_scratch_cardref", "reshoot_r4", "paste")
SHARD_SIZE = 12


def check_paste(items, paste_dir, sha_field, why):
    """逐条复验 paste 字节 sha == 台账 send_sha256；缺文件或摘要不符即停，条数不符即停。"""
    names = set(os.listdir(paste_dir)) if os.path.isdir(paste_dir) else set()
    extra = sorted(n for n in names if n.endswith('.txt') and os.path.splitext(n)[0] not in items)
    bad, ok = [], 0
    for key, rec in items.items():
        p = os.path.join(paste_dir, key + '.txt')
        if not os.path.isfile(p):
            bad.append((key, 'paste 缺文件'))
            continue
        with open(p, 'rb') as fp:
            if hashlib.sha256(fp.read()).hexdigest() != rec[sha_field]:
                bad.append((key, 'paste 字节 sha ≠ 台账 %s' % sha_field))
                continue
        ok += 1
    assert not bad, '%s 的 paste 复验失败 %d 条（示例 %s）：先重跑台账生成脚本，不要带着错串去花钱' % (why, len(bad), bad[:5])
    assert ok == len(items), (ok, len(items))
    return ok, extra


def split(ids):
    ids = sorted(ids)
    return [ids[i:i + SHARD_SIZE] for i in range(0, len(ids), SHARD_SIZE)]


def write_shard_meta(doc, items):
    """每片一份「本片清单」：派单时只把它贴给子代理，3.2MB 的主链台账不进子代理上下文。

    条目里给的是绝对路径＋逐字节自证用的 send_sha256＋母图绝对路径与母图自身摘要——
    子代理手上有这四样就能机械执行，不需要也不允许它去解读串的内容。
    """
    d = os.path.join(os.path.dirname(doc['paste_dir']), 'shards')
    os.makedirs(d, exist_ok=True)
    for i, ids in enumerate(doc['分片'], 1):
        with io.open(os.path.join(d, 'shard_%02d.json' % i), 'w', encoding='utf-8', newline='\n') as fh:
            json.dump({'片号': i, '条数': len(ids),
                       '条': [items[e] for e in ids]}, fh, ensure_ascii=False, indent=1)
    return len(doc['分片'])


def main():
    with io.open(CARD_LEDGER, encoding='utf-8') as _fh:
        card = json.load(_fh)
    card_items = {it['id']: it for it in card['items']}
    assert len(card_items) == card['条数'] == 85, (len(card_items), card['条数'])
    with io.open(MAIN_LEDGER, encoding='utf-8') as _fp:
        mainb = json.load(_fp)
    assert len(mainb) == 310 and all(isinstance(v, dict) for v in mainb.values()), len(mainb)

    card_ok, card_extra = check_paste(card_items, CARD_PASTE, 'send_sha256', '卡面')
    main_ok, main_extra = check_paste(mainb, MAIN_PASTE, 'send_sha256', '主链')

    sizes = {}
    for rec in mainb.values():
        sizes[rec['size']] = sizes.get(rec['size'], 0) + 1

    def abs_in_repo(rel):
        return os.path.join(ROOT, rel.replace('/', os.sep)).replace('\\', '/')

    def file_sha(path):
        with open(path, 'rb') as _handle:
            return hashlib.sha256(_handle.read()).hexdigest()

    card_meta = {it['id']: {
        'id': it['id'], 'send_name': 'card3x4r4-' + it['id'], 'size': '768x1024',
        'paste': os.path.join(CARD_PASTE, it['id'] + '.txt').replace('\\', '/'),
        'send_sha256': it['send_sha256'], 'send_chars': it['send_chars'],
        'ref_image': abs_in_repo(it['ref_image']), 'ref_sha256': it['ref_sha256'],
        'landing': abs_in_repo(it['landing'])} for it in card['items']}
    main_meta = {eid: {
        'id': eid, 'send_name': rec['send_name'], 'size': rec['size'],
        'paste': os.path.join(MAIN_PASTE, eid + '.txt').replace('\\', '/'),
        'send_sha256': rec['send_sha256'], 'send_chars': rec['chars'],
        'ref_image': abs_in_repo(rec['ref_image'])} for eid, rec in mainb.items()}
    for rec in main_meta.values():
        rec['ref_sha256'] = file_sha(rec['ref_image'].replace('/', os.sep))

    plans = [
        {'轮次': 'card3x4_R4', '臂': '现串逐字＋跨卡型画风母图（图生图）', '档名前缀': 'card3x4r4',
         'size': '768x1024', 'paste_dir': CARD_PASTE.replace('\\', '/'),
         '台账': '数据/卡面主图提示词3x4/投放台账R4.json', '条数': len(card_items),
         '分片粒度': SHARD_SIZE, '片数': len(split(card_items)), '分片': split(card_items),
         '统计面': '成员面＝台账 items 的 85 键（真源 数据/卡面主图画风目视.json 判定「判废」）；'
                   'paste 逐字节复验通过 %d／目录内台账外文件 %d 个' % (card_ok, len(card_extra)),
         '_items': card_meta},
        {'轮次': 'R4_画风母图重投', '臂': '现串正文逐字＋跨题材画风母图（图生图）',
         '档串': 'C154母图重投-v01', 'paste_dir': MAIN_PASTE.replace('\\', '/'),
         '台账': '工具/reshoot_campaign_2026_11_06/send_bodies_r4.json', '条数': len(mainb),
         '分片粒度': SHARD_SIZE, '片数': len(split(mainb)), '分片': split(mainb),
         '画幅分布': sizes,
         '统计面': '成员面＝台账 310 键（真源 数据/开图验收备注.json 画风目视判废，达标白名单 2 条只作母图）；'
                   'paste 逐字节复验通过 %d／目录内台账外文件 %d 个' % (main_ok, len(main_extra)),
         '_items': main_meta},
    ]
    for doc in plans:
        items = doc.pop('_items')   # 不进 shard_plan.json：那份是口径件，逐条明细按片单独落盘
        dst = os.path.join(os.path.dirname(doc['paste_dir']), 'shard_plan.json')
        with io.open(dst, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
        n_meta = write_shard_meta(doc, items)
        print('%s：%d 条切成 %d 片（末片 %d 条）｜paste 复验 %d／%d｜分片单 %d 份｜%d 字节'
              % (dst.replace('\\', '/'), doc['条数'], doc['片数'], len(doc['分片'][-1]),
                 doc['条数'], doc['条数'], n_meta, os.path.getsize(dst)))
    total = sum(p['条数'] for p in plans)
    print('两轮合计 %d 条／%d 片（并发≤6，403 即停手并报未投 ID）'
          % (total, sum(p['片数'] for p in plans)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
