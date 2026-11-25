"""
shared/config.py
----------------
Đọc config.yaml một lần, dùng ở mọi nơi.

Dùng:
    from shared.config import cfg
    host = cfg["server"]["host"]
"""

import os
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    """Load YAML configuration, with an optional PHOTOBOOTH_CONFIG override."""
    config_path = Path(
        os.environ.get(
            "PHOTOBOOTH_CONFIG",
            str(PROJECT_ROOT / "config" / "config.yaml"),
        )
    ).expanduser()
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path

    with config_path.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    if not isinstance(config, dict):
        raise ValueError(f"Configuration must be a YAML mapping: {config_path}")

    text_overrides = {
        "PHOTOBOOTH_SERVER_HOST": ("server", "host"),
        "PHOTOBOOTH_CLIENT_HOST": ("server", "client_host"),
        "PHOTOBOOTH_MQTT_HOST": ("mqtt", "broker_host"),
        "PHOTOBOOTH_DEVICE_ID": ("mqtt", "device_id"),
        "PHOTOBOOTH_STATIC_TOKEN": ("server", "static_token"),
        "PHOTOBOOTH_GESTURE_MODEL": ("gesture", "model_path"),
        "PHOTOBOOTH_MQTT_USERNAME": ("mqtt", "username"),
        "PHOTOBOOTH_MQTT_PASSWORD": ("mqtt", "password"),
        "PHOTOBOOTH_MQTT_CA_CERT": ("mqtt", "tls_ca_certs"),
    }
    for variable, (section, key) in text_overrides.items():
        if variable in os.environ:
            config.setdefault(section, {})[key] = os.environ[variable]

    mqtt_tls = os.environ.get("PHOTOBOOTH_MQTT_TLS")
    if mqtt_tls is not None:
        normalized = mqtt_tls.strip().lower()
        if normalized not in {"true", "false", "1", "0"}:
            raise ValueError("PHOTOBOOTH_MQTT_TLS must be true/false or 1/0")
        config.setdefault("mqtt", {})["tls_enabled"] = normalized in {"true", "1"}
    return config


cfg = load_config()

