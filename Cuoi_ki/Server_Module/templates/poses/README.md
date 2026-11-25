# Pose template format

Put one UTF-8 JSON file per reference pose in this folder. The `template_id`
must be unique. Keypoint coordinates use body-relative units: the midpoint of
the shoulders is `(0, 0)` and shoulder width is `1`. If shoulders are absent,
the matcher falls back to hip width, then the visible body bounding box.

```json
{
  "template_id": "arms-out",
  "name": "Arms out",
  "tolerance": 0.35,
  "keypoints": {
    "left_shoulder": [-0.5, 0.0],
    "right_shoulder": [0.5, 0.0],
    "left_elbow": [-1.0, 0.0],
    "right_elbow": [1.0, 0.0]
  }
}
```

The server validates templates at startup and exposes them through
`GET /api/v1/poses`. Sessions can select a template with `pose_template_id`.
