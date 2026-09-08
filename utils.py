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
        
    # Ищем столбец со скоростью V
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