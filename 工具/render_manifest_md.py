# -*- coding: utf-8 -*-
"""按 数据/开图清单.json 刷新 数据/开图清单.md（不重钉提示词基准）。

用法：
    python -X utf8 工具/render_manifest_md.py            # 写盘
    python -X utf8 工具/render_manifest_md.py --check    # 只核对，盘面过期则退出码 1

为什么需要它：这张 md 原先是 工具/build_prompts.py 的副产物，而那个脚本一跑就会重算
312 条 prompt_sha256、让冻结基准整批漂移（R10 轮踩过，靠 git checkout 回退）。收口轮实测
md 写着「已验收 292／待复验 20」、json 已是 312／0，本脚本负责把两者拉回一致。

渲染方只有一处：工具/manifest_md.render_manifest_md()，build_prompts.py 也调它。
"""
import io
import json
import sys
from pathlib import Path

import manifest_md as M

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "数据" / "开图清单.json"
TARGET = ROOT / "数据" / "开图清单.md"
BUILD_PROMPTS = ROOT / "工具" / "build_prompts.py"


def load():
    """读清单与渲染所需的两个常量来源（batch_order 来自 json、科技层词表读源码）。"""
    with io.open(MANIFEST, encoding="utf-8") as fp:
        doc = json.loads(fp.read())
    order = doc.get("batch_order")
    if not order:
        raise SystemExit("清单缺 batch_order，无法按原顺序渲染")
    return doc, order, M.tech_carrier_words_from_source(BUILD_PROMPTS)


def _read_target():
    if not TARGET.exists():
        return ""
    with io.open(TARGET, encoding="utf-8") as fp:
        return fp.read()


def _banner(doc):
    return "%d 条，已验收 %d，待复验 %d，有图 %d" % (
        doc["prompt_count"], doc["accepted"], doc["needs_review"], doc["generated"])


def main(argv):
    check_only = "--check" in argv
    doc, order, words = load()
    text = M.render_manifest_md(doc["items"], doc, order, words)

    if check_only:
        current = _read_target()
        problems = M.check(doc, current, order, words)
        if problems:
            print("清单 Markdown 已过期：")
            for p in problems:
                print("  -", p)
            return 1
        print("清单 Markdown 与清单一致：" + _banner(doc))
        return 0

    current = _read_target()
    if text == current:
        print("无变化：" + _banner(doc))
        return 0
    TARGET.write_text(text, encoding="utf-8")
    print("已刷新：" + _banner(doc))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
