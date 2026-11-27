# -*- coding: utf-8 -*-
"""开图清单 Markdown 与清单 JSON 的一致性闸门。

背景：这张 md 曾是 工具/build_prompts.py 的副产物，而那个脚本一跑就重算 312 条
prompt_sha256、把冻结基准整批挪走，所以实战中没人敢用它刷新这张表——于是 md 停在
「已验收 292／待复验 20」，json 早已 312／0，两边各说各话。收口轮把渲染抽成
工具/manifest_md.render_manifest_md()（唯一渲染方），由 工具/render_manifest_md.py
从 json 渲染，本模块保证它不再分叉。

判据（任一条红都说明「表」与「账」已经分家）：
  1) 盘面 md 与按 json 现渲染逐字相同；
  2) 汇总数只能来自 json（改 json 的计数，表头必须跟着变）；
  3) 状态／备注有变，检查必须判红（违例负测，防止闸门空转）；
  4) build_prompts.py 必须仍用同一个渲染方，且该渲染方不重算提示词摘要、不读提示词目录。
"""
import copy
import inspect
import io
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import manifest_md as M  # noqa: E402
import render_manifest_md as R  # noqa: E402


class ManifestMarkdown(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc, cls.order, cls.words = R.load()
        with io.open(R.TARGET, encoding="utf-8") as fp:
            cls.disk = fp.read()

    # 1) 盘面即现渲染
    def test_a_disk_markdown_matches_json(self):
        problems = M.check(self.doc, self.disk, self.order, self.words)
        self.assertEqual(problems, [], "清单 Markdown 与清单 JSON 已分叉：%s" % problems[:3])

    # 2) 汇总数来自 json
    def test_b_header_counts_come_from_json(self):
        doc = copy.deepcopy(self.doc)
        doc["items"] = doc["items"][:3]
        doc.update({"prompt_count": 3, "pending": 1, "generated": 2,
                    "accepted": 1, "needs_review": 1})
        text = M.render_manifest_md(doc["items"], doc, self.order, self.words)
        self.assertIn("提示词 3｜待开图 1｜有图 2｜已验收 1｜待复验 1", text)
        self.assertIn("# 钛湖城开图清单（3条，一图对一点）", text)

    # 3a) 状态改了必须判红
    def test_c_status_change_is_detected(self):
        doc = copy.deepcopy(self.doc)
        victim = next(i for i, m in enumerate(doc["items"]) if m["status"] == "已验收")
        doc["items"][victim]["status"] = "待复验"
        problems = M.check(doc, self.disk, self.order, self.words)
        self.assertTrue(problems, "把一条改成待复验后闸门没红")

    # 3b) 备注改了必须判红
    def test_d_note_change_is_detected(self):
        doc = copy.deepcopy(self.doc)
        victim = next(i for i, m in enumerate(doc["items"]) if m["review_note"])
        doc["items"][victim]["review_note"] += "（闸门负测追加）"
        problems = M.check(doc, self.disk, self.order, self.words)
        self.assertTrue(problems, "改备注后闸门没红")

    # 3c) 图片列改了必须判红
    def test_e_image_change_is_detected(self):
        doc = copy.deepcopy(self.doc)
        victim = next(i for i, m in enumerate(doc["items"]) if m["image_file"])
        doc["items"][victim]["image_file"] = doc["items"][victim]["image_file"] + ["数据/图集/X/x.png"]
        self.assertTrue(M.check(doc, self.disk, self.order, self.words))

    # 3d) 缺行必须判红（不是只比对前 k 行）
    def test_f_dropping_an_item_is_detected(self):
        doc = copy.deepcopy(self.doc)
        doc["items"].pop()
        doc["prompt_count"] -= 1
        problems = M.check(doc, self.disk, self.order, self.words)
        self.assertTrue(problems, "少一条后闸门没红")

    # 4a) build_prompts 必须还走同一个渲染方（不许各写一份）
    def test_g_build_prompts_uses_the_same_renderer(self):
        with io.open(ROOT / "工具" / "build_prompts.py", encoding="utf-8") as fp:
            src = fp.read()
        self.assertIn("from manifest_md import render_manifest_md", src)
        self.assertIn("render_manifest_md(manifest, out, BATCH_ORDER, TECH_CARRIER_WORDS)", src)
        self.assertNotIn("def render_manifest_md", src, "渲染方被复制回 build_prompts 了")

    # 4b) 渲染方不重算摘要、不碰提示词目录（否则刷新一次就漂移基准）
    def test_h_renderer_is_pure(self):
        import tokenize
        src = inspect.getsource(M.render_manifest_md)
        # 去掉字符串字面量与注释：表头正文里本来就写着 prompt_sha256 这类词（那是给
        # 人看的说明），要拦的是代码真的去算摘要、去读盘、去写盘。
        code = []
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.STRING, tokenize.COMMENT):
                continue
            code.append(tok.string)
        joined = " ".join(code)
        for banned in ("sha256", "hashlib", "io.open", "write_text", "read_text",
                       "open", "glob", "Path("):
            self.assertNotIn(banned, joined, "渲染方代码里出现 %r，会连带改写基准或磁盘" % banned)

    # 4c) 科技层词表从 build_prompts 源码读出且确实渲染进了表
    def test_i_tech_words_are_rendered(self):
        self.assertGreaterEqual(len(self.words), 5)
        self.assertIn("、".join(self.words), self.disk)


if __name__ == "__main__":
    unittest.main()
