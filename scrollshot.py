"""Windows scrolling screenshot utility."""

import ctypes
import io
import sys
import time
from dataclasses import dataclass
from ctypes import wintypes
from pathlib import Path
from threading import Event

# Match Qt's desktop coordinates to physical pixels, including mixed-DPI screens.
if sys.platform == "win32":
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except OSError:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)

import cv2
import mss
import numpy as np
from PIL import Image
from PySide6.QtCore import QAbstractNativeEventFilter, QBuffer, QByteArray, QEvent, QIODevice, QPoint, QPointF, QRect, QRectF, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap, QPolygonF, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)


HOTKEY_ID = 0x5351
ESC_ID = 0x5352
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
VK_ESCAPE = 0x1B
MAX_FRAMES = 40
MAX_HEIGHT = 30000
POLL_SECONDS = .25
STABLE_POLLS = 2
IDLE_SECONDS = 12
PREVIEW_WIDTH = 272
ANNOTATION_COLOR = QColor("#ff7626")


@dataclass(eq=False)
class TextAnnotation:
    rect: QRectF
    text: str = ""
    font_size: float = 24.0


def app_icon(size=64) -> QIcon:
    canvas = QPixmap(size, size)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size / 64, size / 64)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#111111"))
    painter.drawRoundedRect(2, 2, 60, 60, 13, 13)
    painter.setPen(QPen(Qt.white, 3.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawLine(15, 25, 15, 15)
    painter.drawLine(15, 15, 27, 15)
    painter.drawLine(37, 15, 49, 15)
    painter.drawLine(49, 15, 49, 25)
    painter.drawLine(15, 36, 15, 46)
    painter.drawLine(15, 46, 27, 46)
    painter.drawLine(37, 46, 49, 46)
    painter.drawLine(49, 46, 49, 36)
    painter.drawLine(32, 23, 32, 38)
    painter.drawLine(26, 32, 32, 38)
    painter.drawLine(32, 38, 38, 32)
    painter.end()
    return QIcon(canvas)


def tool_icon(name: str, color="#171717") -> QIcon:
    canvas = QPixmap(24, 24)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    if name == "rectangle":
        painter.drawRoundedRect(4, 5, 16, 14, 2, 2)
    elif name == "ellipse":
        painter.drawEllipse(4, 4, 16, 16)
    elif name == "arrow":
        painter.drawLine(5, 19, 19, 5)
        painter.drawLine(12, 5, 19, 5)
        painter.drawLine(19, 5, 19, 12)
    elif name == "pen":
        painter.drawLine(5, 18, 17, 6)
        painter.drawLine(8, 20, 20, 8)
        painter.drawLine(17, 6, 20, 8)
        painter.drawLine(5, 18, 4, 21)
    elif name == "mosaic":
        painter.drawRect(4, 4, 16, 16)
        painter.fillRect(5, 5, 7, 7, QColor(color))
        painter.fillRect(13, 13, 6, 6, QColor(color))
    elif name == "text":
        painter.drawLine(4, 5, 20, 5)
        painter.drawLine(12, 5, 12, 20)
    elif name == "undo":
        painter.drawLine(9, 7, 4, 12)
        painter.drawLine(4, 12, 9, 17)
        painter.drawArc(5, 5, 16, 15, -80 * 16, 215 * 16)
    elif name == "save":
        painter.drawLine(12, 3, 12, 16)
        painter.drawLine(7, 11, 12, 16)
        painter.drawLine(12, 16, 17, 11)
        painter.drawLine(4, 20, 20, 20)
    elif name == "copy":
        painter.drawRect(7, 7, 13, 13)
        painter.drawLine(4, 16, 4, 4)
        painter.drawLine(4, 4, 16, 4)
    elif name == "close":
        painter.drawLine(5, 5, 19, 19)
        painter.drawLine(19, 5, 5, 19)
    elif name == "check":
        painter.drawLine(4, 12, 10, 18)
        painter.drawLine(10, 18, 20, 6)
    elif name == "pin":
        painter.drawLine(7, 5, 17, 5)
        painter.drawLine(9, 5, 9, 12)
        painter.drawLine(15, 5, 15, 12)
        painter.drawLine(6, 13, 18, 13)
        painter.drawLine(12, 13, 12, 21)
    elif name == "scroll":
        painter.drawRoundedRect(6, 3, 12, 18, 5, 5)
        painter.drawLine(12, 7, 12, 11)
        painter.drawLine(9, 14, 12, 17)
        painter.drawLine(12, 17, 15, 14)
    elif name == "capture":
        painter.drawRoundedRect(4, 6, 16, 13, 2, 2)
        painter.drawEllipse(9, 9, 6, 6)
        painter.drawLine(8, 6, 10, 4)
        painter.drawLine(10, 4, 15, 4)
    painter.end()
    return QIcon(canvas)


def icon_button(name, tooltip, callback, *, checkable=False, accent=False):
    button = QPushButton()
    button.setObjectName("toolAccent" if accent else "toolButton")
    button.setIcon(tool_icon(name, "#ffffff" if accent else "#171717"))
    button.setIconSize(QSize(22, 22))
    button.setFixedSize(40, 40)
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    button.setCheckable(checkable)
    button.clicked.connect(callback)
    return button


def exclude_from_capture(widget):
    # Windows 10+ keeps the always-on-top controls out of desktop screenshots.
    if sys.platform == "win32":
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(int(widget.winId()), 0x11))
    return False


def preview_frame(strips, width):
    scale = min(1, PREVIEW_WIDTH / width)
    thumb_width = max(1, round(width * scale))
    thumbs = [strip.resize((thumb_width, max(1, round(strip.height * scale)))) for strip in strips]
    result = Image.new("RGB", (thumb_width, sum(strip.height for strip in thumbs)))
    offset = 0
    for strip in thumbs:
        result.paste(strip, (0, offset))
        offset += strip.height
    buffer = io.BytesIO()
    result.save(buffer, "PNG")
    return buffer.getvalue()


def physical_cursor() -> QPoint:
    point = wintypes.POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        raise OSError("无法读取鼠标位置")
    return QPoint(point.x, point.y)


def frame_changed(previous: Image.Image, current: Image.Image) -> bool:
    a = np.asarray(previous)
    b = np.asarray(current)
    # Sparse samples keep polling inexpensive, while ignoring cursor blinks and tiny animations.
    return float(np.mean(np.abs(a[::4, ::4].astype(np.int16) - b[::4, ::4].astype(np.int16)))) >= 2


def overlap_shift(previous: Image.Image, current: Image.Image) -> int | None:
    """Find how far content advanced, using a strip low in the previous frame."""
    if previous.size != current.size:
        return None
    width, height = previous.size
    if width < 100 or height < 120:
        return None
    scale = min(1.0, 640 / width)
    w, h = max(1, round(width * scale)), max(1, round(height * scale))
    a = cv2.cvtColor(cv2.resize(np.asarray(previous), (w, h)), cv2.COLOR_RGB2GRAY)
    b = cv2.cvtColor(cv2.resize(np.asarray(current), (w, h)), cv2.COLOR_RGB2GRAY)
    x0, x1 = round(w * .08), round(w * .92)
    y0 = round(h * .72)
    band = max(12, round(h * .10))
    template = a[y0:y0 + band, x0:x1]
    search = b[:y0 + band, x0:x1]
    if float(np.std(template)) < 3:
        return None
    _, score, _, position = cv2.minMaxLoc(cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED))
    shift = round((y0 - position[1]) / scale)
    if score < .72 or shift < 12 or shift > height * .85:
        return None
    # Correlation alone can match repeated rows; verify actual pixel agreement.
    y = round(position[1] / scale)
    original_y = round(y0 / scale)
    strip_h = max(8, round(band / scale))
    left, right = round(x0 / scale), round(x1 / scale)
    error = np.mean(np.abs(
        np.asarray(previous)[original_y:original_y + strip_h, left:right].astype(np.int16)
        - np.asarray(current)[y:y + strip_h, left:right].astype(np.int16)
    ))
    return shift if error < 24 else None


class CaptureWorker(QThread):
    progress = Signal(int)
    preview = Signal(bytes, int, int)
    activity = Signal(str)
    completed = Signal(bytes, str)
    failed = Signal(str)

    def __init__(self, rect: QRect):
        super().__init__()
        self.rect = QRect(rect)
        self.cancel = Event()

    def run(self):
        try:
            area = dict(left=self.rect.x(), top=self.rect.y(),
                        width=self.rect.width(), height=self.rect.height())
            strips = []
            total_height = 0
            with mss.mss() as screen:
                def grab():
                    shot = screen.grab(area)
                    return Image.frombytes("RGB", shot.size, shot.rgb)

                previous = grab()
                strips.append(previous)
                total_height += previous.height
                self.preview.emit(preview_frame(strips, self.rect.width()), 1, total_height)
                reason = "已手动结束"
                last_advance = time.monotonic()
                candidate = previous
                stable = 0
                while True:
                    if self.cancel.is_set():
                        break
                    if self.cancel.wait(POLL_SECONDS):
                        break
                    current = grab()
                    if frame_changed(candidate, current):
                        candidate = current
                        stable = 0
                        self.activity.emit("页面正在滚动，等待画面停稳…")
                    else:
                        stable += 1
                    if stable >= STABLE_POLLS and frame_changed(previous, candidate):
                        shift = overlap_shift(previous, candidate)
                        if shift is not None:
                            remaining = MAX_HEIGHT - total_height
                            added = min(shift, remaining)
                            strips.append(candidate.crop((0, candidate.height - shift, candidate.width,
                                                          candidate.height - shift + added)))
                            total_height += added
                            previous = candidate
                            self.progress.emit(len(strips))
                            self.preview.emit(preview_frame(strips, self.rect.width()),
                                              len(strips), total_height)
                            self.activity.emit("已拼接新内容，继续手动滚动")
                            last_advance = time.monotonic()
                            if total_height >= MAX_HEIGHT or len(strips) >= MAX_FRAMES:
                                reason = "长图已到上限，不能继续滚动截取"
                                break
                        else:
                            # Keep the last stitched frame; a later scroll may have enough overlap.
                            candidate = previous
                            self.activity.emit("画面变化过大，未拼接；请小幅滚动")
                        stable = 0
                    if time.monotonic() - last_advance >= IDLE_SECONDS:
                        reason = "未检测到可拼接的滚动内容，区域可能不可滚动"
                        break
            result = Image.new("RGB", (self.rect.width(), total_height))
            offset = 0
            for strip in strips:
                result.paste(strip, (0, offset))
                offset += strip.height
            buffer = io.BytesIO()
            result.save(buffer, "PNG")
            self.completed.emit(buffer.getvalue(), reason)
        except Exception as exc:
            self.failed.emit(str(exc))


class Selection(QWidget):
    selected = Signal(QRect)
    still_selected = Signal(QRect)
    area_changed = Signal(QRect)
    cancelled = Signal()

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.StrongFocus)
        self.origin = None
        self.end = None
        self.selection = None
        self.physical_origin = None
        self.physical_selection = None
        self.toolbar = None

    def begin(self):
        bounds = QGuiApplication.primaryScreen().virtualGeometry()
        self.setGeometry(bounds)
        self.origin = self.end = self.selection = None
        self.physical_origin = self.physical_selection = None
        if self.toolbar is not None:
            self.toolbar.hide()
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.setCursor(Qt.CrossCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.cancelled.emit()
            return
        if event.button() == Qt.LeftButton:
            if self.toolbar is not None:
                self.toolbar.hide()
            self.origin = event.position().toPoint()
            self.physical_origin = physical_cursor()
            self.end = self.origin
            self.selection = None
            self.physical_selection = None
            self.update()

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            self.end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.origin is not None:
            self.end = event.position().toPoint()
            rect = QRect(self.origin, self.end).normalized()
            physical = QRect(self.physical_origin, physical_cursor()).normalized()
            self.origin = None
            if physical.width() >= 100 and physical.height() >= 120:
                self.selection = rect
                self.physical_selection = physical
                self.area_changed.emit(rect.translated(self.geometry().topLeft()))
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
        elif event.key() == Qt.Key_S and self.physical_selection is not None:
            self.selected.emit(self.physical_selection)
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.physical_selection is not None:
            self.still_selected.emit(self.physical_selection)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(15, 23, 32, 130))
        area = self.selection
        if self.origin is not None and self.end is not None:
            area = QRect(self.origin, self.end).normalized()
        if area is not None and area.width() and area.height():
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(area, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor("#111111"), 4))
            painter.drawRect(area.adjusted(0, 0, -1, -1))
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawRect(area.adjusted(0, 0, -1, -1))
            text = f"{area.width()} × {area.height()}"
            pos = QPoint(max(12, area.x()), max(30, area.y() - 12))
        else:
            text = "拖拽选择滚动区域  ·  Esc 取消"
            pos = QPoint(24, 44)
        painter.setPen(Qt.white)
        painter.setFont(QFont("Microsoft YaHei UI", 11, QFont.DemiBold))
        painter.drawText(pos, text)


class SelectionToolbar(QWidget):
    still_requested = Signal(str)
    scroll_requested = Signal()
    cancelled = Signal()

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                         Qt.WindowDoesNotAcceptFocus)
        self.setObjectName("floatingToolbar")
        row = QHBoxLayout(self)
        row.setContentsMargins(9, 7, 9, 7)
        row.setSpacing(5)
        row.addWidget(icon_button("capture", "截取当前选区 (Enter)",
                                   lambda: self.still_requested.emit("preview")))
        row.addWidget(icon_button("scroll", "开始手动滚动长截图 (S)", self.scroll_requested.emit))
        row.addSpacing(8)
        for tool, label in (("rectangle", "矩形"), ("ellipse", "椭圆"), ("arrow", "箭头"),
                            ("pen", "画笔"), ("mosaic", "马赛克"), ("text", "文字")):
            row.addWidget(icon_button(tool, f"截取后添加{label}",
                                       lambda checked=False, mode=tool: self.still_requested.emit(mode)))
        row.addSpacing(8)
        for action, label in (("pin", "截取并置顶"), ("copy", "截取并复制"),
                              ("save", "截取并保存 PNG")):
            row.addWidget(icon_button(action, label,
                                       lambda checked=False, mode=action: self.still_requested.emit(mode)))
        row.addWidget(icon_button("close", "取消选区 (Esc)", self.cancelled.emit))
        row.addWidget(icon_button("check", "确认并截取当前选区 (Enter)",
                                   lambda: self.still_requested.emit("preview"), accent=True))
        self.setFixedSize(row.sizeHint().width(), 56)

    def place(self, area: QRect, desktop: QRect):
        x = max(desktop.left() + 8, min(area.right() - self.width() + 1,
                                        desktop.right() - self.width() - 8))
        below = area.bottom() + 12
        y = below if below + self.height() <= desktop.bottom() - 8 else area.top() - self.height() - 12
        y = max(desktop.top() + 8, min(y, desktop.bottom() - self.height() - 8))
        self.move(x, y)
        self.show()


class TextEditor(QTextEdit):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.annotation = None
        self.drag_mode = None
        self.drag_start = QPointF()
        self.original_rect = QRectF()
        self.original_size = 24.0
        self.setAcceptRichText(False)
        self.setFrameShape(QTextEdit.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QTextEdit { background: rgba(255,255,255,220); color: #ff7626; "
                           "border: 1px dashed #ff7626; padding: 12px; }")
        self.viewport().setMouseTracking(True)
        self.viewport().installEventFilter(self)
        self.textChanged.connect(self.sync_text)
        self.hide()

    def sync_text(self):
        if self.annotation is not None:
            self.annotation.text = self.toPlainText()
            self.canvas.changed.emit()
            self.canvas.update()

    def edit(self, annotation, focus=True):
        self.annotation = annotation
        self.setReadOnly(False)
        self.setPlainText(annotation.text)
        self.reposition()
        self.show()
        self.raise_()
        if focus:
            self.setFocus()
            self.moveCursor(QTextCursor.End)

    def select(self, annotation):
        self.annotation = annotation
        self.setReadOnly(True)
        self.setPlainText(annotation.text)
        self.reposition()
        self.show()
        self.raise_()

    def finish_edit(self):
        if not self.isReadOnly():
            self.setReadOnly(True)
            self.hide()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.finish_edit()

    def reposition(self):
        if self.annotation is None:
            return
        area = self.canvas.image_rect()
        scale_x = area.width() / self.canvas.base.width()
        scale_y = area.height() / self.canvas.base.height()
        rect = self.annotation.rect
        self.setGeometry(round(area.left() + rect.left() * scale_x),
                         round(area.top() + rect.top() * scale_y),
                         max(30, round(rect.width() * scale_x)),
                         max(24, round(rect.height() * scale_y)))
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(max(8, round(self.annotation.font_size * scale_y)))
        self.setFont(font)

    def handle_at(self, point):
        bounds = self.viewport().geometry()
        margin = 14
        if bounds.right() - point.x() <= margin or bounds.bottom() - point.y() <= margin:
            return "resize"
        if point.x() - bounds.left() <= margin or point.y() - bounds.top() <= margin:
            return "move"
        return None

    def eventFilter(self, watched, event):
        if watched is not self.viewport():
            return super().eventFilter(watched, event)
        if event.type() == QEvent.MouseMove and self.drag_mode is None:
            handle = self.handle_at(self.viewport().mapTo(self, event.position().toPoint()))
            self.viewport().setCursor(Qt.SizeFDiagCursor if handle == "resize" else
                                      Qt.SizeAllCursor if handle == "move" or self.isReadOnly() else
                                      Qt.IBeamCursor)
        if event.type() in (QEvent.MouseButtonPress, QEvent.MouseMove, QEvent.MouseButtonRelease):
            point = self.viewport().mapTo(self, event.position().toPoint())
            if event.type() == QEvent.MouseButtonPress:
                return self.begin_drag(point, event)
            if event.type() == QEvent.MouseMove and self.drag_mode is not None:
                self.move_drag(event.globalPosition())
                return True
            if event.type() == QEvent.MouseButtonRelease and self.drag_mode is not None:
                self.drag_mode = None
                return True
        return super().eventFilter(watched, event)

    def begin_drag(self, point, event):
        handle = self.handle_at(point)
        if event.button() == Qt.LeftButton and (handle is not None or self.isReadOnly()):
            self.drag_mode = handle or "move"
            self.drag_start = event.globalPosition()
            self.original_rect = QRectF(self.annotation.rect)
            self.original_size = self.annotation.font_size
            event.accept()
            return True
        return False

    def mousePressEvent(self, event):
        if self.begin_drag(event.position(), event):
            return
        super().mousePressEvent(event)

    def move_drag(self, global_position):
        area = self.canvas.image_rect()
        scale_x = area.width() / self.canvas.base.width()
        scale_y = area.height() / self.canvas.base.height()
        delta = global_position - self.drag_start
        dx, dy = delta.x() / scale_x, delta.y() / scale_y
        rect = QRectF(self.original_rect)
        if self.drag_mode == "move":
            rect.moveTopLeft(QPointF(max(0, min(self.canvas.base.width() - rect.width(), rect.x() + dx)),
                                     max(0, min(self.canvas.base.height() - rect.height(), rect.y() + dy))))
        else:
            rect.setWidth(max(55, min(self.canvas.base.width() - rect.x(), rect.width() + dx)))
            rect.setHeight(max(30, min(self.canvas.base.height() - rect.y(), rect.height() + dy)))
            self.annotation.font_size = max(10, min(160, self.original_size * max(
                rect.width() / self.original_rect.width(),
                rect.height() / self.original_rect.height())))
        self.annotation.rect = rect
        self.reposition()
        self.canvas.changed.emit()
        self.canvas.update()

    def mouseMoveEvent(self, event):
        if self.drag_mode is None:
            super().mouseMoveEvent(event)
            return
        self.move_drag(event.globalPosition())
        event.accept()

    def mouseReleaseEvent(self, event):
        if self.drag_mode is not None:
            self.drag_mode = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


class AnnotationCanvas(QWidget):
    changed = Signal()

    def __init__(self, data: bytes):
        super().__init__()
        self.base = QPixmap.fromImage(QImage.fromData(data))
        self.setMinimumSize(1, 1)
        self.setMouseTracking(True)
        self.tool = None
        self.operations = []
        self.draft = None
        self.zoom = 1.0
        self.offset = QPointF(0, 0)
        self.drag_mode = None
        self.drag_start = QPointF()
        self.drag_zoom = 1.0
        self.drag_offset = QPointF()
        self.drag_global = QPointF()
        self.drag_edge = None
        self.editor = TextEditor(self)
        self.pin_button = icon_button("pin", "取消置顶", lambda: self.window().toggle_pin(False))
        self.pin_button.setParent(self)
        self.pin_button.hide()

    def fit_rect(self):
        if self.base.isNull():
            return QRectF()
        scale = min(self.width() / self.base.width(), self.height() / self.base.height())
        width, height = self.base.width() * scale, self.base.height() * scale
        return QRectF((self.width() - width) / 2, 0, width, height)

    def image_rect(self):
        fitted = self.fit_rect()
        center = fitted.center() + self.offset
        width, height = fitted.width() * self.zoom, fitted.height() * self.zoom
        return QRectF(center.x() - width / 2, center.y() - height / 2, width, height)

    def set_zoom(self, zoom, anchor=None):
        old = self.image_rect()
        zoom = max(0.2, min(12.0, zoom))
        if abs(zoom - self.zoom) < 0.001 or old.isEmpty():
            return
        anchor = anchor or self.rect().center()
        relative = QPointF((anchor.x() - old.left()) / old.width(),
                           (anchor.y() - old.top()) / old.height())
        self.zoom = zoom
        changed = self.image_rect()
        self.offset += QPointF(anchor.x() - (changed.left() + relative.x() * changed.width()),
                               anchor.y() - (changed.top() + relative.y() * changed.height()))
        self.editor.reposition()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.editor.reposition()

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120
        if steps:
            if self.window().pinned:
                self.window().resize_pinned(1.16 ** steps, event.position())
            else:
                self.set_zoom(self.zoom * 1.16 ** steps, event.position())
        event.accept()

    def update_pin_button(self, position):
        if not self.window().pinned or not self.image_rect().contains(position):
            self.pin_button.hide()
            return
        area = self.image_rect().intersected(QRectF(self.rect()))
        self.pin_button.move(max(0, round(area.right() - self.pin_button.width() - 8)),
                             max(0, round(area.top() + 8)))
        self.pin_button.show()
        self.pin_button.raise_()

    def leaveEvent(self, event):
        if not self.pin_button.underMouse():
            self.pin_button.hide()
        super().leaveEvent(event)

    def image_point(self, position):
        area = self.image_rect()
        if not area.contains(position) or area.isEmpty():
            return None
        return QPoint(min(self.base.width() - 1, max(0, int((position.x() - area.left()) * self.base.width() / area.width()))),
                      min(self.base.height() - 1, max(0, int((position.y() - area.top()) * self.base.height() / area.height()))))

    def set_tool(self, tool):
        self.editor.finish_edit()
        self.editor.hide()
        self.tool = tool
        self.setCursor(Qt.CrossCursor if tool else Qt.ArrowCursor)

    def text_at(self, point):
        for operation in reversed(self.operations):
            if isinstance(operation, TextAnnotation) and operation.rect.contains(point):
                return operation
        return None

    def add_text(self, point):
        width = min(240, self.base.width())
        height = min(70, self.base.height())
        left = min(point.x(), self.base.width() - width)
        top = min(point.y(), self.base.height() - height)
        annotation = TextAnnotation(QRectF(left, top, width, height))
        self.operations.append(annotation)
        self.editor.edit(annotation)
        self.changed.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton and self.window().pinned:
            if self.image_rect().contains(event.position()):
                self.window().close()
                event.accept()
            return
        if event.button() == Qt.MiddleButton and not self.window().pinned:
            self.drag_mode = "pan"
            self.drag_start = event.position()
            self.drag_offset = QPointF(self.offset)
            event.accept()
            return
        if event.button() != Qt.LeftButton:
            return
        area = self.image_rect()
        point = self.image_point(event.position())
        if point is not None:
            annotation = self.text_at(point)
            if annotation is not None and self.tool in (None, "text"):
                self.editor.finish_edit()
                self.editor.select(annotation)
                return
        if self.editor.isVisible():
            self.editor.finish_edit()
            self.editor.hide()
        if self.tool is None and area.contains(event.position()):
            self.drag_start = event.position()
            self.drag_global = event.globalPosition()
            self.drag_offset = QPointF(self.offset)
            self.drag_zoom = self.zoom
            distances = (abs(event.position().x() - area.left()),
                         abs(event.position().x() - area.right()),
                         abs(event.position().y() - area.top()),
                         abs(event.position().y() - area.bottom()))
            self.drag_edge = min(range(4), key=distances.__getitem__)
            self.drag_mode = "edge" if distances[self.drag_edge] <= 12 and not self.window().pinned else "window"
            event.accept()
            return
        if self.tool is None:
            return
        if point is None:
            return
        if self.tool == "text":
            self.add_text(point)
        else:
            self.draft = (self.tool, point, [point] if self.tool == "pen" else point)

    def mouseMoveEvent(self, event):
        self.update_pin_button(event.position())
        if self.drag_mode == "edge":
            delta = event.position() - self.drag_start
            outward = (-delta.x(), delta.x(), -delta.y(), delta.y())[self.drag_edge]
            extent = self.fit_rect().width() if self.drag_edge < 2 else self.fit_rect().height()
            self.set_zoom(self.drag_zoom * max(0.2, 1 + outward / max(120, extent)),
                          self.drag_start)
            return
        if self.drag_mode == "window":
            delta = event.globalPosition() - self.drag_global
            self.window().move(self.window().pos() + delta.toPoint())
            self.drag_global = event.globalPosition()
            self.window().raise_()
            return
        if self.drag_mode == "pan":
            self.offset = self.drag_offset + event.position() - self.drag_start
            self.update()
            return
        if self.draft is None:
            if self.tool is None and not self.window().pinned:
                area = self.image_rect()
                if area.contains(event.position()):
                    horizontal = min(abs(event.position().x() - area.left()),
                                     abs(event.position().x() - area.right()))
                    vertical = min(abs(event.position().y() - area.top()),
                                   abs(event.position().y() - area.bottom()))
                    self.setCursor(Qt.SizeHorCursor if horizontal <= min(12, vertical) else
                                   Qt.SizeVerCursor if vertical <= 12 else Qt.OpenHandCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)
            return
        tool, start, _ = self.draft
        point = self.image_point(event.position())
        if point is None:
            return
        if tool == "pen":
            self.draft[2].append(point)
        else:
            self.draft = (tool, start, point)
        self.update()

    def mouseReleaseEvent(self, event):
        if self.drag_mode is not None:
            self.drag_mode = None
            self.drag_edge = None
            return
        if event.button() != Qt.LeftButton or self.draft is None:
            return
        self.mouseMoveEvent(event)
        tool, start, end = self.draft
        if tool == "pen" or (start - end).manhattanLength() > 3:
            self.operations.append(self.draft)
            self.changed.emit()
        self.draft = None
        self.update()

    def undo(self):
        if self.operations:
            if self.operations[-1] is self.editor.annotation:
                self.editor.hide()
                self.editor.annotation = None
            self.operations.pop()
            self.changed.emit()
            self.update()

    def _draw_operation(self, painter, operation):
        if isinstance(operation, TextAnnotation):
            painter.setPen(ANNOTATION_COLOR)
            font = QFont("Microsoft YaHei UI")
            font.setPixelSize(round(operation.font_size))
            painter.setFont(font)
            painter.drawText(operation.rect.adjusted(6, 5, -6, -5),
                             Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, operation.text)
            return
        tool, start, end = operation
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(ANNOTATION_COLOR, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if tool == "rectangle":
            painter.drawRect(QRect(start, end).normalized())
        elif tool == "ellipse":
            painter.drawEllipse(QRect(start, end).normalized())
        elif tool == "arrow":
            vx, vy = end.x() - start.x(), end.y() - start.y()
            length = max(1, (vx * vx + vy * vy) ** .5)
            ux, uy = vx / length, vy / length
            nx, ny = -uy, ux
            head = min(18, length * .4)
            base_x, base_y = end.x() - ux * head, end.y() - uy * head
            shape = QPolygonF([
                QPointF(start.x() + nx, start.y() + ny),
                QPointF(base_x + nx * 3.5, base_y + ny * 3.5),
                QPointF(base_x + nx * 7, base_y + ny * 7),
                QPointF(end),
                QPointF(base_x - nx * 7, base_y - ny * 7),
                QPointF(base_x - nx * 3.5, base_y - ny * 3.5),
                QPointF(start.x() - nx, start.y() - ny),
            ])
            painter.setPen(Qt.NoPen)
            painter.setBrush(ANNOTATION_COLOR)
            painter.drawPolygon(shape)
        elif tool == "pen":
            for first, second in zip(end, end[1:]):
                painter.drawLine(first, second)

    def rendered(self, include_active=True):
        result = self.base.copy()
        painter = QPainter(result)
        for operation in self.operations:
            if isinstance(operation, TextAnnotation):
                if include_active or operation is not self.editor.annotation or not self.editor.isVisible():
                    self._draw_operation(painter, operation)
                continue
            tool, start, end = operation
            if tool == "mosaic":
                area = QRect(start, end).normalized().intersected(result.rect())
                if area.width() and area.height():
                    small = result.copy(area).scaled(max(1, area.width() // 12),
                                                      max(1, area.height() // 12),
                                                      Qt.IgnoreAspectRatio, Qt.FastTransformation)
                    painter.drawPixmap(area, small)
            else:
                self._draw_operation(painter, operation)
        painter.end()
        return result

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        area = self.image_rect()
        painter.drawPixmap(area, self.rendered(include_active=False), QRectF(self.base.rect()))
        if self.draft is not None and self.draft[0] != "mosaic":
            painter.save()
            painter.translate(area.topLeft())
            painter.scale(area.width() / self.base.width(), area.height() / self.base.height())
            self._draw_operation(painter, self.draft)
            painter.restore()

    def png_data(self):
        buffer = QByteArray()
        device = QBuffer(buffer)
        device.open(QIODevice.WriteOnly)
        self.rendered().save(device, "PNG")
        return bytes(buffer)


class CaptureOutline(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool |
                         Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.area = QRect()

    def begin(self, area: QRect, desktop: QRect):
        self.area = QRect(area)
        self.setGeometry(desktop)
        self.show()
        exclude_from_capture(self)

    def paintEvent(self, event):
        painter = QPainter(self)
        area = self.area.translated(-self.geometry().topLeft())
        painter.setPen(QPen(QColor("#111111"), 5))
        painter.drawRect(area.adjusted(-3, -3, 2, 2))
        painter.setPen(QPen(QColor("#ffffff"), 3))
        painter.drawRect(area.adjusted(-3, -3, 2, 2))


class FitPreview(QWidget):
    def __init__(self):
        super().__init__()
        self.picture = QPixmap()
        self.setMinimumSize(1, 1)

    def set_picture(self, data):
        self.picture = QPixmap.fromImage(QImage.fromData(data))
        self.update()

    def paintEvent(self, event):
        if self.picture.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        scale = min(self.width() / self.picture.width(), self.height() / self.picture.height())
        width, height = self.picture.width() * scale, self.picture.height() * scale
        painter.drawPixmap(QRectF((self.width() - width) / 2, (self.height() - height) / 2,
                                  width, height), self.picture, QRectF(self.picture.rect()))


class CapturePanel(QWidget):
    stop_requested = Signal()

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("实时拼接 · Scrollshot")
        self.setObjectName("capturePanel")
        self.setFixedWidth(310)
        self.setMinimumHeight(230)
        self.started = time.monotonic()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)
        title = QLabel("正在滚动截图")
        title.setObjectName("heading")
        layout.addWidget(title)
        self.detail = QLabel("1 帧  ·  等待画面")
        layout.addWidget(self.detail)
        self.dimensions = QLabel("原图尺寸  等待首帧")
        self.dimensions.setObjectName("hint")
        layout.addWidget(self.dimensions)
        self.status = QLabel("请在选区中手动滚动页面")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.image = FitPreview()
        layout.addWidget(self.image, 1)
        button = QPushButton("结束并预览")
        button.setObjectName("accent")
        button.setMinimumHeight(38)
        button.clicked.connect(self.stop_requested)
        layout.addWidget(button)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_elapsed)
        self.timer.start(1000)
        self.frames = 1
        self.height = 0

    def place(self, selection: QRect, desktop: QRect):
        margin = 12
        width = self.width()
        panel_height = min(680, max(300, desktop.height() - 48))
        self.resize(width, panel_height)
        if desktop.right() - selection.right() >= width + margin:
            x = selection.right() + margin
            y = max(desktop.top(), min(selection.top(), desktop.bottom() - panel_height + 1))
        elif selection.left() - desktop.left() >= width + margin:
            x = selection.left() - width - margin
            y = max(desktop.top(), min(selection.top(), desktop.bottom() - panel_height + 1))
        elif desktop.bottom() - selection.bottom() >= panel_height + margin:
            x = max(desktop.left(), min(selection.left(), desktop.right() - width + 1))
            y = selection.bottom() + margin
        elif selection.top() - desktop.top() >= panel_height + margin:
            x = max(desktop.left(), min(selection.left(), desktop.right() - width + 1))
            y = selection.top() - panel_height - margin
        else:
            # On a near-full-screen selection, Windows excludes the overlapping panel.
            x = desktop.right() - width + 1
            y = desktop.top()
            self.status.setText("选区周围空间不足；预览悬浮在页面上，截图会排除本面板")
        self.move(x, y)
        self.show()
        if not exclude_from_capture(self):
            self.status.setText("无法从截图中排除预览窗，请将预览拖到选区外")

    def update_elapsed(self):
        seconds = int(time.monotonic() - self.started)
        self.detail.setText(f"{self.frames} 帧  ·  {self.height} 像素  ·  {seconds} 秒")

    def update_preview(self, data: bytes, frames: int, height: int):
        self.frames, self.height = frames, height
        self.image.set_picture(data)
        self.dimensions.setText(f"原图尺寸  {self.image.picture.width()} × {height} px")
        self.update_elapsed()

    def closeEvent(self, event):
        event.ignore()
        self.stop_requested.emit()


class ImageViewer(QMainWindow):
    def __init__(self, data: bytes, reason: str):
        super().__init__()
        self.data = data
        self.pinned = False
        self.normal_geometry = None
        self.normal_view = None
        self.pinned_size = None
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setObjectName("imageViewer")
        self.setWindowTitle("长截图预览")
        self.resize(760, 750)
        self.setMinimumSize(600, 180)
        root = QWidget()
        root.setObjectName("viewer")
        root.setAttribute(Qt.WA_TranslucentBackground)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = QWidget()
        self.header.setObjectName("viewerHeader")
        row = QHBoxLayout(self.header)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(5)
        self.tool_buttons = {}
        for tool, label in (("rectangle", "矩形"), ("ellipse", "椭圆"), ("arrow", "箭头"),
                            ("pen", "画笔"), ("mosaic", "马赛克"), ("text", "文字")):
            button = icon_button(tool, label, lambda checked, mode=tool: self.select_tool(mode),
                                 checkable=True)
            self.tool_buttons[tool] = button
            row.addWidget(button)
        row.addSpacing(8)
        row.addWidget(icon_button("undo", "撤销上一处标注 (Ctrl+Z)", self.undo))
        row.addStretch()
        self.pin_button = icon_button("pin", "置顶预览", self.toggle_pin, checkable=True)
        self.pin_button.setCheckable(True)
        row.addWidget(self.pin_button)
        copy = icon_button("copy", "复制图片 (Ctrl+C)", self.copy_image)
        row.addWidget(copy)
        save = icon_button("save", "保存 PNG (Ctrl+S)", self.save_image)
        row.addWidget(save)
        row.addWidget(icon_button("close", "关闭预览", self.close))
        row.addWidget(icon_button("check", "完成并复制图片", self.finish, accent=True))
        layout.addWidget(self.header)
        self.dimensions = QLabel()
        self.dimensions.setObjectName("viewerDimensions")
        self.dimensions.setFixedHeight(26)
        layout.addWidget(self.dimensions)
        self.image = AnnotationCanvas(data)
        self.image.setAttribute(Qt.WA_TranslucentBackground)
        self.dimensions.setText(f"原图  {self.image.base.width()} × {self.image.base.height()} px  ·  完整预览")
        layout.addWidget(self.image, 1)
        self.setCentralWidget(root)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        header_height = self.header.sizeHint().height() + self.dimensions.sizeHint().height()
        image_height = round(self.width() * self.image.base.height() / self.image.base.width())
        self.resize(self.width(), min(screen.height() - 40, max(180, header_height + image_height)))
        self.reason = reason
        QShortcut(QKeySequence.Copy, self, activated=self.copy_image)
        QShortcut(QKeySequence.Save, self, activated=self.save_image)
        QShortcut(QKeySequence.Undo, self, activated=self.undo)
        QShortcut(QKeySequence(Qt.Key_Escape), self,
                  activated=lambda: self.toggle_pin(False) if self.pinned else self.close())

    def select_tool(self, tool):
        active = tool if self.tool_buttons[tool].isChecked() else None
        for name, button in self.tool_buttons.items():
            if name != tool:
                button.setChecked(False)
        self.image.set_tool(active)

    def undo(self):
        self.image.undo()

    def toggle_pin(self, checked):
        if checked == self.pinned:
            return
        self.image.editor.hide()
        self.pinned = checked
        self.pin_button.setChecked(checked)
        self.pin_button.setToolTip("取消置顶" if checked else "置顶预览")
        if checked:
            self.normal_geometry = self.geometry()
            self.normal_view = (self.image.zoom, QPointF(self.image.offset))
            image_area = self.image.image_rect()
            top_left = self.image.mapToGlobal(image_area.topLeft().toPoint())
            self.header.hide()
            self.dimensions.hide()
            self.setMinimumSize(1, 1)
            fitted = self.image.fit_rect()
            self.pinned_size = QSize(max(1, round(fitted.width())), max(1, round(fitted.height())))
            self.image.zoom = 1.0
            self.image.offset = QPointF()
            self.setGeometry(top_left.x(), top_left.y(), self.pinned_size.width(),
                             self.pinned_size.height())
        else:
            self.image.pin_button.hide()
            self.header.show()
            self.dimensions.show()
            self.setMinimumSize(600, 180)
            if self.normal_geometry is not None:
                self.setGeometry(self.normal_geometry)
            if self.normal_view is not None:
                self.image.zoom, self.image.offset = self.normal_view
        self.raise_()
        self.image.update()

    def resize_pinned(self, factor, anchor):
        if not self.pinned or self.pinned_size is None:
            return
        current = self.size()
        width = max(24, min(round(self.pinned_size.width() * 12), round(current.width() * factor)))
        height = max(24, min(round(self.pinned_size.height() * 12),
                             round(width * self.image.base.height() / self.image.base.width())))
        width = max(24, round(height * self.image.base.width() / self.image.base.height()))
        if QSize(width, height) == current:
            return
        relative = QPointF(anchor.x() / current.width(), anchor.y() / current.height())
        position = self.pos() + QPoint(round(anchor.x() - relative.x() * width),
                                      round(anchor.y() - relative.y() * height))
        self.setGeometry(position.x(), position.y(), width, height)
        self.image.update_pin_button(QPointF(relative.x() * width, relative.y() * height))

    def copy_image(self):
        QGuiApplication.clipboard().setPixmap(self.image.rendered())

    def finish(self):
        self.copy_image()
        self.close()

    def save_image(self):
        filename, _ = QFileDialog.getSaveFileName(self, "保存长截图", "长截图.png", "PNG 图片 (*.png)")
        if filename:
            try:
                Path(filename).write_bytes(self.image.png_data())
            except OSError as exc:
                QMessageBox.warning(self, "保存失败", str(exc))


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, app):
        super().__init__()
        self.app = app

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                if msg.wParam == HOTKEY_ID:
                    QTimer.singleShot(0, self.app.begin_selection)
                elif msg.wParam == ESC_ID:
                    self.app.stop_capture()
                return True, 0
        return False, 0


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("长截图 · Scrollshot")
        self.setMinimumSize(410, 280)
        self.resize(480, 320)
        self.selection = Selection()
        self.selection_toolbar = SelectionToolbar()
        self.selection.toolbar = self.selection_toolbar
        self.selection.selected.connect(self.capture)
        self.selection.still_selected.connect(self.capture_still)
        self.selection.area_changed.connect(
            lambda area: self.selection_toolbar.place(area, QGuiApplication.primaryScreen().virtualGeometry()))
        self.selection.cancelled.connect(self.cancel_selection)
        self.selection_toolbar.scroll_requested.connect(self.capture_selection)
        self.selection_toolbar.still_requested.connect(self.capture_still_selection)
        self.selection_toolbar.cancelled.connect(self.cancel_selection)
        self.outline = CaptureOutline()
        self.capture_panel = CapturePanel()
        self.capture_panel.stop_requested.connect(self.stop_capture)
        self.worker = None
        self.viewers = []
        self.hotkeys = False
        self.escape_registered = False
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(28, 24, 28, 24)
        column.setSpacing(15)
        eyebrow = QLabel("SCREEN CAPTURE  /  WINDOWS")
        eyebrow.setObjectName("eyebrow")
        column.addWidget(eyebrow)
        title = QLabel("长截图")
        title.setObjectName("title")
        column.addWidget(title)
        description = QLabel("框选屏幕区域，选区工具栏可截取单张或开始长截图。\n长截图时自行滚动页面，旁边实时显示拼接效果。")
        description.setObjectName("description")
        column.addWidget(description)
        column.addSpacing(8)
        self.start_button = QPushButton("选择滚动区域")
        self.start_button.setObjectName("accent")
        self.start_button.setMinimumHeight(44)
        self.start_button.clicked.connect(self.begin_selection)
        column.addWidget(self.start_button)
        hint = QLabel("快捷键  Ctrl + Alt + W     ·     12 秒无有效滚动则结束")
        hint.setObjectName("hint")
        column.addWidget(hint)
        column.addStretch()
        self.setCentralWidget(body)
        self.statusBar().showMessage("准备就绪")

    def register_hotkey(self):
        self.hotkeys = bool(ctypes.windll.user32.RegisterHotKey(None, HOTKEY_ID,
                                                                MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("W")))
        if not self.hotkeys:
            self.statusBar().showMessage("Ctrl + Alt + W 被其他程序占用，请使用窗口按钮")

    def begin_selection(self):
        if self.capture_panel.isVisible() or (self.worker is not None and self.worker.isRunning()):
            return
        self.hide()
        QTimer.singleShot(150, self.selection.begin)

    def cancel_selection(self):
        self.selection_toolbar.hide()
        self.selection.hide()
        self.show()
        self.activateWindow()

    def capture_selection(self):
        if self.selection.physical_selection is not None:
            self.capture(self.selection.physical_selection)

    def capture_still_selection(self, action="preview"):
        if self.selection.physical_selection is not None:
            self.capture_still(self.selection.physical_selection, action)

    def capture_still(self, rect: QRect, action="preview"):
        self.selection_toolbar.hide()
        self.selection.hide()
        def grab_still():
            try:
                with mss.mss() as screen:
                    shot = screen.grab(dict(left=rect.x(), top=rect.y(),
                                            width=rect.width(), height=rect.height()))
                image = Image.frombytes("RGB", shot.size, shot.rgb)
                buffer = io.BytesIO()
                image.save(buffer, "PNG")
                viewer = self.capture_done(buffer.getvalue(), "单张截图完成")
                if action in viewer.tool_buttons:
                    viewer.tool_buttons[action].click()
                elif action == "pin":
                    viewer.toggle_pin(True)
                elif action == "copy":
                    viewer.copy_image()
                elif action == "save":
                    viewer.save_image()
            except Exception as exc:
                self.capture_failed(str(exc))
        QTimer.singleShot(180, grab_still)

    def capture(self, rect: QRect):
        logical_rect = self.selection.selection.translated(self.selection.geometry().topLeft())
        desktop = QGuiApplication.primaryScreen().virtualGeometry()
        self.selection_toolbar.hide()
        self.selection.hide()
        self.outline.begin(logical_rect, desktop)
        self.capture_panel.started = time.monotonic()
        self.capture_panel.frames = 1
        self.capture_panel.height = 0
        self.capture_panel.image.picture = QPixmap()
        self.capture_panel.image.update()
        self.capture_panel.dimensions.setText("原图尺寸  等待首帧")
        self.capture_panel.status.setText("请在选区中手动滚动页面")
        self.capture_panel.place(logical_rect, desktop)
        self.statusBar().showMessage("请手动滚动页面…按 Esc 结束")
        self.worker = CaptureWorker(rect)
        self.worker.progress.connect(lambda count: self.statusBar().showMessage(f"已采集 {count} 帧 · Esc 提前结束"))
        self.worker.preview.connect(self.capture_panel.update_preview)
        self.worker.activity.connect(self.capture_panel.status.setText)
        self.worker.completed.connect(self.capture_done)
        self.worker.failed.connect(self.capture_failed)
        self.worker.finished.connect(self.capture_finished)
        self.escape_registered = bool(ctypes.windll.user32.RegisterHotKey(None, ESC_ID, MOD_NOREPEAT, VK_ESCAPE))
        QTimer.singleShot(200, self.worker.start)

    def stop_capture(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel.set()

    def capture_finished(self):
        if self.escape_registered:
            ctypes.windll.user32.UnregisterHotKey(None, ESC_ID)
            self.escape_registered = False

    def end_capture_ui(self):
        self.capture_panel.hide()
        self.outline.hide()

    def capture_done(self, data: bytes, reason: str):
        self.end_capture_ui()
        self.show()
        self.statusBar().showMessage(reason)
        viewer = ImageViewer(data, reason)
        self.viewers.append(viewer)
        viewer.show()
        viewer.activateWindow()
        return viewer

    def capture_failed(self, message: str):
        self.end_capture_ui()
        self.show()
        QMessageBox.warning(self, "截屏失败", message)

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel.set()
            self.worker.wait()
        if self.escape_registered:
            ctypes.windll.user32.UnregisterHotKey(None, ESC_ID)
        if self.hotkeys:
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
        self.end_capture_ui()
        super().closeEvent(event)
        QApplication.instance().quit()


STYLE = """
QMainWindow, QWidget { background: #171717; color: #f5f5f5; font-family: 'Microsoft YaHei UI'; font-size: 13px; }
QLabel#eyebrow { color: #c4c4c4; font-size: 11px; font-weight: 700; }
QLabel#title { font-size: 30px; font-weight: 700; }
QLabel#description { color: #dedede; }
QLabel#hint { color: #b0b0b0; font-size: 12px; }
QLabel#heading { font-size: 15px; font-weight: 700; }
QLabel#toolbarLabel { padding: 0 7px; font-weight: 600; color: #303030; background: transparent; }
QMainWindow#imageViewer, QWidget#viewer, AnnotationCanvas, QLabel#viewerDimensions { background: transparent; }
QLabel#viewerDimensions { color: #f5f5f5; padding: 8px 15px; }
QWidget#floatingToolbar, QWidget#viewerHeader { background: #f8f8f8; border: 1px solid #d0d0d0; border-radius: 7px; }
QWidget#capturePanel { background: #171717; }
QPushButton { background: #303030; color: #f8f8f8; border: 1px solid #555555; border-radius: 5px; padding: 7px 13px; min-height: 24px; }
QPushButton:hover { background: #424242; border-color: #aaaaaa; }
QPushButton:focus { border: 2px solid #f5f5f5; }
QPushButton#accent { background: #f5f5f5; color: #111111; border-color: #f5f5f5; font-weight: 700; }
QPushButton#accent:hover { background: #d8d8d8; }
QPushButton#toolAccent { background: #171717; color: #ffffff; border-color: #171717; }
QPushButton#toolAccent:hover { background: #404040; }
QPushButton#toolButton, QPushButton#toolAccent { border-radius: 5px; padding: 0; min-height: 0; }
QPushButton#toolButton { background: transparent; border-color: transparent; }
QPushButton#toolButton:hover { background: #e8e8e8; border-color: #d0d0d0; }
QPushButton#toolButton:checked { background: #d6d6d6; border-color: #888888; }
QScrollArea { background: #282828; border: 0; }
QScrollArea AnnotationCanvas, QScrollArea QLabel { background: #ffffff; color: #111111; }
QScrollBar:vertical { background: #282828; width: 11px; border: 0; }
QScrollBar::handle:vertical { background: #696969; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #282828; height: 11px; border: 0; }
QScrollBar::handle:horizontal { background: #696969; border-radius: 4px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QStatusBar { color: #dedede; }
"""


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(app_icon())
    app.setStyleSheet(STYLE)
    window = MainWindow()
    filter_ = HotkeyFilter(window)
    app.installNativeEventFilter(filter_)
    window.register_hotkey()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
