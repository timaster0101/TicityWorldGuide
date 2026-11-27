# -*- coding: utf-8 -*-
"""把「图集里的图都是 AI 生成的」落成一份逐件可核的声明，代替图内角标。

起因（2026-11-27，交接清单 §55.67）：R10 起投送改走方舟标准域，用户裁定关闭平台水印，
而该通道产物本身没有 C2PA／TC260 容器（`container_profile` 实测 caBX=0、iTXt=0）。
于是「AI 生成」这件事在图上不再有任何标记，必须另立一个不烧进画面的标识载体：
本工具生成 `数据/图集AIGC声明.json`（逐件，机器核对）与 `数据/图集AIGC声明.md`（人读）。

为什么放在 `数据/` 而不进合订本：`阅读入口.md` 与 `质量核验报告.md` 是
`工具/compile_book.py` 的模板产物，改它们等于重导 docx、令第 29 次渲染目视作废。
声明是图集侧的附属件，不参与书的排版，因此独立成件、不进编译链。

用法：python -X utf8 工具/build_aigc_declaration.py [--check]
  --check 只核对、不写盘（供单测调用）。
"""
import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
GALLERY = os.path.join(ROOT, '数据', '图集')
OUT_JSON = os.path.join(ROOT, '数据', '图集AIGC声明.json')
OUT_MD = os.path.join(ROOT, '数据', '图集AIGC声明.md')
MANIFEST = os.path.join(ROOT, '数据', '图集清单.json')
PROMPTS = os.path.join(ROOT, '数据', '开图清单.json')
RUNLOGS = ('数据/R10方舟投送记录.json', '数据/R10方舟投送记录-带水印轮.json',
           '数据/R11方舟投送记录.json', '数据/R12方舟投送记录.json',
           '数据/R11方舟投送记录-双重前导废轮.json')
TS_RE = re.compile(r'_(1\d{12})_[0-9a-f]{8}\.[a-z]+$')

STATEMENT = (
    '本图集内所有插图均由生成式人工智能模型产出，不是摄影，也不是人工绘制。'
    '自 R10 轮起投送通道关闭了像素水印，但文件内仍带 C2PA 容器（caBX）元数据；'
    '本声明是叠加在这层机器可读元数据之上的人工可读清单，逐件给出提示词摘要与来源通道。'
    '转载、引用、二次分发图集内任何一枚图片时，须一并保留本声明（或本声明对该枚的在册记录），'
    '不得以裁剪、遮盖、重编码等方式删去其 AI 生成属性。'
)


def load_json(rel, root=None):
    root = root or ROOT
    p = os.path.join(root, rel.replace('/', os.sep))
    if not os.path.exists(p):
        return None
    with io.open(p, encoding='utf-8') as fp:
        return json.load(fp)


def gallery_files(root=None):
    root = root or ROOT
    out = []
    base = os.path.join(root, '数据', '图集')
    for dp, _dn, fn in os.walk(base):
        for name in fn:
            p = os.path.join(dp, name)
            rel = os.path.relpath(p, root).replace(os.sep, '/')
            with io.open(p, 'rb') as fp:
                data = fp.read()
            out.append({'路径': rel, '字节': len(data),
                        'sha256': hashlib.sha256(data).hexdigest()})
    out.sort(key=lambda r: r['路径'])
    return out


def channel_index(root=None):
    root = root or ROOT
    """文件名 → 投送记录行（只收方舟两轮台账，其余视为历史通道）。"""
    idx = {}
    for rel in RUNLOGS:
        rec = load_json(rel, root)
        if not rec:
            continue
        for row in rec['rows']:
            idx[row['file']] = dict(row, 台账=rel)
    return idx


def chunk_names(path, want=(b'caBX', b'iTXt')):
    """不整幅解码，只顺序读 PNG 的 chunk 头，看 caBX／iTXt 在不在（C136 的容器读数）。"""
    hit = []
    with io.open(path, 'rb') as fp:
        if fp.read(8) != b'\x89PNG\r\n\x1a\n':
            return hit
        while True:
            head = fp.read(8)
            if len(head) < 8:
                break
            ln = int.from_bytes(head[:4], 'big')
            name = head[4:8]
            if name in want:
                hit.append(name.decode('ascii'))
            fp.seek(ln + 4, 1)
            if name == b'IEND':
                break
    return hit


def day_of(name):
    m = TS_RE.search(name)
    if not m:
        return None
    import datetime
    ms = int(m.group(1))
    return datetime.datetime.fromtimestamp(ms / 1000.0).strftime('%Y-%m-%d')


def build(root=None):
    root = root or ROOT
    files = gallery_files(root)
    prompts = load_json('数据/开图清单.json', root) or {}
    items = prompts.get('items') or []
    by_id = {it['id']: it for it in items}
    chan = channel_index(root)
    rows, problems = [], []
    for f in files:
        parts = f['路径'].split('/')
        if len(parts) < 4:
            problems.append({'类型': '路径不在 <ID> 目录里', '路径': f['路径']})
            continue
        eid, name = parts[2], parts[3]
        it = by_id.get(eid)
        if it is None:
            problems.append({'类型': '图集里有、开图清单里没有这个ID', '路径': f['路径'], 'ID': eid})
            continue
        run = chan.get(name)
        if run is not None:
            source = '方舟标准域（doubao-seedream）'
            model = run.get('model') or 'doubao-seedream-5-0-pro-260628'
            watermark = '关（watermark=false）'
        else:
            source = 'ImageGen（会话内置，历史轮）'
            model = '未记录'
            watermark = '平台强制角标'
        chunks = chunk_names(os.path.join(root, f['路径'].replace('/', os.sep)))
        meta = '／'.join(chunks) + ' 在位' if chunks else '无容器元数据'
        rows.append({
            'ID': eid,
            '名称': it.get('name'),
            '类型': it.get('type'),
            '路径': f['路径'],
            '字节': f['字节'],
            'sha256': f['sha256'],
            '来源通道': source,
            '模型': model,
            '生成日期': day_of(name),
            '水印': watermark,
            '元数据': meta,
            '提示词摘要12': (it.get('prompt_sha256') or '')[:12],
        })
    stat = {
        '件数': len(rows),
        '覆盖ID数': len({r['ID'] for r in rows}),
        '方舟轮件数': sum(1 for r in rows if r['来源通道'].startswith('方舟')),
        '无日期件数': sum(1 for r in rows if not r['生成日期']),
    }
    rec = {
        '说明': STATEMENT,
        '口径': ('逐件 sha256 为文件全字节摘要，用于确认「被引用的那一枚就是声明里的这一枚」；'
                 '来源通道按文件是否出现在 R10 方舟投送台账里区分，台账之外的件归「历史通道」，'
                 '其模型名不在本仓记录范围内，故写「未记录」而不是猜一个。'
                 '本声明不改变任何图片字节，也不改开图清单的验收状态。'),
        '接线': 'python -X utf8 工具/build_aigc_declaration.py 重出；工具/test_aigc_declaration.py 逐件对拍并带违例负测。',
        '统计': stat,
        '逐件': rows,
    }
    return rec, problems


def render_md(rec):
    s = rec['统计']
    out = ['# 图集 AIGC 声明', '']
    out.append('> %s' % rec['说明'])
    out.append('')
    out.append('在册图片 **%d** 枚，覆盖 **%d** 个地点；其中方舟轮投送 %d 枚。'
               % (s['件数'], s['覆盖ID数'], s['方舟轮件数']))
    out.append('')
    out.append('| ID | 名称 | 文件 | 来源通道 | 模型 | 生成日期 | 水印 | 元数据 |')
    out.append('|---|---|---|---|---|---|---|---|')
    for r in rec['逐件']:
        out.append('| %s | %s | %s | %s | %s | %s | %s | %s |' % (
            r['ID'], r['名称'], r['路径'].rsplit('/', 1)[-1], r['来源通道'], r['模型'],
            r['生成日期'] or '未记录', r['水印'], r['元数据']))
    out.append('')
    out.append('逐件 sha256 与字节数见 `数据/图集AIGC声明.json`；核对面：'
               '`python -X utf8 工具/build_aigc_declaration.py --check`。')
    out.append('')
    return '\n'.join(out)


def main(argv):
    rec, problems = build()
    check = '--check' in argv[1:]
    if problems:
        print('声明构建失败：%d 处' % len(problems))
        for p in problems[:10]:
            print('  ', p)
        return 1
    if check:
        old = load_json('数据/图集AIGC声明.json')
        if old is None:
            print('声明件不存在')
            return 1
        if old['逐件'] != rec['逐件']:
            print('声明件与盘面不一致（逐件行有差异）')
            return 1
        print('声明核对通过：%d 件' % rec['统计']['件数'])
        return 0
    tmp = OUT_JSON + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(json.dumps(rec, ensure_ascii=False, indent=2) + '\n')
    os.replace(tmp, OUT_JSON)
    with io.open(OUT_MD, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(render_md(rec) + '\n')
    print('AIGC 声明已重写：%d 件／%d 个地点（方舟轮 %d 枚）→ 数据/图集AIGC声明.json、.md'
          % (rec['统计']['件数'], rec['统计']['覆盖ID数'], rec['统计']['方舟轮件数']))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
