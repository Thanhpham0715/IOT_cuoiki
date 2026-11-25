import unittest
from pathlib import Path

import numpy as np

from server.photo_layout import crop_to_slot, load_frame_templates, render_frame


class PhotoLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.asset_dir = Path(__file__).parent.parent / "assets" / "photo_effects"
        cls.frames = load_frame_templates(cls.asset_dir)

    def test_asset_manifest_loads_all_four_slot_frames(self):
        self.assertEqual(
            set(self.frames),
            {"classic_strip_4", "pastel_pink_strip_4", "grid_2x2_retro"},
        )
        self.assertTrue(all(len(frame.slots) == 4 for frame in self.frames.values()))

    def test_crop_and_frame_render_preserve_photo_slot_dimensions(self):
        source = np.full((80, 120, 3), (15, 80, 220), dtype=np.uint8)
        fitted = crop_to_slot(source, 40, 60)
        self.assertEqual(fitted.shape, (60, 40, 3))

        template = self.frames["classic_strip_4"]
        colors = [
            np.full((20, 20, 3), color, dtype=np.uint8)
            for color in (
                (10, 20, 30),
                (40, 50, 60),
                (70, 80, 90),
                (100, 110, 120),
            )
        ]
        result = render_frame(template, colors)

        self.assertEqual(result.shape, (1800, 600, 3))
        for color, (x, y, width, height) in zip(colors, template.slots):
            center = result[y + height // 2, x + width // 2]
            np.testing.assert_array_equal(center, color[0, 0])


if __name__ == "__main__":
    unittest.main()
