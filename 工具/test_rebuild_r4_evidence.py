# -*- coding: utf-8 -*-
"""证据行重建器的违例负测：夹具全在仓库外临时目录，跑前跑后对真源逐件 sha 对拍。

这个脚本最容易出的假绿是「产物在盘就记 ok」——F007 的实投串被插了 442 字符、产物判废待重投，
补行若写成 ok，后续统计就会把一枚废枚算成已投达标。所以这里逐条钉住七项机械判据与四条硬前提，
并对判据本身做变异：把 status 改成恒 ok、把幂等检查改成恒空之后，对应负测必须不再判红。
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WORKSPACE = ROOT.parent
REAL_SENT = sorted((WORKSPACE / "_scratch_cardref" / "reshoot_r4").glob("sent_shard*.jsonl"))
REAL_READINGS = ROOT / "工具" / "reshoot_campaign_2026_11_06" / "rebuild_evidence_r4_readings.json"
PREFIX = "rebuild_r4_evidence_neg_"

_spec = importlib.util.spec_from_file_location("rebuild_r4_evidence_under_test",
                                              str(HERE / "rebuild_r4_evidence.py"))
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _real_shas():
    files = list(REAL_SENT) + ([REAL_READINGS] if REAL_READINGS.exists() else [])
    return {str(p): _sha(p.read_bytes()) for p in files}


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000.0, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _png(path, size, color):
    from PIL import Image
    Image.new("RGB", size, color).save(path)


class Fixture:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix=PREFIX)
        self.scratch = os.path.join(self.tmp, "reshoot_r4")
        os.makedirs(os.path.join(self.scratch, "shards"))
        os.makedirs(os.path.join(self.scratch, "paste"))
        self.img_dir = os.path.join(self.tmp, "vibe_images")
        os.makedirs(self.img_dir)
        self.readings = os.path.join(self.tmp, "readings.json")
        self.registry = os.path.join(self.tmp, "transcripts.json")
        self.transcript = os.path.join(self.tmp, "agent-1.jsonl")
        self.main_jsonl = os.path.join(self.tmp, "main.jsonl")
        Path(self.main_jsonl).write_bytes(b"")
        Path(self.transcript).write_bytes(b"")

        self.eid = "X01"
        self.send_name = "X01-测试片区-C154母图重投-v01"
        self.size = "128x96"
        self.paste_text = "图1只借媒介不借构图。\n" + "正文测试串。" * 40
        self.paste = os.path.join(self.scratch, "paste", self.eid + ".txt")
        Path(self.paste).write_bytes(self.paste_text.encode("utf-8"))
        self.ref = os.path.join(self.tmp, "ref.png")
        _png(self.ref, (128, 96), (10, 20, 30))
        self.prod_ms = 1794185876497
        self.prod = os.path.join(self.img_dir, "%s_%d_abcd0123.png" % (self.send_name, self.prod_ms))
        _png(self.prod, (128, 96), (200, 100, 50))
        self.item = {
            "id": self.eid, "send_name": self.send_name, "size": self.size,
            "paste": self.paste.replace(os.sep, "/"),
            "send_sha256": _sha(Path(self.paste).read_bytes()),
            "send_chars": len(self.paste_text),
            "ref_image": self.ref.replace(os.sep, "/"), "ref_sha256": _sha(Path(self.ref).read_bytes()),
        }
        self.write_shard(1, [self.item])
        self.write_registry()

    def write_shard(self, no, items):
        p = os.path.join(self.scratch, "shards", "shard_%02d.json" % no)
        with io.open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"片号": no, "条数": len(items), "条": items}, ensure_ascii=False))

    def write_registry(self, transcripts=None):
        doc = {"group": "R4", "suffix": "C154母图重投-v01",
               "transcripts": transcripts if transcripts is not None
               else {"1-a-fixture": self.transcript.replace(os.sep, "/")},
               "主会话jsonl": self.main_jsonl.replace(os.sep, "/")}
        with io.open(self.registry, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(doc, ensure_ascii=False))

    def sent_path(self, no=1):
        return os.path.join(self.scratch, "sent_shard%02d.jsonl" % no)

    def seed_row(self, eid="X99", no=1, eol="\r\n"):
        row = {"id": eid, "arm": "ref", "send_name": eid + "-别的片区", "status": "ok", "error": "",
               "timestamp_ms": 1}
        with io.open(self.sent_path(no), "a", encoding="utf-8", newline="") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + eol)

    def send(self, prompt=None, images=None, size=None, name=None, prod=None, tool_id="call_fixture01",
             receipt=True, result_delta_ms=44):
        prompt = self.paste_text if prompt is None else prompt
        images = [self.ref.replace(os.sep, "/")] if images is None else images
        prod = self.prod if prod is None else prod
        use = {"type": "assistant", "timestamp": _iso(self.prod_ms - 30000), "uuid": "uuid-use",
               "message": {"content": [{"type": "tool_use", "id": tool_id, "name": "ImageGen",
                                       "input": {"name": name or self.send_name, "prompt": prompt,
                                                 "size": size or self.size, "images": images}}]}}
        lines = [json.dumps(use, ensure_ascii=False)]
        if receipt:
            res = {"type": "user", "timestamp": _iso(self.prod_ms + result_delta_ms), "uuid": "uuid-res",
                   "toolUseResult": {"filePath": prod.replace(os.sep, "\\"), "requestId": "req-fixture"},
                   "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id,
                                            "content": "Image generated successfully. Saved to: " + prod}]}}
            lines.append(json.dumps(res, ensure_ascii=False))
        with io.open(self.transcript, "a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")

    def run(self, dry=False, ids=None):
        argv = ["--scratch", self.scratch, "--registry", self.registry, "--readings", self.readings,
                "--ids", ids or self.eid]
        if dry:
            argv.append("--dry")
        buf = io.StringIO()
        rc = 0
        with contextlib.redirect_stdout(buf):
            try:
                rc = R.main(argv)
            except SystemExit as exc:
                rc = exc.code if isinstance(exc.code, int) else 1
                buf.write(str(exc.code) + "\n")
        return rc, buf.getvalue()

    def rows(self, no=1):
        p = self.sent_path(no)
        if not os.path.isfile(p):
            return []
        with io.open(p, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh if x.strip()]

    def report(self):
        with io.open(self.readings, encoding="utf-8") as fh:
            return json.load(fh)

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class RebuildEvidenceNegative(unittest.TestCase):
    def setUp(self):
        self.before = _real_shas()
        self.fx = Fixture()

    def tearDown(self):
        self.fx.cleanup()
        leaked = [d for d in os.listdir(tempfile.gettempdir()) if d.startswith(PREFIX)]
        self.assertEqual(leaked, [], "临时夹具残留 %d 个：%s" % (len(leaked), leaked))
        self.assertEqual(_real_shas(), self.before, "负测跑动期间真源被改写＝夹具污染了被守护面")

    # ---------- 正向：行形态与来源可分 ----------
    def test_a_ok_row_keeps_16_spec_fields_and_separate_provenance(self):
        self.fx.send()
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        rows = self.fx.rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(tuple(row)[:len(R.FIELDS)], R.FIELDS, "规程 16 字段的顺序被 provenance 插队了")
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["来源"], R.SOURCE_TAG)
        self.assertIn("非代理当场所写", row["error"])
        self.assertIn("按 transcript 反查重建", row["error"])
        self.assertEqual(row["投放时刻_ms"], self.fx.prod_ms)
        self.assertNotEqual(row["timestamp_ms"], row["投放时刻_ms"],
                            "写入当刻与投放时刻被混成一个数＝后续按 timestamp 排序会当成重建那刻投的")
        self.assertEqual(row["send_sha256"], self.fx.item["send_sha256"])
        self.assertEqual(row["实投串_sha256"], self.fx.item["send_sha256"])
        self.assertTrue(row["串面相符"])
        self.assertEqual(len(row["机械判据"]), 7)
        self.assertTrue(all(c["符"] for c in row["机械判据"]))
        self.assertEqual(row["重建依据"]["tool_use_id"], "call_fixture01")
        self.assertTrue(row["imagegen_path"].endswith(".png"))
        self.assertEqual(row["image_sha256"], _sha(Path(self.fx.prod).read_bytes()))

    def test_b_agent_written_rows_stay_distinguishable(self):
        self.fx.seed_row(eid="X99")
        self.fx.send()
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        rows = self.fx.rows()
        self.assertEqual(len(rows), 2)
        self.assertNotIn("来源", rows[0], "代理当场写的行被补挂了 provenance＝两种来源混成一份")
        self.assertEqual(rows[1]["来源"], R.SOURCE_TAG)
        rep = self.fx.report()
        self.assertEqual(rep["status 分布"], {"ok": 1, "failed": 0})

    # ---------- 负测：串面不符必须 failed ----------
    def test_c_prompt_drift_must_be_failed_not_ok(self):
        drifted = self.fx.paste_text[:20] + "【被插进来的一段无关文字】" * 12 + self.fx.paste_text[20:]
        self.fx.send(prompt=drifted)
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        row = self.fx.rows()[0]
        self.assertEqual(row["status"], "failed", "产物在盘就把串面不符写成 ok＝废枚被算成已投达标")
        self.assertFalse(row["串面相符"])
        self.assertEqual(row["实投串_chars"], len(drifted))
        self.assertEqual(row["send_chars"], len(self.fx.paste_text), "send_chars 被实投串顶掉＝规程定义变了")
        self.assertEqual(row["send_sha256"], self.fx.item["send_sha256"])
        self.assertNotEqual(row["实投串_sha256"], row["send_sha256"])
        self.assertIn("判废待重投", row["error"])
        self.assertIn("物理移出 vibe_images", row["error"])
        self.assertIn("非代理当场所写", row["error"])
        self.assertEqual(row["串面差异"]["位置"], 20,
                         "首处差异位置取了 difflib 的 opcode 起点：插入段含原串也有的字时它会往前挪")
        self.assertEqual(row["串面差异"]["公共前缀长"], 20)
        self.assertEqual(row["串面差异"]["多出字符"], len(drifted) - len(self.fx.paste_text))
        self.assertEqual(self.fx.report()["status 分布"], {"ok": 0, "failed": 1})

    def test_d_prompt_truncation_must_be_failed(self):
        self.fx.send(prompt=self.fx.paste_text[:-30])
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        row = self.fx.rows()[0]
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["串面差异"]["多出字符"], -30)

    # ---------- 负测：其余五项机械判据 ----------
    def test_e_size_declaration_mismatch_must_be_failed(self):
        self.fx.send(size="768x1024")
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        row = self.fx.rows()[0]
        self.assertEqual(row["status"], "failed")
        bad = [c["名"] for c in row["机械判据"] if not c["符"]]
        self.assertEqual(bad, ["size 声明相符"],
                         "声明与实读是两条独立判据：产物像素仍是清单那档，只有声明不符")

    def test_e2_product_pixel_size_mismatch_must_be_failed(self):
        wrong = os.path.join(self.fx.img_dir, "%s_%d_abcd0123.png" % (self.fx.send_name, self.fx.prod_ms))
        os.remove(self.fx.prod)
        _png(wrong, (768, 1024), (200, 100, 50))
        self.fx.send(prod=wrong)
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        row = self.fx.rows()[0]
        self.assertEqual(row["status"], "failed")
        self.assertEqual([c["名"] for c in row["机械判据"] if not c["符"]], ["尺寸实读相符"])
        self.assertEqual((row["width"], row["height"]), (768, 1024), "宽高抄了清单而不是实读产物")

    def test_f_ref_sha_mismatch_must_be_failed(self):
        self.fx.item["ref_sha256"] = "0" * 64
        self.fx.write_shard(1, [self.fx.item])
        self.fx.send()
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        row = self.fx.rows()[0]
        self.assertEqual(row["status"], "failed")
        self.assertIn("母图摘要相符", [c["名"] for c in row["机械判据"] if not c["符"]])
        self.assertNotEqual(row["ref_sha256"], self.fx.item["ref_sha256"],
                            "ref_sha256 抄了清单而不是实读母图＝摘要判据被架空")

    def test_g_images_missing_must_be_failed(self):
        self.fx.send(images=[])
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        row = self.fx.rows()[0]
        self.assertEqual(row["status"], "failed", "裸串投放被当成母图臂达标")
        self.assertIn("母图挂载相符", [c["名"] for c in row["机械判据"] if not c["符"]])

    def test_h_images_object_form_still_binds_by_basename(self):
        self.fx.send(images=[{"source": self.fx.ref.replace(os.sep, "/"), "type": "image"}])
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.fx.rows()[0]["status"], "ok")

    def test_i_wrong_ref_image_must_be_failed(self):
        other = os.path.join(self.fx.tmp, "other.png")
        _png(other, (128, 96), (1, 2, 3))
        self.fx.send(images=[other.replace(os.sep, "/")])
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.fx.rows()[0]["status"], "failed")

    def test_j_product_name_unbound_must_be_failed(self):
        stray = os.path.join(self.fx.img_dir, "别的名字_%d_abcd0123.png" % self.fx.prod_ms)
        _png(stray, (128, 96), (9, 9, 9))
        self.fx.send(prod=stray)
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        row = self.fx.rows()[0]
        self.assertEqual(row["status"], "failed")
        self.assertIn("产物名绑发名", [c["名"] for c in row["机械判据"] if not c["符"]])
        self.assertEqual(row["投放时刻_ms"], self.fx.prod_ms,
                         "异名产物的内嵌时间戳仍解析得出来，绑不上的只是发名前缀")

    def test_j2_product_without_timestamp_has_no_landing_time(self):
        stray = os.path.join(self.fx.img_dir, self.fx.send_name + "_无时间戳.png")
        _png(stray, (128, 96), (9, 9, 9))
        self.fx.send(prod=stray)
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        row = self.fx.rows()[0]
        self.assertEqual(row["status"], "failed")
        self.assertIsNone(row["投放时刻_ms"])
        self.assertIsNone(row["投放时刻_utc"])
        self.assertIn("落盘与回执同带", [c["名"] for c in row["机械判据"] if not c["符"]])

    def test_k_receipt_time_far_from_landing_must_be_failed(self):
        self.fx.send(result_delta_ms=R.PAIR_BAND_MS + 1)
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        row = self.fx.rows()[0]
        self.assertEqual(row["status"], "failed")
        self.assertIn("落盘与回执同带", [c["名"] for c in row["机械判据"] if not c["符"]])

    # ---------- 负测：四条硬前提必须停手，不写半条行 ----------
    def test_l_missing_product_hard_stops(self):
        self.fx.send()
        os.remove(self.fx.prod)
        rc, out = self.fx.run()
        self.assertNotEqual(rc, 0)
        self.assertIn("只对已在盘的产物补记录", out)
        self.assertEqual(self.fx.rows(), [])
        self.assertFalse(os.path.exists(self.fx.readings))

    def test_m_missing_receipt_hard_stops(self):
        self.fx.send(receipt=False)
        rc, out = self.fx.run()
        self.assertNotEqual(rc, 0)
        self.assertIn("取不到带 filePath 的回执", out)
        self.assertEqual(self.fx.rows(), [])

    def test_n_paste_drift_from_manifest_hard_stops(self):
        Path(self.fx.paste).write_bytes((self.fx.paste_text + "尾巴").encode("utf-8"))
        self.fx.send()
        rc, out = self.fx.run()
        self.assertNotEqual(rc, 0)
        self.assertIn("输入面坏了先修清单", out)
        self.assertEqual(self.fx.rows(), [])

    def test_o_missing_ref_hard_stops(self):
        self.fx.send()
        os.remove(self.fx.ref)
        rc, out = self.fx.run()
        self.assertNotEqual(rc, 0)
        self.assertIn("母图不在盘", out)
        self.assertEqual(self.fx.rows(), [])

    def test_p_missing_transcript_hard_stops(self):
        self.fx.send()
        self.fx.write_registry({"1-a-gone": os.path.join(self.fx.tmp, "不存在.jsonl")})
        rc, out = self.fx.run()
        self.assertNotEqual(rc, 0)
        self.assertIn("回绑源缺失", out)
        self.assertEqual(self.fx.rows(), [])

    def test_q_two_sends_same_name_refuse(self):
        self.fx.send(tool_id="call_one")
        self.fx.send(tool_id="call_two")
        rc, out = self.fx.run()
        self.assertNotEqual(rc, 0)
        self.assertIn("须恰 1", out)
        self.assertEqual(self.fx.rows(), [], "发起不唯一还挑一条写＝替代理猜哪次算数")

    def test_r_zero_sends_refuse(self):
        rc, out = self.fx.run()
        self.assertNotEqual(rc, 0)
        self.assertIn("命中 0 次发起", out)
        self.assertEqual(self.fx.rows(), [])

    def test_s_id_in_two_shards_refuse(self):
        self.fx.send()
        self.fx.write_shard(2, [self.fx.item])
        rc, out = self.fx.run()
        self.assertNotEqual(rc, 0)
        self.assertIn("须恰 1", out)
        self.assertEqual(self.fx.rows(), [])

    def test_t_existing_row_is_idempotent_refusal(self):
        self.fx.seed_row(eid=self.fx.eid)
        before = Path(self.fx.sent_path()).read_bytes()
        self.fx.send()
        rc, out = self.fx.run()
        self.assertNotEqual(rc, 0)
        self.assertIn("拒跑", out)
        self.assertEqual(Path(self.fx.sent_path()).read_bytes(), before, "幂等拒跑还动了原文件")
        self.assertFalse(os.path.exists(self.fx.readings))

    def test_u_partial_refusal_writes_nothing_for_the_whole_run(self):
        self.fx.seed_row(eid=self.fx.eid)
        other = dict(self.fx.item, id="X02", send_name="X02-测试片区-C154母图重投-v01",
                     paste=os.path.join(self.fx.scratch, "paste", "X02.txt").replace(os.sep, "/"))
        Path(other["paste"]).write_bytes(self.fx.paste_text.encode("utf-8"))
        self.fx.write_shard(1, [self.fx.item, other])
        self.fx.send()
        self.fx.send(name=other["send_name"], tool_id="call_two")
        before = Path(self.fx.sent_path()).read_bytes()
        rc, out = self.fx.run(ids="X01,X02")
        self.assertNotEqual(rc, 0)
        self.assertIn("整轮不写", out)
        self.assertEqual(Path(self.fx.sent_path()).read_bytes(), before,
                         "一条拒跑另一条照写＝半批落盘，续投差集会算错")

    # ---------- 负测：--dry 与落盘面 ----------
    def test_v_dry_writes_nothing(self):
        self.fx.send()
        rc, out = self.fx.run(dry=True)
        self.assertEqual(rc, 0, out)
        self.assertIn("--dry", out)
        self.assertFalse(os.path.exists(self.fx.sent_path()))
        self.assertFalse(os.path.exists(self.fx.readings))
        self.assertFalse(os.path.exists(os.path.join(self.fx.scratch, "bak_evidence_rebuild")))

    def test_w_append_preserves_existing_bytes_and_backs_up(self):
        self.fx.seed_row(eid="X99", eol="\r\n")
        before = Path(self.fx.sent_path()).read_bytes()
        self.fx.send()
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        after = Path(self.fx.sent_path()).read_bytes()
        self.assertTrue(after.startswith(before), "追加改写了既有字节")
        self.assertEqual(after[len(before):].count(b"\r\n"), 1, "行尾没沿用目标文件已有的 CRLF")
        rep = self.fx.report()
        bak = rep["落盘"][0]["备份"]
        self.assertTrue(bak and os.path.isfile(bak))
        self.assertEqual(Path(bak).read_bytes(), before, "备份不是写前那份")
        self.assertEqual(rep["落盘"][0]["行尾"], "CRLF")
        self.assertEqual(rep["落盘"][0]["追加字节"], len(after) - len(before))

    def test_x_lf_target_stays_lf(self):
        self.fx.seed_row(eid="X99", eol="\n")
        self.fx.send()
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.fx.report()["落盘"][0]["行尾"], "LF")
        self.assertNotIn(b"\r\n", Path(self.fx.sent_path()).read_bytes())

    def test_y_two_ids_in_same_shard_back_up_once(self):
        other = dict(self.fx.item, id="X02", send_name="X02-测试片区-C154母图重投-v01",
                     paste=os.path.join(self.fx.scratch, "paste", "X02.txt").replace(os.sep, "/"))
        Path(other["paste"]).write_bytes(self.fx.paste_text.encode("utf-8"))
        self.fx.write_shard(1, [self.fx.item, other])
        self.fx.seed_row(eid="X99")
        self.fx.send()
        self.fx.send(name=other["send_name"], tool_id="call_two")
        rc, out = self.fx.run(ids="X01,X02")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(self.fx.rows()), 3)
        baks = list(Path(self.fx.scratch, "bak_evidence_rebuild").rglob("sent_shard01.jsonl"))
        self.assertEqual(len(baks), 1, "同片两条把备份位撞了＝第二条写不进去")

    def test_z_report_covers_its_own_counting_face(self):
        self.fx.send()
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        rep = self.fx.report()
        self.assertEqual(rep["请求条数"], 1)
        self.assertEqual(rep["可重建条数"], 1)
        self.assertEqual(rep["拒跑条数"], 0)
        self.assertEqual(rep["回绑源"]["在盘份数"], 2)
        self.assertEqual(rep["回绑源"]["缺失份数"], 0)
        self.assertIn("统计面", rep)
        self.assertIn("shards", rep["统计面"])
        self.assertFalse(rep["dry"])

    # ---------- 对判据本身做变异：证明上面每条负测真的在测它 ----------
    def test_mutation_status_always_ok_makes_drift_negative_toothless(self):
        orig = R.evaluate

        def always_ok(item, use, result, now_ms):
            row, checks = orig(item, use, result, now_ms)
            row["status"] = "ok"
            row["串面相符"] = True
            row["error"] = ""
            return row, checks

        R.evaluate = always_ok
        try:
            self.fx.send(prompt=self.fx.paste_text + "被插进来的一段")
            rc, out = self.fx.run()
            self.assertEqual(rc, 0, out)
            self.assertEqual(self.fx.rows()[0]["status"], "ok",
                             "变异后串面负测不再判红＝test_c 测的就是 status 这一条")
        finally:
            R.evaluate = orig

    def test_mutation_idempotency_always_empty_makes_existing_row_negative_toothless(self):
        orig = R.existing_ids
        R.existing_ids = lambda scratch, no: (set(), os.path.join(scratch, "sent_shard%02d.jsonl" % no))
        try:
            self.fx.seed_row(eid=self.fx.eid)
            self.fx.send()
            rc, out = self.fx.run()
            self.assertEqual(rc, 0, "变异后幂等负测不再判红＝test_t 测的就是 existing_ids 这一条")
            self.assertEqual(len(self.fx.rows()), 2, "同一 id 落了两行")
        finally:
            R.existing_ids = orig

    def test_mutation_pair_band_infinite_makes_time_negative_toothless(self):
        orig = R.PAIR_BAND_MS
        R.PAIR_BAND_MS = 10 ** 12
        try:
            self.fx.send(result_delta_ms=orig + 1)
            rc, out = self.fx.run()
            self.assertEqual(rc, 0, out)
            self.assertEqual(self.fx.rows()[0]["status"], "ok",
                             "变异后同带负测不再判红＝test_k 测的就是 PAIR_BAND_MS 这一条")
        finally:
            R.PAIR_BAND_MS = orig


if __name__ == "__main__":
    unittest.main(verbosity=2)