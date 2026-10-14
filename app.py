# -*- coding: utf-8 -*-
"""PNG 压缩工具 —— 基于 pngquant 的可视化批量压缩（视觉近无损）。中英双语。"""
import os
import sys
import zlib
import queue
import shutil
import threading
import subprocess
from tkinter import filedialog, StringVar, BooleanVar

import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES
from PIL import Image

import i18n
from i18n import t

# 启动时确定语言（配置文件优先，其次系统语言）
i18n.init()

# 全局使用微软雅黑（CustomTkinter 默认字体是 Roboto，中文显示不佳）
FONT_FAMILY = "Microsoft YaHei UI"
ctk.ThemeManager.theme["CTkFont"]["family"] = FONT_FAMILY

# ---------------------------------------------------------------- 常量
ACCENT = "#F28020"        # 与图标橙色呼应
ACCENT_HOVER = "#D96A10"
SAVE_GREEN = "#2BB673"
SKIP_AMBER = "#E8A33D"
ERR_RED = "#E5564E"
WAIT_GRAY = "#8A93A6"

# 质量预设：内部键 + 区间（显示名走 i18n）
PRESETS = [
    ("high", 80, 95),
    ("balanced", 65, 85),
    ("max", 45, 70),
]

# 调用 pngquant 子进程时隐藏控制台黑框（GUI 程序默认会为控制台子进程弹窗）
SUBPROCESS_KW = {}
if os.name == "nt":
    _si = subprocess.STARTUPINFO()
    _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _si.wShowWindow = subprocess.SW_HIDE
    SUBPROCESS_KW = {"creationflags": subprocess.CREATE_NO_WINDOW,
                     "startupinfo": _si}


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(base, name)
    if not os.path.exists(p):  # 开发环境下资源位于 assets/
        p = os.path.join(base, "assets", name)
    return p


def human(n):
    if n is None:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024


def pct_str(before, after):
    if not before or after is None:
        return "-"
    return f"-{max(0.0, (1 - after / before) * 100):.1f}%"


def pngquant_path():
    return resource_path("pngquant.exe")


def pngquant_version():
    try:
        out = subprocess.run([pngquant_path(), "--version"],
                             capture_output=True, text=True, timeout=10,
                             stdin=subprocess.DEVNULL, **SUBPROCESS_KW)
        return out.stdout.strip() or out.stderr.strip()
    except Exception:
        return ""


def backup_dir_for(src_dir):
    """覆盖模式下的备份目录：随语言命名，同时识别另一种语言的旧目录。"""
    primary = os.path.join(src_dir, t("backup_folder"))
    if os.path.isdir(primary):
        return primary
    for alt in ("原图备份", "Original Backup"):
        p = os.path.join(src_dir, alt)
        if os.path.isdir(p):
            return p
    return primary


# ---------------------------------------------------------------- 主窗口
class App(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)

        self.title(t("app_title"))
        self.geometry("1060x720")
        self.minsize(940, 620)
        self.iconbitmap(resource_path("icon.ico"))
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.records = []          # {path,name,orig,new,status,row}
        self.ui_q = queue.Queue()
        self.worker = None
        self.cancel_event = threading.Event()
        self.proc = None
        self.proc_lock = threading.Lock()
        self.running = False
        self.cancelling = False
        self.output_dirs = set()
        self.preset_key = "high"
        self.min_q, self.max_q = 80, 95
        self._ver = pngquant_version()
        self._last_status = None   # (key, params)，切换语言时可重渲染

        self._build_ui()
        self._poll_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------ UI 构建
    def _build_ui(self):
        self.configure(fg_color="#16181F")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ---------- 顶部标题栏 ----------
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 8))
        header.grid_columnconfigure(1, weight=1)

        icon_img = ctk.CTkImage(
            light_image=Image.open(resource_path("icon256.png")),
            dark_image=Image.open(resource_path("icon256.png")),
            size=(42, 42))
        ctk.CTkLabel(header, image=icon_img, text="").grid(row=0, column=0,
                                                           rowspan=2, padx=(0, 12))
        self.title_lbl = ctk.CTkLabel(
            header, text=t("app_title"),
            font=ctk.CTkFont(size=22, weight="bold"))
        self.title_lbl.grid(row=0, column=1, sticky="w")
        self.subtitle_lbl = ctk.CTkLabel(
            header, text=self._subtitle_text(),
            text_color="#9AA4B8", font=ctk.CTkFont(size=12))
        self.subtitle_lbl.grid(row=1, column=1, sticky="w")

        # 语言切换
        self.lang_var = StringVar(value="中文" if i18n.get_lang() == "zh" else "EN")
        self.lang_seg = ctk.CTkSegmentedButton(
            header, values=["中文", "EN"], variable=self.lang_var,
            command=self._on_lang, selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER, height=30, width=104,
            font=ctk.CTkFont(size=12))
        self.lang_seg.grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 0))

        # ---------- 主体：左设置 + 右列表 ----------
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=22, pady=8)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._build_settings(body)
        self._build_list(body)

        # ---------- 底部进度区 ----------
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=22, pady=(4, 16))
        footer.grid_columnconfigure(0, weight=1)

        self.progress = ctk.CTkProgressBar(footer, height=10, corner_radius=5,
                                           progress_color=ACCENT)
        self.progress.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        self.progress.set(0)

        self.status_var = StringVar()
        ctk.CTkLabel(footer, textvariable=self.status_var, text_color="#9AA4B8",
                     font=ctk.CTkFont(size=12), anchor="w")\
            .grid(row=1, column=0, sticky="w")
        self._set_status("ready")

        self.total_var = StringVar(value="")
        ctk.CTkLabel(footer, textvariable=self.total_var, text_color=SAVE_GREEN,
                     font=ctk.CTkFont(size=12, weight="bold"))\
            .grid(row=1, column=1, padx=12)

        self.open_btn = ctk.CTkButton(footer, text=t("open_output"), width=120,
                                      fg_color="transparent", border_width=1,
                                      border_color="#3A4152", text_color="#C9D0DE",
                                      hover_color="#232733", state="disabled",
                                      command=self._open_output)
        self.open_btn.grid(row=1, column=2, padx=(0, 10))

        self.run_btn = ctk.CTkButton(footer, text=t("start"), width=150, height=38,
                                     font=ctk.CTkFont(size=15, weight="bold"),
                                     fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                     command=self._toggle_run)
        self.run_btn.grid(row=1, column=3)

    def _subtitle_text(self):
        return t("subtitle") + ((" · " + self._ver) if self._ver else "")

    def _build_settings(self, parent):
        card = ctk.CTkFrame(parent, width=272, corner_radius=14,
                            fg_color="#1E222C", border_width=1, border_color="#2A2F3B")
        card.grid(row=0, column=0, sticky="ns", padx=(0, 14))
        card.grid_propagate(False)

        self.settings_title_lbl = ctk.CTkLabel(
            card, text=t("settings_title"),
            font=ctk.CTkFont(size=15, weight="bold"))
        self.settings_title_lbl.grid(row=0, column=0, sticky="w", padx=18, pady=(16, 10))

        # 质量预设
        self.preset_title_lbl = ctk.CTkLabel(
            card, text=t("quality_preset"), text_color="#9AA4B8",
            font=ctk.CTkFont(size=12))
        self.preset_title_lbl.grid(row=1, column=0, sticky="w", padx=18)
        self.preset_var = StringVar()
        self.preset_seg = ctk.CTkSegmentedButton(
            card, values=self._preset_labels(), variable=self.preset_var,
            command=self._on_preset, selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER, height=30,
            font=ctk.CTkFont(size=12))
        self.preset_var.set(t("preset_high"))
        self.preset_seg.grid(row=2, column=0, sticky="ew", padx=18, pady=(4, 12))

        # 自定义质量区间
        self.range_hint_lbl = ctk.CTkLabel(
            card, text=t("quality_range_hint"), text_color="#9AA4B8",
            font=ctk.CTkFont(size=12), wraplength=230, justify="left")
        self.range_hint_lbl.grid(row=3, column=0, sticky="w", padx=18)

        self.min_label = ctk.CTkLabel(card, text=t("min_quality", v=self.min_q),
                                      font=ctk.CTkFont(size=12))
        self.min_label.grid(row=4, column=0, sticky="w", padx=18, pady=(10, 0))
        self.min_slider = ctk.CTkSlider(card, from_=0, to=100, number_of_steps=100,
                                        command=self._on_min_slider,
                                        progress_color=ACCENT, button_color=ACCENT,
                                        button_hover_color=ACCENT_HOVER)
        self.min_slider.set(self.min_q)
        self.min_slider.grid(row=5, column=0, sticky="ew", padx=18, pady=(2, 8))

        self.max_label = ctk.CTkLabel(card, text=t("max_quality", v=self.max_q),
                                      font=ctk.CTkFont(size=12))
        self.max_label.grid(row=6, column=0, sticky="w", padx=18)
        self.max_slider = ctk.CTkSlider(card, from_=0, to=100, number_of_steps=100,
                                        command=self._on_max_slider,
                                        progress_color=ACCENT, button_color=ACCENT,
                                        button_hover_color=ACCENT_HOVER)
        self.max_slider.set(self.max_q)
        self.max_slider.grid(row=7, column=0, sticky="ew", padx=18, pady=(2, 14))

        # 输出方式
        self.out_title_lbl = ctk.CTkLabel(
            card, text=t("output_mode"), text_color="#9AA4B8",
            font=ctk.CTkFont(size=12))
        self.out_title_lbl.grid(row=8, column=0, sticky="w", padx=18)
        self.out_mode = StringVar(value="sub")
        self.mode_radios = {}
        modes = [("mode_over", "over"), ("mode_sub", "sub"),
                 ("mode_custom", "custom")]
        for i, (text_key, val) in enumerate(modes):
            rb = ctk.CTkRadioButton(card, text=t(text_key), variable=self.out_mode,
                                    value=val, command=self._on_mode,
                                    font=ctk.CTkFont(size=12),
                                    fg_color=ACCENT, border_color="#5A6275")
            rb.grid(row=9 + i, column=0, sticky="w", padx=18, pady=(6, 0))
            self.mode_radios[val] = rb

        self.custom_dir = StringVar(value="")
        self.browse_btn = ctk.CTkButton(card, text=t("browse"), height=28,
                                        fg_color="transparent", border_width=1,
                                        border_color="#3A4152", text_color="#C9D0DE",
                                        hover_color="#232733",
                                        command=self._browse_outdir)
        self.browse_btn.grid(row=12, column=0, sticky="ew", padx=18, pady=(8, 4))
        self.browse_btn.grid_remove()

        # 选项
        self.backup_var = BooleanVar(value=True)
        self.backup_cb = ctk.CTkCheckBox(
            card, text=t("backup_option", folder=t("backup_folder")),
            variable=self.backup_var, font=ctk.CTkFont(size=11),
            fg_color=ACCENT, border_color="#5A6275")
        self.backup_cb.grid(row=13, column=0, sticky="w", padx=18, pady=(6, 0))
        self.backup_cb.grid_remove()

        self.fallback_var = BooleanVar(value=True)
        self.fallback_cb = ctk.CTkCheckBox(
            card, text=t("fallback_option"), variable=self.fallback_var,
            font=ctk.CTkFont(size=11), fg_color=ACCENT, border_color="#5A6275")
        self.fallback_cb.grid(row=14, column=0, sticky="w", padx=18, pady=(14, 0))

        self.strip_var = BooleanVar(value=False)
        self.strip_cb = ctk.CTkCheckBox(
            card, text=t("strip_option"), variable=self.strip_var,
            font=ctk.CTkFont(size=11), fg_color=ACCENT, border_color="#5A6275")
        self.strip_cb.grid(row=15, column=0, sticky="w", padx=18, pady=(10, 0))

        self.tip_lbl = ctk.CTkLabel(card, text=t("tip"), text_color="#6B7488",
                                    font=ctk.CTkFont(size=11),
                                    wraplength=230, justify="left")
        self.tip_lbl.grid(row=16, column=0, sticky="w", padx=18, pady=16)

        card.grid_rowconfigure(17, weight=1)

    def _build_list(self, parent):
        right = ctk.CTkFrame(parent, corner_radius=14, fg_color="#1E222C",
                             border_width=1, border_color="#2A2F3B")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(2, weight=1)
        right.grid_columnconfigure(0, weight=1)

        toolbar = ctk.CTkFrame(right, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        toolbar.grid_columnconfigure(4, weight=1)
        self.add_files_btn = ctk.CTkButton(
            toolbar, text=t("add_files"), width=88, height=30,
            command=self._add_files, fg_color="#2C3242",
            hover_color="#373E52", font=ctk.CTkFont(size=12))
        self.add_files_btn.grid(row=0, column=0, padx=(0, 8))
        self.add_folder_btn = ctk.CTkButton(
            toolbar, text=t("add_folder"), width=92, height=30,
            command=self._add_folder, fg_color="#2C3242",
            hover_color="#373E52", font=ctk.CTkFont(size=12))
        self.add_folder_btn.grid(row=0, column=1, padx=(0, 8))
        self.clear_btn = ctk.CTkButton(
            toolbar, text=t("clear_list"), width=88, height=30,
            command=self.clear_records, fg_color="transparent",
            border_width=1, border_color="#3A4152", text_color="#C9D0DE",
            hover_color="#2A2F3B", font=ctk.CTkFont(size=12))
        self.clear_btn.grid(row=0, column=2)

        # 拖放区 + 列表
        self.list_frame = ctk.CTkScrollableFrame(right, corner_radius=10,
                                                 fg_color="#181B23",
                                                 border_width=2,
                                                 border_color="#333949")
        self.list_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 10))
        self.list_frame.grid_columnconfigure(1, weight=1)
        for w, c in [(34, 0), (320, 1), (96, 2), (96, 3), (76, 4), (34, 5)]:
            self.list_frame.grid_columnconfigure(c, minsize=w)

        self.empty_var = StringVar(value=t("empty_hint"))
        self.empty_label = ctk.CTkLabel(self.list_frame, textvariable=self.empty_var,
                                        text_color="#5B6478",
                                        font=ctk.CTkFont(size=14))
        self.empty_label.grid(row=1, column=0, columnspan=6, pady=80)

        # 整窗 + 列表接受拖放
        for widget in (self, self.list_frame):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)

    # ------------------------------------------------------------ 多语言
    def _preset_labels(self):
        return [t(f"preset_{key}") for key, _, _ in PRESETS]

    def _preset_map(self):
        return {t(f"preset_{key}"): key for key, _, _ in PRESETS}

    def _on_lang(self, value):
        lang = "zh" if value == "中文" else "en"
        self.lang_var.set("中文" if lang == "zh" else "EN")
        i18n.set_lang(lang)
        self._retranslate()

    def _render_status(self, key, params):
        text = t(key, **params)
        if key == "msg_finished" and params.get("d"):
            text += t("msg_finished_cancel", d=params["d"])
        return text

    def _set_status(self, key, **params):
        self._last_status = (key, params)
        self.status_var.set(self._render_status(key, params))

    def _retranslate(self):
        # 窗口 / 顶部
        self.title(t("app_title"))
        self.title_lbl.configure(text=t("app_title"))
        self.subtitle_lbl.configure(text=self._subtitle_text())

        # 设置卡片
        self.settings_title_lbl.configure(text=t("settings_title"))
        self.preset_title_lbl.configure(text=t("quality_preset"))
        self.preset_seg.configure(values=self._preset_labels())
        self.preset_var.set(t(f"preset_{self.preset_key}"))
        self.range_hint_lbl.configure(text=t("quality_range_hint"))
        self.min_label.configure(text=t("min_quality", v=self.min_q))
        self.max_label.configure(text=t("max_quality", v=self.max_q))
        self.out_title_lbl.configure(text=t("output_mode"))
        for val, rb in self.mode_radios.items():
            rb.configure(text=t({"over": "mode_over", "sub": "mode_sub",
                                 "custom": "mode_custom"}[val]))
        self.browse_btn.configure(
            text=os.path.basename(self.custom_dir.get()) or t("browse"))
        self.backup_cb.configure(text=t("backup_option", folder=t("backup_folder")))
        self.fallback_cb.configure(text=t("fallback_option"))
        self.strip_cb.configure(text=t("strip_option"))
        self.tip_lbl.configure(text=t("tip"))

        # 列表工具栏 + 空提示 + 表头
        self.add_files_btn.configure(text=t("add_files"))
        self.add_folder_btn.configure(text=t("add_folder"))
        self.clear_btn.configure(text=t("clear_list"))
        self.empty_var.set(t("empty_hint"))
        self._refresh_rows()

        # 底部
        self.open_btn.configure(text=t("open_output"))
        if self.cancelling:
            self.run_btn.configure(text=t("cancelling_btn"))
        elif self.running:
            self.run_btn.configure(text=t("cancel"))
        else:
            self.run_btn.configure(text=t("start"))
        if self._last_status:
            key, params = self._last_status
            self.status_var.set(self._render_status(key, params))

    # ------------------------------------------------------------ 设置交互
    def _on_preset(self, value):
        key = self._preset_map().get(value, self.preset_key)
        self.preset_key = key
        lo, hi = next((lo, hi) for k, lo, hi in PRESETS if k == key)
        self.min_q, self.max_q = lo, hi
        self.min_slider.set(lo)
        self.max_slider.set(hi)
        self.min_label.configure(text=t("min_quality", v=lo))
        self.max_label.configure(text=t("max_quality", v=hi))

    def _on_min_slider(self, v):
        v = int(round(v))
        if v > self.max_q - 5:
            v = self.max_q - 5
            self.min_slider.set(v)
        self.min_q = v
        self.min_label.configure(text=t("min_quality", v=v))

    def _on_max_slider(self, v):
        v = int(round(v))
        if v < self.min_q + 5:
            v = self.min_q + 5
            self.max_slider.set(v)
        self.max_q = v
        self.max_label.configure(text=t("max_quality", v=v))

    def _on_mode(self):
        if self.out_mode.get() == "custom":
            self.browse_btn.grid()
        else:
            self.browse_btn.grid_remove()
        if self.out_mode.get() == "over":
            self.backup_cb.grid()
        else:
            self.backup_cb.grid_remove()

    def _browse_outdir(self):
        d = filedialog.askdirectory(title=t("dlg_choose_output"))
        if d:
            self.custom_dir.set(d)
            self.browse_btn.configure(text=os.path.basename(d) or d)

    # ------------------------------------------------------------ 文件管理
    def _add_paths(self, paths):
        added = 0
        existing = {r["path"] for r in self.records}
        todo = []
        for p in paths:
            p = os.path.abspath(p)
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in files:
                        if f.lower().endswith(".png"):
                            todo.append(os.path.join(root, f))
            elif os.path.isfile(p) and p.lower().endswith(".png"):
                todo.append(p)
        for p in todo:
            if p in existing:
                continue
            existing.add(p)
            self.records.append({
                "path": p, "name": os.path.basename(p),
                "orig": os.path.getsize(p), "new": None,
                "status": "wait", "widgets": None,
            })
            added += 1
        if added:
            self._refresh_rows()
        return added

    def _add_files(self):
        fs = filedialog.askopenfilenames(
            title=t("dlg_choose_png"),
            filetypes=[(t("png_filetype"), "*.png")])
        if fs:
            n = self._add_paths(list(fs))
            self._set_status("msg_added_n", n=n)

    def _add_folder(self):
        d = filedialog.askdirectory(title=t("dlg_choose_folder"))
        if d:
            n = self._add_paths([d])
            self._set_status("msg_added_folder_n", n=n)

    def _on_drop(self, event):
        if self.running:
            return
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = [event.data.strip("{}")]
        n = self._add_paths(list(paths))
        if n:
            self._set_status("msg_dropped_n", n=n)

    def clear_records(self):
        if self.running:
            return
        self.records.clear()
        self._refresh_rows()
        self.progress.set(0)
        self.total_var.set("")
        self._set_status("msg_list_cleared")
        self.open_btn.configure(state="disabled")
        self.output_dirs.clear()

    def _remove_record(self, rec):
        if self.running:
            return
        self.records.remove(rec)
        self._refresh_rows()

    STATUS_STYLE = {
        "wait": ("●", WAIT_GRAY),
        "work": ("●", ACCENT),
        "done": ("✓", SAVE_GREEN),
        "fallback": ("✓", SAVE_GREEN),
        "skip": ("≈", SKIP_AMBER),
        "error": ("✕", ERR_RED),
        "cancel": ("■", WAIT_GRAY),
    }

    def _refresh_rows(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

        if not self.records:
            self.empty_label = ctk.CTkLabel(
                self.list_frame, textvariable=self.empty_var, text_color="#5B6478",
                font=ctk.CTkFont(size=14))
            self.empty_label.grid(row=1, column=0, columnspan=6, pady=80)
            self._update_total()
            return

        ctk.CTkLabel(self.list_frame, text=t("col_file"), text_color="#6B7488",
                     font=ctk.CTkFont(size=11, weight="bold"), anchor="w")\
            .grid(row=0, column=1, sticky="w", padx=6, pady=(2, 6))
        for col, key in ((2, "col_orig"), (3, "col_new"), (4, "col_saved")):
            ctk.CTkLabel(self.list_frame, text=t(key), text_color="#6B7488",
                         font=ctk.CTkFont(size=11, weight="bold"), anchor="center")\
                .grid(row=0, column=col, pady=(2, 6))

        for i, rec in enumerate(self.records, start=1):
            row = ctk.CTkFrame(self.list_frame, fg_color="transparent")
            row.grid(row=i, column=0, columnspan=6, sticky="ew", pady=1)
            row.grid_columnconfigure(1, weight=1)

            dot = ctk.CTkLabel(row, text="●", text_color=WAIT_GRAY, width=30,
                               font=ctk.CTkFont(size=13))
            dot.grid(row=0, column=0)
            name_lbl = ctk.CTkLabel(row, text=rec["name"], anchor="w",
                                    font=ctk.CTkFont(size=12))
            name_lbl.grid(row=0, column=1, sticky="w", padx=6)
            orig_lbl = ctk.CTkLabel(row, text=human(rec["orig"]), width=90,
                                    font=ctk.CTkFont(size=12))
            orig_lbl.grid(row=0, column=2)
            new_lbl = ctk.CTkLabel(row, text=human(rec["new"]), width=90,
                                   font=ctk.CTkFont(size=12))
            new_lbl.grid(row=0, column=3)
            pct_lbl = ctk.CTkLabel(row, text=pct_str(rec["orig"], rec["new"]),
                                   width=70, font=ctk.CTkFont(size=12))
            pct_lbl.grid(row=0, column=4)
            ctk.CTkButton(row, text="✕", width=26, height=24,
                          fg_color="transparent", hover_color="#3A2128",
                          text_color="#8A93A6", font=ctk.CTkFont(size=12),
                          command=lambda r=rec: self._remove_record(r))\
                .grid(row=0, column=5, padx=(4, 2))

            rec["widgets"] = {
                "row": row, "dot": dot, "new": new_lbl, "pct": pct_lbl,
                "name": name_lbl, "orig": orig_lbl,
            }
            self._paint_record(rec)

        self._update_total()

    def _paint_record(self, rec):
        w = rec["widgets"]
        if not w:
            return
        glyph, color = self.STATUS_STYLE[rec["status"]]
        w["dot"].configure(text=glyph, text_color=color)
        w["new"].configure(text=human(rec["new"]),
                           text_color=SAVE_GREEN if rec["new"] else "#D8DDE8")
        p = pct_str(rec["orig"], rec["new"])
        w["pct"].configure(text=p, text_color=SAVE_GREEN if rec["new"] else "#8A93A6")
        if rec["status"] == "error":
            w["name"].configure(text_color=ERR_RED)
        elif rec["status"] in ("done", "fallback"):
            w["name"].configure(text_color="#D8DDE8")

    def _update_total(self):
        total = len(self.records)
        done = sum(1 for r in self.records if r["status"] in
                   ("done", "fallback", "skip", "error"))
        before = sum(r["orig"] for r in self.records)
        after = sum((r["new"] if r["new"] is not None else r["orig"])
                    for r in self.records)
        if not total:
            self.total_var.set("")
        elif before:
            self.total_var.set(t("total_summary",
                                 done=done, total=total,
                                 before=human(before), after=human(after),
                                 pct=f"{max(0.0, (1 - after / before) * 100):.1f}"))

    # ------------------------------------------------------------ 压缩执行
    def _toggle_run(self):
        if self.running:
            self.cancel_event.set()
            with self.proc_lock:
                if self.proc and self.proc.poll() is None:
                    self.proc.terminate()
            self.cancelling = True
            self.run_btn.configure(text=t("cancelling_btn"), state="disabled")
            self._set_status("msg_cancelling")
            return
        self._start()

    def _start(self):
        if self.out_mode.get() == "custom" and not self.custom_dir.get():
            self._set_status("msg_need_custom_dir")
            return
        pending = [r for r in self.records if r["status"] in
                   ("wait", "error", "cancel")]
        if not pending:
            self._set_status("msg_empty_list")
            return

        self.running = True
        self.cancelling = False
        self.cancel_event.clear()
        self.output_dirs.clear()
        self.open_btn.configure(state="disabled")
        self.run_btn.configure(text=t("cancel"), state="normal",
                               fg_color="#B23A36", hover_color="#93302D")
        self._set_status("msg_starting")

        cfg = {
            "min_q": self.min_q, "max_q": self.max_q,
            "mode": self.out_mode.get(),
            "custom_dir": self.custom_dir.get(),
            "backup": self.backup_var.get(),
            "fallback": self.fallback_var.get(),
            "strip": self.strip_var.get(),
        }
        self.worker = threading.Thread(target=self._run_worker,
                                       args=(pending, cfg), daemon=True)
        self.worker.start()

    def _run_worker(self, pending, cfg):
        q = self.ui_q
        total = len(pending)
        for i, rec in enumerate(pending, 1):
            if self.cancel_event.is_set():
                q.put(("status", rec, "cancel", None, None))
                continue
            q.put(("status", rec, "work", None,
                   ("msg_compressing", {"i": i, "total": total, "name": rec["name"]})))
            try:
                new_size, status, out_dir = self._compress_one(rec, cfg)
                q.put(("result", rec, status, new_size, out_dir))
            except Exception as e:
                q.put(("result", rec, "error", None, str(e)))
        q.put(("all_done", None, None, None, None))

    def _compress_one(self, rec, cfg):
        src = rec["path"]
        src_dir = os.path.dirname(src)
        name = rec["name"]

        if cfg["mode"] == "over":
            out_dir = src_dir
            if cfg["backup"]:
                bak_dir = backup_dir_for(src_dir)
                os.makedirs(bak_dir, exist_ok=True)
                bak = os.path.join(bak_dir, name)
                if not os.path.exists(bak):
                    shutil.copy2(src, bak)
        elif cfg["mode"] == "sub":
            out_dir = os.path.join(src_dir, "compressed")
            os.makedirs(out_dir, exist_ok=True)
        else:
            out_dir = cfg["custom_dir"]
            os.makedirs(out_dir, exist_ok=True)

        final = os.path.join(out_dir, name)
        # 自定义目录下不同源文件同名：加来源目录后缀，避免互相覆盖
        if cfg["mode"] == "custom" and os.path.exists(final) and \
                os.path.getsize(final) != rec["orig"]:
            base, ext = os.path.splitext(name)
            final = os.path.join(out_dir, f"{base}_{zlib.crc32(src_dir.encode('utf-8')) % 100000:05d}{ext}")

        tmp = final + ".pqtmp.png"
        if os.path.exists(tmp):
            os.remove(tmp)

        cmd = [pngquant_path(), "--force",
               f"--quality={cfg['min_q']}-{cfg['max_q']}",
               "--skip-if-larger"]
        if cfg["strip"]:
            cmd.append("--strip")
        cmd += ["--output", tmp, src]

        status = "done"
        rc, err = self._run_proc(cmd)
        if rc == 99 and cfg["fallback"]:
            lo = max(35, cfg["min_q"] - 20)
            hi = max(lo + 5, cfg["max_q"] - 20)
            cmd[2] = f"--quality={lo}-{hi}"
            rc, err = self._run_proc(cmd)
            status = "fallback"

        if rc == 98 or not os.path.exists(tmp):
            if os.path.exists(tmp):
                os.remove(tmp)
            if cfg["mode"] == "over":
                return None, "skip", out_dir
            # 非覆盖模式：直接复制原文件，保证输出齐全
            shutil.copy2(src, final)
            return rec["orig"], "skip", out_dir

        if rc != 0:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise RuntimeError(err.strip() or t("err_exit_code", rc=rc))

        new_size = os.path.getsize(tmp)
        if new_size >= rec["orig"]:
            os.remove(tmp)
            if cfg["mode"] == "over":
                return None, "skip", out_dir
            shutil.copy2(src, final)
            return rec["orig"], "skip", out_dir

        os.replace(tmp, final)
        return new_size, status, out_dir

    def _run_proc(self, cmd):
        with self.proc_lock:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL, **SUBPROCESS_KW)
        _, err = self.proc.communicate()
        rc = self.proc.returncode
        with self.proc_lock:
            self.proc = None
        return rc, err.decode("utf-8", "ignore")

    # ------------------------------------------------------------ UI 队列
    def _poll_queue(self):
        try:
            while True:
                kind, rec, a, b, c = self.ui_q.get_nowait()
                if kind == "status":
                    if rec:
                        rec["status"] = a
                        self._paint_record(rec)
                    if c:
                        msg_key, msg_params = c
                        self._set_status(msg_key, **msg_params)
                elif kind == "result":
                    if a == "error":
                        rec["status"] = "error"
                        self._paint_record(rec)
                        self._set_status("msg_failed_detail",
                                         name=rec["name"], err=c)
                    else:
                        rec["status"] = a
                        rec["new"] = b
                        self._paint_record(rec)
                        if c:
                            self.output_dirs.add(c)
                        if a == "skip":
                            self._set_status("msg_skipped", name=rec["name"])
                        elif a == "fallback":
                            self._set_status("msg_done_fallback", name=rec["name"])
                        else:
                            self._set_status("msg_done_one", name=rec["name"])
                    self.progress.set(sum(
                        1 for r in self.records
                        if r["status"] in ("done", "fallback", "skip", "error", "cancel"))
                        / max(1, len(self.records)))
                    self._update_total()
                elif kind == "all_done":
                    self._finish()
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    def _finish(self):
        self.running = False
        self.cancelling = False
        self.run_btn.configure(text=t("start"), state="normal",
                               fg_color=ACCENT, hover_color=ACCENT_HOVER)
        n_done = sum(1 for r in self.records if r["status"] in ("done", "fallback"))
        n_skip = sum(1 for r in self.records if r["status"] == "skip")
        n_err = sum(1 for r in self.records if r["status"] == "error")
        n_cancel = sum(1 for r in self.records if r["status"] == "cancel")
        self._set_status("msg_finished", a=n_done, b=n_skip, c=n_err,
                         d=n_cancel)
        if self.output_dirs:
            self.open_btn.configure(state="normal")
        self.progress.set(1 if not n_cancel else self.progress.get())

    def _open_output(self):
        if not self.output_dirs:
            return
        d = next(iter(self.output_dirs))
        if os.path.isdir(d):
            os.startfile(d)

    def _on_close(self):
        if self.running:
            self.cancel_event.set()
            with self.proc_lock:
                if self.proc and self.proc.poll() is None:
                    self.proc.terminate()
        self.destroy()


if __name__ == "__main__":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "com.trae.pngquant.gui")
    except Exception:
        pass
    App().mainloop()
