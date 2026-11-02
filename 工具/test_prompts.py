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
# C89 拆掉的旧「唯一超200米」表述；这些串一旦回到任何一条提示词里都算违例。
BANNED_UNIQUE_TOWER = ("唯一超过200米", "唯一超过两百米", "唯一超200米",
                       "第二座超两百米塔", "第二座超过200米", "第二座超200米", "唯一368米地标")


class BuildPromptsTests(unittest.TestCase):
    # C91 形态规则在闸门侧另算一份，刻意不 import 生成器常量：那样两边一起改错就判不出红。
    PORTRAIT_SUFFIX = ("塔", "钟楼")
    PORTRAIT_MIN_HEIGHT_M = 150
    PORTRAIT_EXEMPT_IDS = {"L003", "L007", "L022", "L033", "L038"}
    # C92 的档位表与热闹禁词同样在闸门侧独立抄一份：生成器单方面放松时必须由这条测试判红。
    CROWD_BAND = {
        "城市片区": "街道层连续人流、人行道上人距1—3米（俯瞰条不作人物计数，但必须能看出地面有人在走）",
        "标志性建筑": "前景与中景合计15—40人，主体人物组3—6人，至少一组正在做具体的事（搬、聊、等、吃）",
        "功能区": "20—60人，含卸货、排队与上下班对流，底商连续营业、灯箱亮着",
        "居民区": "8—25人，含老人带孩、晾晒、遛狗、下棋、买菜归来；晾晒与盆栽不得堵通道",
        "产业小镇": "6—18人，以生产活动为主，不出现主城式人流",
        "特色村落": "6—18人，以生产活动为主，不出现主城式人流",
    }
    CROWD_BANNED = ("人山人海", "热闹繁华", "繁华喧嚣", "摩肩接踵", "人流如织", "熙熙攘攘")
    # C93：E1 换档＋D4 双层判据在闸门侧另抄一份，刻意不 import 生成器常量。
    # 写实词与近未来词只许出现在负向段，所以判据是把 tail 按负向段起点切成两半分别断言。
    NEG_OPEN = "not a photograph, no photorealistic pore detail"
    STYLE_BANNED = ("photorealistic", "photorealism", "photograph", "hyperrealistic", "dslr", "hdr photo")
    ERA_BANNED = ("flying cars", "flying car", "hologram", "cyberpunk", "humanoid robot",
                  "near-future sci-fi", "autonomous vehicle fleet")
    ERA_NEGATIVES = ("no flying cars", "no holograms", "no humanoid robots", "no cyberpunk",
                     "no near-future sci-fi")
    TAIL_GUARD_CALL = "    assert_affirmative_style(_label, _text)"

    def expected_portrait_ids(self):
        out = set()
        for entry in self.load("城市空间名录.json")["entries"]:
            if entry["type"] != "标志性建筑":
                continue
            tall_tower = (entry["name"].endswith(self.PORTRAIT_SUFFIX)
                          and entry["height_m"] >= self.PORTRAIT_MIN_HEIGHT_M)
            if tall_tower or entry["id"] in self.PORTRAIT_EXEMPT_IDS:
                out.add(entry["id"])
        return out

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

    def run_raw(self):
        """负测用：不预设退出码，返回原始结果供断言。只在临时副本内执行，真实仓库不受影响。"""
        return subprocess.run(
            [sys.executable, "-B", str(self.script)], cwd=self.root,
            capture_output=True, text=True, encoding="utf-8", timeout=60)

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

    def test_all_312_rents_have_complete_units(self):
        self.assertEqual(len(self.items), 312)
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
        towers = self.expected_portrait_ids()
        landmarks = [item for item in self.items.values() if item["id"].startswith("L")]
        self.assertEqual(len(landmarks), 108)
        for item in landmarks:
            with self.subTest(eid=item["id"]):
                portrait = item["id"] in towers
                self.assertEqual(item["size"], "1024x1536" if portrait else "1536x1024")
                self.assertIn("2:3 竖幅" if portrait else "3:2 横幅", item["aspect"])
                self.assertIn("2:3 竖幅" if portrait else "3:2 横幅", self.prompt(item["id"]))
                self.assertNotIn("single-tower", self.prompt(item["id"]))
        self.assertIn("体育场", self.prompt("L028"))
        self.assertIn("Chinese canon sections overrides this line", self.prompt("L028"))

    def test_portrait_rule_is_height_driven_not_a_hand_written_list(self):
        """注入两处相反违例证明竖幅真的跟名录走：132 米的 L089 抬到 160 米须转竖幅，
        352 米的 L067 改名去掉「塔」字须退回横幅。名称在知识库与名录两份里同步改，免得这条测试变成猜生成器读哪一份。"""
        reg = self.load("城市空间名录.json")
        by_id = {e["id"]: e for e in reg["entries"]}
        self.assertEqual(self.items["L089"]["size"], "1536x1024")
        self.assertEqual(self.items["L067"]["size"], "1024x1536")
        by_id["L089"]["height_m"] = 160
        by_id["L067"]["name"] = "澄湖资本中心"
        kb = self.load("AI地点知识库.json")
        for rec in kb:
            if rec["id"] == "L067":
                rec["name"] = "澄湖资本中心"
        self.save("城市空间名录.json", reg)
        self.save("AI地点知识库.json", kb)
        self.run_generator()
        self.assertEqual(self.items["L089"]["size"], "1024x1536")
        self.assertIn("2:3 竖幅，容纳正典塔身与冠部", self.prompt("L089"))
        self.assertEqual(self.items["L067"]["size"], "1536x1024")
        self.assertIn("3:2 横幅", self.prompt("L067"))

    def test_portrait_set_covers_every_300m_tower_and_excludes_short_named_halls(self):
        """竖幅集必须含全部 300 米以上的塔形地标（含全城第一 L066），
        且不得把 150 米以下的场馆、市政与观测类拖进竖幅——除豁免那 5 条。"""
        towers = self.expected_portrait_ids()
        reg = {e["id"]: e for e in self.load("城市空间名录.json")["entries"]}
        for eid in ("L066", "L067", "L082", "L007"):
            self.assertIn(eid, towers)
        # 名称不含「塔」的高层建筑按规则留在横幅，是 C91 认可的边界，不是漏项
        for eid in ("L069", "L085", "L088"):
            self.assertNotIn(eid, towers)
        self.assertEqual(
            towers - self.PORTRAIT_EXEMPT_IDS,
            {e["id"] for e in reg.values()
             if e["type"] == "标志性建筑" and e["name"].endswith(self.PORTRAIT_SUFFIX)
             and e["height_m"] >= self.PORTRAIT_MIN_HEIGHT_M})

    def test_district_and_settlement_aspects_match_pixel_sizes(self):
        for item in self.items.values():
            if item["id"].startswith(("D", "S")):
                with self.subTest(eid=item["id"]):
                    self.assertEqual(item["size"], "1792x1024")
                    self.assertIn("7:4 横幅", item["aspect"])
                    self.assertNotIn("16:9", self.prompt(item["id"]))

    def test_60_public_assets_are_reference_only_without_invented_residential_prices(self):
        public = [price for price in self.prices if price.get("asset_use") == "公共自用"]
        self.assertEqual(len(public), 60)
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
            for section in ("图像与视频取景", "外观与辨识细节", "人群与生活节奏", "锁定项与禁则"):
                with self.subTest(eid=rec["id"], section=section):
                    self.assertIn(rec["sections"][section], self.prompt(rec["id"]))

    def test_every_prompt_carries_its_crowd_band_and_priority(self):
        """C92：312 条都要有【人群与烟火气】行，行内同时承载本条人群段、该类型的缺省档与详档优先句。
        档位表在闸门侧另抄一份，刻意不 import 生成器常量——两边一起改错时这条要能判红。"""
        by_type = {}
        for rec in self.kb:
            line = next((l for l in self.prompt(rec["id"]).splitlines()
                         if l.startswith("【人群与烟火气】")), None)
            self.assertIsNotNone(line, "%s 缺人群行" % rec["id"])
            self.assertIn(rec["sections"]["人群与生活节奏"], line)
            self.assertIn("优先于该缺省档", line)
            self.assertIn("不为凑人数增删人物", line)
            self.assertIn(self.CROWD_BAND[rec["type"]], line)
            for word in self.CROWD_BANNED:
                self.assertNotIn(word, line)
            by_type.setdefault(rec["type"], []).append(rec["id"])
        self.assertEqual(len(by_type), 6)
        self.assertEqual(sum(len(v) for v in by_type.values()), 312)

    def test_manual_stops_treating_crowd_density_as_a_drift_variable(self):
        """手册第 4 节原来把「增加人群」列为致漂移变量，示例A 写「少量」，示例C 只让人物当尺度参照；
        这三处是接线的反向压制，改回旧措辞必须判红。断言取本轮真源句子，不凭印象。"""
        manual = (ROOT / "AI创作使用手册.md").read_text(encoding="utf-8")
        for gone in ("增加人群", "少量停留拍照的人", "作业区人物只作远处尺度参照"):
            self.assertNotIn(gone, manual, "反向压制措辞回来了：" + gone)
        self.assertIn("画面内的人数不属于这里的“变量”", manual)
        self.assertIn("CROWD_BAND_BY_TYPE", manual)
        self.assertIn("按 L007 提示词【人群与烟火气】行给出的地标缺省档", manual)
        self.assertIn("按 S02 提示词【人群与烟火气】行给出的产业小镇缺省档", manual)
        self.assertIn("也不把镇区人流抬成主城街区的密度", manual)

    def test_uncheckable_cheer_words_abort_the_generator(self):
        """负测：详档把「人山人海」一类不可校验的热闹词写进人群、外观或锁定任一段，生成器必须退出
        而不是照抄进提示词；对照组证明未注入时仍出满 312 条。变异验证：把承载行的标签改掉，
        上一条断言的人数档判据必须落空，证明那条测试不是靠残留文本蒙绿。"""
        pristine = (self.data / "AI地点知识库.json").read_text(encoding="utf-8")
        for section, eid in (("人群与生活节奏", "R001"), ("外观与辨识细节", "L007"), ("锁定项与禁则", "D01")):
            (self.data / "AI地点知识库.json").write_text(pristine, encoding="utf-8")
            kb = self.load("AI地点知识库.json")
            next(r for r in kb if r["id"] == eid)["sections"][section] += "现场人山人海。"
            self.save("AI地点知识库.json", kb)
            result = self.run_raw()
            with self.subTest(section=section):
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(eid, result.stderr + result.stdout)
                self.assertIn("不可校验的热闹词", result.stderr + result.stdout)
        (self.data / "AI地点知识库.json").write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(len(self.items), 312)
        source = self.script.read_text(encoding="utf-8")
        self.assertIn('"【人群与烟火气】%s｜画面内人物密度缺省档：%s。%s"', source)
        self.script.write_text(
            source.replace('"【人群与烟火气】%s｜画面内人物密度缺省档：%s。%s"',
                           '"【外观补充】%s｜画面内人物密度缺省档：%s。%s"', 1), encoding="utf-8")
        self.run_generator()
        self.assertEqual([eid for eid in self.items
                          if "【人群与烟火气】" in self.prompt(eid)], [])

    def test_watermark_rule_explicitly_preserves_mandatory_platform_labels(self):
        for eid in self.items:
            with self.subTest(eid=eid):
                text = self.prompt(eid)
                self.assertIn("平台强制AIGC", text)
                self.assertIn("原样保留", text)
                tail = text.split("English tail: ", 1)[1]
                self.assertIn("no third-party or model-generated watermark", tail)
                self.assertIn("preserve mandatory platform AIGC labels", tail)

    def tail_split(self, eid):
        """返回（正向段, 负向段）：正向段是画风与双层与痕迹与招牌句，负向段自 `not a photograph` 起。
        禁词只许在负向段里以否定式出现，所以必须切开判，不能整串断言。"""
        tail = self.prompt(eid).split("English tail: ", 1)[1]
        affirmative, sep, negative = tail.partition(self.NEG_OPEN)
        self.assertTrue(sep, "%s 的 tail 找不到负向段起点" % eid)
        return affirmative, negative

    def test_tail_is_painted_with_both_city_layers_and_an_era_lock(self):
        """C93：312 条 tail 都要落进厚涂档，并同时给出科技层与老城层的实体、痕迹清单与招牌豁免句；
        近未来词只能以否定式出现。旧六条 photorealistic 开头的 tail 必须整体消失。"""
        for rec in self.kb:
            eid = rec["id"]
            with self.subTest(eid=eid):
                affirmative, negative = self.tail_split(eid)
                for word in self.STYLE_BANNED + self.ERA_BANNED:
                    self.assertNotIn(word, affirmative, "%s 正向段含 %s" % (eid, word))
                for word in self.ERA_NEGATIVES:
                    self.assertIn(word, negative, "%s 负向段缺年代锁 %s" % (eid, word))
                self.assertIn("semi-realistic digital painting", affirmative)
                self.assertIn("modern layer (", affirmative)
                self.assertIn("old layer (", affirmative)
                self.assertIn("at least three of", affirmative)
                self.assertIn("blurred non-readable strokes", affirmative)
                self.assertNotIn("true material texture", self.prompt(eid))

    def test_photorealism_or_near_future_word_injected_into_the_affirmative_tail_aborts(self):
        """负测：往 TAIL_BY_TYPE 的正向段塞 photorealistic 或塞 flying cars，生成器必须退出而不是出图；
        对照组证明未注入时仍出满 312 条。变异验证：删掉守卫调用后同样的注入必须变绿——
        说明上一条的红来自守卫，不是别处恰好报错。只在临时副本的脚本里改，真实仓库不受影响。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = '    "标志性建筑": "painted landmark tower'
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在正向 tail 上")
        for injection, expected in (("photorealistic architectural photography, ", "photorealistic"),
                                    ("flying cars overhead, ", "flying cars")):
            self.script.write_text(
                pristine.replace(anchor, '    "标志性建筑": "%s%s' % (injection, anchor.split(': "', 1)[1]), 1),
                encoding="utf-8")
            result = self.run_raw()
            with self.subTest(injection=injection):
                self.assertNotEqual(result.returncode, 0, result.stdout)
                output = result.stderr + result.stdout
                self.assertIn("正向风格段含禁词", output)
                self.assertIn(expected, output)
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(len(self.items), 312)
        self.assertIn("modern layer (", self.tail_split("L007")[0])
        self.assertEqual(pristine.count(self.TAIL_GUARD_CALL), 1)
        self.script.write_text(pristine.replace(self.TAIL_GUARD_CALL, "    pass", 1), encoding="utf-8")
        self.script.write_text(
            self.script.read_text(encoding="utf-8").replace(
                anchor, '    "标志性建筑": "photorealistic architectural photography, painted landmark tower', 1),
            encoding="utf-8")
        result = self.run_raw()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("photorealistic", self.tail_split("L007")[0])
        self.script.write_text(pristine, encoding="utf-8")

    def test_manual_and_charter_put_e1_inside_the_canon_lane(self):
        """4.5：手册第11节那句「不进正典／不改 photorealistic 口径」与总纲的整句禁霓虹是三处反向压制，
        改回旧措辞必须判红。断言取本轮真源句子，不凭印象。"""
        manual = (ROOT / "AI创作使用手册.md").read_text(encoding="utf-8")
        for gone in ("不改 English tail 的 photorealistic 口径", "不进入开图正典队列",
                     "本节图片不得回填", "即退回正典写实档", "## 11. 非正典美术通道"):
            self.assertNotIn(gone, manual, "反向压制措辞回来了：" + gone)
        self.assertIn("C93 起为开图正典口径", manual)
        self.assertIn("STYLE_CORE", manual)
        self.assertIn("NEGATIVE_TAG", manual)
        self.assertIn("era 2013", manual)
        self.assertIn("legible signage glyphs", manual)
        self.assertIn("科技层与老城层是否同框且有物理接触", manual)
        charter = (ROOT / "00-城市总纲.md").read_text(encoding="utf-8")
        self.assertNotIn("或用霓虹和飞行汽车代表现代性", charter)
        self.assertIn("现代性必须有可画的实体", charter)
        self.assertIn("不得用满屏霓虹替代街道生活", charter)
        self.assertIn("天上现代、地上生活", charter)
        self.assertIn("只有玻璃幕墙、只有仿古街", charter)

    def skyline_clause_ok(self, text):
        """C89 判据：旧「唯一超200米」措辞必须全清，新的分档句与「唯一形态」句必须在场。"""
        gone = all(word not in text for word in BANNED_UNIQUE_TOWER)
        return gone and "L066钛心金融主塔458米为全城第一" in text and "只属于L007" in text

    def test_skyline_tier_replaces_the_single_tower_prohibition(self):
        for eid in self.items:
            with self.subTest(eid=eid):
                self.assertTrue(self.skyline_clause_ok(self.prompt(eid)),
                                "仍残留 %s 之一，或缺分档/唯一形态句" % "、".join(BANNED_UNIQUE_TOWER))
        tower = self.prompt("L066")
        self.assertIn("458", tower)
        self.assertIn("106层", tower)
        self.assertIn("第一高尺度关系", tower)

    def test_reinjecting_the_single_tower_clause_makes_the_gate_red(self):
        # 负测：把 C89 拆掉的旧禁则塞回生成器全局段，312 条必须全部判红，不许有一条漏网。
        source = self.script.read_text(encoding="utf-8")
        self.script.write_text(source.replace(
            '"非对称直线斜削冠与细针状天线的组合只属于L007',
            '"L007钛湖之脊368米（含针状天线）是全城唯一超过200米的塔楼；非对称直线斜削冠与细针状天线的组合只属于L007',
            1), encoding="utf-8")
        self.run_generator()
        failed = [eid for eid in self.items if not self.skyline_clause_ok(self.prompt(eid))]
        self.assertEqual(len(failed), len(self.items))
        self.assertIn("唯一超过200米", self.prompt("S01"))

    def test_no_image_cannot_be_accepted_or_count_as_generated(self):
        for eid, status in (("D01", "已验收"), ("L007", "失败")):
            self.items[eid].update(status=status, image_file=None, batch="failed-batch")
        self.save_manifest()
        self.run_generator()
        self.assertEqual(self.manifest["generated"], 0)
        self.assertEqual(self.manifest["pending"], 312)
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
