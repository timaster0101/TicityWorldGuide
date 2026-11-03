# -*- coding: utf-8 -*-
"""只在临时项目副本执行真实生成器；真实输入只读，不复制或改写真实图片/清单。"""
import json
import math
from pathlib import Path
import re
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
    # C98：城市片区 tail 只许给双层接触点，不许替 20 个片区预先决定谁近谁远。
    DISTRICT_DEPTH_WORDS = ("behind old layer", "in front of old layer", "old layer in the foreground")
    DISTRICT_DEPTH_POINTER = "which layer reads near and which reads far follows the Chinese framing section above"
    DISTRICT_CONTACT_EDGE = "sharing one frame with a visible contact edge where the two layers meet"

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

    # C95 的竖幅画框可纳性口径在闸门侧独立抄一份算式，刻意不 import verify_framing：
    # 高度档还会像 C90 那样再抬，取景段一旦点名屋面物件而机位装不下，就必须自陈截断。
    CROWN_WORDS = ("塔顶", "塔冠", "屋面", "屋顶排", "天线", "排汽", "仪器罩")
    CROP_ACKNOWLEDGEMENTS = ("出在画框上沿之外", "装不下")

    def portrait_crown_violations(self, items, kb_by_id, reg_by_id):
        """返回「竖幅条的取景段点名了冠部物件，但按机位距离与焦距装不下全高，且没写明截断」的条目。"""
        violations = []
        for item in items:
            if item["size"] != "1024x1536":
                continue
            seg = kb_by_id[item["id"]]["sections"]["图像与视频取景"]
            cam = re.search(r"[\(（]\s*(-?\d+(?:\.\d+)?)\s*[,，、]\s*(-?\d+(?:\.\d+)?)\s*[\)）]", seg)
            lens = re.search(r"(\d{2,3})\s*毫米", seg)
            eye = re.search(r"离地(\d+(?:\.\d+)?)\s*米", seg)
            height = reg_by_id[item["id"]].get("height_m")
            center = reg_by_id[item["id"]]["center_km"]
            if not (cam and lens and eye) or not height:
                continue  # 旧竖幅条（豁免 5 条）不写机位坐标，属人工判读范围
            named = next((w for w in self.CROWN_WORDS if w in seg), None)
            if named is None or any(a in seg for a in self.CROP_ACKNOWLEDGEMENTS):
                continue
            dist = math.hypot(float(cam.group(1)) - center[0], float(cam.group(2)) - center[1]) * 1000
            elevation = float(eye.group(1))
            needed = math.degrees(math.atan2(elevation, dist) + math.atan2(height - elevation, dist))
            frame = math.degrees(2 * math.atan(18 / float(lens.group(1))))
            if needed > frame:
                violations.append((item["id"], named, round(needed, 1), round(frame, 1)))
        return violations

    def test_vertical_framing_never_promises_a_crown_the_camera_cannot_hold(self):
        """正测：全部竖幅条要么机位装得下全高，要么取景段写明冠部出框。
        违例注入：把 L083 的取景段改回 C95 订正前的写法，同一条判据必须转红。"""
        kb_by_id = {rec["id"]: rec for rec in self.kb}
        reg_by_id = {e["id"]: e for e in self.load("城市空间名录.json")["entries"]}
        self.assertEqual(self.portrait_crown_violations(self.manifest["items"], kb_by_id, reg_by_id), [],
                         "有竖幅条点名了冠部物件却装不下全高，且未写明截断")
        fixed = kb_by_id["L083"]["sections"]["图像与视频取景"]
        self.assertIn("出在画框上沿之外", fixed)
        kb_by_id["L083"]["sections"]["图像与视频取景"] = (
            "相机置东面内街与湖岸步道之间(-3.549,0.658)千米，离地1.6米朝东，32毫米。"
            "前景为内街的行道树与检修井盖围栏，中景是几乎不开洞的基座与南面接收门，"
            "远景为条纹百叶塔身与屋顶排风群。连续8秒沿内街平移两米。")
        self.assertEqual(self.portrait_crown_violations(self.manifest["items"], kb_by_id, reg_by_id),
                         [("L083", "屋顶排", 61.4, 58.7)], "注入的旧写法必须被这条判据判红")

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

    def district_depth_violations(self, affirmative):
        """判据纯函数：命中即 tail 又越权把双层纵深次序写死。"""
        return [w for w in self.DISTRICT_DEPTH_WORDS if w in affirmative]

    def test_district_tail_gives_a_contact_edge_but_leaves_the_depth_order_to_the_canon(self):
        """C98：20 条片区图的双层实体词与接触点须在，近远次序须交还本条中文取景段。
        D03 v01 的深度序颠倒（真源要塔群在中景、灰瓦古城在湖对岸作远景，成图把老街抬到中景、
        塔群推到对岸）来自旧 tail 写死的 behind old layer，不是模型自由发挥。"""
        districts = [rec["id"] for rec in self.kb if rec["type"] == "城市片区"]
        self.assertEqual(len(districts), 20)
        for eid in districts:
            with self.subTest(eid=eid):
                affirmative, _ = self.tail_split(eid)
                self.assertEqual(self.district_depth_violations(affirmative), [], eid)
                self.assertIn(self.DISTRICT_DEPTH_POINTER, affirmative)
                self.assertIn(self.DISTRICT_CONTACT_EDGE, affirmative)
                self.assertIn("modern layer (", affirmative)
                self.assertIn("old layer (", affirmative)

    def test_rehardcoding_the_district_depth_order_is_caught_only_by_the_new_gate(self):
        """违例负测：把 C98 之前的 behind old layer 注回城市片区 tail。既有双层断言必须仍然绿，
        新判据必须命中——这证明该缺陷要靠新判据才抓得住，而不是既有断言恰好漏判。变异对照：
        恢复原文后同一判据归零。注入只改临时副本，真实仓库不受影响。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = "cranes on super-tall construction) and old layer \""
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在城市片区 tail 上")
        self.script.write_text(
            pristine.replace(anchor, "cranes on super-tall construction) behind old layer \"", 1),
            encoding="utf-8")
        self.run_generator()
        affirmative, _ = self.tail_split("D03")
        self.assertIn("modern layer (", affirmative)
        self.assertIn("old layer (", affirmative)
        self.assertEqual(self.district_depth_violations(affirmative), ["behind old layer"])
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        back, _ = self.tail_split("D03")
        self.assertEqual(self.district_depth_violations(back), [])
        self.assertIn(self.DISTRICT_DEPTH_POINTER, back)

    # C99：日面可纳性。算式在闸门侧独立抄一份，刻意不 import 生成器的 sun_frame_phrase——
    # 两边一起改错才判不出红，所以必须各写各的。
    SUN_IN_MARK = "the sun sits inside this frame"
    SUN_OUT_MARK = "outside this frame's"
    SUN_FALLBACK = "natural light as the canon section states"
    # 本轮实测分档：59 条太阳可入画、237 条必须留在画外、16 条时段变体不套默认光算式。
    SUN_BRANCH_COUNTS = {"in": 59, "out": 237, "fallback": 16}

    def focal_of(self, eid):
        rec = [r for r in self.kb if r["id"] == eid][0]
        m = re.search(r"(\d+(?:\.\d+)?)\s*毫米", rec["sections"]["图像与视频取景"])
        return float(m.group(1)) if m else None

    def expected_sun_branch(self, eid):
        item = self.items[eid]
        if item.get("lighting_baseline") == "labeled variant":
            return "fallback"
        rel, focal = item.get("sun_relative_deg"), self.focal_of(eid)
        if rel is None or not focal:
            return "fallback"
        return "in" if abs(rel) <= math.degrees(math.atan(18.0 / focal)) else "out"

    def actual_sun_branch(self, eid):
        text = self.prompt(eid)
        if self.SUN_IN_MARK in text:
            return "in"
        if self.SUN_OUT_MARK in text:
            return "out"
        if self.SUN_FALLBACK in text:
            return "fallback"
        return "none"

    def sun_phrase_violations(self):
        return [(eid, self.expected_sun_branch(eid), self.actual_sun_branch(eid))
                for eid in sorted(self.items) if self.actual_sun_branch(eid) != self.expected_sun_branch(eid)]

    def test_every_prompt_states_whether_the_sun_may_be_in_frame(self):
        """C99：D08／D11／D14／F012／L083 五张成图都把日面画进了画面，而按 36mm 全幅水平半视锥
        atan(18/焦距) 算，这五条的太阳相对方位都在画框之外（只有 D03 的 3° 在内）。旧 tail 只写
        natural light as the canon section states，等于没告模型「侧别」与「可见」是两件事。"""
        violations = self.sun_phrase_violations()
        self.assertEqual(violations, [])
        seen = {}
        for eid in sorted(self.items):
            seen[self.actual_sun_branch(eid)] = seen.get(self.actual_sun_branch(eid), 0) + 1
        self.assertEqual(seen, self.SUN_BRANCH_COUNTS)
        # 抽样核对：本轮实测过的六条各自落在正确分支上
        for eid, branch in (("D03", "in"), ("D08", "out"), ("D11", "out"),
                            ("D14", "out"), ("F012", "out"), ("L083", "out")):
            with self.subTest(eid=eid):
                self.assertEqual(self.actual_sun_branch(eid), branch)
        # 画外条必须同时禁掉日面、落日辉光与镜头眩光，缺一即等于没修
        for eid in sorted(self.items):
            if self.expected_sun_branch(eid) == "out":
                with self.subTest(eid=eid):
                    text = self.prompt(eid)
                    for token in ("keep the sun disc", "setting-sun glow", "lens flare out of the picture"):
                        self.assertIn(token, text, eid)
        # 可纳条同样必须写侧别：L066 v02 的日面落在画面左侧，而该条 rel=+15°、正文写「右前侧掠入」，
        # 旧写法只给 "off the camera axis" 不带左右，等于让模型自己猜一侧。
        for eid in sorted(self.items):
            if self.expected_sun_branch(eid) == "in":
                rel = self.items[eid]["sun_relative_deg"]
                with self.subTest(eid=eid):
                    self.assertIn("degrees to the %s of the camera axis" % ("right" if rel > 0 else "left"),
                                  self.prompt(eid), eid)

    def test_dropping_the_sun_admissibility_phrase_is_caught_by_the_new_gate(self):
        """违例负测：把 D11（rel 75°、半视锥 27.2°）的算式结果退回 C99 之前的静态句，
        新判据必须只给出这一条；画风／双层／人群等既有断言仍为绿，证明该缺陷要靠新判据才抓得住。
        变异对照：恢复原文后同一判据归零。注入只改临时副本，真实仓库不受影响。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = "                     sun_frame_phrase(rel, focal_mm(取景),"
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在 tail 的日面句上")
        # 注入只改 D11 一条的 variant 实参，其余 311 条的调用与实参逐字不变。
        # （早先写成把整段换成三元表达式，会把下一行的 variant 实参挤成元组第二项，
        # 于是 16 条时段变体条一起退算式——那条红是注入自身的错，不是判据抓到的缺陷。）
        self.script.write_text(
            pristine.replace(anchor,
                             '                     sun_frame_phrase(rel, focal_mm(取景), True if eid == "D11" else', 1),
            encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.sun_phrase_violations(), [("D11", "out", "fallback")])
        affirmative, _ = self.tail_split("D11")
        self.assertIn("modern layer (", affirmative)
        self.assertIn("old layer (", affirmative)
        self.assertIn("visible brushwork", affirmative)
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.sun_phrase_violations(), [])
        self.assertEqual(self.actual_sun_branch("D11"), "out")

    # C100：画风锚点必须在投喂串首句。B3 七张跨类型样本 5 张出成照片质感（L066／L083／F012／F039／R009），
    # 只有 7:4 横幅的 S02／S18 保住厚涂；与已定档的 R043 同尺度裁前景人物对比，最先失效的就是笔触。
    # 画风词此前只写在最末的 English tail，而投喂串从【画面定位】起就是一长串写实题材描述，模型按题材定档。
    ANCHOR_MARKS = ("【画风锚点】", "semi-realistic digital painting", "visible brushwork and hand-mixed edges",
                    "painted illustration rather than a snapshot", "describe the subject, not the medium")

    def fed_body(self, eid):
        head = self.prompt(eid).split("## 提示词正文\n", 1)
        self.assertEqual(len(head), 2, eid)
        return head[1].strip()

    def anchor_violations(self):
        out = []
        for eid in sorted(self.items):
            first = self.fed_body(eid).splitlines()[0]
            missing = [m for m in self.ANCHOR_MARKS if m not in first]
            if missing:
                out.append((eid, tuple(missing)))
        return out

    def test_every_prompt_leads_with_the_style_anchor(self):
        """C100：312 条投喂串的首句必须是画风锚点，且排在【画面定位】之前。
        锚点只许写媒介与题材的分工，写实与近未来词仍只许留在负向段——由既有禁词守卫继续管。"""
        self.assertEqual(self.anchor_violations(), [])
        self.assertEqual(len(self.items), 312)
        for eid in ("L066", "F039", "R009", "S18", "D03"):
            with self.subTest(eid=eid):
                body = self.fed_body(eid)
                self.assertEqual(body.index("【画风锚点】"), 0)
                self.assertLess(body.index("【画风锚点】"), body.index("【画面定位】"))
        for word in self.STYLE_BANNED + self.ERA_BANNED:
            with self.subTest(word=word):
                self.assertNotIn(word, self.fed_body("L066").splitlines()[0])

    def test_dropping_the_style_anchor_from_the_first_line_is_caught_by_the_new_gate(self):
        """违例负测：只让 D11 丢掉首句锚点，新判据必须只给出这一条，且 tail 的画风词仍在（证明尾串没被删），
        缺陷是「锚点不在首句」而不是「画风词缺失」。恢复原文后归零。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = "    lines.append(STYLE_ANCHOR)"
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在正文首句那一行")
        self.script.write_text(
            pristine.replace(anchor, '    lines.append(STYLE_ANCHOR if eid != "D11" else "【题材】")', 1),
            encoding="utf-8")
        self.run_generator()
        self.assertEqual([eid for eid, _ in self.anchor_violations()], ["D11"])
        affirmative, _ = self.tail_split("D11")
        self.assertIn("visible brushwork", affirmative)
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.anchor_violations(), [])

    # C101：远景可纳性。B3 的 F039（机位朝北）与 R009（取景段「远景止于凸出的砖楼梯间」）都在远景画出整片
    # 主城天际线，L066 的 v01／v02 把 L007 的斜削冠＋细针天线安到了背景塔上。几何在闸门侧独立重抄一份，
    # 刻意不 import 生成器的 background_phrase——两边一起改错才判不出红。
    FAR_VIEW_RULE = "the far view must contain only what the Chinese framing section names as 远景"
    NAMED_SUPERTALLS = ("L007", "L066")
    # 本轮实测分档：取景段给出可解析机位坐标的 68 条走几何算式（48 条标志性建筑＋20 条城市片区），
    # 其余 244 条（居民区 120／标志性建筑 60／功能区 40／产业小镇 16／特色村落 8）无机位坐标，只走静态句。
    BG_BRANCH_COUNTS = {"computed": 68, "static": 244}

    def camera_of(self, eid):
        seg = [r for r in self.kb if r["id"] == eid][0]["sections"]["图像与视频取景"]
        m = re.search(r'[（(]\s*(-?\d+(?:\.\d+)?)\s*[，,、]\s*(-?\d+(?:\.\d+)?)\s*[）)]', seg)
        return [float(m.group(1)), float(m.group(2))] if m else None

    def expected_bg_sentence(self, eid, sid):
        entry = next(e for e in self.load("城市空间名录.json")["entries"] if e["id"] == sid)
        cam, focal = self.camera_of(eid), self.focal_of(eid)
        facing = self.items[eid]["camera_facing_deg"]
        if cam is None or facing is None or not focal:
            return ("%s %s may appear only if the Chinese framing section names it"
                    % (sid, entry["name"])), "static"
        b = math.degrees(math.atan2(entry["center_km"][0] - cam[0], entry["center_km"][1] - cam[1])) % 360
        rel = (b - facing + 540) % 360 - 180
        half = math.degrees(math.atan(18.0 / focal))
        side = "right" if rel > 0 else "left"
        if abs(rel) <= half:
            return ("%s %s (%d metres) sits %.0f degrees to the %s of this camera, inside the %.0f degree half-angle"
                    % (sid, entry["name"], entry["height_m"], abs(rel), side, half)), "computed"
        return ("%s %s (%d metres) is %.0f degrees to the %s of this camera and outside this frame's %.0f degree "
                "half-angle" % (sid, entry["name"], entry["height_m"], abs(rel), side, half)), "computed"

    def bg_violations(self):
        out = []
        for eid in sorted(self.items):
            text = self.prompt(eid)
            if self.FAR_VIEW_RULE not in text:
                out.append((eid, "远景总则缺失"))
                continue
            for sid in self.NAMED_SUPERTALLS:
                if sid == eid:
                    continue
                want, _ = self.expected_bg_sentence(eid, sid)
                if want not in text:
                    out.append((eid, sid, want))
        return out

    def bg_branch(self, eid):
        return "computed" if "of this camera" in self.far_view_fragment(eid) else "static"

    # C99 的太阳画外句同样含 "half-angle, so"，所以远景分支只能切出远景片段判，不能整条断言。
    def far_view_fragment(self, eid):
        text = self.prompt(eid)
        self.assertIn(self.FAR_VIEW_RULE, text, eid)
        start = text.index(self.FAR_VIEW_RULE)
        end = text.index(", painted material texture", start)
        return text[start:end]

    def test_far_view_names_the_two_supertalls_by_geometry(self):
        """C101：每条提示词都要写清远景只许取景段点名的内容，并对 L007／L066 两根超高层给出可纳性。
        L066 本条算出 L007 偏右 111°、在 24 毫米的 37° 半视锥之外，与原稿取景段手写的「偏右111.5°」一致，
        这是该算式与真源互证的一例。"""
        self.assertEqual(self.bg_violations(), [])
        seen = {}
        for eid in sorted(self.items):
            seen[self.bg_branch(eid)] = seen.get(self.bg_branch(eid), 0) + 1
        self.assertEqual(seen, self.BG_BRANCH_COUNTS)
        for eid, sid, fragment in (("L066", "L007", "is 111 degrees to the right of this camera"),
                                   ("D03", "L066", "sits 0 degrees to the left of this camera"),
                                   ("D03", "L007", "sits 20 degrees to the right of this camera")):
            with self.subTest(eid=eid, sid=sid):
                self.assertIn(fragment, self.prompt(eid))
        # 静态分支不得假装算过角度；算式分支必须真的给出半视锥数值。两条都只在远景片段内判。
        for eid in sorted(self.items):
            with self.subTest(eid=eid):
                fragment = self.far_view_fragment(eid)
                if self.bg_branch(eid) == "static":
                    self.assertNotIn("half-angle", fragment)
                    self.assertIn("may appear only if the Chinese framing section names it", fragment)
                else:
                    self.assertIn("half-angle", fragment)

    def test_faking_the_supertall_admissibility_is_caught_by_the_new_gate(self):
        """违例负测：只把 D03 传给远景算式的朝向转 180°（等于替它挑一个反方向的机位），
        新判据必须只给出 D03 的两根超高层，其余 311 条不受影响；恢复后归零。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = "                     background_phrase(eid, 取景, facing),"
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在 tail 的远景句上")
        self.script.write_text(
            pristine.replace(anchor,
                             '                     background_phrase(eid, 取景, facing if eid != "D03" else (facing + 180) % 360),', 1),
            encoding="utf-8")
        self.run_generator()
        violations = self.bg_violations()
        self.assertEqual(sorted(set(v[0] for v in violations)), ["D03"])
        self.assertEqual(len(violations), 2)
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.bg_violations(), [])

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
