import unittest

import cv2
import numpy as np

from server.image_processing import EFFECTS, process_image


class ImageProcessingTests(unittest.TestCase):
    def test_effect_catalog_is_allowlisted_and_transforms_jpeg(self):
        image = np.full((16, 16, 3), 100, dtype=np.uint8)
        encoded, jpeg = cv2.imencode(".jpg", image)
        self.assertTrue(encoded)

        processed = process_image(jpeg.tobytes(), "negative")
        decoded = cv2.imdecode(np.frombuffer(processed, dtype=np.uint8), cv2.IMREAD_COLOR)

        self.assertIn("negative", EFFECTS)
        self.assertGreater(float(decoded.mean()), 100)

    def test_unknown_effect_is_rejected(self):
        with self.assertRaises(ValueError):
            process_image(b"not an image", "unknown")

    def test_zoom_is_applied_and_out_of_range_zoom_is_rejected(self):
        image = np.zeros((32, 32, 3), dtype=np.uint8)
        image[8:24, 8:24] = 200
        encoded, jpeg = cv2.imencode(".jpg", image)
        self.assertTrue(encoded)

        zoomed = process_image(jpeg.tobytes(), "original", zoom_factor=2)
        decoded = cv2.imdecode(np.frombuffer(zoomed, dtype=np.uint8), cv2.IMREAD_COLOR)

        self.assertGreater(float(decoded[16, 16].mean()), float(decoded[2, 2].mean()))
        with self.assertRaises(ValueError):
            process_image(jpeg.tobytes(), "original", zoom_factor=3)


if __name__ == "__main__":
    unittest.main()
