try:
    from PyQt5.QtCore import QRect, Qt
    from PyQt5.QtGui import QPixmap
    from PyQt5.QtWidgets import (
        QDialog,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # Krita 6 may expose PySide6 in some builds.
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import (
        QDialog,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )

from .image_writer import node_qimage
from .settings_store import load_settings
from .tags import strip_tags

def collect_prefixed_groups(document, prefixes):
    root = document.rootNode() if document is not None else None
    if root is None or not prefixes:
        return []
    lowered = tuple(prefix.lower() for prefix in prefixes)
    groups = []
    for node in _ordered_children(root):
        if (node.name() or "").startswith("_"):
            continue
        _walk(node, [], groups, lowered)
    return groups


def _walk(node, parents, groups, prefixes):
    if node.type() != "grouplayer":
        return
    if _matches_prefix(node, prefixes):
        groups.append((node, list(parents)))
    for child in _ordered_children(node):
        _walk(child, parents + [node], groups, prefixes)


def _matches_prefix(node, prefixes):
    return (node.name() or "").strip().lower().startswith(prefixes)


def _ordered_children(node):
    return list(reversed(node.childNodes()))


class SpinePreviewDialog(QDialog):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self._applied_window_size = None
        self.setWindowTitle("Spine Skin Preview")
        self.setMinimumSize(320, 240)

        root = QVBoxLayout(self)

        self.summary = QLabel("")
        root.addWidget(self.summary)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        root.addWidget(self.scroll)

        buttons = QHBoxLayout()
        buttons.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.reload)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        buttons.addWidget(refresh_btn)
        buttons.addWidget(close_btn)
        root.addLayout(buttons)

        self.reload()

    def reload(self):
        settings = load_settings()
        columns = settings["preview_columns"]
        thumb_size = settings["preview_thumbnail_size"]
        prefixes = settings["preview_prefixes"]

        self.document.waitForDone()
        self.document.refreshProjection()
        groups = collect_prefixed_groups(self.document, prefixes)

        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(12)

        if not prefixes:
            self.summary.setText(
                "No layer prefix configured. Add one in the settings dialog."
            )
        elif not groups:
            self.summary.setText(
                "No group layers start with: {0}".format(", ".join(prefixes))
            )
        else:
            self.summary.setText(
                "{0} group(s) matching {1} - {2} column(s), {3} px thumbnails.".format(
                    len(groups), ", ".join(prefixes), columns, thumb_size
                )
            )
            for index, (node, parents) in enumerate(groups):
                cell = self._build_cell(node, parents, thumb_size)
                grid.addWidget(cell, index // columns, index % columns)
            grid.setRowStretch(grid.rowCount(), 1)
            for column in range(columns):
                grid.setColumnStretch(column, 1)

        self.scroll.setWidget(container)
        self._apply_window_size(
            settings["preview_window_width"], settings["preview_window_height"]
        )

    def _apply_window_size(self, width, height):
        if self._applied_window_size == (width, height):
            return
        self._applied_window_size = (width, height)
        self.resize(width, height)

    def _build_cell(self, node, parents, thumb_size):
        cell = QFrame()
        cell.setFrameShape(_styled_panel())
        layout = QVBoxLayout(cell)

        image_label = QLabel()
        image_label.setFixedSize(thumb_size, thumb_size)
        image_label.setAlignment(_align_center())
        pixmap = self._thumbnail(node, thumb_size)
        if pixmap is None:
            image_label.setText("(no pixels)")
        else:
            image_label.setPixmap(pixmap)
        layout.addWidget(image_label)

        title = QLabel(strip_tags(node.name()) or node.name())
        title.setWordWrap(True)
        title.setAlignment(_align_center())
        layout.addWidget(title)

        raw = QLabel(node.name())
        raw.setWordWrap(True)
        raw.setAlignment(_align_center())
        raw.setEnabled(False)
        layout.addWidget(raw)

        if parents:
            path = QLabel("/".join(parent.name() for parent in parents))
            path.setWordWrap(True)
            path.setAlignment(_align_center())
            path.setEnabled(False)
            layout.addWidget(path)

        return cell

    def _thumbnail(self, node, thumb_size):
        bounds = node.bounds()
        if bounds is None or bounds.width() <= 0 or bounds.height() <= 0:
            return None
        width, height = _fit_size(bounds.width(), bounds.height(), thumb_size)

        image = None
        try:
            image = node.thumbnail(width, height)
        except Exception:
            image = None
        if image is None or image.isNull():
            image = node_qimage(
                node, QRect(bounds.x(), bounds.y(), bounds.width(), bounds.height())
            )
        if image is None or image.isNull():
            return None
        if image.width() != width or image.height() != height:
            image = image.scaled(
                width, height, _keep_aspect_ratio(), _smooth_transformation()
            )
        return QPixmap.fromImage(image)


def _fit_size(width, height, box):
    ratio = min(box / float(width), box / float(height))
    return max(1, int(round(width * ratio))), max(1, int(round(height * ratio)))


def _styled_panel():
    value = getattr(QFrame, "StyledPanel", None)
    if value is not None:
        return value
    return QFrame.Shape.StyledPanel


def _align_center():
    value = getattr(Qt, "AlignCenter", None)
    if value is not None:
        return value
    return Qt.AlignmentFlag.AlignCenter


def _keep_aspect_ratio():
    value = getattr(Qt, "KeepAspectRatio", None)
    if value is not None:
        return value
    return Qt.AspectRatioMode.KeepAspectRatio


def _smooth_transformation():
    value = getattr(Qt, "SmoothTransformation", None)
    if value is not None:
        return value
    return Qt.TransformationMode.SmoothTransformation
