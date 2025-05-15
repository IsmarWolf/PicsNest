# main.py

import tkinter as tk
from app_manager import PhotoVideoManagerApp # Assuming app_manager.py is in the same directory
import sys
from tkinter import messagebox

# Critical dependency check (Pillow)
try:
    from PIL import Image, ImageTk, UnidentifiedImageError
except ImportError:
    # Attempt to show a Tkinter messagebox even if the main app can't fully initialize
    try:
        root_check = tk.Tk()
        root_check.withdraw() # Hide the main window
        messagebox.showerror("Critical Error", "Pillow library not found.\nPlease install it using: pip install Pillow")
        root_check.destroy()
    except tk.TclError: # Fallback if even basic Tk fails (e.g., no display)
        print("CRITICAL ERROR: Pillow library not found. Please install it using: pip install Pillow")
    sys.exit(1)


if __name__ == "__main__":
    root = tk.Tk()
    app = PhotoVideoManagerApp(root)
    root.mainloop()