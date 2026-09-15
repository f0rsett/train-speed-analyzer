import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import numpy as np
import tkinter as tk
import pandas as pd

UNITS = {
    'Скорость': 'км/ч',
    'Сглаженная скорость': 'км/ч',
    'Скорость в м/с': 'м/с',
    'Ускорение': 'м/с²',
    'Ускорение сглаженное': 'м/с²',
    'Скорость в коридоре': 'км/ч',
    'Уклон': '‰',
    'ТЦ': 'кгс/см²',
    'ТМ': 'кгс/см²',
    'ГР': 'кгс/см²',
    'Тяга': 'кН',
    'Тормоз': 'кН',
}

EXCLUDED_COLUMNS = {
    'KLUB_Svetofor',
    'KLUB_Coord',
    'KLUB_PUR',
    'Af_sr[1]',
    'Freal',
    'Нижняя граница скорости',
    'Верхняя граница скорости',
    'Нижняя граница ускорения',
    'Верхняя граница ускорения',
}

COLORS = {
    'Скорость':               '#1f77b4',
    'Сглаженная скорость':    '#17becf',
    'Скорость в м/с':         '#9467bd',
    'Скорость в коридоре':    '#8c564b',
    'Ускорение':              '#ff7f0e',
    'Ускорение сглаженное':   '#e377c2',
    'Уклон':                  '#7f7f7f',
    'ТЦ':                     '#bcbd22',
    'ТМ':                     '#d62728',
    'ГР':                     '#1f77b4',
    'Тяга':                   '#2ca02c',
    'Тормоз':                 '#d62728',
}

# Порядок отрисовки: чем больше — тем выше
ZORDER = {
    'Тяга':   6,
    'Тормоз': 5,
}

# Столбцы, которые рисуем как гистограмму (bar) вместо линии
HISTOGRAM_COLUMNS = {'Тяга', 'Тормоз'}

# Столбцы, у которых значения меньше порога отображаются как 0
THRESHOLD_ZERO = {
    'ТЦ': 0.1,
}


class QuietToolbar(NavigationToolbar2Tk):
    """Тулбар matplotlib без вывода координат x/y в правом углу."""

    def set_message(self, s):
        pass


class PlotManager:
    def __init__(self, figure_frame, toolbar_frame=None):
        self.figure_frame = figure_frame
        self.toolbar_frame = toolbar_frame
        self.df = None
        self.time_col = None
        self.top_columns = []
        self.bottom_columns = []
        self.show_corridor = False

        self.canvas = None
        self.fig = None
        self.ax1 = None
        self.ax2 = None

        self.vline1 = None
        self.vline2 = None

        self.rects = []
        self.press_x = None
        self.is_dragging = False

        self.cid_motion_hover = None
        self.cid_leave = None
        self.cid_press = None
        self.cid_release = None
        self.cid_motion_drag = None

        self.status_callback = None
        self.hover_callback = None
        self.selection_callback = None

        self.selection_mode = False
        self.toolbar = None

    def set_toolbar_frame(self, frame):
        self.toolbar_frame = frame

    def set_data(self, df, time_col, top_columns, bottom_columns, show_corridor=False):
        self.df = df
        self.time_col = time_col
        self.top_columns = top_columns
        self.bottom_columns = bottom_columns
        self.show_corridor = show_corridor

    def set_status_callback(self, callback):
        self.status_callback = callback

    def set_hover_callback(self, callback):
        self.hover_callback = callback

    def set_selection_callback(self, callback):
        self.selection_callback = callback

    def get_unit(self, column):
        return UNITS.get(column, "")

    def set_selection_mode(self, enabled):
        self.selection_mode = enabled
        if not enabled:
            self.clear_selection()
        if self.status_callback:
            self.status_callback(f"Режим выделения {'включен' if enabled else 'выключен'}")

    @staticmethod
    def _build_bar_segments(time, values):
        """
        Группирует подряд идущие одинаковые значения в интервалы.
        Возвращает список кортежей (start_x, width, value).
        """
        segments = []
        n = len(time)
        if n == 0:
            return segments

        if n >= 2:
            last_dt = time[-1] - time[-2]
            if not np.isfinite(last_dt) or last_dt <= 0:
                last_dt = 1.0
        else:
            last_dt = 1.0

        i = 0
        while i < n:
            v = values[i]
            if not np.isfinite(v):
                i += 1
                continue
            j = i
            while (j + 1 < n
                   and np.isfinite(values[j + 1])
                   and values[j + 1] == v):
                j += 1

            start = time[i]
            if j + 1 < n:
                end = time[j + 1]
            else:
                end = time[j] + last_dt

            width = end - start
            if width > 0:
                segments.append((start, width, v))
            i = j + 1

        return segments

    def _plot_column(self, ax, col, time, y, color, color_idx):
        """Рисует столбец (линию или гистограмму) в заданных осях."""
        label = col
        unit = UNITS.get(col, "")
        if unit:
            label = f"{col} ({unit})"

        z = ZORDER.get(col, 2)

        # Порог: значения меньше порога рисуем как 0 (только для визуализации)
        if col in THRESHOLD_ZERO:
            threshold = THRESHOLD_ZERO[col]
            y_plot = np.where(np.isfinite(y) & (y < threshold), 0.0, y)
        else:
            y_plot = y

        if col in HISTOGRAM_COLUMNS:
            segments = self._build_bar_segments(time, y_plot)
            first = True
            for (start, width, value) in segments:
                ax.bar(start, value, width=width, align='edge',
                       color=color, alpha=0.75, edgecolor='none',
                       label=label if first else None, zorder=z)
                first = False
        else:
            ax.plot(time, y_plot, label=label, color=color, linewidth=1.5, zorder=z)

    def show_plots(self):
        if self.df is None or self.time_col is None:
            return
        if not self.top_columns and not self.bottom_columns:
            return

        for widget in self.figure_frame.winfo_children():
            widget.destroy()

        if self.toolbar is not None:
            try:
                self.toolbar.destroy()
            except Exception:
                pass
            self.toolbar = None
        if self.toolbar_frame is not None:
            for w in self.toolbar_frame.winfo_children():
                w.destroy()

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6))

        time = self.df[self.time_col].values
        colors = plt.cm.tab10(np.linspace(0, 1, 10))

        # ---- Верхний график ----
        color_idx = 0
        for col in self.top_columns:
            if col not in self.df.columns:
                continue
            y = self.df[col].values
            color = COLORS.get(col, colors[color_idx % len(colors)])
            if col not in COLORS:
                color_idx += 1
            self._plot_column(ax1, col, time, y, color, color_idx)

        if self.show_corridor:
            low_col = 'Нижняя граница скорости'
            high_col = 'Верхняя граница скорости'
            if low_col in self.df.columns and high_col in self.df.columns:
                low = self.df[low_col].values
                high = self.df[high_col].values
                ax1.fill_between(time, low, high, alpha=0.2, color='gray',
                                 label='Коридор скорости')
                ax1.plot(time, low, '--', color='gray', linewidth=1, alpha=0.7)
                ax1.plot(time, high, '--', color='gray', linewidth=1, alpha=0.7)

        top_title = "Верхний график"
        if self.top_columns:
            top_title += f" ({', '.join(self.top_columns)})"

        ax1.set_ylabel('Значение')
        ax1.set_title(top_title)
        handles, labels = ax1.get_legend_handles_labels()
        if handles:
            ax1.legend(loc='best')
        ax1.grid(True, alpha=0.3)
        ax1.set_xlim(time.min(), time.max())

        # ---- Нижний график ----
        color_idx = 0
        for col in self.bottom_columns:
            if col not in self.df.columns:
                continue
            y = self.df[col].values
            color = COLORS.get(col, colors[color_idx % len(colors)])
            if col not in COLORS:
                color_idx += 1
            self._plot_column(ax2, col, time, y, color, color_idx)

        if self.show_corridor:
            low_col = 'Нижняя граница ускорения'
            high_col = 'Верхняя граница ускорения'
            if low_col in self.df.columns and high_col in self.df.columns:
                low = self.df[low_col].values
                high = self.df[high_col].values
                ax2.fill_between(time, low, high, alpha=0.2, color='gray',
                                 label='Коридор ускорения')
                ax2.plot(time, low, '--', color='gray', linewidth=1, alpha=0.7)
                ax2.plot(time, high, '--', color='gray', linewidth=1, alpha=0.7)

        bottom_title = "Нижний график"
        if self.bottom_columns:
            bottom_title += f" ({', '.join(self.bottom_columns)})"

        ax2.set_ylabel('Значение')
        ax2.set_xlabel('Время')
        ax2.set_title(bottom_title)
        handles, labels = ax2.get_legend_handles_labels()
        if handles:
            ax2.legend(loc='best')
        ax2.grid(True, alpha=0.3)
        ax2.set_xlim(time.min(), time.max())

        # ---- Y-границы (учитываем линии, патчи и заливки) ----
        for ax in (ax1, ax2):
            y_min = np.inf
            y_max = -np.inf

            for line in ax.lines:
                ydata = line.get_ydata()
                if len(ydata) > 0:
                    finite = ydata[np.isfinite(ydata)]
                    if len(finite) > 0:
                        y_min = min(y_min, np.nanmin(finite))
                        y_max = max(y_max, np.nanmax(finite))

            for patch in ax.patches:
                try:
                    y0 = patch.get_y()
                    h = patch.get_height()
                    y_lo = min(y0, y0 + h)
                    y_hi = max(y0, y0 + h)
                    if np.isfinite(y_lo):
                        y_min = min(y_min, y_lo)
                    if np.isfinite(y_hi):
                        y_max = max(y_max, y_hi)
                except Exception:
                    pass

            for collection in ax.collections:
                if isinstance(collection, plt.matplotlib.collections.PolyCollection):
                    for path in collection.get_paths():
                        verts = path.vertices
                        if len(verts) > 0:
                            y_vals = verts[:, 1]
                            finite = y_vals[np.isfinite(y_vals)]
                            if len(finite) > 0:
                                y_min = min(y_min, np.nanmin(finite))
                                y_max = max(y_max, np.nanmax(finite))

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

        if self.toolbar_frame is not None:
            toolbar = QuietToolbar(canvas, self.toolbar_frame)
            self.toolbar = toolbar
            toolbar.update()
        else:
            toolbar = QuietToolbar(canvas, self.figure_frame)
            self.toolbar = toolbar
            toolbar.update()

        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _add_interactivity(self, canvas, ax1, ax2):
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
        data_dict = {}
        for col in self.df.columns:
            if col == self.time_col:
                continue
            if col in EXCLUDED_COLUMNS:
                continue
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
        if not self.selection_mode:
            return
        if event.inaxes is None:
            return
        self.press_x = event.xdata
        self.is_dragging = True
        self._clear_rects()

    def _clear_rects(self):
        for rect in self.rects:
            try:
                rect.remove()
            except Exception:
                pass
        self.rects.clear()
        if self.canvas:
            self.canvas.draw_idle()

    def on_motion(self, event):
        if not self.selection_mode:
            return
        if not self.is_dragging or event.inaxes is None:
            return
        self._clear_rects()
        x1 = self.press_x
        x2 = event.xdata
        r1 = self.ax1.axvspan(x1, x2, alpha=0.3, color='yellow')
        r2 = self.ax2.axvspan(x1, x2, alpha=0.3, color='yellow')
        self.rects = [r1, r2]
        self.canvas.draw()

    def on_release(self, event):
        if not self.selection_mode:
            return
        if event.inaxes is None or not self.is_dragging:
            return
        self.is_dragging = False
        x1 = min(self.press_x, event.xdata)
        x2 = max(self.press_x, event.xdata)
        if abs(x2 - x1) < 1e-6:
            return
        time = self.df[self.time_col].values
        mask = (time >= x1) & (time <= x2)
        if not mask.any():
            return
        stats = {}
        for col in self.df.columns:
            if col == self.time_col:
                continue
            if col in EXCLUDED_COLUMNS:
                continue
            if pd.api.types.is_numeric_dtype(self.df[col]):
                vals = self.df[col][mask].values
                vals = vals[~np.isnan(vals)]
                if len(vals) > 0:
                    stats[col] = (np.mean(vals), np.min(vals), np.max(vals), np.std(vals))
        if self.selection_callback and stats:
            self.selection_callback(x1, x2, stats)
        if self.status_callback:
            first_col = next(iter(stats)) if stats else None
            if first_col:
                mean_val = stats[first_col][0]
                self.status_callback(
                    f"Выделена область: {x1:.2f} - {x2:.2f} с, "
                    f"среднее {first_col} = {mean_val:.3f}"
                )
            else:
                self.status_callback(
                    f"Выделена область: {x1:.2f} - {x2:.2f} с (нет числовых данных)"
                )

    def clear_selection(self):
        self._clear_rects()
        if self.selection_callback:
            self.selection_callback(None, None, None)

    def update(self):
        self.show_plots()