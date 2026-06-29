"""Workspace persistence: folder list, mode, compare position, etc."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from config import CONFIG_DIR
from i18n import tr

logger = logging.getLogger(__name__)

WORKSPACE_FILE = CONFIG_DIR / 'workspace.json'
WORKSPACE_HISTORY_FILE = CONFIG_DIR / 'workspace_history.json'
MAX_HISTORY = 12


@dataclass
class WorkspaceState:
    folders: List[str] = field(default_factory=list)
    mode: str = 'single'
    grid_align: str = 'name'
    compare_row_index: int = 0
    active_folder_path: str = ''
    excluded_paths: List[str] = field(default_factory=list)
    compare_excluded_folders: List[str] = field(default_factory=list)
    saved_at: str = ''

    @classmethod
    def from_dict(cls, data: dict) -> 'WorkspaceState':
        return cls(
            folders=[str(p) for p in data.get('folders', []) if p],
            mode=str(data.get('mode', 'single') or 'single'),
            grid_align=str(data.get('grid_align', 'name') or 'name'),
            compare_row_index=int(data.get('compare_row_index', 0) or 0),
            active_folder_path=str(data.get('active_folder_path', '') or ''),
            excluded_paths=[str(p) for p in data.get('excluded_paths', [])],
            compare_excluded_folders=[
                str(p) for p in data.get('compare_excluded_folders', [])
            ],
            saved_at=str(data.get('saved_at', '') or ''),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_workspace(state: WorkspaceState) -> None:
    state.saved_at = _now_iso()
    WORKSPACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    WORKSPACE_FILE.write_text(
        json.dumps(asdict(state), ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    _append_history(state)


def load_workspace() -> Optional[WorkspaceState]:
    try:
        if WORKSPACE_FILE.exists():
            data = json.loads(WORKSPACE_FILE.read_text(encoding='utf-8'))
            return WorkspaceState.from_dict(data)
    except Exception as exc:
        logger.warning('load workspace failed: %s', exc)
    return None


def clear_workspace() -> None:
    for path in (WORKSPACE_FILE, WORKSPACE_HISTORY_FILE):
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            logger.warning('clear workspace %s: %s', path, exc)


def _append_history(state: WorkspaceState) -> None:
    history = load_workspace_history()
    payload = asdict(state)
    folders_key = tuple(state.folders)
    history = [h for h in history if tuple(h.get('folders', [])) != folders_key]
    history.insert(0, payload)
    history = history[:MAX_HISTORY]
    try:
        WORKSPACE_HISTORY_FILE.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
    except OSError as exc:
        logger.warning('save workspace history failed: %s', exc)


def load_workspace_history() -> List[dict]:
    try:
        if WORKSPACE_HISTORY_FILE.exists():
            data = json.loads(WORKSPACE_HISTORY_FILE.read_text(encoding='utf-8'))
            if isinstance(data, list):
                return data
    except Exception as exc:
        logger.warning('load workspace history failed: %s', exc)
    return []


def valid_folder_paths(paths: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in paths:
        p = Path(raw)
        if p.is_dir() and str(p) not in seen:
            out.append(str(p))
            seen.add(str(p))
    return out


def load_workspace_history_states() -> List[WorkspaceState]:
    return [WorkspaceState.from_dict(item) for item in load_workspace_history()]


def save_workspace_history_raw(items: List[dict]) -> None:
    WORKSPACE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    WORKSPACE_HISTORY_FILE.write_text(
        json.dumps(items[:MAX_HISTORY], ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def delete_workspace_history_at(index: int) -> bool:
    history = load_workspace_history()
    if index < 0 or index >= len(history):
        return False
    history.pop(index)
    save_workspace_history_raw(history)
    return True


def format_workspace_label(state: WorkspaceState, index: int = 0) -> str:
    names = [Path(p).name for p in state.folders[:4]]
    if len(state.folders) > 4:
        names.append('…')
    folder_part = ', '.join(names) if names else tr('workspace_empty_folders')
    mode = tr('multi_folder') if state.mode == 'multi' else tr('single_folder')
    align = tr('align_index') if state.grid_align == 'index' else tr('align_name')
    when = ''
    if state.saved_at:
        when = state.saved_at.replace('T', ' ')[:16]
    row = state.compare_row_index + 1
    return tr(
        'workspace_history_item',
        index=index + 1,
        when=when or '—',
        folders=folder_part,
        count=len(state.folders),
        mode=mode,
        align=align,
        row=row,
    )
