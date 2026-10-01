import tkinter as tk
from tkinter import filedialog, messagebox, StringVar, Text, Toplevel, BooleanVar, ttk
import pandas as pd
import numpy as np
import os
import sys
import io

from processing import SpeedProcessor
from plotting import PlotManager
from utils import find_columns, calculate_acceleration, calculate_jitter

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BG         = "#f4f6f9"
PANEL_BG   = "#ffffff"
FG         = "#2c3e50"
FG_MUTED   = "#7f8c8d"
ACCENT     = "#2c5f8d"
ACCENT_HOV = "#3a7bb8"
SUCCESS    = "#27ae60"
WARNING    = "#e67e22"
DANGER     = "#e74c3c"
BORDER     = "#dbe3ec"

FONT_BASE  = ("Segoe UI", 10)
FONT_BOLD  = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 14, "bold")
FONT_SMALL = ("Segoe UI", 8)
FONT_MONO  = ("Consolas", 9)

# ---- Физические константы ----
TRAIN_MASS_T       = 7337.0
INERTIAL_MASS_K    = 0.07
INERTIAL_MASS_T    = TRAIN_MASS_T * INERTIAL_MASS_K
TOTAL_MASS_KG      = (TRAIN_MASS_T + INERTIAL_MASS_T) * 1000.0

FREAL_TO_N = 1000.0

# ---- Константы для силы сопротивления движению ----
AXLE_LOAD_T     = 24.78716216   # B10, вкладка «Данные», т
RESISTANCE_COEF = 1.25          # N1, вкладка «Режим»

K_MIN_DENOM = 1e-4

FREAL_RAW_NAME = 'Freal'
TRACTION_NAME  = 'Сила тяги'

CORRIDOR_SPEED_NAME   = 'Коридор скорости'
CORRIDOR_ACCEL_1_NAME = 'Коридор ускорения (1-е сглаж.)'
CORRIDOR_ACCEL_2_NAME = 'Коридор ускорения (2-е сглаж.)'

COL_ACCEL_RAW        = 'Ускорение'
COL_ACCEL_1          = 'Ускорение после 1-го сглаживания'
COL_ACCEL_2          = 'Ускорение после 2-го сглаживания'
COL_V_SMOOTH         = 'Сглаженная скорость'
COL_V_MS             = 'Скорость в м/с'
COL_JITTER           = 'Дребезг ускорения'
COL_SLOPE_FORCE      = 'Сила от уклона'
COL_SLOPE_ACCEL      = 'Ускорение от уклона'
COL_TRACTION_ACCEL   = 'Ускорение от силы тяги'
COL_TRACTION_PCT     = 'Процент силы тяги'
COL_RESISTANCE_FORCE = 'Сила сопротивления движению'
COL_RESISTANCE_ACCEL = 'Ускорение от силы сопротивления'
COL_SUM_ACCEL        = 'Сумма ускорений'
COL_K                = 'Коэффициент K'
COL_K2               = 'Коэффициент K2'
COL_ACCEL_K          = 'Ускорение с учётом K'

LOW_SPEED    = 'Нижняя граница скорости'
HIGH_SPEED   = 'Верхняя граница скорости'
LOW_ACCEL_1  = 'Нижняя граница ускорения (1-е)'
HIGH_ACCEL_1 = 'Верхняя граница ускорения (1-е)'
LOW_ACCEL_2  = 'Нижняя граница ускорения (2-е)'
HIGH_ACCEL_2 = 'Верхняя граница ускорения (2-е)'


# ==================================================================
# Всплывающие подсказки
# ==================================================================
class ToolTip:
    """Всплывающая подсказка при наведении курсора на виджет."""

    def __init__(self, widget, text, delay=500, wraplength=280,
                 bg="#ffffe0", fg="#2c3e50", border="#c9b96b"):
        self.widget     = widget
        self.text       = text
        self.delay      = delay
        self.wraplength = wraplength
        self.bg         = bg
        self.fg         = fg
        self.border     = border
        self._after_id  = None
        self._tip       = None

        widget.bind("<Enter>",       self._on_enter, add="+")
        widget.bind("<Leave>",       self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")
        widget.bind("<Destroy>",     self._on_leave, add="+")

    def set_text(self, text):
        self.text = text

    def _on_enter(self, event=None):
        self._cancel()
        try:
            self._after_id = self.widget.after(self.delay, self._show)
        except Exception:
            self._after_id = None

    def _on_leave(self, event=None):
        self._cancel()
        self._hide()

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        if self._tip is not None:
            return
        if not self.widget.winfo_exists():
            return
        try:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except Exception:
            return
        try:
            self._tip = tk.Toplevel(self.widget)
            self._tip.wm_overrideredirect(True)
            self._tip.wm_geometry(f"+{x}+{y}")
            self._tip.attributes("-topmost", True)
            lbl = tk.Label(self._tip,
                           text=self.text,
                           justify='left',
                           background=self.bg,
                           foreground=self.fg,
                           relief='solid',
                           borderwidth=1,
                           highlightbackground=self.border,
                           font=("Segoe UI", 8),
                           wraplength=self.wraplength,
                           padx=8, pady=4)
            lbl.pack()
        except Exception:
            self._tip = None

    def _hide(self):
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


# ==================================================================
# Стили
# ==================================================================
def _setup_styles(root):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", font=FONT_BASE, background=BG, foreground=FG)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=PANEL_BG)
    style.configure("TLabel", background=BG, foreground=FG, font=FONT_BASE)
    style.configure("Muted.TLabel", background=BG, foreground=FG_MUTED, font=FONT_SMALL)
    style.configure("Card.TLabel", background=PANEL_BG, foreground=FG)
    style.configure("CardMuted.TLabel", background=PANEL_BG,
                    foreground=FG_MUTED, font=FONT_SMALL)
    style.configure("CardBold.TLabel", background=PANEL_BG, foreground=FG, font=FONT_BOLD)
    style.configure("Section.TLabel", background=PANEL_BG, foreground=FG, font=FONT_BOLD)

    style.configure("TLabelframe", background=PANEL_BG,
                    bordercolor=BORDER, relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=PANEL_BG,
                    foreground=ACCENT, font=FONT_BOLD)

    def _button_style(name, bg, fg="white", hover=None, padding=(14, 8), font=FONT_BOLD):
        hover = hover or bg
        style.configure(name, font=font, foreground=fg,
                        background=bg, borderwidth=0, focusthickness=0,
                        padding=padding)
        style.map(name,
                  background=[("active", hover), ("pressed", hover)],
                  foreground=[("disabled", "#cccccc")])

    _button_style("Primary.TButton", ACCENT, hover=ACCENT_HOV)
    _button_style("Success.TButton", SUCCESS, hover="#2ecc71")
    _button_style("Warning.TButton", WARNING, hover="#f39c12")
    _button_style("Danger.TButton",  DANGER,  hover="#ff6b6b")
    _button_style("Secondary.TButton", "#e8eef5", fg=ACCENT, hover="#d5e2f0")

    _button_style("SmallPrimary.TButton",   ACCENT, hover=ACCENT_HOV,
                  padding=(8, 3), font=("Segoe UI", 9))
    _button_style("SmallDanger.TButton",    DANGER, hover="#ff6b6b",
                  padding=(8, 3), font=("Segoe UI", 9))
    _button_style("SmallSecondary.TButton", "#e8eef5", fg=ACCENT, hover="#d5e2f0",
                  padding=(8, 3), font=("Segoe UI", 9))
    _button_style("SmallSuccess.TButton",   SUCCESS, hover="#2ecc71",
                  padding=(8, 3), font=("Segoe UI", 9))
    _button_style("SmallWarning.TButton",   WARNING, hover="#f39c12",
                  padding=(8, 3), font=("Segoe UI", 9))

    _button_style("Icon.TButton", "#e8eef5", fg=ACCENT, hover="#d5e2f0",
                  padding=(8, 6), font=("Segoe UI", 11, "bold"))

    style.configure("TCheckbutton", background=BG, foreground=FG, font=FONT_BASE)
    style.map("TCheckbutton", background=[("active", BG)])
    style.configure("Card.TCheckbutton", background=PANEL_BG, foreground=FG, font=FONT_BASE)
    style.map("Card.TCheckbutton", background=[("active", PANEL_BG)])

    style.configure("TCombobox",
                    fieldbackground=PANEL_BG, background=PANEL_BG,
                    foreground=FG, arrowcolor=ACCENT,
                    bordercolor=BORDER, padding=4)

    style.configure("TSeparator", background=BORDER)


# ==================================================================
# Тексты подсказок
# ==================================================================
STAGE_TIPS = {
    "enabled":  "Включить/выключить эту ступень сглаживания.\n"
                "Если выключено — данные передаются дальше без изменений.",
    "algo":     "Метод сглаживания сигнала:\n"
                "• Стандартный — двойное усреднение с коридором,\n"
                "• Экспоненциальный — EMA,\n"
                "• Калман — оптимальный фильтр,\n"
                "• Медианный — против импульсных выбросов,\n"
                "• Савицкого–Голея — сглаживание полиномом.",

    "default.corridor":     "Ширина коридора вокруг усечённого среднего, %.\n"
                            "Значения вне коридора обрезаются до границ.\n"
                            "Больше — мягче ограничения, сильнее разброс.",
    "default.window_trunc": "Окно усечённого среднего (нечётное).\n"
                            "Внутри окна отбрасываются макс. и мин.,\n"
                            "остальные усредняются. Больше — устойчивее к выбросам.",
    "default.window_final": "Окно финального скользящего среднего (нечётное).\n"
                            "Больше — сглаженнее итоговая кривая.",

    "exponential.alpha":    "Коэффициент α экспоненциального сглаживания:\n"
                            "y[i] = α·x[i] + (1−α)·y[i−1].\n"
                            "Меньше — сильнее сглаживание и инерция,\n"
                            "больше — ближе к исходному сигналу.",

    "kalman.q":             "Шум процесса Q фильтра Калмана.\n"
                            "Больше — фильтр быстрее реагирует на изменения,\n"
                            "но становится шумнее.",
    "kalman.r":             "Шум измерения R фильтра Калмана.\n"
                            "Больше — фильтр больше доверяет модели,\n"
                            "кривая становится плавнее и инертнее.",

    "median.window":        "Размер окна медианного фильтра (нечётное).\n"
                            "Хорошо убирает одиночные импульсные выбросы.\n"
                            "Больше — сильнее сглаживание, могут теряться пики.",

    "savgol.window":        "Окно фильтра Савицкого–Голея (нечётное).\n"
                            "Больше — сильнее сглаживание, но хуже передаются\n"
                            "быстрые изменения.",
    "savgol.order":         "Степень аппроксимирующего полинома (обычно 2–4).\n"
                            "Меньше степень — сильнее сглаживание,\n"
                            "больше — лучше сохраняются локальные формы.",
}

APP_TIPS = {
    "jitter_window": "Размер окна ±Δt для расчёта локального размаха\n"
                     "ускорения (max − min) — это мера дребезга.\n"
                     "Больше окно — дребезг усредняется по более длинному\n"
                     "интервалу времени.",

    "k_threshold":   "Порог дребезга для сглаживания K.\n"
                     "K (сырой) = сумма ускорений / сглаженное ускорение —\n"
                     "считается всегда, без сглаживания.\n"
                     "K2 — это K, пропущенный через фильтр Калмана там,\n"
                     "где дребезг ниже порога.\n"
                     "На шумных участках K2 «замораживается» на последнем\n"
                     "валидном значении.",

    "k_q":           "Шум процесса Q фильтра Калмана для K2.\n"
                     "Больше — K2 быстрее реагирует на изменения, но шумнее.\n"
                     "Меньше — K2 стабильнее, но инертнее.",

    "k_r":           "Шум измерения R фильтра Калмана для K2.\n"
                     "Больше — K2 более стабильный и плавный.\n"
                     "Меньше — K2 сильнее следует за сырыми значениями K.",

    "k2":            "K2 — сглаженный коэффициент K (Калман с гейтингом по дребезгу).\n"
                     "Восстановленное ускорение = сумма / K2\n"
                     "должно совпасть со сглаженным ускорением.",

    "toggle_panel":  "Скрыть панель управления (F9)",
}


# ==================================================================
# Ступень сглаживания
# ==================================================================
class SmoothingStage:
    """Одна ступень сглаживания: вкл/выкл + алгоритм + параметры."""

    ALGO_DISPLAY = {
        "Стандартный (двойное сглаживание)": "default",
        "Экспоненциальное сглаживание":      "exponential",
        "Фильтр Калмана":                    "kalman",
        "Медианный фильтр":                  "median",
        "Фильтр Савицкого – Голея":          "savgol",
    }
    ALGO_REVERSE = {v: k for k, v in ALGO_DISPLAY.items()}

    def __init__(self, parent, title,
                 enabled_default=True, algo_default="default"):
        self.enabled   = tk.BooleanVar(value=enabled_default)
        self.algorithm = tk.StringVar(value=algo_default)

        self.params = {
            'default':    {'corridor':      tk.DoubleVar(value=0.1),
                           'window_trunc':  tk.IntVar(value=11),
                           'window_final':  tk.IntVar(value=21)},
            'exponential':{'alpha':         tk.DoubleVar(value=0.3)},
            'kalman':     {'q':             tk.DoubleVar(value=0.01),
                           'r':             tk.DoubleVar(value=0.1)},
            'median':     {'window':        tk.IntVar(value=5)},
            'savgol':     {'window':        tk.IntVar(value=11),
                           'order':         tk.IntVar(value=3)},
        }

        self.frame = ttk.LabelFrame(parent, text=f" {title} ", padding=(8, 6))

        row1 = ttk.Frame(self.frame, style="Card.TFrame")
        row1.pack(fill='x')

        self.cb_enabled = ttk.Checkbutton(row1, text="Применять",
                                          variable=self.enabled,
                                          style="Card.TCheckbutton")
        self.cb_enabled.pack(side=tk.LEFT)
        ToolTip(self.cb_enabled, STAGE_TIPS["enabled"])

        ttk.Label(row1, text="Алгоритм:",
                  style="Card.TLabel").pack(side=tk.LEFT, padx=(8, 4))

        self.cb = ttk.Combobox(row1, values=list(self.ALGO_DISPLAY.keys()),
                               state='readonly', width=22, font=FONT_BASE)
        self.cb.set(self.ALGO_REVERSE[algo_default])
        self.cb.pack(side=tk.LEFT, fill='x', expand=True)
        self.cb.bind('<<ComboboxSelected>>', self._on_algo_change)
        ToolTip(self.cb, STAGE_TIPS["algo"])

        self.params_frame = ttk.Frame(self.frame, style="Card.TFrame")
        self.params_frame.pack(fill='x', pady=(6, 0))

        self._rebuild_params()

    @property
    def algo_code(self):
        return self.ALGO_DISPLAY.get(self.cb.get(), "default")

    def _on_algo_change(self, event=None):
        self.algorithm.set(self.algo_code)
        self._rebuild_params()

    def _rebuild_params(self):
        for w in self.params_frame.winfo_children():
            w.destroy()
        code = self.algo_code
        p = self.params[code]

        def lbl(t):
            ttk.Label(self.params_frame, text=t,
                      style="Card.TLabel").pack(side=tk.LEFT)

        def sp(var, f, t, inc, w, tip_key):
            box = ttk.Spinbox(self.params_frame, from_=f, to=t, increment=inc,
                              width=w, textvariable=var,
                              font=FONT_BASE)
            box.pack(side=tk.LEFT, padx=3)
            tip_text = STAGE_TIPS.get(tip_key)
            if tip_text:
                ToolTip(box, tip_text)
            return box

        if code == 'default':
            lbl("Коридор:")
            sp(p['corridor'],     0.01, 10.0, 0.01, 5, "default.corridor")
            lbl("%")
            lbl("  Усеч.:")
            sp(p['window_trunc'], 3, 101, 2, 4, "default.window_trunc")
            lbl("  Фин.:")
            sp(p['window_final'], 3, 201, 2, 4, "default.window_final")
        elif code == 'exponential':
            lbl("α:")
            sp(p['alpha'], 0.01, 1.0, 0.01, 5, "exponential.alpha")
        elif code == 'kalman':
            lbl("Q:")
            sp(p['q'], 0.0001, 1.0, 0.0001, 7, "kalman.q")
            lbl("  R:")
            sp(p['r'], 0.0001, 1.0, 0.0001, 7, "kalman.r")
        elif code == 'median':
            lbl("Окно:")
            sp(p['window'], 3, 21, 2, 4, "median.window")
        elif code == 'savgol':
            lbl("Окно:")
            sp(p['window'], 5, 31, 2, 4, "savgol.window")
            lbl("  Степень:")
            sp(p['order'], 1, 5, 1, 3, "savgol.order")

    def get_params(self):
        code = self.algo_code
        return {k: v.get() for k, v in self.params[code].items()}

    def pack(self, **kw):
        self.frame.pack(**kw)


# ==================================================================
# Диалог выбора столбцов
# ==================================================================
class ColumnSelectorDialog:
    def __init__(self, parent, title, all_columns, default_selected=None, useful_columns=None):
        self.parent = parent
        self.title = title
        self.all_columns = all_columns
        self.default_selected = default_selected or []
        self.useful_columns = useful_columns or []

        self.selected = []
        self.checkboxes = {}
        self.show_all = BooleanVar(value=False)
        self.canvas = None

        self.dialog = Toplevel(parent)
        self.dialog.title(title)
        self.dialog.configure(bg=BG)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        dialog_width = 420
        dialog_height = 500
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        self.dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        self.dialog.protocol("WM_DELETE_WINDOW", self.on_cancel)

        self.create_widgets()
        self._bind_mousewheel()
        self.dialog.wait_window()

    def create_widgets(self):
        top = ttk.Frame(self.dialog, padding=(12, 10, 12, 4))
        top.pack(fill='x')

        ttk.Checkbutton(top, text="Показать все столбцы",
                        variable=self.show_all, command=self.update_list,
                        style="TCheckbutton").pack(anchor='w')

        body = ttk.Frame(self.dialog, padding=(12, 4, 12, 4))
        body.pack(fill=tk.BOTH, expand=True)

        canvas_frame = ttk.Frame(body, style="Card.TFrame")
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(canvas_frame, bg=PANEL_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style="Card.TFrame")

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        scrollbar.pack(side="right", fill="y")

        self.canvas = canvas
        self.scrollable_frame = scrollable_frame

        btn_frame = ttk.Frame(self.dialog, padding=(12, 8, 12, 12))
        btn_frame.pack(fill='x')
        ttk.Button(btn_frame, text="OK", command=self.on_ok,
                   style="Primary.TButton", width=12).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Отмена", command=self.on_cancel,
                   style="Secondary.TButton", width=12).pack(side=tk.LEFT)

        self.update_list()

    def _bind_mousewheel(self):
        self.dialog.bind_all("<MouseWheel>", self._on_mousewheel)
        self.dialog.bind_all("<Button-4>",   self._on_mousewheel)
        self.dialog.bind_all("<Button-5>",   self._on_mousewheel)

    def _unbind_mousewheel(self):
        self.dialog.unbind_all("<MouseWheel>")
        self.dialog.unbind_all("<Button-4>")
        self.dialog.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        if self.canvas is None:
            return
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            d = event.delta
            if d == 0:
                return
            delta = -int(d / 120) if abs(d) >= 120 else (-1 if d > 0 else 1)
        self.canvas.yview_scroll(delta, "units")

    def update_list(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.checkboxes.clear()

        if self.show_all.get():
            columns_to_show = self.all_columns
        else:
            columns_to_show = [col for col in self.all_columns if col in self.useful_columns]
            if not columns_to_show:
                columns_to_show = self.all_columns

        for col in columns_to_show:
            var = BooleanVar(value=(col in self.default_selected))
            cb = ttk.Checkbutton(self.scrollable_frame, text=col, variable=var,
                                 style="Card.TCheckbutton")
            cb.pack(fill='x', padx=4, pady=2)
            self.checkboxes[col] = var

        if self.canvas is not None:
            self.canvas.yview_moveto(0)

    def on_ok(self):
        self.selected = [col for col, var in self.checkboxes.items() if var.get()]
        self._unbind_mousewheel()
        self.dialog.destroy()

    def on_cancel(self):
        self.selected = self.default_selected
        self._unbind_mousewheel()
        self.dialog.destroy()


# ==================================================================
# Главное приложение
# ==================================================================
class SpeedAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.state('zoomed')
        self.root.title("Анализ скорости поезда")
        self.root.geometry("1400x800")
        self.root.configure(bg=BG)

        _setup_styles(self.root)

        self.file_path = tk.StringVar()
        self.df_raw = None
        self.df_full = None
        self.time_col = None
        self.top_columns = []
        self.bottom_columns = []

        self.default_top_columns = []
        self.default_bottom_columns = []

        self.selection_x1 = None
        self.selection_x2 = None

        self.processor = SpeedProcessor()

        self.max_traction_N = None

        self.jitter_window_var = tk.DoubleVar(value=5.0)

        # ---- Параметры коэффициента K2 ----
        self.k_jitter_threshold_var = tk.DoubleVar(value=0.01)
        self.k_kalman_q_var         = tk.DoubleVar(value=0.01)
        self.k_kalman_r_var         = tk.DoubleVar(value=0.1)

        # ---- Состояние панели управления ----
        self.control_panel_visible = True
        self.tooltip_toggle_panel  = None

        self.create_widgets()

        # ---- Горячая клавиша F9 ----
        self.root.bind("<F9>", lambda e: self.toggle_control_panel())

    def create_widgets(self):
        self.status_var = tk.StringVar()
        self.status_var.set("Готов к работе")
        status_bar = tk.Label(self.root, textvariable=self.status_var,
                              relief=tk.FLAT, anchor=tk.W, font=FONT_SMALL,
                              bg="#e8eef5", fg=FG, padx=12, pady=6)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.main_split = ttk.Frame(self.root, padding=(12, 12, 12, 6))
        self.main_split.pack(fill=tk.BOTH, expand=True)

        left_container = ttk.Frame(self.main_split)
        left_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        top_card = ttk.Frame(left_container, style="Card.TFrame", padding=12)
        top_card.pack(fill='x', pady=(0, 8))

        ttk.Button(top_card, text="📂  Выбрать Excel-файл",
                   command=self.select_file, style="Success.TButton").pack(side=tk.LEFT)

        self.lbl_path = tk.Label(top_card, text="Файл не выбран",
                                 font=FONT_SMALL, bg=PANEL_BG, fg=FG_MUTED,
                                 anchor='w')
        self.lbl_path.pack(side=tk.LEFT, padx=14, fill='x', expand=True)

        self.btn_toggle_panel = ttk.Button(top_card, text="▶",
                                           command=self.toggle_control_panel,
                                           style="Icon.TButton")
        self.btn_toggle_panel.pack(side=tk.RIGHT, padx=(6, 0))
        self.tooltip_toggle_panel = ToolTip(self.btn_toggle_panel,
                                            APP_TIPS["toggle_panel"])

        ttk.Button(top_card, text="⚡  Выполнить расчёт",
                   command=self.calculate, style="Primary.TButton").pack(side=tk.RIGHT)

        pipeline_frame = ttk.LabelFrame(left_container,
                                        text=" Обработка ", padding=8)
        pipeline_frame.pack(fill='x', pady=(0, 8))

        stages_row = ttk.Frame(pipeline_frame, style="Card.TFrame")
        stages_row.pack(fill='x')

        self.stage_speed = SmoothingStage(
            stages_row, "① Скорость",
            enabled_default=True, algo_default="default")
        self.stage_speed.pack(side=tk.LEFT, fill='x', expand=True, padx=(0, 4))

        self.stage_accel1 = SmoothingStage(
            stages_row, "② Ускорение — 1-е сглаживание",
            enabled_default=False, algo_default="default")
        self.stage_accel1.pack(side=tk.LEFT, fill='x', expand=True, padx=4)

        self.stage_accel2 = SmoothingStage(
            stages_row, "③ Ускорение — 2-е сглаживание",
            enabled_default=False, algo_default="default")
        self.stage_accel2.pack(side=tk.LEFT, fill='x', expand=True, padx=(4, 0))

        info_row = ttk.Frame(pipeline_frame, style="Card.TFrame")
        info_row.pack(fill='x', pady=(8, 0))

        lbl_jw = ttk.Label(info_row, text="Дребезг ускорения — окно ±",
                           style="Card.TLabel")
        lbl_jw.pack(side=tk.LEFT)
        ToolTip(lbl_jw, APP_TIPS["jitter_window"])

        sb_jw = ttk.Spinbox(info_row, from_=0.1, to=120.0, increment=0.5,
                            width=6, textvariable=self.jitter_window_var,
                            font=FONT_BASE)
        sb_jw.pack(side=tk.LEFT, padx=4)
        ToolTip(sb_jw, APP_TIPS["jitter_window"])

        ttk.Label(info_row, text="с", style="Card.TLabel").pack(side=tk.LEFT)

        self.info_label = ttk.Label(info_row, text="", style="CardMuted.TLabel")
        self.info_label.pack(side=tk.LEFT, padx=(16, 0))
        self._update_info_label()

        k_row = ttk.Frame(pipeline_frame, style="Card.TFrame")
        k_row.pack(fill='x', pady=(6, 0))

        lbl_kt = ttk.Label(k_row, text="K2: сглаживаем, если дребезг <",
                           style="Card.TLabel")
        lbl_kt.pack(side=tk.LEFT)
        ToolTip(lbl_kt, APP_TIPS["k_threshold"])

        sb_kt = ttk.Spinbox(k_row, from_=0.0, to=1.0, increment=0.001,
                            width=7, textvariable=self.k_jitter_threshold_var,
                            font=FONT_BASE)
        sb_kt.pack(side=tk.LEFT, padx=4)
        ToolTip(sb_kt, APP_TIPS["k_threshold"])

        ttk.Label(k_row, text="м/с²",
                  style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 14))

        lbl_kq = ttk.Label(k_row, text="Калман Q:",
                           style="Card.TLabel")
        lbl_kq.pack(side=tk.LEFT)
        ToolTip(lbl_kq, APP_TIPS["k_q"])

        sb_kq = ttk.Spinbox(k_row, from_=0.000001, to=1.0, increment=0.0001,
                            width=8, textvariable=self.k_kalman_q_var,
                            font=FONT_BASE)
        sb_kq.pack(side=tk.LEFT, padx=4)
        ToolTip(sb_kq, APP_TIPS["k_q"])

        lbl_kr = ttk.Label(k_row, text="R:", style="Card.TLabel")
        lbl_kr.pack(side=tk.LEFT, padx=(8, 0))
        ToolTip(lbl_kr, APP_TIPS["k_r"])

        sb_kr = ttk.Spinbox(k_row, from_=0.000001, to=1.0, increment=0.0001,
                            width=8, textvariable=self.k_kalman_r_var,
                            font=FONT_BASE)
        sb_kr.pack(side=tk.LEFT, padx=4)
        ToolTip(sb_kr, APP_TIPS["k_r"])

        self.figure_frame = ttk.Frame(left_container, style="Card.TFrame")
        self.figure_frame.pack(fill=tk.BOTH, expand=True)

        self.control_panel = ttk.Frame(self.main_split, style="Card.TFrame", width=360)
        self.control_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(12, 0))
        self.control_panel.pack_propagate(False)

        self.toolbar_frame = ttk.Frame(self.control_panel, style="Card.TFrame")

        self.plot_manager = PlotManager(self.figure_frame,
                                        toolbar_frame=self.toolbar_frame)
        self.plot_manager.set_status_callback(self.update_status)
        self.plot_manager.set_hover_callback(self.on_hover)
        self.plot_manager.set_selection_callback(self.on_selection)

        self.create_control_panel()

        self.btn_toggle_panel.config(text="▶")
        if self.tooltip_toggle_panel is not None:
            self.tooltip_toggle_panel.set_text("Скрыть панель управления (F9)")

    # ------------------------------------------------------------------
    def toggle_control_panel(self):
        if self.control_panel_visible:
            self.control_panel.pack_forget()
            self.control_panel_visible = False
            self.btn_toggle_panel.config(text="◀")
            if self.tooltip_toggle_panel is not None:
                self.tooltip_toggle_panel.set_text("Показать панель управления (F9)")
            self.status_var.set("Панель управления скрыта (F9 — показать)")
        else:
            self.control_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(12, 0))
            self.control_panel_visible = True
            self.btn_toggle_panel.config(text="▶")
            if self.tooltip_toggle_panel is not None:
                self.tooltip_toggle_panel.set_text("Скрыть панель управления (F9)")
            self.status_var.set("Панель управления показана")

    # ------------------------------------------------------------------
    def _card_section(self, parent, title=None):
        wrap = ttk.Frame(parent, style="Card.TFrame", padding=(10, 6, 10, 6))
        if title:
            ttk.Label(wrap, text=title, style="Section.TLabel").pack(anchor='w')
        return wrap

    def _separator(self, parent):
        ttk.Separator(parent, orient='horizontal').pack(fill='x', pady=4)

    def create_control_panel(self):
        header = ttk.Frame(self.control_panel, style="Card.TFrame",
                           padding=(10, 8, 10, 2))
        header.pack(fill='x')
        ttk.Label(header, text="Управление графиками",
                  style="Section.TLabel").pack(anchor='w')

        sec_cols = self._card_section(self.control_panel, "Столбцы графиков")
        sec_cols.pack(fill='x', padx=6, pady=(0, 4))

        row_top = ttk.Frame(sec_cols, style="Card.TFrame")
        row_top.pack(fill='x')
        ttk.Label(row_top, text="Верхний:", style="Card.TLabel",
                  width=9).pack(side=tk.LEFT)
        ttk.Button(row_top, text="Выбрать…",
                   command=lambda: self.select_columns('top'),
                   style="SmallSecondary.TButton").pack(side=tk.LEFT, padx=4)
        self.lbl_top_selected = tk.Label(sec_cols, text="не выбрано",
                                         font=FONT_SMALL, bg=PANEL_BG, fg=FG_MUTED,
                                         wraplength=320, justify='left', anchor='w')
        self.lbl_top_selected.pack(fill='x', padx=(4, 0), pady=(2, 4))

        row_bot = ttk.Frame(sec_cols, style="Card.TFrame")
        row_bot.pack(fill='x')
        ttk.Label(row_bot, text="Нижний:", style="Card.TLabel",
                  width=9).pack(side=tk.LEFT)
        ttk.Button(row_bot, text="Выбрать…",
                   command=lambda: self.select_columns('bottom'),
                   style="SmallSecondary.TButton").pack(side=tk.LEFT, padx=4)
        self.lbl_bottom_selected = tk.Label(sec_cols, text="не выбрано",
                                            font=FONT_SMALL, bg=PANEL_BG, fg=FG_MUTED,
                                            wraplength=320, justify='left', anchor='w')
        self.lbl_bottom_selected.pack(fill='x', padx=(4, 0), pady=(2, 2))

        self._separator(self.control_panel)

        row_btn = ttk.Frame(self.control_panel, style="Card.TFrame",
                            padding=(10, 0, 10, 0))
        row_btn.pack(fill='x')
        ttk.Button(row_btn, text="✓ Применить",
                   command=self.apply_changes,
                   style="SmallSuccess.TButton").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(row_btn, text="↺ Сбросить",
                   command=self.reset_selection,
                   style="SmallWarning.TButton").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(row_btn, text="⤢ Вид",
                   command=self.reset_view,
                   style="SmallSecondary.TButton").pack(side=tk.LEFT)

        self._separator(self.control_panel)

        sec_tools = self._card_section(self.control_panel, "Инструменты графика")
        sec_tools.pack(fill='x', padx=6, pady=(0, 4))
        self.toolbar_frame.pack(fill='x')

        self._separator(self.control_panel)

        sec_sel = self._card_section(self.control_panel, "Выделение области")
        sec_sel.pack(fill='x', padx=6, pady=(0, 4))
        self.selection_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sec_sel, text="Режим выделения (вкл/выкл)",
                        variable=self.selection_mode_var,
                        command=self.toggle_selection_mode,
                        style="Card.TCheckbutton").pack(anchor='w')

        sel_btns_row1 = ttk.Frame(sec_sel, style="Card.TFrame")
        sel_btns_row1.pack(fill='x', pady=(4, 0))
        ttk.Button(sel_btns_row1, text="Выделить всю область",
                   command=self.select_full_range,
                   style="SmallSecondary.TButton").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(sel_btns_row1, text="Очистить",
                   command=self.clear_selection,
                   style="SmallDanger.TButton").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(sel_btns_row1, text="В Excel",
                   command=self.export_selection_to_excel,
                   style="SmallPrimary.TButton").pack(side=tk.LEFT)

        self._separator(self.control_panel)

        sec_hover = self._card_section(self.control_panel, "Значения в точке")
        sec_hover.pack(fill='x', padx=6, pady=(0, 4))

        hover_border = tk.Frame(sec_hover, bg=BORDER)
        hover_border.pack(fill=tk.X, expand=False)

        self.hover_label = tk.Label(hover_border,
                                    text="Наведите курсор на график",
                                    font=FONT_MONO,
                                    bg="#fbfcfe", fg=FG,
                                    justify='left', anchor='nw',
                                    wraplength=310,
                                    padx=8, pady=6)
        self.hover_label.pack(fill=tk.BOTH, expand=True)

        self._separator(self.control_panel)

        stat_header = ttk.Frame(self.control_panel, style="Card.TFrame",
                                padding=(10, 0, 10, 2))
        stat_header.pack(fill='x')
        ttk.Label(stat_header, text="Статистика выделенной области",
                  style="Section.TLabel").pack(anchor='w')

        stat_body = ttk.Frame(self.control_panel, style="Card.TFrame",
                              padding=(10, 0, 10, 8))
        stat_body.pack(fill='x')

        selection_frame = ttk.Frame(stat_body, style="Card.TFrame")
        selection_frame.pack(fill='x')

        self.selection_text = tk.Text(selection_frame, height=8, width=42,
                                      font=FONT_MONO, relief=tk.FLAT, bd=0,
                                      wrap=tk.WORD, bg="#fbfcfe", fg=FG,
                                      highlightthickness=1,
                                      highlightbackground=BORDER,
                                      highlightcolor=ACCENT)
        sel_scroll_y = ttk.Scrollbar(selection_frame, orient=tk.VERTICAL,
                                     command=self.selection_text.yview)
        self.selection_text.config(yscrollcommand=sel_scroll_y.set)
        self.selection_text.grid(row=0, column=0, sticky='nsew')
        sel_scroll_y.grid(row=0, column=1, sticky='ns')
        selection_frame.grid_rowconfigure(0, weight=1)
        selection_frame.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    def _update_info_label(self):
        m_text = (f"Масса поезда {TRAIN_MASS_T:.0f} т, "
                  f"инерционная {INERTIAL_MASS_T:.1f} т "
                  f"({INERTIAL_MASS_K:.2f} от массы), "
                  f"сумма {TRAIN_MASS_T + INERTIAL_MASS_T:.1f} т")
        if self.max_traction_N is not None:
            f_text = (f"   |   |Freal| макс = {self.max_traction_N:.0f} Н "
                      f"({self.max_traction_N / 1000:.1f} кН)")
        else:
            f_text = "   |   |Freal| макс: нет столбца"
        self.info_label.config(text="   " + m_text + f_text)

    def toggle_selection_mode(self):
        enabled = self.selection_mode_var.get()
        self.plot_manager.set_selection_mode(enabled)

    def select_full_range(self):
        if self.df_full is None:
            messagebox.showinfo("Информация",
                                "Сначала загрузите данные и выполните расчёт.")
            return
        if self.plot_manager.ax1 is None:
            messagebox.showinfo("Информация",
                                "Сначала постройте график.")
            return
        self.plot_manager.select_full_range()

    def on_selection(self, x1, x2, stats):
        if x1 is None and stats is None:
            self.selection_x1 = None
            self.selection_x2 = None
            self.selection_text.delete(1.0, tk.END)
            self.selection_text.insert(tk.END, "Выделение очищено")
            return

        self.selection_x1 = x1
        self.selection_x2 = x2

        self.selection_text.delete(1.0, tk.END)
        if not stats:
            self.selection_text.insert(tk.END, "Нет числовых данных в выделенной области")
            return
        header = f"Интервал: {x1:.2f} – {x2:.2f} с\n\n"
        self.selection_text.insert(tk.END, header)
        for col, (mean, minv, maxv, std) in stats.items():
            unit = self.plot_manager.get_unit(col)
            unit_str = f" ({unit})" if unit else ""
            line = (f"{col}{unit_str}:\n"
                    f"  среднее = {mean:.3f}\n"
                    f"  мин     = {minv:.3f}\n"
                    f"  макс    = {maxv:.3f}\n"
                    f"  ст.откл = {std:.3f}\n\n")
            self.selection_text.insert(tk.END, line)
        self.selection_text.see(1.0)

    def clear_selection(self):
        self.plot_manager.clear_selection()
        self.selection_x1 = None
        self.selection_x2 = None
        self.selection_text.delete(1.0, tk.END)
        self.selection_text.insert(tk.END, "Выделение очищено")
        self.status_var.set("Выделение очищено")

    def export_selection_to_excel(self):
        if self.df_full is None:
            messagebox.showinfo("Информация",
                                "Сначала загрузите данные и выполните расчёт.")
            return
        if self.selection_x1 is None or self.selection_x2 is None:
            messagebox.showinfo("Информация",
                                "Сначала выделите область на графике.")
            return

        x1, x2 = self.selection_x1, self.selection_x2
        time = self.df_full[self.time_col].values
        mask = (time >= x1) & (time <= x2)
        if not mask.any():
            messagebox.showwarning("Предупреждение",
                                   "В выделенном интервале нет данных.")
            return

        export_df = self.df_full.loc[mask].copy()
        default_name = f"selection_{x1:.2f}_{x2:.2f}.xlsx"
        filename = filedialog.asksaveasfilename(
            title="Сохранить выделенную область в Excel",
            defaultextension=".xlsx",
            initialfile=default_name,
            filetypes=[("Excel files", "*.xlsx")]
        )
        if not filename:
            return

        try:
            export_df.to_excel(filename, index=False)
            self.status_var.set(
                f"Сохранено {len(export_df)} строк в {os.path.basename(filename)}")
            messagebox.showinfo("Успех",
                                f"Данные сохранены:\n{filename}\n\n"
                                f"Строк: {len(export_df)}\n"
                                f"Столбцов: {len(export_df.columns)}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{str(e)}")

    def on_hover(self, time, data_dict):
        if time is None or not data_dict:
            self.hover_label.config(text="Наведите курсор на график")
            return

        lines = [f"t = {time:.2f} с", ""]
        for col, value in sorted(data_dict.items()):
            if value is not None and np.isfinite(value):
                unit = self.plot_manager.get_unit(col)
                if unit:
                    lines.append(f"{col} ({unit}): {value:.3f}")
                else:
                    lines.append(f"{col}: {value:.3f}")
        if len(lines) == 2:
            lines.append("(нет данных)")

        self.hover_label.config(text="\n".join(lines))

    def update_status(self, message):
        self.status_var.set(message)

    # ------------------------------------------------------------------
    def _available_columns(self):
        hidden = {LOW_SPEED, HIGH_SPEED,
                  LOW_ACCEL_1, HIGH_ACCEL_1,
                  LOW_ACCEL_2, HIGH_ACCEL_2}

        df_cols = [c for c in self.df_full.columns
                   if c != self.time_col and c not in hidden]

        has_speed_corr   = (LOW_SPEED in self.df_full.columns
                            and HIGH_SPEED in self.df_full.columns)
        has_accel_1_corr = (LOW_ACCEL_1 in self.df_full.columns
                            and HIGH_ACCEL_1 in self.df_full.columns)
        has_accel_2_corr = (LOW_ACCEL_2 in self.df_full.columns
                            and HIGH_ACCEL_2 in self.df_full.columns)

        speed_raw = next((c for c in df_cols
                          if 'скорость' in c.lower() or 'speed' in c.lower()),
                         None)
        group_speed = []
        if speed_raw:
            group_speed.append(speed_raw)
        for name in (COL_V_SMOOTH, COL_V_MS):
            if name in df_cols:
                group_speed.append(name)
        if has_speed_corr:
            group_speed.append(CORRIDOR_SPEED_NAME)

        group_accel = []
        for name in (COL_ACCEL_RAW, COL_ACCEL_1, COL_ACCEL_2):
            if name in df_cols:
                group_accel.append(name)
        if has_accel_1_corr:
            group_accel.append(CORRIDOR_ACCEL_1_NAME)
        if has_accel_2_corr:
            group_accel.append(CORRIDOR_ACCEL_2_NAME)
        if COL_SLOPE_ACCEL in df_cols:
            group_accel.append(COL_SLOPE_ACCEL)
        if COL_TRACTION_ACCEL in df_cols:
            group_accel.append(COL_TRACTION_ACCEL)
        if COL_RESISTANCE_ACCEL in df_cols:
            group_accel.append(COL_RESISTANCE_ACCEL)
        if COL_SUM_ACCEL in df_cols:
            group_accel.append(COL_SUM_ACCEL)
        if COL_K in df_cols:
            group_accel.append(COL_K)
        if COL_K2 in df_cols:
            group_accel.append(COL_K2)
        if COL_ACCEL_K in df_cols:
            group_accel.append(COL_ACCEL_K)
        if COL_JITTER in df_cols:
            group_accel.append(COL_JITTER)

        group_pressure = [c for c in ('ТЦ', 'ТМ', 'ГР') if c in df_cols]

        group_force = [c for c in (TRACTION_NAME, COL_TRACTION_PCT,
                                   'Тяга', 'Тормоз',
                                   COL_RESISTANCE_FORCE,
                                   COL_SLOPE_FORCE, 'Уклон')
                       if c in df_cols]

        used = set(group_speed + group_accel + group_pressure + group_force)
        rest = [c for c in df_cols if c not in used]

        return group_speed + group_accel + group_pressure + group_force + rest

    def select_columns(self, target):
        if self.df_full is None:
            messagebox.showinfo("Информация", "Сначала загрузите данные.")
            return

        all_cols = self._available_columns()
        if not all_cols:
            messagebox.showwarning("Предупреждение", "Нет доступных столбцов.")
            return

        useful = ['Уклон', COL_SLOPE_FORCE, COL_SLOPE_ACCEL,
                  COL_TRACTION_ACCEL, COL_RESISTANCE_ACCEL,
                  COL_RESISTANCE_FORCE, COL_SUM_ACCEL,
                  COL_K, COL_K2, COL_ACCEL_K,
                  TRACTION_NAME, COL_TRACTION_PCT,
                  'Тяга', 'Тормоз',
                  'ТЦ', 'ТМ', 'ГР', 'Скорость',
                  COL_V_SMOOTH, COL_V_MS,
                  COL_ACCEL_RAW, COL_ACCEL_1, COL_ACCEL_2,
                  COL_JITTER,
                  CORRIDOR_SPEED_NAME,
                  CORRIDOR_ACCEL_1_NAME,
                  CORRIDOR_ACCEL_2_NAME]
        useful_cols = [col for col in useful if col in all_cols]

        default = self.top_columns if target == 'top' else self.bottom_columns
        dialog = ColumnSelectorDialog(
            self.root,
            f"Выбор столбцов для {'верхнего' if target == 'top' else 'нижнего'} графика",
            all_cols,
            default_selected=default,
            useful_columns=useful_cols
        )
        selected = dialog.selected
        if target == 'top':
            self.top_columns = selected
            self.lbl_top_selected.config(
                text=", ".join(selected) if selected else "не выбрано")
        else:
            self.bottom_columns = selected
            self.lbl_bottom_selected.config(
                text=", ".join(selected) if selected else "не выбрано")

    def select_file(self):
        filename = filedialog.askopenfilename(
            title="Выберите Excel-файл с данными",
            filetypes=[("Excel files", "*.xlsx *.xls")]
        )
        if filename:
            self.file_path.set(filename)
            self.lbl_path.config(text=os.path.basename(filename), fg=FG)
            self.status_var.set(f"Выбран файл: {os.path.basename(filename)}")
            try:
                df_full = pd.read_excel(filename, header=0)

                if FREAL_RAW_NAME in df_full.columns and \
                        TRACTION_NAME not in df_full.columns:
                    df_full = df_full.rename(
                        columns={FREAL_RAW_NAME: TRACTION_NAME})
                if TRACTION_NAME in df_full.columns:
                    df_full[TRACTION_NAME] = (
                        pd.to_numeric(df_full[TRACTION_NAME], errors='coerce')
                        * FREAL_TO_N
                    )

                time_col, _ = find_columns(df_full)
                if time_col is None:
                    time_col = df_full.columns[0]
                self.time_col = time_col
                self.df_raw = df_full.copy()
                self.df_full = df_full.copy()

                if TRACTION_NAME in df_full.columns:
                    tr = pd.to_numeric(df_full[TRACTION_NAME], errors='coerce')
                    if tr.notna().any():
                        self.max_traction_N = float(tr.abs().max())
                    else:
                        self.max_traction_N = None
                else:
                    self.max_traction_N = None

                self.top_columns = []
                self.bottom_columns = []
                self.default_top_columns = []
                self.default_bottom_columns = []
                self.selection_x1 = None
                self.selection_x2 = None
                self.lbl_top_selected.config(text="не выбрано", fg=FG_MUTED)
                self.lbl_bottom_selected.config(text="не выбрано", fg=FG_MUTED)
                self._update_info_label()
                self.status_var.set(
                    "Данные загружены. Нажмите 'Выполнить расчёт' для построения графиков.")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{str(e)}")
        else:
            self.status_var.set("Файл не выбран")

    # ------------------------------------------------------------------
    def _smooth(self, values, algorithm, params):
        n = len(values)
        if algorithm == "default":
            return self.processor.smooth_default(
                values, n,
                corridor_percent=params['corridor'],
                window_trunc=params['window_trunc'],
                window_final=params['window_final'])
        if algorithm == "exponential":
            return self.processor.smooth_exponential(
                values, n, alpha=params['alpha'])
        if algorithm == "kalman":
            return self.processor.smooth_kalman(
                values, n, q=params['q'], r=params['r'])
        if algorithm == "median":
            return self.processor.smooth_median(
                values, n, window=params['window'])
        if algorithm == "savgol":
            return self.processor.smooth_savgol(
                values, n, window=params['window'], order=params['order'])
        return self.processor.smooth_default(values, n)

    # ------------------------------------------------------------------
    @staticmethod
    def _kalman_with_gating(values, valid_mask, q=0.01, r=0.1):
        """Фильтр Калмана с «заморозкой»."""
        n = len(values)
        out = np.full(n, np.nan)
        x_est = None
        p_est = 1.0
        last_held = np.nan
        for i in range(n):
            v = values[i]
            if valid_mask[i] and np.isfinite(v):
                if x_est is None:
                    x_est = float(v)
                    p_est = 1.0
                else:
                    x_pred = x_est
                    p_pred = p_est + q
                    k = p_pred / (p_pred + r)
                    x_est = x_pred + k * (v - x_pred)
                    p_est = (1 - k) * p_pred
                out[i] = x_est
                last_held = x_est
            else:
                if not np.isnan(last_held):
                    out[i] = last_held
        return out

    # ------------------------------------------------------------------
    def calculate(self):
        if not self.file_path.get():
            messagebox.showerror("Ошибка", "Сначала выберите Excel-файл!")
            return
        try:
            self.status_var.set("Выполняется расчёт...")
            self.root.update()

            if self.df_raw is None:
                df_raw = pd.read_excel(self.file_path.get(), header=0)
                if FREAL_RAW_NAME in df_raw.columns and \
                        TRACTION_NAME not in df_raw.columns:
                    df_raw = df_raw.rename(
                        columns={FREAL_RAW_NAME: TRACTION_NAME})
                if TRACTION_NAME in df_raw.columns:
                    df_raw[TRACTION_NAME] = (
                        pd.to_numeric(df_raw[TRACTION_NAME], errors='coerce')
                        * FREAL_TO_N
                    )
                time_col, _ = find_columns(df_raw)
                if time_col is None:
                    time_col = df_raw.columns[0]
                self.time_col = time_col
                self.df_raw = df_raw.copy()
                self.df_full = df_raw.copy()

            df = self.df_raw.copy()

            drop_cols = [
                LOW_SPEED, HIGH_SPEED,
                LOW_ACCEL_1, HIGH_ACCEL_1,
                LOW_ACCEL_2, HIGH_ACCEL_2,
                COL_V_SMOOTH, COL_V_MS,
                COL_ACCEL_RAW, COL_ACCEL_1, COL_ACCEL_2,
                COL_JITTER,
                COL_SLOPE_FORCE, COL_SLOPE_ACCEL,
                COL_TRACTION_ACCEL, COL_TRACTION_PCT,
                COL_RESISTANCE_FORCE, COL_RESISTANCE_ACCEL,
                COL_SUM_ACCEL, COL_K, COL_K2, COL_ACCEL_K,
                'Ускорение сглаженное',
            ]
            df = df.drop(columns=[c for c in drop_cols if c in df.columns])

            if not pd.api.types.is_numeric_dtype(df[self.time_col]):
                df[self.time_col] = pd.to_numeric(df[self.time_col], errors='coerce')

            speed_col = next((c for c in df.columns
                              if 'скорость' in c.lower() or 'speed' in c.lower()),
                             None)
            if speed_col is None:
                raise ValueError("Не найден столбец со скоростью для расчёта.")

            df = df.dropna(subset=[self.time_col, speed_col]).reset_index(drop=True)
            if len(df) < 5:
                raise ValueError(
                    f"Слишком мало данных ({len(df)} строк). Нужно минимум 5.")

            if 'Уклон' in df.columns:
                uklon = pd.to_numeric(df['Уклон'], errors='coerce')
                F = uklon * TRAIN_MASS_T * 9.81
                df[COL_SLOPE_FORCE] = F
                df[COL_SLOPE_ACCEL] = -F / TOTAL_MASS_KG

            if TRACTION_NAME in df.columns:
                tr = pd.to_numeric(df[TRACTION_NAME], errors='coerce')
                df[COL_TRACTION_ACCEL] = tr / TOTAL_MASS_KG

            if TRACTION_NAME in df.columns:
                tr = pd.to_numeric(df[TRACTION_NAME], errors='coerce')
                tr_abs_max = tr.abs().max()
                if pd.notna(tr_abs_max) and tr_abs_max > 0:
                    df[COL_TRACTION_PCT] = tr.abs() / tr_abs_max * 100.0
                else:
                    df[COL_TRACTION_PCT] = np.nan

            time = df[self.time_col].values
            V    = df[speed_col].values

            if self.stage_speed.enabled.get():
                V_used = self._smooth(V, self.stage_speed.algo_code,
                                      self.stage_speed.get_params())
                df[COL_V_SMOOTH] = V_used
                if self.stage_speed.algo_code == 'default':
                    df[LOW_SPEED]  = self.processor.low_bound
                    df[HIGH_SPEED] = self.processor.high_bound
            else:
                V_used = V

            V_used_ms = V_used / 3.6
            df[COL_V_MS] = V_used_ms

            V_kmh = V_used
            df[COL_RESISTANCE_FORCE] = (
                (5.2 + (34.2 + 0.732 * V_kmh + 0.022 * V_kmh ** 2)
                 / AXLE_LOAD_T)
                * TRAIN_MASS_T
                * RESISTANCE_COEF
            )

            df[COL_RESISTANCE_ACCEL] = -df[COL_RESISTANCE_FORCE] / TOTAL_MASS_KG

            sum_accel = np.zeros(len(df))
            has_any = False
            if COL_TRACTION_ACCEL in df.columns:
                sum_accel += df[COL_TRACTION_ACCEL].fillna(0).values
                has_any = True
            if COL_SLOPE_ACCEL in df.columns:
                sum_accel += df[COL_SLOPE_ACCEL].fillna(0).values
                has_any = True
            if COL_RESISTANCE_ACCEL in df.columns:
                sum_accel += df[COL_RESISTANCE_ACCEL].fillna(0).values
                has_any = True
            if has_any:
                df[COL_SUM_ACCEL] = sum_accel

            accel = calculate_acceleration(V_used_ms, time)
            df[COL_ACCEL_RAW] = accel

            accel1 = None
            accel2 = None
            if self.stage_accel1.enabled.get():
                accel1 = self._smooth(accel, self.stage_accel1.algo_code,
                                      self.stage_accel1.get_params())
                df[COL_ACCEL_1] = accel1
                if self.stage_accel1.algo_code == 'default':
                    df[LOW_ACCEL_1]  = self.processor.low_bound
                    df[HIGH_ACCEL_1] = self.processor.high_bound
                accel = accel1

            if self.stage_accel2.enabled.get():
                accel2 = self._smooth(accel, self.stage_accel2.algo_code,
                                      self.stage_accel2.get_params())
                df[COL_ACCEL_2] = accel2
                if self.stage_accel2.algo_code == 'default':
                    df[LOW_ACCEL_2]  = self.processor.low_bound
                    df[HIGH_ACCEL_2] = self.processor.high_bound

            if accel2 is not None:
                accel_final = accel2
            elif accel1 is not None:
                accel_final = accel1
            else:
                accel_final = df[COL_ACCEL_RAW].values

            try:
                half_window = float(self.jitter_window_var.get())
            except (tk.TclError, ValueError):
                half_window = 5.0
            if half_window <= 0:
                half_window = 5.0

            df[COL_JITTER] = calculate_jitter(accel_final, time,
                                              half_window_sec=half_window)

            # ---------- Коэффициент K (сырой) ----------
            # K = сумма ускорений / сглаженное ускорение
            # Без сглаживания. Только защита от деления на ≈0.
            if COL_SUM_ACCEL in df.columns:
                sum_arr = df[COL_SUM_ACCEL].values.astype(float)
                num     = np.asarray(accel_final, dtype=float)

                with np.errstate(divide='ignore', invalid='ignore'):
                    k_raw = sum_arr / num
                k_raw = np.where(np.isfinite(k_raw), k_raw, np.nan)
                k_raw = np.where(np.abs(num) > K_MIN_DENOM, k_raw, np.nan)

                df[COL_K] = k_raw

                # ---------- Коэффициент K2 (сглаженный) ----------
                # Калман с гейтингом по дребезгу, применённый к K.
                try:
                    k_thr = float(self.k_jitter_threshold_var.get())
                except (tk.TclError, ValueError):
                    k_thr = 0.01
                try:
                    k_q = float(self.k_kalman_q_var.get())
                except (tk.TclError, ValueError):
                    k_q = 0.01
                try:
                    k_r = float(self.k_kalman_r_var.get())
                except (tk.TclError, ValueError):
                    k_r = 0.1

                jitter_arr = df[COL_JITTER].values.astype(float)

                valid_mask = (
                    np.isfinite(jitter_arr)
                    & (jitter_arr < k_thr)
                    & np.isfinite(k_raw)
                )

                df[COL_K2] = self._kalman_with_gating(k_raw, valid_mask,
                                                      q=k_q, r=k_r)

                # ---------- Восстановленное ускорение = сумма / K2 ----------
                k2_arr = df[COL_K2].values.astype(float)
                with np.errstate(divide='ignore', invalid='ignore'):
                    accel_restored = sum_arr / k2_arr
                df[COL_ACCEL_K] = np.where(
                    np.isfinite(accel_restored), accel_restored, np.nan
                )

            top_default = (COL_V_SMOOTH if self.stage_speed.enabled.get()
                           else speed_col)
            if self.stage_accel2.enabled.get():
                bottom_default = COL_ACCEL_2
            elif self.stage_accel1.enabled.get():
                bottom_default = COL_ACCEL_1
            else:
                bottom_default = COL_ACCEL_RAW

            self.default_top_columns    = [top_default]
            self.default_bottom_columns = [bottom_default]
            self.top_columns    = [top_default]
            self.bottom_columns = [bottom_default]
            self.lbl_top_selected.config(text=top_default, fg=FG)
            self.lbl_bottom_selected.config(text=bottom_default, fg=FG)

            self.df_full = df
            self.apply_changes(preserve_view=False)

            self.status_var.set("Расчёт выполнен!")
            messagebox.showinfo("Успех", "Расчёт выполнен успешно!")

        except Exception as e:
            self.status_var.set("Ошибка!")
            messagebox.showerror("Ошибка", f"Произошла ошибка:\n{str(e)}")

    def apply_changes(self, preserve_view=True):
        if self.df_full is None:
            messagebox.showinfo("Информация", "Сначала загрузите данные.")
            return
        if not self.top_columns and not self.bottom_columns:
            messagebox.showwarning("Предупреждение",
                                   "Не выбрано ни одного столбца для отображения.")
            return

        self.plot_manager.set_data(
            self.df_full,
            self.time_col,
            self.top_columns,
            self.bottom_columns,
        )
        self.plot_manager.show_plots(preserve_view=preserve_view)
        self.status_var.set("Графики обновлены")

    def reset_view(self):
        """Сбросить зум осей и построить графики в авто-масштабе."""
        if self.df_full is None:
            return
        self.plot_manager.set_data(
            self.df_full,
            self.time_col,
            self.top_columns,
            self.bottom_columns,
        )
        self.plot_manager.show_plots(preserve_view=False)
        self.status_var.set("Вид сброшен")

    def reset_selection(self):
        if self.df_full is None:
            self.top_columns = []
            self.bottom_columns = []
            self.lbl_top_selected.config(text="не выбрано", fg=FG_MUTED)
            self.lbl_bottom_selected.config(text="не выбрано", fg=FG_MUTED)
            self.status_var.set("Выбор сброшен.")
            return

        if self.default_top_columns or self.default_bottom_columns:
            self.top_columns = list(self.default_top_columns)
            self.bottom_columns = list(self.default_bottom_columns)
            self.lbl_top_selected.config(
                text=", ".join(self.top_columns) if self.top_columns else "не выбрано",
                fg=FG if self.top_columns else FG_MUTED)
            self.lbl_bottom_selected.config(
                text=", ".join(self.bottom_columns) if self.bottom_columns else "не выбрано",
                fg=FG if self.bottom_columns else FG_MUTED)

            self.plot_manager.set_data(
                self.df_full,
                self.time_col,
                self.top_columns,
                self.bottom_columns,
            )
            self.plot_manager.show_plots(preserve_view=True)
            self.status_var.set("Графики возвращены к исходному виду")
        else:
            self.top_columns = []
            self.bottom_columns = []
            self.lbl_top_selected.config(text="не выбрано", fg=FG_MUTED)
            self.lbl_bottom_selected.config(text="не выбрано", fg=FG_MUTED)
            self.status_var.set(
                "Выбор сброшен. Нажмите 'Выполнить расчёт' или выберите столбцы вручную.")


if __name__ == "__main__":
    root = tk.Tk()
    app = SpeedAnalyzerApp(root)
    root.mainloop()