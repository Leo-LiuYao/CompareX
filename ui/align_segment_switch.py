"""Multi-folder grid alignment mode switch."""
from PyQt6.QtCore import pyqtSignal

from i18n import tr
from ui.segment_switch import SegmentSwitch


class AlignSegmentSwitch(SegmentSwitch):
    align_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(
            (('name', tr('align_name')), ('index', tr('align_index'))),
            initial='name',
            tooltip=tr('align_tip_enabled'),
            parent=parent,
        )
        self.value_changed.connect(self.align_changed.emit)

    def retranslate_ui(self):
        self.set_item_labels(
            (('name', tr('align_name')), ('index', tr('align_index'))),
        )

    def align(self) -> str:
        return self.value()

    def set_align(self, align: str, *, animate: bool = True, emit: bool = True):
        self.set_value(align, animate=animate, emit=emit)
