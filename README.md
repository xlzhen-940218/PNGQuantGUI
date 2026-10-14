[English](README.en.md) | 简体中文

# PNG 压缩工具（PNGQuantGUI）

基于 [pngquant](https://pngquant.org) 的 Windows 桌面批量 PNG 压缩工具，深色精美界面、中英双语、拖放操作，可打包为单文件 exe。

pngquant 通过调色板量化实现**视觉近无损**压缩（最多 256 色），照片类图片通常可再减小 50%–70%，日常观感与原图几乎无差。

## 界面预览

英文界面、批量压缩进行中：

![PNG Compressor 界面截图](docs/screenshot.png)

## 功能

- **添加文件**：拖入文件或整个文件夹（自动递归查找 `.png`），也可按钮选择；列表支持单张移除、一键清空
- **质量控制**：高画质 80–95 / 均衡 65–85 / 高压缩 45–70 三档预设，另提供最低/最高质量双滑块自定义
- **输出方式**：
  - 输出到源目录下的 `compressed` 子文件夹（默认，不动原图）
  - 覆盖原文件（可选自动备份到「原图备份 / Original Backup」目录，已备份过不会重复备份）
  - 输出到自定义文件夹
- **安全策略**：压缩后反而变大自动保留原样；质量不达标自动放宽一档（可关闭）；可选去除 EXIF 元数据
- **过程交互**：实时进度条、逐张状态（✓ 完成 / ≈ 保留原样 / ✕ 失败）、压缩前后大小与节省百分比、随时取消、完成后一键打开输出目录
- **双语界面**：中文 / English，右上角一键切换、即时生效；首次启动按系统语言自动选择，选择结果持久化
- pngquant 以子进程方式内嵌调用，后台线程执行，界面不卡顿，且全程不弹出任何命令行黑框

## 运行环境

- Windows 10 / 11
- Python 3.9+（仅开发与打包时需要，成品 exe 无需 Python）

## 从源码运行

```powershell
pip install customtkinter tkinterdnd2 pillow
python app.py
```

需确保 `assets/` 目录下存在以下文件：

| 文件 | 用途 |
|---|---|
| `icon.ico` | 窗口与 exe 图标 |
| `icon256.png` | 界面标题栏图标 |
| `pngquant.exe` | 压缩引擎（[官网下载](https://pngquant.org) 或 `npm i pngquant-bin`） |

## 打包为单文件 exe

```powershell
pip install pyinstaller
pyinstaller "PNG压缩工具.spec"
```

产物位于 `dist\PNG压缩工具.exe`（约 28 MB，双击即用）。也可直接运行 `build.bat`。

## 项目结构

```
PNGQuantGUI/
├── app.py              # GUI 主程序（CustomTkinter）
├── i18n.py             # 中英文案、系统语言探测、语言配置持久化
├── PNG压缩工具.spec     # PyInstaller 打包配置
├── build.bat           # 一键打包脚本
├── .gitignore
├── assets/
│   ├── icon.ico
│   ├── icon256.png
│   ├── icon_main256.png
│   └── pngquant.exe
└── docs/
    └── screenshot.png  # README 展示截图
```

语言选择保存在 exe 同目录的 `pngquant_gui_config.json`（该目录不可写时落到 `%APPDATA%\PNGCompressor`）。

## 许可说明

- 本仓库代码可自由使用
- [pngquant](https://pngquant.org) 基于 **GPLv3** 发布，随附的 `pngquant.exe` 遵循其许可；商业分发请留意该许可约束
