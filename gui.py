import tkinter as tk
from tkinter import filedialog, messagebox, Radiobutton, StringVar, Frame, Label, Spinbox, DoubleVar, IntVar, Button, Toplevel, Checkbutton, BooleanVar, Text, Scrollbar
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
        self.dialog.transient(parent)
        self.dialog.grab_set()

        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        dialog_width = 400
        dialog_height = 450
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        self.dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        self.create_widgets()
        self.dialog.wait_window()

    def create_widgets(self):
        filter_frame = tk.Frame(self.dialog)
        filter_frame.pack(pady=5, padx=10, fill='x')

        cb_show_all = Checkbutton(filter_frame, text="Показать все столбцы",
                                  variable=self.show_all, command=self.update_list)
        cb_show_all.pack(anchor='w')

        canvas_frame = tk.Frame(self.dialog)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        canvas = tk.Canvas(canvas_frame)
        scrollbar = tk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.scrollable_frame = scrollable_frame

        btn_frame = tk.Frame(self.dialog)
        btn_frame.pack(pady=10)

        btn_ok = Button(btn_frame, text="OK", command=self.on_ok, width=10)
        btn_ok.pack(side=tk.LEFT, padx=5)

        btn_cancel = Button(btn_frame, text="Отмена", command=self.on_cancel, width=10)
        btn_cancel.pack(side=tk.LEFT, padx=5)

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
            cb = Checkbutton(self.scrollable_frame, text=col, variable=var, anchor='w')
            cb.pack(fill='x', padx=5, pady=2)
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

        self.file_path = tk.StringVar()
        self.df_full = None
        self.time_col = None
        self.top_columns = []
        self.bottom_columns = []

        self.corridor_percent_speed = DoubleVar(value=0.1)
        self.corridor_percent_accel = DoubleVar(value=0.1)

        self.window_trunc_mean = IntVar(value=11)
        self.window_final_mean = IntVar(value=21)

        self.alpha_exp = DoubleVar(value=0.3)
        self.kalman_q = DoubleVar(value=0.01)
        self.kalman_r = DoubleVar(value=0.1)
        self.median_window = IntVar(value=5)
        self.savgol_window = IntVar(value=11)
        self.savgol_order = IntVar(value=3)

        self.algorithm = StringVar(value="default")
        self.algorithm.trace_add('write', self.on_algorithm_change)

        self.smooth_speed_var = BooleanVar(value=True)
        self.smooth_accel_var = BooleanVar(value=False)
        self.show_corridor_var = BooleanVar(value=False)

        self.processor = SpeedProcessor()

        self.create_widgets()

    def create_widgets(self):
        top_frame = tk.Frame(self.root)
        top_frame.pack(pady=10, padx=10, fill='x')

        btn_select = tk.Button(top_frame, text="Выбрать Excel-файл",
                               command=self.select_file, font=('Arial', 12),
                               bg='#4CAF50', fg='white', padx=20, pady=5)
        btn_select.pack(side=tk.LEFT, padx=5)

        self.lbl_path = tk.Label(top_frame, text="Файл не выбран",
                                 font=('Arial', 10), fg='gray')
        self.lbl_path.pack(side=tk.LEFT, padx=10)

        btn_calc = tk.Button(top_frame, text="Выполнить расчёт",
                             command=self.calculate, font=('Arial', 12),
                             bg='#2196F3', fg='white', padx=20, pady=5)
        btn_calc.pack(side=tk.RIGHT, padx=5)

        algo_frame = Frame(self.root)
        algo_frame.pack(pady=5, padx=10, fill='x')

        lbl_algo = tk.Label(algo_frame, text="Выберите алгоритм сглаживания:",
                            font=('Arial', 10, 'bold'))
        lbl_algo.pack(side=tk.LEFT, padx=5)

        algorithms = [
            ("Стандартный (двойное сглаживание)", "default"),
            ("Экспоненциальное сглаживание", "exponential"),
            ("Фильтр Калмана", "kalman"),
            ("Медианный фильтр", "median"),
            ("Фильтр Савицкого – Голея", "savgol")
        ]

        for text, value in algorithms:
            rb = Radiobutton(algo_frame, text=text,
                             variable=self.algorithm, value=value,
                             font=('Arial', 9))
            rb.pack(side=tk.LEFT, padx=5)

        target_frame = Frame(self.root)
        target_frame.pack(pady=5, padx=10, fill='x')

        lbl_target = tk.Label(target_frame, text="Опции:", font=('Arial', 10, 'bold'))
        lbl_target.pack(side=tk.LEFT, padx=5)

        cb_speed = Checkbutton(target_frame, text="Сгладить скорость",
                               variable=self.smooth_speed_var,
                               font=('Arial', 9))
        cb_speed.pack(side=tk.LEFT, padx=5)

        cb_accel = Checkbutton(target_frame, text="Сгладить ускорение",
                               variable=self.smooth_accel_var,
                               font=('Arial', 9))
        cb_accel.pack(side=tk.LEFT, padx=5)

        # Чекбокс коридора — создаём, но показываем только для стандартного алгоритма
        self.cb_corridor = Checkbutton(target_frame, text="Показать коридор",
                                       variable=self.show_corridor_var,
                                       font=('Arial', 9))
        self.cb_corridor.pack(side=tk.LEFT, padx=5)

        self.status_var = tk.StringVar()
        self.status_var.set("Готов к работе")
        status_bar = tk.Label(self.root, textvariable=self.status_var,
                              relief=tk.SUNKEN, anchor=tk.W, font=('Arial', 9))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.params_frame = Frame(self.root, relief=tk.GROOVE, bd=2)
        self.params_frame.pack(pady=5, padx=10, fill='x')

        lbl_params = tk.Label(self.params_frame, text="Параметры алгоритма:",
                              font=('Arial', 10, 'bold'))
        lbl_params.pack(side=tk.LEFT, padx=5)

        self.params_container = Frame(self.params_frame)
        self.params_container.pack(side=tk.LEFT, padx=10, fill='x', expand=True)
        self.show_default_params()

        main_container = Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.figure_frame = Frame(main_container)
        self.figure_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.plot_manager = PlotManager(self.figure_frame)
        self.plot_manager.set_status_callback(self.update_status)
        self.plot_manager.set_hover_callback(self.on_hover)
        self.plot_manager.set_selection_callback(self.on_selection)

        self.control_panel = Frame(main_container, width=300, relief=tk.GROOVE, bd=2)
        self.control_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        self.control_panel.pack_propagate(False)

        self.create_control_panel()

        # --- Управление видимостью чекбокса «Показать коридор» ---
        self._update_corridor_checkbox_visibility()

    def _update_corridor_checkbox_visibility(self):
        """Показывает чекбокс коридора только для стандартного алгоритма."""
        is_default = (self.algorithm.get() == "default")
        if is_default:
            if not self.cb_corridor.winfo_ismapped():
                self.cb_corridor.pack(side=tk.LEFT, padx=5)
        else:
            self.cb_corridor.pack_forget()
            # При переключении на другой алгоритм сбрасываем галочку
            self.show_corridor_var.set(False)

    def create_control_panel(self):
        lbl_title = tk.Label(self.control_panel, text="Выбор столбцов для графиков",
                             font=('Arial', 11, 'bold'), pady=10)
        lbl_title.pack()

        tk.Frame(self.control_panel, height=2, bd=1, relief=tk.SUNKEN).pack(
            fill=tk.X, padx=10, pady=5)

        lbl_top = tk.Label(self.control_panel, text="Верхний график:",
                           font=('Arial', 10, 'bold'), pady=5)
        lbl_top.pack(anchor=tk.W, padx=15)

        self.btn_top = Button(self.control_panel, text="Выбрать столбцы...",
                              command=lambda: self.select_columns('top'),
                              font=('Arial', 10), bg='#E3F2FD')
        self.btn_top.pack(fill=tk.X, padx=15, pady=5)

        self.lbl_top_selected = Label(self.control_panel, text="не выбрано",
                                      font=('Arial', 8), fg='gray', wraplength=270)
        self.lbl_top_selected.pack(anchor=tk.W, padx=15, pady=2)

        tk.Frame(self.control_panel, height=2, bd=1, relief=tk.SUNKEN).pack(
            fill=tk.X, padx=10, pady=10)

        lbl_bottom = tk.Label(self.control_panel, text="Нижний график:",
                              font=('Arial', 10, 'bold'), pady=5)
        lbl_bottom.pack(anchor=tk.W, padx=15)

        self.btn_bottom = Button(self.control_panel, text="Выбрать столбцы...",
                                 command=lambda: self.select_columns('bottom'),
                                 font=('Arial', 10), bg='#E3F2FD')
        self.btn_bottom.pack(fill=tk.X, padx=15, pady=5)

        self.lbl_bottom_selected = Label(self.control_panel, text="не выбрано",
                                         font=('Arial', 8), fg='gray', wraplength=270)
        self.lbl_bottom_selected.pack(anchor=tk.W, padx=15, pady=2)

        tk.Frame(self.control_panel, height=2, bd=1, relief=tk.SUNKEN).pack(
            fill=tk.X, padx=10, pady=10)

        btn_frame = Frame(self.control_panel)
        btn_frame.pack(pady=5)

        btn_apply = Button(btn_frame, text="Применить выбор",
                           command=self.apply_changes, font=('Arial', 10),
                           bg='#4CAF50', fg='white', padx=15, pady=5)
        btn_apply.pack(side=tk.LEFT, padx=5)

        btn_reset = Button(btn_frame, text="Сбросить",
                           command=self.reset_selection, font=('Arial', 10),
                           bg='#FF9800', fg='white', padx=15, pady=5)
        btn_reset.pack(side=tk.LEFT, padx=5)

        tk.Frame(self.control_panel, height=2, bd=1, relief=tk.SUNKEN).pack(
            fill=tk.X, padx=10, pady=10)
        self.selection_mode_var = BooleanVar(value=False)
        cb_selection = Checkbutton(
            self.control_panel,
            text="Режим выделения (вкл/выкл)",
            variable=self.selection_mode_var,
            command=self.toggle_selection_mode,
            font=('Arial', 10)
        )
        cb_selection.pack(anchor=tk.W, padx=15, pady=5)

        tk.Frame(self.control_panel, height=2, bd=1, relief=tk.SUNKEN).pack(
            fill=tk.X, padx=10, pady=10)
        lbl_selection_title = Label(self.control_panel,
                                    text="Статистика выделенной области",
                                    font=('Arial', 10, 'bold'))
        lbl_selection_title.pack(anchor=tk.W, padx=15, pady=5)

        btn_clear_selection = Button(self.control_panel, text="Очистить выделение",
                                     command=self.clear_selection, font=('Arial', 10),
                                     bg='#f44336', fg='white', padx=10, pady=3)
        btn_clear_selection.pack(anchor=tk.W, padx=15, pady=5)

        self.selection_text = Text(self.control_panel, height=12, width=35,
                                   font=('Courier', 8), relief=tk.SUNKEN, bd=1)
        self.selection_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        scrollbar = Scrollbar(self.control_panel, command=self.selection_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 15))
        self.selection_text.config(yscrollcommand=scrollbar.set)

        tk.Frame(self.control_panel, height=2, bd=1, relief=tk.SUNKEN).pack(
            fill=tk.X, padx=10, pady=10)
        lbl_hover_title = Label(self.control_panel, text="Значения в точке:",
                                font=('Arial', 9, 'bold'))
        lbl_hover_title.pack(anchor=tk.W, padx=15)

        self.hover_label = Label(self.control_panel, text="Наведите курсор на график",
                                 font=('Arial', 8), fg='gray', justify=tk.LEFT,
                                 wraplength=280, anchor='w')
        self.hover_label.pack(anchor=tk.W, padx=15, pady=5, fill=tk.X)

        self.lbl_info = Label(self.control_panel, text="", font=('Arial', 8), fg='gray')
        self.lbl_info.pack(pady=5)

    def toggle_selection_mode(self):
        enabled = self.selection_mode_var.get()
        self.plot_manager.set_selection_mode(enabled)

    def on_selection(self, x1, x2, stats):
        if x1 is None and stats is None:
            self.selection_text.delete(1.0, tk.END)
            self.selection_text.insert(tk.END, "Выделение очищено")
            return
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
        self.selection_text.delete(1.0, tk.END)
        self.selection_text.insert(tk.END, "Выделение очищено")
        self.status_var.set("Выделение очищено")

    def on_hover(self, time, data_dict):
        if time is None or not data_dict:
            self.hover_label.config(text="Наведите курсор на график")
            return
        lines = []
        for col, value in sorted(data_dict.items()):
            if value is not None and np.isfinite(value):
                unit = self.plot_manager.get_unit(col)
                if unit:
                    lines.append(f"{col} ({unit}): {value:.3f}")
                else:
                    lines.append(f"{col}: {value:.3f}")
        if lines:
            text = f"t = {time:.2f} с\n" + "\n".join(lines)
            self.hover_label.config(text=text)
        else:
            self.hover_label.config(text=f"t = {time:.2f} с\n(нет данных)")

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
        useful = ['Уклон', 'ТЦ', 'ТМ', 'скорость', 'ГР', 'тяга', 'тормоз',
                  'Сглаженная скорость (км/ч)', 'Скорость в м/с', 'Ускорение (м/с²)',
                  'Ускорение сглаженное (м/с²)', 'Скорость в коридоре (км/ч)',
                  'Нижняя граница (км/ч)', 'Верхняя граница (км/ч)',
                  'Нижняя граница ускорения (м/с²)', 'Верхняя граница ускорения (м/с²)']
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
        if selected:
            self.apply_changes()

    def select_file(self):
        filename = filedialog.askopenfilename(
            title="Выберите Excel-файл с данными",
            filetypes=[("Excel files", "*.xlsx *.xls")]
        )
        if filename:
            self.file_path.set(filename)
            self.lbl_path.config(text=os.path.basename(filename), fg='black')
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
                self.lbl_top_selected.config(text="не выбрано")
                self.lbl_bottom_selected.config(text="не выбрано")
                self.status_var.set(
                    "Данные загружены. Нажмите 'Выполнить расчёт' для построения графиков.")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{str(e)}")
        else:
            self.status_var.set("Файл не выбран")

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

            # Убираем столбцы коридоров из предыдущих расчётов — они
            # заполняются только при стандартном алгоритме.
            corridor_cols = [
                'Нижняя граница (км/ч)', 'Верхняя граница (км/ч)',
                'Нижняя граница ускорения (м/с²)', 'Верхняя граница ускорения (м/с²)'
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

            self.processor.set_params(
                corridor_percent_speed=self.corridor_percent_speed.get(),
                corridor_percent_accel=self.corridor_percent_accel.get(),
                window_trunc_mean=self.window_trunc_mean.get(),
                window_final_mean=self.window_final_mean.get(),
                alpha_exp=self.alpha_exp.get(),
                kalman_q=self.kalman_q.get(),
                kalman_r=self.kalman_r.get(),
                median_window=self.median_window.get(),
                savgol_window=self.savgol_window.get(),
                savgol_order=self.savgol_order.get()
            )

            V_ms = V / 3.6
            accel_orig = calculate_acceleration(V_ms, time)

            smooth_speed = self.smooth_speed_var.get()
            smooth_accel = self.smooth_accel_var.get()
            show_corridor = self.show_corridor_var.get() and (self.algorithm.get() == "default")
            is_default = (self.algorithm.get() == "default")

            # --- Сглаживание скорости ---
            if smooth_speed:
                if is_default:
                    smoothed_speed = self.processor.smooth_default(
                        V, len(V),
                        corridor_percent=self.corridor_percent_speed.get()
                    )
                    low_speed = self.processor.low_bound.copy()
                    high_speed = self.processor.high_bound.copy()
                else:
                    smoothed_speed = self._apply_smoothing(V, len(V), self.algorithm.get())
                    low_speed = high_speed = None

                smoothed_speed_ms = smoothed_speed / 3.6
                accel_from_smoothed = calculate_acceleration(smoothed_speed_ms, time)
                df['Сглаженная скорость (км/ч)'] = smoothed_speed
                df['Скорость в м/с'] = smoothed_speed_ms
                df['Ускорение (м/с²)'] = accel_from_smoothed
                current_accel = accel_from_smoothed

                if is_default and show_corridor and low_speed is not None:
                    df['Нижняя граница (км/ч)'] = low_speed
                    df['Верхняя граница (км/ч)'] = high_speed
            else:
                df['Скорость в м/с'] = V_ms
                df['Ускорение (м/с²)'] = accel_orig
                current_accel = accel_orig

            # --- Сглаживание ускорения ---
            if smooth_accel:
                if is_default:
                    smoothed_accel = self.processor.smooth_default(
                        current_accel, len(current_accel),
                        corridor_percent=self.corridor_percent_accel.get()
                    )
                    low_accel = self.processor.low_bound.copy()
                    high_accel = self.processor.high_bound.copy()
                else:
                    smoothed_accel = self._apply_smoothing(
                        current_accel, len(current_accel), self.algorithm.get())
                    low_accel = high_accel = None

                df['Ускорение сглаженное (м/с²)'] = smoothed_accel

                if is_default and show_corridor and low_accel is not None:
                    df['Нижняя граница ускорения (м/с²)'] = low_accel
                    df['Верхняя граница ускорения (м/с²)'] = high_accel

            top_default = 'Сглаженная скорость (км/ч)' if smooth_speed else 'скорость'
            bottom_default = ('Ускорение сглаженное (м/с²)'
                              if smooth_accel else 'Ускорение (м/с²)')

            self.top_columns = [top_default]
            self.bottom_columns = [bottom_default]
            self.lbl_top_selected.config(text=top_default)
            self.lbl_bottom_selected.config(text=bottom_default)

            self.df_full = df
            self.apply_changes()

            self.status_var.set("Расчёт выполнен!")
            messagebox.showinfo("Успех", "Расчёт выполнен успешно!")

        except Exception as e:
            self.status_var.set("Ошибка!")
            messagebox.showerror("Ошибка", f"Произошла ошибка:\n{str(e)}")

    def _apply_smoothing(self, arr, n, algorithm):
        if algorithm == "default":
            return self.processor.smooth_default(arr, n)
        elif algorithm == "exponential":
            return self.processor.smooth_exponential(arr, n)
        elif algorithm == "kalman":
            return self.processor.smooth_kalman(arr, n)
        elif algorithm == "median":
            return self.processor.smooth_median(arr, n)
        elif algorithm == "savgol":
            return self.processor.smooth_savgol(arr, n)
        else:
            return self.processor.smooth_default(arr, n)

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
        self.top_columns = []
        self.bottom_columns = []
        self.lbl_top_selected.config(text="не выбрано")
        self.lbl_bottom_selected.config(text="не выбрано")
        if self.df_full is not None:
            self.status_var.set(
                "Выбор сброшен. Нажмите 'Выполнить расчёт' или выберите столбцы вручную.")
        else:
            self.status_var.set("Выбор сброшен.")

    # ---- Параметры алгоритмов ----
    def clear_params(self):
        for widget in self.params_container.winfo_children():
            widget.destroy()

    def show_default_params(self):
        self.clear_params()

        row1 = tk.Frame(self.params_container)
        row1.pack(side=tk.TOP, fill='x', anchor='w')

        lbl_speed = tk.Label(row1, text="Коридор скорости:", font=('Arial', 9))
        lbl_speed.pack(side=tk.LEFT, padx=2)
        spin_speed = Spinbox(row1, from_=0.01, to=10.0,
                             increment=0.01, width=6,
                             textvariable=self.corridor_percent_speed,
                             font=('Arial', 9))
        spin_speed.pack(side=tk.LEFT, padx=2)
        tk.Label(row1, text="%", font=('Arial', 9)).pack(side=tk.LEFT)

        lbl_accel = tk.Label(row1, text="   Коридор ускорения:", font=('Arial', 9))
        lbl_accel.pack(side=tk.LEFT, padx=2)
        spin_accel = Spinbox(row1, from_=0.01, to=10.0,
                             increment=0.01, width=6,
                             textvariable=self.corridor_percent_accel,
                             font=('Arial', 9))
        spin_accel.pack(side=tk.LEFT, padx=2)
        tk.Label(row1, text="%", font=('Arial', 9)).pack(side=tk.LEFT)

        row2 = tk.Frame(self.params_container)
        row2.pack(side=tk.TOP, fill='x', anchor='w', pady=(5, 0))

        lbl_w1 = tk.Label(row2, text="Окно усечённого среднего:",
                          font=('Arial', 9))
        lbl_w1.pack(side=tk.LEFT, padx=2)
        spin_w1 = Spinbox(row2, from_=3, to=101,
                          increment=2, width=5,
                          textvariable=self.window_trunc_mean,
                          font=('Arial', 9))
        spin_w1.pack(side=tk.LEFT, padx=2)
        lbl_hint1 = tk.Label(
            row2,
            text="(нечётное, ≥3) — в окне отбрасываются макс. и мин., остальные усредняются",
            font=('Arial', 8), fg='gray')
        lbl_hint1.pack(side=tk.LEFT, padx=(2, 15))

        lbl_w2 = tk.Label(row2, text="Окно финального среднего:",
                          font=('Arial', 9))
        lbl_w2.pack(side=tk.LEFT, padx=2)
        spin_w2 = Spinbox(row2, from_=3, to=201,
                          increment=2, width=5,
                          textvariable=self.window_final_mean,
                          font=('Arial', 9))
        spin_w2.pack(side=tk.LEFT, padx=2)
        lbl_hint2 = tk.Label(
            row2,
            text="(нечётное, ≥3) — простое среднее всех точек в окне",
            font=('Arial', 8), fg='gray')
        lbl_hint2.pack(side=tk.LEFT, padx=2)

    def show_exponential_params(self):
        self.clear_params()
        lbl = tk.Label(self.params_container, text="Alpha (α):", font=('Arial', 9))
        lbl.pack(side=tk.LEFT, padx=2)
        spin = Spinbox(self.params_container, from_=0.01, to=1.0,
                       increment=0.01, width=6,
                       textvariable=self.alpha_exp, font=('Arial', 9))
        spin.pack(side=tk.LEFT, padx=2)
        lbl_info = tk.Label(
            self.params_container,
            text="(0.01–1.0) — коэффициент сглаживания: чем больше, тем сильнее "
                 "доверяем новым значениям и слабее сглаживание",
            font=('Arial', 8), fg='gray')
        lbl_info.pack(side=tk.LEFT, padx=5)

    def show_kalman_params(self):
        self.clear_params()
        lbl_q = tk.Label(self.params_container, text="Q (шум процесса):",
                         font=('Arial', 9))
        lbl_q.pack(side=tk.LEFT, padx=2)
        spin_q = Spinbox(self.params_container, from_=0.0001, to=1.0,
                         increment=0.0001, width=8,
                         textvariable=self.kalman_q, font=('Arial', 9))
        spin_q.pack(side=tk.LEFT, padx=2)
        lbl_r = tk.Label(self.params_container, text="R (шум измерения):",
                         font=('Arial', 9))
        lbl_r.pack(side=tk.LEFT, padx=5)
        spin_r = Spinbox(self.params_container, from_=0.0001, to=1.0,
                         increment=0.0001, width=8,
                         textvariable=self.kalman_r, font=('Arial', 9))
        spin_r.pack(side=tk.LEFT, padx=2)
        lbl_info = tk.Label(
            self.params_container,
            text="(Q — насколько быстро меняется система; R — насколько шумные "
                 "измерения). Чем меньше Q и больше R, тем сильнее сглаживание",
            font=('Arial', 8), fg='gray')
        lbl_info.pack(side=tk.LEFT, padx=5)

    def show_median_params(self):
        self.clear_params()
        lbl = tk.Label(self.params_container, text="Размер окна:", font=('Arial', 9))
        lbl.pack(side=tk.LEFT, padx=2)
        spin = Spinbox(self.params_container, from_=3, to=21,
                       increment=2, width=6,
                       textvariable=self.median_window, font=('Arial', 9))
        spin.pack(side=tk.LEFT, padx=2)
        lbl_info = tk.Label(
            self.params_container,
            text="(нечётное, 3–21) — берётся медиана всех точек окна; "
                 "хорошо убирает одиночные выбросы",
            font=('Arial', 8), fg='gray')
        lbl_info.pack(side=tk.LEFT, padx=5)

    def show_savgol_params(self):
        self.clear_params()
        lbl_w = tk.Label(self.params_container, text="Размер окна:", font=('Arial', 9))
        lbl_w.pack(side=tk.LEFT, padx=2)
        spin_w = Spinbox(self.params_container, from_=5, to=31,
                         increment=2, width=6,
                         textvariable=self.savgol_window, font=('Arial', 9))
        spin_w.pack(side=tk.LEFT, padx=2)
        lbl_o = tk.Label(self.params_container, text="Степень:", font=('Arial', 9))
        lbl_o.pack(side=tk.LEFT, padx=5)
        spin_o = Spinbox(self.params_container, from_=1, to=5,
                         increment=1, width=4,
                         textvariable=self.savgol_order, font=('Arial', 9))
        spin_o.pack(side=tk.LEFT, padx=2)
        lbl_info = tk.Label(
            self.params_container,
            text="(окно нечётное, > степени) — аппроксимация полиномом заданной "
                 "степени внутри окна; хорошо сохраняет форму кривой",
            font=('Arial', 8), fg='gray')
        lbl_info.pack(side=tk.LEFT, padx=5)

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
        # Спрятать/показать чекбокс «Показать коридор»
        self._update_corridor_checkbox_visibility()


if __name__ == "__main__":
    root = tk.Tk()
    app = SpeedAnalyzerApp(root)
    root.mainloop()