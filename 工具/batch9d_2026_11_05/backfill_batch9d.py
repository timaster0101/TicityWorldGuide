# -*- coding: utf-8 -*-
"""第9批 d 轮 19 条 C123新串-v02 重投里人工读数无判废项的条目：把读数打进备注，并把本轮图占上格。

口径四条，写在备注里而不是只写在脚本注释里：
1. 只回填人工读数里没有判废项的条目。判废条目（远景越权／触记号档）不占格、状态维持待开图。
   名单由 readings_draft.json 正文里的判废句派生，脚本不手抄第二份。
2. 本轮 19 条此前都没有格（image_file 为空、状态待开图），一律首占，不写「替换」。
   若跑出「替换」分支即说明清单被别处动过，脚本直接停下让人复核。
3. image_prompt_sha256 一律留空。本轮实发串与真源逐字相等（见 sent_binding.json），
   但绑定摘要是人工验收动作，脚本不代签；状态仍派生为待复验，accepted 不签。
4. 批次串用 -v02 结尾：v01 是 29 条那轮的 C123 新串首投，本轮是 19 条判废条目在同串下的第二投，
   两版并存时靠后缀分档，不覆盖上一轮的批次名。

跑法：python -X utf8 工具/batch9d_2026_11_05/backfill_batch9d.py（工作目录＝设定集根）
"""
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(ROOT, '数据', '开图清单.json')
NOTES = os.path.join(ROOT, '数据', '开图验收备注.json')
MEASURE = os.path.join(HERE, 'batch9d_measure.json')
READINGS = os.path.join(HERE, 'readings_draft.json')

HARD = re.compile(r'判废')
SOFT = re.compile(r'不作判废|未判废|无判废|不作硬判|判废依据')

GUARD = '；image_prompt_sha256 留空、状态按清单派生为待复验，不代签验收'
HEAD = 'C123新串%s重投第二投（v02）人工目视读数（'


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
        assert row['container']['cabx'] == 1, (k, 'caBX 不在位，不能占格')
        assert row['container']['itxt'] == 0, (k, 'PNG 侧不应出现 iTXt·TC260')
        assert 'C123新串-v02' in row['file'], (k, row['file'])
        assert row['逐字相等'] is True, (k, '实发串与真源不相等')
        assert row['size_match'] is True, (k, '尺寸与清单不符')
        assert not items[k].get('image_prompt_sha256'), (k, '已绑定摘要，不该再打表')

        fmt = HEAD + ('vibe_images/%s，%s，%d字节，sha12=%s，caBX=1、iTXt=0；'
                      '本条此前无格，为首占%s）：%s')
        note = fmt % (k, row['file'], row['dims'], row['bytes'], row['sha256_12'], GUARD, readings[k])
        assert '本条只记人工读数，不代签验收。' in note, (k, '读数缺人工声明')

        notes['备注'].setdefault(k, [])
        at = [i for i, prev in enumerate(notes['备注'][k]) if '重投第二投（v02）' in prev]
        if at:
            # 判读改口（本轮 L080 由判废改备注档）之后重跑：已打过的条目只换正文，不重复追加。
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

    with io.open(NOTES, 'w', encoding='utf-8', newline='\n') as _handle:
        _handle.write(
            json.dumps(notes, ensure_ascii=False, indent=2) + '\n')
    with io.open(MANIFEST, 'w', encoding='utf-8', newline='\n') as _h90:
        _h90.write(
            json.dumps(man, ensure_ascii=False, indent=2) + '\n')
    print('回填 %d 条（新增首占 %d 条、改口重打 %d 条）：%s'
          % (len(clean), added, resynced, ' '.join(clean)))
    print('判废不回填 %d 条：%s' % (len(readings) - len(clean),
                                    ' '.join(sorted(k for k in readings if k not in clean))))


if __name__ == '__main__':
    main()
