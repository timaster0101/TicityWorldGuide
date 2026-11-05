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

    def test_manual_states_the_three_aspect_tiers_and_hands_the_card_ratio_to_the_spec(self):
        """C104：手册写「为什么是这三档」而不抄第二份尺寸表，卡面比例的唯一出处在《卡面标准样式规范》第七节。
        反向压制：手册重新长出卡面像素数字、或被否决的「统一改 16:9／3:5」措辞回来，都必须判红。
        断言取本轮真源句子，不凭印象。"""
        manual = (ROOT / "AI创作使用手册.md").read_text(encoding="utf-8")
        spec = (ROOT / "设计" / "2026-10-31-卡面标准样式规范.md").read_text(encoding="utf-8")
        for keep in ("三档画幅的分工是一条判据而不是审美偏好",
                     "三档的像素数字只写在`工具/build_prompts.py`的`SIZE_BY_TYPE`与地标竖幅覆盖处，本手册不抄第二份表",
                     "出图通道既不提供16:9也不提供3:5",
                     "卡牌的画幅不在这三档里，唯一出处是《卡面标准样式规范》第七节",
                     "卡牌的画幅与像素档不在本节，比例的唯一出处是《卡面标准样式规范》第七节"):
            self.assertIn(keep, manual, "手册第9／11节的画幅口径丢了：" + keep[:24])
        self.assertNotIn("1020×1360", manual, "手册抄了卡面像素，第二份数字表回来了")
        for gone in ("统一改为16:9", "全部改用16:9", "卡牌改为3:5", "场景图统一16:9"):
            self.assertNotIn(gone, manual, "被 C104 否决的统一画幅措辞回来了：" + gone)
        for keep in ("## 七、卡面尺寸与比例", "3:4 竖版（宽:高＝0.7500），1020×1360 像素",
                     "共 124 张，尺寸全部 1020×1360，无一例偏离", "不提供 16:9 也不提供 3:5",
                     "两套数字各管各的载体，不互相换算"):
            self.assertIn(keep, spec, "卡面规范第七节的口径丢了：" + keep[:24])

    def test_manual_states_the_c122_medium_words_and_the_two_variable_attribution(self):
        """C122：手册第11节的画风段必须把「颜料怎么铺」写成可执行的媒介句（非金属层平滑过渡、无厚涂无干笔、
        皮肤豁免笔触、天空平滑渐变），并把 C105 的单变量归因（措辞管媒介感、画幅管远景可纳性）留在选型依据里——
        否则下一轮又会拿换画幅当改画风。英文tag 单独取代码段判：C105 那两句作为「被撤掉的旧串」允许出现在
        注释里引用，但不许再出现在实际投放的 tag 里。反向压制：厚涂句一回到 tag 或画风段就说明档位被人改回去了。"""
        manual = (ROOT / "AI创作使用手册.md").read_text(encoding="utf-8")
        for keep in ("玻璃、石材、布料、树叶与天空都画成柔和过渡的色面，不做厚涂堆叠、不做干笔边缘",
                     "皮肤干净平滑，既不带笔触也不带毛孔",
                     "天空画成平滑渐变，不铺云朵笔触",
                     "中文段写的是题材不是媒介，媒介感得靠首句的声明撑住",
                     "措辞管媒介感、画幅管远景可纳性",
                     "C105只加媒介强度、不动画幅档位",
                     "人物通道与开图正典仍用同一组媒介词",
                     "C122 起这一问不再看笔触",
                     "尚未裁定」自 C122 起作废"):
            self.assertIn(keep, manual, "手册第11节的 C122 口径丢了：" + keep[:24])
        self.assertNotIn("厚涂出。人物", manual, "手册画风段退回旧写法，媒介句没了")
        for gone in ("用不透明颜料的堆叠笔触与干笔边缘铺每一个面", "颜料保持可读而不是被抹平"):
            self.assertNotIn(gone, manual, "C105 的厚涂媒介句回到手册画风段：" + gone[:24])
        tag_line = [line for line in manual.splitlines() if line.startswith("英文tag：")][0]
        tag = tag_line.split("`")[1]
        self.assertNotIn("realistic proportions, smooth airbrushed skin", tag,
                         "人物特写 tag 退回 C100 的喷枪磨皮写法")
        for keep in ("smoothly blended paint on glass, stone, fabric and foliage with no impasto texture",
                     "clean blended skin", "sky as a smooth blended gradient",
                     "hair in clean clumps with one stylized highlight streak"):
            self.assertIn(keep, tag, "人物特写 tag 没有跟上 C122 的媒介词：" + keep[:32])
        for gone in ("opaque impasto brush strokes and dry-brush edges on skin and fabric",
                     "paint kept readable instead of smoothly blended", "visible brushwork"):
            self.assertNotIn(gone, tag, "人物特写 tag 里 C105 的厚涂句回来了：" + gone[:40])

    def test_manual_checks_skyline_source_as_a_tenth_item(self):
        """C106：手册第10节的交付清单必须有「背景塔形来源」这一项，且第10节后面的复看段把判据数改成十条——
        判据加在真源与 tail 里却不进交付清单，就等于人工复看时没人去看这一项。"""
        manual = (ROOT / "AI创作使用手册.md").read_text(encoding="utf-8")
        for keep in ("背景塔群的形体是否按本正典自己的几何画",
                     "陆家嘴、香港、深圳湾、曼哈顿、迪拜、芝加哥这类可辨认轮廓",
                     "C101 只管远景有没有资格出现，形体来源是另一条",
                     "把既有图的十项判据"):
            self.assertIn(keep, manual, "手册第10节的 C106 判据丢了：" + keep[:20])
        self.assertNotIn("九项判据", manual, "手册还在说九项判据，第十条没进交付清单")

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
        """C93：312 条 tail 都要落进半写实数字绘画档（媒介词的具体档位自 C122 起由 MEDIUM_* 判据管），
        并同时给出科技层与老城层的实体、痕迹清单与招牌豁免句；近未来词只能以否定式出现。
        旧六条 photorealistic 开头的 tail 必须整体消失。"""
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
    # C111：变体豁免按「取景段是否自己把太阳换掉」分档，闸门侧从正典措辞独立推导，
    # 再与生成器手写分档表的结果对拍——分档表漏了一条或某条取景段改了光照，两边就对不上。
    SUN_KEPT_VARIANTS = {"R006", "R015", "R034", "R054", "R063", "R066"}
    SUN_REPLACED_TOKENS = ("不沿用", "不套用", "不套入", "不调用", "而非", "不额外放入")
    SUN_ABSENT_BASELINE_TOKENS = ("夜景", "夜间", "入夜", "清晨", "阴天")
    SUN_LOCK_PREFIX = "本条沿用255°黄昏太阳"
    # C118：水平半视锥的画幅口径在闸门侧独立抄一份——生成器把竖幅的半幅宽从 18 毫米收到 12 毫米，
    # 闸门侧必须自己按画幅重算，两边一起改错才判不出红。竖幅判据复用 C91 的形态规则（PORTRAIT_*）。
    FRAME_HALF_WIDTH_MM = 18.0
    PORTRAIT_FRAME_HALF_WIDTH_MM = 12.0
    # C118 的实测分档：竖幅口径收窄后，L063（24毫米、rel 30°）从「可纳」翻到「画外」，
    # 故 61 条太阳可入画、241 条必须留在画外、10 条取景段自换太阳故仍走静态句。
    SUN_BRANCH_COUNTS = {"in": 61, "out": 241, "fallback": 10}
    # C118：未点名远景塔的桅杆禁令按 C111 的路子复述进段末，凭据名单与句子在闸门侧另抄一份。
    MAST_RECAP_IDS = ("L061", "L083")
    MAST_RECAP_CLAUSE = ("本条远景里凡【取景指令】未点名的塔一律只画体量，屋顶不得起桅杆、天线、细竖杆或任何"
                         "冠部构件；取景段点名的塔才按它写明的形制画")
    # C118：几何可纳的那句 tail 只许给形制，不许给入画许可——旧串 "so it may read in the far view" 回来了要判红。
    # 句内不得有分号：far_view_fragment 的逐塔切片按 "; " 断，句内分号会把形制串切走。
    FAR_ADMIT_ONLY_FORM = ("which makes it geometrically admissible here, but the Chinese framing section stays "
                           "the only thing that can put it in the picture")
    FAR_ADMIT_OLD_WORDING = "so it may read in the far view"

    def frame_half_angle(self, focal, portrait):
        half = self.PORTRAIT_FRAME_HALF_WIDTH_MM if portrait else self.FRAME_HALF_WIDTH_MM
        return math.degrees(math.atan(half / focal))

    def focal_of(self, eid):
        rec = [r for r in self.kb if r["id"] == eid][0]
        m = re.search(r"(\d+(?:\.\d+)?)\s*毫米", rec["sections"]["图像与视频取景"])
        return float(m.group(1)) if m else None

    def is_labeled_variant(self, eid):
        return self.items[eid].get("lighting_baseline") == "labeled variant"

    def variant_replaces_the_sun(self, eid):
        """C111 分档的推导侧：只看取景段有没有写明换掉太阳或本就无日面的基线，不看生成器的分档表。"""
        rec = [r for r in self.kb if r["id"] == eid][0]
        取景 = rec["sections"]["图像与视频取景"]
        return any(t in 取景 for t in self.SUN_REPLACED_TOKENS + self.SUN_ABSENT_BASELINE_TOKENS)

    def expected_sun_branch(self, eid, towers):
        item = self.items[eid]
        if self.is_labeled_variant(eid) and self.variant_replaces_the_sun(eid):
            return "fallback"
        rel, focal = item.get("sun_relative_deg"), self.focal_of(eid)
        if rel is None or not focal:
            return "fallback"
        return "in" if abs(rel) <= self.frame_half_angle(focal, eid in towers) else "out"

    def expected_sun_lock(self, eid, towers):
        """C111 段内复述句的镜像重抄：侧别、度数与半视锥都由闸门侧从名录另算一遍（C118 起按画幅取半幅宽）。"""
        rel, focal = self.items[eid]["sun_relative_deg"], self.focal_of(eid)
        half = self.frame_half_angle(focal, eid in towers)
        return ("太阳相对本条机位偏%s%d°，在%g毫米镜头的±%.1f°水平半视锥之外，"
                "日面、落日辉光与镜头光斑一律不入画，只画取景段所述的光向、受光面与投影"
                % ("左" if rel < 0 else "右", round(abs(rel)), focal, half))

    def sun_lock_violations(self, towers=None):
        """须画外的沿用255°变体条必须带段内复述句，其余 309 条必须不带。"""
        towers = self.expected_portrait_ids() if towers is None else towers
        out = []
        for eid in sorted(self.items):
            want = (self.is_labeled_variant(eid) and self.expected_sun_branch(eid, towers) == "out")
            has = self.SUN_LOCK_PREFIX in self.prompt(eid)
            if want != has:
                out.append((eid, "want" if want else "have"))
            elif want and self.expected_sun_lock(eid, towers) not in self.prompt(eid):
                out.append((eid, "wording"))
        return out

    def actual_sun_branch(self, eid):
        text = self.prompt(eid)
        if self.SUN_IN_MARK in text:
            return "in"
        if self.SUN_OUT_MARK in text:
            return "out"
        if self.SUN_FALLBACK in text:
            return "fallback"
        return "none"

    def sun_phrase_violations(self, towers=None):
        towers = self.expected_portrait_ids() if towers is None else towers
        return [(eid, self.expected_sun_branch(eid, towers), self.actual_sun_branch(eid))
                for eid in sorted(self.items)
                if self.actual_sun_branch(eid) != self.expected_sun_branch(eid, towers)]

    def test_every_prompt_states_whether_the_sun_may_be_in_frame(self):
        """C99：D08／D11／D14／F012／L083 五张成图都把日面画进了画面，而按 36mm 全幅水平半视锥
        atan(18/焦距) 算，这五条的太阳相对方位都在画框之外（只有 D03 的 3° 在内）。旧 tail 只写
        natural light as the canon section states，等于没告模型「侧别」与「可见」是两件事。
        C118 起半视锥按画幅取半幅宽：竖幅 12 毫米、其余 18 毫米。"""
        towers = self.expected_portrait_ids()
        violations = self.sun_phrase_violations(towers)
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
        # C118：竖幅口径收窄唯一翻档的一条——L063 是 24 毫米竖幅、rel 30°，按 18 毫米口径的 36.9° 可纳，
        # 按竖幅 12 毫米口径的 26.6° 就在画外了。这条翻档是本轮改口的全部太阳侧后果，多一条都算扩大。
        with self.subTest(c118="L063"):
            self.assertEqual(self.expected_sun_branch("L063", towers), "out")
            self.assertEqual(self.actual_sun_branch("L063"), "out")
        # C111：分档表与取景段推导必须完全一致，且 R054 这条两版都画日面的串必须有算句
        derived = {eid for eid in self.items
                   if self.is_labeled_variant(eid) and not self.variant_replaces_the_sun(eid)}
        self.assertEqual(derived, self.SUN_KEPT_VARIANTS, "沿用255°的变体分档与取景段措辞对不上")
        for eid in ("R054", "R063", "R066"):
            with self.subTest(eid=eid):
                self.assertEqual(self.actual_sun_branch(eid), "out", eid)
        for eid in ("R006", "R015", "R034"):
            with self.subTest(eid=eid):
                self.assertEqual(self.actual_sun_branch(eid), "in", eid)
        for eid in ("S23", "R092", "L033", "R116"):
            with self.subTest(eid=eid):
                self.assertEqual(self.actual_sun_branch(eid), "fallback", eid)
        # 画外条必须同时禁掉日面、落日辉光与镜头眩光，缺一即等于没修
        for eid in sorted(self.items):
            if self.expected_sun_branch(eid, towers) == "out":
                with self.subTest(eid=eid):
                    text = self.prompt(eid)
                    for token in ("keep the sun disc", "setting-sun glow", "lens flare out of the picture"):
                        self.assertIn(token, text, eid)
        # 可纳条同样必须写侧别：L066 v02 的日面落在画面左侧，而该条 rel=+15°、正文写「右前侧掠入」，
        # 旧写法只给 "off the camera axis" 不带左右，等于让模型自己猜一侧。
        for eid in sorted(self.items):
            if self.expected_sun_branch(eid, towers) == "in":
                rel = self.items[eid]["sun_relative_deg"]
                with self.subTest(eid=eid):
                    self.assertIn("degrees to the %s of the camera axis" % ("right" if rel > 0 else "left"),
                                  self.prompt(eid), eid)
        # C111：沿用255°却算得须画外的变体条，禁令必须复述进本条【锁定与禁则】段末，
        # 且侧别与度数按闸门侧另算的半视锥逐字对上；其余条一律不带这句（可纳的条被套上禁句等于画不出来）。
        self.assertEqual(self.sun_lock_violations(towers), [])
        self.assertEqual(sorted(eid for eid in self.items if self.SUN_LOCK_PREFIX in self.prompt(eid)),
                         ["R054", "R063", "R066"])

    def test_dropping_the_sun_admissibility_phrase_is_caught_by_the_new_gate(self):
        """违例负测：把 D11（rel 75°、半视锥 27.2°）的算式结果退回 C99 之前的静态句，
        新判据必须只给出这一条；画风／双层／人群等既有断言仍为绿，证明该缺陷要靠新判据才抓得住。
        变异对照：恢复原文后同一判据归零。注入只改临时副本，真实仓库不受影响。"""
        towers = self.expected_portrait_ids()
        pristine = self.script.read_text(encoding="utf-8")
        anchor = "                     sun_frame_phrase(rel, focal_mm(取景), portrait,"
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在 tail 的日面句上")
        # 注入只改 D11 一条的 variant 实参，其余 311 条的调用与实参逐字不变。
        # （早先写成把整段换成三元表达式，会把下一行的 variant 实参挤成元组第二项，
        # 于是 16 条时段变体条一起退算式——那条红是注入自身的错，不是判据抓到的缺陷。）
        self.script.write_text(
            pristine.replace(anchor,
                             '                     sun_frame_phrase(rel, focal_mm(取景), portrait,'
                             ' True if eid == "D11" else', 1),
            encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.sun_phrase_violations(towers), [("D11", "out", "fallback")])
        affirmative, _ = self.tail_split("D11")
        self.assertIn("modern layer (", affirmative)
        self.assertIn("old layer (", affirmative)
        self.assertIn("illustrated cityscape rather than a snapshot", affirmative)
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.sun_phrase_violations(towers), [])

    def test_erasing_the_in_body_sun_clause_is_caught_by_the_new_gate(self):
        """违例负测（C111 段内侧）：只把 R054 的段内复述句抹掉——tail 的算句逐字不动，
        所以 C99 那条判据仍然全绿。这证明「日面禁令只写在尾部」这一类缺陷必须靠新判据才抓得住。
        变异对照：恢复原文后两条判据同时归零。注入只改临时副本，真实仓库不受影响。"""
        towers = self.expected_portrait_ids()
        pristine = self.script.read_text(encoding="utf-8")
        anchor = "if abs(_rel) > frame_half_angle(_focal, portrait):"
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在 C111 的段内复述上")
        self.script.write_text(
            pristine.replace(anchor, 'if eid != "R054" and abs(_rel) > frame_half_angle(_focal, portrait):', 1),
            encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.sun_lock_violations(towers), [("R054", "want")])
        # 旧的尾部判据看不见这个缺陷：R054 的 tail 仍是算出来的画外句，311 条逐字未动。
        self.assertEqual(self.actual_sun_branch("R054"), "out")
        self.assertEqual(self.sun_phrase_violations(towers), [])
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.sun_lock_violations(towers), [])

    def test_a_canon_sun_replacement_moves_the_item_out_of_the_computed_branch(self):
        """守卫负测（分档侧·改正典）：给 R034 的取景段补一句「不沿用255°黄昏基准」——
        它就不再沿用默认太阳，而分档表还把它留在算式里，生成器必须非零退出并点名 R034，
        而不是带着与正典矛盾的光照句继续出图。恢复后归零。只改临时副本的正典。"""
        pristine = (self.data / "AI地点知识库.json").read_text(encoding="utf-8")
        rec = [r for r in self.kb if r["id"] == "R034"][0]
        self.assertIn("255°黄昏基准光在此变体里只作对照", rec["sections"]["图像与视频取景"])
        rec["sections"]["图像与视频取景"] = rec["sections"]["图像与视频取景"] + "本变体不沿用255°黄昏基准。"
        self.save("AI地点知识库.json", self.kb)
        result = self.run_raw()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("R034", result.stderr + result.stdout)
        self.assertIn("换光凭据", result.stderr + result.stdout)
        (self.data / "AI地点知识库.json").write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.sun_lock_violations(self.expected_portrait_ids()), [])

    def test_an_unlisted_variant_without_a_replacement_marker_aborts_the_generator(self):
        """守卫负测（分档侧·漏条）：把 S23 的「夜景变体」改成「晴夜变体」，它就既不在分档表里、
        取景段又没有换光凭据——255° 那句「若改拍黄昏」于是可能被读成实际光照，
        生成器必须拒绝自动判定并要求人工补表，而不是静默给它套上或摘掉算句。"""
        pristine = (self.data / "AI地点知识库.json").read_text(encoding="utf-8")
        rec = [r for r in self.kb if r["id"] == "S23"][0]
        self.assertIn("夜景变体，相机在公共讲解院南侧", rec["sections"]["图像与视频取景"])
        rec["sections"]["图像与视频取景"] = rec["sections"]["图像与视频取景"].replace(
            "夜景变体，相机在公共讲解院南侧", "晴夜变体，相机在公共讲解院南侧", 1)
        self.save("AI地点知识库.json", self.kb)
        result = self.run_raw()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("S23", result.stderr + result.stdout)
        self.assertIn("没有换光凭据", result.stderr + result.stdout)
        (self.data / "AI地点知识库.json").write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.actual_sun_branch("S23"), "fallback")
        self.assertEqual(self.actual_sun_branch("D11"), "out")

    # C100：画风锚点必须在投喂串首句。B3 七张跨类型样本 5 张出成照片质感（L066／L083／F012／F039／R009），
    # 只有 7:4 横幅的 S02／S18 保住厚涂；与已定档的 R043 同尺度裁前景人物对比，最先失效的就是笔触。
    # 画风词此前只写在最末的 English tail，而投喂串从【画面定位】起就是一长串写实题材描述，模型按题材定档。
    # C122：本层只钉「锚点在不在首句、有没有声明媒介与题材分工」这四条结构标记。原第五条
    # visible brushwork and hand-mixed edges 是措辞层的厚涂要求，随皮肤豁免一并撤销，改由下面
    # MEDIUM_ANCHOR_MARKS 按档钉——分层不变，只是措辞层换档时不必再动结构层。
    ANCHOR_MARKS = ("【画风锚点】", "semi-realistic digital painting",
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
        self.assertIn("illustrated cityscape rather than a snapshot", affirmative)
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.anchor_violations(), [])

    # C105 曾把媒介强度钉成「不透明厚涂铺每个面」；C122（2026-11-04）按三轮单变量诊断把它翻到另一头：
    # 皮肤豁免笔触、非金属层降到探底档。诊断链与归因见 工具/build_prompts.py 的 C122 注释块与本节手册第11节。
    # 判据仍两侧钉：首句（媒介感唯一的实际生效位）与 English tail 正向段（模型读的第二遍）。
    # 分层要点：结构层 ANCHOR_MARKS 管「有没有声明媒介」，本层管「声明的是哪一档媒介」，换档只动本层。
    MEDIUM_ANCHOR_MARKS = ("smoothly blended painted areas", "no visible impasto", "skin is clean and blended")
    MEDIUM_CORE_MARKS = ("smoothly blended paint on glass", "no impasto texture",
                         "sky as a smooth blended gradient")
    # 被 C122 否证的上一档措辞：厚涂铺每个面、颜料保持可读、云笔触铺天——这三句一旦回到 tail，
    # 说明有人把油画感加回来了；本档的画面里不许再出现「颜料可读优先于平滑过渡」这句话。
    MEDIUM_ROLLBACK_PHRASES = ("opaque impasto paint layers", "kept readable instead of smoothly blended",
                               "sky laid in with visible cloud strokes")
    # C100／C105 时代的锚点原文，只用于违例负测（把 D11 降回旧措辞）。
    ANCHOR_C100 = ("【画风锚点】medium is a semi-realistic digital painting: visible brushwork and hand-mixed edges on "
                   "every surface, including faces, glass, stone, fabric and foliage; painted illustration rather than "
                   "a snapshot; the Chinese sections below describe the subject, not the medium")
    ANCHOR_C105 = ("【画风锚点】medium is a semi-realistic digital painting: opaque impasto brush strokes and dry-brush "
                   "edges build every surface, with visible brushwork and hand-mixed edges on faces, glass, stone, "
                   "fabric and foliage, and the paint kept readable instead of smoothly blended; painted illustration "
                   "rather than a snapshot; the Chinese sections below describe the subject, not the medium")
    CORE_C100 = ('STYLE_CORE = ("semi-realistic digital painting, visible brushwork and hand-mixed edges, painted surfaces, "\n'
                 '              "soft airbrushed gradient sky, warm late-autumn palette, illustrated cityscape rather than a snapshot")')
    CORE_C105 = ('STYLE_CORE = ("semi-realistic digital painting, visible brushwork and hand-mixed edges, opaque impasto paint layers "\n'
                 '              "with dry-brush edges, painted surfaces, sky laid in with visible cloud strokes rather than a smooth "\n'
                 '              "blended gradient, warm late-autumn palette, illustrated cityscape rather than a snapshot")')
    CORE_C122 = ('STYLE_CORE = ("semi-realistic digital painting, smoothly blended paint on glass, stone, fabric and foliage "\n'
                 '              "with no impasto texture and no dry-brush edges, clean blended skin, sky as a smooth blended gradient, "\n'
                 '              "warm late-autumn palette, illustrated cityscape rather than a snapshot")')

    def medium_violations(self):
        out = []
        for eid in sorted(self.items):
            first = self.fed_body(eid).splitlines()[0]
            affirm, _ = self.tail_split(eid)
            missing = [m for m in self.MEDIUM_ANCHOR_MARKS if m not in first]
            missing += [m for m in self.MEDIUM_CORE_MARKS if m not in affirm]
            missing += ["旧措辞回来了:" + r for r in self.MEDIUM_ROLLBACK_PHRASES if r in affirm]
            if missing:
                out.append((eid, tuple(missing)))
        return out

    def test_every_prompt_carries_the_c122_medium_words(self):
        """C122：312 条的首句与 tail 正向段都要带本档的媒介词（非金属层平滑过渡／无厚涂／皮肤不带笔触／天空平滑渐变），
        且被本档否证的上一档措辞（厚涂铺每个面、颜料可读优先、云笔触铺天）不得在 tail 里以任何形式回来。"""
        self.assertEqual(self.medium_violations(), [])
        for eid in ("L083", "L066", "F039", "R009", "S02", "S18", "D03"):
            with self.subTest(eid=eid):
                first = self.fed_body(eid).splitlines()[0]
                for mark in self.MEDIUM_ANCHOR_MARKS:
                    self.assertIn(mark, first)
        for word in self.STYLE_BANNED + self.ERA_BANNED:
            with self.subTest(word=word):
                self.assertNotIn(word, self.fed_body("L083").splitlines()[0])

    def test_downgrading_one_anchor_to_the_c105_wording_is_caught(self):
        """违例负测（首句侧）：只把 D11 的首句降回 C105 锚点（厚涂铺每个面、皮肤须带笔触那一档）。
        旧锚点仍满足 C122 结构层的四条标记，所以锚点判据必须全绿、媒介判据必须只报 D11 且报的是三个媒介词缺失——
        证明媒介层判据严格强于结构层，而不是同一件事重复一遍。恢复后归零。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = "    lines.append(STYLE_ANCHOR)"
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在正文首句那一行")
        downgrade = ('    lines.append(STYLE_ANCHOR if eid != "D11" else %r)' % self.ANCHOR_C105)
        self.script.write_text(pristine.replace(anchor, downgrade, 1), encoding="utf-8")
        self.run_generator()
        violations = self.medium_violations()
        self.assertEqual([eid for eid, _ in violations], ["D11"])
        self.assertEqual(violations[0][1], tuple(self.MEDIUM_ANCHOR_MARKS))
        self.assertEqual(self.anchor_violations(), [])
        affirm, _ = self.tail_split("D11")
        for mark in self.MEDIUM_CORE_MARKS:
            self.assertIn(mark, affirm)
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.medium_violations(), [])

    def test_rolling_the_tail_core_back_to_the_c105_phrase_is_caught(self):
        """违例负测（tail 侧）：把 STYLE_CORE 整体降回 C105 的三行写法（含 opaque impasto paint layers 与
        sky laid in with visible cloud strokes）。312 条必须全报，缺失项只有 tail 侧三个媒介词与两句「旧措辞回来了」，
        首句侧不许被牵连——证明这一判据管的是 tail，不与首句判据混成一个变量。恢复后归零。"""
        pristine = self.script.read_text(encoding="utf-8")
        self.assertEqual(pristine.count(self.CORE_C122), 1, "注入用的 STYLE_CORE 原文与生成器不一致")
        self.script.write_text(pristine.replace(self.CORE_C122, self.CORE_C105, 1), encoding="utf-8")
        self.run_generator()
        violations = self.medium_violations()
        self.assertEqual([eid for eid, _ in violations], sorted(self.items))
        expected = tuple(self.MEDIUM_CORE_MARKS) + tuple(
            "旧措辞回来了:" + r for r in self.MEDIUM_ROLLBACK_PHRASES
            if r in self.CORE_C105 and r not in self.CORE_C122)
        self.assertEqual({v[1] for v in violations}, {expected})
        self.assertEqual(self.anchor_violations(), [])
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.medium_violations(), [])

    # C101：远景可纳性。B3 的 F039（机位朝北）与 R009（取景段「远景止于凸出的砖楼梯间」）都在远景画出整片
    # 主城天际线，L066 的 v01／v02 把 L007 的斜削冠＋细针天线安到了背景塔上。几何在闸门侧独立重抄一份，
    # 刻意不 import 生成器的 background_phrase——两边一起改错才判不出红。
    # C123：授权宾语从「取景段点名为『远景』的内容」换成不被主体构件占位的背景天际线口径。
    # 闸门只抄总则前缀（与生成器同串），旧术语回到任何一条都判红——第9批 48 条里 44 条的
    # `远景为…` 宾语是主体自身构件，旧总则因此对背景天际线空转，这是它被换掉的唯一理由。
    FAR_VIEW_RULE = "the background skyline beyond the main subject may contain only the distant objects the Chinese"
    FAR_VIEW_OLD_WORDING = "the far view must contain only what the Chinese framing section names as 远景"
    GLOBAL_CLUSTER_WITHHELD = ("成簇只是正典事实、不构成本条画面的授权，背景天际线只许画【取景指令】逐一点名的独立远景对象，"
                               "未点名者一律不入画")
    GLOBAL_TERM_WITHDRAWN = "「远景」二字常指主体自身的远处构件"
    NAMED_SUPERTALLS = ("L007", "L066")
    # 本轮实测分档：取景段给出可解析机位坐标的 68 条走几何算式（48 条标志性建筑＋20 条城市片区），
    # 其余 244 条（居民区 120／标志性建筑 60／功能区 40／产业小镇 16／特色村落 8）无机位坐标，只走静态句。
    BG_BRANCH_COUNTS = {"computed": 68, "static": 244}

    def camera_of(self, eid):
        seg = [r for r in self.kb if r["id"] == eid][0]["sections"]["图像与视频取景"]
        m = re.search(r'[（(]\s*(-?\d+(?:\.\d+)?)\s*[，,、]\s*(-?\d+(?:\.\d+)?)\s*[）)]', seg)
        return [float(m.group(1)), float(m.group(2))] if m else None

    def expected_bg_sentence(self, eid, sid, towers):
        entry = next(e for e in self.load("城市空间名录.json")["entries"] if e["id"] == sid)
        cam, focal = self.camera_of(eid), self.focal_of(eid)
        facing = self.items[eid]["camera_facing_deg"]
        if cam is None or facing is None or not focal:
            return ("%s %s may appear only if the Chinese framing section names it"
                    % (sid, entry["name"])), "static"
        b = math.degrees(math.atan2(entry["center_km"][0] - cam[0], entry["center_km"][1] - cam[1])) % 360
        rel = (b - facing + 540) % 360 - 180
        half = self.frame_half_angle(focal, eid in towers)
        side = "right" if rel > 0 else "left"
        if abs(rel) <= half:
            # C118：框内那句只许可形制、不许可入画，镜像串把这段优先次序一起钉住。
            return ("%s %s (%d metres) sits %.0f degrees to the %s of this camera, inside the %.0f degree "
                    "half-angle, %s" % (sid, entry["name"], entry["height_m"], abs(rel), side, half,
                                        self.FAR_ADMIT_ONLY_FORM), "computed")
        return ("%s %s (%d metres) is %.0f degrees to the %s of this camera and outside this frame's %.0f degree "
                "half-angle" % (sid, entry["name"], entry["height_m"], abs(rel), side, half)), "computed"

    def bg_violations(self, towers=None):
        towers = self.expected_portrait_ids() if towers is None else towers
        out = []
        for eid in sorted(self.items):
            text = self.prompt(eid)
            if self.FAR_VIEW_RULE not in text:
                out.append((eid, "远景总则缺失"))
                continue
            for sid in self.NAMED_SUPERTALLS:
                if sid == eid:
                    continue
                want, _ = self.expected_bg_sentence(eid, sid, towers)
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
        L066 本条算出 L007 偏右 111°、在竖幅 24 毫米的 27° 半视锥之外（C118 前是 37°），
        与原稿取景段手写的「偏右111.5°」一致，这是该算式与真源互证的一例。"""
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
        # C118：竖幅半幅宽收窄后，这 10 组「塔×条目」从框内翻到框外（其余算式条不动）。
        # 逐组钉住是为了让「再收一档口径」必须留下新的读数，而不是悄悄多关几根塔。
        # 判据是「新口径算在框外、但按旧的 18 毫米半幅宽还算得进」——只有这种组合才是被这次收窄关掉的。
        towers = self.expected_portrait_ids()
        flipped = {("L070", "L007"), ("L071", "L007"), ("L080", "L066"), ("L084", "L007"), ("L084", "L066"),
                   ("L087", "L066"), ("L090", "L007"), ("L090", "L066"), ("L092", "L007"), ("L099", "L066")}
        got = {(eid, sid) for eid in self.items for sid in self.NAMED_SUPERTALLS
               if self.form_expectation(eid, sid, towers) == "outside"
               and abs(self.bg_offset(eid, sid, towers)) <= self.frame_half_angle(self.focal_of(eid), False)}
        self.assertEqual(got, flipped, "竖幅收窄翻到框外的十组对不上：多一组就是偷偷多关几根塔，少一组就是没收窄")
        # C118：框内那句只许可形制、不许可入画；旧的入许可措辞回到任何一条都算违例。
        for eid in sorted(self.items):
            with self.subTest(no_entry_permission=eid):
                self.assertNotIn(self.FAR_ADMIT_OLD_WORDING, self.prompt(eid))
        for eid, sid in (("D03", "L007"), ("D06", "L066"), ("L083", "L007")):
            with self.subTest(admissible=eid, sid=sid):
                self.assertIn(self.FAR_ADMIT_ONLY_FORM, self.supertall_chunk(eid, sid))

    def bg_offset(self, eid, sid, towers):
        """给翻档钉子用的独立重算：塔相对本条机位的方位偏移（度，带符号）。"""
        entry = next(e for e in self.load("城市空间名录.json")["entries"] if e["id"] == sid)
        cam, facing = self.camera_of(eid), self.items[eid]["camera_facing_deg"]
        bearing = math.degrees(math.atan2(entry["center_km"][0] - cam[0], entry["center_km"][1] - cam[1])) % 360
        return (bearing - facing + 540) % 360 - 180

    def test_faking_the_supertall_admissibility_is_caught_by_the_new_gate(self):
        """违例负测：只把 D03 传给远景算式的朝向转 180°（等于替它挑一个反方向的机位），
        新判据必须只给出 D03 的两根超高层，其余 311 条不受影响；恢复后归零。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = "                     background_phrase(eid, 取景, facing, portrait),"
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在 tail 的远景句上")
        self.script.write_text(
            pristine.replace(anchor,
                             '                     background_phrase(eid, 取景, facing if eid != "D03" else (facing + 180) % 360, portrait),', 1),
            encoding="utf-8")
        self.run_generator()
        violations = self.bg_violations()
        self.assertEqual(sorted(set(v[0] for v in violations)), ["D03"])
        self.assertEqual(len(violations), 2)
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.bg_violations(), [])

    # C123：第9批 20/48 条把未点名的超高层画进背景，根因不是少写一条禁令，而是同一串里既禁点名、又宣布有簇，
    # 且旧总则的授权宾语「远景」在 48 条里 44 条被主体自身构件占位（L088 是整墙斜拉索上段、L100 是内凹小平台）。
    # 中文与闸门两侧各抄一份，刻意不 import 生成器常量。
    def global_view_violations(self):
        out = []
        for eid in sorted(self.items):
            text = self.prompt(eid)
            line = next((l for l in text.splitlines() if l.startswith("【全局硬设定】")), "")
            for mark in (self.GLOBAL_CLUSTER_WITHHELD, self.GLOBAL_TERM_WITHDRAWN):
                if mark not in line:
                    out.append((eid, mark))
            if self.FAR_VIEW_OLD_WORDING in text:
                out.append((eid, "旧的远景授权术语回流"))
        return out

    def test_the_cluster_clause_no_longer_authorises_a_background_skyline(self):
        """C123：312 条的中文【全局硬设定】都要读到「成簇只是正典事实、不构成本条画面的授权」与
        「「远景」二字常指主体自身的远处构件」两句，tail 的新总则逐条在位，旧术语一条不许残留。"""
        self.assertEqual(self.global_view_violations(), [])
        self.assertEqual(self.bg_violations(), [])
        for eid in ("L088", "L100", "L061", "D03", "S18"):
            with self.subTest(eid=eid):
                self.assertIn(self.GLOBAL_CLUSTER_WITHHELD, self.prompt(eid))

    def test_reverting_the_background_authorization_wording_is_caught_by_the_new_gate(self):
        """违例负测：只把 tail 总则换回旧术语，其余逐字不动——新判据必须 312 条全报「旧的远景授权术语回流」，
        且 C101 的远景判据同时 312 条报总则缺失，证明旧宾语一回来就同时废掉总则与依赖它的逐塔片段。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = 'FAR_VIEW_RULE = ("the background skyline beyond the main subject may contain only the distant objects the Chinese "'
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在 C123 的新总则上")
        self.script.write_text(
            pristine.replace(anchor,
                             'FAR_VIEW_RULE = ("the far view must contain only what the Chinese framing section names as 远景; '
                             'do not add a distant "', 1), encoding="utf-8")
        self.run_generator()
        violations = self.global_view_violations()
        self.assertEqual(sorted({eid for eid, _ in violations}), sorted(self.items))
        self.assertEqual({reason for _, reason in violations}, {"旧的远景授权术语回流"})
        self.assertEqual(sorted({eid for eid, _ in self.bg_violations()}), sorted(self.items))
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.global_view_violations(), [])
        self.assertEqual(self.bg_violations(), [])

    def test_dropping_the_withheld_authorisation_from_the_global_clause_is_caught(self):
        """违例负测：只删中文全局段的「成簇不授权」句（tail 逐字不动），新判据必须 312 条全报且只报这一句缺失；
        C101 的远景算式与 C106 的形体来源判据全绿，证明本轮改的是「收回邀请」，不是再加一条禁令。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = "；成簇只是正典事实、不构成本条画面的授权，背景天际线只许画【取景指令】逐一点名的独立远景对象，未点名者一律不入画"
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在 C123 的成簇收回授权句上")
        self.script.write_text(pristine.replace(anchor, "", 1), encoding="utf-8")
        self.run_generator()
        violations = self.global_view_violations()
        self.assertEqual(sorted({eid for eid, _ in violations}), sorted(self.items))
        self.assertEqual({reason for _, reason in violations}, {self.GLOBAL_CLUSTER_WITHHELD})
        self.assertEqual(self.bg_violations(), [])
        self.assertEqual(self.skyline_violations(), [])
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.global_view_violations(), [])

    # C106：远景「有没有资格出现」由 C101 管，「出现的那几栋长什么样」是另一条。L083 的 C105 换档重出 v05
    # 侧别算对（两座超高层落在左侧），轮廓却是陆家嘴三件套的现成剪影——模型被允许画远景时默认去抄现实天际线。
    # 两侧刻意镜像重抄，不 import 生成器常量。C109 给这条补了剪影兜底：没点名形制的远景塔只许画体量。
    SKYLINE_SOURCE_RULE = ("background towers are composed from this canon's own geometry (straight shafts, louver "
                           "bands and the flat or stepped crowns the Chinese sections name); any far tower this line "
                           "does not name a crown form for stays a plain mass with a flat or stepped top and no "
                           "invented crown, antenna or aperture; do not trace a real city's skyline and do not "
                           "borrow a real supertall's crown, twist or aperture")
    SKYLINE_NEGATIVE = ("no recognizable real-world skyline (Lujiazui, Hong Kong, Shenzhen Bay, Manhattan, Dubai, "
                        "Chicago) and no crown, twist or aperture copied from a real supertall")

    def skyline_violations(self):
        out = []
        for eid in sorted(self.items):
            text = self.prompt(eid)
            affirmative, negative = self.tail_split(eid)
            missing = []
            if self.SKYLINE_SOURCE_RULE not in affirmative:
                missing.append("正向段缺形体来源句")
            if self.SKYLINE_NEGATIVE not in negative:
                missing.append("负向段缺现实天际线否定式")
            if missing:
                out.append((eid, tuple(missing)))
        return out

    def test_far_view_towers_are_told_to_come_from_the_canon_not_a_real_skyline(self):
        """C106：312 条都要给出「背景塔按本正典自己的几何画」的正向句（且落在远景片段内，
        与 C101 的总则同段），并在负向段给出现实天际线否定式；正向段不许出现现实城市名的肯定式。"""
        self.assertEqual(self.skyline_violations(), [])
        for eid in ("L083", "L066", "D03", "F012", "R009", "S02", "S18"):
            with self.subTest(eid=eid):
                self.assertIn(self.SKYLINE_SOURCE_RULE, self.far_view_fragment(eid))
        for city in ("Lujiazui", "Manhattan", "Dubai"):
            with self.subTest(city=city):
                affirmative, negative = self.tail_split("L083")
                self.assertNotIn(city, affirmative)
                self.assertIn(city, negative)

    def test_dropping_the_skyline_source_rule_from_one_prompt_is_caught(self):
        """违例负测：只让 D11 的远景片段丢掉形体来源句（负向段的否定式仍在），
        新判据必须只给出 D11 且报的是正向段缺失；C101 的远景判据不受牵连，证明两条管的是不同的事。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = "    parts = [FAR_VIEW_RULE, SKYLINE_SOURCE_RULE]"
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在远景句装配处")
        self.script.write_text(
            pristine.replace(anchor,
                             "    parts = [FAR_VIEW_RULE] if eid == \"D11\" else [FAR_VIEW_RULE, SKYLINE_SOURCE_RULE]", 1),
            encoding="utf-8")
        self.run_generator()
        violations = self.skyline_violations()
        self.assertEqual([eid for eid, _ in violations], ["D11"])
        self.assertEqual(violations[0][1], ("正向段缺形体来源句",))
        self.assertEqual(self.bg_violations(), [])
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.skyline_violations(), [])

    def test_losing_the_real_skyline_negative_is_caught_on_all_312(self):
        """违例负测（负向侧）：把 NEGATIVE_TAG 里的现实天际线否定式抹掉，312 条必须全报且只报负向缺失——
        正向句不受牵连，证明这一判据的正向与负向是两处独立钉。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = '"no neon-drenched street replacing street life; no recognizable real-world skyline (Lujiazui, "'
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在 NEGATIVE_TAG 的天际线否定式上")
        self.script.write_text(
            pristine.replace(anchor, '"no neon-drenched street replacing street life; not a skyline (Lujiazui, "', 1),
            encoding="utf-8")
        self.run_generator()
        violations = self.skyline_violations()
        self.assertEqual([eid for eid, _ in violations], sorted(self.items))
        self.assertEqual({v[1] for v in violations}, {("负向段缺现实天际线否定式",)})
        self.assertEqual(self.bg_violations(), [])
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.skyline_violations(), [])

    # C107：时段变体条的三条失手（R053 v01 无招牌实体、R086 v01 右下角悬浮字母形笔画、
    # S23 v01／v02 连续两版画出银河带）都在同一处——判据写在 GLOBAL 尾部，被题材压倒。
    # 复述进本条【锁定与禁则】段末的串外试投把 R053 v02／R086 v02 救回，故落进生成器，只挂 16 条变体。
    # 镜像重抄，不 import 生成器常量。
    VARIANT_LOCK_MARKS = ("本条是显式标注的时段变体", "门牌、店招或公告灯箱须有实体在画面中可见",
                          "无字母形签名、台标或悬浮笔画", "夜景不得画出银河带、密集星场或长曝光星轨")

    def variant_ids(self):
        return sorted(eid for eid in self.items if self.items[eid].get("lighting_baseline") == "labeled variant")

    def variant_lock_violations(self):
        out = []
        for eid in sorted(self.items):
            body = self.prompt(eid).split("【全局硬设定】", 1)[0]
            lock = body.split("【锁定与禁则】", 1)
            lock = lock[1] if len(lock) == 2 else ""
            missing = [m for m in self.VARIANT_LOCK_MARKS if m not in lock]
            want = eid in self.variant_ids()
            if want and missing:
                out.append((eid, tuple(missing)))
            if not want and not missing:
                out.append((eid, ("默认光条不该带变体复述句",)))
        return out

    def test_time_variant_lock_restates_the_three_clauses_global_tail_loses(self):
        """C107：16 条时段变体的锁定段末必须复述三条易失手判据，296 条默认光条必须逐字不带——
        带错范围等于把 296 条的摘要绑定一起洗掉。"""
        self.assertEqual(len(self.variant_ids()), 16)
        self.assertEqual(self.variant_lock_violations(), [])
        for eid in ("R038", "R053", "R086", "S23", "L033", "R092"):
            with self.subTest(eid=eid):
                self.assertEqual([v for v, _ in self.variant_lock_violations()], [])
                self.assertIn("本条是显式标注的时段变体", self.prompt(eid))
        for eid in ("L007", "D03", "F012"):
            with self.subTest(untouched=eid):
                self.assertNotIn("本条是显式标注的时段变体", self.prompt(eid))

    def test_dropping_the_variant_restatement_from_one_entry_is_caught(self):
        """违例负测：只让 R053 一条退回未复述状态，判据必须只报 R053 且报的是三条全缺；
        C99 的太阳分支与 C106 的天际线判据不受牵连，证明本轮补的是段内位置而非新判据。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = '    if rec.get("lighting_baseline") == "labeled variant":\n        锁定 ='
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在变体锁定段复述处")
        self.script.write_text(
            pristine.replace(anchor,
                             '    if rec.get("lighting_baseline") == "labeled variant" and eid != "R053":\n        锁定 =',
                             1),
            encoding="utf-8")
        self.run_generator()
        violations = self.variant_lock_violations()
        self.assertEqual([eid for eid, _ in violations], ["R053"])
        self.assertEqual(len(violations[0][1]), len(self.VARIANT_LOCK_MARKS))
        self.assertEqual(self.sun_phrase_violations(self.expected_portrait_ids()), [])
        self.assertEqual(self.skyline_violations(), [])
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.variant_lock_violations(), [])

    # C118：第12轮 L083／L061 两条投放 2/2 栽在同一处——背景／未点名远景塔的屋顶凭空起桅杆，
    # 而这条禁令当时只住在 tail 的 SKYLINE_SOURCE_RULE 里。C111 已经量过「只写在尾部的禁令压不住模型」，
    # 于是按同一路子把禁令复述进凭据两条的【锁定与禁则】段末。名单与句子在闸门侧另抄一份，不 import。
    def mast_recap_violations(self):
        out = []
        for eid in sorted(self.items):
            has = self.MAST_RECAP_CLAUSE in self.prompt(eid)
            want = eid in self.MAST_RECAP_IDS
            if want != has:
                out.append((eid, "want" if want else "have"))
        return out

    def test_the_far_view_mast_ban_is_restated_in_body_for_the_two_read_items(self):
        """C118：桅杆禁则必须落在段内（【锁定与禁则】行），且只落在有读数凭据的两条上——
        铺到全部竖幅就是无证据扩大；tail 的剪影兜底句同时保留，段内是复述不是替换。"""
        self.assertEqual(self.mast_recap_violations(), [])
        for eid in self.MAST_RECAP_IDS:
            with self.subTest(eid=eid):
                line = next(l for l in self.prompt(eid).splitlines() if l.startswith("【锁定与禁则】"))
                self.assertIn(self.MAST_RECAP_CLAUSE, line)
                self.assertIn("no invented crown, antenna or aperture", self.prompt(eid))
        self.assertEqual(sorted(eid for eid in self.items if self.MAST_RECAP_CLAUSE in self.prompt(eid)),
                         sorted(self.MAST_RECAP_IDS))

    def test_dropping_the_mast_restatement_is_caught_by_the_new_gate(self):
        """违例负测：只让 L061 一条退回未复述状态——tail 的剪影兜底句逐字不动，
        C106 的天际线判据与 C101 的远景算式仍然全绿，证明这一缺陷必须靠新判据才抓得住。
        变异对照：恢复原文后同一判据归零。注入只改临时副本，真实仓库不受影响。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = "    if eid in MAST_RECAP_IDS:"
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在 C118 的段内复述上")
        self.script.write_text(
            pristine.replace(anchor, '    if eid in MAST_RECAP_IDS and eid != "L061":', 1), encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.mast_recap_violations(), [("L061", "want")])
        self.assertEqual(self.skyline_violations(), [])
        self.assertEqual(self.bg_violations(), [])
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.mast_recap_violations(), [])

    def test_a_mast_recap_id_that_no_longer_qualifies_aborts_the_generator(self):
        """守卫负测（两个方向）：把 L083 改名到不掉出竖幅规则以外的名字，名单与画幅口径脱节，生成器必须退出；
        把同一条禁则写进 L061 的原稿锁定段，段内复述就成了重复，生成器同样必须退出。恢复后归零。"""
        pristine = (self.data / "AI地点知识库.json").read_text(encoding="utf-8")
        kb = self.load("AI地点知识库.json")
        next(r for r in kb if r["id"] == "L083")["name"] = "数岸算力中心"
        self.save("AI地点知识库.json", kb)
        result = self.run_raw()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("已不是竖幅条", result.stderr + result.stdout)
        (self.data / "AI地点知识库.json").write_text(pristine, encoding="utf-8")
        kb = self.load("AI地点知识库.json")
        rec = next(r for r in kb if r["id"] == "L061")
        rec["sections"]["锁定项与禁则"] += self.MAST_RECAP_CLAUSE
        self.save("AI地点知识库.json", kb)
        result = self.run_raw()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("已自写远景桅杆禁令", result.stderr + result.stdout)
        self.assertIn("L061", result.stderr + result.stdout)
        (self.data / "AI地点知识库.json").write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.mast_recap_violations(), [])

    # C118 的第二处判据：竖幅的水平半视锥按 12 毫米半幅宽算。tail 里那个度数是判据本身，
    # 所以闸门侧把打印值抠出来与自己另算的半角对拍——生成器单方面把竖幅退回 18 毫米口径必须判红。
    SUN_OUT_HALF = re.compile(r"the sun is \d+ degrees to the (?:left|right) of the camera axis and "
                              r"outside this frame's (\d+) degree half-angle")
    SUN_IN_HALF = re.compile(r"inside the (\d+) degree half-angle\), low and backlit")

    def sun_half_angle_violations(self, towers):
        out = []
        for eid in sorted(self.items):
            if self.expected_sun_branch(eid, towers) == "fallback":
                continue
            m = self.SUN_OUT_HALF.search(self.prompt(eid)) or self.SUN_IN_HALF.search(self.prompt(eid))
            if not m:
                out.append((eid, "算式句里读不到半角度数"))
                continue
            want = round(self.frame_half_angle(self.focal_of(eid), eid in towers))
            if int(m.group(1)) != want:
                out.append((eid, int(m.group(1)), want))
        return out

    def test_the_printed_half_angle_follows_the_frame_aspect(self):
        """C118：竖幅与横幅各按自己的半幅宽打印半视锥。竖幅 32 毫米必须是 21°（不是 29°）、
        24 毫米必须是 27°（不是 37°）；横幅同焦距仍按 18 毫米口径——只许动竖幅这一个变量。"""
        towers = self.expected_portrait_ids()
        self.assertEqual(self.sun_half_angle_violations(towers), [])
        with self.subTest(portrait="32mm 竖幅"):
            self.assertAlmostEqual(self.frame_half_angle(32.0, True), 20.6, places=1)
            self.assertAlmostEqual(self.frame_half_angle(32.0, False), 29.4, places=1)
        with self.subTest(portrait="24mm 竖幅"):
            self.assertAlmostEqual(self.frame_half_angle(24.0, True), 26.6, places=1)
            self.assertAlmostEqual(self.frame_half_angle(24.0, False), 36.9, places=1)
        # 竖幅与横幅各挑一条实测：L083（32毫米竖幅）与 D06（35毫米横幅）打印值必须分属两个口径
        self.assertIn("outside this frame's 21 degree half-angle", self.prompt("L083"))
        self.assertIn("inside the 27 degree half-angle", self.prompt("D06"))

    def test_portrait_prompts_rolled_back_to_the_wide_half_angle_are_caught(self):
        """违例负测：只把竖幅的半幅宽从 12 毫米退回 18 毫米（生成器常量单点），
        新判据必须报出竖幅算式条、且一条横幅条都不许被牵连——横幅口径本轮没动。
        变异对照：恢复后归零。注入只改临时副本，真实仓库不受影响。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = "PORTRAIT_FRAME_HALF_WIDTH_MM = 12.0"
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在 C118 的竖幅半幅宽上")
        self.script.write_text(pristine.replace(anchor, "PORTRAIT_FRAME_HALF_WIDTH_MM = 18.0", 1), encoding="utf-8")
        self.run_generator()
        towers = self.expected_portrait_ids()
        violations = self.sun_half_angle_violations(towers)
        self.assertTrue(violations, "竖幅退回横幅口径必须被这条判据判红")
        self.assertTrue(set(v[0] for v in violations) <= towers, "非竖幅条被横幅口径的注入牵连了")
        self.assertIn("L083", {v[0] for v in violations})
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.sun_half_angle_violations(self.expected_portrait_ids()), [])

    # C108：雨后批三条（R015 v01 落点约(1250,1009)、R034 v02、R054 v01）与夜光批 R086 v01 都塌在右下角
    # 地面的字母形笔画簇，而 tail 原有的 no third-party or model-generated watermark, logo or signature
    # 管的是画外水印与台标。R015 的单变量实验：同一条串只加一句 nothing written on the ground or pavement
    # in any corner，v02 同一落点只剩湿石高光——故把该句落进 NEGATIVE_TAG，312 条全带。镜像重抄，不 import。
    GROUND_MARKS_NEG = ("nothing written on the ground or pavement in any corner; no letter-shaped signature "
                        "cluster, monogram or floating glyph strokes on street surfaces, kerbs or in the four "
                        "corners of the frame")

    def ground_mark_violations(self):
        out = []
        for eid in sorted(self.items):
            affirmative, negative = self.tail_split(eid)
            missing = []
            if self.GROUND_MARKS_NEG not in negative:
                missing.append("负向段缺地面字形否定式")
            if self.GROUND_MARKS_NEG in affirmative:
                missing.append("正向段混入地面否定式")
            if missing:
                out.append((eid, tuple(missing)))
        return out

    def test_ground_and_four_corners_get_an_explicit_letterform_negative(self):
        """C108：312 条的负向段都要带地面与四角的字母形否定式，且只许出现在负向段；
        招牌实体句必须照旧落在正向段——负向扩到墙面或店招会把 D3／C93 要求的商业层一起否掉。"""
        self.assertEqual(self.ground_mark_violations(), [])
        for eid in ("R015", "R034", "R054", "R086", "S23", "L007", "D03", "S02"):
            with self.subTest(eid=eid):
                affirmative, negative = self.tail_split(eid)
                self.assertIn(self.GROUND_MARKS_NEG, negative)
                self.assertNotIn(self.GROUND_MARKS_NEG, affirmative)
                self.assertIn("shop signboards, banners, lampboxes and door plates must exist along the street",
                              affirmative)
                self.assertNotIn("kerbs", affirmative)

    def test_dropping_the_ground_mark_negative_is_caught_on_all_312(self):
        """违例负测：把 NEGATIVE_TAG 末尾的地面否定式摘掉，312 条必须全报且只报负向缺失——
        C106 的天际线否定式、C107 的变体段内复述与 C101 的远景判据都不受牵连，
        证明这三条各管一处，删任一处不会被另一处兜住。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = '                "a real supertall; " + GROUND_MARKS_NEG)'
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在 NEGATIVE_TAG 的地面否定式拼接处")
        self.script.write_text(pristine.replace(anchor, '                "a real supertall")', 1), encoding="utf-8")
        self.run_generator()
        violations = self.ground_mark_violations()
        self.assertEqual([eid for eid, _ in violations], sorted(self.items))
        self.assertEqual({v[1] for v in violations}, {("负向段缺地面字形否定式",)})
        self.assertEqual(self.skyline_violations(), [])
        self.assertEqual(self.variant_lock_violations(), [])
        self.assertEqual(self.bg_violations(), [])
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.ground_mark_violations(), [])

    def test_the_ground_mark_negative_must_stay_out_of_the_affirmative_tail(self):
        """违例负测（位置侧）：把该句从负向段挪到正向段（tail 模板里排在 NEGATIVE_TAG 之前），
        必须同时报「正向段混入」与「负向段缺」——位置与存在是两件事，只钉存在会放过挪位。"""
        pristine = self.script.read_text(encoding="utf-8")
        drop = '                "a real supertall; " + GROUND_MARKS_NEG)'
        move = 'STREET_TRACES, SIGNAGE_RULE, NEGATIVE_TAG))'
        self.assertEqual(pristine.count(drop), 1, "注入锚点没落在 NEGATIVE_TAG 的地面否定式拼接处")
        self.assertEqual(pristine.count(move), 1, "注入锚点没落在 tail 模板的正向装配处")
        # 挪位走 STREET_TRACES 那个 %s 的拼接，不新增参数——多塞一个参数会让 tail 模板
        # 格式化直接 TypeError、生成器退出，测出的是「串长不对」而不是「位置不对」。
        self.script.write_text(
            pristine.replace(drop, '                "a real supertall")', 1)
            .replace(move, 'STREET_TRACES + GROUND_MARKS_NEG, SIGNAGE_RULE, NEGATIVE_TAG))', 1),
            encoding="utf-8")
        self.run_generator()
        violations = self.ground_mark_violations()
        self.assertEqual([eid for eid, _ in violations], sorted(self.items))
        self.assertEqual({v[1] for v in violations},
                         {("负向段缺地面字形否定式", "正向段混入地面否定式")})
        self.assertEqual(self.skyline_violations(), [])
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.ground_mark_violations(), [])

    # C109：C106 只管到「形体从哪来」，L083 的 v06／v07 仍各塌一处——v07 把 L007 画成平顶＋居中细针。
    # 「按本正典自己的几何画」是泛指，读不出「这一根具体是什么冠」，所以点名句要带上该塔自己的形制串。
    # 形制串在闸门侧镜像重抄，中文括注取自各地标自己的【外观与辨识细节】与【锁定项与禁则】。
    SUPERTALL_FORM = {
        "L007": ("a deep blue-grey straight shaft closed by an asymmetric straight-cut sloped crown whose high "
                 "side carries a slender needle antenna (非对称直线斜削冠＋细针状天线), and this crown belongs to "
                 "L007 alone"),
        "L066": ("a straight shaft whose section has small cut corners at the four corners and whose roof carries "
                 "no crown antenna at all (四角小切角轮廓、禁止加塔冠天线)"),
    }
    # 注入锚点另存一份「源码版式」：形制串在生成器里是跨行隐式拼接，拼好的整串在源文件中并不连续，
    # count 只能按源文件的字面行来数——与 CORE_C105 同一手法。
    SUPERTALL_FORM_SRC = {
        "L007": ('             "a deep blue-grey straight shaft closed by an asymmetric straight-cut sloped crown whose high side "\n'
                 '             "carries a slender needle antenna (非对称直线斜削冠＋细针状天线), and this crown belongs to L007 alone"'),
        "L066": ('             "a straight shaft whose section has small cut corners at the four corners and whose roof carries no "\n'
                 '             "crown antenna at all (四角小切角轮廓、禁止加塔冠天线)"'),
    }
    FORM_PLACEHOLDER = '             "a plain shaft with a top the framing section never names"'
    # C110：科技层核对串分两类词——具名设施词要有承载体，表层材质词不作核对项。
    TECH_CARRIER_WORDS = ("玻璃幕墙", "城市轨道", "站厅", "闸机", "地下环道", "管廊", "数据中心", "实验室",
                          "光伏", "大巴", "充电", "围挡", "吊装", "换乘", "枢纽")
    TECH_SURFACE_WORDS = ("LED媒体立面", "光纤到楼箱", "屋顶通信设备")

    def form_expectation(self, eid, sid, towers):
        """独立重算可纳性：static＝取景段没给可解析机位，inside＝落在半视锥内，outside＝在框外。
        只有前两种该给形制；框外那条给了形制反而是在邀请画它。半视锥按画幅取半幅宽（C118）。"""
        entry = next(e for e in self.load("城市空间名录.json")["entries"] if e["id"] == sid)
        cam, focal = self.camera_of(eid), self.focal_of(eid)
        facing = self.items[eid]["camera_facing_deg"]
        if cam is None or facing is None or not focal:
            return "static"
        bearing = math.degrees(math.atan2(entry["center_km"][0] - cam[0], entry["center_km"][1] - cam[1])) % 360
        rel = (bearing - facing + 540) % 360 - 180
        return "inside" if abs(rel) <= self.frame_half_angle(focal, eid in towers) else "outside"

    def supertall_chunk(self, eid, sid):
        for chunk in self.far_view_fragment(eid).split("; "):
            if chunk.startswith(sid + " "):
                return chunk
        return ""

    def form_violations(self, towers=None):
        towers = self.expected_portrait_ids() if towers is None else towers
        out = []
        for eid in sorted(self.items):
            for sid in self.NAMED_SUPERTALLS:
                if sid == eid:
                    continue
                state = self.form_expectation(eid, sid, towers)
                chunk = self.supertall_chunk(eid, sid)
                if state == "outside":
                    if self.SUPERTALL_FORM[sid] in chunk:
                        out.append((eid, sid, "框外条给了形制"))
                elif self.SUPERTALL_FORM[sid] not in chunk:
                    out.append((eid, sid, "%s分支缺该塔形制点名" % state))
        return out

    def test_named_far_view_supertalls_are_painted_with_their_own_canon_form(self):
        """C109：静态分支与框内分支的点名句都要带该塔自己的形制，框外分支一律不给；两条同时点名时形制不许互换
        （L007 的斜削冠＋细针全城唯一，安到 L066 上就是穿帮）；未点名形制的远景塔走剪影兜底句。"""
        self.assertEqual(self.form_violations(), [])
        towers = self.expected_portrait_ids()
        states = {self.form_expectation(eid, sid, towers)
                  for eid in self.items for sid in self.NAMED_SUPERTALLS if sid != eid}
        self.assertEqual(states, {"static", "inside", "outside"})
        for eid, sid in (("L083", "L007"), ("L083", "L066"), ("D03", "L066"),
                         ("R009", "L007"), ("S02", "L066")):
            with self.subTest(eid=eid, sid=sid):
                self.assertIn(self.SUPERTALL_FORM[sid], self.supertall_chunk(eid, sid))
        self.assertNotIn(self.SUPERTALL_FORM["L007"], self.supertall_chunk("L066", "L007"))
        self.assertNotIn(self.SUPERTALL_FORM["L066"], self.supertall_chunk("L083", "L007"))
        self.assertNotIn(self.SUPERTALL_FORM["L007"], self.supertall_chunk("L083", "L066"))
        self.assertIn("stays a plain mass with a flat or stepped top", self.far_view_fragment("L083"))

    def test_dropping_the_l007_form_is_caught_only_where_l007_is_nameable(self):
        """违例负测：只把 L007 的形制串换成中性占位词，判据必须恰好报「该条本该给 L007 形制」的那些条目；
        L066 的形制、C106 来源句与 C101 可纳性都不受牵连，证明形制是逐塔各钉、不是整段兜住。"""
        towers = self.expected_portrait_ids()
        pristine = self.script.read_text(encoding="utf-8")
        self.assertEqual(pristine.count(self.SUPERTALL_FORM_SRC["L007"]), 1, "注入锚点没落在 L007 的形制串上")
        self.script.write_text(pristine.replace(self.SUPERTALL_FORM_SRC["L007"], self.FORM_PLACEHOLDER, 1),
                               encoding="utf-8")
        self.run_generator()
        violations = self.form_violations()
        expected = sorted(eid for eid in self.items
                          if eid != "L007" and self.form_expectation(eid, "L007", towers) != "outside")
        self.assertEqual(sorted(set(eid for eid, _, _ in violations)), expected)
        self.assertEqual(sorted(set(sid for _, sid, _ in violations)), ["L007"])
        self.assertEqual(self.skyline_violations(), [])
        self.assertEqual(self.bg_violations(), [])
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.form_violations(), [])

    def test_swapping_the_two_crown_forms_is_caught_by_the_per_tower_pin(self):
        """违例负测（交叉侧）：把 L007 与 L066 的形制串整段互换——两句都在，逐条「有没有形制」判不出红，
        必须靠「该塔的点名句里带该塔的形制」这条邻接判据抓住，且 L083（两根同时框内）首当其冲。"""
        pristine = self.script.read_text(encoding="utf-8")
        for sid in self.NAMED_SUPERTALLS:
            self.assertEqual(pristine.count(self.SUPERTALL_FORM_SRC[sid]), 1, sid + " 的形制串源码锚点不唯一")
        swapped = (pristine.replace(self.SUPERTALL_FORM_SRC["L007"], "@@SENTINEL@@", 1)
                   .replace(self.SUPERTALL_FORM_SRC["L066"], self.SUPERTALL_FORM_SRC["L007"], 1)
                   .replace("@@SENTINEL@@", self.SUPERTALL_FORM_SRC["L066"], 1))
        self.script.write_text(swapped, encoding="utf-8")
        self.run_generator()
        violations = self.form_violations()
        self.assertIn(("L083", "L007", "inside分支缺该塔形制点名"), violations)
        self.assertIn(("L083", "L066", "inside分支缺该塔形制点名"), violations)
        self.assertTrue(violations)
        self.assertEqual(self.skyline_violations(), [])
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.form_violations(), [])

    def test_a_crown_form_that_no_longer_matches_the_canon_aborts_the_generator(self):
        """守卫负测：把 L007 正文里所有「非对称直线斜削冠」改成「平顶冠」，SUPERTALL_FORM 的中文出处就对不上原稿，
        生成器必须非零退出并点名 L007——原稿改了形制而形制串没跟着改，不许带着旧形制继续出图；
        对照组证明恢复后仍出满 312 条。出处按整条正文判（真改原稿时两处措辞会一起变），所以违例也整条抹。"""
        pristine = (self.data / "AI地点知识库.json").read_text(encoding="utf-8")
        kb = self.load("AI地点知识库.json")
        rec = next(r for r in kb if r["id"] == "L007")
        holders = sorted(k for k, v in rec["sections"].items() if "非对称直线斜削冠" in v)
        self.assertEqual(holders, ["关联与地方性", "锁定项与禁则"])
        for key in holders:
            rec["sections"][key] = rec["sections"][key].replace("非对称直线斜削冠", "平顶冠")
        self.save("AI地点知识库.json", kb)
        result = self.run_raw()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("远景形制点名的正典出处对不上", result.stderr + result.stdout)
        self.assertIn("L007", result.stderr + result.stdout)
        (self.data / "AI地点知识库.json").write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(len(self.items), 312)

    def test_the_tech_checklist_only_names_facility_words_with_a_canon_carrier(self):
        """C110：开图清单的核对句只列有承载体的具名设施词，逐词能在 312 条正文里找到具名条目；
        表层材质词写明不作核对项；「轻轨」「机场专线」「塔吊与在建超高层」这三个 0 承载体的旧词
        不得再出现在核对串或任何一条【全局硬设定】里。"""
        md = (self.data / "开图清单.md").read_text(encoding="utf-8")
        bodies = ["".join((rec.get("sections") or {}).values()) for rec in self.kb]
        for word in self.TECH_CARRIER_WORDS:
            with self.subTest(word=word):
                self.assertIn(word, md)
                self.assertTrue(any(word in body for body in bodies), word + " 在 312 条正文里无承载体")
        for word in self.TECH_SURFACE_WORDS:
            self.assertIn(word, md)
        self.assertIn("不要求名录承载体", md)
        for gone in ("轻轨", "机场专线", "塔吊与在建超高层"):
            self.assertNotIn(gone, md)
            hits = [eid for eid in sorted(self.items) if gone in self.prompt(eid).split("English tail:")[0]]
            self.assertEqual(hits, [], gone + " 仍挂在【全局硬设定】里")

    def test_a_carrierless_facility_word_in_the_checklist_aborts_the_generator(self):
        """守卫负测：把「轻轨」塞回核对词表，312 条正文 0 命中，生成器必须非零退出并点名「轻轨」——
        判据要求画一个正典里不存在的地点时，宁可不出图。"""
        pristine = self.script.read_text(encoding="utf-8")
        anchor = 'TECH_CARRIER_WORDS = ("玻璃幕墙", "城市轨道",'
        self.assertEqual(pristine.count(anchor), 1, "注入锚点没落在核对词表中")
        self.script.write_text(pristine.replace(anchor, 'TECH_CARRIER_WORDS = ("玻璃幕墙", "轻轨", "城市轨道",', 1),
                               encoding="utf-8")
        result = self.run_raw()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("无承载体", result.stderr + result.stdout)
        self.assertIn("轻轨", result.stderr + result.stdout)
        self.script.write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(len(self.items), 312)

    def test_erasing_a_carrier_from_the_canon_aborts_the_generator(self):
        """守卫负测（承载侧）：把 L037 正文里的「城市轨道」抹掉——它是该词在全名录的唯一承载体，
        抹掉后核对词表就悬空，生成器必须非零退出并点名「城市轨道」；恢复后归零。
        这条与上一条各管一侧：一条改词表，一条改正典。"""
        pristine = (self.data / "AI地点知识库.json").read_text(encoding="utf-8")
        carriers = [r for r in self.kb if "城市轨道" in "".join((r.get("sections") or {}).values())]
        self.assertEqual([r["id"] for r in carriers], ["L037"], "承载体唯一性前提变了，先重数再改这条")
        kb = self.load("AI地点知识库.json")
        rec = next(r for r in kb if r["id"] == "L037")
        rec["sections"] = {k: v.replace("城市轨道", "铁路") for k, v in rec["sections"].items()}
        self.save("AI地点知识库.json", kb)
        result = self.run_raw()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("城市轨道", result.stderr + result.stdout)
        self.assertIn("无承载体", result.stderr + result.stdout)
        (self.data / "AI地点知识库.json").write_text(pristine, encoding="utf-8")
        self.run_generator()
        self.assertEqual(self.form_violations(), [])

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


class RulingC122MediumGrade(unittest.TestCase):
    """C122 的裁定文本是这一档唯一的完整出处：换档理由、五臂地板读数、干净CG的新判废地位与回退口径都在里面。
    只改 build_prompts 的三处媒介串而不在裁定记录留痕，下一轮就没人知道为什么皮肤不带笔触、也不知道旧串还在闸门里。
    这里钉的是话术与读数本身——档位数字被改回旧读数就说明记录没跟着本轮换档重写。"""

    def test_c122_records_the_glide_to_smooth_blend(self):
        rows = json.loads((ROOT / "数据" / "设定裁定记录.json").read_text(encoding="utf-8"))
        by_id = {r["编号"]: r for r in rows}
        self.assertIn("C122", by_id)
        self.assertEqual(set(by_id["C122"]), {"编号", "裁定", "原因", "影响"})
        for keep in ("皮肤豁免笔触，非金属表面降到探底档（极轻档）",
                     "画感由柔和的手调过渡、勾形与理想化五官承担",
                     "结构层 ANCHOR_MARKS",
                     "MEDIUM_ROLLBACK_PHRASES 三条",
                     "prompts 312／files 312",
                     "干净CG渲染从C122起是新的判废项",
                     "已交付的 264 张图按旧厚涂串出",
                     "计数钉 121→122"):
            self.assertIn(keep, by_id["C122"]["裁定"] + by_id["C122"]["原因"] + by_id["C122"]["影响"],
                          "C122 裁定丢了关键句：" + keep[:24])
        # 极轻档的两条地板读数（塔整图与人物脸部窗口）是「这是措辞地板」的唯一证据，钉死数字防止记录被改软。
        for reading in ("0.000414", "0.000346"):
            self.assertIn(reading, by_id["C122"]["原因"], "C122 原因里的极轻档地板读数丢了：" + reading)
        self.assertIn("脚本不得代签", by_id["C122"]["影响"])


class RulingC123C124BackgroundAndFloor(unittest.TestCase):
    """C123／C124 的裁定文本是这两处口径的唯一完整出处：一条讲「成簇不授权＋旧术语为何空转」，
    一条讲「层数为什么退出判废栏」。下一轮若要改回，必须先在这两条记录上留下新的读数，
    所以这里把措辞、量化凭据与「不触发 docx 重导」的边界一起钉住。"""

    def test_c123_records_the_withheld_background_authorisation(self):
        rows = json.loads((ROOT / "数据" / "设定裁定记录.json").read_text(encoding="utf-8"))
        by_id = {r["编号"]: r for r in rows}
        self.assertIn("C123", by_id)
        self.assertEqual(set(by_id["C123"]), {"编号", "裁定", "原因", "影响"})
        body = by_id["C123"]["裁定"] + by_id["C123"]["原因"] + by_id["C123"]["影响"]
        for keep in ("the background skyline beyond the main subject may contain only the distant objects",
                     "成簇只是正典事实、不构成本条画面的授权",
                     "44 条的 `【取景指令】远景为…` 宾语是主体自身的构件",
                     "逐字存在于 312/312 条",
                     "`prompt_sha256` 实测 312 变、0 未变",
                     "MAST_RECAP_CLAUSE",
                     "不触发 docx 重导",
                     "计数钉 122→124"):
            self.assertIn(keep, body, "C123 裁定丢了关键句：" + keep[:24])

    def test_c124_records_the_floor_count_demotion_to_a_note(self):
        rows = json.loads((ROOT / "数据" / "设定裁定记录.json").read_text(encoding="utf-8"))
        by_id = {r["编号"]: r for r in rows}
        self.assertIn("C124", by_id)
        self.assertEqual(set(by_id["C124"]), {"编号", "裁定", "原因", "影响"})
        body = by_id["C124"]["裁定"] + by_id["C124"]["原因"] + by_id["C124"]["影响"]
        for keep in ("只记备注、不单独判废",
                     "实测 101/312 条带 `锁定N层M米`",
                     "English tail 里 `floors` 出现 0 次",
                     "9/48 条因层数量级判废",
                     "并集 22、交集 7",
                     "只有 L097 失去唯一判废理由",
                     "另立裁定"):
            self.assertIn(keep, body, "C124 裁定丢了关键句：" + keep[:24])
        # 判废力度只降层数：高度与冠部两句必须仍在记录里，否则下一轮会把整栏一起放松。
        for hold in ("高度与冠部形态同名录真值一致即过关", "把 L007 的斜削冠＋针状天线安到别的塔上即判废"):
            self.assertIn(hold, by_id["C124"]["裁定"], "C124 把不该降的力度也降了：" + hold[:20])


class RulingC125SilhouetteBoundary(unittest.TestCase):
    """C125 把「未点名背景体量」按能否读出专属形制记号分两档：带记号者仍判废、平头与剪影者记备注。
    这一条只许动判据侧——分档渗进画面串就会让 312 条 prompt_sha256 再变一次档，属跨批次基准变化，
    所以这里同时钉住「判据有分档」与「提示词零变化」两面。"""

    MARKED = ("未点名体量上出现非对称斜削冠、细针状天线、桅杆或斜拉索上段、冠部开洞、扭转塔身任一记号即判废")
    SILHOUETTE = "只读得出平头板楼、阶梯退台或雾中无冠部细节的剪影时记备注、不单独判废"

    def test_c125_records_the_two_tier_boundary(self):
        rows = json.loads((ROOT / "数据" / "设定裁定记录.json").read_text(encoding="utf-8"))
        by_id = {r["编号"]: r for r in rows}
        self.assertIn("C125", by_id)
        self.assertEqual(set(by_id["C125"]), {"编号", "裁定", "原因", "影响"})
        body = by_id["C125"]["裁定"] + by_id["C125"]["原因"] + by_id["C125"]["影响"]
        for keep in ("0/19", "11/19", "L061／L064／L066／L068／L071／L077／L079／L082／L084／L091／L096",
                     "§31.5 当时写的 15 含未落进备注的目视面",
                     "不牵连 `prompt_sha256`",
                     "手册是 compile_book 的六个根 md 输入之一",
                     "第10次 Word 目视重签",
                     "撤销本条分档"):
            self.assertIn(keep, body, "C125 裁定丢了关键句：" + keep[:24])
        for hold in ("非对称斜削冠", "C106", "L007 冠部挪用"):
            self.assertIn(hold, by_id["C125"]["裁定"] + by_id["C125"]["影响"],
                          "C125 把不该降的力度也降了：" + hold)

    def test_the_rejection_clause_in_the_manifest_carries_both_tiers(self):
        md = (ROOT / "数据" / "开图清单.md").read_text(encoding="utf-8")
        self.assertIn(self.MARKED, md)
        self.assertIn(self.SILHOUETTE, md)
        self.assertIn("（C125）", md)

    def test_c125_moves_no_prompt_digest_and_writes_nothing_into_the_prompt_bodies(self):
        snapshot = json.loads((ROOT / "工具" / "reinject_2026_11_05" / "prompt_digests_c123.json")
                               .read_text(encoding="utf-8"))["items"]
        manifest = json.loads((ROOT / "数据" / "开图清单.json").read_text(encoding="utf-8"))["items"]
        self.assertEqual(len(manifest), 312)
        moved = [m["id"] for m in manifest if m["prompt_sha256"] != snapshot[m["id"]]["after"]]
        self.assertEqual(moved, [], "C125 动了画面串，变更 %d 条：%s" % (len(moved), moved[:5]))
        leaks = []
        for path in sorted((ROOT / "数据" / "开图提示词").glob("*.txt")):
            text = path.read_text(encoding="utf-8")
            if self.MARKED in text or self.SILHOUETTE in text:
                leaks.append(path.name)
        self.assertEqual(leaks, [], "两档判据措辞渗进提示词正文：%s" % leaks[:3])


class RulingC126RodAndCraneTiering(unittest.TestCase):
    """C126 把 C125 记号档里唯一在两档之间反复的两项读法钉成可量的数：屋面细杆按杆高对可见塔身
    十二分之一分档，塔吊按街面施工层与天际线远景带分档。与 C125 同属判据侧改动，
    一面钉「三处落点都带阈值与分档」，一面钉「一条画面串都没动」。"""

    ROD = ("屋面上的细竖杆按 C126 量着判而不是看着判：发丝状直杆且无横档、无格构、无灯球、无斜削面、无开洞，"
           "杆高不超过同屏可见塔身的十二分之一，读作避雷带或旗杆类构件、记备注")
    CRANE = "塔吊同样按 C126 分工：立于街面施工围挡层、不与任何未点名远景塔冠绑定的吊机读作生活痕迹"

    def test_c126_records_the_threshold_and_the_crane_split(self):
        rows = json.loads((ROOT / "数据" / "设定裁定记录.json").read_text(encoding="utf-8"))
        by_id = {r["编号"]: r for r in rows}
        self.assertIn("C126", by_id)
        self.assertEqual(set(by_id["C126"]), {"编号", "裁定", "原因", "影响"})
        body = by_id["C126"]["裁定"] + by_id["C126"]["原因"] + by_id["C126"]["影响"]
        for keep in ("十二分之一", "grid_crop.py", "杆顶 y、女儿墙 y、前景遮断处 y",
                     "construction hoarding with a tower crane",
                     "约十八分之一", "16→15", "不牵连 `prompt_sha256`", "撤销分档"):
            self.assertIn(keep, body, "C126 裁定丢了关键句：" + keep[:24])
        for hold in ("斜削冠", "冠部开洞", "扭转塔身", "L007"):
            self.assertIn(hold, by_id["C126"]["裁定"] + by_id["C126"]["影响"],
                          "C126 把不该降的力度也降了：" + hold)

    def test_the_manifest_and_worksheet_carry_the_measured_tiers(self):
        md = (ROOT / "数据" / "开图清单.md").read_text(encoding="utf-8")
        self.assertIn(self.ROD, md)
        self.assertIn(self.CRANE, md)
        self.assertIn("两个数一并写进读数", md)
        sheet = (ROOT / "数据" / "人工复看套件" / "工作单.md").read_text(encoding="utf-8")
        self.assertIn("屋面细杆按 C126 量：无横档／格构／灯球／斜削／开洞且杆高≤同屏可见塔身十二分之一者记备注",
                      sheet)
        self.assertIn("塔吊立于街面施工层记备注、立于天际线远景带判废（C126）", sheet)
        self.assertIn("C126（屋面细杆按杆高对可见塔身十二分之一分档、塔吊按街面与天际线分档）", sheet)

    def test_c126_moves_no_prompt_digest_and_writes_nothing_into_the_prompt_bodies(self):
        snapshot = json.loads((ROOT / "工具" / "reinject_2026_11_05" / "prompt_digests_c123.json")
                               .read_text(encoding="utf-8"))["items"]
        manifest = json.loads((ROOT / "数据" / "开图清单.json").read_text(encoding="utf-8"))["items"]
        moved = [m["id"] for m in manifest if m["prompt_sha256"] != snapshot[m["id"]]["after"]]
        self.assertEqual(moved, [], "C126 动了画面串，变更 %d 条：%s" % (len(moved), moved[:5]))
        leaks = []
        for path in sorted((ROOT / "数据" / "开图提示词").glob("*.txt")):
            text = path.read_text(encoding="utf-8")
            # 只扫「## 提示词正文」之后：抬头里的复验备注是人工读数，读数引 C126 是应有之物，不是渗串。
            body = text.split("## 提示词正文", 1)[1] if "## 提示词正文" in text else ""
            if "C126" in body or self.ROD in body or self.CRANE in body:
                leaks.append(path.name)
        self.assertEqual(leaks, [], "分档措辞渗进提示词正文：%s" % leaks[:3])


if __name__ == "__main__":
    unittest.main(verbosity=2)
