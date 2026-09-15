import numpy as np
from scipy.signal import savgol_filter


class SpeedProcessor:
    """Класс для обработки данных скорости и ускорения.

    Все параметры сглаживания передаются явно в методы.
    """

    def __init__(self):
        self.last_after_restriction = None
        self.low_bound = None
        self.high_bound = None

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

    def smooth_default(self, V, n,
                       corridor_percent=0.1,
                       window_trunc=11,
                       window_final=21):
        """
        Стандартный алгоритм:
            1. Усечённое скользящее среднее (окно window_trunc)
            2. Построение границ коридора: tmean ± |tmean| * percent/100
            3. Ограничение исходных значений внутри коридора
            4. Скользящее среднее (окно window_final)
        """
        truncated_mean = np.full(n, np.nan)
        after_restriction = np.full(n, np.nan)
        smoothed = np.full(n, np.nan)

        w1 = self._normalize_window(window_trunc, n, min_window=3)
        w2 = self._normalize_window(window_final, n, min_window=3)

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

    def smooth_exponential(self, V, n, alpha=0.3):
        smoothed = np.full(n, np.nan)
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

    def smooth_kalman(self, V, n, q=0.01, r=0.1):
        smoothed = np.full(n, np.nan)
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

    def smooth_median(self, V, n, window=5):
        smoothed = np.full(n, np.nan)
        w = self._normalize_window(window, n, min_window=3)
        if w is None:
            return smoothed
        half = w // 2
        for i in range(half, n - half):
            win = V[i - half: i + half + 1]
            if not np.isnan(win).all():
                smoothed[i] = np.nanmedian(win)
        return smoothed

    def smooth_savgol(self, V, n, window=11, order=3):
        mask = ~np.isnan(V)
        if np.sum(mask) < window:
            return V
        x = np.arange(n)
        V_interp = np.interp(x, x[mask], V[mask])
        smoothed = savgol_filter(V_interp, window, order)
        return smoothed