import os
import tempfile
from typing import Tuple

from krita import InfoObject

from .models import ExportSettings, LayerInfo, SpineExportError

try:
    from PyQt6.QtCore import QRect, Qt
    from PyQt6.QtGui import QImage, QPainter
except ImportError:
    from PyQt5.QtCore import QRect, Qt
    from PyQt5.QtGui import QImage, QPainter


def write_layer_png(document, settings: ExportSettings, layer: LayerInfo):
    filename = (
        os.path.join(settings.images_dir, *layer.attachment_path.split("/")) + ".png"
    )
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    rect = QRect(
        layer.rect.x() - settings.padding,
        layer.rect.y() - settings.padding,
        layer.rect.width() + settings.padding * 2,
        layer.rect.height() + settings.padding * 2,
    )
    if layer.rendered_image is not None:
        if _write_rendered_png(
            layer.rendered_image,
            layer.rendered_rect,
            layer.rect,
            filename,
            settings.padding,
            layer.exported_size,
        ):
            return
        raise SpineExportError("Could not write PNG: {0}".format(filename))
    if _write_qimage_png(layer.node, filename, rect, layer.exported_size):
        return
    export_config = png_config()
    if not layer.node.save(filename, 72, 72, export_config, rect):
        raise SpineExportError("Could not write PNG: {0}".format(filename))


def write_template_png(document, settings: ExportSettings):
    base = os.path.dirname(settings.json_path)
    os.makedirs(base, exist_ok=True)
    filename = os.path.join(base, "template.png")
    if not document.exportImage(filename, png_config()):
        raise SpineExportError("Could not write template PNG: {0}".format(filename))


def png_config():
    config = InfoObject()
    config.setProperty("alpha", True)
    config.setProperty("compression", 6)
    config.setProperty("forceSRGB", False)
    config.setProperty("indexed", False)
    config.setProperty("interlaced", False)
    config.setProperty("saveSRGBProfile", False)
    return config


def node_qimage(node, rect: QRect):
    if node.colorModel() != "RGBA" or node.colorDepth() != "U8":
        return None
    raw = bytes(
        node.projectionPixelData(rect.x(), rect.y(), rect.width(), rect.height())
    )
    expected = rect.width() * rect.height() * 4
    if len(raw) < expected:
        return None
    rgba = bytearray(expected)
    rgba[0::4] = raw[2::4]
    rgba[1::4] = raw[1::4]
    rgba[2::4] = raw[0::4]
    rgba[3::4] = raw[3::4]
    return QImage(
        bytes(rgba), rect.width(), rect.height(), _qimage_format_rgba8888()
    ).copy()


def node_has_layer_style(node) -> bool:
    try:
        if node.layerStyleToAsl():
            return True
    except Exception:
        return False
    return any(node_has_layer_style(child) for child in node.childNodes())


def render_styled_node(document, node):
    clone = document.clone()
    if clone is None:
        raise SpineExportError("Could not create a temporary document for layer styles.")
    temp_path = None
    try:
        rendered_node = node.duplicate()
        if rendered_node is None:
            raise SpineExportError("Could not duplicate a layer for styled export.")
        rendered_node.setVisible(True)
        clone.rootNode().setChildNodes([rendered_node])
        clone.waitForDone()
        clone.refreshProjection()
        clone.waitForDone()
        clone.flatten()
        clone.waitForDone()

        flattened = clone.rootNode().childNodes()
        if not flattened:
            raise SpineExportError("Styled layer produced no flattened projection.")
        flattened_node = flattened[0]
        rect = flattened_node.bounds()
        if rect is None or rect.width() <= 0 or rect.height() <= 0:
            return None, rect

        image = node_qimage(flattened_node, rect)
        if image is None:
            handle, temp_path = tempfile.mkstemp(suffix=".png")
            os.close(handle)
            if not flattened_node.save(temp_path, 72, 72, png_config(), rect):
                raise SpineExportError("Could not render a styled layer projection.")
            image = QImage(temp_path)
            if image.isNull():
                raise SpineExportError("Could not read a styled layer projection.")
        return image, rect
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        clone.close()


def _write_qimage_png(node, filename: str, rect: QRect, size: Tuple[int, int]) -> bool:
    image = node_qimage(node, rect)
    if image is None:
        return False
    if size != (rect.width(), rect.height()):
        image = image.scaled(
            size[0], size[1], _qt_ignore_aspect_ratio(), _qt_smooth_transformation()
        )
    return image.save(filename, "PNG")


def _write_rendered_png(
    image: QImage,
    image_rect: QRect,
    export_rect: QRect,
    filename: str,
    padding: int,
    size: Tuple[int, int],
) -> bool:
    padded = QImage(
        export_rect.width() + padding * 2,
        export_rect.height() + padding * 2,
        _qimage_format_rgba8888(),
    )
    padded.fill(0)
    painter = QPainter(padded)
    painter.drawImage(
        image_rect.x() - export_rect.x() + padding,
        image_rect.y() - export_rect.y() + padding,
        image,
    )
    painter.end()
    if size != (padded.width(), padded.height()):
        padded = padded.scaled(
            size[0], size[1], _qt_ignore_aspect_ratio(), _qt_smooth_transformation()
        )
    return padded.save(filename, "PNG")


def _qimage_format_rgba8888():
    fmt = getattr(QImage, "Format_RGBA8888", None)
    if fmt is not None:
        return fmt
    return QImage.Format.Format_RGBA8888


def _qt_ignore_aspect_ratio():
    value = getattr(Qt, "IgnoreAspectRatio", None)
    if value is not None:
        return value
    return Qt.AspectRatioMode.IgnoreAspectRatio


def _qt_smooth_transformation():
    value = getattr(Qt, "SmoothTransformation", None)
    if value is not None:
        return value
    return Qt.TransformationMode.SmoothTransformation
