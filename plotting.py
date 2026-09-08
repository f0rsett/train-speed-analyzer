import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import numpy as np
import tkinter as tk
import pandas as pd

UNITS = {
    'скорость': 'км/ч',
    'Сглаженная скорость (км/ч)': 'км/ч',
    'Скорость в м/с': 'м/с',
    'Ускорение (м/с²)': 'м/с²',
    'Скорость в коридоре (км/ч)': 'км/ч',
    'Уклон': '‰',
    'ТЦ': 'кгс/см²',
    'ТМ': 'кгс/см²',
    'ГР': 'кгс/см²',
    'тяга': 'кН',
    'тормоз': 'кН',
}

class PlotManager:
    def __init__(self, figure_frame):
        self.figure_frame = figure_frame
        self.df = None
        self.time_col = None
        self.top_columns = []
        self.bottom_columns = []
        
        self.canvas = None
        self.fig = None
        self.ax1 = None
        self.ax2 = None
        
        self.vline1 = None
        self.vline2 = None
        # Убрали info_text1, info_text2
        
        self.rect = None
        self.press_x = None
        self.is_dragging = False
        
        self.cid_motion_hover = None
        self.cid_leave = None
        self.cid_press = None
        self.cid_release = None
        self.cid_motion_drag = None
        
        self.status_callback = None
        self.hover_callback = None
    
    def set_data(self, df, time_col, top_columns, bottom_columns):
        self.df = df
        self.time_col = time_col
        self.top_columns = top_columns
        self.bottom_columns = bottom_columns
    
    def set_status_callback(self, callback):
        self.status_callback = callback
    
    def set_hover_callback(self, callback):
        self.hover_callback = callback
    
    def get_unit(self, column):
        return UNITS.get(column, "")
    
    def show_plots(self):
        if self.df is None or self.time_col is None:
            return
        if not self.top_columns and not self.bottom_columns:
            return
        
        for widget in self.figure_frame.winfo_children():
            widget.destroy()
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6))
        
        time = self.df[self.time_col].values
        colors = plt.cm.tab10(np.linspace(0, 1, 10))
        color_idx = 0
        
        for col in self.top_columns:
            if col not in self.df.columns:
                continue
            y = self.df[col].values
            label = col
            if col in UNITS:
                label = f"{col} ({UNITS[col]})"
            ax1.plot(time, y, label=label, color=colors[color_idx % len(colors)], linewidth=1.5)
            color_idx += 1
        
        ax1.set_ylabel('Значение')
        ax1.set_title('Верхний график')
        ax1.legend(loc='best')
        ax1.grid(True, alpha=0.3)
        ax1.set_xlim(time.min(), time.max())
        
        color_idx = 0
        for col in self.bottom_columns:
            if col not in self.df.columns:
                continue
            y = self.df[col].values
            label = col
            if col in UNITS:
                label = f"{col} ({UNITS[col]})"
            ax2.plot(time, y, label=label, color=colors[color_idx % len(colors)], linewidth=1.5)
            color_idx += 1
        
        ax2.set_ylabel('Значение')
        ax2.set_xlabel('Время')
        ax2.set_title('Нижний график')
        ax2.legend(loc='best')
        ax2.grid(True, alpha=0.3)
        ax2.set_xlim(time.min(), time.max())
        
        for ax in (ax1, ax2):
            if ax.lines:
                y_min = np.inf
                y_max = -np.inf
                for line in ax.lines:
                    ydata = line.get_ydata()
                    if len(ydata) > 0:
                        y_min = min(y_min, np.nanmin(ydata))
                        y_max = max(y_max, np.nanmax(ydata))
                if np.isfinite(y_min) and np.isfinite(y_max):
                    y_range = y_max - y_min
                    if y_range > 0:
                        ax.set_ylim(y_min - y_range * 0.1, y_max + y_range * 0.1)
        
        plt.tight_layout()
        
        canvas = FigureCanvasTkAgg(fig, master=self.figure_frame)
        canvas.draw()
        
        self.canvas = canvas
        self.fig = fig
        self.ax1 = ax1
        self.ax2 = ax2
        
        self._add_interactivity(canvas, ax1, ax2)
        
        toolbar = NavigationToolbar2Tk(canvas, self.figure_frame)
        toolbar.update()
        
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def _add_interactivity(self, canvas, ax1, ax2):
        # Только вертикальные линии (без текстовых меток)
        self.vline1 = ax1.axvline(x=0, color='#FF6B6B', linestyle='--', 
                                  linewidth=2, alpha=0.8, visible=False)
        self.vline2 = ax2.axvline(x=0, color='#FF6B6B', linestyle='--', 
                                  linewidth=2, alpha=0.8, visible=False)
        
        self.cid_motion_hover = canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
        self.cid_leave = canvas.mpl_connect('axes_leave_event', self.on_mouse_leave)
        self.cid_press = canvas.mpl_connect('button_press_event', self.on_press)
        self.cid_release = canvas.mpl_connect('button_release_event', self.on_release)
        self.cid_motion_drag = canvas.mpl_connect('motion_notify_event', self.on_motion)
    
    def on_mouse_move(self, event):
        if event.inaxes is None or self.df is None:
            return
        
        x = event.xdata
        if x is None:
            return
        
        time = self.df[self.time_col].values
        if x < time.min() or x > time.max():
            self.vline1.set_visible(False)
            self.vline2.set_visible(False)
            self.canvas.draw_idle()
            return
        
        self.vline1.set_xdata([x, x])
        self.vline1.set_visible(True)
        self.vline2.set_xdata([x, x])
        self.vline2.set_visible(True)
        
        idx = np.argmin(np.abs(time - x))
        if idx >= len(time):
            return
        time_val = time[idx]
        
        # Собираем значения ВСЕХ числовых столбцов (кроме времени)
        data_dict = {}
        for col in self.df.columns:
            if col == self.time_col:
                continue
            # Проверяем, что столбец числовой
            if pd.api.types.is_numeric_dtype(self.df[col]):
                if idx < len(self.df):
                    val = self.df[col].iloc[idx]
                    if np.isfinite(val):
                        data_dict[col] = val
        
        if self.hover_callback:
            self.hover_callback(time_val, data_dict)
        
        if self.status_callback:
            self.status_callback(f"t={time_val:.2f} с")
        
        self.canvas.draw_idle()
    
    def on_mouse_leave(self, event):
        self.vline1.set_visible(False)
        self.vline2.set_visible(False)
        self.canvas.draw_idle()
        
        if self.hover_callback:
            self.hover_callback(None, {})
        if self.status_callback:
            self.status_callback("Готов к работе")
    
    def on_press(self, event):
        if event.inaxes is None:
            return
        self.press_x = event.xdata
        self.is_dragging = True
        if self.rect is not None:
            self.rect.remove()
            self.rect = None
            self.canvas.draw_idle()
    
    def on_motion(self, event):
        if not self.is_dragging or event.inaxes is None:
            return
        if self.rect is not None:
            self.rect.remove()
        x1 = self.press_x
        x2 = event.xdata
        self.rect = self.ax1.axvspan(x1, x2, alpha=0.3, color='yellow')
        self.ax2.axvspan(x1, x2, alpha=0.3, color='yellow')
        self.canvas.draw_idle()
    
    def on_release(self, event):
        if event.inaxes is None or not self.is_dragging:
            return
        self.is_dragging = False
        x1 = min(self.press_x, event.xdata)
        x2 = max(self.press_x, event.xdata)
        
        time = self.df[self.time_col].values
        mask = (time >= x1) & (time <= x2)
        
        if mask.any():
            if self.ax1.lines:
                first_line = self.ax1.lines[0]
                y_selected = first_line.get_ydata()[mask]
                mean_val = np.nanmean(y_selected)
                if self.status_callback:
                    self.status_callback(f"Выделена область: {x1:.2f} - {x2:.2f} с, среднее = {mean_val:.3f}")
    
    def update(self):
        self.show_plots()
    
    def clear_selection(self):
        if self.rect is not None:
            self.rect.remove()
            self.rect = None
            self.canvas.draw_idle()