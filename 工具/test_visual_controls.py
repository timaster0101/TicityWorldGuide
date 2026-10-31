import copy
import math
import unittest
import wave

import numpy as np

import build_l007_realistic as l007_realistic
import finalize_r043_video as r043_finalizer

from build_visual_controls import (
    SCENES,
    camera_at,
    camera_for,
    project_point,
    render_frame,
    scene_geometry,
    validate_scene,
)


class VisualControlsTests(unittest.TestCase):
    def test_l007_site_area_matches_canon(self):
        scene = SCENES["L007"]
        self.assertEqual(scene["site"]["width_m"] * scene["site"]["depth_m"], 62000)
        self.assertEqual(scene["canonical"]["area_m2"], 62000)

    def test_r043_site_area_matches_canon(self):
        scene = SCENES["R043"]
        self.assertEqual(scene["site"]["width_m"] * scene["site"]["depth_m"], 294000)
        self.assertEqual(scene["canonical"]["area_m2"], 294000)

    def test_l007_camera_moves_east_six_metres_at_constant_height(self):
        scene = SCENES["L007"]
        start = camera_at(scene, 0)
        end = camera_at(scene, 8)
        self.assertEqual(start, (-30.0, -120.0, 1.6))
        self.assertEqual(end, (-24.0, -120.0, 1.6))
        self.assertAlmostEqual(math.dist(start, end), 6.0)

    def test_r043_camera_moves_four_metres_northeast(self):
        scene = SCENES["R043"]
        start = camera_at(scene, 0)
        end = camera_at(scene, 8)
        self.assertAlmostEqual(math.dist(start, end), 4.0)
        self.assertGreater(end[0], start[0])
        self.assertGreater(end[1], start[1])
        self.assertAlmostEqual(end[0] - start[0], end[1] - start[1], places=6)
        self.assertEqual(start[2], end[2])

    def test_keyframe_times_cover_full_eight_seconds(self):
        for scene in SCENES.values():
            self.assertEqual(scene["key_times_s"], (0, 2, 4, 6, 8))
            self.assertEqual(scene["duration_s"], 8)
            self.assertEqual(validate_scene(scene), [])

    def test_camera_path_outside_site_is_rejected(self):
        scene = copy.deepcopy(SCENES["L007"])
        scene["camera"]["end_m"] = (1000.0, -120.0, 1.6)
        with self.assertRaisesRegex(ValueError, "路径越界"):
            validate_scene(scene)

    def test_project_point_on_forward_axis_lands_at_image_center(self):
        camera = {
            "position": (0.0, 0.0, 1.6),
            "yaw_deg": 0.0,
            "pitch_deg": 0.0,
            "lens_mm": 35.0,
            "sensor_fit": "horizontal",
        }
        x, y, depth = project_point((0.0, 10.0, 1.6), camera, (1280, 1024))
        self.assertAlmostEqual(x, 640.0)
        self.assertAlmostEqual(y, 512.0)
        self.assertAlmostEqual(depth, 10.0)

    def test_l007_antenna_rises_above_southern_crown_in_every_keyframe(self):
        scene = SCENES["L007"]
        _, lines = scene_geometry(scene)
        antenna = next((start, end) for start, end, color, _ in lines if color == (75, 82, 87))
        for time_s in scene["key_times_s"]:
            camera = camera_for(scene, time_s)
            tip = project_point(antenna[1], camera, scene["control_size"])
            crown = project_point((-24, 0, 344), camera, scene["control_size"])
            self.assertLess(tip[1], crown[1])
            self.assertGreaterEqual(tip[1], 0)

    def test_r043_closed_gate_does_not_cover_final_frame(self):
        scene = SCENES["R043"]
        faces, _ = scene_geometry(scene)
        gate = next(vertices for vertices, color in faces if color == (115, 82, 53))
        camera = camera_for(scene, 8)
        width, height = scene["control_size"]
        projected = [project_point(point, camera, scene["control_size"]) for point in gate]
        self.assertTrue(all(0 <= x <= width and 0 <= y <= height for x, y, _ in projected))

    def test_render_frame_uses_requested_control_image_size(self):
        image = render_frame(SCENES["R043"], 0, (320, 256))
        self.assertEqual(image.size, (320, 256))

    def test_l007_realistic_model_contains_exactly_78_contiguous_floors(self):
        if not hasattr(l007_realistic, "floor_bands"):
            self.fail("缺少L007写实模型楼层定义")
        bands = l007_realistic.floor_bands()
        self.assertEqual(len(bands), 78)
        self.assertEqual(bands[0][0], 24)
        self.assertEqual(bands[-1][1], 320)
        self.assertEqual(len({round(top - bottom, 6) for bottom, top in bands}), 1)
        self.assertTrue(all(math.isclose(bands[i][1], bands[i + 1][0]) for i in range(77)))

    def test_l007_realistic_frame_uses_requested_portrait_size(self):
        if not hasattr(l007_realistic, "render_realistic_frame"):
            self.fail("缺少L007写实帧渲染功能")
        image = l007_realistic.render_realistic_frame(0, (256, 384))
        self.assertEqual(image.size, (256, 384))

    def test_l007_photo_composite_uses_requested_portrait_size(self):
        if not hasattr(l007_realistic, "composite_realistic_still"):
            self.fail("缺少L007照片材质合成功能")
        image = l007_realistic.composite_realistic_still((256, 384))
        self.assertEqual(image.size, (256, 384))

    def test_l007_video_frame_locks_first_image_and_moves_camera(self):
        if not hasattr(l007_realistic, "composite_realistic_frame"):
            self.fail("缺少L007写实视频帧合成功能")
        size = (256, 384)
        first = l007_realistic.composite_realistic_frame(0, size)
        last = l007_realistic.composite_realistic_frame(8, size)
        self.assertEqual(first.size, size)
        self.assertEqual(last.size, size)
        np.testing.assert_array_equal(
            np.asarray(first), np.asarray(l007_realistic.composite_realistic_still(size))
        )
        difference = np.abs(np.asarray(last, dtype=np.int16) - np.asarray(first, dtype=np.int16))
        self.assertGreater(float(difference.mean()), 1.0)

    def test_l007_video_motion_does_not_replicate_edge_columns(self):
        frame = np.asarray(l007_realistic.composite_realistic_frame(8, (256, 384)), dtype=np.int16)
        edge_difference = np.abs(frame[:, -1] - frame[:, -4]).mean()
        self.assertGreater(float(edge_difference), 0.5)

    def test_r043_effect_track_contains_broom_and_wood_events(self):
        if not hasattr(r043_finalizer, "synthesize_effects"):
            self.fail("缺少R043音效合成功能")
        audio, sample_rate = r043_finalizer.synthesize_effects()
        self.assertEqual(sample_rate, 32000)
        self.assertEqual(audio.shape, (8 * 32000, 2))
        quiet = np.sqrt(np.mean(audio[32000:2 * 32000] ** 2))
        broom = np.sqrt(np.mean(audio[3 * 32000:4 * 32000] ** 2))
        wood = np.sqrt(np.mean(audio[6 * 32000:8 * 32000] ** 2))
        self.assertGreater(broom, quiet * 5)
        self.assertGreater(wood, quiet * 5)
        self.assertLessEqual(float(np.max(np.abs(audio))), 0.8)

    def test_r043_wav_export_preserves_eight_second_stereo_track(self):
        if not hasattr(r043_finalizer, "write_effect_wav"):
            self.fail("缺少R043音效导出功能")
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "效果.wav"
            r043_finalizer.write_effect_wav(path)
            with wave.open(str(path), "rb") as stream:
                self.assertEqual(stream.getframerate(), 32000)
                self.assertEqual(stream.getnchannels(), 2)
                self.assertEqual(stream.getnframes(), 8 * 32000)


if __name__ == "__main__":
    unittest.main()
