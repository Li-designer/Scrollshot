import sys
import io
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image
from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QScrollArea

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scrollshot
from scrollshot import CaptureWorker, overlap_shift


def test_overlap():
    rng = np.random.default_rng(13)
    document = Image.fromarray(rng.integers(0, 256, (1000, 360, 3), dtype=np.uint8))
    previous = document.crop((0, 0, 360, 400))
    current = document.crop((0, 190, 360, 590))
    assert abs(overlap_shift(previous, current) - 190) <= 2
    assert overlap_shift(previous, previous) is None


def test_manual_capture(height_limit=None):
    rng = np.random.default_rng(27)
    document = Image.fromarray(rng.integers(0, 256, (850, 240, 3), dtype=np.uint8))
    frames = [document.crop((0, y, 240, y + 300)) for y in (0, 0, 120, 120, 120, 240, 240, 240)]

    class FakeScreen:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def grab(self, area):
            assert area == dict(left=70, top=90, width=240, height=300)
            image = frames.pop(0) if frames else document.crop((0, 240, 240, 540))
            return type("Shot", (), {"size": image.size, "rgb": image.tobytes()})()

    worker = CaptureWorker(QRect(70, 90, 240, 300))
    output = []
    worker.completed.connect(lambda data, reason: output.append((data, reason)))
    ticks = iter(range(100))
    with patch.object(scrollshot.mss, "mss", FakeScreen), \
         patch.object(worker.cancel, "wait", return_value=False), \
         patch.object(scrollshot, "MAX_HEIGHT", height_limit or scrollshot.MAX_HEIGHT), \
         patch.object(scrollshot.time, "monotonic", side_effect=lambda: next(ticks)):
        worker.run()
    result = Image.open(io.BytesIO(output[0][0]))
    expected_height = height_limit or 540
    assert result.size == (240, expected_height)
    assert np.array_equal(np.asarray(result), np.asarray(document.crop((0, 0, 240, expected_height))))
    assert ("不能继续滚动" if height_limit else "不可滚动") in output[0][1]


def test_live_preview():
    app = QApplication.instance() or QApplication([])
    image = Image.new("RGB", (240, 300), "white")
    data = scrollshot.preview_frame([image, image.crop((0, 200, 240, 300))], 240)
    panel = scrollshot.CapturePanel()
    panel.update_preview(data, 2, 400)
    assert panel.image.picture.width() == 240
    assert panel.image.picture.height() == 400
    assert "400 像素" in panel.detail.text()
    assert "240 × 400" in panel.dimensions.text()
    assert not panel.findChildren(QScrollArea)
    panel.timer.stop()
    app.processEvents()


def test_annotation_toolbar():
    app = QApplication.instance() or QApplication([])
    original = Image.new("RGB", (240, 300), "white")
    buffer = io.BytesIO()
    original.save(buffer, "PNG")
    viewer = scrollshot.ImageViewer(buffer.getvalue(), "测试")
    viewer.resize(760, 750)
    viewer.show()
    app.processEvents()
    area = viewer.image.image_rect()
    assert area.width() <= viewer.image.width() + 0.01
    assert area.height() <= viewer.image.height() + 0.01
    mapped = viewer.image.image_point(QPointF(area.left() + area.width() / 2,
                                               area.top() + area.height() / 2))
    assert abs(mapped.x() - 120) <= 1 and abs(mapped.y() - 150) <= 1
    assert not viewer.findChildren(QScrollArea)
    assert "240 × 300" in viewer.dimensions.text()
    assert viewer.testAttribute(Qt.WA_TranslucentBackground)
    assert viewer.windowFlags() & Qt.WindowStaysOnTopHint
    assert viewer.header.window() is viewer.image.window() is viewer
    center = viewer.image.image_rect().center()
    start_global = QPointF(viewer.image.mapToGlobal(center.toPoint()))
    original_position = viewer.pos()
    original_offset = QPointF(viewer.image.offset)
    viewer.image.mousePressEvent(QMouseEvent(QMouseEvent.MouseButtonPress, center, center, start_global,
                                            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    moved_global = start_global + QPointF(45, 30)
    viewer.image.mouseMoveEvent(QMouseEvent(QMouseEvent.MouseMove, center, center, moved_global,
                                           Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    viewer.image.mouseReleaseEvent(QMouseEvent(QMouseEvent.MouseButtonRelease, center, center, moved_global,
                                              Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
    assert viewer.pos() == original_position + QPoint(45, 30)
    assert viewer.image.offset == original_offset
    assert viewer.windowFlags() & Qt.WindowStaysOnTopHint
    viewer.image.mousePressEvent(QMouseEvent(QMouseEvent.MouseButtonPress, center, center, moved_global,
                                            Qt.MiddleButton, Qt.MiddleButton, Qt.NoModifier))
    viewer.image.mouseMoveEvent(QMouseEvent(QMouseEvent.MouseMove, center + QPointF(15, 10),
                                           center + QPointF(15, 10), moved_global + QPointF(15, 10),
                                           Qt.NoButton, Qt.MiddleButton, Qt.NoModifier))
    viewer.image.mouseReleaseEvent(QMouseEvent(QMouseEvent.MouseButtonRelease, center, center, moved_global,
                                              Qt.MiddleButton, Qt.NoButton, Qt.NoModifier))
    assert viewer.pos() == original_position + QPoint(45, 30)
    assert viewer.image.offset == original_offset + QPointF(15, 10)
    viewer.image.offset = QPointF()
    anchor = area.center()
    wheel = QWheelEvent(anchor, viewer.image.mapToGlobal(anchor.toPoint()), QPoint(0, 0),
                        QPoint(0, 120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    viewer.image.wheelEvent(wheel)
    assert viewer.image.zoom > 1
    viewer.image.set_zoom(1)
    edge = viewer.image.image_rect()
    start = QPointF(edge.right() - 2, edge.center().y())
    end = start + QPointF(30, 0)
    viewer.image.mousePressEvent(QMouseEvent(QMouseEvent.MouseButtonPress, start, start,
                                            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    viewer.image.mouseMoveEvent(QMouseEvent(QMouseEvent.MouseMove, end, end,
                                           Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    viewer.image.mouseReleaseEvent(QMouseEvent(QMouseEvent.MouseButtonRelease, end, end,
                                              Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
    assert viewer.image.zoom > 1
    viewer.image.set_zoom(1.5, area.center())
    assert viewer.image.image_rect().width() > area.width()
    viewer.image.set_zoom(1)
    viewer.toggle_pin(True)
    app.processEvents()
    assert viewer.pinned and not viewer.header.isVisible() and not viewer.dimensions.isVisible()
    assert not viewer.image.pin_button.isVisible()
    pinned_size = viewer.size()
    viewer.resize_pinned(1.16, QPointF(pinned_size.width() / 2, pinned_size.height() / 2))
    app.processEvents()
    assert viewer.width() > pinned_size.width() and viewer.height() > pinned_size.height()
    assert abs(viewer.width() / viewer.height() - 240 / 300) < .01
    viewer.image.update_pin_button(viewer.image.image_rect().center())
    assert viewer.image.pin_button.isVisible()
    viewer.image.pin_button.click()
    app.processEvents()
    assert not viewer.pinned and viewer.header.isVisible() and viewer.dimensions.isVisible()
    assert viewer.windowFlags() & Qt.WindowStaysOnTopHint
    assert viewer.size().width() == 760
    assert len(viewer.tool_buttons) == 6
    viewer.tool_buttons["rectangle"].click()
    assert viewer.image.tool == "rectangle"
    viewer.image.operations.append(("rectangle", QPoint(10, 10), QPoint(60, 50)))
    assert QColor(viewer.image.rendered().toImage().pixel(10, 25)).green() < 150
    assert Image.open(io.BytesIO(viewer.image.png_data())).size == (240, 300)
    viewer.undo()
    assert QColor(viewer.image.rendered().toImage().pixel(10, 25)) == QColor("white")
    viewer.tool_buttons["pen"].click()
    assert viewer.image.tool == "pen"
    assert not viewer.tool_buttons["rectangle"].isChecked()
    viewer.image.operations.append(("pen", QPoint(5, 5), [QPoint(5, 5), QPoint(12, 12)]))
    viewer.image.operations.append(("arrow", QPoint(30, 40), QPoint(80, 90)))
    viewer.image.operations.append(("ellipse", QPoint(20, 100), QPoint(80, 150)))
    viewer.image.operations.append(("mosaic", QPoint(10, 160), QPoint(60, 210)))
    viewer.image.operations.append(scrollshot.TextAnnotation(scrollshot.QRectF(20, 230, 100, 50), "Test", 18))
    assert Image.open(io.BytesIO(viewer.image.png_data())).size == (240, 300)
    viewer.close()
    app.processEvents()


def test_still_toolbar_actions():
    app = QApplication.instance() or QApplication([])
    toolbar = scrollshot.SelectionToolbar()
    requested = []
    toolbar.still_requested.connect(requested.append)
    buttons = toolbar.findChildren(scrollshot.QPushButton)
    for index, action in ((0, "preview"), (2, "rectangle"), (8, "pin"),
                          (9, "copy"), (10, "save"), (12, "preview")):
        buttons[index].click()
        assert requested[-1] == action
    assert toolbar.width() >= toolbar.layout().sizeHint().width()
    desktop = QRect(0, 0, 640, 720)
    toolbar.place(QRect(8, 580, 160, 110), desktop)
    assert desktop.contains(toolbar.geometry())
    toolbar.hide()

    class FakeScreen:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def grab(self, area):
            assert area == dict(left=40, top=50, width=240, height=300)
            image = Image.new("RGB", (240, 300), "white")
            return type("Shot", (), {"size": image.size, "rgb": image.tobytes()})()

    window = scrollshot.MainWindow()
    rect = QRect(40, 50, 240, 300)
    with patch.object(scrollshot.mss, "mss", FakeScreen), \
         patch.object(scrollshot.QTimer, "singleShot", side_effect=lambda delay, callback: callback()), \
         patch.object(scrollshot.ImageViewer, "save_image", autospec=True) as save, \
         patch.object(scrollshot.ImageViewer, "copy_image", autospec=True) as copy:
        for action in ("rectangle", "pin", "copy", "save"):
            window.capture_still(rect, action)
            viewer = window.viewers[-1]
            if action == "rectangle":
                assert viewer.image.tool == "rectangle"
            elif action == "pin":
                assert viewer.pinned and not viewer.header.isVisible()
            elif action == "copy":
                copy.assert_called_once_with(viewer)
            elif action == "save":
                save.assert_called_once_with(viewer)
            viewer.close()
    window.close()


def test_preview_top_alignment_and_pinned_right_click():
    app = QApplication.instance() or QApplication([])
    buffer = io.BytesIO()
    Image.new("RGB", (900, 180), "white").save(buffer, "PNG")
    viewer = scrollshot.ImageViewer(buffer.getvalue(), "测试")
    viewer.show()
    app.processEvents()
    assert abs(viewer.image.image_rect().top()) < .01
    assert abs(viewer.image.image_rect().height() - viewer.image.height()) < 20
    assert viewer.height() < 350
    point = viewer.image.image_rect().center()
    right_click = QMouseEvent(QMouseEvent.MouseButtonPress, point, point,
                              Qt.RightButton, Qt.RightButton, Qt.NoModifier)
    app.sendEvent(viewer.image, right_click)
    assert viewer.isVisible()
    viewer.toggle_pin(True)
    app.processEvents()
    point = viewer.image.image_rect().center()
    right_click = QMouseEvent(QMouseEvent.MouseButtonPress, point, point,
                              Qt.RightButton, Qt.RightButton, Qt.NoModifier)
    app.sendEvent(viewer.image, right_click)
    app.processEvents()
    assert not viewer.isVisible()


def test_orange_annotations_and_text_editor():
    app = QApplication.instance() or QApplication([])
    buffer = io.BytesIO()
    Image.new("RGB", (600, 500), "white").save(buffer, "PNG")
    viewer = scrollshot.ImageViewer(buffer.getvalue(), "测试")
    viewer.show()
    app.processEvents()
    canvas = viewer.image
    canvas.operations.extend([
        ("rectangle", QPoint(20, 20), QPoint(100, 90)),
        ("ellipse", QPoint(120, 20), QPoint(200, 90)),
        ("arrow", QPoint(30, 140), QPoint(230, 220)),
        ("pen", QPoint(20, 250), [QPoint(20, 250), QPoint(100, 250)]),
    ])
    rendered = canvas.rendered().toImage()
    orange = scrollshot.ANNOTATION_COLOR
    for x, y in ((20, 50), (160, 20), (220, 216), (60, 250)):
        color = QColor(rendered.pixel(x, y))
        assert abs(color.red() - orange.red()) < 5 and abs(color.blue() - orange.blue()) < 5

    viewer.tool_buttons["text"].click()
    image_area = canvas.image_rect()
    def at(x, y):
        return QPointF(image_area.left() + x * image_area.width() / 600,
                       image_area.top() + y * image_area.height() / 500)

    def event(kind, position, global_position=None, button=Qt.LeftButton, buttons=Qt.LeftButton):
        return QMouseEvent(kind, position, position, global_position or position,
                           button, buttons, Qt.NoModifier)

    canvas.mousePressEvent(event(QMouseEvent.MouseButtonPress, at(260, 270)))
    annotation = canvas.operations[-1]
    assert isinstance(annotation, scrollshot.TextAnnotation)
    assert canvas.editor.isVisible()
    canvas.editor.setPlainText("Orange text")
    assert annotation.text == "Orange text"
    canvas.editor.finish_edit()
    assert canvas.editor.isReadOnly() and not canvas.editor.isVisible()
    canvas.mousePressEvent(event(QMouseEvent.MouseButtonPress, at(annotation.rect.x() + 12,
                                                                  annotation.rect.y() + 15)))
    assert canvas.editor.isVisible() and canvas.editor.toPlainText() == "Orange text"
    assert canvas.editor.isReadOnly()
    editor = canvas.editor
    before = scrollshot.QRectF(annotation.rect)
    viewport = editor.viewport()
    def send_to_viewport(kind, position, global_position, button, buttons):
        local = QPointF(viewport.mapFrom(editor, position.toPoint()))
        app.sendEvent(viewport, event(kind, local, global_position, button, buttons))

    interior = QPointF(viewport.geometry().center())
    send_to_viewport(QMouseEvent.MouseButtonPress, interior, QPointF(100, 100),
                     Qt.LeftButton, Qt.LeftButton)
    send_to_viewport(QMouseEvent.MouseMove, interior, QPointF(130, 120),
                     Qt.NoButton, Qt.LeftButton)
    send_to_viewport(QMouseEvent.MouseButtonRelease, interior, QPointF(130, 120),
                     Qt.LeftButton, Qt.NoButton)
    assert annotation.rect.x() > before.x() and annotation.rect.y() > before.y()
    assert annotation.text == "Orange text" and editor.isReadOnly()
    old_size = annotation.font_size
    corner = QPointF(editor.width() - 3, editor.height() - 3)
    send_to_viewport(QMouseEvent.MouseButtonPress, corner, QPointF(200, 200),
                     Qt.LeftButton, Qt.LeftButton)
    send_to_viewport(QMouseEvent.MouseMove, corner, QPointF(260, 250),
                     Qt.NoButton, Qt.LeftButton)
    send_to_viewport(QMouseEvent.MouseButtonRelease, corner, QPointF(260, 250),
                     Qt.LeftButton, Qt.NoButton)
    assert annotation.font_size > old_size and annotation.rect.width() > before.width()
    old_size = annotation.font_size
    right_edge = QPointF(viewport.geometry().right() - 3, viewport.geometry().center().y())
    send_to_viewport(QMouseEvent.MouseButtonPress, right_edge, QPointF(300, 300),
                     Qt.LeftButton, Qt.LeftButton)
    send_to_viewport(QMouseEvent.MouseMove, right_edge, QPointF(335, 300),
                     Qt.NoButton, Qt.LeftButton)
    send_to_viewport(QMouseEvent.MouseButtonRelease, right_edge, QPointF(335, 300),
                     Qt.LeftButton, Qt.NoButton)
    assert annotation.font_size > old_size
    assert editor.isVisible()
    exported = Image.open(io.BytesIO(canvas.png_data())).convert("RGB")
    assert exported.size == (600, 500)
    assert exported.getpixel((round(annotation.rect.x()), round(annotation.rect.y()))) == (255, 255, 255)
    assert any(exported.getpixel((x, y))[0] > 200 and exported.getpixel((x, y))[2] < 100
               for y in range(round(annotation.rect.top()) + 5, round(annotation.rect.bottom()) - 5)
               for x in range(round(annotation.rect.left()) + 5, round(annotation.rect.right()) - 5))
    viewer.toggle_pin(True)
    app.processEvents()
    assert not editor.isVisible()
    viewer.toggle_pin(False)
    viewer.close()
    app.processEvents()


if __name__ == "__main__":
    test_overlap()
    test_manual_capture()
    test_manual_capture(370)
    test_live_preview()
    test_annotation_toolbar()
    test_still_toolbar_actions()
    test_preview_top_alignment_and_pinned_right_click()
    test_orange_annotations_and_text_editor()
    print("stitch test passed")
