# -*- coding: utf-8 -*-
"""wire_card_main_images 的证据归一与「留最后一次发起」判据（C154 配套闸门）。

夹具全部落在 tempfile，不碰仓内 landing 与分档证据。
"""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

import hashlib

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("wire_card_main_images",
                                               os.path.join(HERE, "wire_card_main_images.py"))
wire = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wire)

WAVE1 = {"id": "L001", "prompt_sha256": "a" * 64, "imagegen_path": "vibe/L001.png",
         "landing": "L001.png", "landing_bytes": 0, "width": 768, "height": 1024,
         "landing_sha256": "", "status": "ok", "error": "", "timestamp_ms": 1}
WAVE2 = {"id": "L001", "name": "钛湖市民议事厅", "round": "r3", "prompt_file": "L001.txt",
         "prompt_sha256": "a" * 64, "bytes": 1500, "size": [768, 1024], "landing": "L001.png",
         "sent_at": "2026-11-09T03:00:00", "timestamp_ms": 2, "gen_path": "vibe/L001.png",
         "gen_bytes": 1500, "gen_sha256_12": "1a2b3c4d5e6f", "copy_bytes": 1500,
         "copy_sha256_12": "1a2b3c4d5e6f", "status": "ok"}


class NormalizeTest(unittest.TestCase):
    def test_wave2_schema_maps_onto_wave1_keys(self):
        got = wire.normalize(dict(WAVE2))
        self.assertEqual(got["landing_bytes"], WAVE2["copy_bytes"])
        self.assertEqual(got["landing_sha256"], WAVE2["copy_sha256_12"])
        self.assertEqual(got["imagegen_path"], WAVE2["gen_path"])
        self.assertEqual((got["width"], got["height"]), (768, 1024))

    def test_wave1_rows_pass_through_unchanged(self):
        got = wire.normalize(dict(WAVE1))
        for key in ("landing_bytes", "landing_sha256", "imagegen_path", "width", "height"):
            self.assertEqual(got[key], WAVE1[key])


class LatestSendWinsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="wire_ev_")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write(self, name, rows):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def test_older_probe_row_does_not_override_newer_full_send(self):
        # 文件名排序把 sent_shard_probe 排在 sent_shard_02 之后，旧串探针不得顶掉现串放量
        self.write("sent_shard_02.jsonl", [dict(WAVE1, timestamp_ms=2000, prompt_sha256="b" * 64)])
        self.write("sent_shard_probe.jsonl", [dict(WAVE1, timestamp_ms=1000, prompt_sha256="a" * 64)])
        ev, files, dup = wire.collect_evidence(self.dir)
        self.assertEqual(ev["L001"]["timestamp_ms"], 2000)
        self.assertEqual(ev["L001"]["prompt_sha256"], "b" * 64)
        self.assertEqual(dup, {"L001": 1})
        self.assertEqual(files, ["sent_shard_02.jsonl", "sent_shard_probe.jsonl"])

    def test_reverting_to_file_order_would_bind_the_stale_string(self):
        """负测：按文件顺序覆盖（旧行为）会让探针旧串成为送入串，check() 必须当场判红。"""
        old = dict(WAVE1, timestamp_ms=1000, prompt_sha256="a" * 64)
        led = {"id": "L001", "prompt_sha256": "b" * 64, "landing": "missing.png"}
        problems, _ = _check_with_no_landing(wire, led, old)
        self.assertIn("送入串 sha256 与台账 prompt_sha256 不符", problems)

    def test_r4_arm_compares_against_send_sha_not_base_sha(self):
        """r4 图生图臂：证据记的是「真实喂进去那串」（前导一行＋底串逐字）的摘要。

        拿底串摘要去对拍会 85 条全判「送入串 sha256 与台账不符」；反过来，如果这一轮误用底串摘要当
        对拍目标，逐字面就看不见漏加前导的那批发起——两侧都得钉住。
        """
        led = {"id": "idx007", "base_sha256": "b" * 64, "send_sha256": "c" * 64, "landing": "missing.png"}
        bad = dict(WAVE1, prompt_sha256="b" * 64)
        problems, _ = _check_with_no_landing(wire, led, bad, "send_sha256")
        self.assertIn("送入串 sha256 与台账 send_sha256 不符", problems)
        ok = dict(WAVE1, prompt_sha256="c" * 64)
        problems, _ = _check_with_no_landing(wire, led, ok, "send_sha256")
        self.assertNotIn("送入串 sha256 与台账 send_sha256 不符", problems)


def _check_with_no_landing(module, led_row, ev_row, sha_field="prompt_sha256"):
    """只跑到 landing 缺失之前的一支：串 sha 对拍先于落盘存在性，旧串必须当场判红。"""
    got = module.check("L001", led_row, ev_row, sha_field)
    return (got, None) if isinstance(got, list) else got


class ShaPrefixTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="wire_sha_")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.old_root = wire.ROOT
        wire.ROOT = self.dir
        self.addCleanup(setattr, wire, "ROOT", self.old_root)
        path = os.path.join(self.dir, "L001.png")
        Image.new("RGB", (768, 1024), (10, 20, 30)).save(path)
        with open(path, "rb") as fh:
            self.raw = fh.read()
        self.sha = hashlib.sha256(self.raw).hexdigest()
        self.led = {"id": "L001", "prompt_sha256": "p" * 64, "landing": "L001.png"}

    def _row(self, **kw):
        row = {"id": "L001", "status": "ok", "prompt_sha256": "p" * 64,
               "landing_bytes": len(self.raw), "landing_sha256": self.sha, "timestamp_ms": 1}
        row.update(kw)
        return row

    def test_full_sha_passes(self):
        got = wire.check("L001", self.led, self._row())
        problems = got[0] if isinstance(got, tuple) else got
        self.assertEqual(problems, [])

    def test_twelve_char_prefix_passes_and_is_recorded(self):
        got = wire.check("L001", self.led, self._row(landing_sha256=self.sha[:12]))
        problems, reading = got
        self.assertEqual(problems, [])
        self.assertEqual(reading["证据sha位数"], 12)

    def test_wrong_prefix_is_caught(self):
        bad = self.sha[:12]
        bad = ("0" if bad[0] != "0" else "1") + bad[1:]
        problems, _ = wire.check("L001", self.led, self._row(landing_sha256=bad))
        self.assertEqual(problems, ["证据 sha 前缀≠实读"])

    def test_missing_sha_is_caught_not_silently_passed(self):
        problems, _ = wire.check("L001", self.led, self._row(landing_sha256=""))
        self.assertEqual(problems, ["证据无 sha256（位数 0）"])

    def test_short_form_bytes_field_normalizes_before_check(self):
        row = wire.normalize(dict(WAVE2, landing_bytes=None, copy_bytes=len(self.raw),
                                  prompt_sha256="p" * 64, landing_sha256=None,
                                  copy_sha256_12=self.sha[:12]))
        problems, reading = wire.check("L001", self.led, row)
        self.assertEqual(problems, [])
        self.assertEqual(reading["bytes"], len(self.raw))


if __name__ == "__main__":
    unittest.main()
