"""Application state persistence."""
import json
from pathlib import Path

from config import CONFIG_DIR

LAST_FOLDER_FILE = CONFIG_DIR / 'last_folder.json'
DISPLAY_PREF_FILE = CONFIG_DIR / 'compare_display.json'
LANGUAGE_FILE = CONFIG_DIR / 'language.json'


def load_last_folder_dir() -> str:
    try:
        if LAST_FOLDER_FILE.exists():
            data = json.loads(LAST_FOLDER_FILE.read_text(encoding='utf-8'))
            path = data.get('last_folder', '')
            if path and Path(path).exists():
                return path
    except Exception:
        pass
    return str(Path.home())


def save_last_folder_dir(folder_path: str):
    LAST_FOLDER_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_FOLDER_FILE.write_text(
        json.dumps({'last_folder': folder_path}, ensure_ascii=False),
        encoding='utf-8',
    )


def load_compare_display_name() -> str:
    """Last selected compare-window display name; empty string means primary screen."""
    try:
        if DISPLAY_PREF_FILE.exists():
            data = json.loads(DISPLAY_PREF_FILE.read_text(encoding='utf-8'))
            return str(data.get('screen_name', '') or '')
    except Exception:
        pass
    return ''


def save_compare_display_name(screen_name: str):
    DISPLAY_PREF_FILE.parent.mkdir(parents=True, exist_ok=True)
    DISPLAY_PREF_FILE.write_text(
        json.dumps({'screen_name': screen_name}, ensure_ascii=False),
        encoding='utf-8',
    )


def load_language() -> str:
    try:
        if LANGUAGE_FILE.exists():
            lang = json.loads(LANGUAGE_FILE.read_text(encoding='utf-8')).get('language', 'zh')
            return 'en' if lang == 'en' else 'zh'
    except Exception:
        pass
    return 'zh'


def save_language(lang: str):
    LANGUAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LANGUAGE_FILE.write_text(
        json.dumps({'language': 'en' if lang == 'en' else 'zh'}, ensure_ascii=False),
        encoding='utf-8',
    )
