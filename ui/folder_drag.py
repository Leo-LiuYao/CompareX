"""Folder column drag reorder - sidebar and multi-column grid."""
from typing import Optional
from PyQt6.QtCore import QMimeData, Qt
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import QApplication, QWidget

FOLDER_DRAG_MIME = "application/x-imagecompare-folder-path"


def folder_path_from_mime(mime: QMimeData) -> Optional[str]:
    if mime.hasFormat(FOLDER_DRAG_MIME):
        raw = mime.data(FOLDER_DRAG_MIME)
        if raw:
            return bytes(raw).decode("utf-8")
    text = mime.text().strip()
    return text or None


def start_folder_drag(widget: QWidget, folder_path: str) -> None:
    drag = QDrag(widget)
    mime = QMimeData()
    mime.setData(FOLDER_DRAG_MIME, folder_path.encode("utf-8"))
    mime.setText(folder_path)
    drag.setMimeData(mime)
    drag.exec(Qt.DropAction.MoveAction)
