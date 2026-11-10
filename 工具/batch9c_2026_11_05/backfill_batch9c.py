# -*- coding: utf-8 -*-
"""第9批 31 条里人工读数无判废项的 12 条：把读数打进备注，并把本轮 C123 新串图占上格。

口径四条，写在备注里而不是只写在脚本注释里：
1. 只回填人工读数里没有判废项的条目。判废条目（远景越权／触锁定禁则）不占格、状态维持待开图。
2. 替换不是追加。R063／R066 的旧第5格出成于 B6 雨后批串，其后画风锚点换到 C122、
   背景授权又随 C123 收回，基准连换两档；并排占格会让「这格图存在」读成「两版都可用」。
   旧文件不删、旧备注不删，被替换的旧文件名写进本轮读数。
3. L063 等 10 条此前无格（image_file 为空、状态待开图），本轮是首占，不写「替换」。
4. image_prompt_sha256 一律留空。本轮 31 条实发串与真源逐字相等（见 sent_binding.json），
   但绑定摘要是人工验收动作，脚本不代签；状态仍派生为待复验，accepted 不签。

跑法：python -X utf8 工具/batch9c_2026_11_05/backfill_batch9c.py（工作目录＝设定集根）
"""
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(ROOT, '数据', '开图清单.json')
NOTES = os.path.join(ROOT, '数据', '开图验收备注.json')
MEASURE = os.path.join(HERE, 'batch9c_measure.json')
READINGS = os.path.join(HERE, 'readings_draft.json')

# 人工读数里带判废项的条目一律不回填。名单从读数正文的判废句派生，不在脚本里手抄第二份。
HARD = re.compile(r'判废')
SOFT = re.compile(r'不作判废|未判废|无判废|不作硬判|判废依据')


# 抬头必须自带的两枚口径要素：上一批（工具/reinject_2026_11_05）把它们写在人工结论正文里，
# 本轮改由抬头统一声明，免得只读抬头的人把「这格图存在」读成「这格已验收」。
GUARD = '；image_prompt_sha256 留空、状态按清单派生为待复验，不代签验收'


def header_tail(kind, old=None):
    """占格口径句：替换写清被替换的旧格文件名，首占写明此前无格；两种都接同一句绑定声明。"""
    if kind == '替换':
        return '；替换第5格 %s，旧文件与旧备注都不删%s' % (old, GUARD)
    return '；本条此前无格，为首占%s' % GUARD


def is_clean(text):
    return not [s for s in re.split(r'(?<=[。；])', text) if HARD.search(s) and not SOFT.search(s)]


def main():
    mea = {}
    with io.open(MEASURE, encoding='utf-8') as fp:
        for row in json.load(fp):
            mea[row['id']] = row
    with io.open(READINGS, encoding='utf-8') as fh:
        readings = json.load(fh)
    assert sorted(readings) == sorted(mea), (len(readings), len(mea))
    clean = sorted(k for k, v in readings.items() if is_clean(v))

    with io.open(NOTES, encoding='utf-8') as _fh:
        notes = json.load(_fh)
    with io.open(MANIFEST, encoding='utf-8') as _fp:
        man = json.load(_fp)
    items = {it['id']: it for it in man['items']}

    filled = 0
    replaced = 0
    for k in clean:
        row = mea[k]
        assert row['container']['cabx'] == 1, (k, 'caBX 不在位，不能占格')
        assert row['container']['itxt'] == 0, (k, 'PNG 侧不应出现 iTXt·TC260')
        assert 'C123新串' in row['file'], (k, row['file'])
        assert row['逐字相等'] is True, (k, '实发串与真源不相等')
        assert row['size_match'] is True, (k, '尺寸与清单不符')

        body = readings[k]
        old_list = items[k].get('image_file')
        if old_list:
            old = old_list[-1]
            assert 'B6雨后批' in old, (k, old)
            note = ('C123新串%s重投人工目视读数（vibe_images/%s，%s，%d字节，sha12=%s，caBX=1、iTXt=0%s）：%s'
                    % (k, row['file'], row['dims'], row['bytes'], row['sha256_12'],
                       header_tail('替换', old), body))
            old_list[-1] = 'vibe_images/' + row['file']
            items[k]['image_file'] = old_list
            replaced += 1
        else:
            note = ('C123新串%s重投人工目视读数（vibe_images/%s，%s，%d字节，sha12=%s，caBX=1、iTXt=0%s）：%s'
                    % (k, row['file'], row['dims'], row['bytes'], row['sha256_12'], header_tail('首占'), body))
            items[k]['image_file'] = ['vibe_images/' + row['file']]
        assert '本条只记人工读数，不代签验收。' in note, (k, '读数缺人工声明')

        notes['备注'].setdefault(k, [])
        for prev in notes['备注'][k]:
            assert 'C123新串%s重投' % k not in prev, (k, '本轮读数已打过')
        notes['备注'][k].append(note)

        items[k]['batch'] = '%s-%sC123新串-v01' % (items[k]['type'], k)
        assert not items[k].get('image_prompt_sha256'), (k, '已绑定摘要，不该再打表')
        filled += 1

    with io.open(NOTES, 'w', encoding='utf-8', newline='\n') as _handle:
        _handle.write(
            json.dumps(notes, ensure_ascii=False, indent=2) + '\n')
    with io.open(MANIFEST, 'w', encoding='utf-8', newline='\n') as _h103:
        _h103.write(
            json.dumps(man, ensure_ascii=False, indent=2) + '\n')
    print('回填 %d 条（首占 %d 条、替换第5格 %d 条）：%s'
          % (filled, filled - replaced, replaced, ' '.join(clean)))
    print('判废不回填 %d 条：%s' % (len(readings) - filled,
                                    ' '.join(sorted(k for k in readings if k not in clean))))


def align():
    """把本轮已落盘的 12 条抬头补齐 GUARD 句：只动脚本生成的抬头括号，人工读数正文一字不改。

    为什么补：判据要求读数自带「绑定留空、状态只到待复验」两枚口径要素，上一批这两句写在结论正文里，
    本轮写在括号里；不补齐，下一轮按抬头复述时这两句会查不到。
    """
    with io.open(NOTES, encoding='utf-8') as _h118:
        notes = json.load(_h118)
    hit = 0
    for eid, rows in notes['备注'].items():
        for i, row in enumerate(rows):
            head = 'C123新串%s重投人工目视读数（' % eid
            if not row.startswith(head) or GUARD in row:
                continue
            cut = row.find('）：')
            assert cut > 0, (eid, '抬头括号未闭合')
            assert 'sha12=' in row[:cut], (eid, '切点不在抬头内')
            rows[i] = row[:cut] + GUARD + row[cut:]
            hit += 1
    assert hit == 12, hit
    with io.open(NOTES, 'w', encoding='utf-8', newline='\n') as _h132:
        _h132.write(
            json.dumps(notes, ensure_ascii=False, indent=2) + '\n')
    print('抬头补齐 %d 条，正文未动' % hit)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'align':
        align()
    else:
        main()
