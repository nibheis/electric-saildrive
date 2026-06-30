#!/usr/bin/env python3
"""Configuration persistence for J1939 Explorer."""
import json
import os
from typing import Dict, Any

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "configuration.json")

DEFAULTS: Dict[str, Any] = {
    "socketcan_interface": "can0",
    "can_bitrate": 250000,
    "replay_delay": 500,
}


def load_config() -> Dict[str, Any]:
    """Load configuration from JSON, creating default file if missing."""
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULTS.copy())
        return DEFAULTS.copy()
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config: Dict[str, Any] = json.load(f)
    for key, default in DEFAULTS.items():
        if key not in config:
            config[key] = default
    return config


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to JSON file."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
