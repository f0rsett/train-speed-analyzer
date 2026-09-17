# utils.py
import numpy as np
import pandas as pd


def find_columns(df):
    """Находит колонки с временем и скоростью в DataFrame"""
    time_col = None
    speed_col = None

    for col in df.columns:
        if 'Время' in col or 'время' in col or 'Time' in col or 'time' in col:
            time_col = col
            break

    for col in df.columns:
        if 'Скорость' in col or 'Speed' in col or 'speed' in col:
            speed_col = col
            break

    return time_col, speed_col


def calculate_acceleration(speed, time, step=10):
    """Расчёт ускорения по шагам"""
    n = len(speed)
    acceleration = np.full(n, np.nan)
    for i in range(step, n):
        if not np.isnan(speed[i]) and not np.isnan(speed[i - step]):
            dt = time[i] - time[i - step]
            if dt != 0:
                acceleration[i] = (speed[i] - speed[i - step]) / dt
    return acceleration

def calculate_jitter(signal, time, half_window_sec=5.0):
    """Локальный размах: max(signal) - min(signal) в окне ±half_window_sec.

    Для каждой точки i берётся интервал [t_i - h, t_i + h] и считается
    разница между максимальным и минимальным значением сигнала в нём.
    Если в самой точке сигнал отсутствует (NaN) — результат тоже NaN.
    """
    n = len(signal)
    result = np.full(n, np.nan)
    for i in range(n):
        # Нет значения в самой точке — нет и дребезга
        if not np.isfinite(signal[i]):
            continue
        t = time[i]
        left = np.searchsorted(time, t - half_window_sec, side='left')
        right = np.searchsorted(time, t + half_window_sec, side='right')
        window = signal[left:right]
        if len(window) == 0:
            continue
        finite = window[np.isfinite(window)]
        if len(finite) >= 2:
            result[i] = np.max(finite) - np.min(finite)
    return result