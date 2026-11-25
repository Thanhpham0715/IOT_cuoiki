import unittest

from server.gesture_control import GestureControl, GestureDebouncer, ZoomController


class GestureDebouncerTests(unittest.TestCase):
    def test_requires_hold_and_release_before_same_gesture_repeats(self):
        debounce = GestureDebouncer(hold_frames=3, min_score=0.6)
        first_event = None
        for frame in range(3):
            first_event = debounce.update("Victory", 0.9, 10 + frame * 0.1)
        self.assertEqual(first_event, "Victory")

        self.assertIsNone(debounce.update("Victory", 0.9, 11))
        for frame in range(5):
            debounce.update(None, 0, 12 + frame * 0.1)
        second_event = None
        for frame in range(3):
            second_event = debounce.update("Victory", 0.9, 13 + frame * 0.1)
        self.assertEqual(second_event, "Victory")

    def test_rejects_low_confidence_gesture(self):
        debounce = GestureDebouncer(hold_frames=2, min_score=0.6)
        debounce.update("Open_Palm", 0.5, 10)
        self.assertIsNone(debounce.update("Open_Palm", 0.5, 10.1))

    def test_one_missing_frame_does_not_reset_hold_count(self):
        debounce = GestureDebouncer(hold_frames=3, min_score=0.6)
        debounce.update("Open_Palm", 0.9, 10)
        debounce.update("Open_Palm", 0.9, 10.1)

        self.assertIsNone(debounce.update(None, 0, 10.2))
        self.assertEqual(debounce.count, 2)
        self.assertEqual(debounce.update("Open_Palm", 0.9, 10.3), "Open_Palm")


class GestureControlTests(unittest.TestCase):
    def setUp(self):
        self.control = GestureControl(hold_frames=2, countdown_sec=3)
        self.now = 10.0
        self.effects = ["original", "gray", "sepia"]

    def send(self, gesture):
        self.now += 0.2
        hands = (
            [{"gesture": gesture, "score": 0.9, "landmarks": []}]
            if gesture
            else []
        )
        return self.control.process(
            "session-1", hands, self.control.effect_id, self.effects, self.now
        )

    def release(self):
        for _ in range(5):
            self.send(None)

    def activate(self):
        self.send("Open_Palm")
        result = self.send("Open_Palm")
        self.assertTrue(result["control_active"])
        self.release()

    def test_open_palm_activates_and_victory_cycles_filter(self):
        self.activate()
        self.send("Victory")
        result = self.send("Victory")
        self.assertTrue(result["effect_changed"])
        self.assertEqual(result["selected_effect_id"], "gray")

    def test_open_palm_uses_lower_activation_threshold(self):
        control = GestureControl(
            hold_frames=2, min_score=0.6, activation_min_score=0.5
        )
        result = None
        for timestamp in (10.0, 10.2):
            result = control.process(
                "session-1",
                [{"gesture": "Open_Palm", "score": 0.55}],
                "original",
                self.effects,
                now=timestamp,
            )

        self.assertTrue(result["control_active"])

    def test_thumb_up_countdown_can_be_cancelled_by_closed_fist(self):
        self.activate()
        self.send("Thumb_Up")
        result = self.send("Thumb_Up")
        self.assertEqual(result["control_state"], "countdown")
        self.release()
        self.send("Closed_Fist")
        result = self.send("Closed_Fist")
        self.assertEqual(result["control_state"], "ready")
        self.assertEqual(result["countdown_remaining"], 0)

    def test_countdown_requests_capture_once(self):
        self.activate()
        self.send("Thumb_Up")
        self.send("Thumb_Up")
        result = self.control.process(
            "session-1", [], self.control.effect_id, self.effects, self.now + 3.1
        )
        self.assertTrue(result["capture_requested"])
        self.assertEqual(result["control_state"], "capturing")
        self.assertFalse(
            self.control.process(
                "session-1", [], self.control.effect_id, self.effects, self.now + 3.2
            )["capture_requested"]
        )

    def test_zoom_remains_in_supported_range(self):
        zoom = ZoomController()
        self.assertGreater(zoom.update(0.9, 0.03), 1.0)
        self.assertGreaterEqual(zoom.zoom, 1.0)
        self.assertLessEqual(zoom.zoom, 2.5)


if __name__ == "__main__":
    unittest.main()
