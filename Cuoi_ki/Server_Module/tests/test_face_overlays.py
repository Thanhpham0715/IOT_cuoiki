import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from server.face_overlays import (
    FaceLandmarkerUnavailable,
    FaceOverlayProcessor,
    blend_overlay,
    face_geometry,
    load_overlays,
    rotate_overlay_with_pivot,
)


class FaceOverlayTests(unittest.TestCase):
    def test_face_geometry_uses_eye_line_and_anchor_specific_reference_width(self):
        landmarks = [(0.5, 0.5)] * 478
        landmarks[10] = (0.5, 0.25)
        landmarks[33] = (0.3, 0.4)
        landmarks[133] = (0.4, 0.4)
        landmarks[362] = (0.6, 0.4)
        landmarks[263] = (0.7, 0.4)
        landmarks[234] = (0.2, 0.5)
        landmarks[454] = (0.8, 0.5)

        eyes = face_geometry(landmarks, 200, 100, "eyes")
        self.assertIsNotNone(eyes)
        self.assertAlmostEqual(eyes[0][0], 100.0)
        self.assertAlmostEqual(eyes[0][1], 40.0)
        self.assertAlmostEqual(eyes[1], 80.0)
        self.assertAlmostEqual(eyes[2], 0.0)

        forehead = face_geometry(landmarks, 200, 100, "forehead")
        self.assertIsNotNone(forehead)
        self.assertAlmostEqual(forehead[0][0], 100.0)
        self.assertAlmostEqual(forehead[0][1], 25.0)
        self.assertAlmostEqual(forehead[1], 120.0)
        self.assertAlmostEqual(forehead[2], 0.0)

    def test_rotated_overlay_returns_pivot_in_rotated_coordinates(self):
        overlay = np.zeros((10, 20, 4), dtype=np.uint8)
        rotated, pivot = rotate_overlay_with_pivot(overlay, (10.0, 5.0), 0.0)

        self.assertEqual(rotated.shape[:2], (10, 20))
        self.assertEqual(pivot, (10.0, 5.0))

    def test_alpha_blending_clips_overlay_at_frame_edges(self):
        frame = np.zeros((2, 2, 3), dtype=np.uint8)
        overlay = np.zeros((2, 2, 4), dtype=np.uint8)
        overlay[:, :, 0] = 255
        overlay[:, :, 3] = 255

        self.assertTrue(blend_overlay(frame, overlay, -1, -1))
        self.assertEqual(frame[0, 0].tolist(), [255, 0, 0])
        self.assertEqual(int(frame[1, 1].sum()), 0)
        self.assertFalse(blend_overlay(frame, overlay, 3, 3))

    def test_overlay_metadata_requires_rgba_png_and_missing_model_is_explicit(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            asset_dir = Path(temporary_directory)
            overlay_dir = asset_dir / "crown"
            overlay_dir.mkdir()
            (overlay_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "id": "crown",
                        "name": "Crown",
                        "anchor": "forehead",
                        "width_ratio": 1.15,
                        "pivot": [0.5, 0.85],
                        "offset": [0.0, -0.08],
                        "angle_offset": 0.0,
                    }
                ),
                encoding="utf-8",
            )
            cv2.imwrite(
                str(overlay_dir / "overlay.png"),
                np.zeros((8, 8, 4), dtype=np.uint8),
            )

            self.assertEqual(list(load_overlays(asset_dir)), ["crown"])
            processor = FaceOverlayProcessor(
                {
                    "face_effects": {
                        "asset_dir": str(asset_dir),
                        "model_path": str(asset_dir / "missing.task"),
                    }
                }
            )
            self.assertFalse(processor.available)
            with self.assertRaises(FaceLandmarkerUnavailable):
                processor.prepare(np.zeros((10, 10, 3), dtype=np.uint8), "crown")


if __name__ == "__main__":
    unittest.main()
