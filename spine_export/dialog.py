import os

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QCheckBox,
        QDialog,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QVBoxLayout,
    )
except ImportError:  # Krita 6 may expose PySide6 in some builds.
    from PySide6.QtWidgets import (
        QCheckBox,
        QDialog,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QVBoxLayout,
    )

from .exporter import (
    ExportSettings,
    SpineExporter,
    SpineExportError,
    document_export_name,
)


class SpineExportDialog(QDialog):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.setWindowTitle("Export to Spine")
        self.setMinimumWidth(520)
        self._build_ui()

    def _default_base_dir(self):
        filename = self.document.fileName() or ""
        if filename:
            return os.path.dirname(filename)
        return os.path.expanduser("~")

    def _build_ui(self):
        root = QVBoxLayout(self)

        form = QFormLayout()
        self.export_dir = QLineEdit(self._default_base_dir())

        export_row = QHBoxLayout()
        export_row.addWidget(self.export_dir)
        export_btn = QPushButton("Browse")
        export_btn.clicked.connect(self._browse_export_dir)
        export_row.addWidget(export_btn)
        form.addRow("Export folder", export_row)

        self.scale = QSpinBox()
        self.scale.setRange(1, 1000)
        self.scale.setValue(100)
        self.scale.setSuffix("%")
        form.addRow("Scale", self.scale)

        self.padding = QSpinBox()
        self.padding.setRange(0, 512)
        self.padding.setValue(1)
        self.padding.setSuffix(" px")
        form.addRow("Padding", self.padding)

        root.addLayout(form)

        self.trim_whitespace = QCheckBox("Trim whitespace")
        self.trim_whitespace.setChecked(True)
        self.ignore_hidden_layers = QCheckBox("Ignore hidden layers")
        self.ignore_hidden_layers.setChecked(False)
        self.write_json = QCheckBox("Write Spine JSON")
        self.write_json.setChecked(True)
        self.write_images = QCheckBox("Write PNG images")
        self.write_images.setChecked(True)
        self.write_template = QCheckBox("Write template image")
        self.write_template.setChecked(False)
        self.legacy_json = QCheckBox("Legacy Spine skin JSON")
        self.legacy_json.setChecked(False)

        for widget in (
            self.trim_whitespace,
            self.ignore_hidden_layers,
            self.write_json,
            self.write_images,
            self.write_template,
            self.legacy_json,
        ):
            root.addWidget(widget)

        # note = QLabel(
        #     "Layer tags match PhotoshopToSpine where Krita exposes equivalent data."
        # )
        # note.setWordWrap(True)
        # note.setAlignment(Qt.AlignLeft)
        # root.addWidget(note)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self._export)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(export_btn)
        root.addLayout(buttons)

    def _browse_export_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Export folder", self.export_dir.text()
        )
        if path:
            self.export_dir.setText(path)

    def _export(self):
        try:
            target_subdir, json_name = document_export_name(self.document)
        except SpineExportError as exc:
            QMessageBox.critical(self, "Spine export failed", str(exc))
            return

        export_dir = self.export_dir.text().strip()
        if not export_dir:
            QMessageBox.critical(
                self, "Spine export failed", "Choose an export folder."
            )
            return

        target_dir = os.path.join(export_dir, target_subdir)
        settings = ExportSettings(
            json_path=os.path.join(target_dir, json_name + ".json"),
            images_dir=os.path.join(target_dir, "images"),
            scale=self.scale.value() / 100.0,
            padding=self.padding.value(),
            trim_whitespace=self.trim_whitespace.isChecked(),
            ignore_hidden_layers=self.ignore_hidden_layers.isChecked(),
            write_json=self.write_json.isChecked(),
            write_images=self.write_images.isChecked(),
            write_template=self.write_template.isChecked(),
            legacy_json=self.legacy_json.isChecked(),
        )
        try:
            result = SpineExporter(self.document, settings).export()
        except SpineExportError as exc:
            QMessageBox.critical(self, "Spine export failed", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(
                self, "Spine export failed", f"Unexpected error: {exc}"
            )
            return

        QMessageBox.information(
            self,
            "Spine export complete",
            "Exported {0} attachment(s).\nJSON: {1}\nImages: {2}".format(
                result.attachment_count,
                result.json_path or "not written",
                result.images_dir or "not written",
            ),
        )
        self.accept()
