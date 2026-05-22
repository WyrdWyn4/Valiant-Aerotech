"""Interactive image canvas for screenshot annotation.

The canvas intentionally supports two complementary authoring styles:

1. Fast creation by click/drag tools.
2. Direct manipulation after creation: wall/door corner handles and the draft
   target circle can be dragged into their exact positions.

The main window owns the session data model; this canvas only renders items and
emits model-friendly signals when an annotation is created or moved.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)

from ..geometry import Point
from ..models import CircleAnnotation, LineAnnotation


@dataclass(slots=True)
class CanvasStyle:
    marker_radius: float = 6.0
    point_pen_width: float = 2.0
    line_pen_width: float = 2.0
    target_pen_width: float = 2.0


POINT_TOOLS = {"wall_corner", "door_corner"}
LINE_TOOLS = {
    "boundary_top",
    "boundary_right",
    "boundary_bottom",
    "boundary_left",
    "approx_reference_edge",
    "door_left_edge",
    "door_right_edge",
}
CIRCLE_TOOLS = {"target_circle"}


class _MovablePointMarker(QGraphicsEllipseItem):
    """Draggable corner marker with a fixed child label."""

    def __init__(
        self,
        *,
        point: Point,
        label: str,
        colour: QColor,
        radius: float,
        pen_width: float,
        image_rect: QRectF,
        on_moved: Callable[[Point], None],
        on_move_finished: Callable[[Point], None],
    ) -> None:
        super().__init__(-radius, -radius, 2 * radius, 2 * radius)
        self._image_rect = image_rect
        self._on_moved = on_moved
        self._on_move_finished = on_move_finished
        self._callbacks_enabled = False
        self._radius = radius

        self.setPen(QPen(colour, pen_width))
        self.setBrush(QBrush(QColor(colour.red(), colour.green(), colour.blue(), 95)))
        self.setZValue(20)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(f"Drag to adjust {label}.")

        text = QGraphicsTextItem(label, self)
        text.setDefaultTextColor(colour)
        text.setPos(radius + 3, -radius - 12)
        text.setZValue(21)

        self.setPos(float(point[0]), float(point[1]))
        self._callbacks_enabled = True

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):  # type: ignore[override]
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and isinstance(value, QPointF):
            return self._clamp_point(value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self._callbacks_enabled:
            pos = self.pos()
            self._on_moved((float(pos.x()), float(pos.y())))
        return super().itemChange(change, value)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        pos = self.pos()
        self._on_move_finished((float(pos.x()), float(pos.y())))

    def _clamp_point(self, point: QPointF) -> QPointF:
        return QPointF(
            min(max(point.x(), self._image_rect.left()), self._image_rect.right()),
            min(max(point.y(), self._image_rect.top()), self._image_rect.bottom()),
        )


class _MovableCircleMarker(QGraphicsEllipseItem):
    """Draggable target circle; radius is fixed until the operator redraws it."""

    def __init__(
        self,
        *,
        circle: CircleAnnotation,
        label: str,
        colour: QColor,
        pen_width: float,
        image_rect: QRectF,
        on_moved: Callable[[CircleAnnotation], None],
        on_move_finished: Callable[[CircleAnnotation], None],
    ) -> None:
        radius = max(float(circle.radius_px), 2.0)
        super().__init__(-radius, -radius, 2 * radius, 2 * radius)
        self._radius = radius
        self._image_rect = image_rect
        self._on_moved = on_moved
        self._on_move_finished = on_move_finished
        self._callbacks_enabled = False

        self.setPen(QPen(colour, pen_width))
        self.setBrush(QBrush(QColor(colour.red(), colour.green(), colour.blue(), 36)))
        self.setZValue(22)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Drag to adjust the draft target circle. Redraw if the radius needs changing.")

        center_dot = QGraphicsEllipseItem(-2.75, -2.75, 5.5, 5.5, self)
        center_dot.setPen(QPen(colour, 1.0))
        center_dot.setBrush(QBrush(colour))
        center_dot.setZValue(23)

        text = QGraphicsTextItem(label, self)
        text.setDefaultTextColor(colour)
        text.setPos(radius + 4, -radius - 12)
        text.setZValue(24)

        self.setPos(float(circle.center[0]), float(circle.center[1]))
        self._callbacks_enabled = True

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):  # type: ignore[override]
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and isinstance(value, QPointF):
            return self._clamp_center(value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self._callbacks_enabled:
            self._on_moved(self._as_circle())
        return super().itemChange(change, value)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._on_move_finished(self._as_circle())

    def _as_circle(self) -> CircleAnnotation:
        pos = self.pos()
        return CircleAnnotation(
            center=(float(pos.x()), float(pos.y())),
            radius_px=float(self._radius),
        )

    def _clamp_center(self, point: QPointF) -> QPointF:
        return QPointF(
            min(max(point.x(), self._image_rect.left()), self._image_rect.right()),
            min(max(point.y(), self._image_rect.top()), self._image_rect.bottom()),
        )


class ImageCanvas(QGraphicsView):
    point_created = Signal(str, object)
    line_created = Signal(str, object)
    circle_created = Signal(object)

    point_moved = Signal(str, int, object)
    point_move_finished = Signal(str, int, object)
    circle_moved = Signal(object)
    circle_move_finished = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.pixmap_item: QGraphicsPixmapItem | None = None
        self.current_tool = "pan"
        self.style = CanvasStyle()
        self.overlay_items: list[QGraphicsItem] = []
        self.preview_item: QGraphicsItem | None = None
        self._drag_start: QPointF | None = None
        self._zoom_factor = 1.0
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))

    # ------------------------------------------------------------------
    # Canvas state
    # ------------------------------------------------------------------
    def set_tool(self, tool: str) -> None:
        self.current_tool = tool
        if tool == "pan":
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._clear_preview()

    def has_image(self) -> bool:
        return self.pixmap_item is not None

    def image_size(self) -> tuple[int, int] | None:
        if self.pixmap_item is None:
            return None
        pixmap = self.pixmap_item.pixmap()
        return pixmap.width(), pixmap.height()

    def image_rect(self) -> QRectF:
        if self.pixmap_item is None:
            return QRectF()
        return self.pixmap_item.boundingRect()

    def load_image(self, image_path: str | Path) -> None:
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            raise ValueError(f"Could not load image: {image_path}")
        self.scene.clear()
        self.overlay_items.clear()
        self.preview_item = None
        self.pixmap_item = self.scene.addPixmap(pixmap)
        self.pixmap_item.setZValue(0)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self.resetTransform()
        self._zoom_factor = 1.0
        self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def clear_overlays(self) -> None:
        for item in self.overlay_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self.overlay_items.clear()
        self._clear_preview()

    # ------------------------------------------------------------------
    # Overlay rendering
    # ------------------------------------------------------------------
    def add_point_marker(
        self,
        point: Point,
        label: str,
        *,
        colour: QColor | None = None,
        radius: float | None = None,
        draggable_kind: str | None = None,
        draggable_index: int | None = None,
    ) -> None:
        colour = colour or QColor(255, 214, 10)
        radius = radius if radius is not None else self.style.marker_radius
        if draggable_kind is not None and draggable_index is not None:
            item = _MovablePointMarker(
                point=point,
                label=label,
                colour=colour,
                radius=radius,
                pen_width=self.style.point_pen_width,
                image_rect=self.image_rect(),
                on_moved=lambda new_point, kind=draggable_kind, index=draggable_index: self.point_moved.emit(kind, index, new_point),
                on_move_finished=lambda new_point, kind=draggable_kind, index=draggable_index: self.point_move_finished.emit(kind, index, new_point),
            )
            self.scene.addItem(item)
            self.overlay_items.append(item)
            return

        ellipse = self.scene.addEllipse(
            point[0] - radius,
            point[1] - radius,
            2 * radius,
            2 * radius,
            QPen(colour, self.style.point_pen_width),
            QBrush(QColor(colour.red(), colour.green(), colour.blue(), 70)),
        )
        ellipse.setZValue(10)
        text = self.scene.addText(label)
        text.setDefaultTextColor(colour)
        text.setPos(point[0] + radius + 2, point[1] - radius - 10)
        text.setZValue(11)
        self.overlay_items.extend([ellipse, text])

    def add_line_marker(
        self,
        line: LineAnnotation,
        label: str,
        *,
        colour: QColor | None = None,
    ) -> None:
        colour = colour or QColor(100, 220, 255)
        item = self.scene.addLine(
            line.start[0],
            line.start[1],
            line.end[0],
            line.end[1],
            QPen(colour, self.style.line_pen_width),
        )
        item.setZValue(8)
        mid_x = (line.start[0] + line.end[0]) / 2.0
        mid_y = (line.start[1] + line.end[1]) / 2.0
        text = self.scene.addText(label)
        text.setDefaultTextColor(colour)
        text.setPos(mid_x + 4, mid_y + 4)
        text.setZValue(9)
        self.overlay_items.extend([item, text])

    def add_circle_marker(
        self,
        circle: CircleAnnotation,
        label: str,
        *,
        colour: QColor | None = None,
        draggable: bool = False,
    ) -> None:
        colour = colour or QColor(255, 120, 120)
        radius = max(circle.radius_px, 2.0)
        if draggable:
            item = _MovableCircleMarker(
                circle=circle,
                label=label,
                colour=colour,
                pen_width=self.style.target_pen_width,
                image_rect=self.image_rect(),
                on_moved=lambda updated: self.circle_moved.emit(updated),
                on_move_finished=lambda updated: self.circle_move_finished.emit(updated),
            )
            self.scene.addItem(item)
            self.overlay_items.append(item)
            return

        ellipse = self.scene.addEllipse(
            circle.center[0] - radius,
            circle.center[1] - radius,
            2 * radius,
            2 * radius,
            QPen(colour, self.style.target_pen_width),
            QBrush(QColor(colour.red(), colour.green(), colour.blue(), 30)),
        )
        ellipse.setZValue(12)
        center = self.scene.addEllipse(
            circle.center[0] - 2.5,
            circle.center[1] - 2.5,
            5.0,
            5.0,
            QPen(colour, 1.0),
            QBrush(colour),
        )
        center.setZValue(13)
        text = self.scene.addText(label)
        text.setDefaultTextColor(colour)
        text.setPos(circle.center[0] + radius + 4, circle.center[1] - radius - 10)
        text.setZValue(14)
        self.overlay_items.extend([ellipse, center, text])

    # ------------------------------------------------------------------
    # Creation gestures
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.pixmap_item is None:
            super().mousePressEvent(event)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        # First let existing draggable graphics items claim their drag gesture.
        scene_point = self.mapToScene(event.position().toPoint())
        existing = self.scene.itemAt(scene_point, self.transform())
        if isinstance(existing, (_MovablePointMarker, _MovableCircleMarker)):
            super().mousePressEvent(event)
            return
        parent = existing.parentItem() if existing is not None else None
        if isinstance(parent, (_MovablePointMarker, _MovableCircleMarker)):
            super().mousePressEvent(event)
            return

        if not self._point_inside_image(scene_point):
            super().mousePressEvent(event)
            return

        if self.current_tool in POINT_TOOLS:
            self.point_created.emit(self.current_tool, (float(scene_point.x()), float(scene_point.y())))
            return

        if self.current_tool in LINE_TOOLS or self.current_tool in CIRCLE_TOOLS:
            self._drag_start = scene_point
            self._clear_preview()
            if self.current_tool in LINE_TOOLS:
                self.preview_item = self.scene.addLine(
                    scene_point.x(),
                    scene_point.y(),
                    scene_point.x(),
                    scene_point.y(),
                    QPen(QColor(255, 255, 255), 1.0, Qt.PenStyle.DashLine),
                )
            else:
                self.preview_item = self.scene.addEllipse(
                    scene_point.x(),
                    scene_point.y(),
                    1.0,
                    1.0,
                    QPen(QColor(255, 255, 255), 1.0, Qt.PenStyle.DashLine),
                )
            if self.preview_item is not None:
                self.preview_item.setZValue(99)
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.pixmap_item is None or self._drag_start is None or self.preview_item is None:
            super().mouseMoveEvent(event)
            return
        current = self.mapToScene(event.position().toPoint())
        current = self._clamp_to_image(current)
        if self.current_tool in LINE_TOOLS and isinstance(self.preview_item, QGraphicsLineItem):
            self.preview_item.setLine(
                self._drag_start.x(), self._drag_start.y(), current.x(), current.y()
            )
            return
        if self.current_tool in CIRCLE_TOOLS and isinstance(self.preview_item, QGraphicsEllipseItem):
            radius = max(
                2.0,
                ((current.x() - self._drag_start.x()) ** 2 + (current.y() - self._drag_start.y()) ** 2) ** 0.5,
            )
            self.preview_item.setRect(
                self._drag_start.x() - radius,
                self._drag_start.y() - radius,
                2 * radius,
                2 * radius,
            )
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            self.pixmap_item is None
            or self._drag_start is None
            or event.button() != Qt.MouseButton.LeftButton
        ):
            super().mouseReleaseEvent(event)
            return

        current = self.mapToScene(event.position().toPoint())
        current = self._clamp_to_image(current)
        start = self._drag_start
        if self.current_tool in LINE_TOOLS:
            line = LineAnnotation(
                start=(float(start.x()), float(start.y())),
                end=(float(current.x()), float(current.y())),
            )
            self.line_created.emit(self.current_tool, line)
        elif self.current_tool in CIRCLE_TOOLS:
            radius = max(
                2.0,
                ((current.x() - start.x()) ** 2 + (current.y() - start.y()) ** 2) ** 0.5,
            )
            circle = CircleAnnotation(center=(float(start.x()), float(start.y())), radius_px=float(radius))
            self.circle_created.emit(circle)

        self._drag_start = None
        self._clear_preview()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.pixmap_item is None:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        next_zoom = self._zoom_factor * factor
        if 0.05 <= next_zoom <= 40.0:
            self.scale(factor, factor)
            self._zoom_factor = next_zoom

    def fit_image(self) -> None:
        if self.pixmap_item is not None:
            self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _point_inside_image(self, point: QPointF) -> bool:
        if self.pixmap_item is None:
            return False
        return self.pixmap_item.boundingRect().contains(point)

    def _clamp_to_image(self, point: QPointF) -> QPointF:
        if self.pixmap_item is None:
            return point
        rect = self.pixmap_item.boundingRect()
        return QPointF(
            min(max(point.x(), rect.left()), rect.right()),
            min(max(point.y(), rect.top()), rect.bottom()),
        )

    def _clear_preview(self) -> None:
        if self.preview_item is not None and self.preview_item.scene() is self.scene:
            self.scene.removeItem(self.preview_item)
        self.preview_item = None
