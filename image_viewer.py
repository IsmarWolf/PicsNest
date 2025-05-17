# image_viewer.py

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, UnidentifiedImageError
import os
from constants import IMAGE_VIEWER_BG 

class ImageViewerWindow(tk.Toplevel):
    def __init__(self, parent, image_paths_list, current_index, main_app_ref):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.focus_set()

        self.image_paths = list(image_paths_list)
        self.current_image_index = current_index
        self.main_app = main_app_ref
        self.items_deleted_from_viewer = False # New flag

        self.title("Image Viewer")
        self.geometry("800x650")
        self.configure(bg=IMAGE_VIEWER_BG) 

        self.image_label = tk.Label(self, background=IMAGE_VIEWER_BG, anchor="center") 
        self.image_label.pack(expand=True, fill=tk.BOTH, padx=10, pady=10) 
        self.tk_image = None 

        controls_frame = ttk.Frame(self) 
        controls_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)

        buttons_inner_frame = ttk.Frame(controls_frame)
        buttons_inner_frame.pack()

        self.prev_button = ttk.Button(buttons_inner_frame, text="< Previous", command=self.show_prev_image)
        self.prev_button.pack(side=tk.LEFT, padx=5)

        self.filename_label = ttk.Label(buttons_inner_frame, text="", anchor="center")
        if IMAGE_VIEWER_BG.lower() in ["black", "#000000"]:
            self.filename_label.configure(foreground="white", background=IMAGE_VIEWER_BG)
        else:
            s = ttk.Style()
            control_bg = s.lookup("TFrame", "background") 
            self.filename_label.configure(background=control_bg)


        self.filename_label.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=10)

        self.next_button = ttk.Button(buttons_inner_frame, text="Next >", command=self.show_next_image)
        self.next_button.pack(side=tk.LEFT, padx=5)

        self.delete_button = ttk.Button(buttons_inner_frame, text="Delete", command=self.delete_current_image)
        self.delete_button.pack(side=tk.LEFT, padx=10)

        self.bind("<Left>", lambda e: self.show_prev_image())
        self.bind("<Right>", lambda e: self.show_next_image())
        self.bind("<Escape>", lambda e: self.on_close())
        self.bind("<Delete>", lambda e: self.delete_current_image())
        self.bind("<Configure>", self.on_resize)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.load_image() 

    def on_resize(self, event=None):
        if hasattr(self, '_resize_job'):
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(150, self.load_image)

    def load_image(self):
        if not self.image_paths or not (0 <= self.current_image_index < len(self.image_paths)):
            self.image_label.config(image='', text="No image to display or index out of bounds.")
            self.filename_label.config(text="")
            self.update_nav_buttons_state()
            self.tk_image = None 
            return

        image_path = self.image_paths[self.current_image_index]

        if not os.path.exists(image_path):
            self.image_label.config(image='', text=f"Error: File not found\n{image_path}")
            self.filename_label.config(text=f"File not found: {os.path.basename(image_path)}")
            self.tk_image = None
            original_len = len(self.image_paths)
            self.image_paths.pop(self.current_image_index)
            if not self.image_paths:
                self.on_close(); return
            if self.current_image_index >= len(self.image_paths) and len(self.image_paths) > 0:
                 self.current_image_index = len(self.image_paths) - 1
            self.load_image(); return


        self.filename_label.config(text=os.path.basename(image_path))
        self.title(f"Image Viewer - {os.path.basename(image_path)}")

        try:
            img_pil = Image.open(image_path)
            
            try: 
                exif = img_pil.getexif()
                orientation_tag = 274
                if orientation_tag in exif:
                    orientation = exif[orientation_tag]
                    if orientation == 3: img_pil = img_pil.rotate(180, expand=True)
                    elif orientation == 6: img_pil = img_pil.rotate(-90, expand=True)
                    elif orientation == 8: img_pil = img_pil.rotate(90, expand=True)
            except Exception: 
                pass

            if img_pil.mode == 'P': 
                img_pil = img_pil.convert('RGBA')
            elif img_pil.mode not in ('RGB', 'RGBA'): 
                img_pil = img_pil.convert('RGB')

            self.update_idletasks() 
            
            container_w = self.image_label.winfo_width()
            container_h = self.image_label.winfo_height()

            if container_w <= 1 or container_h <= 1: 
                container_w = self.winfo_width() - 20 
                container_h = self.winfo_height() - (self.filename_label.winfo_height() + self.prev_button.winfo_height() + 40) 
            if container_w <=1 or container_h <=1: 
                container_w, container_h = 600, 400


            img_w, img_h = img_pil.size
            if img_w == 0 or img_h == 0: 
                raise ValueError("Image has zero dimension")

            ratio = min(container_w / img_w, container_h / img_h)
            new_w = int(img_w * ratio)
            new_h = int(img_h * ratio)

            if new_w > 0 and new_h > 0:
                img_resized = img_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
                self.tk_image = ImageTk.PhotoImage(img_resized)
                self.image_label.config(image=self.tk_image, text="")
            else:
                self.image_label.config(image='', text="Error resizing image.")
                self.tk_image = None

        except UnidentifiedImageError:
            self.image_label.config(image='', text=f"Error: Cannot identify image file\n{image_path}")
            self.tk_image = None
        except Exception as e:
            self.image_label.config(image='', text=f"Error loading image:\n{e}")
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

    def delete_current_image(self): # MODIFIED
        if not self.image_paths or not (0 <= self.current_image_index < len(self.image_paths)): return
        path_to_delete = self.image_paths[self.current_image_index]
        
        deleted_successfully = self.main_app.delete_selected_items_action_entry(items_to_delete_override={path_to_delete}, from_viewer=True)
        
        if deleted_successfully:
            self.items_deleted_from_viewer = True # Mark deletion
            self.image_paths.pop(self.current_image_index)
            if not self.image_paths: self.on_close(); return
            self.current_image_index = min(self.current_image_index, len(self.image_paths) - 1)
            self.load_image() 

    def update_nav_buttons_state(self):
        self.prev_button.config(state=tk.NORMAL if self.current_image_index > 0 else tk.DISABLED)
        self.next_button.config(state=tk.NORMAL if self.current_image_index < len(self.image_paths) - 1 else tk.DISABLED)
        self.delete_button.config(state=tk.NORMAL if self.image_paths else tk.DISABLED)

    def on_close(self): # MODIFIED
        if hasattr(self, '_resize_job'): self.after_cancel(self._resize_job)
        
        if self.main_app and self.main_app.root.winfo_exists():
            if self.items_deleted_from_viewer: # Only reload if items were deleted from this viewer
                current_folder = self.main_app.current_folder.get()
                if isinstance(current_folder, str) and os.path.isdir(current_folder):
                     self.main_app.load_items(current_folder) 
            else:
                self.main_app.update_ui_state() # Just update button states etc.
        self.destroy()