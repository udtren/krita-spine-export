import os
from typing import Tuple

from krita import InfoObject

from .models import ExportSettings, LayerInfo, SpineExportError

try:
    from PyQt5.QtCore import QRect, Qt
    from PyQt5.QtGui import QImage
except ImportError:
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QImage


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


def _write_qimage_png(node, filename: str, rect: QRect, size: Tuple[int, int]) -> bool:
    image = node_qimage(node, rect)
    if image is None:
        return False
    if size != (rect.width(), rect.height()):
        image = image.scaled(
            size[0], size[1], _qt_ignore_aspect_ratio(), _qt_smooth_transformation()
        )
    return image.save(filename, "PNG")


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
