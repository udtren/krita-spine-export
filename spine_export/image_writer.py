import os
import struct
import tempfile
from typing import Tuple

from krita import InfoObject, Krita

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
    if os.path.exists(filename):
        os.remove(filename)
    saved = _save_node(layer.node, filename, export_config, rect)
    # Krita binds Node.save() as void, so Python gets None; check the file.
    if saved is False or not os.path.exists(filename):
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
    if node.colorModel() != "RGBA":
        return None
    depth = node.colorDepth()
    if depth != "U8" and (
        depth not in _DEEP_CHANNEL_FORMATS or not _is_srgb_profile(node.colorProfile())
    ):
        return None
    raw = bytes(
        node.projectionPixelData(rect.x(), rect.y(), rect.width(), rect.height())
    )
    expected = rect.width() * rect.height() * 4
    if depth == "U8":
        if len(raw) < expected:
            return None
        rgba = bytearray(expected)
        rgba[0::4] = raw[2::4]
        rgba[1::4] = raw[1::4]
        rgba[2::4] = raw[0::4]
        rgba[3::4] = raw[3::4]
    else:
        rgba = _deep_to_rgba8(raw, depth, expected)
        if rgba is None:
            return None
    return QImage(
        bytes(rgba), rect.width(), rect.height(), _qimage_format_rgba8888()
    ).copy()


# Struct format and channel byte order of deeper RGBA depths: integer depths
# are stored BGRA like U8, float depths RGBA.
_DEEP_CHANNEL_FORMATS = {
    "U16": ("H", True),
    "F16": ("e", False),
    "F32": ("f", False),
}


def _is_srgb_profile(profile: str) -> bool:
    # Same test as Krita's PNG export: sRGB-encoded values, not linear (g10).
    name = (profile or "").lower()
    return "srgb" in name and "g10" not in name


def _deep_to_rgba8(raw: bytes, depth: str, expected: int):
    """Convert U16/F16/F32 pixel data to 8-bit RGBA without Node.save().

    Node.save() builds a temporary document and image stroke for every layer,
    which is slow and has crashed Solstice with the GPU engine.
    """
    fmt, bgr = _DEEP_CHANNEL_FORMATS[depth]
    size = struct.calcsize(fmt)
    if len(raw) < expected * size:
        return None
    values = struct.unpack("<{0}{1}".format(expected, fmt), raw[: expected * size])
    if fmt == "H":
        channels = bytes((v * 255 + 32767) // 65535 for v in values)
    else:
        channels = bytes(
            0 if not v > 0.0 else 255 if v >= 1.0 else int(v * 255.0 + 0.5)
            for v in values
        )
    if not bgr:
        return bytearray(channels)
    rgba = bytearray(expected)
    rgba[0::4] = channels[2::4]
    rgba[1::4] = channels[1::4]
    rgba[2::4] = channels[0::4]
    rgba[3::4] = channels[3::4]
    return rgba


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
            # Node.save() returns None (void binding); the isNull() check
            # below catches a failed write of the empty temporary file.
            if _save_node(flattened_node, temp_path, png_config(), rect) is False:
                raise SpineExportError("Could not render a styled layer projection.")
            image = QImage(temp_path)
            if image.isNull():
                raise SpineExportError("Could not read a styled layer projection.")
        return image, rect
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        clone.close()


def _save_node(node, filename: str, config, rect: QRect):
    # Outside batch mode Krita shows the PNG options dialog for every
    # Node.save(); the plugin already passes the configuration.
    app = Krita.instance()
    batch = app.batchmode()
    app.setBatchmode(True)
    try:
        return node.save(filename, 72, 72, config, rect)
    finally:
        app.setBatchmode(batch)


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
