# -*- coding: utf-8 -*-
"""「3 全改」：把 20 个城市片区的取景段从「同一机位模板」改成按片区轮换的三类视点。

为什么改：六条取景指令全是「外缘中轴公共观景屋面＋离地55米＋35毫米」，只有坐标与朝向不同，
D06（朝北）与 D10（朝144°）朝向差 144° 仍出同构图（见 数据/片区重复构图复验.json）。

改什么：只改视点类型、机位高度与同段的近景描述；坐标、朝向、焦距一律不动——
verify_framing 按朝向与焦距算水平视锥、逐条核本片区地标是否在画内，动这三样会把地标挤出画外。
中景与远景的点名对象按原文抽出来原样保留（C123「背景只许画逐一点名对象」不受影响）。

三类视点按 D 序号轮换：
  i%3==1 → 外缘中轴公共观景屋面，离地 55/72/96 米（按 i//3 轮换）
  i%3==2 → 片区内主街人行道，离地 1.7 米
  i%3==0 → 片区跨层退台平台，离地 24/32/48 米
改的是 分卷/原稿 两份原稿与 数据/AI地点知识库.json 两处真源，逐字一致。

跑法：python -X utf8 工具/rediversify_district_framing.py [--check]
  --check 只打印将要改的 20 条的新旧摘要，不写盘。
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
MS = [os.path.join(ROOT, '分卷', '原稿', '02-D01-D10.md'),
      os.path.join(ROOT, '分卷', '原稿', '02-D11-D20.md')]
KB = os.path.join(ROOT, '数据', 'AI地点知识库.json')

HEAD = '**图像与视频取景**：'
COORD = re.compile(r'[\(\（]\s*(-?\d+(?:\.\d+)?)\s*[，,]\s*(-?\d+(?:\.\d+)?)\s*[\)\）]\s*千米')
FACING = re.compile(r'35毫米朝([^\d°]{1,3}°?|\d+°)拍摄')
MID = re.compile(r'中景为(.+?)，远景为(.+?)。')
SUN = re.compile(r'(255°.*)$', re.S)
HEIGHT = {'外缘中轴公共观景屋面': [55, 72, 96], '片区跨层退台平台': [24, 32, 48]}

TEMPLATE = {
    'A': ('建议在本片区外缘中轴公共观景屋面(%s,%s)千米，机位离地%d米，35毫米朝%s拍摄。'
          '近景为屋面栏板、屋顶设备带与相邻屋脊线，中景为%s，远景为%s。'
          '用8秒沿屋面缓慢横移，保留街面脚步与楼顶设备声，镜头不越过公共栏板。'),
    'B': ('建议在本片区主街人行道(%s,%s)千米，机位离地1.7米，35毫米朝%s拍摄。'
          '近景为近侧店招下沿、遮雨棚与行道树，中景为%s，远景为%s。'
          '用8秒沿人行道缓慢前移，保留交谈、脚步与车流声，镜头不越过人行道护栏。'),
    'C': ('建议在本片区跨层退台平台(%s,%s)千米，机位离地%d米，35毫米朝%s拍摄。'
          '近景为退台绿化、栏板与相邻屋面，中景为%s，远景为%s。'
          '用8秒沿退台缓慢横移，保留屋顶设备声与街面人声，镜头不越过退台护栏。'),
}


# 被点名同构的三对各自拆成「街面人视 vs 高处」，其余 14 条按序号轮换：
# 光靠 A(55m) 与 C(48m) 差 7 米拆不开构图，必须让每对里至少一条落到人视。
PAIR_OVERRIDE = {
    'D06': ('B', None), 'D10': ('A', 96),
    'D11': ('B', None), 'D15': ('C', 72),
    'D12': ('B', None), 'D20': ('A', 128),
}


def archetype(i, eid=None):
    if eid in PAIR_OVERRIDE:
        return PAIR_OVERRIDE[eid]
    k = i % 3
    if k == 1:
        return 'A', HEIGHT['外缘中轴公共观景屋面'][(i // 3) % 3]
    if k == 2:
        return 'B', None
    return 'C', HEIGHT['片区跨层退台平台'][(i // 3) % 3]


def rewrite(text, i, eid=None):
    """把一条取景段改写成轮换后的视点；解析不出必需元素就抛，绝不猜。"""
    m_coord = COORD.search(text)
    m_face = FACING.search(text)
    m_mid = MID.search(text)
    m_sun = SUN.search(text)
    assert m_coord and m_face and m_mid and m_sun, ('取景段缺元素，停手人工复核', text[:80])
    kind, h = archetype(i, eid)
    args = [m_coord.group(1), m_coord.group(2)]
    if h is not None:
        args.append(h)
    args += [m_face.group(1), m_mid.group(1), m_mid.group(2)]
    return (TEMPLATE[kind] % tuple(args)) + m_sun.group(1)


def sha12(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:12]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--emit-kb', action='store_true', help='把改写结果写进 数据/AI地点知识库.json')
    args = ap.parse_args(argv[1:])
    changed = []
    for path in MS:
        with io.open(path, encoding='utf-8', newline='') as fp:
            raw = fp.read()
        nl = '\r\n' if '\r\n' in raw else '\n'
        parts = raw.split(HEAD)
        out = [parts[0]]
        for chunk in parts[1:]:
            eid = None
            # 抬头在 chunk 之前：用已拼好的尾部找本段所属 ID
            tail = out[-1]
            m_id = list(re.finditer(r'^## (D\d{2}) ', tail, re.M))
            if m_id:
                eid = m_id[-1].group(1)
            end = chunk.find(nl + '**')
            body = chunk[:end]
            rest = chunk[end:]
            if eid is not None and 1 <= int(eid[1:]) <= 20:
                i = int(eid[1:])
                new = rewrite(body, i, eid)
                changed.append((eid, sha12(body), sha12(new), len(body), len(new)))
                body = new
            out.append(body + rest)
        new_raw = HEAD.join(out)
        if not args.check:
            with io.open(path, 'w', encoding='utf-8', newline='') as fp:
                fp.write(new_raw)
    print('20 条取景段改写%s：' % ('（干跑）' if args.check else ''))
    for eid, a, b, la, lb in changed:
        print('  %s  %s → %s  (%d→%d 字符)' % (eid, a, b, la, lb))
    if args.emit_kb:
        with io.open(KB, encoding='utf-8') as fp:
            kv = json.loads(fp.read())
        by = {r['id']: r for r in kv}
        n = 0
        for eid, _a, _b, _la, _lb in changed:
            sec = by[eid]['sections']
            cur = sec['图像与视频取景']
            sec['图像与视频取景'] = rewrite(cur, int(eid[1:]), eid)
            n += 1
        with io.open(KB, 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(json.dumps(kv, ensure_ascii=False, indent=2) + '\n')
        print('知识库已同步 %d 条' % n)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
