"""Background metrics computation and export for the compare view."""
from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from core.image_loader import ImageInfo, ImageLoader
from core.metrics_batch import compute_current_group_metrics, export_metrics_csv

logger = logging.getLogger(__name__)


class MetricsComputeWorker(QThread):
    finished = pyqtSignal(dict, int, list)

    def __init__(
        self,
        sources: List[Optional[np.ndarray]],
        baseline_idx: int,
        metrics: List[str],
        *,
        preview: bool = True,
    ):
        super().__init__()
        self._sources = sources
        self._baseline_idx = baseline_idx
        self._metrics = metrics
        self._preview = preview

    def run(self):
        slot_metrics = compute_current_group_metrics(
            self._sources,
            self._baseline_idx,
            self._metrics,
            preview=self._preview,
        )
        self.finished.emit(slot_metrics, self._baseline_idx, self._metrics)


class MetricsExportWorker(QThread):
    finished = pyqtSignal(int, object)

    def __init__(
        self,
        path: str,
        groups: List[List[ImageInfo]],
        baseline_idx: int,
        metrics: List[str],
        image_loader: ImageLoader,
        folder_labels: Optional[List[str]] = None,
    ):
        super().__init__()
        self._path = path
        self._groups = groups
        self._baseline_idx = baseline_idx
        self._metrics = metrics
        self._loader = image_loader
        self._folder_labels = folder_labels

    def run(self):
        try:
            count, err = export_metrics_csv(
                self._path,
                self._groups,
                self._baseline_idx,
                self._metrics,
                self._loader,
                self._folder_labels,
            )
            self.finished.emit(count, err)
        except Exception as exc:
            logger.exception('metrics export worker failed')
            self.finished.emit(0, str(exc))
