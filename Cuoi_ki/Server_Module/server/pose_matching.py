"""Load reference poses and compare them with normalized server keypoints."""

import json
import logging
import math

from pydantic import BaseModel, Field, ValidationError

from shared.config import PROJECT_ROOT
from shared.schemas import FeedbackItem, KeyPoint

logger = logging.getLogger(__name__)


class PoseTemplate(BaseModel):
    template_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    tolerance: float = Field(default=0.35, gt=0)
    keypoints: dict[str, tuple[float, float]] = Field(min_length=3)


class PoseMatcher:
    def __init__(self) -> None:
        self.directory = PROJECT_ROOT / "templates" / "poses"
        self.templates = self._load_templates()

    def _load_templates(self) -> dict[str, PoseTemplate]:
        templates = {}
        self.directory.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.directory.glob("*.json")):
            try:
                template = PoseTemplate.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValidationError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"Invalid pose template {path}: {exc}") from exc
            if template.template_id in templates:
                raise ValueError(f"Duplicate pose template ID: {template.template_id}")
            templates[template.template_id] = template
        logger.info("Loaded %s pose templates from %s", len(templates), self.directory)
        return templates

    def list_templates(self) -> list[dict[str, str]]:
        return [
            {"template_id": item.template_id, "name": item.name}
            for item in self.templates.values()
        ]

    def has_template(self, template_id: str) -> bool:
        return template_id in self.templates

    def match(
        self, template_id: str, keypoints: list[KeyPoint]
    ) -> tuple[int, list[FeedbackItem]]:
        template = self.templates[template_id]
        observed = {point.name: point for point in keypoints}
        common_names = template.keypoints.keys() & observed.keys()
        if len(common_names) < 3:
            return 0, [
                FeedbackItem(
                    body_part="body",
                    message="Keep more of your body visible to the camera",
                )
            ]

        center, scale = self._body_reference(observed)
        errors = []
        for name in common_names:
            point = observed[name]
            expected_x, expected_y = template.keypoints[name]
            actual_x = (point.x - center[0]) / scale
            actual_y = (point.y - center[1]) / scale
            distance = ((actual_x - expected_x) ** 2 + (actual_y - expected_y) ** 2) ** 0.5
            errors.append((name, distance, point.visibility))

        total_visibility = sum(visibility for _, _, visibility in errors)
        mean_error = (
            sum(distance * visibility for _, distance, visibility in errors)
            / max(total_visibility, 1e-6)
        )
        score = round(max(0, min(100, 100 * (1 - mean_error / template.tolerance))))
        if score >= 90:
            return score, []
        feedback = [
            FeedbackItem(
                body_part=name.replace("_", " "),
                message=f"Move your {name.replace('_', ' ')} closer to the reference pose",
            )
            for name, distance, _ in sorted(errors, key=lambda item: item[1], reverse=True)[:2]
        ]
        return score, feedback

    @staticmethod
    def _body_reference(
        keypoints: dict[str, KeyPoint],
    ) -> tuple[tuple[float, float], float]:
        shoulders = [keypoints[name] for name in ("left_shoulder", "right_shoulder") if name in keypoints]
        hips = [keypoints[name] for name in ("left_hip", "right_hip") if name in keypoints]
        anchors = shoulders or hips
        if len(anchors) == 2:
            center = (
                (anchors[0].x + anchors[1].x) / 2,
                (anchors[0].y + anchors[1].y) / 2,
            )
            scale = math.dist(
                (anchors[0].x, anchors[0].y),
                (anchors[1].x, anchors[1].y),
            )
            if scale > 1e-6:
                return center, scale
        points = list(keypoints.values())
        center = (
            (min(point.x for point in points) + max(point.x for point in points)) / 2,
            (min(point.y for point in points) + max(point.y for point in points)) / 2,
        )
        scale = max(
            max(point.x for point in points) - min(point.x for point in points),
            max(point.y for point in points) - min(point.y for point in points),
        )
        return center, max(scale, 1e-6)
