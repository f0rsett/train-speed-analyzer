# processing.py
import numpy as np
from scipy.signal import savgol_filter

class SpeedProcessor:
    """Класс для обработки данных скорости"""
    
    def __init__(self):
        # Параметры будут устанавливаться извне
        self.corridor_percent = 0.1
        self.alpha_exp = 0.3
        self.kalman_q = 0.01
        self.kalman_r = 0.1
        self.median_window = 5
        self.savgol_window = 11
        self.savgol_order = 3
        self.last_after_restriction = None
    
    def set_params(self, corridor_percent=None, alpha_exp=None, 
                   kalman_q=None, kalman_r=None, 
                   median_window=None, savgol_window=None, savgol_order=None):
        """Обновляет параметры алгоритмов"""
        if corridor_percent is not None:
            self.corridor_percent = corridor_percent
        if alpha_exp is not None:
            self.alpha_exp = alpha_exp
        if kalman_q is not None:
            self.kalman_q = kalman_q
        if kalman_r is not None:
            self.kalman_r = kalman_r
        if median_window is not None:
            self.median_window = median_window
        if savgol_window is not None:
            self.savgol_window = savgol_window
        if savgol_order is not None:
            self.savgol_order = savgol_order
    
    def smooth_default(self, V, n):
        """Стандартный алгоритм: 11→21 точек"""
        truncated_mean = np.full(n, np.nan)
        after_restriction = np.full(n, np.nan)
        smoothed = np.full(n, np.nan)
        
        # 1. Усечённое скользящее среднее по 11 точкам
        window_size = 11
        half = window_size // 2
        for i in range(half, n - half):
            window = V[i - half : i + half + 1]
            if len(window) > 2 and not np.isnan(window).all():
                sum_win = np.nansum(window) - np.nanmax(window) - np.nanmin(window)
                truncated_mean[i] = sum_win / (len(window) - 2)
        
        # 2. Ограничение диапазона
        percent = self.corridor_percent / 100.0
        for i in range(n):
            if not np.isnan(truncated_mean[i]):
                low = truncated_mean[i] * (1 - percent)
                high = truncated_mean[i] * (1 + percent)
                if V[i] < low:
                    after_restriction[i] = low
                elif V[i] > high:
                    after_restriction[i] = high
                else:
                    after_restriction[i] = V[i]
        
        # 3. Скользящее среднее по 21 точке
        window_size2 = 21
        half2 = window_size2 // 2
        for i in range(half2, n - half2):
            window = after_restriction[i - half2 : i + half2 + 1]
            if not np.isnan(window).all():
                smoothed[i] = np.nanmean(window)
        
        self.last_after_restriction = after_restriction
        return smoothed
    
    def smooth_exponential(self, V, n):
        """Экспоненциальное сглаживание"""
        alpha = self.alpha_exp
        smoothed = np.full(n, np.nan)
        if n > 0:
            smoothed[0] = V[0]
            for i in range(1, n):
                if not np.isnan(V[i]):
                    smoothed[i] = alpha * V[i] + (1 - alpha) * smoothed[i-1]
                else:
                    smoothed[i] = smoothed[i-1]
        return smoothed
    
    def smooth_kalman(self, V, n):
        """Упрощённый фильтр Калмана"""
        smoothed = np.full(n, np.nan)
        q = self.kalman_q
        r = self.kalman_r
        
        if n > 0:
            x_est = V[0]
            p_est = 1.0
            
            for i in range(n):
                if not np.isnan(V[i]):
                    x_pred = x_est
                    p_pred = p_est + q
                    k = p_pred / (p_pred + r)
                    x_est = x_pred + k * (V[i] - x_pred)
                    p_est = (1 - k) * p_pred
                    smoothed[i] = x_est
                else:
                    smoothed[i] = smoothed[i-1] if i > 0 else V[i]
        return smoothed
    
    def smooth_median(self, V, n):
        """Медианный фильтр"""
        window_size = self.median_window
        smoothed = np.full(n, np.nan)
        half = window_size // 2
        for i in range(half, n - half):
            window = V[i - half : i + half + 1]
            if not np.isnan(window).all():
                smoothed[i] = np.nanmedian(window)
        return smoothed
    
    def smooth_savgol(self, V, n):
        """Фильтр Савицкого-Голая"""
        window_size = self.savgol_window
        order = self.savgol_order
        
        mask = ~np.isnan(V)
        if np.sum(mask) < window_size:
            return V
        
        x = np.arange(n)
        V_interp = np.interp(x, x[mask], V[mask])
        smoothed = savgol_filter(V_interp, window_size, order)
        return smoothed
    
    def process(self, V, time, algorithm="default"):
        """Основной метод обработки данных"""
        n = len(V)
        
        # Выбор алгоритма
        if algorithm == "default":
            smoothed = self.smooth_default(V, n)
        elif algorithm == "exponential":
            smoothed = self.smooth_exponential(V, n)
        elif algorithm == "kalman":
            smoothed = self.smooth_kalman(V, n)
        elif algorithm == "median":
            smoothed = self.smooth_median(V, n)
        elif algorithm == "savgol":
            smoothed = self.smooth_savgol(V, n)
        else:
            smoothed = self.smooth_default(V, n)
        
        # Перевод в м/с
        speed = smoothed / 3.6
        
        # Расчёт ускорения
        from utils import calculate_acceleration
        acceleration = calculate_acceleration(speed, time)
        
        return smoothed, speed, acceleration