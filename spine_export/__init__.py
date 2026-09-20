from krita import Krita, Extension

try:
    from PyQt6.QtWidgets import QMessageBox
except ImportError:
    from PyQt5.QtWidgets import QMessageBox

from .dialog import SpineExportDialog
from .preview_dialog import SpinePreviewDialog
from .settings_dialog import SpineSettingsDialog


class KritaSpineExtension(Extension):
    def __init__(self, parent):
        super().__init__(parent)
        self._preview_dialog = None

    def setup(self):
        pass

    def createActions(self, window):
        action = window.createAction(
            "spine_export",
            "Export to Spine...",
            "tools/scripts",
        )
        action.triggered.connect(self._show_export_dialog)

        preview_action = window.createAction(
            "spine_export_show_preview_thumbnail",
            "show preview thumbnail",
            "tools/scripts",
        )
        preview_action.triggered.connect(self._show_preview_thumbnail)

        settings_action = window.createAction(
            "spine_export_show_settings",
            "show spine export settings",
            "tools/scripts",
        )
        settings_action.triggered.connect(self._show_settings_dialog)

    def _show_export_dialog(self):
        app = Krita.instance()
        document = app.activeDocument()
        if document is None:
            app.activeWindow().qwindow().showMessage(
                "Open a document before exporting to Spine."
            )
            return
        dialog = SpineExportDialog(document, app.activeWindow().qwindow())
        dialog.exec()

    def _show_preview_thumbnail(self):
        app = Krita.instance()
        parent = app.activeWindow().qwindow()
        document = app.activeDocument()
        if document is None:
            QMessageBox.information(
                parent,
                "Spine Skin Preview",
                "Open a document before showing skin thumbnails.",
            )
            return
        if self._preview_dialog is not None:
            self._preview_dialog.close()
        self._preview_dialog = SpinePreviewDialog(document, parent)
        self._preview_dialog.show()
        self._preview_dialog.raise_()
        self._preview_dialog.activateWindow()

    def _show_settings_dialog(self):
        app = Krita.instance()
        dialog = SpineSettingsDialog(app.activeWindow().qwindow())
        if dialog.exec() and self._preview_dialog is not None:
            if self._preview_dialog.isVisible():
                self._preview_dialog.reload()


app = Krita.instance()
app.addExtension(KritaSpineExtension(app))
