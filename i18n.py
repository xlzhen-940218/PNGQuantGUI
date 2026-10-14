# -*- coding: utf-8 -*-
"""多语言支持（简体中文 / English）。

- 首次启动按系统 UI 语言自动选择
- 用户手动切换后保存到配置文件（exe 旁，不可写时落到 %APPDATA%\\PNGCompressor）
"""
import os
import sys
import json
import locale

LANGS = ("zh", "en")
DEFAULT_LANG = "zh"

STRINGS = {
    "zh": {
        # 标题栏 / 顶部
        "app_title": "PNG 压缩工具",
        "subtitle": "基于 pngquant · 批量 PNG 视觉近无损压缩",

        # 设置卡片
        "settings_title": "压缩设置",
        "quality_preset": "质量预设",
        "preset_high": "高画质 80-95",
        "preset_balanced": "均衡 65-85",
        "preset_max": "高压缩 45-70",
        "quality_range_hint": "质量区间（数值越高画质越好、体积越大）",
        "min_quality": "最低质量  {v}",
        "max_quality": "最高质量  {v}",
        "output_mode": "输出方式",
        "mode_over": "覆盖原文件",
        "mode_sub": "输出到 compressed 子文件夹",
        "mode_custom": "输出到自定义文件夹",
        "browse": "选择文件夹…",
        "backup_option": "覆盖前备份原图到「{folder}」",
        "fallback_option": "质量不达标时自动放宽（保底 35）",
        "strip_option": "去除元数据（EXIF），体积略小",
        "tip": "提示：压缩后反而变大的文件会自动保留原样",

        # 文件列表
        "add_files": "添加文件",
        "add_folder": "添加文件夹",
        "clear_list": "清空列表",
        "col_file": "文件",
        "col_orig": "原始大小",
        "col_new": "压缩后",
        "col_saved": "减少",
        "empty_hint": "拖放 PNG 文件 / 文件夹到这里，或点击「添加文件」",

        # 底部
        "open_output": "打开输出目录",
        "start": "开始压缩",
        "cancel": "取消",
        "cancelling_btn": "正在取消…",
        "ready": "准备就绪 — 拖入 PNG 文件或文件夹，或点击右侧按钮添加",
        "total_summary": "{done}/{total} 张 · {before} → {after} · 总节省 {pct}%",

        # 状态消息
        "msg_cancelling": "正在取消，等待当前文件结束…",
        "msg_need_custom_dir": "请先选择自定义输出文件夹",
        "msg_empty_list": "列表为空 — 请先添加 PNG 文件",
        "msg_starting": "开始压缩…",
        "msg_list_cleared": "列表已清空",
        "msg_added_n": "已添加 {n} 个文件",
        "msg_added_folder_n": "已从文件夹添加 {n} 个 PNG",
        "msg_dropped_n": "拖入并添加了 {n} 个 PNG",
        "msg_compressing": "({i}/{total}) 正在压缩 {name}",
        "msg_failed_detail": "{name} 失败：{err}",
        "msg_skipped": "{name} 压缩收益不足，已保留原样",
        "msg_done_fallback": "{name} 已完成（自动放宽质量）",
        "msg_done_one": "{name} 压缩完成",
        "msg_finished": "结束 — 压缩 {a} 张，保留原样 {b} 张，失败 {c} 张",
        "msg_finished_cancel": "，取消 {d} 张",
        "err_exit_code": "pngquant 退出码 {rc}",

        # 文件对话框
        "dlg_choose_output": "选择压缩后文件的输出文件夹",
        "dlg_choose_png": "选择 PNG 文件",
        "dlg_choose_folder": "选择包含 PNG 的文件夹（含子文件夹）",
        "png_filetype": "PNG 图像",

        # 磁盘目录名
        "backup_folder": "原图备份",
    },
    "en": {
        # Title bar / header
        "app_title": "PNG Compressor",
        "subtitle": "Powered by pngquant · Batch near-lossless PNG compression",

        # Settings card
        "settings_title": "Settings",
        "quality_preset": "Quality preset",
        "preset_high": "High 80-95",
        "preset_balanced": "Balanced 65-85",
        "preset_max": "Smallest 45-70",
        "quality_range_hint": "Quality range (higher = better quality, larger file)",
        "min_quality": "Min quality  {v}",
        "max_quality": "Max quality  {v}",
        "output_mode": "Output",
        "mode_over": "Overwrite originals",
        "mode_sub": "Into 'compressed' subfolder",
        "mode_custom": "To a custom folder",
        "browse": "Choose folder…",
        "backup_option": "Back up originals to '{folder}' first",
        "fallback_option": "Auto-relax quality if unreachable (floor 35)",
        "strip_option": "Strip metadata (EXIF), slightly smaller",
        "tip": "Tip: files that grow after compression are kept unchanged",

        # File list
        "add_files": "Add files",
        "add_folder": "Add folder",
        "clear_list": "Clear",
        "col_file": "File",
        "col_orig": "Original",
        "col_new": "Compressed",
        "col_saved": "Saved",
        "empty_hint": "Drop PNG files / folders here, or click 'Add files'",

        # Footer
        "open_output": "Open output",
        "start": "Compress",
        "cancel": "Cancel",
        "cancelling_btn": "Cancelling…",
        "ready": "Ready — drop in PNG files or folders, or use the buttons",
        "total_summary": "{done}/{total} files · {before} → {after} · saved {pct}%",

        # Status messages
        "msg_cancelling": "Cancelling, waiting for the current file…",
        "msg_need_custom_dir": "Please choose a custom output folder first",
        "msg_empty_list": "The list is empty — add PNG files first",
        "msg_starting": "Starting compression…",
        "msg_list_cleared": "List cleared",
        "msg_added_n": "{n} file(s) added",
        "msg_added_folder_n": "{n} PNG file(s) added from folder",
        "msg_dropped_n": "{n} PNG file(s) dropped in",
        "msg_compressing": "({i}/{total}) Compressing {name}",
        "msg_failed_detail": "{name} failed: {err}",
        "msg_skipped": "{name}: no size gain, original kept",
        "msg_done_fallback": "{name} done (quality auto-relaxed)",
        "msg_done_one": "{name} compressed",
        "msg_finished": "Finished — {a} compressed, {b} kept unchanged, {c} failed",
        "msg_finished_cancel": ", {d} cancelled",
        "err_exit_code": "pngquant exited with code {rc}",

        # File dialogs
        "dlg_choose_output": "Choose the output folder for compressed files",
        "dlg_choose_png": "Choose PNG files",
        "dlg_choose_folder": "Choose a folder containing PNGs (subfolders included)",
        "png_filetype": "PNG image",

        # On-disk folder name
        "backup_folder": "Original Backup",
    },
}

CONFIG_NAME = "pngquant_gui_config.json"

_lang = DEFAULT_LANG


# ---------------------------------------------------------------- 翻译入口
def t(key, **kwargs):
    table = STRINGS.get(_lang, STRINGS[DEFAULT_LANG])
    text = table.get(key)
    if text is None:
        text = STRINGS[DEFAULT_LANG].get(key, key)
    return text.format(**kwargs) if kwargs else text


def get_lang():
    return _lang


# ---------------------------------------------------------------- 配置存取
def _config_dir():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    if os.path.isdir(base) and os.access(base, os.W_OK):
        return base
    appdata = os.environ.get("APPDATA")
    if appdata:
        d = os.path.join(appdata, "PNGCompressor")
        os.makedirs(d, exist_ok=True)
        return d
    return base


def _config_path():
    return os.path.join(_config_dir(), CONFIG_NAME)


def _load_config():
    try:
        with open(_config_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_config(data):
    try:
        with open(_config_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


# ---------------------------------------------------------------- 语言探测
def detect_lang():
    """优先读 Windows 用户 UI 语言；失败再退回 Python locale。"""
    try:
        import ctypes
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        if (lang_id & 0x03FF) == 0x04:  # LANG_CHINESE
            return "zh"
    except Exception:
        pass
    try:
        loc = locale.getdefaultlocale()[0] or ""
        if loc.lower().startswith("zh"):
            return "zh"
    except Exception:
        pass
    return "en"


def init():
    """程序启动时调用：配置优先，其次系统语言。"""
    global _lang
    saved = _load_config().get("lang")
    _lang = saved if saved in LANGS else detect_lang()
    return _lang


def set_lang(lang, persist=True):
    global _lang
    if lang not in LANGS:
        return
    _lang = lang
    if persist:
        data = _load_config()
        data["lang"] = lang
        _save_config(data)
