try:
    from PyQt6.QtCore import QRect, Qt
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtWidgets import (
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
except ImportError:
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

from .image_writer import node_qimage
from .settings_store import load_settings
from .tags import direct_tag_value, has_tag, strip_tags

_MASK_TYPES = {
    "transparencymask",
    "filtermask",
    "transformmask",
    "selectionmask",
    "colorizemask",
}


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


def _head_variants(node):
    match = _find_head_slot(node, ())
    if match is None:
        return []
    path, choices = match
    return [
        (path, tuple(index for index, _ in choices), index, child.name())
        for index, child in choices
    ]


def _find_head_slot(node, path):
    children = node.childNodes()
    for index in range(len(children) - 1, -1, -1):
        child = children[index]
        if child.type() != "grouplayer":
            continue
        child_path = path + (index,)
        if _is_head_slot(child):
            choices = _variant_children(child)
            if len(choices) > 1:
                return child_path, choices
        match = _find_head_slot(child, child_path)
        if match is not None:
            return match
    return None


def _is_head_slot(node):
    slot = direct_tag_value(node, "slot")
    return bool(slot and slot.strip().lower().endswith("head"))


def _variant_children(node):
    children = node.childNodes()
    return [
        (index, children[index])
        for index in range(len(children) - 1, -1, -1)
        if children[index].type() not in _MASK_TYPES
        and not (children[index].name() or "").startswith("_")
        and not has_tag(children[index], "ignore")
    ]


def _node_at_path(node, path):
    current = node
    current.setVisible(True)
    for index in path:
        current = current.childNodes()[index]
        current.setVisible(True)
    return current


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
            entries = []
            for node, parents in groups:
                variants = _head_variants(node)
                if variants:
                    entries.extend((node, parents, variant) for variant in variants)
                else:
                    entries.append((node, parents, None))
            self.summary.setText(
                "{0} preview(s) from {1} group(s) matching {2} - {3} column(s), "
                "{4} px thumbnails.".format(
                    len(entries),
                    len(groups),
                    ", ".join(prefixes),
                    columns,
                    thumb_size,
                )
            )
            for index, (node, parents, variant) in enumerate(entries):
                cell = self._build_cell(node, parents, thumb_size, variant)
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

    def _build_cell(self, node, parents, thumb_size, variant):
        cell = QFrame()
        cell.setFrameShape(_styled_panel())
        layout = QVBoxLayout(cell)

        image_label = QLabel()
        image_label.setAlignment(_align_center())
        pixmap = self._thumbnail(node, thumb_size, variant)
        if pixmap is None:
            image_label.setFixedSize(thumb_size, thumb_size)
            image_label.setText("(no pixels)")
        else:
            image_label.setFixedSize(
                thumb_size, min(thumb_size, _pixmap_logical_height(pixmap))
            )
            image_label.setPixmap(pixmap)
        layout.addWidget(image_label)

        title = QLabel(strip_tags(node.name()) or node.name())
        title.setWordWrap(True)
        title.setAlignment(_align_center())
        layout.addWidget(title)

        if variant is not None:
            variant_name = variant[3]
            choice = QLabel("Head: {0}".format(strip_tags(variant_name) or variant_name))
            choice.setWordWrap(True)
            choice.setAlignment(_align_center())
            layout.addWidget(choice)

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

    def _thumbnail(self, node, thumb_size, variant):
        if variant is None:
            return self._node_thumbnail(node, thumb_size)

        clone = self.document.clone()
        if clone is None:
            return None
        try:
            rendered_node = node.duplicate()
            if rendered_node is None:
                return None
            rendered_node.setVisible(True)
            if variant is not None:
                path, choice_indices, active_index, _ = variant
                head = _node_at_path(rendered_node, path)
                children = head.childNodes()
                for index in choice_indices:
                    children[index].setVisible(index == active_index)

            clone.rootNode().setChildNodes([rendered_node])
            clone.waitForDone()
            clone.refreshProjection()
            clone.waitForDone()
            clone.flatten()
            clone.waitForDone()

            flattened = clone.rootNode().childNodes()
            if not flattened:
                return None
            rendered_node = flattened[0]
            return self._node_thumbnail(rendered_node, thumb_size)
        finally:
            clone.close()

    def _node_thumbnail(self, node, thumb_size):
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


def _pixmap_logical_height(pixmap):
    logical_size = getattr(pixmap, "deviceIndependentSize", None)
    if logical_size is not None:
        return max(1, int(round(logical_size().height())))
    ratio = pixmap.devicePixelRatio()
    return max(1, int(round(pixmap.height() / ratio)))


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
