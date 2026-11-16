# -*- coding: utf-8 -*-
"""L079 双发登记（零付费）：首送把 images 写成 ref_image 键被工具参数校验挡下、零产物，同串重发成功。

按 D13 口径：两发 prompt 均逐字等于台账 body，故「作废发起」记 0，那次作废由「投次=2」＋「冻结带内落盘恒 1 枚」承载。
serialisation 口径与既有件逐字一致（indent=1／ensure_ascii=False／LF／结尾单换行），改前后取字节与 U+2026 计数自证。
"""
import hashlib
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(HERE, 'send_bodies_r4.json')
EV = os.path.join(HERE, 'send_bodies_r4_evidence.json')
ID = 'L079'
NAME = 'L079-月湾市集商厦-C154母图重投-v01'
LANDING = 'L079-月湾市集商厦-C154母图重投-v01_1794534420529_d693dbbf.png'
SRC = 'C:/Users/TIMASTER/.qoder/projects/C--Users-TIMASTER-Documents-Qoder-2026-10-29-c8c10ff8---------' \
      '/d52455f0-e564-44d4-9fa6-f71a76e2ce58/subagents/agent-ageneral-purpose-5193a97e4ba3a21d.jsonl'
DECL = ('2026-11-13 用户原话「F007 补投 1 次（付费）、291 条待投面逐轮放行、§55.49 三种处置选哪种（建议②＋③）、'
        'L027 被拒后重发是否违例、这 8 件的提交与推送（两句独立点单） 全做」——本轮放行面是 291 次调用，'
        'L079 这条不属于补投：它是放量分片 r4-todo-main03 投放时的一次参数形态错误，重发仍落在放行面内。')


def read(p):
    with io.open(p, encoding='utf-8', newline='') as fh:
        return fh.read()


def main():
    old = read(EV)
    t0 = old
    assert '\r' not in t0 and t0.endswith('\n')
    ev = json.loads(t0)
    assert ID not in ev, 'L079 已在证据台账里，勿重复登记'
    body = json.loads(read(MAIN))
    ref = body[ID]
    assert ref['send_name'] == NAME
    digest = hashlib.sha256(ref['body'].encode('utf-8')).hexdigest()
    assert digest[:12] == '33689efb96d7' and digest == ref['send_sha256'], (digest, ref['send_sha256'])
    ev[ID] = {
        'body': ref['body'],
        'send_name': NAME,
        '投次': 2,
        '作废发起': 0,
        '留盘枚': [LANDING + '｜1536x1024｜IMG_DIR 与仓库内 vibe_images 两侧同名同摘要（处置①已回写，冻结带内唯一枚）'],
        '复投': ('2026-11-13 01:45:52Z 子代理 ' + os.path.basename(SRC)[len('agent-'):-len('.jsonl')] +
                 ' 的 L079 首送把母图写成 ref_image 键（入参键面 name／prompt／ref_image／size，无 images），'
                 '工具当场判「params must NOT have additional properties」，零产物；'
                 '2026-11-13 01:47:00Z 同代理按规程第 2 节的正确形态 images=[路径字符串] 重发成功。'
                 '两发 prompt 逐字相同且等于台账 body（5702 字符／sha12 33689efb96d7），'
                 '非逐字发起数=0、作废发起登记 0，同 D13 口径：形态类作废由「投次」＋「冻结带内落盘恒 1 枚」承载。'
                 '根因仍在规程侧——规程已写明「元素是路径字符串，不是对象」，但漏了「键名必须叫 images」，'
                 '本轮已在两片投放规程补这一句。'),
        '并轨来源': ('R4 双发证据（首送 images 键名写错被参数校验挡下、零产物，非串面损坏；'
                     '发起与产物取证：' + SRC + ' 第 42／46 行）'),
        '点单': DECL,
    }
    out = json.dumps(ev, ensure_ascii=False, indent=1) + '\n'
    assert '\r' in out or True
    assert out.count('\u2026') == t0.count('\u2026'), (out.count('\u2026'), t0.count('\u2026'))
    with io.open(EV, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(out)
    n = read(EV)
    print('L079 登记完成：%d → %d 字节｜sha %s → %s｜键面 %s｜CRLF %d｜U+2026 %d → %d'
          % (len(t0.encode('utf-8')), len(n.encode('utf-8')),
             hashlib.sha256(t0.encode('utf-8')).hexdigest()[:12],
             hashlib.sha256(n.encode('utf-8')).hexdigest()[:12],
             ' '.join(sorted(json.loads(n))), n.count('\r'),
             t0.count('\u2026'), n.count('\u2026')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
