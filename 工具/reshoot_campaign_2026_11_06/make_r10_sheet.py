# -*- coding: utf-8 -*-
"""把 send_bodies_r10.json 渲染成一份人／外部会话都能照做的投送单（不复制串面，只指路）。

为什么不把 6 千多字的送入串抄进 md：串面真源只有台账 body 一处，抄第二份就等着两处对不上
（R9 那次正是靠「body 与盘上正文逐字」判据才发现口径分叉）。投送单只给发哪个、多大、用哪张
母图、发名与串 sha，正文回台账取。

跑法：python -X utf8 工具/reshoot_campaign_2026_11_06/make_r10_sheet.py
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(HERE, 'R10投送单.md')


def main():
    with io.open(os.path.join(HERE, 'send_bodies_r10.json'), encoding='utf-8') as fp:
        led = json.loads(fp.read())
    with io.open(os.path.join(HERE, 'send_bodies_r10_note.json'), encoding='utf-8') as fp:
        note = json.loads(fp.read())
    ids = note['成员面']
    probe = note['探针']
    lines = [
        '# R10 投送单（%d 枚，探针先行）' % len(ids),
        '',
        '- 送入串真源：`工具/reshoot_campaign_2026_11_06/send_bodies_r10.json` 的 `body` 字段'
        '（已含 r4_style_ref 前导一行；`send_sha256` 是 `body` 实际送入值的 sha）',
        '- 顺序：**先发探针 %s**；返回 `HTTP 403 · code 112` 就地停手，其余 %d 条一条都不发；'
        '绿了再按本表续发' % (probe, len(ids) - 1),
        '- 母图按每行的 `ref_image` 附上（ImageGen `images` 参数一张）；尺寸用 `size`',
        '- 发名用 `send_name`；落地后勿手改、勿裁角标，回填走 `verify_round.py R10` → '
        '`backfill_round.py R10`',
        '',
        '| # | ID | 发名 | 尺寸 | 字符 | send sha12 | 母图 |',
        '|---|---|---|---|---|---|---|',
    ]
    for n, eid in enumerate(ids, 1):
        row = led[eid]
        tag = ' **探针**' if eid == probe else ''
        lines.append('| %d | %s%s | %s | %s | %d | %s | `%s` |'
                     % (n, eid, tag, row['send_name'], row['size'], row['chars'],
                        row['send_sha256'][:12], row['ref_image']))
    lines += ['', '## 逐条落地信息', '']
    for n, eid in enumerate(ids, 1):
        row = led[eid]
        lines += [
            '### %d. %s%s' % (n, eid, '（探针）' if eid == probe else ''),
            '',
            '- 发名：`%s`' % row['send_name'],
            '- 尺寸：%s｜字符 %d｜body 字符 %d' % (row['size'], row['chars'], row['body_chars']),
            '- send sha256：`%s`' % row['send_sha256'],
            '- 母图：`%s`（%s）' % (row['ref_image'], row.get('ref_dims', '登记未载')),
            '- 母图绝对路径：`%s`' % os.path.join(ROOT, row['ref_image'].replace('/', os.sep)),
            '- 占格（落地件应落在此处替代）：`%s`' % row['replaced_cell'],
            '- 串面：取 ledger `["%s"]["body"]`' % eid,
            '',
        ]
    text = '\n'.join(lines).rstrip() + '\n'
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(text)
    print('写出 %s（%d 行，%d 字符）' % (os.path.basename(OUT), len(lines), len(text)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
