import json
import os

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_DIR_NAME = "spine_export"
_CONFIG_FILE_NAME = "preview.json"

DEFAULTS = {
    "preview_columns": 4,
    "preview_thumbnail_size": 160,
    "preview_prefixes": ["[skin"],
    "preview_window_width": 800,
    "preview_window_height": 640,
}

MIN_COLUMNS = 1
MAX_COLUMNS = 12
MIN_THUMBNAIL_SIZE = 32
MAX_THUMBNAIL_SIZE = 512
MIN_WINDOW_SIZE = 320
MAX_WINDOW_SIZE = 4096


def config_dir():
    return os.path.normpath(
        os.path.join(_PLUGIN_DIR, os.pardir, os.pardir, _CONFIG_DIR_NAME)
    )


def config_path():
    return os.path.join(config_dir(), _CONFIG_FILE_NAME)


def load_settings():
    settings = _default_settings()
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            stored = json.load(fh)
    except (OSError, ValueError):
        return settings
    if not isinstance(stored, dict):
        return settings
    for key in DEFAULTS:
        if key in stored:
            settings[key] = stored[key]
    settings["preview_columns"] = _clamp_int(
        settings["preview_columns"], MIN_COLUMNS, MAX_COLUMNS, DEFAULTS["preview_columns"]
    )
    settings["preview_thumbnail_size"] = _clamp_int(
        settings["preview_thumbnail_size"],
        MIN_THUMBNAIL_SIZE,
        MAX_THUMBNAIL_SIZE,
        DEFAULTS["preview_thumbnail_size"],
    )
    settings["preview_prefixes"] = clean_prefixes(settings["preview_prefixes"])
    for key in ("preview_window_width", "preview_window_height"):
        settings[key] = _clamp_int(
            settings[key], MIN_WINDOW_SIZE, MAX_WINDOW_SIZE, DEFAULTS[key]
        )
    return settings


def save_settings(settings):
    merged = _default_settings()
    merged.update({key: settings[key] for key in DEFAULTS if key in settings})
    merged["preview_prefixes"] = clean_prefixes(merged["preview_prefixes"])
    target = config_path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return merged


def clean_prefixes(values):
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)):
        return []
    cleaned = []
    for value in values:
        if not isinstance(value, str):
            continue
        prefix = value.strip()
        if prefix and prefix not in cleaned:
            cleaned.append(prefix)
    return cleaned


def _default_settings():
    settings = dict(DEFAULTS)
    settings["preview_prefixes"] = list(DEFAULTS["preview_prefixes"])
    return settings


def _clamp_int(value, minimum, maximum, default):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))
