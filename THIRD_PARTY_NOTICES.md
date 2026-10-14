# Third-party notices / 第三方组件说明

Scrollshot 源码采用仓库中的 MIT `LICENSE`。以下依赖仍受各自许可证约束。`v0.1.0` 的 Windows EXE 在 Python 3.11 环境中构建；下表列出主要直接依赖及构建工具的版本。具体许可证文本、附带组件和分发义务请以各上游发行包及其许可证文件为准。

| 组件 | 构建版本 | 许可证与上游 |
| --- | --- | --- |
| PySide6 Essentials / Qt | 6.12.0 | [LGPL-3.0-only / GPL-2.0-only / GPL-3.0-only / 商业许可](https://doc.qt.io/qtforpython-6/licenses.html)；[源码](https://code.qt.io/cgit/pyside/pyside-setup.git/) |
| shiboken6 | 6.12.0 | [LGPL-3.0-only / GPL-2.0-only / GPL-3.0-only / 商业许可](https://doc.qt.io/qtforpython-6/licenses.html)；[源码](https://code.qt.io/cgit/pyside/pyside-setup.git/) |
| mss | 10.2.0 | [MIT](https://github.com/BoboTiG/python-mss/blob/main/LICENSE.txt) |
| Pillow | 12.3.0 | [HPND / MIT-CMU](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| NumPy | 2.4.6 | [BSD-3-Clause 及捆绑组件许可](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| opencv-python-headless / OpenCV | 5.0.0.93 | [Apache-2.0 及捆绑组件许可](https://github.com/opencv/opencv/blob/4.x/LICENSE) |
| PyInstaller（构建工具） | 6.22.3 | [GPL-2.0-or-later，带构建产物例外](https://pyinstaller.org/en/stable/license.html) |

Python 解释器和这些包的传递依赖也可能包含在单文件 EXE 中，并受其各自许可证约束。特别是 Qt/PySide6 的 LGPL 路径可能要求保留许可与版权声明，并允许用户替换、重新链接或调试被覆盖的库；单文件封装并不会自动豁免这些条件。需要严格合规或商用分发时，请逐项审查最终构建包，必要时改用便于替换共享库的分发方式或取得商业许可。
