# image_viewer.py

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, UnidentifiedImageError
import os

from constants import (
    PICSNEST_VIEWER_BG, PICSNEST_TEXT_LIGHT,
    PICSNEST_BG_DARK, PICSNEST_BG_MEDIUM, 
    PICSNEST_ACCENT_BLUE, PICSNEST_ACCENT_RED
)

class ImageViewerWindow(tk.Toplevel):
    def __init__(self, parent, image_paths_list, current_index, main_app_ref):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.focus_set()

        self.image_paths = list(image_paths_list)
        self.current_image_index = current_index
        self.main_app = main_app_ref
        self.items_deleted_from_viewer = False 

        self.title("PicsNest - Image Viewer")
        self.geometry("800x650")
        self.configure(bg=PICSNEST_VIEWER_BG)

        # Main frame to hold image and controls, using grid
        main_viewer_frame = ttk.Frame(self, style="PicsNest.Dark.TFrame") # Use main dark theme
        main_viewer_frame.pack(expand=True, fill=tk.BOTH)
        main_viewer_frame.grid_rowconfigure(0, weight=1) # Image area expands
        main_viewer_frame.grid_rowconfigure(1, weight=0) # Controls area does not expand
        main_viewer_frame.grid_columnconfigure(0, weight=1)


        self.image_label = tk.Label(main_viewer_frame, background=PICSNEST_VIEWER_BG, anchor="center") 
        self.image_label.grid(row=0, column=0, sticky="nsew", padx=10, pady=10) 
        self.tk_image = None 

        controls_frame = ttk.Frame(main_viewer_frame, style="PicsNest.Dark.TFrame") 
        controls_frame.grid(row=1, column=0, sticky="ew", pady=(5,10)) # south-east-west

        buttons_inner_frame = ttk.Frame(controls_frame, style="PicsNest.Dark.TFrame")
        buttons_inner_frame.pack() # Use pack within this smaller centered frame

        self.prev_button = ttk.Button(buttons_inner_frame, text="< Previous", command=self.show_prev_image, style="PicsNest.Tool.TButton")
        self.prev_button.pack(side=tk.LEFT, padx=5)

        self.filename_label = ttk.Label(buttons_inner_frame, text="", anchor="center", 
                                        style="PicsNest.Status.TLabel", foreground=PICSNEST_TEXT_LIGHT, background=PICSNEST_BG_DARK)
        self.filename_label.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=10)

        self.next_button = ttk.Button(buttons_inner_frame, text="Next >", command=self.show_next_image, style="PicsNest.Tool.TButton")
        self.next_button.pack(side=tk.LEFT, padx=5)

        self.delete_button = ttk.Button(buttons_inner_frame, text="Delete", command=self.delete_current_image, style="PicsNest.Danger.TButton")
        self.delete_button.pack(side=tk.LEFT, padx=10)

        self.bind("<Left>", lambda e: self.show_prev_image())
        self.bind("<Right>", lambda e: self.show_next_image())
        self.bind("<Escape>", lambda e: self.on_close())
        self.bind("<Delete>", lambda e: self.delete_current_image())
        # Remove the <Configure> binding to stop automatic reloading/resizing on window configure events
        # self.bind("<Configure>", self.on_resize) 
        self.main_viewer_frame_ref = main_viewer_frame # Store ref if needed for manual resize later
        self.after(100, self.initial_load_and_resize) # Load and resize once after window is mapped

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        # self.load_image() # Moved to initial_load_and_resize

    def initial_load_and_resize(self):
        """Loads the first image and attempts to resize it once."""
        self.load_image(is_initial_load=True)

    # def on_resize(self, event=None): # Kept for manual resize logic if re-enabled
    #     if hasattr(self, '_resize_job'):
    #         self.after_cancel(self._resize_job)
    #     self._resize_job = self.after(150, self.load_image) # Debounce resize

    def load_image(self, is_initial_load=False): # Added flag
        if not self.image_paths or not (0 <= self.current_image_index < len(self.image_paths)):
            self.image_label.config(image='', text="No image to display or index out of bounds.", 
                                    fg=PICSNEST_TEXT_LIGHT, bg=PICSNEST_VIEWER_BG)
            if hasattr(self, 'filename_label'): 
                self.filename_label.config(text="")
            self.update_nav_buttons_state()
            self.tk_image = None 
            return

        image_path = self.image_paths[self.current_image_index]

        if not os.path.exists(image_path):
            self.image_label.config(image='', text=f"Error: File not found\n{image_path}", 
                                    fg=PICSNEST_TEXT_LIGHT, bg=PICSNEST_VIEWER_BG)
            if hasattr(self, 'filename_label'):
                self.filename_label.config(text=f"File not found: {os.path.basename(image_path)}")
            self.tk_image = None
            self.image_paths.pop(self.current_image_index)
            if not self.image_paths:
                self.on_close(); return
            if self.current_image_index >= len(self.image_paths) and len(self.image_paths) > 0:
                 self.current_image_index = len(self.image_paths) - 1
            self.load_image(); 
            return

        if hasattr(self, 'filename_label'):
            self.filename_label.config(text=os.path.basename(image_path))
        self.title(f"PicsNest - {os.path.basename(image_path)}")

        try:
            img_pil_original = Image.open(image_path) # Load original once
            img_pil = img_pil_original.copy() # Work with a copy for orientation/conversion
            
            try: 
                exif = img_pil.getexif()
                orientation_tag = 274
                if orientation_tag in exif:
                    orientation = exif[orientation_tag]
                    if orientation == 3: img_pil = img_pil.rotate(180, expand=True)
                    elif orientation == 6: img_pil = img_pil.rotate(-90, expand=True)
                    elif orientation == 8: img_pil = img_pil.rotate(90, expand=True)
            except Exception: pass

            if img_pil.mode == 'P': img_pil = img_pil.convert('RGBA')
            elif img_pil.mode not in ('RGB', 'RGBA'): img_pil = img_pil.convert('RGB')

            # Only resize based on container for initial load, or if user triggers resize (not implemented yet)
            # For next/prev, try to maintain aspect ratio based on *original* image dims and current window size.
            
            # Ensure image_label container is ready to give dimensions
            self.image_label.update_idletasks()
            container_w = self.image_label.winfo_width()
            container_h = self.image_label.winfo_height()

            # If the image label hasn't been drawn yet (e.g., on very first load before window map),
            # try to get dimensions from its parent (main_viewer_frame_ref) and estimate controls height
            if container_w <= 1 or container_h <= 1:
                self.main_viewer_frame_ref.update_idletasks()
                parent_w = self.main_viewer_frame_ref.winfo_width()
                parent_h = self.main_viewer_frame_ref.winfo_height()
                
                # Estimate controls height (this is tricky, could hardcode or get actuals if widgets exist)
                # This part is less critical now due to grid layout for controls
                controls_h_estimate = 60 # A rough estimate
                if hasattr(self, 'prev_button') and self.prev_button.winfo_exists(): # Try to get actual height
                    controls_h_estimate = self.prev_button.master.master.winfo_height() + 10 # controls_frame height + padding

                container_w = parent_w - 20 # -20 for padding
                container_h = parent_h - controls_h_estimate # Adjust for controls


            if container_w <=1 or container_h <=1: # Fallback if still not good
                # This means window isn't fully ready, might happen on fast next/prev before UI updates
                # Default to a reasonable size, image will be scaled down if too big
                container_w, container_h = self.winfo_width() - 20, self.winfo_height() - 80

            img_w, img_h = img_pil.size
            if img_w == 0 or img_h == 0: raise ValueError("Image has zero dimension")

            ratio = min(1.0, container_w / img_w, container_h / img_h) # Don't scale up beyond 100% unless container is huge
            new_w = int(img_w * ratio)
            new_h = int(img_h * ratio)

            if new_w > 0 and new_h > 0:
                img_resized = img_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
                self.tk_image = ImageTk.PhotoImage(img_resized)
                self.image_label.config(image=self.tk_image, text="")
            else:
                self.image_label.config(image='', text="Error resizing image.", fg=PICSNEST_TEXT_LIGHT, bg=PICSNEST_VIEWER_BG)
                self.tk_image = None

        except UnidentifiedImageError:
            self.image_label.config(image='', text=f"Error: Cannot identify image file\n{image_path}", fg=PICSNEST_TEXT_LIGHT, bg=PICSNEST_VIEWER_BG)
            self.tk_image = None
        except Exception as e:
            self.image_label.config(image='', text=f"Error loading image:\n{e}", fg=PICSNEST_TEXT_LIGHT, bg=PICSNEST_VIEWER_BG)
            self.tk_image = None
            
        self.update_nav_buttons_state()

    def show_prev_image(self): 
        if self.current_image_index > 0:
            self.image_label.config(image='') 
            self.update_idletasks() 
            self.current_image_index -= 1
            self.load_image()

    def show_next_image(self): 
        if self.current_image_index < len(self.image_paths) - 1:
            self.image_label.config(image='') 
            self.update_idletasks()
            self.current_image_index += 1
            self.load_image()

    def delete_current_image(self): 
        if not self.image_paths or not (0 <= self.current_image_index < len(self.image_paths)): return
        path_to_delete = self.image_paths[self.current_image_index]
        
        deleted_successfully = self.main_app.delete_selected_items_action_entry(items_to_delete_override={path_to_delete}, from_viewer=True)
        
        if deleted_successfully:
            self.items_deleted_from_viewer = True 
            self.image_paths.pop(self.current_image_index)
            if not self.image_paths: self.on_close(); return
            self.current_image_index = min(self.current_image_index, len(self.image_paths) - 1)
            self.load_image() 

    def update_nav_buttons_state(self):
        if hasattr(self, 'prev_button') and self.prev_button.winfo_exists():
            self.prev_button.config(state=tk.NORMAL if self.current_image_index > 0 else tk.DISABLED)
        if hasattr(self, 'next_button') and self.next_button.winfo_exists():
            self.next_button.config(state=tk.NORMAL if self.current_image_index < len(self.image_paths) - 1 else tk.DISABLED)
        if hasattr(self, 'delete_button') and self.delete_button.winfo_exists():
            self.delete_button.config(state=tk.NORMAL if self.image_paths else tk.DISABLED)

    def on_close(self): 
        if hasattr(self, '_resize_job'): self.after_cancel(self._resize_job)
        
        if self.main_app and self.main_app.root.winfo_exists():
            if self.items_deleted_from_viewer: 
                current_folder = self.main_app.current_folder.get()
                if isinstance(current_folder, str) and os.path.isdir(current_folder):
                     self.main_app.load_items(current_folder) 
            else:
                self.main_app.update_ui_state() 
        self.destroy()