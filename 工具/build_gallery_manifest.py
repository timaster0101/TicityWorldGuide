# -*- coding: utf-8 -*-
"""把不入仓的图集落成一份仓内可核对清单：逐件相对路径、字节数与 sha256。

为什么需要它：`数据/图集/` 在 `.gitignore` 里（单张 3—4MB，647 件共约 1.9GB），git 里只有清单与备注记录
「哪一格挂哪个文件名」，文件本身一旦丢失或从备份还原，仓内没有任何东西能证明「还原回来的那一枚就是当初那一枚」。
本清单补的就是这一层：仓内留 647 行路径与摘要，仓外任意一份副本按它逐件对拍即可判真伪。

怎么更新：图集增删（回填、重投、归档）后跑一次
  python -X utf8 工具/build_gallery_manifest.py
它会重写 `数据/图集清单.json`；`工具/test_gallery_manifest.py` 随后就能逐件对上。
不写生成时间戳：时间戳每天变，会制造无意义的 diff；绑定面用「开图清单 sha12＋件数＋合计字节」三样。
"""
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
GALLERY = os.path.join(ROOT, '数据', '图集')
MANIFEST = os.path.join(ROOT, '数据', '开图清单.json')
OUT = os.path.join(ROOT, '数据', '图集清单.json')
PREFIX = '数据/图集/'


def collect(root=None):
    root = root or ROOT
    """返回 (逐件, 统计)。逐件按相对路径排序，摘要与字节现读现算。"""
    gallery = os.path.join(root, '数据', '图集')
    rows = []
    for dp, _dn, fn in os.walk(gallery):
        for name in fn:
            p = os.path.join(dp, name)
            rel = os.path.relpath(p, root).replace(os.sep, '/')
            with io.open(p, 'rb') as fp:
                data = fp.read()
            rows.append({'路径': rel, '字节': len(data),
                         'sha256': hashlib.sha256(data).hexdigest()})
    rows.sort(key=lambda r: r['路径'])
    with io.open(os.path.join(root, '数据', '开图清单.json'), 'rb') as fp:
        man_sha = hashlib.sha256(fp.read()).hexdigest()[:12]
    stat = {
        '件数': len(rows),
        '合计字节': sum(r['字节'] for r in rows),
        '合计MB': round(sum(r['字节'] for r in rows) / 1048576, 1),
        '目录数': len({r['路径'].rsplit('/', 1)[0] for r in rows}),
        '开图清单sha12': man_sha,
    }
    return rows, stat


def verify(root=None):
    root = root or ROOT
    """返回 (问题列表, 清单)。问题＝盘面与清单不一致之处，空列表即全对得上。"""
    p = os.path.join(root, '数据', '图集清单.json')
    with io.open(p, encoding='utf-8') as fp:
        rec = json.loads(fp.read())
    listed = {r['路径']: r for r in rec['逐件']}
    problems = []
    on_disk = set()
    for rel, r in listed.items():
        f = os.path.join(root, rel.replace('/', os.sep))
        if not os.path.isfile(f):
            problems.append({'类型': '清单有、盘上没有', '路径': rel})
            continue
        on_disk.add(rel)
        with io.open(f, 'rb') as fp:
            data = fp.read()
        if len(data) != r['字节']:
            problems.append({'类型': '字节不符', '路径': rel, '清单': r['字节'], '盘面': len(data)})
        elif hashlib.sha256(data).hexdigest() != r['sha256']:
            problems.append({'类型': '摘要不符', '路径': rel})
    gallery = os.path.join(root, '数据', '图集')
    for dp, _dn, fn in os.walk(gallery):
        for name in fn:
            rel = os.path.relpath(os.path.join(dp, name), root).replace(os.sep, '/')
            if rel not in listed:
                problems.append({'类型': '盘上有、清单没有', '路径': rel})
    return problems, rec


def main(argv):
    if len(argv) > 1 and argv[1] == '--verify':
        problems, rec = verify()
        print('图集清单核对：%d 件／%s MB｜问题 %d' % (rec['统计']['件数'], rec['统计']['合计MB'], len(problems)))
        for x in problems[:10]:
            print('  ', x)
        return 0 if not problems else 1
    rows, stat = collect()
    # 直链是 工具/oss_gallery.py --backfill 写的，不由本生成器负责；重写清单时把已有 url 带过去，
    # 否则「重跑 build_gallery_manifest」会静默抹掉 808 条直链，随后 test_oss_gallery 判红。
    prev_url = {}
    if os.path.isfile(OUT):
        try:
            with io.open(OUT, encoding='utf-8') as fp:
                for r in json.loads(fp.read()).get('逐件', []):
                    if r.get('url'):
                        prev_url[r['路径']] = r['url']
        except (ValueError, OSError):
            prev_url = {}
    kept = 0
    for r in rows:
        url = prev_url.get(r['路径'])
        if url:
            r['url'] = url
            kept += 1
    rec = {
        '说明': '数据/图集/ 的仓内可核对清单。图集本体在 .gitignore 内不入仓（单张 3—4MB，合计约 1.9GB），'
                '仓内只留这份路径＋摘要，用于核对任意一份副本（备份／还原／异机）是否与在册那一版逐件相同。',
        '口径': ('逐件 sha256 是文件全字节的摘要；路径相对仓库根；清单按路径排序。'
                 '本清单不绑定生成时间，绑定的是 开图清单sha12＋件数＋合计字节 这三样——'
                 '图集增删后必须重跑 `python -X utf8 工具/build_gallery_manifest.py`，'
                 '否则 `工具/test_gallery_manifest.py` 会以「盘上有、清单没有」或「摘要不符」判红。'),
        '接线': '工具/build_gallery_manifest.py --verify 逐件对拍；工具/test_gallery_manifest.py 在单测里跑同一套核对。',
        '统计': stat,
        '逐件': rows,
    }
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(json.dumps(rec, ensure_ascii=False, indent=2) + '\n')
    print('图集清单已重写：%d 件／%s MB（%d 个目录）→ 数据/图集清单.json'
          % (stat['件数'], stat['合计MB'], stat['目录数'])
          + ('｜带回直链 %d 条' % kept if kept else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
