"""Custom tools: naming, persistence, compile validation."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from config import CONFIG_DIR

CUSTOM_TOOLS_FILE = CONFIG_DIR / 'custom_tools.json'

DEFAULT_TOOL_CODE = '''def run(ctx):
    """示例：两分区绝对差。ctx.slots[i].display 为当前显示图，.source 为原图。"""
    if ctx.slot_count < 2:
        return {"message": "需要至少 2 个分区"}
    ref = ctx.ref()
    cmp = ctx.cmp()
    if ref is None or cmp is None:
        return {"message": "请选择参考与对比分区"}
    a = ref.display.astype(ctx.np.float32)
    b = cmp.display.astype(ctx.np.float32)
    if a.shape != b.shape:
        sh_a, sh_b = a.shape[:2], b.shape[:2]
        return {"message": f"尺寸不一致: {sh_a} vs {sh_b}"}
    diff = ctx.np.abs(a - b).astype(ctx.np.uint8)
    return {
        "message": f"平均差 {diff.mean():.2f}，最大 {diff.max()}",
        "image": diff,
    }
'''

SINGLE_SLOT_TOOL_CODE = '''def run(ctx):
    """示例：单图转灰度。使用 ctx.target() 获取当前作用分区。"""
    slot = ctx.target()
    if slot is None:
        return {"message": "无可用分区"}
    img = slot.display
    gray = ctx.cv2.cvtColor(img, ctx.cv2.COLOR_RGB2GRAY)
    rgb = ctx.np.stack([gray, gray, gray], axis=2)
    return {
        "message": f"灰度化完成: {img.shape[1]}×{img.shape[0]}",
        "image": rgb,
        "apply_slot": slot.index,
    }
'''


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


@dataclass
class CustomToolRecord:
    id: str
    name: str
    code: str
    description: str = ''
    show_result_panel: bool = False  # Multi-image preview: show bottom result panel
    needs_slot_picker: bool = False  # Whether ref/compare slot pickers are needed
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    @staticmethod
    def new(
        name: str,
        code: str = SINGLE_SLOT_TOOL_CODE,
        description: str = '',
        *,
        show_result_panel: bool = False,
        needs_slot_picker: bool = False,
    ) -> 'CustomToolRecord':
        return CustomToolRecord(
            id=str(uuid.uuid4()),
            name=name,
            code=code,
            description=description,
            show_result_panel=show_result_panel,
            needs_slot_picker=needs_slot_picker,
        )


def _record_from_dict(item: dict) -> CustomToolRecord:
    return CustomToolRecord(
        id=item['id'],
        name=item['name'],
        code=item['code'],
        description=item.get('description', ''),
        show_result_panel=bool(item.get('show_result_panel', False)),
        needs_slot_picker=bool(item.get('needs_slot_picker', False)),
        created_at=item.get('created_at', _now_iso()),
        updated_at=item.get('updated_at', _now_iso()),
    )


@dataclass
class CustomToolsState:
    tools: List[CustomToolRecord] = field(default_factory=list)
    last_selected_id: str = ''

    def tool_by_id(self, tool_id: str) -> Optional[CustomToolRecord]:
        for tool in self.tools:
            if tool.id == tool_id:
                return tool
        return None


def _default_state() -> CustomToolsState:
    multi = CustomToolRecord.new(
        '绝对差示例', DEFAULT_TOOL_CODE, '多图对比，显示结果面板',
        show_result_panel=True, needs_slot_picker=True,
    )
    single = CustomToolRecord.new(
        '单图灰度示例', SINGLE_SLOT_TOOL_CODE, '单图处理，不展开结果面板',
        show_result_panel=False, needs_slot_picker=False,
    )
    return CustomToolsState(tools=[multi, single], last_selected_id=multi.id)


def load_custom_tools() -> CustomToolsState:
    try:
        if not CUSTOM_TOOLS_FILE.exists():
            state = _default_state()
            save_custom_tools(state)
            return state
        raw = json.loads(CUSTOM_TOOLS_FILE.read_text(encoding='utf-8'))
        tools = [_record_from_dict(item) for item in raw.get('tools', [])]
        if not tools:
            return _default_state()
        last_id = raw.get('last_selected_id', '')
        if not any(t.id == last_id for t in tools):
            last_id = tools[0].id
        return CustomToolsState(tools=tools, last_selected_id=last_id)
    except Exception:
        return _default_state()


def save_custom_tools(state: CustomToolsState) -> None:
    CUSTOM_TOOLS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'tools': [asdict(t) for t in state.tools],
        'last_selected_id': state.last_selected_id,
    }
    CUSTOM_TOOLS_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def validate_tool_code(code: str) -> Tuple[bool, str]:
    if not code.strip():
        return False, '代码不能为空'
    try:
        compile(code, '<custom_tool>', 'exec')
    except SyntaxError as exc:
        return False, f'语法错误: {exc}'

    from extensions.custom_tool_runtime import load_run_function

    try:
        load_run_function(code, cache_key='__validate__', force_reload=True)
    except Exception as exc:
        return False, f'加载失败: {exc}'
    return True, '编译通过'


def upsert_tool(state: CustomToolsState, record: CustomToolRecord) -> None:
    record.updated_at = _now_iso()
    for i, tool in enumerate(state.tools):
        if tool.id == record.id:
            state.tools[i] = record
            return
    state.tools.append(record)


def delete_tool(state: CustomToolsState, tool_id: str) -> None:
    state.tools = [t for t in state.tools if t.id != tool_id]
    if state.last_selected_id == tool_id:
        state.last_selected_id = state.tools[0].id if state.tools else ''
