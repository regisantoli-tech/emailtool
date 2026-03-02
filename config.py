import json
from pathlib import Path

DEFAULT_CONFIG = {
    "host": "0.0.0.0",
    "port": 8000,
    "open_browser": False
}

def config_path() -> Path:
    return Path(__file__).resolve().parent / "config.json"

def load_config() -> dict:
    path = config_path()
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        return DEFAULT_CONFIG.copy()
    try:
        return {**DEFAULT_CONFIG, **json.loads(path.read_text(encoding="utf-8"))}
    except Exception:
        return DEFAULT_CONFIG.copy()