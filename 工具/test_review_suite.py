# -*- coding: utf-8 -*-
"""B5 人工复看套件的判据：套件只许排工作与列判据，不许替人写结论。
真实仓库只读，全部执行在临时副本里。"""
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
INPUT_FILES = ("开图清单.json", "开图验收备注.json")
CHECK_LABELS = ("画风", "双层接触", "生活痕迹", "招牌与文字", "年代锁", "日面可纳性",
                "远景可纳性", "远景塔形来源", "形体与硬参数", "人数落档")


class ReviewSuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="test_review_suite_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "工具").mkdir()
        (self.root / "数据").mkdir()
        self.script = self.root / "工具" / "build_review_suite.py"
        shutil.copyfile(ROOT / "工具" / "build_review_suite.py", self.script)
        for name in INPUT_FILES:
            shutil.copyfile(ROOT / "数据" / name, self.root / "数据" / name)
        shutil.copytree(ROOT / "数据" / "开图提示词", self.root / "数据" / "开图提示词")
        self.manifest = json.loads((self.root / "数据" / "开图清单.json").read_text(encoding="utf-8"))["items"]
        self.run_suite()

    def run_suite(self):
        before = (self.root / "数据" / "开图清单.json").read_bytes()
        result = subprocess.run([sys.executable, "-B", str(self.script)], cwd=self.root,
                                capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.out = self.root / "数据" / "人工复看套件"
        self.work = (self.out / "工作单.md").read_text(encoding="utf-8")
        # 套件是只读工作 aids：清单字节必须逐字节不变。
        self.assertEqual((self.root / "数据" / "开图清单.json").read_bytes(), before)

    def item_blocks(self):
        """按 `### ID 名称｜类型` 切块，返回 {id: 该条正文行}。"""
        blocks = {}
        current = None
        for line in self.work.splitlines():
            if line.startswith("### "):
                current = line.split()[1]
                blocks[current] = []
            elif current:
                blocks[current].append(line)
        return blocks

    def signed_verdict_ids(self):
        """判据纯函数：凡是「结论／十条打表栏」被脚本填成非空（不是 ＿＿）的条，就是代签。"""
        out = []
        for eid, lines in self.item_blocks().items():
            for line in lines:
                m = re.match(r"^  - (结论|%s)：(.*)$" % "|".join(CHECK_LABELS), line)
                if not m:
                    continue
                value = m.group(2).split("｜")[0].split("（")[0].strip()
                if value != "＿＿":
                    out.append((eid, m.group(1), value))
        return out

    def test_covers_every_item_with_images_and_every_cell_once(self):
        with_images = [it for it in self.manifest if it.get("image_file")]
        # 第五投 3 条（L093／L101／L108）首占后，有图条目 300→303、格数 1113→1116
        self.assertEqual(len(with_images), 303)
        cells = [p for it in with_images for p in it["image_file"]]
        self.assertEqual(len(cells), 1116)
        blocks = self.item_blocks()
        self.assertEqual(sorted(blocks), sorted(it["id"] for it in with_images))
        for path in cells:
            self.assertEqual(self.work.count("- 图格：%s" % path), 1, path)
        for it in with_images:
            block = "\n".join(blocks[it["id"]])
            self.assertEqual(block.count("- 图格："), len(it["image_file"]), it["id"])

    def test_lists_the_ten_criteria_and_the_rule_sources(self):
        for eid, lines in self.item_blocks().items():
            block = "\n".join(lines)
            with self.subTest(eid=eid):
                for label in CHECK_LABELS:
                    self.assertEqual(block.count("  - %s：" % label), 1, eid)
                self.assertIn("  - 结论：", block)
        header = self.work.split("### ")[0]
        for token in ("C100", "C101", "C99", "C92", "C97", "C106", "判据十条", "不写结论", "本单每次重跑会被覆盖"):
            self.assertIn(token, header)

    def test_c123_and_c124_rewrite_the_background_and_floor_criteria(self):
        """C123／C124 落进判据栏的两处口径：背景授权唯一入口是取景段逐一点名，正文写作「远景」的主体构件不算；
        画面可读层数与锁定层数不符只记备注、不单独判废。**Why**：层数与米数只活在 101/312 条的中文段，
        English tail 里没有可数的单元，判废栏留着它就等于判一条模型无从得知的禁令。
        旧的「高度、层数、冠部形态与名录真值一致」串回到任何一条即判红。"""
        text = "\n".join(self.item_blocks()["L001"])
        self.assertIn("画面可读层数与锁定层数不符只记备注、不单独判废（C124", text)
        self.assertNotIn("高度、层数、冠部形态与名录真值一致", text)
        self.assertIn("正文里写作「远景」的主体自身构件不算背景授权", text)
        header = self.work.split("### ")[0]
        for token in ("C123", "C124"):
            self.assertIn(token, header)

    C125_MARKED_TIER = ("凭空冠部、塔吊或带专属形制记号（斜削冠／细针天线／桅杆与斜拉索上段／冠部开洞／"
                        "扭转塔身）的未点名体量即判废")
    C125_SILHOUETTE_TIER = "平头与剪影类未点名体量记备注、不单独判废（C125：剪影不带记号，人工复看不作硬判）"
    C125_LEGACY_TIER = "凭空天际线、超高层冠部或塔吊即判废"

    def c125_violations(self):
        """判据纯函数：每条的「远景可纳性」栏必须同时给出 C125 的两档——带记号者判废、平头与剪影者记备注，
        且 C123 之前的整句判废不得回流。缺任一句即按条报，两档是同时存在的，不是二选一。"""
        out = []
        for eid, block in sorted(self.item_blocks().items()):
            text = "\n".join(block)
            if "远景可纳性" not in text:
                out.append((eid, "本条无远景可纳性判据栏"))
                continue
            if self.C125_MARKED_TIER not in text:
                out.append((eid, "记号档判废句缺失"))
            if self.C125_SILHOUETTE_TIER not in text:
                out.append((eid, "剪影档备注句缺失"))
            if self.C125_LEGACY_TIER in text:
                out.append((eid, "旧的整句判废回流"))
        return out

    def test_c125_splits_unnamed_background_bodies_into_two_tiers(self):
        """C125 的判据侧分档：背景里未点名的体量按「能否读出专属形制记号」分两档——带记号者判废、
        平头与剪影者只记备注。**Why**：第9批 19 条重投的读数是 0/19 带记号违例、11/19 带剪影体量，
        剪影不带记号、人工复看对不到名录的某一栋，留在判废栏等于每轮复核一次不可核对的判废。"""
        self.assertEqual(self.c125_violations(), [])
        text = "\n".join(self.item_blocks()["L001"])
        self.assertIn(self.C125_MARKED_TIER, text)
        self.assertIn(self.C125_SILHOUETTE_TIER, text)
        self.assertIn("C125", self.work.split("### ")[0])

    def test_demoting_every_unnamed_body_is_caught(self):
        """违例负测：从生成器副本里删掉记号档判废句、只留降级句（即把「记备注」误扩到全部未点名体量），
        判据必须 300 条全报且只报这一句缺失；剪影档降级句仍在，证明红的是力度越界，不是判据丢失。"""
        pristine = self.script.read_text(encoding="utf-8")
        self.assertEqual(pristine.count(self.C125_MARKED_TIER), 1, "注入锚点没落在 C125 的记号档判废句上")
        self.script.write_text(pristine.replace(self.C125_MARKED_TIER, "", 1), encoding="utf-8")
        self.run_suite()
        violations = self.c125_violations()
        self.assertEqual(sorted({eid for eid, _ in violations}), sorted(self.item_blocks()))
        self.assertEqual({reason for _, reason in violations}, {"记号档判废句缺失"})
        self.assertIn(self.C125_SILHOUETTE_TIER, "\n".join(self.item_blocks()["L001"]))
        self.script.write_text(pristine, encoding="utf-8")
        self.run_suite()
        self.assertEqual(self.c125_violations(), [])

    def test_reverting_to_the_wholesale_background_rejection_is_caught(self):
        """违例负测：把判据栏改回 C125 之前的整句判废（未点名者一律判废、不分两档），逐条报三处：
        两档句各缺失、旧串回流。恢复后必须回到全绿，夹具不留残留。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = self.C125_MARKED_TIER + "；" + self.C125_SILHOUETTE_TIER
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在 C125 的两档分工上")
        self.script.write_text(pristine.replace(anchor, self.C125_LEGACY_TIER, 1), encoding="utf-8")
        self.run_suite()
        self.assertEqual(sorted({reason for _, reason in self.c125_violations()}),
                         ["剪影档备注句缺失", "旧的整句判废回流", "记号档判废句缺失"])
        self.script.write_text(pristine, encoding="utf-8")
        self.run_suite()
        self.assertEqual(self.c125_violations(), [])

    def test_verdict_columns_are_blank_and_no_acceptance_language(self):
        self.assertEqual(self.signed_verdict_ids(), [])
        self.assertNotIn("已验收", self.work)
        self.assertNotIn("结论：通过", self.work)
        csv_text = (self.out / "打表汇总.csv").read_text(encoding="utf-8-sig")
        # 第五投首占 3 条后：有图条目 300→303，打表行 301→304（含表头）
        self.assertEqual(len(csv_text.strip().splitlines()), 304)
        self.assertNotIn("通过", csv_text.splitlines()[0])
        self.assertEqual(csv_text.count("已验收"), 0)

    def test_contact_sheets_paginate_and_link_local_images(self):
        sheets = self.out / "联络表"
        pages = sorted(sheets.glob("页-*.html"))
        self.assertEqual(len(pages), 38)
        index = (sheets / "index.html").read_text(encoding="utf-8")
        self.assertIn("共 303 条既有图", index)
        self.assertIn("结构合规不等于视觉验收", index)
        cells = [p for it in self.manifest if it.get("image_file") for p in it["image_file"]]
        linked = []
        for page in pages:
            text = page.read_text(encoding="utf-8")
            self.assertLessEqual(text.count('<div class="item">'), 8, page.name)
            self.assertIn("本页只排图与判据，不写通过", text)
            for src in re.findall(r'<img loading="lazy" src="([^"]+)"', text):
                # 联络表深三层，缺一级 ../ 就整页脱链。
                self.assertTrue(src.startswith("../../../"), src)
                linked.append(unquote(src)[len("../../../"):])
        # 链接只按字符串还原：图片文件不版本化，临时副本里本来就没有图。这里判的是「src 解码后
        # 正好落回清单里的某一格、且一格不漏不多」；格子在不在盘上由 verify_image_assets 的 1116 格负责。
        self.assertEqual(sorted(linked), sorted(cells))
        self.assertEqual(len(linked), 1116)

    def test_rerun_is_byte_identical(self):
        snapshot = {p.relative_to(self.out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(self.out.rglob("*")) if p.is_file()}
        self.run_suite()
        again = {p.relative_to(self.out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(self.out.rglob("*")) if p.is_file()}
        self.assertEqual(snapshot.keys(), again.keys())
        self.assertEqual(snapshot, again)

    def test_script_signed_verdict_is_caught_by_the_new_gate(self):
        """违例负测：让脚本替 L001 把「结论」栏直接填成 通过（等于代签验收），
        新判据必须只给出这一条；十条判据与图格数等既有断言仍为绿，证明该缺陷要靠新判据才抓得住。
        变异对照：恢复原文后同一判据归零。注入只改临时副本，真实仓库不受影响。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = '        lines.append("  - 结论：%s（通过／判废重出／待重出）｜备注：%s" % (BLANK, BLANK))'
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在工作单的结论行")
        injected = ('        lines.append("  - 结论：%s（通过／判废重出／待重出）｜备注：%s"'
                    ' % ("通过" if it["id"] == "L001" else BLANK, BLANK))')
        self.script.write_text(pristine.replace(anchor, injected, 1), encoding="utf-8")
        self.run_suite()
        self.assertEqual(self.signed_verdict_ids(), [("L001", "结论", "通过")])
        self.assertIn("- 图格：数据/图集", self.work)
        self.script.write_text(pristine, encoding="utf-8")
        self.run_suite()
        self.assertEqual(self.signed_verdict_ids(), [])


if __name__ == "__main__":
    unittest.main()
