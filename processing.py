import numpy as np
from scipy.signal import savgol_filter


class SpeedProcessor:
    """Класс для обработки данных скорости и ускорения"""

    def __init__(self):
        self.corridor_percent_speed = 0.1
        self.corridor_percent_accel = 0.1

        self.window_trunc_mean = 11
        self.window_final_mean = 21

        self.alpha_exp = 0.3
        self.kalman_q = 0.01
        self.kalman_r = 0.1
        self.median_window = 5
        self.savgol_window = 11
        self.savgol_order = 3

        self.last_after_restriction = None
        self.low_bound = None
        self.high_bound = None

    def set_params(self,
                   corridor_percent_speed=None,
                   corridor_percent_accel=None,
                   window_trunc_mean=None,
                   window_final_mean=None,
                   alpha_exp=None, kalman_q=None, kalman_r=None,
                   median_window=None, savgol_window=None, savgol_order=None):
        if corridor_percent_speed is not None:
            self.corridor_percent_speed = corridor_percent_speed
        if corridor_percent_accel is not None:
            self.corridor_percent_accel = corridor_percent_accel
        if window_trunc_mean is not None:
            self.window_trunc_mean = window_trunc_mean
        if window_final_mean is not None:
            self.window_final_mean = window_final_mean
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

    @staticmethod
    def _normalize_window(window, n, min_window=3):
        w = int(window)
        if w % 2 == 0:
            w -= 1
        max_w = n if n % 2 == 1 else n - 1
        if w > max_w:
            w = max_w
        if w < min_window:
            return None
        return w

    def smooth_default(self, V, n, corridor_percent=None):
        if corridor_percent is None:
            corridor_percent = self.corridor_percent_speed

        truncated_mean = np.full(n, np.nan)
        after_restriction = np.full(n, np.nan)
        smoothed = np.full(n, np.nan)

        w1 = self._normalize_window(self.window_trunc_mean, n, min_window=3)
        w2 = self._normalize_window(self.window_final_mean, n, min_window=3)

        # 1. Усечённое скользящее среднее
        if w1 is not None:
            half = w1 // 2
            for i in range(half, n - half):
                window = V[i - half: i + half + 1]
                if len(window) > 2 and not np.isnan(window).all():
                    sum_win = np.nansum(window) - np.nanmax(window) - np.nanmin(window)
                    truncated_mean[i] = sum_win / (len(window) - 2)

        # 2 + 3. Коридор и ограничение
        percent = corridor_percent / 100.0
        self.low_bound = np.full(n, np.nan)
        self.high_bound = np.full(n, np.nan)
        for i in range(n):
            if not np.isnan(truncated_mean[i]):
                delta = abs(truncated_mean[i]) * percent
                low = truncated_mean[i] - delta
                high = truncated_mean[i] + delta
                self.low_bound[i] = low
                self.high_bound[i] = high
                if V[i] < low:
                    after_restriction[i] = low
                elif V[i] > high:
                    after_restriction[i] = high
                else:
                    after_restriction[i] = V[i]
            else:
                after_restriction[i] = np.nan

        # 4. Финальное скользящее среднее
        if w2 is not None:
            half2 = w2 // 2
            for i in range(half2, n - half2):
                window = after_restriction[i - half2: i + half2 + 1]
                if not np.isnan(window).all():
                    smoothed[i] = np.nanmean(window)

        self.last_after_restriction = after_restriction
        return smoothed

    def smooth_exponential(self, V, n):
        """Экспоненциальное сглаживание. Стартует с первого не-NaN значения."""
        alpha = self.alpha_exp
        smoothed = np.full(n, np.nan)

        # Ищем первое не-NaN значение
        first_valid = None
        for i in range(n):
            if not np.isnan(V[i]):
                first_valid = i
                break
        if first_valid is None:
            return smoothed

        smoothed[first_valid] = V[first_valid]
        for i in range(first_valid + 1, n):
            if not np.isnan(V[i]):
                smoothed[i] = alpha * V[i] + (1 - alpha) * smoothed[i - 1]
            else:
                smoothed[i] = smoothed[i - 1]
        return smoothed

    def smooth_kalman(self, V, n):
        """Фильтр Калмана. Стартует с первого не-NaN значения."""
        smoothed = np.full(n, np.nan)
        q = self.kalman_q
        r = self.kalman_r

        first_valid = None
        for i in range(n):
            if not np.isnan(V[i]):
                first_valid = i
                break
        if first_valid is None:
            return smoothed

        x_est = V[first_valid]
        p_est = 1.0
        smoothed[first_valid] = x_est

        for i in range(first_valid + 1, n):
            if not np.isnan(V[i]):
                x_pred = x_est
                p_pred = p_est + q
                k = p_pred / (p_pred + r)
                x_est = x_pred + k * (V[i] - x_pred)
                p_est = (1 - k) * p_pred
                smoothed[i] = x_est
            else:
                smoothed[i] = smoothed[i - 1]
        return smoothed

    def smooth_median(self, V, n):
        window_size = self.median_window
        smoothed = np.full(n, np.nan)
        half = window_size // 2
        for i in range(half, n - half):
            window = V[i - half: i + half + 1]
            if not np.isnan(window).all():
                smoothed[i] = np.nanmedian(window)
        return smoothed

    def smooth_savgol(self, V, n):
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
        n = len(V)
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

        speed = smoothed / 3.6
        from utils import calculate_acceleration
        acceleration = calculate_acceleration(speed, time)
        return smoothed, speed, acceleration