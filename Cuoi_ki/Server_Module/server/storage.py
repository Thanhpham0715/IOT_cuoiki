"""SQLite persistence for sessions, captured photos, and device telemetry."""

import json
import sqlite3
import threading
import time
import uuid
import logging
from pathlib import Path

from shared.config import PROJECT_ROOT, cfg

logger = logging.getLogger(__name__)


def _configured_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


class Storage:
    def __init__(self, config: dict | None = None) -> None:
        settings = (config or cfg).get("storage", {})
        self.photo_dir = _configured_path(settings.get("photo_dir", "data/photos"))
        database_path = _configured_path(settings.get("db_path", "data/photobooth.db"))
        self.photo_dir.mkdir(parents=True, exist_ok=True)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    pose_template_id TEXT,
                    effect_id TEXT NOT NULL DEFAULT 'original',
                    face_overlay_id TEXT,
                    zoom_factor REAL NOT NULL DEFAULT 1.0,
                    status TEXT NOT NULL CHECK (status IN ('active', 'completed')),
                    created_at REAL NOT NULL,
                    ended_at REAL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_session_per_device
                    ON sessions(device_id) WHERE status = 'active';
                CREATE TABLE IF NOT EXISTS photos (
                    photo_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id),
                    timestamp REAL NOT NULL,
                    file_path TEXT NOT NULL UNIQUE,
                    raw_file_path TEXT,
                    capture_batch_id TEXT,
                    sequence_number INTEGER,
                    is_raw INTEGER NOT NULL DEFAULT 0,
                    pose_score INTEGER NOT NULL DEFAULT 0,
                    effect_id TEXT NOT NULL DEFAULT 'original',
                    face_overlay_id TEXT,
                    face_count INTEGER NOT NULL DEFAULT 0,
                    face_overlay_applied INTEGER NOT NULL DEFAULT 0,
                    zoom_factor REAL NOT NULL DEFAULT 1.0
                );
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    value REAL NOT NULL,
                    timestamp REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    version TEXT,
                    updated_at REAL NOT NULL,
                    led_brightness INTEGER
                );
                CREATE TABLE IF NOT EXISTS capture_batches (
                    batch_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id),
                    device_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('countdown', 'capturing', 'completed',
                                   'failed', 'cancelled', 'interrupted')
                    ),
                    target_count INTEGER NOT NULL,
                    countdown_sec INTEGER NOT NULL,
                    current_shot INTEGER NOT NULL DEFAULT 0,
                    next_shot_at REAL,
                    last_error TEXT,
                    started_at REAL NOT NULL,
                    completed_at REAL,
                    attempt_number INTEGER NOT NULL DEFAULT 1
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_capture_batch_per_session
                    ON capture_batches(session_id)
                    WHERE status IN ('countdown', 'capturing');
                CREATE TABLE IF NOT EXISTS capture_shots (
                    batch_id TEXT NOT NULL REFERENCES capture_batches(batch_id),
                    shot_number INTEGER NOT NULL,
                    photo_id TEXT NOT NULL UNIQUE,
                    command_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK (status IN ('queued', 'completed', 'failed')),
                    error TEXT,
                    created_at REAL NOT NULL,
                    completed_at REAL,
                    PRIMARY KEY (batch_id, shot_number)
                );
                CREATE TABLE IF NOT EXISTS capture_reviews (
                    session_id TEXT PRIMARY KEY REFERENCES sessions(session_id),
                    batch_id TEXT NOT NULL REFERENCES capture_batches(batch_id),
                    status TEXT NOT NULL CHECK (
                        status IN ('pending', 'retake_started', 'accepted', 'timed_out')
                    ),
                    retake_used INTEGER NOT NULL DEFAULT 0,
                    decision_deadline REAL,
                    decided_at REAL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS photo_layouts (
                    session_id TEXT PRIMARY KEY REFERENCES sessions(session_id),
                    batch_id TEXT NOT NULL REFERENCES capture_batches(batch_id),
                    frame_id TEXT NOT NULL,
                    slots_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            capture_batch_columns = {
                row["name"]
                for row in self._connection.execute(
                    "PRAGMA table_info(capture_batches)"
                ).fetchall()
            }
            if "attempt_number" not in capture_batch_columns:
                self._connection.execute(
                    "ALTER TABLE capture_batches ADD COLUMN attempt_number INTEGER NOT NULL DEFAULT 1"
                )
            session_columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "effect_id" not in session_columns:
                self._connection.execute(
                    "ALTER TABLE sessions ADD COLUMN effect_id TEXT NOT NULL DEFAULT 'original'"
                )
            if "face_overlay_id" not in session_columns:
                self._connection.execute(
                    "ALTER TABLE sessions ADD COLUMN face_overlay_id TEXT"
                )
            if "zoom_factor" not in session_columns:
                self._connection.execute(
                    "ALTER TABLE sessions ADD COLUMN zoom_factor REAL NOT NULL DEFAULT 1.0"
                )
            photo_columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(photos)").fetchall()
            }
            if "effect_id" not in photo_columns:
                self._connection.execute(
                    "ALTER TABLE photos ADD COLUMN effect_id TEXT NOT NULL DEFAULT 'original'"
                )
            if "face_overlay_id" not in photo_columns:
                self._connection.execute(
                    "ALTER TABLE photos ADD COLUMN face_overlay_id TEXT"
                )
            if "face_count" not in photo_columns:
                self._connection.execute(
                    "ALTER TABLE photos ADD COLUMN face_count INTEGER NOT NULL DEFAULT 0"
                )
            if "face_overlay_applied" not in photo_columns:
                self._connection.execute(
                    "ALTER TABLE photos ADD COLUMN face_overlay_applied INTEGER NOT NULL DEFAULT 0"
                )
            if "zoom_factor" not in photo_columns:
                self._connection.execute(
                    "ALTER TABLE photos ADD COLUMN zoom_factor REAL NOT NULL DEFAULT 1.0"
                )
            for column, definition in (
                ("raw_file_path", "TEXT"),
                ("capture_batch_id", "TEXT"),
                ("sequence_number", "INTEGER"),
                ("is_raw", "INTEGER NOT NULL DEFAULT 0"),
            ):
                if column not in photo_columns:
                    self._connection.execute(
                        f"ALTER TABLE photos ADD COLUMN {column} {definition}"
                    )
            retention_days = int(cfg.get("storage", {}).get("telemetry_retention_days", 7))
            if retention_days < 0:
                raise ValueError("telemetry_retention_days cannot be negative")
            cutoff = time.time() - retention_days * 86400
            self._connection.execute(
                "DELETE FROM telemetry WHERE timestamp < ?",
                (cutoff,),
            )

    def create_session(
        self,
        device_id: str,
        pose_template_id: str | None,
        effect_id: str = "original",
        face_overlay_id: str | None = None,
    ) -> dict:
        session_id = str(uuid.uuid4())
        created_at = time.time()
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """INSERT INTO sessions
                       (session_id, device_id, pose_template_id, effect_id,
                        face_overlay_id, status, created_at)
                       VALUES (?, ?, ?, ?, ?, 'active', ?)""",
                    (
                        session_id,
                        device_id,
                        pose_template_id,
                        effect_id,
                        face_overlay_id,
                        created_at,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Device {device_id} already has an active session") from exc
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_active_sessions(self, device_id: str) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM sessions
                   WHERE device_id = ? AND status = 'active'
                   ORDER BY created_at DESC""",
                (device_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def end_session(self, session_id: str) -> dict | None:
        with self._lock, self._connection:
            now = time.time()
            self._connection.execute(
                """UPDATE sessions SET status = 'completed', ended_at = ?
                   WHERE session_id = ? AND status = 'active'""",
                (now, session_id),
            )
            self._connection.execute(
                """UPDATE capture_reviews SET status = 'timed_out',
                       decision_deadline = NULL, decided_at = ?, updated_at = ?
                   WHERE session_id = ?
                     AND status IN ('pending', 'retake_started')""",
                (now, now, session_id),
            )
        return self.get_session(session_id)

    def update_session_controls(
        self, session_id: str, effect_id: str, zoom_factor: float
    ) -> dict | None:
        if not 1 <= zoom_factor <= 2.5:
            raise ValueError("zoom_factor must be between 1.0 and 2.5")
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """UPDATE sessions SET effect_id = ?, zoom_factor = ?
                   WHERE session_id = ? AND status = 'active'""",
                (effect_id, zoom_factor, session_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_session(session_id)

    def update_session_face_overlay(
        self, session_id: str, face_overlay_id: str | None
    ) -> dict | None:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """UPDATE sessions SET face_overlay_id = ?
                   WHERE session_id = ? AND status = 'active'""",
                (face_overlay_id, session_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_session(session_id)

    def create_capture_batch(
        self,
        session_id: str,
        target_count: int,
        countdown_sec: int,
        is_retake: bool = False,
    ) -> dict:
        if not 1 <= target_count <= 8:
            raise ValueError("target_count must be between 1 and 8")
        if not 1 <= countdown_sec <= 30:
            raise ValueError("countdown_sec must be between 1 and 30")
        if is_retake:
            self.get_capture_review(session_id)
        batch_id = str(uuid.uuid4())
        started_at = time.time()
        with self._lock, self._connection:
            session = self._connection.execute(
                """SELECT device_id FROM sessions
                   WHERE session_id = ? AND status = 'active'""",
                (session_id,),
            ).fetchone()
            if session is None:
                raise ValueError("Session is not active")
            attempt_number = 1
            review = self._connection.execute(
                "SELECT * FROM capture_reviews WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if is_retake:
                if (
                    review is None
                    or review["status"] != "pending"
                    or review["retake_used"]
                ):
                    raise ValueError("No unused retake is available")
                if (
                    review["decision_deadline"] is not None
                    and review["decision_deadline"] <= started_at
                ):
                    raise ValueError("Retake decision has timed out")
                attempt_number = 2
                self._connection.execute(
                    """UPDATE capture_reviews SET status = 'retake_started',
                           retake_used = 1, decision_deadline = NULL,
                           decided_at = NULL, updated_at = ?
                       WHERE session_id = ? AND status = 'pending'
                         AND retake_used = 0""",
                    (started_at, session_id),
                )
            elif review is not None:
                raise ValueError("The initial capture set has already completed")
            try:
                self._connection.execute(
                    """INSERT INTO capture_batches
                       (batch_id, session_id, device_id, status, target_count,
                        countdown_sec, started_at, attempt_number)
                       VALUES (?, ?, ?, 'countdown', ?, ?, ?, ?)""",
                    (
                        batch_id,
                        session_id,
                        session["device_id"],
                        target_count,
                        countdown_sec,
                        started_at,
                        attempt_number,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("A capture sequence is already active") from exc
        batch = self.get_capture_batch(batch_id)
        if batch is None:
            raise RuntimeError(f"Capture batch metadata missing after creating {batch_id}")
        return batch

    def get_capture_batch(self, batch_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM capture_batches WHERE batch_id = ?", (batch_id,)
            ).fetchone()
            if row is None:
                return None
            batch = dict(row)
            shots = self._connection.execute(
                """SELECT shot_number, photo_id, command_id, status, error,
                          created_at, completed_at
                   FROM capture_shots WHERE batch_id = ? ORDER BY shot_number""",
                (batch_id,),
            ).fetchall()
        batch["shots"] = [dict(shot) for shot in shots]
        return batch

    def get_latest_capture_batch(self, session_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                """SELECT batch_id FROM capture_batches
                   WHERE session_id = ? ORDER BY started_at DESC LIMIT 1""",
                (session_id,),
            ).fetchone()
        return self.get_capture_batch(row["batch_id"]) if row else None

    def get_active_capture_batch(self, session_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                """SELECT batch_id FROM capture_batches
                   WHERE session_id = ? AND status IN ('countdown', 'capturing')
                   ORDER BY started_at DESC LIMIT 1""",
                (session_id,),
            ).fetchone()
        return self.get_capture_batch(row["batch_id"]) if row else None

    def get_capture_review(self, session_id: str) -> dict | None:
        now = time.time()
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM capture_reviews WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if (
                row is not None
                and row["status"] == "pending"
                and row["decision_deadline"] is not None
                and row["decision_deadline"] <= now
            ):
                with self._connection:
                    self._connection.execute(
                        """UPDATE capture_reviews SET status = 'timed_out',
                               decision_deadline = NULL, decided_at = ?, updated_at = ?
                           WHERE session_id = ? AND status = 'pending'
                             AND decision_deadline <= ?""",
                        (now, now, session_id, now),
                    )
                row = self._connection.execute(
                    "SELECT * FROM capture_reviews WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
        if row is None:
            return None
        review = dict(row)
        review["retake_used"] = bool(review["retake_used"])
        return review

    def decide_capture_review(self, session_id: str) -> dict | None:
        now = time.time()
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE capture_reviews SET status = 'accepted',
                       decision_deadline = NULL, decided_at = ?, updated_at = ?
                   WHERE session_id = ? AND status = 'pending'
                     AND decision_deadline > ?""",
                (now, now, session_id, now),
            )
        return self.get_capture_review(session_id)

    def get_photo_layout(self, session_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM photo_layouts WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        layout = dict(row)
        layout["slots"] = json.loads(layout.pop("slots_json"))
        return layout

    def save_photo_layout(
        self,
        session_id: str,
        batch_id: str,
        frame_id: str,
        slots: list[dict],
    ) -> dict:
        if len(slots) != 4:
            raise ValueError("A photo layout must contain exactly four slots")
        photo_ids = [slot["photo_id"] for slot in slots]
        if len(set(photo_ids)) != 4:
            raise ValueError("Each photo can be selected only once")

        now = time.time()
        with self._lock, self._connection:
            review = self._connection.execute(
                """SELECT batch_id, status FROM capture_reviews
                   WHERE session_id = ?""",
                (session_id,),
            ).fetchone()
            if (
                review is None
                or review["status"] not in {"accepted", "timed_out"}
                or review["batch_id"] != batch_id
            ):
                raise ValueError("The capture review must be completed first")

            batch = self._connection.execute(
                """SELECT status FROM capture_batches
                   WHERE batch_id = ? AND session_id = ?""",
                (batch_id, session_id),
            ).fetchone()
            if batch is None or batch["status"] != "completed":
                raise ValueError("The selected capture batch is not complete")

            placeholders = ",".join("?" for _ in photo_ids)
            photos = self._connection.execute(
                f"""SELECT photo_id FROM photos
                    WHERE session_id = ? AND capture_batch_id = ?
                      AND is_raw = 1 AND photo_id IN ({placeholders})""",
                (session_id, batch_id, *photo_ids),
            ).fetchall()
            if len(photos) != 4:
                raise ValueError("All four selected photos must belong to this set")

            self._connection.execute(
                """INSERT INTO photo_layouts
                   (session_id, batch_id, frame_id, slots_json, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET
                       batch_id = excluded.batch_id,
                       frame_id = excluded.frame_id,
                       slots_json = excluded.slots_json,
                       updated_at = excluded.updated_at""",
                (
                    session_id,
                    batch_id,
                    frame_id,
                    json.dumps(slots, separators=(",", ":")),
                    now,
                ),
            )
        layout = self.get_photo_layout(session_id)
        if layout is None:
            raise RuntimeError(f"Photo layout missing after saving for {session_id}")
        return layout

    def restore_capture_review_after_retake(
        self, batch_id: str, timeout_sec: int
    ) -> dict | None:
        if not 30 <= timeout_sec <= 60:
            raise ValueError("retake decision timeout must be between 30 and 60 seconds")
        now = time.time()
        with self._lock, self._connection:
            batch = self._connection.execute(
                """SELECT session_id, attempt_number FROM capture_batches
                   WHERE batch_id = ?""",
                (batch_id,),
            ).fetchone()
            if batch is None or batch["attempt_number"] != 2:
                return None
            session = self._connection.execute(
                "SELECT status FROM sessions WHERE session_id = ?",
                (batch["session_id"],),
            ).fetchone()
            active = session is not None and session["status"] == "active"
            deadline = now + timeout_sec if active else None
            self._connection.execute(
                """UPDATE capture_reviews SET status = ?, decision_deadline = ?,
                       decided_at = ?, updated_at = ?
                   WHERE session_id = ? AND status = 'retake_started'""",
                (
                    "pending" if active else "timed_out",
                    deadline,
                    None if active else now,
                    now,
                    batch["session_id"],
                ),
            )
        return self.get_capture_review(batch["session_id"])

    def complete_capture_batch(
        self, batch_id: str, review_timeout_sec: int
    ) -> dict | None:
        if not 30 <= review_timeout_sec <= 60:
            raise ValueError("retake decision timeout must be between 30 and 60 seconds")
        now = time.time()
        deadline = now + review_timeout_sec
        with self._lock, self._connection:
            batch = self._connection.execute(
                """SELECT session_id, attempt_number, target_count FROM capture_batches
                   WHERE batch_id = ? AND status IN ('countdown', 'capturing')""",
                (batch_id,),
            ).fetchone()
            if batch is None:
                return self.get_capture_batch(batch_id)
            saved_shots = self._connection.execute(
                """SELECT COUNT(*) AS count FROM capture_shots cs
                   JOIN photos p ON p.photo_id = cs.photo_id
                   WHERE cs.batch_id = ? AND cs.status = 'completed'
                     AND p.is_raw = 1""",
                (batch_id,),
            ).fetchone()["count"]
            if saved_shots != batch["target_count"]:
                raise ValueError(
                    "Capture sequence cannot complete before all raw photos are saved"
                )

            self._connection.execute(
                """UPDATE capture_batches SET status = 'completed',
                       next_shot_at = NULL, last_error = NULL, completed_at = ?
                   WHERE batch_id = ? AND status IN ('countdown', 'capturing')""",
                (now, batch_id),
            )
            if batch["attempt_number"] == 1:
                self._connection.execute(
                    """INSERT INTO capture_reviews
                       (session_id, batch_id, status, retake_used,
                        decision_deadline, updated_at)
                       VALUES (?, ?, 'pending', 0, ?, ?)""",
                    (batch["session_id"], batch_id, deadline, now),
                )
            else:
                cursor = self._connection.execute(
                    """UPDATE capture_reviews SET batch_id = ?, status = 'pending',
                           decision_deadline = ?, decided_at = NULL, updated_at = ?
                       WHERE session_id = ? AND status = 'retake_started'
                         AND retake_used = 1""",
                    (batch_id, deadline, now, batch["session_id"]),
                )
                if cursor.rowcount == 0:
                    raise ValueError("Retake review state is missing")
        return self.get_capture_batch(batch_id)

    def create_capture_shot(
        self, batch_id: str, shot_number: int, photo_id: str, command_id: str
    ) -> None:
        photo_id = str(uuid.UUID(photo_id))
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO capture_shots
                   (batch_id, shot_number, photo_id, command_id, status, created_at)
                   VALUES (?, ?, ?, ?, 'queued', ?)""",
                (batch_id, shot_number, photo_id, command_id, time.time()),
            )

    def get_capture_shot_by_photo_id(self, photo_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM capture_shots WHERE photo_id = ?", (photo_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_capture_shot(
        self, photo_id: str, status: str, error: str | None = None
    ) -> None:
        if status not in {"queued", "completed", "failed"}:
            raise ValueError(f"Unsupported capture shot status: {status}")
        completed_at = time.time() if status in {"completed", "failed"} else None
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE capture_shots SET status = ?, error = ?, completed_at = ?
                   WHERE photo_id = ?""",
                (status, error, completed_at, photo_id),
            )

    def update_capture_batch(
        self,
        batch_id: str,
        status: str,
        current_shot: int,
        next_shot_at: float | None = None,
        last_error: str | None = None,
    ) -> dict | None:
        allowed_statuses = {
            "countdown",
            "capturing",
            "failed",
            "cancelled",
            "interrupted",
        }
        if status not in allowed_statuses:
            raise ValueError(f"Unsupported capture batch status: {status}")
        completed_at = (
            time.time()
            if status in {"failed", "cancelled", "interrupted"}
            else None
        )
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE capture_batches SET status = ?, current_shot = ?,
                       next_shot_at = ?, last_error = ?, completed_at = ?
                   WHERE batch_id = ?
                     AND status IN ('countdown', 'capturing')""",
                (
                    status,
                    current_shot,
                    next_shot_at,
                    last_error,
                    completed_at,
                    batch_id,
                ),
            )
        return self.get_capture_batch(batch_id)

    def cancel_capture_batch(self, batch_id: str) -> dict | None:
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE capture_batches SET status = 'cancelled',
                       next_shot_at = NULL, last_error = 'Cancelled by operator',
                       completed_at = ?
                   WHERE batch_id = ? AND status IN ('countdown', 'capturing')""",
                (time.time(), batch_id),
            )
        return self.get_capture_batch(batch_id)

    def interrupt_active_capture_batches(self) -> None:
        with self._lock, self._connection:
            now = time.time()
            review_timeout_sec = int(
                cfg.get("capture_sequence", {}).get(
                    "retake_decision_timeout_sec", 30
                )
            )
            self._connection.execute(
                """UPDATE capture_batches SET status = 'interrupted',
                       next_shot_at = NULL,
                       last_error = 'Server restarted before sequence completed',
                       completed_at = ?
                   WHERE status IN ('countdown', 'capturing')""",
                (now,),
            )
            self._connection.execute(
                """UPDATE capture_reviews SET status = 'pending',
                       decision_deadline = ?, decided_at = NULL, updated_at = ?
                   WHERE status = 'retake_started'""",
                (now + review_timeout_sec, now),
            )
            self._connection.execute(
                """UPDATE capture_shots SET status = 'failed',
                       error = 'Server restarted before photo upload completed',
                       completed_at = ?
                   WHERE status = 'queued'
                     AND batch_id IN (
                         SELECT batch_id FROM capture_batches WHERE status = 'interrupted'
                     )""",
                (now,),
            )

    def save_photo(
        self,
        session_id: str,
        image: bytes,
        pose_score: int = 0,
        photo_id: str | None = None,
        effect_id: str = "original",
        zoom_factor: float = 1.0,
        face_overlay_id: str | None = None,
        face_count: int = 0,
        face_overlay_applied: bool = False,
        raw_image: bytes | None = None,
        raw_extension: str = "jpg",
    ) -> dict:
        if not 1 <= zoom_factor <= 2.5:
            raise ValueError("zoom_factor must be between 1.0 and 2.5")
        if face_count < 0:
            raise ValueError("face_count cannot be negative")
        photo_id = str(uuid.UUID(photo_id)) if photo_id else str(uuid.uuid4())
        if raw_extension not in {"jpg", "png"}:
            raise ValueError("raw_extension must be jpg or png")
        timestamp = time.time()
        filename = f"{photo_id}.jpg"
        destination = self.photo_dir / filename
        raw_relative_path = None
        raw_destination = None
        if raw_image is not None:
            session_folder = str(uuid.UUID(session_id))
            raw_relative_path = str(
                Path("raw") / session_folder / f"{photo_id}.{raw_extension}"
            )
            raw_destination = self.photo_dir / raw_relative_path
        with self._lock:
            existing = self._connection.execute(
                "SELECT session_id FROM photos WHERE photo_id = ?", (photo_id,)
            ).fetchone()
            if existing:
                if existing["session_id"] != session_id:
                    raise ValueError("Photo ID is already associated with another session")
                return self.get_photo(photo_id)

            try:
                destination.write_bytes(image)
                if raw_destination is not None and raw_image is not None:
                    raw_destination.parent.mkdir(parents=True, exist_ok=True)
                    raw_destination.write_bytes(raw_image)
                with self._connection:
                    self._connection.execute(
                        """INSERT INTO photos
                           (photo_id, session_id, timestamp, file_path, raw_file_path,
                            pose_score,
                            effect_id, zoom_factor, face_overlay_id, face_count,
                            face_overlay_applied)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            photo_id,
                            session_id,
                            timestamp,
                            filename,
                            raw_relative_path,
                            pose_score,
                            effect_id,
                            zoom_factor,
                            face_overlay_id,
                            face_count,
                            int(face_overlay_applied),
                        ),
                    )
            except (OSError, sqlite3.Error):
                for path in (destination, raw_destination):
                    if path is not None:
                        try:
                            path.unlink(missing_ok=True)
                        except OSError:
                            logger.exception("Could not remove incomplete photo file %s", path)
                raise
        session = self.get_session(session_id)
        return {
            "photo_id": photo_id,
            "session_id": session_id,
            "pose_template_id": session["pose_template_id"] if session else None,
            "effect_id": effect_id,
            "face_overlay_id": face_overlay_id,
            "face_count": face_count,
            "face_overlay_applied": face_overlay_applied,
            "zoom_factor": zoom_factor,
            "timestamp": timestamp,
            "file_path": filename,
            "raw_file_path": raw_relative_path,
            "raw_available": raw_relative_path is not None,
            "is_raw": False,
            "capture_batch_id": None,
            "sequence_number": None,
            "pose_score": pose_score,
        }

    def save_raw_photo(
        self,
        session_id: str,
        image: bytes,
        photo_id: str,
        batch_id: str,
        sequence_number: int,
        pose_score: int = 0,
        extension: str = "jpg",
    ) -> dict:
        if not 1 <= sequence_number <= 8:
            raise ValueError("sequence_number must be between 1 and 8")
        if extension not in {"jpg", "png"}:
            raise ValueError("Raw photo extension must be jpg or png")
        photo_id = str(uuid.UUID(photo_id))
        session_id = str(uuid.UUID(session_id))
        batch_id = str(uuid.UUID(batch_id))
        relative_path = str(
            Path("raw")
            / session_id
            / batch_id
            / f"raw_{sequence_number:02}.{extension}"
        )
        destination = self.photo_dir / relative_path
        timestamp = time.time()
        with self._lock:
            shot = self._connection.execute(
                """SELECT cs.photo_id, cb.session_id FROM capture_shots cs
                   JOIN capture_batches cb USING (batch_id)
                   WHERE cs.batch_id = ? AND cs.shot_number = ? AND cs.photo_id = ?""",
                (batch_id, sequence_number, photo_id),
            ).fetchone()
            if shot is None or shot["session_id"] != session_id:
                raise ValueError("Raw photo does not match a capture sequence shot")
            existing = self._connection.execute(
                "SELECT session_id FROM photos WHERE photo_id = ?", (photo_id,)
            ).fetchone()
            if existing:
                if existing["session_id"] != session_id:
                    raise ValueError("Photo ID is already associated with another session")
                return self.get_photo(photo_id)

            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(image)
                with self._connection:
                    self._connection.execute(
                        """INSERT INTO photos
                           (photo_id, session_id, timestamp, file_path, raw_file_path,
                            capture_batch_id, sequence_number, is_raw, pose_score,
                            effect_id, zoom_factor)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, 'original', 1.0)""",
                        (
                            photo_id,
                            session_id,
                            timestamp,
                            relative_path,
                            relative_path,
                            batch_id,
                            sequence_number,
                            pose_score,
                        ),
                    )
                    self._connection.execute(
                        """UPDATE capture_shots SET status = 'completed', error = NULL,
                               completed_at = ?
                           WHERE batch_id = ? AND shot_number = ? AND photo_id = ?""",
                        (timestamp, batch_id, sequence_number, photo_id),
                    )
            except (OSError, sqlite3.Error):
                try:
                    destination.unlink(missing_ok=True)
                except OSError:
                    logger.exception("Could not remove incomplete raw photo %s", destination)
                raise
        photo = self.get_photo(photo_id)
        if photo is None:
            raise RuntimeError(f"Raw photo metadata missing after saving {photo_id}")
        return photo

    def get_photo(self, photo_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                """SELECT p.*, s.pose_template_id FROM photos p
                   JOIN sessions s USING (session_id) WHERE p.photo_id = ?""",
                (photo_id,),
            ).fetchone()
        return self._photo_dict(row) if row else None

    def list_photos(self, session_id: str | None = None) -> list[dict]:
        query = """SELECT p.*, s.pose_template_id FROM photos p
                   JOIN sessions s USING (session_id)"""
        parameters: tuple = ()
        if session_id:
            query += " WHERE p.session_id = ?"
            parameters = (session_id,)
        query += " ORDER BY p.timestamp DESC"
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return [self._photo_dict(row) for row in rows]

    @staticmethod
    def _photo_dict(row: sqlite3.Row) -> dict:
        photo = dict(row)
        photo["raw_available"] = photo.get("raw_file_path") is not None
        photo["is_raw"] = bool(photo.get("is_raw", False))
        photo["face_overlay_applied"] = bool(
            photo.get("face_overlay_applied", False)
        )
        return photo

    def record_telemetry(self, device_id: str, metric: str, value: float, timestamp: float) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO telemetry (device_id, metric, value, timestamp) VALUES (?, ?, ?, ?)",
                (device_id, metric, value, timestamp),
            )

    def list_telemetry(self, device_id: str | None = None, limit: int = 100) -> list[dict]:
        query = "SELECT device_id, metric, value, timestamp FROM telemetry"
        parameters: tuple = ()
        if device_id:
            query += " WHERE device_id = ?"
            parameters = (device_id,)
        query += " ORDER BY timestamp DESC LIMIT ?"
        parameters += (limit,)
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def update_device(self, device_id: str, status: str, version: str | None = None) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO devices (device_id, status, version, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(device_id) DO UPDATE SET status = excluded.status,
                       version = excluded.version, updated_at = excluded.updated_at""",
                (device_id, status, version, time.time()),
            )

    def update_led(self, device_id: str, brightness: int) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO devices (device_id, status, updated_at, led_brightness)
                   VALUES (?, 'unknown', ?, ?)
                   ON CONFLICT(device_id) DO UPDATE SET
                       led_brightness = excluded.led_brightness""",
                (device_id, time.time(), brightness),
            )

    def connected_devices(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS count FROM devices WHERE status = 'online'"
            ).fetchone()
        return int(row["count"])

    def close(self) -> None:
        with self._lock:
            self._connection.close()
