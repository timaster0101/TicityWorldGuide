# -*- coding: utf-8 -*-
"""把 数据/开图清单.json 的五个计数按状态现算同步（只动计数，不动提示词串）。

为什么要单独一支：这五个计数原本由 build_prompts.py 派生，但那个脚本会重算 312 份提示词正文并重写
prompt_sha256——实测它与冻结基准对不上（详档正文 908→914 汉字），跑一次就让 312 条基准全线漂移。
所以收口之后同步计数只能走这一支：口径与 build_prompts.py:696-700 逐字一致，输入只有清单自己的 status。

不改的东西：提示词 txt、prompt_sha256、image_prompt_sha256、image_file、备注。也不重写 数据/开图清单.md
（那份表逐条列状态，重写同样得走 build_prompts），它的 stale 面在交接清单里注明，等一次完整重建再刷新。

跑法：
    python 工具/sync_manifest_counts.py            干跑，只打印前后
    python 工具/sync_manifest_counts.py --execute  落盘
"""
import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / '数据' / '开图清单.json'


def counts(items):
    """口径与 build_prompts.py:696-700 逐字一致，改口径必须两处同改并在 test 里对拍。"""
    return {
        'prompt_count': len(items),
        'pending': sum(1 for m in items if m['status'] == '待开图'),
        'generated': sum(1 for m in items if m['image_file']),
        'accepted': sum(1 for m in items if m['status'] == '已验收'),
        'needs_review': sum(1 for m in items if m['status'] == '待复验'),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--execute', action='store_true')
    args = ap.parse_args()
    with io.open(MANIFEST, encoding='utf-8') as fp:
        doc = json.load(fp)
    before = {k: doc.get(k) for k in counts(doc['items'])}
    after = counts(doc['items'])
    diff = {k: (before[k], after[k]) for k in after if before[k] != after[k]}
    print('现算 %s' % json.dumps(after, ensure_ascii=False))
    print('变化 %s' % (json.dumps(diff, ensure_ascii=False) if diff else '无'))
    if not diff:
        return 0
    if not args.execute:
        print('（干跑，未落盘。加 --execute 才写）')
        return 0
    doc.update(after)
    with io.open(MANIFEST, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(json.dumps(doc, ensure_ascii=False, indent=2) + '\n')
    print('✅ 已落盘 数据/开图清单.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
