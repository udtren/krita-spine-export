try:
    from PyQt6.QtWidgets import (
        QAbstractItemView,
        QDialog,
        QFormLayout,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    from PyQt5.QtWidgets import (
        QAbstractItemView,
        QDialog,
        QFormLayout,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

from .settings_store import (
    MAX_COLUMNS,
    MAX_THUMBNAIL_SIZE,
    MAX_WINDOW_SIZE,
    MIN_COLUMNS,
    MIN_THUMBNAIL_SIZE,
    MIN_WINDOW_SIZE,
    clean_prefixes,
    config_path,
    load_settings,
    save_settings,
)


class SpineSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spine Export Settings")
        self.setMinimumSize(520, 400)
        self._build_ui()

    def _build_ui(self):
        settings = load_settings()
        root = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._build_prefix_tab(settings), "Layer Prefixes")
        tabs.addTab(self._build_display_tab(settings), "Display")
        root.addWidget(tabs)

        path_label = QLabel("Settings file: {0}".format(config_path()))
        path_label.setWordWrap(True)
        path_label.setEnabled(False)
        root.addWidget(path_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        root.addLayout(buttons)

    def _build_prefix_tab(self, settings):
        page = QWidget()
        layout = QVBoxLayout(page)

        tools = QHBoxLayout()
        tools.addStretch()
        for text, slot in (
            ("Add", self._add_prefix),
            ("Remove", self._remove_prefix),
            ("Up", self._move_prefix_up),
            ("Down", self._move_prefix_down),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            tools.addWidget(button)
        layout.addLayout(tools)

        self.prefix_table = QTableWidget(0, 1)
        self.prefix_table.setHorizontalHeaderLabels(["Prefix"])
        self.prefix_table.verticalHeader().setVisible(True)
        self.prefix_table.setSelectionBehavior(_select_rows())
        self.prefix_table.setSelectionMode(_single_selection())
        self.prefix_table.horizontalHeader().setSectionResizeMode(_stretch_mode())
        layout.addWidget(self.prefix_table)

        for prefix in settings["preview_prefixes"]:
            self._append_prefix_row(prefix)

        note = QLabel(
            "Group layers whose name starts with any of these prefixes are shown "
            "in the preview window. Matching is case-insensitive."
        )
        note.setWordWrap(True)
        note.setEnabled(False)
        layout.addWidget(note)

        return page

    def _build_display_tab(self, settings):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()

        self.columns = QSpinBox()
        self.columns.setRange(MIN_COLUMNS, MAX_COLUMNS)
        self.columns.setValue(settings["preview_columns"])
        form.addRow("Preview columns", self.columns)

        self.thumbnail_size = QSpinBox()
        self.thumbnail_size.setRange(MIN_THUMBNAIL_SIZE, MAX_THUMBNAIL_SIZE)
        self.thumbnail_size.setSingleStep(16)
        self.thumbnail_size.setValue(settings["preview_thumbnail_size"])
        self.thumbnail_size.setSuffix(" px")
        form.addRow("Thumbnail size", self.thumbnail_size)

        self.window_width = QSpinBox()
        self.window_width.setRange(MIN_WINDOW_SIZE, MAX_WINDOW_SIZE)
        self.window_width.setSingleStep(20)
        self.window_width.setValue(settings["preview_window_width"])
        self.window_width.setSuffix(" px")
        form.addRow("Preview window width", self.window_width)

        self.window_height = QSpinBox()
        self.window_height.setRange(MIN_WINDOW_SIZE, MAX_WINDOW_SIZE)
        self.window_height.setSingleStep(20)
        self.window_height.setValue(settings["preview_window_height"])
        self.window_height.setSuffix(" px")
        form.addRow("Preview window height", self.window_height)

        layout.addLayout(form)
        layout.addStretch()
        return page

    def _append_prefix_row(self, prefix):
        row = self.prefix_table.rowCount()
        self.prefix_table.insertRow(row)
        self.prefix_table.setItem(row, 0, QTableWidgetItem(prefix))
        return row

    def _add_prefix(self):
        row = self._append_prefix_row("")
        self.prefix_table.setCurrentCell(row, 0)
        self.prefix_table.editItem(self.prefix_table.item(row, 0))

    def _remove_prefix(self):
        row = self.prefix_table.currentRow()
        if row >= 0:
            self.prefix_table.removeRow(row)

    def _move_prefix_up(self):
        self._move_prefix(-1)

    def _move_prefix_down(self):
        self._move_prefix(1)

    def _move_prefix(self, offset):
        row = self.prefix_table.currentRow()
        target = row + offset
        if row < 0 or target < 0 or target >= self.prefix_table.rowCount():
            return
        current = self.prefix_table.takeItem(row, 0)
        other = self.prefix_table.takeItem(target, 0)
        self.prefix_table.setItem(row, 0, other or QTableWidgetItem(""))
        self.prefix_table.setItem(target, 0, current or QTableWidgetItem(""))
        self.prefix_table.setCurrentCell(target, 0)

    def _prefixes(self):
        self.prefix_table.setCurrentCell(-1, -1)
        values = []
        for row in range(self.prefix_table.rowCount()):
            item = self.prefix_table.item(row, 0)
            values.append(item.text() if item is not None else "")
        return clean_prefixes(values)

    def _save(self):
        prefixes = self._prefixes()
        if not prefixes:
            QMessageBox.warning(
                self, "Spine settings", "Add at least one layer prefix."
            )
            return
        try:
            save_settings(
                {
                    "preview_columns": self.columns.value(),
                    "preview_thumbnail_size": self.thumbnail_size.value(),
                    "preview_prefixes": prefixes,
                    "preview_window_width": self.window_width.value(),
                    "preview_window_height": self.window_height.value(),
                }
            )
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Spine settings",
                "Could not write {0}:\n{1}".format(config_path(), exc),
            )
            return
        self.accept()


def _select_rows():
    value = getattr(QAbstractItemView, "SelectRows", None)
    if value is not None:
        return value
    return QAbstractItemView.SelectionBehavior.SelectRows


def _single_selection():
    value = getattr(QAbstractItemView, "SingleSelection", None)
    if value is not None:
        return value
    return QAbstractItemView.SelectionMode.SingleSelection


def _stretch_mode():
    value = getattr(QHeaderView, "Stretch", None)
    if value is not None:
        return value
    return QHeaderView.ResizeMode.Stretch
