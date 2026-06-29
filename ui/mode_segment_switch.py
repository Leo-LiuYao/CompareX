"""Single / multi-folder mode switch."""
from PyQt6.QtCore import pyqtSignal

from i18n import tr
from ui.segment_switch import SegmentSwitch


class ModeSegmentSwitch(SegmentSwitch):
    mode_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(
            (('single', tr('single_folder')), ('multi', tr('multi_folder'))),
            initial='single',
            tooltip=tr('mode_switch_tip'),
            parent=parent,
        )
        self.value_changed.connect(self.mode_changed.emit)

    def retranslate_ui(self):
        self.set_item_labels(
            (('single', tr('single_folder')), ('multi', tr('multi_folder'))),
            tooltip=tr('mode_switch_tip'),
        )

    def mode(self) -> str:
        return self.value()

    def set_mode(self, mode: str, *, animate: bool = True, emit: bool = True):
        self.set_value(mode, animate=animate, emit=emit)
