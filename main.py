# main.py
# Version: 3.0
import multiprocessing
import tkinter as tk
from main_app import MainApp

if __name__ == "__main__":
    # Notwendig für PyInstaller oder Windows Multiprocessing
    multiprocessing.freeze_support()

    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()