import tkinter as tk
from tkinter import filedialog, messagebox, Radiobutton, StringVar, Frame, Label, Spinbox, DoubleVar, IntVar, Button, Toplevel, Checkbutton, BooleanVar, Text, Scrollbar
import pandas as pd
import numpy as np
import os
import sys
import io

from processing import SpeedProcessor
from plotting import PlotManager
from utils import find_columns

# Настройка кодировки
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


class ColumnSelectorDialog:
    """Диалог выбора столбцов с чекбоксами"""
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
        
        # Центрируем диалог относительно родителя
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
        
        # Параметры алгоритмов
        self.corridor_percent = DoubleVar(value=0.1)
        self.alpha_exp = DoubleVar(value=0.3)
        self.kalman_q = DoubleVar(value=0.01)
        self.kalman_r = DoubleVar(value=0.1)
        self.median_window = IntVar(value=5)
        self.savgol_window = IntVar(value=11)
        self.savgol_order = IntVar(value=3)
        
        self.algorithm = StringVar(value="default")
        self.algorithm.trace_add('write', self.on_algorithm_change)
        
        self.processor = SpeedProcessor()
        
        self.create_widgets()
    
    def create_widgets(self):
        # Верхняя панель
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
        
        # Панель алгоритма
        algo_frame = Frame(self.root)
        algo_frame.pack(pady=5, padx=10, fill='x')
        
        lbl_algo = tk.Label(algo_frame, text="Выберите алгоритм сглаживания:", 
                            font=('Arial', 10, 'bold'))
        lbl_algo.pack(side=tk.LEFT, padx=5)
        
        algorithms = [
            ("Стандартный (11→21 точек)", "default"),
            ("Экспоненциальное сглаживание", "exponential"),
            ("Фильтр Калмана", "kalman"),
            ("Медианный фильтр", "median"),
            ("Savitzky-Golay", "savgol")
        ]
        
        for text, value in algorithms:
            rb = Radiobutton(algo_frame, text=text, 
                             variable=self.algorithm, value=value,
                             font=('Arial', 9))
            rb.pack(side=tk.LEFT, padx=5)
        
        # Статус
        self.status_var = tk.StringVar()
        self.status_var.set("Готов к работе")
        status_bar = tk.Label(self.root, textvariable=self.status_var, 
                              relief=tk.SUNKEN, anchor=tk.W, font=('Arial', 9))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Параметры алгоритма
        self.params_frame = Frame(self.root, relief=tk.GROOVE, bd=2)
        self.params_frame.pack(pady=5, padx=10, fill='x')
        
        lbl_params = tk.Label(self.params_frame, text="Параметры алгоритма:", 
                              font=('Arial', 10, 'bold'))
        lbl_params.pack(side=tk.LEFT, padx=5)
        
        self.params_container = Frame(self.params_frame)
        self.params_container.pack(side=tk.LEFT, padx=10, fill='x', expand=True)
        self.show_default_params()
        
        # Основная область
        main_container = Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.figure_frame = Frame(main_container)
        self.figure_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.plot_manager = PlotManager(self.figure_frame)
        self.plot_manager.set_status_callback(self.update_status)
        self.plot_manager.set_hover_callback(self.on_hover)
        self.plot_manager.set_selection_callback(self.on_selection)   # новый callback
        
        # Правая панель
        self.control_panel = Frame(main_container, width=300, relief=tk.GROOVE, bd=2)
        self.control_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        self.control_panel.pack_propagate(False)
        
        self.create_control_panel()
    
    def create_control_panel(self):
        lbl_title = tk.Label(self.control_panel, text="Выбор столбцов для графиков", 
                             font=('Arial', 11, 'bold'), pady=10)
        lbl_title.pack()
        
        tk.Frame(self.control_panel, height=2, bd=1, relief=tk.SUNKEN).pack(fill=tk.X, padx=10, pady=5)
        
        # Верхний график
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
        
        tk.Frame(self.control_panel, height=2, bd=1, relief=tk.SUNKEN).pack(fill=tk.X, padx=10, pady=10)
        
        # Нижний график
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
        
        tk.Frame(self.control_panel, height=2, bd=1, relief=tk.SUNKEN).pack(fill=tk.X, padx=10, pady=10)
        
        # Кнопки управления выбором
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
        
        # ---- Новая секция для выделенной области ----
        tk.Frame(self.control_panel, height=2, bd=1, relief=tk.SUNKEN).pack(fill=tk.X, padx=10, pady=10)
        
        lbl_selection_title = Label(self.control_panel, text="Статистика выделенной области", 
                                    font=('Arial', 10, 'bold'))
        lbl_selection_title.pack(anchor=tk.W, padx=15, pady=5)
        
        # Кнопка очистки выделения
        btn_clear_selection = Button(self.control_panel, text="Очистить выделение", 
                                     command=self.clear_selection, font=('Arial', 10),
                                     bg='#f44336', fg='white', padx=10, pady=3)
        btn_clear_selection.pack(anchor=tk.W, padx=15, pady=5)
        
        # Текстовое поле для вывода статистики
        self.selection_text = Text(self.control_panel, height=12, width=35, 
                                   font=('Courier', 8), relief=tk.SUNKEN, bd=1)
        self.selection_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        # Добавим скролл
        scrollbar = Scrollbar(self.control_panel, command=self.selection_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 15))
        self.selection_text.config(yscrollcommand=scrollbar.set)
        
        # ---- Конец новой секции ----
        
        # Информация при наведении
        tk.Frame(self.control_panel, height=2, bd=1, relief=tk.SUNKEN).pack(fill=tk.X, padx=10, pady=10)
        lbl_hover_title = Label(self.control_panel, text="Значения в точке:", 
                                font=('Arial', 9, 'bold'))
        lbl_hover_title.pack(anchor=tk.W, padx=15)
        
        self.hover_label = Label(self.control_panel, text="Наведите курсор на график", 
                                 font=('Arial', 8), fg='gray', justify=tk.LEFT, 
                                 wraplength=280, anchor='w')
        self.hover_label.pack(anchor=tk.W, padx=15, pady=5, fill=tk.X)
        
        self.lbl_info = Label(self.control_panel, text="", font=('Arial', 8), fg='gray')
        self.lbl_info.pack(pady=5)
    
    # --- Новый метод обработки выделения ---
    def on_selection(self, x1, x2, stats):
        """Вызывается при выделении области на графике"""
        if x1 is None and stats is None:
            # сигнал очистки
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
            # Получаем единицу, если есть
            unit = self.plot_manager.get_unit(col)
            unit_str = f" ({unit})" if unit else ""
            line = (f"{col}{unit_str}:\n"
                    f"  среднее = {mean:.3f}\n"
                    f"  мин     = {minv:.3f}\n"
                    f"  макс    = {maxv:.3f}\n"
                    f"  ст.откл = {std:.3f}\n\n")
            self.selection_text.insert(tk.END, line)
        self.selection_text.see(1.0)  # прокрутка в начало
    
    def clear_selection(self):
        """Очищает выделение и обновляет график"""
        self.plot_manager.clear_selection()
        # также очищаем текстовую область (вызовется через callback, но на всякий случай)
        self.selection_text.delete(1.0, tk.END)
        self.selection_text.insert(tk.END, "Выделение очищено")
        self.status_var.set("Выделение очищено")
    # --- конец новых методов ---
    
    def on_hover(self, time, data_dict):
        """Обновляет информацию при наведении на график"""
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
                  'Скорость в коридоре (км/ч)']
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
            self.lbl_top_selected.config(text=", ".join(selected) if selected else "не выбрано")
        else:
            self.bottom_columns = selected
            self.lbl_bottom_selected.config(text=", ".join(selected) if selected else "не выбрано")
        
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
                
                cols = [col for col in df_full.columns if col != time_col]
                if 'скорость' in cols:
                    self.top_columns = ['скорость']
                    self.lbl_top_selected.config(text="скорость")
                if 'Уклон' in cols:
                    self.bottom_columns = ['Уклон']
                    self.lbl_bottom_selected.config(text="Уклон")
                
                if not self.top_columns and cols:
                    self.top_columns = [cols[0]]
                    self.lbl_top_selected.config(text=cols[0])
                if not self.bottom_columns and len(cols) > 1:
                    self.bottom_columns = [cols[1]]
                    self.lbl_bottom_selected.config(text=cols[1])
                
                if self.top_columns or self.bottom_columns:
                    self.apply_changes()
                
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
            if len(V) < 11:
                raise ValueError(f"Слишком мало данных ({len(V)} строк). Нужно минимум 11.")
            
            self.processor.set_params(
                corridor_percent=self.corridor_percent.get(),
                alpha_exp=self.alpha_exp.get(),
                kalman_q=self.kalman_q.get(),
                kalman_r=self.kalman_r.get(),
                median_window=self.median_window.get(),
                savgol_window=self.savgol_window.get(),
                savgol_order=self.savgol_order.get()
            )
            
            smoothed, speed, acceleration = self.processor.process(
                V, time, self.algorithm.get()
            )
            
            df['Сглаженная скорость (км/ч)'] = smoothed
            df['Скорость в м/с'] = speed
            df['Ускорение (м/с²)'] = acceleration
            
            if self.processor.last_after_restriction is not None:
                df['Скорость в коридоре (км/ч)'] = self.processor.last_after_restriction
            else:
                df['Скорость в коридоре (км/ч)'] = np.full(len(V), np.nan)
            
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
            messagebox.showwarning("Предупреждение", "Не выбрано ни одного столбца для отображения.")
            return
        
        self.plot_manager.set_data(
            self.df_full,
            self.time_col,
            self.top_columns,
            self.bottom_columns
        )
        self.plot_manager.show_plots()
        self.status_var.set("Графики обновлены")
    
    def reset_selection(self):
        self.top_columns = []
        self.bottom_columns = []
        self.lbl_top_selected.config(text="не выбрано")
        self.lbl_bottom_selected.config(text="не выбрано")
        
        if self.df_full is not None:
            cols = [col for col in self.df_full.columns if col != self.time_col]
            if 'скорость' in cols:
                self.top_columns = ['скорость']
                self.lbl_top_selected.config(text="скорость")
            if 'Уклон' in cols:
                self.bottom_columns = ['Уклон']
                self.lbl_bottom_selected.config(text="Уклон")
            if not self.top_columns and cols:
                self.top_columns = [cols[0]]
                self.lbl_top_selected.config(text=cols[0])
            if not self.bottom_columns and len(cols) > 1:
                self.bottom_columns = [cols[1]]
                self.lbl_bottom_selected.config(text=cols[1])
        
        self.apply_changes()
    
    # Параметры алгоритмов
    def clear_params(self):
        for widget in self.params_container.winfo_children():
            widget.destroy()
    
    def show_default_params(self):
        self.clear_params()
        lbl = tk.Label(self.params_container, text="Процентный коридор:", font=('Arial', 9))
        lbl.pack(side=tk.LEFT, padx=2)
        spin = Spinbox(self.params_container, from_=0.01, to=10.0, 
                       increment=0.01, width=8,
                       textvariable=self.corridor_percent, font=('Arial', 9))
        spin.pack(side=tk.LEFT, padx=2)
        lbl_percent = tk.Label(self.params_container, text="%", font=('Arial', 9))
        lbl_percent.pack(side=tk.LEFT, padx=2)
        lbl_info = tk.Label(self.params_container, text="(0.01-10.0, стандартное значение 0.1%)", 
                           font=('Arial', 8), fg='gray')
        lbl_info.pack(side=tk.LEFT, padx=5)
    
    def show_exponential_params(self):
        self.clear_params()
        lbl = tk.Label(self.params_container, text="Alpha (α):", font=('Arial', 9))
        lbl.pack(side=tk.LEFT, padx=2)
        spin = Spinbox(self.params_container, from_=0.01, to=1.0, 
                       increment=0.01, width=6,
                       textvariable=self.alpha_exp, font=('Arial', 9))
        spin.pack(side=tk.LEFT, padx=2)
        lbl_info = tk.Label(self.params_container, text="(0.01-1.0, чем выше тем быстрее реакция)", 
                           font=('Arial', 8), fg='gray')
        lbl_info.pack(side=tk.LEFT, padx=5)
    
    def show_kalman_params(self):
        self.clear_params()
        lbl_q = tk.Label(self.params_container, text="Q (шум процесса):", font=('Arial', 9))
        lbl_q.pack(side=tk.LEFT, padx=2)
        spin_q = Spinbox(self.params_container, from_=0.0001, to=1.0, 
                         increment=0.0001, width=8,
                         textvariable=self.kalman_q, font=('Arial', 9))
        spin_q.pack(side=tk.LEFT, padx=2)
        lbl_r = tk.Label(self.params_container, text="R (шум измерения):", font=('Arial', 9))
        lbl_r.pack(side=tk.LEFT, padx=5)
        spin_r = Spinbox(self.params_container, from_=0.0001, to=1.0, 
                         increment=0.0001, width=8,
                         textvariable=self.kalman_r, font=('Arial', 9))
        spin_r.pack(side=tk.LEFT, padx=2)
        lbl_info = tk.Label(self.params_container, text="(чем меньше Q, тем сильнее сглаживание)", 
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
        lbl_info = tk.Label(self.params_container, text="(нечётное число, 3-21)", 
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
        lbl_info = tk.Label(self.params_container, text="(окно должно быть > степени)", 
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


if __name__ == "__main__":
    root = tk.Tk()
    app = SpeedAnalyzerApp(root)
    root.mainloop()