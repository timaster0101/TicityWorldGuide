# -*- coding: utf-8 -*-
"""第9批 g 轮（9 条待开图第六投）里人工读数无判废项的条目：把读数打进备注，并把本轮图占上格。

口径五条，写在备注里而不是只写在脚本注释里：
1. 只回填人工读数里没有判废项的条目。判废条目（远景越权／触记号档）不占格、状态维持待开图，
   读数只留在批次目录，不进真源备注。名单由 readings_draft.json 正文里的判废句派生，脚本不手抄第二份。
   本轮实测：8 张读数全部带判废句（未点名独立远景塔入画、其中一栋带 L007 独占的斜削冠＋细针天线），
   干净项 0 条，因此清单与备注都应一字不动；跑出来只要 added≠0 就说明读数或派生口径出了问题。
2. 干净项若出现，一律按「此前无格、首占」处理，不写「替换」。
   若跑出「替换」分支即说明清单被别处动过，脚本直接停下让人复核。
3. image_prompt_sha256 一律留空。本轮实发串与真源逐字相等 8/8（第 9 次发起 L106 被服务端 403 code 112
   拒了、无产物，见 sent_binding.json 的「本轮未投 1」），
   但绑定摘要是人工验收动作，脚本不代签；状态仍派生为待复验，accepted 不签。
4. 批次串仍用 -v02 结尾：文件名后缀跟的是投放用的串档，本轮没换提示词模板（prompt_sha256 变更 0/312），
   后缀就不换，投次只写在读数抬头里。抬头有两个编号空间，必须分清楚：
   抬头写「C123新串…重投第五投」——序号从 C123 新串首投起算（v01 那轮首投、19 条那轮第二投、
   15 条那轮第三投、12 条那轮第四投、本轮第五投），与已落盘的 L080／L090／L092／L095 同一把尺往后接；
   移交清单与批次目录写「第六投」——那套序号把 2026-11-03 的 C118 放量首投也算进去，同一轮差一格。
5. 取本轮产物一律按探针落盘时间戳带（§32.6）：同一个 id 现在挂着 4 个同名 -C123新串-v02 文件，
   历史档不参与回填；带内多于 1 张就说明重复投放，测量脚本已经 assert 停过。

跑法：python -X utf8 工具/batch9g_2026_11_06/backfill_batch9g.py（工作目录＝设定集根）
"""
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(ROOT, '数据', '开图清单.json')
NOTES = os.path.join(ROOT, '数据', '开图验收备注.json')
MEASURE = os.path.join(HERE, 'batch9g_measure.json')
READINGS = os.path.join(HERE, 'readings_draft.json')

HARD = re.compile(r'判废')
SOFT = re.compile(r'不作判废|不判废|未判废|无判废|不作硬判|判废依据')

GUARD = '；image_prompt_sha256 留空、状态按清单派生为待复验，不代签验收'
HEAD = 'C123新串%s重投第五投（v02）人工目视读数（'


def is_clean(text):
    return not [s for s in re.split(r'(?<=[。；])', text) if HARD.search(s) and not SOFT.search(s)]


def main():
    with io.open(MEASURE, encoding='utf-8') as fp:
        rows = json.load(fp)
    mea = {r['id']: r for r in (rows['rows'] if isinstance(rows, dict) else rows)}
    with io.open(READINGS, encoding='utf-8') as fh:
        readings = json.load(fh)
    assert sorted(readings) == sorted(mea), (len(readings), len(mea))
    clean = sorted(k for k, v in readings.items() if is_clean(v))

    with io.open(NOTES, encoding='utf-8') as _fh:
        notes = json.load(_fh)
    with io.open(MANIFEST, encoding='utf-8') as _fp:
        man = json.load(_fp)
    items = {it['id']: it for it in man['items']}

    added = 0
    resynced = 0
    for k in clean:
        row = mea[k]
        # C136 订正：容器画像不再按出图通道分别成立（同是文本生图，本轮格 caBX=0／iTXt=1，
        # 母图 caBX=1／iTXt=0）。占格只要求「AIGC 标识容器至少其一在位」，具体画像由实测数据打印。
        cont = row['container']
        assert cont['cabx'] >= 1 or cont['itxt'] >= 1, (k, 'caBX 与 iTXt 都不在位，无 AIGC 标识不能占格')
        assert 'C123新串-v02' in row['file'], (k, row['file'])
        assert row['逐字相等'] is True, (k, '实发串与真源不相等')
        assert row['size_match'] is True, (k, '尺寸与清单不符')
        assert not items[k].get('image_prompt_sha256'), (k, '已绑定摘要，不该再打表')

        fmt = HEAD + ('vibe_images/%s，%s，%d字节，sha12=%s，%s；'
                      '本条此前无格，为首占%s）：%s')
        note = fmt % (k, row['file'], row['dims'], row['bytes'], row['sha256_12'],
                      'caBX=%d、iTXt=%d' % (cont['cabx'], cont['itxt']), GUARD, readings[k])
        assert '本条只记人工读数，不代签验收。' in note, (k, '读数缺人工声明')

        notes['备注'].setdefault(k, [])
        at = [i for i, prev in enumerate(notes['备注'][k]) if '重投第五投（v02）' in prev]
        if at:
            assert len(at) == 1, (k, at)
            assert note[:note.index('）：')] == notes['备注'][k][at[0]][:notes['备注'][k][at[0]].index('）：')], \
                (k, '抬头变了，说明占格口径动过，请人工复核')
            notes['备注'][k][at[0]] = note
            resynced += 1
            continue
        assert not items[k].get('image_file'), (k, '本轮应全部首占，出现旧格请人工复核')
        notes['备注'][k].append(note)

        items[k]['image_file'] = ['vibe_images/' + row['file']]
        items[k]['batch'] = '%s-%sC123新串-v02' % (items[k]['type'], k)
        added += 1

    if added or resynced:
        with io.open(NOTES, 'w', encoding='utf-8', newline='\n') as _handle:
            _handle.write(
                json.dumps(notes, ensure_ascii=False, indent=2) + '\n')
        with io.open(MANIFEST, 'w', encoding='utf-8', newline='\n') as _h101:
            _h101.write(
                json.dumps(man, ensure_ascii=False, indent=2) + '\n')
    else:
        print('本轮无回填，两份真源一律不落笔（不加尾换行、不重排缩进），文件 sha 与跑前一致')
    print('回填 %d 条（新增首占 %d 条、改口重打 %d 条）：%s'
          % (len(clean), added, resynced, ' '.join(clean)))
    print('判废不回填 %d 条：%s' % (len(readings) - len(clean),
                                    ' '.join(sorted(k for k in readings if k not in clean))))


if __name__ == '__main__':
    main()
