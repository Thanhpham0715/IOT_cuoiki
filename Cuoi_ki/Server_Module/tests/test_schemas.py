import unittest

from pydantic import ValidationError

from shared.schemas import (
    FrameMeta,
    LEDCommand,
    LEDRequest,
    PhotoLayoutSelection,
)


class ContractTests(unittest.TestCase):
    def test_frame_metadata_requires_positive_timestamp(self):
        with self.assertRaises(ValidationError):
            FrameMeta(session_id="session", frame_id=1, timestamp=0)

    def test_led_request_limits_brightness_and_command_owns_id(self):
        request = LEDRequest(brightness=70)
        command = LEDCommand(command_id="cmd-1", brightness=request.brightness)
        self.assertEqual(command.brightness, 70)
        with self.assertRaises(ValidationError):
            LEDRequest(brightness=101)

    def test_photo_layout_requires_four_slots(self):
        PhotoLayoutSelection(
            frame_id="classic_strip_4",
            slots=[{"photo_id": str(index)} for index in range(4)],
        )
        with self.assertRaises(ValidationError):
            PhotoLayoutSelection(
                frame_id="classic_strip_4",
                slots=[{"photo_id": "only-one"}],
            )


if __name__ == "__main__":
    unittest.main()
