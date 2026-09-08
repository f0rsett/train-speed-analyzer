# main.py
import tkinter as tk
from gui import SpeedAnalyzerApp

if __name__ == "__main__":
    root = tk.Tk()
    app = SpeedAnalyzerApp(root)
    
    def on_closing():
        root.quit()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()