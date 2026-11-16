# -*- coding: utf-8 -*-
"""R4 双发登记（零付费）：把「同一条发了 N 次、串面逐字相等」这一类形态事实写进证据台账。

为什么走这个通道而不是改主台账：`build_send_bodies_r4.py` 生成 `send_bodies_r4.json` 时把 `投次` 写死成 1，
直接改主台账必被重导覆盖；`verify_round.py` 的 `merge_bodies` 只从 `send_bodies_r4_evidence.json` 取
（投次／作废发起／作废删除／点单／复投）五键，所以形态类事实一律登记在这里。

口径（D13／L079 先例）：`作废发起` 只数串面不符的发次。N 发 prompt 逐字相等时记 0，
那次形态／传输作废由「投次=N」＋「冻结带内落盘恒 1 枚」共同承载；往 `作废发起` 填数会让
`drifted != known_drift` 当场判红（陷阱负测 test_r4_h 钉的就是这一处）。

括注订正（2026-11-16）：`--transcript` 原只接一份源。R086／R102／S06 这一类是 11-13 被额度挡下
（HTTP 403／code 112，零产物）＋11-16 同串真投，两次发起分属两波分片的 transcript——单份源会数出
投次=1、把那次付费发起从调用面上抹掉，正是「放行数是调用次数不是条目数」要防的形态，故改为 nargs='+'。
"""
import argparse
import hashlib
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(HERE, 'send_bodies_r4.json')
EV = os.path.join(HERE, 'send_bodies_r4_evidence.json')


def read(p):
    with io.open(p, encoding='utf-8', newline='') as fh:
        return fh.read()


def imagegen_uses(transcript, send_name):
    """发起面只认 tool_use 的 name 字段，结构键匹配会造出幽灵调用。"""
    out = []
    with io.open(transcript, encoding='utf-8', errors='replace') as fh:
        for no, line in enumerate(fh, 1):
            if '"ImageGen"' not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            content = (rec.get('message') or {}).get('content')
            if not isinstance(content, list):
                continue
            for blk in content:
                if (isinstance(blk, dict) and blk.get('type') == 'tool_use'
                        and blk.get('name') == 'ImageGen'):
                    inp = blk.get('input') or {}
                    if inp.get('name') == send_name:
                        out.append((no, inp, rec.get('timestamp')))
    return out


def _group(uses):
    """按源文件归并取证行号，保持 --transcript 的给定顺序输出，供「并轨来源」逐份点名。"""
    order, acc = [], {}
    for src, no, _inp, _ts in uses:
        if src not in acc:
            acc[src] = []
            order.append(src)
        acc[src].append(no)
    return [(s, acc[s]) for s in order]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('id')
    ap.add_argument('--transcript', required=True, nargs='+',
                    help='发起面源，可给多份：同一发名分属两波投放时（11-13 被额度挡下、11-16 同串真投）'
                         '两次发起落在不同 transcript，单份源会数出投次=1 而漏掉那次零产物发起')
    ap.add_argument('--reason', required=True, help='逐字写清每一次发起的形态与取证行号')
    ap.add_argument('--decl', required=True, help='逐字引用户放行原话')
    ap.add_argument('--landing', required=True, help='冻结带内唯一那枚的文件名')
    ap.add_argument('--source-note', default='')
    a = ap.parse_args(argv)

    old = read(EV)
    assert '\r' not in old and old.endswith('\n')
    ev = json.loads(old)
    assert a.id not in ev, '%s 已在证据台账里，勿重复登记（要改走人工，脚本不覆盖）' % a.id

    ref = json.loads(read(MAIN))[a.id]
    send_name = ref['send_name']
    uses = []
    for src in a.transcript:
        for no, inp, ts in imagegen_uses(src, send_name):
            uses.append((src, no, inp, ts))
    assert uses, ('%s 在这些 transcript 里没有任何 ImageGen 发起（发名 %s）——先把源找对，不许凭报告填投次'
                  % (a.id, send_name))
    shas = {}
    for src, no, inp, ts in uses:
        pr = inp.get('prompt') or ''
        got = hashlib.sha256(pr.encode('utf-8')).hexdigest()
        assert got == ref['send_sha256'], ('%s 在 %s 第 %d 行发起的 prompt 与台账串逐字不等（%s≠%s）：'
                                           '串面不符属另一类，须登记作废发起与作废删除，不走本通道'
                                           % (a.id, os.path.basename(src), no, got[:12],
                                              ref['send_sha256'][:12]))
        shas.setdefault(got[:12], []).append(no)
    assert len(shas) == 1, ('%s 的 %d 发串面分 %d 档，逐字相等的前提不成立' % (a.id, len(uses), len(shas)))
    landed = os.path.join(HERE, '..', '..', 'vibe_images')
    assert os.path.isfile(os.path.abspath(os.path.join(landed, a.landing))), \
        ('冻结带内那枚 %s 不在盘：登记前先证明产物在，否则闸门会判「零产物」') % a.landing

    ev[a.id] = {
        'body': ref['body'],
        'send_name': send_name,
        '投次': len(uses),
        '作废发起': 0,
        '留盘枚': [a.landing + '｜冻结带内唯一枚（%s）' % a.source_note],
        '复投': a.reason,
        '并轨来源': ('R4 同串多发证据（N=%d 发 prompt 逐字等于台账 body %s／%d 字符，'
                     '非逐字发起 0；发起取证 %s）'
                     % (len(uses), list(shas)[0], len(ref['body']),
                        '＋'.join('%s 第 %s 行' % (os.path.basename(s), '／'.join(str(n) for n in ns))
                                  for s, ns in _group(uses)))),
        '点单': a.decl,
    }
    out = json.dumps(ev, ensure_ascii=False, indent=1) + '\n'
    assert out.count('\u2026') == old.count('\u2026'), (out.count('\u2026'), old.count('\u2026'))
    with io.open(EV, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(out)
    n = read(EV)
    print('%s 登记完成：投次 %d／作废发起 0｜%d → %d 字节｜sha %s → %s｜键数 %d｜CRLF %d｜U+2026 %d → %d'
          % (a.id, len(uses), len(old.encode('utf-8')), len(n.encode('utf-8')),
             hashlib.sha256(old.encode('utf-8')).hexdigest()[:12],
             hashlib.sha256(n.encode('utf-8')).hexdigest()[:12],
             len(json.loads(n)), n.count('\r'), old.count('\u2026'), n.count('\u2026')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
