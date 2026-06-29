"""PyQt6-Fluent-Widgets theme and color integration."""
import sys
from typing import Dict

from PyQt6.QtCore import QSize, Qt, QRect, QPoint, QRectF
from PyQt6.QtGui import QColor, QIcon, QTransform, QPainter, QPalette, QFontMetrics
from PyQt6.QtWidgets import QWidget, QSizePolicy, QScrollArea, QStyle, QStyleOptionButton, QLabel
from qfluentwidgets import Theme, isDarkTheme, setTheme, setThemeColor, CheckBox
from qfluentwidgets.common.font import setFont, setFontFamilies
from qfluentwidgets.components.widgets.check_box import CheckBoxState, CheckBoxIcon
from qfluentwidgets.common.color import fallbackThemeColor

FLUENT_ACCENT = '#0078D4'

# Compact sizing: match original image_compare toolbar/sidebar proportions
COMPACT_FONT = 12
COMPACT_HEIGHT = 28
COMPACT_ICON = 14
PILL_RADIUS = 7
# Compare window toolbar (one step smaller)
DIALOG_TOOLBAR_HEIGHT = 24
DIALOG_TOOLBAR_FONT = 11

DARK_FLUENT: Dict[str, str] = {
    'background': '#202020',
    'foreground': '#FFFFFF',
    'accent': FLUENT_ACCENT,
    'success': '#107C10',
    'panel_bg': '#2B2B2B',
    'panel_border': '#3F3F3F',
    'sidebar_bg': '#252525',
    'canvas_bg': '#1A1A1A',
    'text_muted': '#ADADAD',
    'text_dim': '#8A8A8A',
    'hover_bg': 'rgba(255,255,255,0.06)',
    'icon_btn_hover': 'rgba(255, 255, 255, 0.15)',
    'selection': FLUENT_ACCENT,
}

LIGHT_FLUENT: Dict[str, str] = {
    'background': '#F3F3F3',
    'foreground': '#1A1A1A',
    'accent': FLUENT_ACCENT,
    'success': '#107C10',
    'panel_bg': '#FFFFFF',
    'panel_border': '#E5E5E5',
    'sidebar_bg': '#FAFAFA',
    'canvas_bg': '#EBEBEB',
    'text_muted': '#616161',
    'text_dim': '#9E9E9E',
    'hover_bg': 'rgba(0,0,0,0.04)',
    'icon_btn_hover': 'rgba(0, 0, 0, 0.12)',
    'selection': FLUENT_ACCENT,
}


def flip_icon_horizontal(icon: QIcon, size: int = COMPACT_ICON) -> QIcon:
    """Flip icon horizontally (e.g. rotate-right reuses FIF.ROTATE)."""
    pm = icon.pixmap(size, size)
    if pm.isNull():
        return icon
    return QIcon(pm.transformed(QTransform().scale(-1, 1)))


def make_pill_button(text: str, icon=None) -> 'QPushButton':
    """Standard QPushButton + icon (native Qt layout, avoids Fluent icon/text overlap)."""
    from PyQt6.QtWidgets import QPushButton

    btn = QPushButton(text)
    if icon is not None:
        btn._pill_fluent_icon = icon  # type: ignore[attr-defined]
        btn.setIcon(icon.icon() if hasattr(icon, 'icon') else icon)
        btn.setIconSize(QSize(COMPACT_ICON, COMPACT_ICON))
    btn.setAutoDefault(False)
    btn.setDefault(False)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return btn


def _apply_pill_icon(btn: QWidget, colors: Dict[str, str], variant: str):
    icon = getattr(btn, '_pill_fluent_icon', None)
    if icon is None or not hasattr(icon, 'icon'):
        return
    if variant == 'primary':
        btn.setIcon(icon.icon(Theme.DARK))
    elif variant == 'accent':
        btn.setIcon(icon.icon(color=QColor(colors['accent'])))
    else:
        theme = Theme.DARK if isDarkTheme() else Theme.LIGHT
        btn.setIcon(icon.icon(theme))


def apply_pill_button(btn: QWidget, colors: Dict[str, str], variant: str = 'primary'):
    """
    Pill button aligned with top bar segment switch.
    variant: primary filled | secondary outline | accent outline (compare, etc.)
    """
    btn.setFixedHeight(COMPACT_HEIGHT)
    setFont(btn, COMPACT_FONT)
    _apply_pill_icon(btn, colors, variant)
    if hasattr(btn, 'icon') and hasattr(btn, 'setIconSize'):
        ic = btn.icon()
        if ic is not None and not ic.isNull():
            btn.setIconSize(QSize(COMPACT_ICON, COMPACT_ICON))

    name = f'pillBtn_{variant}'
    btn.setObjectName(name)
    accent = colors['accent']
    r = PILL_RADIUS
    # Horizontal padding + icon/text gap handled by Qt QPushButton
    pad = "4px 12px 4px 10px"

    if variant == 'primary':
        btn.setStyleSheet(
            f"#{name} {{"
            f"  background-color: {accent}; color: #FFFFFF;"
            "  border: none;"
            f"  border-radius: {r}px; padding: {pad};"
            "}"
            f"#{name}:hover {{ background-color: #106EBE; }}"
            f"#{name}:pressed {{ background-color: #005A9E; }}"
            f"#{name}:disabled {{ background-color: {colors['panel_border']}; color: {colors['text_dim']}; }}"
        )
    elif variant == 'secondary':
        btn.setStyleSheet(
            f"#{name} {{"
            f"  background-color: {colors['panel_bg']}; color: {colors['foreground']};"
            f"  border: 1px solid {colors['panel_border']};"
            f"  border-radius: {r}px; padding: {pad};"
            "}"
            f"#{name}:hover {{"
            f"  background-color: {colors['hover_bg']};"
            f"  border-color: {colors['text_muted']};"
            "}"
            f"#{name}:pressed {{ background-color: {colors['canvas_bg']}; }}"
            f"#{name}:disabled {{ color: {colors['text_dim']}; border-color: {colors['panel_border']}; }}"
        )
    else:  # accent — primary outline, top bar Compare
        btn.setStyleSheet(
            f"#{name} {{"
            f"  background-color: {colors['panel_bg']}; color: {accent};"
            f"  border: 1px solid {accent};"
            f"  border-radius: {r}px; padding: {pad};"
            "  font-weight: 600;"
            "}"
            f"#{name}:hover {{ background-color: {accent}22; }}"
            f"#{name}:pressed {{ background-color: {accent}33; }}"
            f"#{name}:disabled {{ color: {colors['text_dim']}; border-color: {colors['panel_border']}; }}"
        )


def style_compact_button(
    btn,
    *,
    height: int = COMPACT_HEIGHT,
    font_size: int = COMPACT_FONT,
    icon_size: int = COMPACT_ICON,
):
    """Compact Fluent button (toolbar, dialogs, etc.)."""
    btn.setFixedHeight(height)
    setFont(btn, font_size)
    if hasattr(btn, 'setIconSize'):
        btn.setIconSize(QSize(icon_size, icon_size))
    if hasattr(btn, 'setAutoDefault'):
        btn.setAutoDefault(False)
        btn.setDefault(False)


def style_compact_input(
    widget: QWidget,
    *,
    height: int = COMPACT_HEIGHT,
    font_size: int = COMPACT_FONT,
):
    """Compact inputs (SpinBox, ComboBox, LineEdit, etc.)."""
    widget.setFixedHeight(height)
    setFont(widget, font_size)


def style_search_input(widget: QWidget, colors: Dict[str, str]):
    """Sidebar search: rounded border, focus highlight, Fluent sidebar style."""
    from PyQt6.QtCore import QSize

    style_compact_input(widget, height=30, font_size=COMPACT_FONT)
    bg = colors['panel_bg']
    border = colors['panel_border']
    accent = colors['accent']
    fg = colors['foreground']
    ph = colors['text_dim']
    widget.setStyleSheet(
        "SearchLineEdit {"
        f"  background-color: {bg};"
        f"  border: 1px solid {border};"
        "  border-radius: 6px;"
        "  padding: 0 4px;"
        f"  color: {fg};"
        "}"
        "SearchLineEdit:hover {"
        f"  border: 1px solid {colors['text_muted']};"
        "}"
        "SearchLineEdit:focus {"
        f"  border: 1px solid {accent};"
        "}"
        f"SearchLineEdit[placeholderText] {{ color: {ph}; }}"
    )
    if hasattr(widget, 'searchButton'):
        widget.searchButton.setIconSize(QSize(COMPACT_ICON, COMPACT_ICON))
        widget.searchButton.setFixedSize(24, 24)
    if hasattr(widget, 'clearButton'):
        widget.clearButton.setIconSize(QSize(12, 12))
        widget.clearButton.setFixedSize(20, 20)


def style_compact_checkbox(cb, font_size: int = COMPACT_FONT):
    setFont(cb, font_size)


DIALOG_CHECKBOX_INDICATOR = 14


class DialogCheckBox(CheckBox):
    """Compare window small checkbox: theme fill + checkmark when selected."""

    INDICATOR = DIALOG_CHECKBOX_INDICATOR
    RADIUS = 3.5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._label_spacing = 4

    def paintEvent(self, e):
        from PyQt6.QtGui import QFontMetrics, QPalette

        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        spacing = self._label_spacing
        fm = QFontMetrics(self.font())
        row_h = max(self.INDICATOR, fm.height())
        top = (self.height() - row_h) // 2
        ind_y = top + (row_h - self.INDICATOR) // 2
        rect = QRect(0, ind_y, self.INDICATOR, self.INDICATOR)

        painter.setPen(self._borderColor())
        painter.setBrush(self._backgroundColor())
        painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

        if not self.isEnabled():
            painter.setOpacity(0.8)

        if self.checkState() == Qt.CheckState.Checked:
            CheckBoxIcon.ACCEPT.render(painter, rect)
        elif self.checkState() == Qt.CheckState.PartiallyChecked:
            CheckBoxIcon.PARTIAL_ACCEPT.render(painter, rect)

        painter.setOpacity(1.0)
        painter.setPen(self.palette().color(QPalette.ColorRole.Text))
        painter.setFont(self.font())
        text_rect = QRect(
            self.INDICATOR + spacing, top,
            self.width() - self.INDICATOR - spacing, row_h,
        )
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())


class HorizontalScrollArea(QScrollArea):
    """Horizontal scroll only; block vertical wheel/drag."""

    def wheelEvent(self, event):
        if event.angleDelta().y() != 0 and event.angleDelta().x() == 0:
            event.ignore()
            return
        super().wheelEvent(event)

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, 0)


def _dialog_checkbox_indicator_ss(indicator: int = DIALOG_CHECKBOX_INDICATOR) -> str:
    base = (
        f"width: {indicator}px; height: {indicator}px; "
        f"border-radius: 3px;"
    )
    states = (
        "unchecked", "checked", "hover", "pressed",
        "checked:hover", "checked:pressed", "indeterminate",
    )
    return "".join(f"CheckBox::indicator:{s} {{ {base} }}" for s in states)


def _compact_checked_checkbox_colors(cb):
    """Small checkbox checked state: theme fill + visible checkmark."""
    if getattr(cb, '_compact_checkbox_patched', False):
        return
    orig_bg = cb._backgroundColor
    orig_border = cb._borderColor

    def _backgroundColor():
        state = cb._state()
        if state in {
            CheckBoxState.CHECKED,
            CheckBoxState.CHECKED_HOVER,
            CheckBoxState.CHECKED_PRESSED,
        }:
            return fallbackThemeColor(
                cb.darkCheckedColor if isDarkTheme() else cb.lightCheckedColor
            )
        return orig_bg()

    def _borderColor():
        state = cb._state()
        if state in {
            CheckBoxState.CHECKED,
            CheckBoxState.CHECKED_HOVER,
            CheckBoxState.CHECKED_PRESSED,
        }:
            return fallbackThemeColor(
                cb.darkCheckedColor if isDarkTheme() else cb.lightCheckedColor
            )
        return orig_border()

    cb._backgroundColor = _backgroundColor
    cb._borderColor = _borderColor
    cb._compact_checkbox_patched = True


def dialog_checkbox_stylesheet(
    colors: Dict[str, str],
    *,
    spacing: int = 6,
    indicator: int = DIALOG_CHECKBOX_INDICATOR,
) -> str:
    fg = colors['foreground']
    return (
        f"CheckBox {{ color: {fg}; font-size: {DIALOG_TOOLBAR_FONT}px; "
        f"spacing: 0px; min-height: {DIALOG_TOOLBAR_HEIGHT}px; "
        f"max-height: {DIALOG_TOOLBAR_HEIGHT}px; "
        f"padding: 0px; margin: 0px; }}"
        f"{_dialog_checkbox_indicator_ss(indicator)}"
    )


def apply_dialog_checkbox_theme(cb, colors: Dict[str, str], *, spacing: int = 6):
    if isinstance(cb, DialogCheckBox):
        cb._label_spacing = spacing
    cb.setStyleSheet(dialog_checkbox_stylesheet(colors, spacing=spacing))
    _compact_checked_checkbox_colors(cb)
    if isinstance(cb, DialogCheckBox):
        fit_checkbox_width(cb, spacing=spacing)


def style_dialog_checkbox(
    cb,
    font_size: int = DIALOG_TOOLBAR_FONT,
    *,
    indicator: int = DIALOG_CHECKBOX_INDICATOR,
    spacing: int = 6,
    height: int = DIALOG_TOOLBAR_HEIGHT,
):
    """Compact toolbar checkbox: smaller box, wider label spacing."""
    setFont(cb, font_size)
    cb._label_spacing = spacing
    ind_ss = _dialog_checkbox_indicator_ss(indicator)
    cb.setStyleSheet(
        f"CheckBox {{ spacing: 0px; min-height: {height}px; max-height: {height}px; "
        f"padding: 0px; margin: 0px; }}"
        f"{ind_ss}"
    )
    _compact_checked_checkbox_colors(cb)
    fit_checkbox_width(cb, font_size=font_size, indicator=indicator, spacing=spacing)


def style_dialog_toolbar_label(
    label: QLabel,
    *,
    font_size: int = DIALOG_TOOLBAR_FONT,
    height: int = DIALOG_TOOLBAR_HEIGHT,
    width: int = None,
    vcenter: bool = False,
):
    """Compact label aligned with DialogCheckBox text baseline."""
    from qfluentwidgets.common.font import setFont, getFont
    from PyQt6.QtGui import QFontMetrics

    setFont(label, font_size)
    label.setFixedHeight(height)
    label.setContentsMargins(0, 0, 0, 0)
    fm = QFontMetrics(getFont(font_size))
    if vcenter:
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        label.setStyleSheet(
            f"padding: 0px; margin: 0px; border: none; background: transparent; "
            f"font-size: {font_size}px;"
        )
    else:
        text_h = fm.ascent() + fm.descent()
        pad_top = max(0, (height - text_h) // 2)
        label.setStyleSheet(
            f"padding: {pad_top}px 0 0 0; margin: 0px; border: none; background: transparent; "
            f"font-size: {font_size}px;"
        )
    if width is not None:
        label.setFixedWidth(width)
    else:
        label.setFixedWidth(fm.horizontalAdvance(label.text()) + 4)


def apply_dialog_toolbar_label_theme(
    label: QLabel, colors: Dict[str, str], *, vcenter: bool = False,
):
    if vcenter:
        label.setStyleSheet(
            f"color: {colors['foreground']}; background: transparent; "
            f"font-size: {DIALOG_TOOLBAR_FONT}px; padding: 0px; "
            f"margin: 0px; border: none;"
        )
        return
    from qfluentwidgets.common.font import getFont
    from PyQt6.QtGui import QFontMetrics

    fm = QFontMetrics(getFont(DIALOG_TOOLBAR_FONT))
    text_h = fm.ascent() + fm.descent()
    pad_top = max(0, (DIALOG_TOOLBAR_HEIGHT - text_h) // 2)
    label.setStyleSheet(
        f"color: {colors['foreground']}; background: transparent; "
        f"font-size: {DIALOG_TOOLBAR_FONT}px; padding: {pad_top}px 0 0 0; "
        f"margin: 0px; border: none;"
    )


def fit_checkbox_width(
    cb,
    *,
    font_size: int = DIALOG_TOOLBAR_FONT,
    indicator: int = DIALOG_CHECKBOX_INDICATOR,
    spacing: int = 6,
    extra: int = 6,
    height: int = DIALOG_TOOLBAR_HEIGHT,
):
    """Fix CheckBox width to text; avoid Fluent min-width clipping."""
    from qfluentwidgets.common.font import getFont
    from PyQt6.QtGui import QFontMetrics

    fm = QFontMetrics(getFont(font_size))
    text_w = fm.horizontalAdvance(cb.text())
    cb.setFixedWidth(indicator + spacing + text_w + extra)
    cb.setFixedHeight(height)
    cb.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


def fit_compact_button_width(
    btn,
    *,
    font_size: int = DIALOG_TOOLBAR_FONT,
    padding: int = 20,
    min_width: int = 0,
):
    """Compact button width from text (compare toolbar)."""
    from qfluentwidgets.common.font import setFont, getFont
    from PyQt6.QtGui import QFontMetrics

    setFont(btn, font_size)
    fm = QFontMetrics(getFont(font_size))
    text_w = fm.horizontalAdvance(btn.text()) + padding
    hint_w = btn.sizeHint().width()
    btn.setFixedWidth(max(min_width, text_w, hint_w))


def fit_dialog_toolbar_button(
    btn,
    *,
    font_size: int = DIALOG_TOOLBAR_FONT,
    padding: int = 20,
    min_width: int = 0,
):
    """Compare toolbar PushButton: fixed height + text-based width."""
    style_compact_button(btn, height=DIALOG_TOOLBAR_HEIGHT, font_size=font_size)
    fit_compact_button_width(btn, font_size=font_size, padding=padding, min_width=min_width)


def style_dialog_combo(
    combo,
    *,
    height: int = DIALOG_TOOLBAR_HEIGHT,
    font_size: int = DIALOG_TOOLBAR_FONT,
    item_height: int = 24,
):
    """Compare ComboBox: compact height + smaller dropdown font."""
    from PyQt6.QtCore import Qt as QtCore
    from qfluentwidgets.components.widgets.combo_box import ComboBoxMenu

    style_compact_input(combo, height=height, font_size=font_size)
    combo.setFocusPolicy(QtCore.FocusPolicy.NoFocus)

    def _create_menu():
        menu = ComboBoxMenu(combo)
        menu.setItemHeight(item_height)
        menu.view.setStyleSheet(
            f"QListWidget#comboListWidget {{ font-size: {font_size}px; }}"
        )
        return menu

    combo._createComboMenu = _create_menu


def dialog_combo_stylesheet(
    colors: Dict[str, str],
    *,
    padding_left: int = 8,
    padding_right: int = 32,
) -> str:
    """Unified Fluent ComboBox style in compare window (matches crop shape dropdown)."""
    fg = colors['foreground']
    bg = colors['background']
    border = colors['panel_border']
    return (
        f"ComboBox {{ color: {fg}; background-color: {bg}; "
        f"border: 1px solid {border}; border-radius: 4px; "
        f"font-size: {DIALOG_TOOLBAR_FONT}px; "
        f"padding-left: {padding_left}px; padding-right: {padding_right}px; }}"
    )


def dialog_toolbar_button_stylesheet(colors: Dict[str, str]) -> str:
    """Compare toolbar PushButton (matches dropdown background)."""
    fg = colors['foreground']
    bg = colors['background']
    border = colors['panel_border']
    hover = colors.get('hover_bg', colors['panel_bg'])
    return (
        f"PushButton {{ color: {fg}; background-color: {bg}; "
        f"border: 1px solid {border}; border-radius: 4px; "
        f"font-size: {DIALOG_TOOLBAR_FONT}px; padding: 0 8px; }}"
        f"PushButton:hover {{ background-color: {hover}; "
        f"border-color: {colors.get('text_muted', border)}; }}"
        f"PushButton:pressed {{ background-color: {colors['panel_bg']}; }}"
        f"PushButton:disabled {{ color: {colors['text_dim']}; "
        f"background-color: {colors['panel_bg']}; border-color: {border}; }}"
    )


def style_baseline_combo(
    combo,
    labels,
    *,
    closed_width: int = 118,
    height: int = DIALOG_TOOLBAR_HEIGHT,
    font_size: int = DIALOG_TOOLBAR_FONT,
    item_height: int = 24,
):
    """Baseline column combo: fixed collapsed width, menu widened to full labels."""
    from PyQt6.QtCore import Qt as QtCore
    from PyQt6.QtGui import QFontMetrics
    from qfluentwidgets.common.font import getFont
    from qfluentwidgets.components.widgets.combo_box import ComboBoxMenu

    style_dialog_combo(combo, height=height, font_size=font_size, item_height=item_height)
    combo.setFixedWidth(closed_width)
    combo.setFocusPolicy(QtCore.FocusPolicy.NoFocus)
    fm = QFontMetrics(getFont(font_size))
    texts = labels or ['']
    menu_w = max(fm.horizontalAdvance(t) for t in texts) + 48

    def _create_menu():
        menu = ComboBoxMenu(combo)
        menu.setItemHeight(item_height)
        menu.view.setMinimumWidth(menu_w)
        menu.view.setStyleSheet(
            f"QListWidget#comboListWidget {{ font-size: {font_size}px; }}"
        )
        return menu

    combo._createComboMenu = _create_menu


def fit_dialog_combo_width(
    combo,
    texts,
    *,
    font_size: int = DIALOG_TOOLBAR_FONT,
    extra: int = 44,
    min_width: int = 52,
):
    """Set ComboBox width from longest option (avoid arrow covering text)."""
    from qfluentwidgets.common.font import getFont
    from PyQt6.QtGui import QFontMetrics

    fm = QFontMetrics(getFont(font_size))
    text_w = max(fm.horizontalAdvance(t) for t in texts)
    combo.setFixedWidth(max(min_width, text_w + extra))


def style_compact_dialog_slider(
    slider,
    *,
    handle_size: int = 16,
    height: int = DIALOG_TOOLBAR_HEIGHT,
):
    """Compare slider: smaller handle so toolbar row height stays tight."""
    from qfluentwidgets.common.color import autoFallbackThemeColor
    from qfluentwidgets.common.style_sheet import isDarkTheme

    slider.setFixedHeight(height)
    handle = slider.handle
    handle.setFixedSize(handle_size, handle_size)
    cx = handle_size // 2
    cy = handle_size // 2

    def _start_ani(radius: int):
        handle.radiusAni.stop()
        handle.radiusAni.setStartValue(handle.radius)
        handle.radiusAni.setEndValue(min(radius, max(3, handle_size // 2 - 2)))
        handle.radiusAni.start()

    def _paint_handle(event):
        painter = QPainter(handle)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        dark = isDarkTheme()
        painter.setPen(QColor(0, 0, 0, 90 if dark else 25))
        painter.setBrush(QColor(69, 69, 69) if dark else Qt.GlobalColor.white)
        painter.drawEllipse(handle.rect().adjusted(1, 1, -1, -1))
        painter.setBrush(autoFallbackThemeColor(handle.lightHandleColor, handle.darkHandleColor))
        painter.drawEllipse(QPoint(cx, cy), handle.radius, handle.radius)

    handle._startAni = _start_ani
    handle.paintEvent = _paint_handle
    handle._startAni(4)

    _orig_adjust = slider._adjustHandlePos

    def _adjust_handle_pos():
        total = max(slider.maximum() - slider.minimum(), 1)
        delta = int((slider.value() - slider.minimum()) / total * slider.grooveLength)
        hy = max(0, (slider.height() - handle.height()) // 2)
        handle.move(delta, hy)

    def _draw_horizon_groove(painter):
        w = slider.width()
        r = handle.width() / 2
        gy = slider.height() / 2.0 - 2
        painter.setBrush(QColor(255, 255, 255, 115) if isDarkTheme() else QColor(0, 0, 0, 100))
        painter.drawRoundedRect(QRectF(r, gy, w - r * 2, 4), 2, 2)
        if slider.maximum() - slider.minimum() == 0:
            return
        painter.setBrush(autoFallbackThemeColor(slider.lightGrooveColor, slider.darkGrooveColor))
        aw = (slider.value() - slider.minimum()) / (slider.maximum() - slider.minimum()) * (w - r * 2)
        painter.drawRoundedRect(QRectF(r, gy, aw, 4), 2, 2)

    slider._adjustHandlePos = _adjust_handle_pos
    slider._drawHorizonGroove = _draw_horizon_groove
    try:
        slider.valueChanged.disconnect(_orig_adjust)
    except TypeError:
        pass
    slider.valueChanged.connect(_adjust_handle_pos)
    slider._adjustHandlePos()
    enable_slider_keyboard_tune(slider)


def enable_slider_keyboard_tune(slider) -> None:
    """Focus slider on hover for keyboard ← → fine adjustment."""
    from PyQt6.QtCore import QEvent, QObject

    if getattr(slider, '_keyboard_tune_enabled', False):
        return
    slider._keyboard_tune_enabled = True
    slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    if slider.singleStep() <= 0:
        slider.setSingleStep(1)

    class _SliderKeyFilter(QObject):
        def __init__(self, target):
            super().__init__(target)
            self._target = target

        def eventFilter(self, obj, event):
            if obj is not self._target:
                return False
            if event.type() == QEvent.Type.Enter:
                self._target.setFocus(Qt.FocusReason.MouseFocusReason)
            elif event.type() == QEvent.Type.KeyPress:
                key = event.key()
                step = max(1, self._target.singleStep())
                if key == Qt.Key.Key_Left:
                    self._target.setValue(
                        max(self._target.minimum(), self._target.value() - step)
                    )
                    event.accept()
                    return True
                if key == Qt.Key.Key_Right:
                    self._target.setValue(
                        min(self._target.maximum(), self._target.value() + step)
                    )
                    event.accept()
                    return True
            return False

    filt = _SliderKeyFilter(slider)
    slider._keyboard_tune_filter = filt
    slider.installEventFilter(filt)


def sync_fluent_slider(slider, value: int):
    """Fluent Slider does not move handle under blockSignals; sync manually."""
    slider.blockSignals(True)
    slider.setValue(value)
    slider.blockSignals(False)
    if hasattr(slider, '_adjustHandlePos'):
        slider._adjustHandlePos()
    slider.update()


def compact_pivot(pivot):
    """Shrink Pivot mode switch items (default 18px font fills top bar)."""
    from qfluentwidgets.components.navigation.pivot import PivotItem

    for item in pivot.findChildren(PivotItem):
        setFont(item, COMPACT_FONT)
        item.setFixedHeight(COMPACT_HEIGHT)
    pivot.setFixedHeight(COMPACT_HEIGHT)


def setup_fluent_app():
    """Initialize Fluent theme at app startup."""
    if sys.platform == 'darwin':
        setFontFamilies(['PingFang SC', 'Helvetica Neue', 'Microsoft YaHei', 'Segoe UI'])
    else:
        setFontFamilies(['Segoe UI', 'Microsoft YaHei', 'PingFang SC'])
    setTheme(Theme.AUTO)
    setThemeColor(QColor(FLUENT_ACCENT))


def apply_fluent_theme(is_dark: bool | None = None):
    """Sync Fluent theme with built-in theme toggle."""
    if is_dark is None:
        setTheme(Theme.AUTO)
    elif is_dark:
        setTheme(Theme.DARK)
    else:
        setTheme(Theme.LIGHT)
    setThemeColor(QColor(FLUENT_ACCENT))


def get_fluent_colors() -> Dict[str, str]:
    return DARK_FLUENT if isDarkTheme() else LIGHT_FLUENT
