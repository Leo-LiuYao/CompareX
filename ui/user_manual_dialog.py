"""User manual dialog (bilingual content in HTML helpers)."""
import sys

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QHBoxLayout
from qfluentwidgets import CaptionLabel, PrimaryPushButton

from config import APP_NAME, APP_VERSION
from i18n import tr, language
from ui.theme import get_colors


def _mod_key() -> str:
    return "⌘" if sys.platform == "darwin" else "Ctrl"


def _manual_html_zh(mod: str) -> str:
    return f"""
<h2>{APP_NAME} 用户手册</h2>
<p>版本 {APP_VERSION}</p>
<h3>1. 概述</h3>
<p>用于批量浏览、对比多组文件夹中的图片，适合算法结果对比、数据集检查。</p>
<h3>2. 导入文件夹</h3>
<ul>
<li><b>添加文件夹</b> 或 <b>{mod}+O</b>；拖入中央区域；最多 12 个文件夹</li>
<li>左侧单击切换单文件夹预览；× 或右键可移除</li>
<li>搜索框下方 <b>历史</b> 可恢复以往工作区</li>
</ul>
<h3>3. 浏览模式</h3>
<ul>
<li><b>单文件夹</b> / <b>多文件夹</b>：顶栏切换或 <b>{mod}+M</b></li>
<li><b>名称对齐</b> / <b>顺序对齐</b>：多文件夹时按文件名或顺序对齐行</li>
</ul>
<h3>4. 对比</h3>
<ul>
<li>选中图片后点 <b>对比</b> 或按 <b>空格</b>；双击单张快速对比</li>
<li>对比页可开 <b>指标</b>：选基准列，查看 PSNR/SSIM，导出宽表 CSV</li>
</ul>
<h3>5. 对比窗口</h3>
<ul>
<li>滚轮/捏合缩放；<b>R</b> 重置；<b>Shift+拖拽</b> 裁剪并导出</li>
<li><b>空格</b> 下一行，<b>B</b> 上一行；长按 <b>Tab</b> 预览下一列</li>
<li>吸管、差异图、色彩、扩展工具等见底栏开关</li>
</ul>
<h3>6. 快捷键</h3>
<table cellspacing="6"><tr><td><b>空格</b></td><td>对比 / 下一行</td></tr>
<tr><td><b>B</b></td><td>上一行</td></tr>
<tr><td><b>{mod}+M</b></td><td>单/多文件夹</td></tr>
<tr><td><b>{mod}+O</b></td><td>打开文件夹</td></tr>
<tr><td><b>R</b></td><td>重置缩放</td></tr>
<tr><td><b>Esc</b></td><td>关闭对比窗</td></tr></table>
<h3>7. 其他</h3>
<ul>
<li><b>视图</b> 菜单切换深/浅色与 <b>中文/English</b></li>
<li><b>文件 → 工作区</b> 保存与恢复对比环境</li>
</ul>
"""


def _manual_html_en(mod: str) -> str:
    return f"""
<h2>{APP_NAME} User Manual</h2>
<p>Version {APP_VERSION}</p>
<h3>1. Overview</h3>
<p>Browse and compare images across folders — ideal for algorithm outputs and dataset review.</p>
<h3>2. Import</h3>
<ul>
<li><b>Add Folder</b> or <b>{mod}+O</b>; drag folders into the center; up to 12 folders</li>
<li>Click a folder in the sidebar; use × or context menu to remove</li>
<li><b>History</b> below search restores past workspaces</li>
</ul>
<h3>3. Modes</h3>
<ul>
<li><b>Single</b> / <b>Multi</b> folder: top bar or <b>{mod}+M</b></li>
<li><b>Align by name</b> / <b>by order</b> for multi-folder rows</li>
</ul>
<h3>4. Compare</h3>
<ul>
<li>Select images, click <b>Compare</b> or press <b>Space</b>; double-click for quick view</li>
<li><b>Metrics</b> in compare window: baseline column, PSNR/SSIM overlay, CSV export</li>
</ul>
<h3>5. Compare Window</h3>
<ul>
<li>Wheel/pinch zoom; <b>R</b> reset; <b>Shift+drag</b> crop and export</li>
<li><b>Space</b> next row, <b>B</b> previous; hold <b>Tab</b> to preview next column</li>
<li>Eyedropper, diff map, color, extensions in the bottom bar</li>
</ul>
<h3>6. Shortcuts</h3>
<table cellspacing="6"><tr><td><b>Space</b></td><td>Compare / next row</td></tr>
<tr><td><b>B</b></td><td>Previous row</td></tr>
<tr><td><b>{mod}+M</b></td><td>Single/Multi</td></tr>
<tr><td><b>{mod}+O</b></td><td>Open folder</td></tr>
<tr><td><b>R</b></td><td>Reset zoom</td></tr>
<tr><td><b>Esc</b></td><td>Close compare</td></tr></table>
<h3>7. More</h3>
<ul>
<li><b>View</b> menu: theme and <b>中文/English</b></li>
<li><b>File → Workspace</b> to save/restore session</li>
</ul>
"""


class UserManualDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('user_manual'))
        self.resize(560, 640)

        colors = get_colors()
        mod = _mod_key()
        html = _manual_html_en(mod) if language() == 'en' else _manual_html_zh(mod)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = CaptionLabel(tr('user_manual_title'))
        title.setStyleSheet(
            f"color: {colors['foreground']}; font-size: 15px; font-weight: 600;",
        )
        layout.addWidget(title)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setHtml(html)
        self.browser.setStyleSheet(
            f"QTextBrowser {{ background: {colors['panel_bg']}; color: {colors['foreground']}; "
            f"border: 1px solid {colors['panel_border']}; border-radius: 6px; padding: 8px; }}"
        )
        layout.addWidget(self.browser, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = PrimaryPushButton(tr('close'))
        close_btn.setFixedWidth(96)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.setStyleSheet(f"background: {colors['background']};")

    def retranslate_ui(self):
        mod = _mod_key()
        html = _manual_html_en(mod) if language() == 'en' else _manual_html_zh(mod)
        self.setWindowTitle(tr('user_manual'))
        self.browser.setHtml(html)
