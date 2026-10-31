# -*- coding: utf-8 -*-
"""只在临时项目副本执行真实生成器；真实输入只读，不复制或改写真实图片/清单。"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
INPUTS = ("AI地点知识库.json", "参考房价租金.json", "城市空间名录.json")


class BuildPromptsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="test_prompts_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "数据"
        self.data.mkdir()
        tools = self.root / "工具"
        tools.mkdir()
        self.script = tools / "build_prompts.py"
        shutil.copyfile(ROOT / "工具" / "build_prompts.py", self.script)
        for name in INPUTS:
            shutil.copyfile(ROOT / "数据" / name, self.data / name)
        self.kb = self.load("AI地点知识库.json")
        self.prices = self.load("参考房价租金.json")["records"]
        self.run_generator()

    def load(self, name):
        return json.loads((self.data / name).read_text(encoding="utf-8"))

    def save(self, name, value):
        (self.data / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def run_generator(self):
        result = subprocess.run(
            [sys.executable, "-B", str(self.script)], cwd=self.root,
            capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.manifest = self.load("开图清单.json")
        self.items = {item["id"]: item for item in self.manifest["items"]}

    def prompt(self, eid):
        return (self.root / self.items[eid]["prompt_file"]).read_text(encoding="utf-8")

    def save_manifest(self):
        self.save("开图清单.json", self.manifest)

    def add_image(self, eid="D01", accepted=True, bind=True):
        item = self.items[eid]
        item.update(image_file="数据/test-image.bin", batch="fixture-batch",
                    status="已验收" if accepted else "待复验", note="既有人工备注",
                    review_note="已有复验备注")
        (self.root / item["image_file"]).write_bytes(b"unchanged fixture image")
        if bind:
            self.assertRegex(item.get("prompt_sha256", ""), r"^[0-9a-f]{64}$")
            item["image_prompt_sha256"] = item["prompt_sha256"]
        else:
            item.pop("image_prompt_sha256", None)
        self.save_manifest()
        return dict(item)

    def assert_status_outputs(self, eid, status):
        item = self.items[eid]
        self.assertEqual(item["status"], status)
        self.assertIn("- 状态：" + status, self.prompt(eid))
        md = (self.data / "开图清单.md").read_text(encoding="utf-8")
        row = next(line for line in md.splitlines() if line.startswith("| " + eid + " |"))
        self.assertIn(status, row)
        if item.get("review_note"):
            self.assertIn(item["review_note"], self.prompt(eid))
            self.assertIn(item["review_note"], row)

    def test_all_264_rents_have_complete_units(self):
        self.assertEqual(len(self.items), 264)
        for price in self.prices:
            text = self.items[price["id"]]["pricing_reference"]
            for key in ("residential", "office", "retail", "street_retail"):
                value = price.get(key)
                if not value:
                    continue
                with self.subTest(eid=price["id"], use=key):
                    if "rent_tt_per_m2_month" in value:
                        expected = "租%s钛币/㎡·月" % value["rent_tt_per_m2_month"]
                    else:
                        expected = "租%s钛币/㎡·天" % value["rent_tt_per_m2_day"]
                    self.assertIn(expected, text)
                    self.assertIn(expected, self.prompt(price["id"]))

    def test_all_20_city_districts_belong_to_main_city(self):
        districts = [item for item in self.items.values() if item["parent"] == "CITY"]
        self.assertEqual(len(districts), 20)
        for item in districts:
            with self.subTest(eid=item["id"]):
                self.assertEqual(item["parent_name"], "主城区")
                self.assertIn("主城区（CITY）", self.prompt(item["id"]))

    def test_landmarks_use_canonical_shape_and_only_known_towers_are_portrait(self):
        towers = {"L003", "L007", "L022", "L033", "L038"}
        landmarks = [item for item in self.items.values() if item["id"].startswith("L")]
        self.assertEqual(len(landmarks), 60)
        for item in landmarks:
            with self.subTest(eid=item["id"]):
                portrait = item["id"] in towers
                self.assertEqual(item["size"], "1024x1536" if portrait else "1536x1024")
                self.assertIn("2:3 竖幅" if portrait else "3:2 横幅", item["aspect"])
                self.assertNotIn("single-tower", self.prompt(item["id"]))
        self.assertIn("体育场", self.prompt("L028"))
        self.assertIn("Chinese canon sections overrides this line", self.prompt("L028"))

    def test_district_and_settlement_aspects_match_pixel_sizes(self):
        for item in self.items.values():
            if item["id"].startswith(("D", "S")):
                with self.subTest(eid=item["id"]):
                    self.assertEqual(item["size"], "1792x1024")
                    self.assertIn("7:4 横幅", item["aspect"])
                    self.assertNotIn("16:9", self.prompt(item["id"]))

    def test_46_public_assets_are_reference_only_without_invented_residential_prices(self):
        public = [price for price in self.prices if price.get("asset_use") == "公共自用"]
        self.assertEqual(len(public), 46)
        for price in public:
            with self.subTest(eid=price["id"]):
                text = self.items[price["id"]]["pricing_reference"]
                self.assertIn("仅周边/同地块功能组合参考", text)
                self.assertIn("不是本建筑交易价", text)
                self.assertIn(text, self.prompt(price["id"]))
                if not price.get("residential"):
                    self.assertNotIn("住宅", text)

    def test_full_framing_appearance_and_locks_are_not_truncated(self):
        for rec in self.kb:
            for section in ("图像与视频取景", "外观与辨识细节", "锁定项与禁则"):
                with self.subTest(eid=rec["id"], section=section):
                    self.assertIn(rec["sections"][section], self.prompt(rec["id"]))

    def test_watermark_rule_explicitly_preserves_mandatory_platform_labels(self):
        for eid in self.items:
            with self.subTest(eid=eid):
                text = self.prompt(eid)
                self.assertIn("平台强制AIGC", text)
                self.assertIn("原样保留", text)
                tail = text.split("English tail: ", 1)[1]
                self.assertIn("no third-party or model-generated watermark", tail)
                self.assertIn("preserve mandatory platform AIGC labels", tail)

    def test_no_image_cannot_be_accepted_or_count_as_generated(self):
        for eid, status in (("D01", "已验收"), ("L007", "失败")):
            self.items[eid].update(status=status, image_file=None, batch="failed-batch")
        self.save_manifest()
        self.run_generator()
        self.assertEqual(self.manifest["generated"], 0)
        self.assertEqual(self.manifest["pending"], 264)
        self.assertEqual(self.manifest.get("accepted"), 0)
        self.assertEqual(self.manifest.get("needs_review"), 0)
        self.assert_status_outputs("D01", "待开图")
        self.assert_status_outputs("L007", "待开图")

    def test_legacy_unbound_image_needs_review_without_changing_image_or_notes(self):
        previous = self.add_image(bind=False)
        self.run_generator()
        item = self.items["D01"]
        self.assert_status_outputs("D01", "待复验")
        self.assertIn("缺少 image_prompt_sha256", item["review_note"])
        self.assertIn("已有复验备注", item["review_note"])
        self.assertIsNone(item.get("image_prompt_sha256"))
        for field in ("image_file", "batch", "note"):
            self.assertEqual(item[field], previous[field])
        self.assertEqual((self.root / item["image_file"]).read_bytes(), b"unchanged fixture image")
        self.assertEqual(self.manifest["generated"], 1)
        self.assertEqual(self.manifest.get("accepted"), 0)
        self.assertEqual(self.manifest.get("needs_review"), 1)
        self.run_generator()
        self.assertEqual(self.items["D01"], item)

    def test_real_d01_framing_change_invalidates_previous_acceptance(self):
        previous = self.add_image()
        rec = next(rec for rec in self.kb if rec["id"] == "D01")
        original = rec["sections"]["图像与视频取景"]
        self.assertIn("机位离地55米", original)
        rec["sections"]["图像与视频取景"] = original.replace("机位离地55米", "机位离地65米")
        self.save("AI地点知识库.json", self.kb)
        self.run_generator()
        item = self.items["D01"]
        self.assert_status_outputs("D01", "待复验")
        self.assertNotEqual(item["prompt_sha256"], previous["prompt_sha256"])
        self.assertEqual(item["image_prompt_sha256"], previous["image_prompt_sha256"])
        self.assertIn("不一致", item["review_note"])
        self.assertIn("机位离地65米", self.prompt("D01"))
        self.assertEqual((self.root / item["image_file"]).read_bytes(), b"unchanged fixture image")

    def test_same_inputs_preserve_bound_acceptance_across_reruns(self):
        previous = self.add_image()
        self.run_generator()
        item = self.items["D01"]
        self.assert_status_outputs("D01", "已验收")
        for field in ("prompt_sha256", "image_prompt_sha256", "image_file", "batch", "note", "review_note"):
            self.assertEqual(item[field], previous[field])
        self.assertEqual(self.manifest.get("accepted"), 1)
        self.assertEqual(self.manifest.get("needs_review"), 0)
        first = self.manifest
        first_prompt = self.prompt("D01")
        self.run_generator()
        self.assertEqual(self.manifest, first)
        self.assertEqual(self.prompt("D01"), first_prompt)

    def test_hash_excludes_backfill_paths_batch_status_and_notes(self):
        self.assertTrue(all("prompt_sha256" in item for item in self.items.values()))
        before = {eid: item["prompt_sha256"] for eid, item in self.items.items()}
        self.add_image()
        self.items["D01"].update(batch="another-batch", note="补充人工结论")
        self.save_manifest()
        self.run_generator()
        self.assertEqual({eid: item["prompt_sha256"] for eid, item in self.items.items()}, before)
        self.assertEqual(self.items["D01"]["status"], "已验收")

    def test_binding_mismatch_is_not_silently_rebound(self):
        self.add_image()
        self.items["D01"]["image_prompt_sha256"] = "0" * 64
        self.save_manifest()
        self.run_generator()
        self.assert_status_outputs("D01", "待复验")
        self.assertEqual(self.items["D01"]["image_prompt_sha256"], "0" * 64)

    def test_binding_alone_does_not_automatically_accept_image(self):
        self.add_image(accepted=False)
        self.run_generator()
        self.assert_status_outputs("D01", "待复验")
        self.assertEqual(self.manifest.get("accepted"), 0)

    def bind_supplemental_input(self):
        item = self.add_image(bind=False)
        item = self.items["D01"]
        item.update(
            generation_input_file="数据/test-generation-input.txt",
            generation_input_sha256="a" * 64,
            image_base_prompt_sha256=item["prompt_sha256"],
            image_prompt_sha256="a" * 64,
        )
        self.save_manifest()

    def test_supplemental_input_binds_actual_hash_and_base_version(self):
        self.bind_supplemental_input()
        self.run_generator()
        item = self.items["D01"]
        self.assert_status_outputs("D01", "已验收")
        self.assertEqual(item["image_prompt_sha256"], "a" * 64)
        self.assertEqual(item["image_base_prompt_sha256"], item["prompt_sha256"])
        self.assertEqual(item["generation_input_file"], "数据/test-generation-input.txt")

    def test_supplemental_input_base_change_needs_review(self):
        self.bind_supplemental_input()
        rec = next(rec for rec in self.kb if rec["id"] == "D01")
        rec["sections"]["图像与视频取景"] += "测试改变基准。"
        self.save("AI地点知识库.json", self.kb)
        self.run_generator()
        item = self.items["D01"]
        self.assert_status_outputs("D01", "待复验")
        self.assertEqual(item["image_prompt_sha256"], "a" * 64)
        self.assertIn("基准提示词已变化", item["review_note"])

    def test_hash_changes_with_hard_parameters_identity_price_and_size(self):
        self.assertTrue(all("prompt_sha256" in item for item in self.items.values()))
        baseline = {eid: item["prompt_sha256"] for eid, item in self.items.items()}
        registry = self.load("城市空间名录.json")
        next(e for e in registry["entries"] if e["id"] == "L007")["height_m"] = 369
        self.save("城市空间名录.json", registry)
        next(rec for rec in self.kb if rec["id"] == "D01")["name"] += "测试更名"
        next(rec for rec in self.kb if rec["id"] == "L028")["sections"]["锁定项与禁则"] += "测试新增锁定。"
        self.save("AI地点知识库.json", self.kb)
        pricing = self.load("参考房价租金.json")
        next(p for p in pricing["records"] if p["id"] == "D02")["office"]["sale_tt_per_m2"] += 100
        self.save("参考房价租金.json", pricing)
        self.run_generator()
        for eid in ("L007", "D01", "L028", "D02"):
            with self.subTest(eid=eid):
                self.assertNotEqual(self.items[eid]["prompt_sha256"], baseline[eid])
        self.assertEqual(self.items["S01"]["prompt_sha256"], baseline["S01"])
        # 尺寸是生成器模板输入；只修改临时脚本来验证它也参与摘要。
        source = self.script.read_text(encoding="utf-8")
        self.assertIn('"1792x1024"', source)
        self.script.write_text(source.replace('"1792x1024"', '"2048x1024"'), encoding="utf-8")
        self.run_generator()
        for eid in ("L007", "D01", "L028", "D02", "S01"):
            with self.subTest(eid=eid):
                self.assertNotEqual(self.items[eid]["prompt_sha256"], baseline[eid])
        self.assertEqual(self.items["F001"]["prompt_sha256"], baseline["F001"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
