"""Main PySide6 window for the Task One target localization desktop app."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..geometry import ConfidenceLabel
from ..localization import WallTargetDraft, calculate_wall_target_draft
from ..models import (
    CalibrationMode,
    CircleAnnotation,
    FACE_DIRECTIONS,
    ProjectSession,
    ScreenshotSession,
    SurfaceType,
    TARGET_COLOURS,
    TargetRecord,
)
from ..persistence import copy_image_into_workspace, load_session, save_session, write_report
from ..reporting import generate_ground_location_sentence, render_report
from .canvas import ImageCanvas

APP_TITLE = "Task One Target Localization - Valiant Aerotech"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1600, 950)

        self.session = ProjectSession()
        self.active_screenshot_id: str | None = None
        self.current_wall_draft: WallTargetDraft | None = None

        self.canvas = ImageCanvas()
        self.canvas.point_created.connect(self._on_point_created)
        self.canvas.line_created.connect(self._on_line_created)
        self.canvas.circle_created.connect(self._on_circle_created)
        self.canvas.point_moved.connect(self._on_point_moved)
        self.canvas.point_move_finished.connect(self._on_point_move_finished)
        self.canvas.circle_moved.connect(self._on_circle_moved)
        self.canvas.circle_move_finished.connect(self._on_circle_move_finished)

        self._build_ui()
        self._bind_session_to_ui()
        self._refresh_all()
        self.statusBar().showMessage("Ready. Paste or load a screenshot to begin.")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        self.setCentralWidget(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        instruction = QLabel(
            "Wheel: zoom • Pan tool: drag image • Wall/door corner handles: place, then drag into position • Target: draw a circle, then drag to refine"
        )
        instruction.setWordWrap(True)
        left_layout.addWidget(instruction)
        left_layout.addWidget(self.canvas, stretch=1)
        fit_btn = QPushButton("Fit Image")
        fit_btn.clicked.connect(self.canvas.fit_image)
        left_layout.addWidget(fit_btn)
        splitter.addWidget(left_panel)

        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_content = QWidget()
        side_layout = QVBoxLayout(side_content)
        side_layout.setContentsMargins(4, 4, 4, 4)
        side_scroll.setWidget(side_content)
        splitter.addWidget(side_scroll)
        splitter.setSizes([1020, 560])

        side_layout.addWidget(self._build_project_group())
        side_layout.addWidget(self._build_screenshot_group())
        side_layout.addWidget(self._build_annotation_group())
        side_layout.addWidget(self._build_wall_target_group())
        side_layout.addWidget(self._build_ground_target_group())
        side_layout.addWidget(self._build_review_group())
        side_layout.addStretch(1)

    def _build_project_group(self) -> QGroupBox:
        group = QGroupBox("1. Project and Output")
        layout = QVBoxLayout(group)
        form = QFormLayout()
        layout.addLayout(form)

        self.team_name_edit = QLineEdit("Valiant_Aerotech")
        self.team_name_edit.editingFinished.connect(self._update_project_config)
        form.addRow("Team name", self.team_name_edit)

        self.building_length_spin = self._metre_spinbox()
        self.building_width_spin = self._metre_spinbox()
        self.building_height_spin = self._metre_spinbox()
        self.building_length_spin.valueChanged.connect(self._update_project_config)
        self.building_width_spin.valueChanged.connect(self._update_project_config)
        self.building_height_spin.valueChanged.connect(self._update_project_config)
        form.addRow("Building length (m)", self.building_length_spin)
        form.addRow("Building width (m)", self.building_width_spin)
        form.addRow("Building height (m)", self.building_height_spin)

        self.ns_span_source_combo = QComboBox()
        self.ns_span_source_combo.addItems(["length", "width"])
        self.ns_span_source_combo.currentTextChanged.connect(self._update_project_config)
        form.addRow("North/South face span uses", self.ns_span_source_combo)

        note = QLabel(
            "Face-span mapping avoids silently assuming whether the competition 'length' or 'width' applies to North/South faces."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QHBoxLayout()
        self.new_session_button = QPushButton("New Session")
        self.load_session_button = QPushButton("Load Session")
        self.save_session_button = QPushButton("Save Session")
        self.new_session_button.clicked.connect(self._new_session)
        self.load_session_button.clicked.connect(self._load_session_dialog)
        self.save_session_button.clicked.connect(self._persist)
        buttons.addWidget(self.new_session_button)
        buttons.addWidget(self.load_session_button)
        buttons.addWidget(self.save_session_button)
        layout.addLayout(buttons)

        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)
        return group

    def _build_screenshot_group(self) -> QGroupBox:
        group = QGroupBox("2. Screenshot Session")
        layout = QVBoxLayout(group)

        image_buttons = QHBoxLayout()
        self.paste_image_button = QPushButton("Paste Screenshot")
        self.load_image_button = QPushButton("Load Image")
        self.paste_image_button.clicked.connect(self._paste_image_from_clipboard)
        self.load_image_button.clicked.connect(self._load_image_dialog)
        image_buttons.addWidget(self.paste_image_button)
        image_buttons.addWidget(self.load_image_button)
        layout.addLayout(image_buttons)

        self.screenshot_list = QListWidget()
        self.screenshot_list.currentItemChanged.connect(self._on_screenshot_selection_changed)
        layout.addWidget(self.screenshot_list)

        form = QFormLayout()
        layout.addLayout(form)
        self.face_direction_combo = QComboBox()
        self.face_direction_combo.addItems(FACE_DIRECTIONS)
        self.face_direction_combo.currentTextChanged.connect(self._on_face_direction_changed)
        form.addRow("Face direction", self.face_direction_combo)

        self.wall_width_spin = self._metre_spinbox()
        self.wall_height_spin = self._metre_spinbox()
        self.wall_width_spin.valueChanged.connect(self._on_wall_dimension_changed)
        self.wall_height_spin.valueChanged.connect(self._on_wall_dimension_changed)
        form.addRow("Wall face width (m)", self.wall_width_spin)
        form.addRow("Wall face height (m)", self.wall_height_spin)

        auto_button = QPushButton("Refill Face Dimensions from Building Setup")
        auto_button.clicked.connect(self._refill_active_face_dimensions)
        layout.addWidget(auto_button)
        return group

    def _build_annotation_group(self) -> QGroupBox:
        group = QGroupBox("3. Annotation and Calibration")
        layout = QVBoxLayout(group)
        form = QFormLayout()
        layout.addLayout(form)

        self.calibration_mode_combo = QComboBox()
        self.calibration_mode_combo.addItems([mode.value for mode in CalibrationMode])
        self.calibration_mode_combo.currentTextChanged.connect(self._on_calibration_mode_changed)
        form.addRow("Calibration mode", self.calibration_mode_combo)

        self.approx_edge_side_combo = QComboBox()
        self.approx_edge_side_combo.addItems(["left", "right"])
        self.approx_edge_side_combo.currentTextChanged.connect(self._on_approx_edge_side_changed)
        form.addRow("Approx. reference edge", self.approx_edge_side_combo)

        self.tool_combo = QComboBox()
        self.tool_combo.addItem("Pan / inspect", "pan")
        self.tool_combo.addItem("Wall corner: TL → TR → BR → BL", "wall_corner")
        self.tool_combo.addItem("Boundary line: top", "boundary_top")
        self.tool_combo.addItem("Boundary line: right", "boundary_right")
        self.tool_combo.addItem("Boundary line: bottom", "boundary_bottom")
        self.tool_combo.addItem("Boundary line: left", "boundary_left")
        self.tool_combo.addItem("Approx. reference wall edge", "approx_reference_edge")
        self.tool_combo.addItem("Door corner: TL → TR → BR → BL", "door_corner")
        self.tool_combo.addItem("Door left edge", "door_left_edge")
        self.tool_combo.addItem("Door right edge", "door_right_edge")
        self.tool_combo.addItem("Target circle", "target_circle")
        self.tool_combo.currentIndexChanged.connect(self._on_tool_changed)
        form.addRow("Canvas tool", self.tool_combo)

        handle_buttons = QHBoxLayout()
        self.place_wall_handles_button = QPushButton("Place Wall Corner Handles")
        self.place_door_handles_button = QPushButton("Place Door Corner Handles")
        self.place_wall_handles_button.clicked.connect(self._place_wall_corner_handles)
        self.place_door_handles_button.clicked.connect(self._place_door_corner_handles)
        handle_buttons.addWidget(self.place_wall_handles_button)
        handle_buttons.addWidget(self.place_door_handles_button)
        layout.addLayout(handle_buttons)

        drag_note = QLabel(
            "Corner handles are draggable after placement. Full-wall calculations update automatically once a draft target circle exists and enough geometry is present."
        )
        drag_note.setWordWrap(True)
        layout.addWidget(drag_note)

        self.annotation_status_label = QLabel()
        self.annotation_status_label.setWordWrap(True)
        layout.addWidget(self.annotation_status_label)

        buttons = QHBoxLayout()
        reset_calibration = QPushButton("Reset Calibration")
        reset_door = QPushButton("Reset Door")
        reset_draft_circle = QPushButton("Clear Draft Circle")
        reset_calibration.clicked.connect(self._reset_calibration)
        reset_door.clicked.connect(self._reset_door)
        reset_draft_circle.clicked.connect(self._clear_draft_circle)
        buttons.addWidget(reset_calibration)
        buttons.addWidget(reset_door)
        buttons.addWidget(reset_draft_circle)
        layout.addLayout(buttons)
        return group

    def _build_wall_target_group(self) -> QGroupBox:
        group = QGroupBox("4. Wall Target Draft")
        layout = QVBoxLayout(group)
        form = QFormLayout()
        layout.addLayout(form)

        self.wall_colour_combo = QComboBox()
        self.wall_colour_combo.addItems(TARGET_COLOURS)
        self.wall_colour_combo.currentTextChanged.connect(self._try_recalculate_wall_target_draft)
        form.addRow("Target colour", self.wall_colour_combo)

        buttons = QHBoxLayout()
        calculate_button = QPushButton("Calculate Wall Target Draft")
        calculate_button.clicked.connect(self._calculate_wall_target_draft)
        confirm_button = QPushButton("Confirm Wall Target")
        confirm_button.clicked.connect(self._confirm_wall_target)
        buttons.addWidget(calculate_button)
        buttons.addWidget(confirm_button)
        layout.addLayout(buttons)

        self.wall_metrics_label = QLabel("No wall target draft calculated.")
        self.wall_metrics_label.setWordWrap(True)
        layout.addWidget(self.wall_metrics_label)

        self.confidence_label = QLabel("Confidence: —")
        self.confidence_label.setFrameShape(QFrame.Shape.StyledPanel)
        self.confidence_label.setWordWrap(True)
        layout.addWidget(self.confidence_label)

        self.warning_box = QPlainTextEdit()
        self.warning_box.setReadOnly(True)
        self.warning_box.setPlaceholderText("Calculation warnings and review notes will appear here.")
        self.warning_box.setMaximumHeight(110)
        layout.addWidget(self.warning_box)

        self.wall_draft_editor = QPlainTextEdit()
        self.wall_draft_editor.setPlaceholderText("Generated wall-target location sentence appears here and can be edited before confirmation.")
        self.wall_draft_editor.setMaximumHeight(120)
        layout.addWidget(self.wall_draft_editor)
        return group

    def _build_ground_target_group(self) -> QGroupBox:
        group = QGroupBox("5. Ground / Off-Wall Manual Target")
        layout = QVBoxLayout(group)
        form = QFormLayout()
        layout.addLayout(form)

        self.ground_colour_combo = QComboBox()
        self.ground_colour_combo.addItems(TARGET_COLOURS)
        self.ground_face_combo = QComboBox()
        self.ground_face_combo.addItems(FACE_DIRECTIONS)
        self.ground_distance_spin = self._metre_spinbox()
        self.ground_door_relation_combo = QComboBox()
        self.ground_door_relation_combo.addItems(["none", "left", "right", "aligned"])
        self.ground_door_offset_spin = self._metre_spinbox()
        self.ground_freeform_edit = QLineEdit()
        self.ground_freeform_edit.setPlaceholderText("Optional extra landmark wording")

        form.addRow("Target colour", self.ground_colour_combo)
        form.addRow("Reference face", self.ground_face_combo)
        form.addRow("Distance from face (m)", self.ground_distance_spin)
        form.addRow("Door relation", self.ground_door_relation_combo)
        form.addRow("Door offset (m)", self.ground_door_offset_spin)
        form.addRow("Optional extra wording", self.ground_freeform_edit)

        buttons = QHBoxLayout()
        generate_button = QPushButton("Generate Ground Draft")
        add_button = QPushButton("Confirm Manual Target")
        generate_button.clicked.connect(self._generate_ground_target_draft)
        add_button.clicked.connect(self._confirm_ground_target)
        buttons.addWidget(generate_button)
        buttons.addWidget(add_button)
        layout.addLayout(buttons)

        self.ground_draft_editor = QPlainTextEdit()
        self.ground_draft_editor.setPlaceholderText("Generated ground/off-wall description appears here and can be edited.")
        self.ground_draft_editor.setMaximumHeight(110)
        layout.addWidget(self.ground_draft_editor)
        return group

    def _build_review_group(self) -> QGroupBox:
        group = QGroupBox("6. Confirmed Targets and Final Report")
        layout = QVBoxLayout(group)

        self.target_list = QListWidget()
        self.target_list.currentItemChanged.connect(self._on_target_selection_changed)
        layout.addWidget(self.target_list)

        self.selected_target_editor = QPlainTextEdit()
        self.selected_target_editor.setPlaceholderText("Select a confirmed target to edit its final location sentence.")
        self.selected_target_editor.setMaximumHeight(110)
        layout.addWidget(self.selected_target_editor)

        edit_buttons = QHBoxLayout()
        update_target_button = QPushButton("Update Selected Target Text")
        delete_target_button = QPushButton("Delete Selected Target")
        update_target_button.clicked.connect(self._update_selected_target_text)
        delete_target_button.clicked.connect(self._delete_selected_target)
        edit_buttons.addWidget(update_target_button)
        edit_buttons.addWidget(delete_target_button)
        layout.addLayout(edit_buttons)

        report_label = QLabel("Live `Task_1_<team_name>_targets.txt` preview")
        report_label.setWordWrap(True)
        layout.addWidget(report_label)

        self.report_preview = QPlainTextEdit()
        self.report_preview.setReadOnly(True)
        self.report_preview.setMaximumHeight(300)
        layout.addWidget(self.report_preview)
        return group

    @staticmethod
    def _metre_spinbox() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 999.9)
        spin.setDecimals(2)
        spin.setSingleStep(0.1)
        spin.setSuffix(" m")
        return spin

    # ------------------------------------------------------------------
    # Session and path persistence
    # ------------------------------------------------------------------
    def _new_session(self) -> None:
        self.session = ProjectSession()
        self.active_screenshot_id = None
        self.current_wall_draft = None
        self.canvas.clear_overlays()
        self.canvas.scene.clear()
        self.canvas.pixmap_item = None
        self._bind_session_to_ui()
        self._refresh_all()
        self._persist()
        self.statusBar().showMessage("New session created.")

    def _load_session_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Task One Localization Session",
            str(Path.cwd()),
            "JSON Files (*.json)",
        )
        if not path:
            return
        try:
            self.session = load_session(path)
        except Exception as exc:  # noqa: BLE001 - user-facing UI boundary
            self._show_error("Could not load session", str(exc))
            return
        self.active_screenshot_id = self.session.screenshots[0].id if self.session.screenshots else None
        self.current_wall_draft = None
        self._bind_session_to_ui()
        self._refresh_all()
        self.statusBar().showMessage(f"Loaded session: {path}")

    def _persist(self) -> None:
        try:
            report_path = write_report(self.session)
            session_path = save_session(self.session)
        except Exception as exc:  # noqa: BLE001 - user-facing UI boundary
            self._show_error("Could not save session/report", str(exc))
            return
        self.path_label.setText(
            f"Session JSON: {session_path}\nFinal TXT: {report_path}"
        )
        self._refresh_report_preview()
        self.statusBar().showMessage(f"Saved report and session at {datetime.now().strftime('%H:%M:%S')}.")

    def _bind_session_to_ui(self) -> None:
        self.team_name_edit.blockSignals(True)
        self.building_length_spin.blockSignals(True)
        self.building_width_spin.blockSignals(True)
        self.building_height_spin.blockSignals(True)
        self.ns_span_source_combo.blockSignals(True)
        self.team_name_edit.setText(self.session.team_name)
        self.building_length_spin.setValue(self.session.building_length_m)
        self.building_width_spin.setValue(self.session.building_width_m)
        self.building_height_spin.setValue(self.session.building_height_m)
        self.ns_span_source_combo.setCurrentText(self.session.north_south_face_span_source)
        self.team_name_edit.blockSignals(False)
        self.building_length_spin.blockSignals(False)
        self.building_width_spin.blockSignals(False)
        self.building_height_spin.blockSignals(False)
        self.ns_span_source_combo.blockSignals(False)
        self._refresh_screenshot_list()
        self._refresh_target_list()
        self._refresh_report_preview()

    def _update_project_config(self) -> None:
        team_name = self.team_name_edit.text().strip() or "Valiant_Aerotech"
        self.session.team_name = team_name.replace(" ", "_")
        self.session.building_length_m = self.building_length_spin.value()
        self.session.building_width_m = self.building_width_spin.value()
        self.session.building_height_m = self.building_height_spin.value()
        self.session.north_south_face_span_source = self.ns_span_source_combo.currentText()
        self.session.normalize_output_paths()
        self._persist()

    # ------------------------------------------------------------------
    # Screenshot handling
    # ------------------------------------------------------------------
    def _paste_image_from_clipboard(self) -> None:
        image = QApplication.clipboard().image()
        if image.isNull():
            self._show_error(
                "No screenshot image found",
                "Copy a screenshot to the clipboard first, then press Paste Screenshot.",
            )
            return
        try:
            workspace = Path(self.session.workspace_dir)
            (workspace / "screenshots").mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_path = workspace / "screenshots" / f"clipboard_capture_{stamp}.png"
            suffix = 2
            while image_path.exists():
                image_path = workspace / "screenshots" / f"clipboard_capture_{stamp}_{suffix}.png"
                suffix += 1
            if not image.save(str(image_path), "PNG"):
                raise OSError("Qt could not save the clipboard image as PNG.")
            self._create_screenshot_session(str(image_path))
        except Exception as exc:  # noqa: BLE001 - user-facing UI boundary
            self._show_error("Could not save clipboard screenshot", str(exc))

    def _load_image_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Screenshot Image",
            str(Path.cwd()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not path:
            return
        try:
            copied_path = copy_image_into_workspace(self.session, path)
            self._create_screenshot_session(str(copied_path))
        except Exception as exc:  # noqa: BLE001 - user-facing UI boundary
            self._show_error("Could not load screenshot image", str(exc))

    def _create_screenshot_session(self, image_path: str) -> None:
        screenshot = ScreenshotSession.create(image_path)
        screenshot.face_direction = self.face_direction_combo.currentText() or "North"
        screenshot.wall_width_m = self._default_face_span(screenshot.face_direction)
        screenshot.wall_height_m = self.session.building_height_m
        screenshot.calibration_mode = self.calibration_mode_combo.currentText()
        screenshot.calibration.approximate_reference_edge_side = self.approx_edge_side_combo.currentText()
        self.session.screenshots.append(screenshot)
        self.active_screenshot_id = screenshot.id
        self.current_wall_draft = None
        self._refresh_screenshot_list(select_id=screenshot.id)
        self._load_active_screenshot_into_ui()
        self._persist()

    def _refresh_screenshot_list(self, *, select_id: str | None = None) -> None:
        desired = select_id or self.active_screenshot_id
        self.screenshot_list.blockSignals(True)
        self.screenshot_list.clear()
        index_to_select = -1
        for index, screenshot in enumerate(self.session.screenshots):
            label = f"{index + 1}. {screenshot.face_direction} face · {Path(screenshot.image_path).name}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, screenshot.id)
            self.screenshot_list.addItem(item)
            if screenshot.id == desired:
                index_to_select = index
        if index_to_select >= 0:
            self.screenshot_list.setCurrentRow(index_to_select)
        self.screenshot_list.blockSignals(False)

    def _on_screenshot_selection_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            self.active_screenshot_id = None
            return
        self.active_screenshot_id = str(current.data(Qt.ItemDataRole.UserRole))
        self.current_wall_draft = None
        self._load_active_screenshot_into_ui()

    def _active_screenshot(self) -> ScreenshotSession | None:
        if not self.active_screenshot_id:
            return None
        return self.session.screenshot_by_id(self.active_screenshot_id)

    def _load_active_screenshot_into_ui(self) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None:
            return
        try:
            self.canvas.load_image(screenshot.image_path)
        except Exception as exc:  # noqa: BLE001 - user-facing UI boundary
            self._show_error("Could not display screenshot", str(exc))
            return
        self.face_direction_combo.blockSignals(True)
        self.wall_width_spin.blockSignals(True)
        self.wall_height_spin.blockSignals(True)
        self.calibration_mode_combo.blockSignals(True)
        self.approx_edge_side_combo.blockSignals(True)
        self.face_direction_combo.setCurrentText(screenshot.face_direction)
        self.wall_width_spin.setValue(screenshot.wall_width_m)
        self.wall_height_spin.setValue(screenshot.wall_height_m)
        self.calibration_mode_combo.setCurrentText(screenshot.calibration_mode)
        self.approx_edge_side_combo.setCurrentText(screenshot.calibration.approximate_reference_edge_side)
        self.face_direction_combo.blockSignals(False)
        self.wall_width_spin.blockSignals(False)
        self.wall_height_spin.blockSignals(False)
        self.calibration_mode_combo.blockSignals(False)
        self.approx_edge_side_combo.blockSignals(False)
        self._redraw_active_overlays()
        self._update_annotation_status()

    def _default_face_span(self, face_direction: str) -> float:
        ns_uses_length = self.session.north_south_face_span_source == "length"
        if face_direction in {"North", "South"}:
            return self.session.building_length_m if ns_uses_length else self.session.building_width_m
        return self.session.building_width_m if ns_uses_length else self.session.building_length_m

    def _refill_active_face_dimensions(self) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None:
            return
        screenshot.wall_width_m = self._default_face_span(screenshot.face_direction)
        screenshot.wall_height_m = self.session.building_height_m
        self.wall_width_spin.blockSignals(True)
        self.wall_height_spin.blockSignals(True)
        self.wall_width_spin.setValue(screenshot.wall_width_m)
        self.wall_height_spin.setValue(screenshot.wall_height_m)
        self.wall_width_spin.blockSignals(False)
        self.wall_height_spin.blockSignals(False)
        self._try_recalculate_wall_target_draft()
        self._persist()

    def _on_face_direction_changed(self, face_direction: str) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None:
            return
        screenshot.face_direction = face_direction
        screenshot.wall_width_m = self._default_face_span(face_direction)
        screenshot.wall_height_m = self.session.building_height_m
        self.wall_width_spin.blockSignals(True)
        self.wall_height_spin.blockSignals(True)
        self.wall_width_spin.setValue(screenshot.wall_width_m)
        self.wall_height_spin.setValue(screenshot.wall_height_m)
        self.wall_width_spin.blockSignals(False)
        self.wall_height_spin.blockSignals(False)
        self._refresh_screenshot_list(select_id=screenshot.id)
        self._try_recalculate_wall_target_draft()
        self._persist()

    def _on_wall_dimension_changed(self) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None:
            return
        screenshot.wall_width_m = self.wall_width_spin.value()
        screenshot.wall_height_m = self.wall_height_spin.value()
        self._try_recalculate_wall_target_draft()
        self._persist()

    # ------------------------------------------------------------------
    # Annotation handlers
    # ------------------------------------------------------------------
    def _on_calibration_mode_changed(self, mode: str) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None:
            return
        screenshot.calibration_mode = mode
        self._update_annotation_status()
        self._try_recalculate_wall_target_draft()
        self._persist()

    def _on_approx_edge_side_changed(self, side: str) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None:
            return
        screenshot.calibration.approximate_reference_edge_side = side
        self._try_recalculate_wall_target_draft()
        self._persist()

    def _on_tool_changed(self) -> None:
        tool = str(self.tool_combo.currentData())
        self.canvas.set_tool(tool)
        self._update_annotation_status()

    def _on_point_created(self, tool: str, point: tuple[float, float]) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None:
            return
        if tool == "wall_corner":
            if len(screenshot.calibration.corners_tl_tr_br_bl) >= 4:
                self._show_error("Wall corners already complete", "Reset Calibration to mark corners again.")
                return
            screenshot.calibration.corners_tl_tr_br_bl.append(point)
        elif tool == "door_corner":
            if len(screenshot.door.corners_tl_tr_br_bl) >= 4:
                self._show_error("Door corners already complete", "Reset Door to mark door corners again.")
                return
            screenshot.door.corners_tl_tr_br_bl.append(point)
        self._redraw_active_overlays()
        self._update_annotation_status()
        self._try_recalculate_wall_target_draft()
        self._persist()

    def _on_line_created(self, tool: str, line) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None:
            return
        calibration = screenshot.calibration
        if tool == "boundary_top":
            calibration.top_boundary = line
        elif tool == "boundary_right":
            calibration.right_boundary = line
        elif tool == "boundary_bottom":
            calibration.bottom_boundary = line
        elif tool == "boundary_left":
            calibration.left_boundary = line
        elif tool == "approx_reference_edge":
            calibration.approximate_reference_edge = line
        elif tool == "door_left_edge":
            screenshot.door.left_edge = line
        elif tool == "door_right_edge":
            screenshot.door.right_edge = line
        self._redraw_active_overlays()
        self._update_annotation_status()
        self._try_recalculate_wall_target_draft()
        self._persist()

    def _on_circle_created(self, circle: CircleAnnotation) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None:
            return
        screenshot.draft_circle = circle
        self.current_wall_draft = None
        self.wall_draft_editor.clear()
        self.warning_box.clear()
        self.confidence_label.setText("Confidence: —")
        self.wall_metrics_label.setText("Draft circle captured. Auto-calculation will run as soon as wall geometry is sufficient.")
        self._redraw_active_overlays()
        self._try_recalculate_wall_target_draft()
        self._persist()

    def _place_wall_corner_handles(self) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None or not self.canvas.has_image():
            self._show_error("No screenshot selected", "Paste or load a screenshot before placing wall corner handles.")
            return
        existing = screenshot.calibration.corners_tl_tr_br_bl
        if existing:
            choice = QMessageBox.question(
                self,
                "Replace wall corner handles?",
                "Wall corner handles already exist. Replace them with a fresh draggable set?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice != QMessageBox.StandardButton.Yes:
                self.statusBar().showMessage("Wall corner handles left unchanged; drag the existing handles to adjust them.")
                return
        width, height = self.canvas.image_size() or (0, 0)
        if width <= 0 or height <= 0:
            self._show_error("Image dimensions unavailable", "Could not determine screenshot size.")
            return
        screenshot.calibration.corners_tl_tr_br_bl = [
            (0.16 * width, 0.16 * height),
            (0.84 * width, 0.16 * height),
            (0.84 * width, 0.84 * height),
            (0.16 * width, 0.84 * height),
        ]
        self.current_wall_draft = None
        self._redraw_active_overlays()
        self._update_annotation_status()
        self._try_recalculate_wall_target_draft()
        self._persist()
        self.statusBar().showMessage("Wall corner handles placed. Drag TL, TR, BR, and BL onto the wall corners.")

    def _place_door_corner_handles(self) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None or not self.canvas.has_image():
            self._show_error("No screenshot selected", "Paste or load a screenshot before placing door corner handles.")
            return
        existing = screenshot.door.corners_tl_tr_br_bl
        if existing:
            choice = QMessageBox.question(
                self,
                "Replace door corner handles?",
                "Door corner handles already exist. Replace them with a fresh draggable set?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice != QMessageBox.StandardButton.Yes:
                self.statusBar().showMessage("Door corner handles left unchanged; drag the existing handles to adjust them.")
                return
        width, height = self.canvas.image_size() or (0, 0)
        if width <= 0 or height <= 0:
            self._show_error("Image dimensions unavailable", "Could not determine screenshot size.")
            return
        screenshot.door.corners_tl_tr_br_bl = [
            (0.40 * width, 0.46 * height),
            (0.60 * width, 0.46 * height),
            (0.60 * width, 0.86 * height),
            (0.40 * width, 0.86 * height),
        ]
        self.current_wall_draft = None
        self._redraw_active_overlays()
        self._update_annotation_status()
        self._try_recalculate_wall_target_draft()
        self._persist()
        self.statusBar().showMessage("Door corner handles placed. Drag TL, TR, BR, and BL onto the visible door corners.")

    def _on_point_moved(self, kind: str, index: int, point: tuple[float, float]) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None:
            return
        if kind == "wall_corner":
            if 0 <= index < len(screenshot.calibration.corners_tl_tr_br_bl):
                screenshot.calibration.corners_tl_tr_br_bl[index] = point
        elif kind == "door_corner":
            if 0 <= index < len(screenshot.door.corners_tl_tr_br_bl):
                screenshot.door.corners_tl_tr_br_bl[index] = point
        self._try_recalculate_wall_target_draft()

    def _on_point_move_finished(self, kind: str, index: int, point: tuple[float, float]) -> None:
        self._on_point_moved(kind, index, point)
        self._update_annotation_status()
        self._persist()

    def _on_circle_moved(self, circle: CircleAnnotation) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None:
            return
        screenshot.draft_circle = circle
        self._try_recalculate_wall_target_draft()

    def _on_circle_move_finished(self, circle: CircleAnnotation) -> None:
        self._on_circle_moved(circle)
        self._persist()

    def _try_recalculate_wall_target_draft(self, *_args) -> None:
        """Refresh the wall-target draft when annotations are sufficient, without error popups.

        This is used for direct-manipulation edits. The explicit Calculate button still
        exists for a deliberate operator action and will show blocking error dialogs.
        """
        screenshot = self._active_screenshot()
        if screenshot is None or screenshot.draft_circle is None:
            return
        try:
            draft = calculate_wall_target_draft(
                screenshot=screenshot,
                circle=screenshot.draft_circle,
                colour=self.wall_colour_combo.currentText(),
            )
        except Exception as exc:  # noqa: BLE001 - live edit path must not spam popups
            self.current_wall_draft = None
            self.confidence_label.setText("Confidence: —")
            self.warning_box.setPlainText(f"Auto-calculation pending: {exc}")
            self.wall_metrics_label.setText("Auto-calculation pending. Finish or adjust wall/door annotations.")
            return
        self.current_wall_draft = draft
        self.wall_draft_editor.setPlainText(draft.generated_sentence)
        self.confidence_label.setText(f"Confidence: {draft.confidence}")
        warning_text = "\n".join(f"• {warning}" for warning in draft.warnings) if draft.warnings else "No warnings."
        self.warning_box.setPlainText(warning_text)
        self.wall_metrics_label.setText(
            "Computed wall position: "
            f"x={draft.location.x_from_left_m:.1f} m from the screenshot-left wall edge, "
            f"height={draft.location.height_above_ground_m:.1f} m above ground."
        )

    def _reset_calibration(self) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None:
            return
        screenshot.calibration.corners_tl_tr_br_bl.clear()
        screenshot.calibration.top_boundary = None
        screenshot.calibration.right_boundary = None
        screenshot.calibration.bottom_boundary = None
        screenshot.calibration.left_boundary = None
        screenshot.calibration.approximate_reference_edge = None
        self.current_wall_draft = None
        self.wall_draft_editor.clear()
        self.warning_box.setPlainText("Calibration reset. Wall-target draft is no longer valid until calibration is rebuilt.")
        self.confidence_label.setText("Confidence: —")
        self.wall_metrics_label.setText("No wall target draft calculated.")
        self._redraw_active_overlays()
        self._update_annotation_status()
        self._try_recalculate_wall_target_draft()
        self._persist()

    def _reset_door(self) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None:
            return
        screenshot.door.corners_tl_tr_br_bl.clear()
        screenshot.door.left_edge = None
        screenshot.door.right_edge = None
        self.current_wall_draft = None
        self.wall_draft_editor.clear()
        self.warning_box.setPlainText("Door annotation reset. Any door-relative draft wording has been invalidated.")
        self.confidence_label.setText("Confidence: —")
        self.wall_metrics_label.setText("No wall target draft calculated.")
        self._redraw_active_overlays()
        self._update_annotation_status()
        self._try_recalculate_wall_target_draft()
        self._persist()

    def _clear_draft_circle(self) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None:
            return
        screenshot.draft_circle = None
        self.current_wall_draft = None
        self.wall_draft_editor.clear()
        self.warning_box.clear()
        self.confidence_label.setText("Confidence: —")
        self.wall_metrics_label.setText("No wall target draft calculated.")
        self._redraw_active_overlays()
        self._persist()

    def _redraw_active_overlays(self) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None or not self.canvas.has_image():
            return
        self.canvas.clear_overlays()

        for index, point in enumerate(screenshot.calibration.corners_tl_tr_br_bl):
            label = ["TL", "TR", "BR", "BL"][index]
            self.canvas.add_point_marker(
                point,
                f"Wall {label}",
                colour=QColor(255, 214, 10),
                draggable_kind="wall_corner",
                draggable_index=index,
            )

        boundary_lines = [
            (screenshot.calibration.top_boundary, "Top"),
            (screenshot.calibration.right_boundary, "Right"),
            (screenshot.calibration.bottom_boundary, "Bottom"),
            (screenshot.calibration.left_boundary, "Left"),
        ]
        for line, label in boundary_lines:
            if line is not None:
                self.canvas.add_line_marker(line, f"Wall {label}", colour=QColor(100, 220, 255))

        if screenshot.calibration.approximate_reference_edge is not None:
            self.canvas.add_line_marker(
                screenshot.calibration.approximate_reference_edge,
                f"Approx. {screenshot.calibration.approximate_reference_edge_side} edge",
                colour=QColor(180, 160, 255),
            )

        for index, point in enumerate(screenshot.door.corners_tl_tr_br_bl):
            label = ["TL", "TR", "BR", "BL"][index]
            self.canvas.add_point_marker(
                point,
                f"Door {label}",
                colour=QColor(120, 255, 160),
                draggable_kind="door_corner",
                draggable_index=index,
            )
        if screenshot.door.left_edge is not None:
            self.canvas.add_line_marker(screenshot.door.left_edge, "Door left", colour=QColor(120, 255, 160))
        if screenshot.door.right_edge is not None:
            self.canvas.add_line_marker(screenshot.door.right_edge, "Door right", colour=QColor(120, 255, 160))

        for target in self.session.targets:
            if target.screenshot_id == screenshot.id and target.circle is not None:
                self.canvas.add_circle_marker(
                    target.circle,
                    f"Target {target.number}",
                    colour=QColor(255, 120, 120),
                )
        if screenshot.draft_circle is not None:
            self.canvas.add_circle_marker(
                screenshot.draft_circle,
                "Draft target",
                colour=QColor(255, 210, 120),
                draggable=True,
            )

    def _update_annotation_status(self) -> None:
        screenshot = self._active_screenshot()
        tool = str(self.tool_combo.currentData()) if hasattr(self, "tool_combo") else "pan"
        if screenshot is None:
            self.annotation_status_label.setText("No screenshot selected.")
            return
        mode = screenshot.calibration_mode
        corners = len(screenshot.calibration.corners_tl_tr_br_bl)
        door_corners = len(screenshot.door.corners_tl_tr_br_bl)
        lines = screenshot.calibration
        boundary_count = sum(
            line is not None
            for line in [lines.top_boundary, lines.right_boundary, lines.bottom_boundary, lines.left_boundary]
        )
        approx_ready = lines.approximate_reference_edge is not None
        status = [f"Mode: {mode}."]
        if mode == CalibrationMode.FULL_CORNERS.value:
            status.append(f"Wall corners: {corners}/4, use TL → TR → BR → BL.")
        elif mode == CalibrationMode.BOUNDARY_LINES.value:
            status.append(f"Boundary lines: {boundary_count}/4.")
        else:
            status.append(
                f"Approximate reference edge: {'ready' if approx_ready else 'not marked'}; side={lines.approximate_reference_edge_side}."
            )
        status.append(f"Door corners: {door_corners}/4; door edges can be used instead or in addition.")
        if tool == "target_circle":
            status.append("Drag a circle around the target; the app uses the circle centre for localization.")
        elif tool in {"boundary_top", "boundary_right", "boundary_bottom", "boundary_left", "approx_reference_edge", "door_left_edge", "door_right_edge"}:
            status.append("Drag from one end of the requested line to the other.")
        self.annotation_status_label.setText(" ".join(status))

    # ------------------------------------------------------------------
    # Wall-target workflow
    # ------------------------------------------------------------------
    def _calculate_wall_target_draft(self) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None:
            self._show_error("No screenshot selected", "Paste or load a screenshot first.")
            return
        if screenshot.draft_circle is None:
            self._show_error("No target circle drawn", "Select Target circle and draw around the target first.")
            return
        colour = self.wall_colour_combo.currentText()
        try:
            draft = calculate_wall_target_draft(
                screenshot=screenshot,
                circle=screenshot.draft_circle,
                colour=colour,
            )
        except Exception as exc:  # noqa: BLE001 - user-facing UI boundary
            self._show_error("Wall target calculation failed", str(exc))
            return
        self.current_wall_draft = draft
        self.wall_draft_editor.setPlainText(draft.generated_sentence)
        self.confidence_label.setText(f"Confidence: {draft.confidence}")
        warning_text = "\n".join(f"• {warning}" for warning in draft.warnings) if draft.warnings else "No warnings."
        self.warning_box.setPlainText(warning_text)
        self.wall_metrics_label.setText(
            "Computed wall position: "
            f"x={draft.location.x_from_left_m:.1f} m from the screenshot-left wall edge, "
            f"height={draft.location.height_above_ground_m:.1f} m above ground."
        )

    def _confirm_wall_target(self) -> None:
        screenshot = self._active_screenshot()
        if screenshot is None or screenshot.draft_circle is None:
            self._show_error("No wall draft ready", "Draw and calculate a wall target first.")
            return
        if self.current_wall_draft is None:
            self._calculate_wall_target_draft()
            if self.current_wall_draft is None:
                return
        description = self.wall_draft_editor.toPlainText().strip()
        if not description:
            self._show_error("Description is empty", "Edit or regenerate the wall target sentence before confirming.")
            return
        target = TargetRecord(
            number=self.session.next_target_number(),
            surface_type=SurfaceType.WALL.value,
            colour=self.wall_colour_combo.currentText(),
            description_text=description,
            generated_text=self.current_wall_draft.generated_sentence,
            confidence=self.current_wall_draft.confidence,
            warnings=list(self.current_wall_draft.warnings),
            screenshot_id=screenshot.id,
            circle=screenshot.draft_circle,
            computed_wall_location=self.current_wall_draft.location,
        )
        self.session.targets.append(target)
        screenshot.draft_circle = None
        self.current_wall_draft = None
        self.wall_draft_editor.clear()
        self.warning_box.clear()
        self.confidence_label.setText("Confidence: —")
        self.wall_metrics_label.setText("Wall target confirmed. Draw the next target circle or select another screenshot.")
        self._refresh_target_list(select_number=target.number)
        self._redraw_active_overlays()
        self._persist()

    # ------------------------------------------------------------------
    # Manual ground/off-wall workflow
    # ------------------------------------------------------------------
    def _generate_ground_target_draft(self) -> None:
        relation = self.ground_door_relation_combo.currentText()
        sentence = generate_ground_location_sentence(
            reference_face=self.ground_face_combo.currentText(),
            distance_from_face_m=self.ground_distance_spin.value(),
            colour=self.ground_colour_combo.currentText(),
            door_relation=None if relation == "none" else relation,
            door_offset_m=self.ground_door_offset_spin.value() if relation in {"left", "right"} else None,
            freeform_tail=self.ground_freeform_edit.text().strip() or None,
        )
        self.ground_draft_editor.setPlainText(sentence)

    def _confirm_ground_target(self) -> None:
        description = self.ground_draft_editor.toPlainText().strip()
        if not description:
            self._generate_ground_target_draft()
            description = self.ground_draft_editor.toPlainText().strip()
        if not description:
            self._show_error("Manual target description is empty", "Generate or write the manual target sentence first.")
            return
        relation = self.ground_door_relation_combo.currentText()
        target = TargetRecord(
            number=self.session.next_target_number(),
            surface_type=SurfaceType.GROUND.value,
            colour=self.ground_colour_combo.currentText(),
            description_text=description,
            generated_text=description,
            confidence=ConfidenceLabel.MANUAL.value,
            warnings=[],
            manual_fields={
                "reference_face": self.ground_face_combo.currentText(),
                "distance_from_face_m": self.ground_distance_spin.value(),
                "door_relation": relation,
                "door_offset_m": self.ground_door_offset_spin.value(),
                "freeform_tail": self.ground_freeform_edit.text().strip(),
            },
        )
        self.session.targets.append(target)
        self.ground_draft_editor.clear()
        self._refresh_target_list(select_number=target.number)
        self._persist()

    # ------------------------------------------------------------------
    # Review / report workflow
    # ------------------------------------------------------------------
    def _refresh_target_list(self, *, select_number: int | None = None) -> None:
        desired = select_number
        current_item = self.target_list.currentItem() if hasattr(self, "target_list") else None
        if desired is None and current_item is not None:
            desired = int(current_item.data(Qt.ItemDataRole.UserRole))
        self.target_list.blockSignals(True)
        self.target_list.clear()
        index_to_select = -1
        for index, target in enumerate(sorted(self.session.targets, key=lambda item: item.number)):
            label = f"Target {target.number} · {target.colour} · {target.surface_type} · Confidence {target.confidence}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, target.number)
            self.target_list.addItem(item)
            if target.number == desired:
                index_to_select = index
        if index_to_select >= 0:
            self.target_list.setCurrentRow(index_to_select)
        self.target_list.blockSignals(False)

    def _on_target_selection_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            self.selected_target_editor.clear()
            return
        number = int(current.data(Qt.ItemDataRole.UserRole))
        target = self.session.target_by_number(number)
        if target is None:
            self.selected_target_editor.clear()
            return
        self.selected_target_editor.setPlainText(target.description_text)

    def _update_selected_target_text(self) -> None:
        item = self.target_list.currentItem()
        if item is None:
            return
        number = int(item.data(Qt.ItemDataRole.UserRole))
        target = self.session.target_by_number(number)
        if target is None:
            return
        description = self.selected_target_editor.toPlainText().strip()
        if not description:
            self._show_error("Description is empty", "The final location sentence cannot be blank.")
            return
        target.description_text = description
        self._persist()
        self._refresh_target_list(select_number=number)

    def _delete_selected_target(self) -> None:
        item = self.target_list.currentItem()
        if item is None:
            return
        number = int(item.data(Qt.ItemDataRole.UserRole))
        self.session.remove_target(number)
        self.selected_target_editor.clear()
        self._refresh_target_list()
        self._redraw_active_overlays()
        self._persist()

    def _refresh_report_preview(self) -> None:
        if hasattr(self, "report_preview"):
            self.report_preview.setPlainText(render_report(self.session))

    # ------------------------------------------------------------------
    # Whole-window refresh and dialogs
    # ------------------------------------------------------------------
    def _refresh_all(self) -> None:
        self._refresh_screenshot_list(select_id=self.active_screenshot_id)
        if self.active_screenshot_id:
            self._load_active_screenshot_into_ui()
        self._refresh_target_list()
        self._refresh_report_preview()
        self._update_annotation_status()
        self._persist()

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)
