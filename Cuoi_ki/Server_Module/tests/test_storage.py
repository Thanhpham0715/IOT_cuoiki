import tempfile
import time
import unittest
import uuid
from pathlib import Path

from server.storage import Storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.storage = Storage(
            {
                "storage": {
                    "photo_dir": str(root / "photos"),
                    "db_path": str(root / "photobooth.db"),
                }
            }
        )

    def tearDown(self):
        self.storage.close()
        self.temporary_directory.cleanup()

    def _complete_single_shot_batch(self, session_id, is_retake=False):
        batch = self.storage.create_capture_batch(
            session_id, 1, 10, is_retake=is_retake
        )
        photo_id = str(uuid.uuid4())
        self.storage.create_capture_shot(
            batch["batch_id"], 1, photo_id, uuid.uuid4().hex
        )
        self.storage.save_raw_photo(
            session_id, b"raw photo", photo_id, batch["batch_id"], 1
        )
        return self.storage.complete_capture_batch(batch["batch_id"], 30)

    def _complete_four_shot_batch(self, session_id, accept_review=True):
        batch = self.storage.create_capture_batch(session_id, 4, 1)
        photo_ids = []
        for number in range(1, 5):
            photo_id = str(uuid.uuid4())
            photo_ids.append(photo_id)
            self.storage.create_capture_shot(
                batch["batch_id"], number, photo_id, uuid.uuid4().hex
            )
            self.storage.save_raw_photo(
                session_id, b"raw photo", photo_id, batch["batch_id"], number
            )
        self.storage.complete_capture_batch(batch["batch_id"], 30)
        if accept_review:
            self.storage.decide_capture_review(session_id)
        return batch, photo_ids

    def test_only_one_active_session_per_device(self):
        first = self.storage.create_session("pi01", None)
        with self.assertRaises(ValueError):
            self.storage.create_session("pi01", None)

        self.storage.end_session(first["session_id"])
        second = self.storage.create_session("pi01", None)
        self.assertNotEqual(first["session_id"], second["session_id"])

    def test_session_effect_and_zoom_controls_are_persisted_per_photo(self):
        session = self.storage.create_session("pi01", None)
        updated = self.storage.update_session_controls(
            session["session_id"], "sepia", 1.8
        )

        self.assertEqual(updated["effect_id"], "sepia")
        self.assertEqual(updated["zoom_factor"], 1.8)

        photo = self.storage.save_photo(
            session["session_id"],
            b"jpeg bytes",
            effect_id="sepia",
            zoom_factor=1.8,
        )
        self.assertEqual(photo["effect_id"], "sepia")
        self.assertEqual(photo["zoom_factor"], 1.8)
        self.assertEqual(self.storage.get_photo(photo["photo_id"])["effect_id"], "sepia")

    def test_photo_upload_is_idempotent_and_bound_to_its_session(self):
        first_session = self.storage.create_session("pi01", None)
        photo = self.storage.save_photo(
            first_session["session_id"],
            b"jpeg bytes",
            pose_score=82,
            photo_id="a" * 32,
        )
        duplicate = self.storage.save_photo(
            first_session["session_id"],
            b"jpeg bytes",
            pose_score=82,
            photo_id="a" * 32,
        )
        self.assertEqual(photo["photo_id"], duplicate["photo_id"])
        self.assertTrue((self.storage.photo_dir / photo["file_path"]).is_file())

        self.storage.end_session(first_session["session_id"])
        second_session = self.storage.create_session("pi01", None)
        with self.assertRaises(ValueError):
            self.storage.save_photo(
                second_session["session_id"],
                b"jpeg bytes",
                photo_id="a" * 32,
            )

    def test_face_overlay_selection_and_photo_result_are_persisted(self):
        session = self.storage.create_session("pi01", None, face_overlay_id="crown")
        updated = self.storage.update_session_face_overlay(
            session["session_id"], "glasses"
        )
        self.assertEqual(updated["face_overlay_id"], "glasses")

        photo = self.storage.save_photo(
            session["session_id"],
            b"jpeg bytes",
            face_overlay_id="glasses",
            face_count=2,
            face_overlay_applied=True,
        )
        stored_photo = self.storage.get_photo(photo["photo_id"])
        self.assertEqual(stored_photo["face_overlay_id"], "glasses")
        self.assertEqual(stored_photo["face_count"], 2)
        self.assertEqual(stored_photo["face_overlay_applied"], 1)

    def test_capture_sequence_saves_correlated_raw_photo(self):
        session = self.storage.create_session("pi01", None)
        batch = self.storage.create_capture_batch(session["session_id"], 2, 10)
        photo_id = "b" * 32
        self.storage.create_capture_shot(batch["batch_id"], 1, photo_id, "command-1")

        with self.assertRaises(ValueError):
            other_session = self.storage.create_session("pi02", None)
            self.storage.save_raw_photo(
                other_session["session_id"],
                b"wrong session",
                photo_id,
                batch["batch_id"],
                1,
            )

        raw_bytes = b"original jpeg bytes"
        photo = self.storage.save_raw_photo(
            session["session_id"],
            raw_bytes,
            photo_id,
            batch["batch_id"],
            1,
        )
        self.assertTrue(photo["is_raw"])
        self.assertEqual(photo["capture_batch_id"], batch["batch_id"])
        self.assertEqual(photo["sequence_number"], 1)
        self.assertEqual((self.storage.photo_dir / photo["file_path"]).read_bytes(), raw_bytes)
        saved_batch = self.storage.get_capture_batch(batch["batch_id"])
        self.assertEqual(saved_batch["shots"][0]["status"], "completed")

    def test_capture_batch_terminal_state_cannot_be_overwritten(self):
        session = self.storage.create_session("pi01", None)
        batch = self.storage.create_capture_batch(session["session_id"], 1, 10)
        self.storage.cancel_capture_batch(batch["batch_id"])

        updated = self.storage.update_capture_batch(
            batch["batch_id"], "failed", current_shot=1
        )

        self.assertEqual(updated["status"], "cancelled")

    def test_capture_batch_cannot_complete_before_all_originals_are_saved(self):
        session = self.storage.create_session("pi01", None)
        batch = self.storage.create_capture_batch(session["session_id"], 1, 10)

        with self.assertRaises(ValueError):
            self.storage.complete_capture_batch(batch["batch_id"], 30)

        self.assertEqual(
            self.storage.get_capture_batch(batch["batch_id"])["status"],
            "countdown",
        )
        self.assertIsNone(self.storage.get_capture_review(session["session_id"]))

    def test_capture_review_allows_only_one_retake_and_can_be_accepted(self):
        session = self.storage.create_session("pi01", None)
        initial = self._complete_single_shot_batch(session["session_id"])

        review = self.storage.get_capture_review(session["session_id"])
        self.assertEqual(review["status"], "pending")
        retake = self.storage.create_capture_batch(
            session["session_id"], 1, 10, is_retake=True
        )
        self.assertEqual(retake["attempt_number"], 2)
        self.assertEqual(
            self.storage.get_capture_review(session["session_id"])["status"],
            "retake_started",
        )

        self.storage.cancel_capture_batch(retake["batch_id"])
        restored = self.storage.restore_capture_review_after_retake(
            retake["batch_id"], 30
        )
        self.assertEqual(restored["status"], "pending")
        self.assertTrue(restored["retake_used"])
        self.assertEqual(restored["batch_id"], initial["batch_id"])
        with self.assertRaises(ValueError):
            self.storage.create_capture_batch(
                session["session_id"], 1, 10, is_retake=True
            )

        accepted = self.storage.decide_capture_review(session["session_id"])
        self.assertEqual(accepted["status"], "accepted")

    def test_completed_retake_replaces_the_preview_batch(self):
        session = self.storage.create_session("pi01", None)
        initial = self._complete_single_shot_batch(session["session_id"])

        retake = self._complete_single_shot_batch(
            session["session_id"], is_retake=True
        )

        review = self.storage.get_capture_review(session["session_id"])
        self.assertEqual(review["status"], "pending")
        self.assertTrue(review["retake_used"])
        self.assertEqual(review["batch_id"], retake["batch_id"])
        self.assertNotEqual(review["batch_id"], initial["batch_id"])

    def test_capture_review_timeout_automatically_keeps_current_set(self):
        session = self.storage.create_session("pi01", None)
        self._complete_single_shot_batch(session["session_id"])
        with self.storage._lock, self.storage._connection:
            self.storage._connection.execute(
                """UPDATE capture_reviews SET decision_deadline = ?
                   WHERE session_id = ?""",
                (time.time() - 1, session["session_id"]),
            )

        review = self.storage.get_capture_review(session["session_id"])

        self.assertEqual(review["status"], "timed_out")
        self.assertIsNone(review["decision_deadline"])

    def test_photo_layout_persists_frame_and_per_slot_effects(self):
        session = self.storage.create_session("pi01", None)
        batch, photo_ids = self._complete_four_shot_batch(session["session_id"])
        slots = [
            {
                "photo_id": photo_id,
                "effect_id": effect_id,
                "face_overlay_id": overlay_id,
            }
            for photo_id, effect_id, overlay_id in zip(
                photo_ids,
                ["gray", "sepia", "warm", "original"],
                [None, "crown", None, "glasses"],
            )
        ]

        saved = self.storage.save_photo_layout(
            session["session_id"], batch["batch_id"], "classic_strip_4", slots
        )

        self.assertEqual(saved["frame_id"], "classic_strip_4")
        self.assertEqual(saved["batch_id"], batch["batch_id"])
        self.assertEqual(saved["slots"], slots)

    def test_photo_layout_requires_completed_review_and_four_distinct_photos(self):
        session = self.storage.create_session("pi01", None)
        batch, photo_ids = self._complete_four_shot_batch(
            session["session_id"], accept_review=False
        )
        slots = [
            {
                "photo_id": photo_id,
                "effect_id": "original",
                "face_overlay_id": None,
            }
            for photo_id in photo_ids
        ]

        with self.assertRaises(ValueError):
            self.storage.save_photo_layout(
                session["session_id"], batch["batch_id"], "classic_strip_4", slots
            )

        self.storage.decide_capture_review(session["session_id"])
        slots[1] = {**slots[1], "photo_id": slots[0]["photo_id"]}
        with self.assertRaises(ValueError):
            self.storage.save_photo_layout(
                session["session_id"], batch["batch_id"], "classic_strip_4", slots
            )

        slots[1] = {**slots[1], "photo_id": photo_ids[1]}
        other_session = self.storage.create_session("pi02", None)
        with self.assertRaises(ValueError):
            self.storage.save_photo_layout(
                other_session["session_id"],
                batch["batch_id"],
                "classic_strip_4",
                slots,
            )


if __name__ == "__main__":
    unittest.main()
