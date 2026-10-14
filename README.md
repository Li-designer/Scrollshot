# Scrollshot

Windows 区域截图与手动滚动长截图工具。框选想保留的内容，自己控制滚动节奏，在旁边查看实时拼接结果；完成后可标注、复制、保存或将图片置顶参考。

[下载 Windows 版](https://github.com/Li-designer/Scrollshot/releases/latest) · [查看源码](scrollshot.py) · [反馈问题](https://github.com/Li-designer/Scrollshot/issues)

## 功能

| 截图与拼接 | 预览与编辑 |
| --- | --- |
| 框选屏幕区域，截取单张 PNG | 整图预览；滚轮缩放，拖边调整大小 |
| 手动滚动，画面停稳后自动匹配并拼接 | 橙色矩形、椭圆、箭头、画笔和文字标注 |
| 选区边框与侧边实时预览、帧数及尺寸 | 马赛克、撤销、复制、保存 PNG |
| 40 帧或 30,000 像素上限提示 | 图钉精简模式、透明背景与窗口拖动 |

程序不会自动滚动页面，也不会自动上传截图。截图数据在本机处理。

## 下载与运行

1. 在 [Releases](https://github.com/Li-designer/Scrollshot/releases) 下载最新版的 `Scrollshot.exe`。
2. 在 Windows 10/11 上运行，无需单独安装 Python。首次运行时 Windows SmartScreen 可能提示未知发布者；此程序未做代码签名，请只从本仓库的 Release 下载并自行核对文件哈希。
3. 点击“选择滚动区域”，或按 `Ctrl + Alt + W` 开始框选。

### 单张截图

拖出选区后，按 `Enter` 或点击工具栏的相机/对勾。也可直接点标注、图钉、复制或保存图标：程序先抓取选区，再打开预览并执行对应动作。`Esc` 或右键取消选择。

### 滚动长截图

1. 框选实际会滚动的内容区域，尽量避开固定导航栏、悬浮按钮和滚动条。
2. 按 `S` 或点选区工具栏的滚动图标。选区边框与实时拼接预览会留在屏幕上。
3. **自己滚动页面**。每次移动不要超过选区高度的大约 80%，停顿片刻让程序找到前后画面的重叠部分。
4. 按 `Esc` 或点击“结束并预览”。连续 12 秒没有可拼接内容时会自动结束；达到 40 帧或 30,000 像素时停止并提示上限。

### 预览操作

| 操作 | 方法 |
| --- | --- |
| 缩放、移动 | 图片上滚轮缩放；拖动图片边缘调整；左键拖图片移动预览窗，中键拖动平移画布 |
| 标注 | 工具栏选择矩形、椭圆、箭头、画笔、马赛克或文字；`Ctrl + Z` 撤销 |
| 文字 | 点击图片创建输入框，点框外完成；之后可拖动文字框移动，拉右侧/下侧调整字号，不支持重新编辑已有文字 |
| 复制、保存 | `Ctrl + C` 复制，`Ctrl + S` 保存 PNG；使用原始分辨率，不把编辑虚线框写进图片 |
| 图钉 | 只显示图片；鼠标移入后点击图钉或按 `Esc` 恢复工具栏；右键图片关闭该预览 |

## 从源码运行

需要 Windows、Python 3.11 或更新版本。建议先创建虚拟环境：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scrollshot.py
```

运行测试：

```powershell
.\.venv\Scripts\python.exe tests\test_stitch.py
```

自行构建 Windows EXE（构建产物在 `dist/Scrollshot.exe`）：

```powershell
.\.venv\Scripts\python.exe -m pip install "pyinstaller>=6,<7"
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm packaging\Scrollshot.spec
```

## 已知限制

- 重叠匹配依赖页面内容。重复纹理、持续动画、固定浮层、缩放变化或一次滚动太远都可能导致拼接失败；遇到问题请缩小滚动步幅或重新框选。
- 某些受保护窗口禁止屏幕抓取；多显示器和不同 DPI 的配置建议先用单张截图核对选区。
- 长图完整适配预览窗口时字会显得很小，但复制和保存仍使用原图像素。
- 该项目目前主要在 Windows 上使用与测试；尚无 macOS/Linux 版本。

## 许可证与第三方组件

项目源码按 [MIT License](LICENSE) 发布，版权归仓库所有者。依赖及构建组件详见 [第三方组件说明](THIRD_PARTY_NOTICES.md)；它们各自的许可证不因本项目的 MIT 许可证而改变。尤其是分发包含 PySide6/Qt 的单文件 EXE 时，应核对适用的 LGPL/GPL 或商业许可条款、保留版权及许可文本，并满足相应的再链接等义务。项目 EXE 未签名。

欢迎通过 [Issues](https://github.com/Li-designer/Scrollshot/issues) 报告可复现的问题，注明 Windows 版本、显示器缩放比例、截图区域与操作步骤；提交问题前请遮挡截图中的私人信息。
