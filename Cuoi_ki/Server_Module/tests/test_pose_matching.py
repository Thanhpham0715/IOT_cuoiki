import unittest

from server.pose_matching import PoseMatcher, PoseTemplate
from shared.schemas import KeyPoint


class PoseMatcherTests(unittest.TestCase):
    def test_matching_pose_scores_aligned_body_relative_keypoints(self):
        matcher = PoseMatcher()
        matcher.templates = {
            "arms-out": PoseTemplate(
                template_id="arms-out",
                name="Arms out",
                keypoints={
                    "left_shoulder": (-0.5, 0.0),
                    "right_shoulder": (0.5, 0.0),
                    "left_elbow": (-1.0, 0.0),
                    "right_elbow": (1.0, 0.0),
                },
            )
        }
        keypoints = [
            KeyPoint(name="left_shoulder", x=0.4, y=0.3, visibility=0.95),
            KeyPoint(name="right_shoulder", x=0.6, y=0.3, visibility=0.95),
            KeyPoint(name="left_elbow", x=0.3, y=0.3, visibility=0.9),
            KeyPoint(name="right_elbow", x=0.7, y=0.3, visibility=0.9),
        ]

        score, feedback = matcher.match("arms-out", keypoints)

        self.assertEqual(score, 100)
        self.assertEqual(feedback, [])


if __name__ == "__main__":
    unittest.main()
