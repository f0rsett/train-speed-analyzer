import tkinter as tk
from tkinter import filedialog, messagebox, StringVar, Text, Toplevel, BooleanVar, Scrollbar, ttk
import pandas as pd
import numpy as np
import os
import sys
import io

from processing import SpeedProcessor
from plotting import PlotManager
from utils import find_columns, calculate_acceleration

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
    style.configure("CardBold.TLabel", background=PANEL_BG, foreground=FG, font=FONT_BOLD)
    style.configure("Section.TLabel", background=PANEL_BG, foreground=FG, font=FONT_BOLD)

    style.configure("TLabelframe", background=PANEL_BG,
                    bordercolor=BORDER, relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=PANEL_BG,
                    foreground=ACCENT, font=FONT_BOLD)

    def _button_style(name, bg, fg="white", hover=None):
        hover = hover or bg
        style.configure(name, font=FONT_BOLD, foreground=fg,
                        background=bg, borderwidth=0, focusthickness=0,
                        padding=(14, 8))
        style.map(name,
                  background=[("active", hover), ("pressed", hover)],
                  foreground=[("disabled", "#cccccc")])

    _button_style("Primary.TButton", ACCENT, hover=ACCENT_HOV)
    _button_style("Success.TButton", SUCCESS, hover="#2ecc71")
    _button_style("Warning.TButton", WARNING, hover="#f39c12")
    _button_style("Danger.TButton",  DANGER,  hover="#ff6b6b")
    _button_style("Secondary.TButton", "#e8eef5", fg=ACCENT, hover="#d5e2f0")

    style.configure("TCheckbutton", background=BG, foreground=FG, font=FONT_BASE)
    style.map("TCheckbutton", background=[("active", BG)])
    style.configure("Card.TCheckbutton", background=PANEL_BG, foreground=FG, font=FONT_BASE)
    style.map("Card.TCheckbutton", background=[("active", PANEL_BG)])

    style.configure("TCombobox",
                    fieldbackground=PANEL_BG, background=PANEL_BG,
                    foreground=FG, arrowcolor=ACCENT,
                    bordercolor=BORDER, padding=4)

    style.configure("TSeparator", background=BORDER)


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

        self.create_widgets()
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

        self.scrollable_frame = scrollable_frame

        btn_frame = ttk.Frame(self.dialog, padding=(12, 8, 12, 12))
        btn_frame.pack(fill='x')
        ttk.Button(btn_frame, text="OK", command=self.on_ok,
                   style="Primary.TButton", width=12).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Отмена", command=self.on_cancel,
                   style="Secondary.TButton", width=12).pack(side=tk.LEFT)

        self.update_list()

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

    def on_ok(self):
        self.selected = [col for col, var in self.checkboxes.items() if var.get()]
        self.dialog.destroy()

    def on_cancel(self):
        self.selected = self.default_selected
        self.dialog.destroy()


class SpeedAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.state('zoomed')
        self.root.title("Анализ скорости поезда")
        self.root.geometry("1400x800")
        self.root.configure(bg=BG)

        _setup_styles(self.root)

        self.file_path = tk.StringVar()
        self.df_full = None
        self.time_col = None
        self.top_columns = []
        self.bottom_columns = []

        self.default_top_columns = []
        self.default_bottom_columns = []

        self.selection_x1 = None
        self.selection_x2 = None

        # ---- Параметры для СКОРОСТИ ----
        self.corridor_percent_speed = tk.DoubleVar(value=0.1)
        self.window_trunc_speed = tk.IntVar(value=11)
        self.window_final_speed = tk.IntVar(value=21)

        self.alpha_exp_speed = tk.DoubleVar(value=0.3)
        self.kalman_q_speed = tk.DoubleVar(value=0.01)
        self.kalman_r_speed = tk.DoubleVar(value=0.1)
        self.median_window_speed = tk.IntVar(value=5)
        self.savgol_window_speed = tk.IntVar(value=11)
        self.savgol_order_speed = tk.IntVar(value=3)

        # ---- Параметры для УСКОРЕНИЯ ----
        self.corridor_percent_accel = tk.DoubleVar(value=0.1)
        self.window_trunc_accel = tk.IntVar(value=11)
        self.window_final_accel = tk.IntVar(value=21)

        self.alpha_exp_accel = tk.DoubleVar(value=0.3)
        self.kalman_q_accel = tk.DoubleVar(value=0.01)
        self.kalman_r_accel = tk.DoubleVar(value=0.1)
        self.median_window_accel = tk.IntVar(value=5)
        self.savgol_window_accel = tk.IntVar(value=11)
        self.savgol_order_accel = tk.IntVar(value=3)

        self.algorithm = tk.StringVar(value="default")

        self.algorithm_display = {
            "Стандартный (двойное сглаживание)": "default",
            "Экспоненциальное сглаживание": "exponential",
            "Фильтр Калмана": "kalman",
            "Медианный фильтр": "median",
            "Фильтр Савицкого – Голея": "savgol",
        }
        self.algorithm_reverse = {v: k for k, v in self.algorithm_display.items()}

        self.smooth_speed_var = tk.BooleanVar(value=True)
        self.smooth_accel_var = tk.BooleanVar(value=False)
        self.show_corridor_var = tk.BooleanVar(value=False)

        self.processor = SpeedProcessor()

        self.create_widgets()

    def create_widgets(self):
        self.status_var = tk.StringVar()
        self.status_var.set("Готов к работе")
        status_bar = tk.Label(self.root, textvariable=self.status_var,
                              relief=tk.FLAT, anchor=tk.W, font=FONT_SMALL,
                              bg="#e8eef5", fg=FG, padx=12, pady=6)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        main_split = ttk.Frame(self.root, padding=(12, 12, 12, 6))
        main_split.pack(fill=tk.BOTH, expand=True)

        left_container = ttk.Frame(main_split)
        left_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        top_card = ttk.Frame(left_container, style="Card.TFrame", padding=12)
        top_card.pack(fill='x', pady=(0, 8))

        ttk.Button(top_card, text="📂  Выбрать Excel-файл",
                   command=self.select_file, style="Success.TButton").pack(side=tk.LEFT)

        self.lbl_path = tk.Label(top_card, text="Файл не выбран",
                                 font=FONT_SMALL, bg=PANEL_BG, fg=FG_MUTED,
                                 anchor='w')
        self.lbl_path.pack(side=tk.LEFT, padx=14, fill='x', expand=True)

        ttk.Button(top_card, text="⚡  Выполнить расчёт",
                   command=self.calculate, style="Primary.TButton").pack(side=tk.RIGHT)

        algo_card = ttk.Frame(left_container, style="Card.TFrame", padding=12)
        algo_card.pack(fill='x', pady=(0, 8))

        ttk.Label(algo_card, text="Алгоритм сглаживания:",
                  style="Section.TLabel").pack(side=tk.LEFT, padx=(0, 8))

        self.cb_algo = ttk.Combobox(
            algo_card,
            values=list(self.algorithm_display.keys()),
            state='readonly',
            width=30,
            font=FONT_BASE
        )
        self.cb_algo.set(self.algorithm_reverse[self.algorithm.get()])
        self.cb_algo.pack(side=tk.LEFT)
        self.cb_algo.bind('<<ComboboxSelected>>', self.on_algorithm_selected)

        sep = ttk.Separator(algo_card, orient='vertical')
        sep.pack(side=tk.LEFT, fill='y', padx=14, pady=2)

        ttk.Label(algo_card, text="Опции:", style="Section.TLabel").pack(
            side=tk.LEFT, padx=(0, 8))

        ttk.Checkbutton(algo_card, text="Сгладить скорость",
                        variable=self.smooth_speed_var,
                        style="Card.TCheckbutton").pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(algo_card, text="Сгладить ускорение",
                        variable=self.smooth_accel_var,
                        style="Card.TCheckbutton").pack(side=tk.LEFT, padx=4)
        self.cb_corridor = ttk.Checkbutton(
            algo_card, text="Показать коридор",
            variable=self.show_corridor_var,
            style="Card.TCheckbutton")
        self.cb_corridor.pack(side=tk.LEFT, padx=4)

        self.params_frame = ttk.LabelFrame(left_container, text=" Параметры алгоритма ",
                                           padding=12)
        self.params_frame.pack(fill='x', pady=(0, 8))

        self.params_container = ttk.Frame(self.params_frame, style="Card.TFrame")
        self.params_container.pack(fill='x', expand=True)
        self.show_default_params()

        self.figure_frame = ttk.Frame(left_container, style="Card.TFrame")
        self.figure_frame.pack(fill=tk.BOTH, expand=True)

        self.control_panel = ttk.Frame(main_split, style="Card.TFrame", width=400)
        self.control_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(12, 0))
        self.control_panel.pack_propagate(False)

        self.toolbar_frame = ttk.Frame(self.control_panel, style="Card.TFrame")

        self.plot_manager = PlotManager(self.figure_frame,
                                        toolbar_frame=self.toolbar_frame)
        self.plot_manager.set_status_callback(self.update_status)
        self.plot_manager.set_hover_callback(self.on_hover)
        self.plot_manager.set_selection_callback(self.on_selection)

        self.create_control_panel()

        self._update_corridor_checkbox_visibility()

    def _card_section(self, parent, title=None):
        wrap = ttk.Frame(parent, style="Card.TFrame", padding=(12, 10, 12, 10))
        if title:
            ttk.Label(wrap, text=title, style="Section.TLabel").pack(anchor='w')
        return wrap

    def _separator(self, parent):
        ttk.Separator(parent, orient='horizontal').pack(fill='x', pady=8)

    def create_control_panel(self):
        header = ttk.Frame(self.control_panel, style="Card.TFrame", padding=(14, 12, 14, 4))
        header.pack(fill='x')
        ttk.Label(header, text="Управление графиками",
                  style="Section.TLabel").pack(anchor='w')

        sec_cols = self._card_section(self.control_panel, "Столбцы графиков")
        sec_cols.pack(fill='x', padx=8, pady=(0, 6))

        row_top = ttk.Frame(sec_cols, style="Card.TFrame")
        row_top.pack(fill='x')
        ttk.Label(row_top, text="Верхний:", style="Card.TLabel",
                  width=10).pack(side=tk.LEFT)
        ttk.Button(row_top, text="Выбрать…",
                   command=lambda: self.select_columns('top'),
                   style="Secondary.TButton").pack(side=tk.LEFT, padx=6)
        self.lbl_top_selected = tk.Label(sec_cols, text="не выбрано",
                                         font=FONT_SMALL, bg=PANEL_BG, fg=FG_MUTED,
                                         wraplength=340, justify='left', anchor='w')
        self.lbl_top_selected.pack(fill='x', padx=(6, 0), pady=(4, 6))

        row_bot = ttk.Frame(sec_cols, style="Card.TFrame")
        row_bot.pack(fill='x')
        ttk.Label(row_bot, text="Нижний:", style="Card.TLabel",
                  width=10).pack(side=tk.LEFT)
        ttk.Button(row_bot, text="Выбрать…",
                   command=lambda: self.select_columns('bottom'),
                   style="Secondary.TButton").pack(side=tk.LEFT, padx=6)
        self.lbl_bottom_selected = tk.Label(sec_cols, text="не выбрано",
                                            font=FONT_SMALL, bg=PANEL_BG, fg=FG_MUTED,
                                            wraplength=340, justify='left', anchor='w')
        self.lbl_bottom_selected.pack(fill='x', padx=(6, 0), pady=(4, 4))

        self._separator(self.control_panel)

        row_btn = ttk.Frame(self.control_panel, style="Card.TFrame", padding=(14, 0, 14, 0))
        row_btn.pack(fill='x')
        ttk.Button(row_btn, text="✓  Применить",
                   command=self.apply_changes, style="Success.TButton").pack(
            side=tk.LEFT, padx=(0, 6))
        ttk.Button(row_btn, text="↺  Сбросить",
                   command=self.reset_selection, style="Warning.TButton").pack(
            side=tk.LEFT)

        self._separator(self.control_panel)

        sec_tools = self._card_section(self.control_panel, "Инструменты графика")
        sec_tools.pack(fill='x', padx=8, pady=(0, 6))
        self.toolbar_frame.pack(fill='x')

        self._separator(self.control_panel)

        sec_sel = self._card_section(self.control_panel)
        sec_sel.pack(fill='x', padx=8, pady=(0, 6))
        self.selection_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sec_sel, text="Режим выделения (вкл/выкл)",
                        variable=self.selection_mode_var,
                        command=self.toggle_selection_mode,
                        style="Card.TCheckbutton").pack(anchor='w')

        self._separator(self.control_panel)

        sec_hover = self._card_section(self.control_panel, "Значения в точке")
        sec_hover.pack(fill='x', padx=8, pady=(0, 6))

        hover_border = tk.Frame(sec_hover, bg=BORDER)
        hover_border.pack(fill=tk.X, expand=False)

        self.hover_label = tk.Label(hover_border,
                                    text="Наведите курсор на график",
                                    font=FONT_MONO,
                                    bg="#fbfcfe", fg=FG,
                                    justify='left', anchor='nw',
                                    wraplength=340,
                                    padx=10, pady=8)
        self.hover_label.pack(fill=tk.BOTH, expand=True)

        self._separator(self.control_panel)

        stat_header = ttk.Frame(self.control_panel, style="Card.TFrame",
                                padding=(14, 0, 14, 4))
        stat_header.pack(fill='x')
        ttk.Label(stat_header, text="Статистика выделенной области",
                  style="Section.TLabel").pack(anchor='w')

        stat_buttons = ttk.Frame(self.control_panel, style="Card.TFrame",
                                 padding=(14, 0, 14, 4))
        stat_buttons.pack(fill='x')
        ttk.Button(stat_buttons, text="В Excel",
                   command=self.export_selection_to_excel,
                   style="Primary.TButton").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(stat_buttons, text="Очистить",
                   command=self.clear_selection,
                   style="Danger.TButton").pack(side=tk.LEFT)

        stat_body = ttk.Frame(self.control_panel, style="Card.TFrame",
                              padding=(14, 0, 14, 12))
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
    def on_algorithm_selected(self, event=None):
        display = self.cb_algo.get()
        code = self.algorithm_display.get(display, "default")
        self.algorithm.set(code)
        self.on_algorithm_change()

    def _update_corridor_checkbox_visibility(self):
        is_default = (self.algorithm.get() == "default")
        if is_default:
            if not self.cb_corridor.winfo_ismapped():
                self.cb_corridor.pack(side=tk.LEFT, padx=4)
        else:
            self.cb_corridor.pack_forget()
            self.show_corridor_var.set(False)

    def toggle_selection_mode(self):
        enabled = self.selection_mode_var.get()
        self.plot_manager.set_selection_mode(enabled)

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

    def select_columns(self, target):
        if self.df_full is None:
            messagebox.showinfo("Информация", "Сначала загрузите данные.")
            return
        all_cols = [col for col in self.df_full.columns if col != self.time_col]
        if not all_cols:
            messagebox.showwarning("Предупреждение", "Нет доступных столбцов.")
            return
        useful = ['Уклон', 'ТЦ', 'ТМ', 'Скорость', 'ГР', 'Тяга', 'Тормоз',
                  'Сглаженная скорость', 'Скорость в м/с', 'Ускорение',
                  'Ускорение сглаженное', 'Скорость в коридоре']
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
                time_col, _ = find_columns(df_full)
                if time_col is None:
                    time_col = df_full.columns[0]
                self.time_col = time_col
                self.df_full = df_full
                self.top_columns = []
                self.bottom_columns = []
                self.default_top_columns = []
                self.default_bottom_columns = []
                self.selection_x1 = None
                self.selection_x2 = None
                self.lbl_top_selected.config(text="не выбрано", fg=FG_MUTED)
                self.lbl_bottom_selected.config(text="не выбрано", fg=FG_MUTED)
                self.status_var.set(
                    "Данные загружены. Нажмите 'Выполнить расчёт' для построения графиков.")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{str(e)}")
        else:
            self.status_var.set("Файл не выбран")

    # ------------------------------------------------------------------
    # Расчёт
    # ------------------------------------------------------------------
    def _smooth(self, values, algorithm, params):
        """
        Применяет выбранный алгоритм с заданными параметрами.
        params — словарь параметров для конкретной цели (speed / accel).
        """
        n = len(values)
        if algorithm == "default":
            return self.processor.smooth_default(
                values, n,
                corridor_percent=params['corridor'],
                window_trunc=params['window_trunc'],
                window_final=params['window_final'],
            )
        elif algorithm == "exponential":
            return self.processor.smooth_exponential(
                values, n, alpha=params['alpha'])
        elif algorithm == "kalman":
            return self.processor.smooth_kalman(
                values, n, q=params['q'], r=params['r'])
        elif algorithm == "median":
            return self.processor.smooth_median(
                values, n, window=params['median_window'])
        elif algorithm == "savgol":
            return self.processor.smooth_savgol(
                values, n,
                window=params['savgol_window'],
                order=params['savgol_order'])
        else:
            return self.processor.smooth_default(values, n)

    def calculate(self):
        if not self.file_path.get():
            messagebox.showerror("Ошибка", "Сначала выберите Excel-файл!")
            return
        try:
            self.status_var.set("Выполняется расчёт...")
            self.root.update()

            if self.df_full is None:
                df_full = pd.read_excel(self.file_path.get(), header=0)
                time_col, _ = find_columns(df_full)
                if time_col is None:
                    time_col = df_full.columns[0]
                self.time_col = time_col
                self.df_full = df_full

            df = self.df_full.copy()

            corridor_cols = [
                'Нижняя граница скорости', 'Верхняя граница скорости',
                'Нижняя граница ускорения', 'Верхняя граница ускорения'
            ]
            for c in corridor_cols:
                if c in df.columns:
                    df = df.drop(columns=[c])

            time = df[self.time_col].values

            speed_col = None
            for col in df.columns:
                if 'скорость' in col.lower() or 'speed' in col.lower():
                    speed_col = col
                    break
            if speed_col is None:
                raise ValueError("Не найден столбец со скоростью для расчёта.")

            V = df[speed_col].values
            if not pd.api.types.is_numeric_dtype(df[self.time_col]):
                df[self.time_col] = pd.to_numeric(df[self.time_col], errors='coerce')
                time = df[self.time_col].values

            df = df.dropna(subset=[self.time_col, speed_col])
            if len(V) < 5:
                raise ValueError(
                    f"Слишком мало данных ({len(V)} строк). Нужно минимум 5.")

            V_ms = V / 3.6
            accel_orig = calculate_acceleration(V_ms, time)

            smooth_speed = self.smooth_speed_var.get()
            smooth_accel = self.smooth_accel_var.get()
            is_default = (self.algorithm.get() == "default")
            show_corridor = self.show_corridor_var.get() and is_default

            # Собираем параметры для скорости
            params_speed = {
                'corridor':      self.corridor_percent_speed.get(),
                'window_trunc':  self.window_trunc_speed.get(),
                'window_final':  self.window_final_speed.get(),
                'alpha':         self.alpha_exp_speed.get(),
                'q':             self.kalman_q_speed.get(),
                'r':             self.kalman_r_speed.get(),
                'median_window': self.median_window_speed.get(),
                'savgol_window': self.savgol_window_speed.get(),
                'savgol_order':  self.savgol_order_speed.get(),
            }
            # Собираем параметры для ускорения
            params_accel = {
                'corridor':      self.corridor_percent_accel.get(),
                'window_trunc':  self.window_trunc_accel.get(),
                'window_final':  self.window_final_accel.get(),
                'alpha':         self.alpha_exp_accel.get(),
                'q':             self.kalman_q_accel.get(),
                'r':             self.kalman_r_accel.get(),
                'median_window': self.median_window_accel.get(),
                'savgol_window': self.savgol_window_accel.get(),
                'savgol_order':  self.savgol_order_accel.get(),
            }

            # ---- Сглаживание скорости ----
            if smooth_speed:
                smoothed_speed = self._smooth(V, self.algorithm.get(), params_speed)
                if is_default:
                    low_speed = self.processor.low_bound.copy()
                    high_speed = self.processor.high_bound.copy()
                else:
                    low_speed = high_speed = None

                smoothed_speed_ms = smoothed_speed / 3.6
                accel_from_smoothed = calculate_acceleration(smoothed_speed_ms, time)
                df['Сглаженная скорость'] = smoothed_speed
                df['Скорость в м/с'] = smoothed_speed_ms
                df['Ускорение'] = accel_from_smoothed
                current_accel = accel_from_smoothed

                if is_default and show_corridor and low_speed is not None:
                    df['Нижняя граница скорости'] = low_speed
                    df['Верхняя граница скорости'] = high_speed
            else:
                df['Скорость в м/с'] = V_ms
                df['Ускорение'] = accel_orig
                current_accel = accel_orig

            # ---- Сглаживание ускорения ----
            if smooth_accel:
                smoothed_accel = self._smooth(current_accel, self.algorithm.get(),
                                              params_accel)
                if is_default:
                    low_accel = self.processor.low_bound.copy()
                    high_accel = self.processor.high_bound.copy()
                else:
                    low_accel = high_accel = None

                df['Ускорение сглаженное'] = smoothed_accel

                if is_default and show_corridor and low_accel is not None:
                    df['Нижняя граница ускорения'] = low_accel
                    df['Верхняя граница ускорения'] = high_accel

            top_default = 'Сглаженная скорость' if smooth_speed else 'Скорость'
            bottom_default = 'Ускорение сглаженное' if smooth_accel else 'Ускорение'

            self.default_top_columns = [top_default]
            self.default_bottom_columns = [bottom_default]

            self.top_columns = [top_default]
            self.bottom_columns = [bottom_default]
            self.lbl_top_selected.config(text=top_default, fg=FG)
            self.lbl_bottom_selected.config(text=bottom_default, fg=FG)

            self.df_full = df
            self.apply_changes()

            self.status_var.set("Расчёт выполнен!")
            messagebox.showinfo("Успех", "Расчёт выполнен успешно!")

        except Exception as e:
            self.status_var.set("Ошибка!")
            messagebox.showerror("Ошибка", f"Произошла ошибка:\n{str(e)}")

    def apply_changes(self):
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
            show_corridor=self.show_corridor_var.get() and (self.algorithm.get() == "default")
        )
        self.plot_manager.show_plots()
        self.status_var.set("Графики обновлены")

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
                show_corridor=self.show_corridor_var.get() and (self.algorithm.get() == "default")
            )
            self.plot_manager.show_plots()
            self.status_var.set("Графики возвращены к исходному виду")
        else:
            self.top_columns = []
            self.bottom_columns = []
            self.lbl_top_selected.config(text="не выбрано", fg=FG_MUTED)
            self.lbl_bottom_selected.config(text="не выбрано", fg=FG_MUTED)
            self.status_var.set(
                "Выбор сброшен. Нажмите 'Выполнить расчёт' или выберите столбцы вручную.")

    # ------------------------------------------------------------------
    # Панель параметров: двухколоночная (Скорость | Ускорение)
    # ------------------------------------------------------------------
    def clear_params(self):
        for widget in self.params_container.winfo_children():
            widget.destroy()

    def _spinbox(self, parent, var, from_, to, increment, width):
        return ttk.Spinbox(parent, from_=from_, to=to, increment=increment,
                           width=width, textvariable=var, font=FONT_BASE)

    def _header_row(self, grid):
        ttk.Label(grid, text="СКОРОСТЬ", style="CardBold.TLabel").grid(
            row=0, column=0, sticky='w', padx=(0, 30), pady=(0, 6))
        ttk.Label(grid, text="УСКОРЕНИЕ", style="CardBold.TLabel").grid(
            row=0, column=1, sticky='w', padx=0, pady=(0, 6))

    def show_default_params(self):
        self.clear_params()

        grid = ttk.Frame(self.params_container, style="Card.TFrame")
        grid.pack(fill='x')
        self._header_row(grid)

        # --- Коридоры (строка 1) ---
        fr_s = ttk.Frame(grid, style="Card.TFrame")
        fr_s.grid(row=1, column=0, sticky='w', padx=(0, 30), pady=2)
        ttk.Label(fr_s, text="Коридор:", style="Card.TLabel").pack(side=tk.LEFT)
        self._spinbox(fr_s, self.corridor_percent_speed,
                      0.01, 10.0, 0.01, 6).pack(side=tk.LEFT, padx=4)
        ttk.Label(fr_s, text="%", style="Card.TLabel").pack(side=tk.LEFT)

        fr_a = ttk.Frame(grid, style="Card.TFrame")
        fr_a.grid(row=1, column=1, sticky='w', pady=2)
        ttk.Label(fr_a, text="Коридор:", style="Card.TLabel").pack(side=tk.LEFT)
        self._spinbox(fr_a, self.corridor_percent_accel,
                      0.01, 10.0, 0.01, 6).pack(side=tk.LEFT, padx=4)
        ttk.Label(fr_a, text="%", style="Card.TLabel").pack(side=tk.LEFT)

        # --- Окно усечённого среднего (строка 2) ---
        fr_s2 = ttk.Frame(grid, style="Card.TFrame")
        fr_s2.grid(row=2, column=0, sticky='w', padx=(0, 30), pady=2)
        ttk.Label(fr_s2, text="Окно усеч. среднего:", style="Card.TLabel").pack(side=tk.LEFT)
        self._spinbox(fr_s2, self.window_trunc_speed,
                      3, 101, 2, 5).pack(side=tk.LEFT, padx=4)

        fr_a2 = ttk.Frame(grid, style="Card.TFrame")
        fr_a2.grid(row=2, column=1, sticky='w', pady=2)
        ttk.Label(fr_a2, text="Окно усеч. среднего:", style="Card.TLabel").pack(side=tk.LEFT)
        self._spinbox(fr_a2, self.window_trunc_accel,
                      3, 101, 2, 5).pack(side=tk.LEFT, padx=4)

        # --- Окно финального среднего (строка 3) ---
        fr_s3 = ttk.Frame(grid, style="Card.TFrame")
        fr_s3.grid(row=3, column=0, sticky='w', padx=(0, 30), pady=2)
        ttk.Label(fr_s3, text="Окно финального среднего:", style="Card.TLabel").pack(side=tk.LEFT)
        self._spinbox(fr_s3, self.window_final_speed,
                      3, 201, 2, 5).pack(side=tk.LEFT, padx=4)

        fr_a3 = ttk.Frame(grid, style="Card.TFrame")
        fr_a3.grid(row=3, column=1, sticky='w', pady=2)
        ttk.Label(fr_a3, text="Окно финального среднего:", style="Card.TLabel").pack(side=tk.LEFT)
        self._spinbox(fr_a3, self.window_final_accel,
                      3, 201, 2, 5).pack(side=tk.LEFT, padx=4)

    def show_exponential_params(self):
        self.clear_params()
        grid = ttk.Frame(self.params_container, style="Card.TFrame")
        grid.pack(fill='x')
        self._header_row(grid)

        fr_s = ttk.Frame(grid, style="Card.TFrame")
        fr_s.grid(row=1, column=0, sticky='w', padx=(0, 30), pady=2)
        ttk.Label(fr_s, text="Alpha (α):", style="Card.TLabel").pack(side=tk.LEFT)
        self._spinbox(fr_s, self.alpha_exp_speed,
                      0.01, 1.0, 0.01, 6).pack(side=tk.LEFT, padx=4)

        fr_a = ttk.Frame(grid, style="Card.TFrame")
        fr_a.grid(row=1, column=1, sticky='w', pady=2)
        ttk.Label(fr_a, text="Alpha (α):", style="Card.TLabel").pack(side=tk.LEFT)
        self._spinbox(fr_a, self.alpha_exp_accel,
                      0.01, 1.0, 0.01, 6).pack(side=tk.LEFT, padx=4)

        ttk.Label(self.params_container,
                  text="(0.01–1.0) — чем больше, тем сильнее доверяем новым значениям и слабее сглаживание",
                  style="Muted.TLabel", background=PANEL_BG).pack(anchor='w', pady=(6, 0))

    def show_kalman_params(self):
        self.clear_params()
        grid = ttk.Frame(self.params_container, style="Card.TFrame")
        grid.pack(fill='x')
        self._header_row(grid)

        fr_s = ttk.Frame(grid, style="Card.TFrame")
        fr_s.grid(row=1, column=0, sticky='w', padx=(0, 30), pady=2)
        ttk.Label(fr_s, text="Q:", style="Card.TLabel").pack(side=tk.LEFT)
        self._spinbox(fr_s, self.kalman_q_speed,
                      0.0001, 1.0, 0.0001, 8).pack(side=tk.LEFT, padx=4)
        ttk.Label(fr_s, text="R:", style="Card.TLabel").pack(side=tk.LEFT, padx=(10, 0))
        self._spinbox(fr_s, self.kalman_r_speed,
                      0.0001, 1.0, 0.0001, 8).pack(side=tk.LEFT, padx=4)

        fr_a = ttk.Frame(grid, style="Card.TFrame")
        fr_a.grid(row=1, column=1, sticky='w', pady=2)
        ttk.Label(fr_a, text="Q:", style="Card.TLabel").pack(side=tk.LEFT)
        self._spinbox(fr_a, self.kalman_q_accel,
                      0.0001, 1.0, 0.0001, 8).pack(side=tk.LEFT, padx=4)
        ttk.Label(fr_a, text="R:", style="Card.TLabel").pack(side=tk.LEFT, padx=(10, 0))
        self._spinbox(fr_a, self.kalman_r_accel,
                      0.0001, 1.0, 0.0001, 8).pack(side=tk.LEFT, padx=4)

        ttk.Label(self.params_container,
                  text="Q — динамика системы, R — шум измерений. Меньше Q и больше R → сильнее сглаживание",
                  style="Muted.TLabel", background=PANEL_BG).pack(anchor='w', pady=(6, 0))

    def show_median_params(self):
        self.clear_params()
        grid = ttk.Frame(self.params_container, style="Card.TFrame")
        grid.pack(fill='x')
        self._header_row(grid)

        fr_s = ttk.Frame(grid, style="Card.TFrame")
        fr_s.grid(row=1, column=0, sticky='w', padx=(0, 30), pady=2)
        ttk.Label(fr_s, text="Размер окна:", style="Card.TLabel").pack(side=tk.LEFT)
        self._spinbox(fr_s, self.median_window_speed,
                      3, 21, 2, 6).pack(side=tk.LEFT, padx=4)

        fr_a = ttk.Frame(grid, style="Card.TFrame")
        fr_a.grid(row=1, column=1, sticky='w', pady=2)
        ttk.Label(fr_a, text="Размер окна:", style="Card.TLabel").pack(side=tk.LEFT)
        self._spinbox(fr_a, self.median_window_accel,
                      3, 21, 2, 6).pack(side=tk.LEFT, padx=4)

        ttk.Label(self.params_container,
                  text="(нечётное, 3–21) — медиана точек окна; убирает одиночные выбросы",
                  style="Muted.TLabel", background=PANEL_BG).pack(anchor='w', pady=(6, 0))

    def show_savgol_params(self):
        self.clear_params()
        grid = ttk.Frame(self.params_container, style="Card.TFrame")
        grid.pack(fill='x')
        self._header_row(grid)

        fr_s = ttk.Frame(grid, style="Card.TFrame")
        fr_s.grid(row=1, column=0, sticky='w', padx=(0, 30), pady=2)
        ttk.Label(fr_s, text="Окно:", style="Card.TLabel").pack(side=tk.LEFT)
        self._spinbox(fr_s, self.savgol_window_speed,
                      5, 31, 2, 6).pack(side=tk.LEFT, padx=4)
        ttk.Label(fr_s, text="Степень:", style="Card.TLabel").pack(side=tk.LEFT, padx=(10, 0))
        self._spinbox(fr_s, self.savgol_order_speed,
                      1, 5, 1, 4).pack(side=tk.LEFT, padx=4)

        fr_a = ttk.Frame(grid, style="Card.TFrame")
        fr_a.grid(row=1, column=1, sticky='w', pady=2)
        ttk.Label(fr_a, text="Окно:", style="Card.TLabel").pack(side=tk.LEFT)
        self._spinbox(fr_a, self.savgol_window_accel,
                      5, 31, 2, 6).pack(side=tk.LEFT, padx=4)
        ttk.Label(fr_a, text="Степень:", style="Card.TLabel").pack(side=tk.LEFT, padx=(10, 0))
        self._spinbox(fr_a, self.savgol_order_accel,
                      1, 5, 1, 4).pack(side=tk.LEFT, padx=4)

        ttk.Label(self.params_container,
                  text="(окно нечётное, > степени) — полиномиальная аппроксимация в окне; хорошо сохраняет форму кривой",
                  style="Muted.TLabel", background=PANEL_BG).pack(anchor='w', pady=(6, 0))

    def on_algorithm_change(self, *args):
        algo = self.algorithm.get()
        if algo == "default":
            self.show_default_params()
        elif algo == "exponential":
            self.show_exponential_params()
        elif algo == "kalman":
            self.show_kalman_params()
        elif algo == "median":
            self.show_median_params()
        elif algo == "savgol":
            self.show_savgol_params()
        self._update_corridor_checkbox_visibility()


if __name__ == "__main__":
    root = tk.Tk()
    app = SpeedAnalyzerApp(root)
    root.mainloop()