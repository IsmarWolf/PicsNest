import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
import sys
import subprocess
import threading
import queue
import time
import json
import shutil
import math
import collections # For deque (Undo stack)
from datetime import datetime

from image_viewer import ImageViewerWindow
from video_viewer import VideoViewerWindow # For date formatting

# --- External Libraries ---
try:
    from PIL import Image, ImageTk, UnidentifiedImageError
except ImportError:
    messagebox.showerror("Error", "Pillow library not found.\nPlease install it using: pip install Pillow")
    sys.exit(1)

try:
    import vlc
except ImportError:
    vlc = None

try:
    import imagehash
except ImportError:
    imagehash = None

try:
    import cv2 # OpenCV for video thumbnails
except ImportError:
    cv2 = None

# --- Constants ---
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp')
VIDEO_EXTENSIONS = ('.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv')
GRID_THUMBNAIL_SIZE = (120, 120)
PREVIEW_THUMBNAIL_SIZE = (350, 350) 
PREVIEW_CONTAINER_SIZE = (350, 350) 
GRID_COLUMNS = 5
LAZY_LOAD_BATCH_SIZE = 20
UNDO_STACK_MAX_SIZE = 10

# --- Colors & Styles ---
FOLDER_COLOR = "#F4D37B"
PLACEHOLDER_COLOR = "#EAEAEA"
FILE_COLOR = "#FFFFFF"
SELECTED_COLOR = "#ADD8E6"
ERROR_COLOR = "#FF9999"
SIMILAR_COLOR = "#FFD700"
LOADING_TEXT = "..."
IMAGE_VIEWER_BG = "black" 

# --- Configuration ---
CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
FOLDER_THUMB_DB_FILENAME = "folder_thumbs.json"
TRASH_DIR_NAME = ".app_trash_v3"

# --- Application Class ---
class PhotoVideoManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Photo & Video Manager")
        self.root.geometry("1250x800")

        self.CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
        self.FOLDER_THUMB_DB_FILE = os.path.join(self.CONFIG_DIR, FOLDER_THUMB_DB_FILENAME)
        self.TRASH_DIR = os.path.join(self.CONFIG_DIR, TRASH_DIR_NAME) 
        os.makedirs(self.TRASH_DIR, exist_ok=True)


        self.current_folder = tk.StringVar(value="No folder selected")
        self.folder_history = []
        self.items_in_view = {}

        self.selected_item_paths = set()

        self.thumbnail_queue = queue.Queue()
        self.active_thumbnail_thread = None
        self.cancel_long_operation = threading.Event()

        self.folder_thumb_db = self._load_folder_thumb_db()

        self.all_folder_items_raw = []
        self.all_folder_items = []
        self.displayed_item_count = 0
        self.current_grid_row = 0
        self.current_grid_col = 0
        self.is_loading_batch = False

        self.rubber_band_rect = None
        self.rubber_band_start_x = 0
        self.rubber_band_start_y = 0

        self.undo_stack = collections.deque(maxlen=UNDO_STACK_MAX_SIZE)

        self.show_only_similar_var = tk.BooleanVar(value=False)
        self.show_images_var = tk.BooleanVar(value=True)
        self.show_videos_var = tk.BooleanVar(value=True)

        self.similar_image_groups = []
        self.image_hashes_cache = {}
        self.marked_similar_paths = set()
        self.is_finding_similar = False
        self.similarity_threshold = 5 
        self._was_filter_active_before_style_refresh = False
        self._similarity_scan_done_for_current_folder = False

        self.root.grid_columnconfigure(0, weight=3)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        self._create_menu()
        self._create_top_bar()
        self._create_main_content_area()
        self._create_preview_area() 
        self._create_action_bar()
        self._apply_styles()

        self.root.after(100, self._process_thumbnail_queue)
        self.update_ui_state()

        self.root.bind("<Delete>", self.on_delete_key_press)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        if vlc is None:
            messagebox.showwarning("VLC Warning", "VLC library (python-vlc) not found. Video playback features will be limited or disabled.\nPlease install it for full video support (e.g., 'pip install python-vlc').")
        if imagehash is None:
             messagebox.showwarning("ImageHash Warning", "The 'imagehash' library is not found. 'Find Similar Images' feature will be disabled.\nPlease install it: pip install imagehash")
        if cv2 is None:
            messagebox.showwarning("OpenCV Warning", "The 'opencv-python' (cv2) library is not found. Video thumbnails will not be generated.\nPlease install it: pip install opencv-python")

    def on_closing(self):
        self._save_folder_thumb_db()
        self.cancel_long_operation.set() 
        self.root.destroy()

    def _load_folder_thumb_db(self):
        try:
            if os.path.exists(self.FOLDER_THUMB_DB_FILE): 
                with open(self.FOLDER_THUMB_DB_FILE, 'r') as f:
                    content = f.read()
                    return json.loads(content if content else '{}')
            return {}
        except json.JSONDecodeError:
            print(f"Error decoding JSON from {self.FOLDER_THUMB_DB_FILE}. Returning empty DB.")
            return {}
        except Exception as e:
            print(f"Error loading folder thumb DB: {e}")
            return {}

    def _save_folder_thumb_db(self):
        try:
            with open(self.FOLDER_THUMB_DB_FILE, 'w') as f: 
                json.dump(self.folder_thumb_db, f, indent=4)
        except Exception as e:
            print(f"Error saving folder thumb DB: {e}")

    def _create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Select Root Folder...", command=self.select_root_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)

        self.edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=self.edit_menu)
        self.edit_menu.add_command(label="Undo", command=self._undo_last_action, state=tk.DISABLED)

        self.view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=self.view_menu)
        self.view_menu.add_checkbutton(label="Show Images", variable=self.show_images_var, command=self.apply_all_filters_and_refresh)
        self.view_menu.add_checkbutton(label="Show Videos", variable=self.show_videos_var, command=self.apply_all_filters_and_refresh)
        self.view_menu.add_separator()
        self.view_menu.add_checkbutton(label="Show Only Similar Images", variable=self.show_only_similar_var, command=self.handle_show_similar_toggle)

        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Find Similar Images in Current Folder", command=self._find_similar_images_action)
        tools_menu.add_command(label="Consolidate Media from Root...", command=self._consolidate_media_action)
        tools_menu.add_command(label="Organize Media by Date from Root...", command=self._organize_media_by_date_action)
        tools_menu.add_separator()
        tools_menu.add_command(label="Delete All Errored Items...", command=self._delete_all_errored_action)
        tools_menu.add_command(label="Move All Errored Items To...", command=self._move_all_errored_action)

    def _create_top_bar(self):
        top_frame = ttk.Frame(self.root, padding="5")
        top_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        
        self.up_button = ttk.Button(top_frame, text="Up", command=self.navigate_up, state=tk.DISABLED)
        self.up_button.pack(side=tk.LEFT, padx=(0, 5))
        
        folder_label = ttk.Label(top_frame, textvariable=self.current_folder, relief="sunken", padding="2")
        folder_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.status_label = ttk.Label(top_frame, text="", width=35) 
        self.status_label.pack(side=tk.LEFT, padx=10)

    def _create_main_content_area(self):
        content_frame = ttk.Frame(self.root, padding=(5, 0, 0, 0))
        content_frame.grid(row=1, column=0, sticky="nsew")
        content_frame.grid_rowconfigure(0, weight=1)
        content_frame.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(content_frame, borderwidth=0, background="#ffffff")
        self.item_frame = ttk.Frame(self.canvas, padding="5", style="View.TFrame")
        self.canvas.create_window((0, 0), window=self.item_frame, anchor="nw", tags="self.item_frame")
        vsb = ttk.Scrollbar(content_frame, orient="vertical", command=self.canvas.yview)
        hsb = ttk.Scrollbar(content_frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.item_frame.bind("<Configure>", self.on_frame_configure)
        if sys.platform == "win32" or sys.platform == "darwin":
             self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        else:
             self.canvas.bind_all("<Button-4>", lambda e: self._on_mousewheel(e, direction=-1))
             self.canvas.bind_all("<Button-5>", lambda e: self._on_mousewheel(e, direction=1))
        
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press_for_rubber_band)
        self.canvas.bind("<B1-Motion>", self._on_canvas_motion_for_rubber_band)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release_for_rubber_band)

    def _create_preview_area(self): 
        preview_area_lf = ttk.LabelFrame(self.root, text="Preview & Info", padding="10")
        preview_area_lf.grid(row=1, column=1, sticky="nsew", padx=(5, 5), pady=(0, 5))
        preview_area_lf.grid_columnconfigure(0, weight=1)
        preview_area_lf.grid_rowconfigure(0, weight=3) 
        preview_area_lf.grid_rowconfigure(1, weight=1)  

        self.preview_image_container = ttk.Frame(preview_area_lf, 
                                                 width=PREVIEW_CONTAINER_SIZE[0], 
                                                 height=PREVIEW_CONTAINER_SIZE[1])
        self.preview_image_container.grid_propagate(False) 
        self.preview_image_container.grid(row=0, column=0, sticky="nsew", pady=(0,10))
        
        self.preview_label = ttk.Label(self.preview_image_container, text="Select an item", anchor="center", background="lightgrey")
        self.preview_label.pack(expand=True, fill=tk.BOTH) 
        self.preview_image_obj = None 

        info_subframe = ttk.Frame(preview_area_lf)
        info_subframe.grid(row=1, column=0, sticky="nsew", pady=(10,0))
        self.info_name_label = ttk.Label(info_subframe, text="Name: -", wraplength=PREVIEW_CONTAINER_SIZE[0] - 20)
        self.info_name_label.pack(anchor="w", pady=1)
        self.info_size_label = ttk.Label(info_subframe, text="Size: -")
        self.info_size_label.pack(anchor="w", pady=1)
        self.info_type_label = ttk.Label(info_subframe, text="Type: -")
        self.info_type_label.pack(anchor="w", pady=1)

    def _create_action_bar(self):
        action_frame = ttk.Frame(self.root, padding="5")
        action_frame.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.open_button = ttk.Button(action_frame, text="Open/View", command=self.open_selected_item_action, state=tk.DISABLED)
        self.open_button.pack(side=tk.LEFT, padx=5)
        self.delete_button = ttk.Button(action_frame, text="Delete Selected", command=self.delete_selected_items_action, state=tk.DISABLED)
        self.delete_button.pack(side=tk.LEFT, padx=5)
        self.undo_button = ttk.Button(action_frame, text="Undo", command=self._undo_last_action, state=tk.DISABLED)
        self.undo_button.pack(side=tk.LEFT, padx=5)

    def _apply_styles(self):
        style = ttk.Style()
        try:
             if 'vista' in style.theme_names(): style.theme_use('vista')
             elif 'clam' in style.theme_names(): style.theme_use('clam')
        except tk.TclError: pass
        style.configure("View.TFrame", background="#ffffff")
        style.configure("Item.TFrame", background=PLACEHOLDER_COLOR, borderwidth=1, relief='raised')
        style.configure("ItemLoaded.TFrame", background=FILE_COLOR, borderwidth=1, relief='raised')
        style.configure("Folder.TFrame", background=FOLDER_COLOR, borderwidth=1, relief='raised')
        style.configure("Selected.TFrame", background=SELECTED_COLOR, borderwidth=2, relief='solid')
        style.configure("Error.TFrame", background=ERROR_COLOR, borderwidth=1, relief='raised')
        style.configure("Similar.TFrame", background=SIMILAR_COLOR, borderwidth=2, relief='solid')

    def on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_mousewheel(self, event, direction=None):
        delta = 0
        if direction is not None: delta = direction
        elif sys.platform == "win32": delta = -1 * int(event.delta / 120)
        elif sys.platform == "darwin": delta = event.delta
        if delta != 0:
            self.canvas.yview_scroll(delta, "units")
            self.root.after_idle(self.on_scroll_check_lazy_load)

    def on_scroll_check_lazy_load(self):
        if self.is_loading_batch or self.displayed_item_count >= len(self.all_folder_items): return
        self.canvas.update_idletasks()
        scroll_info = self.canvas.yview()
        if (scroll_info[1] > 0.85 or \
           (scroll_info[0] == 0.0 and scroll_info[1] == 1.0 and self.item_frame.winfo_height() < self.canvas.winfo_height())) \
           and self.displayed_item_count < len(self.all_folder_items):
            self._load_next_batch_of_items()
            
    def _on_canvas_press_for_rubber_band(self, event):
        self._clear_all_selection_visuals() 
        self.selected_item_paths.clear()
        
        self.rubber_band_start_x = self.canvas.canvasx(event.x)
        self.rubber_band_start_y = self.canvas.canvasy(event.y)
        if self.rubber_band_rect:
            self.canvas.delete(self.rubber_band_rect)
        self.rubber_band_rect = self.canvas.create_rectangle(
            self.rubber_band_start_x, self.rubber_band_start_y,
            self.rubber_band_start_x, self.rubber_band_start_y,
            outline="blue", width=1, dash=(4, 2), tags="rubber_band_tag"
        )
        self.update_preview_and_info() 
        self.update_ui_state()

    def _on_canvas_motion_for_rubber_band(self, event):
        if self.rubber_band_rect:
            cur_x = self.canvas.canvasx(event.x)
            cur_y = self.canvas.canvasy(event.y)
            self.canvas.coords(self.rubber_band_rect, self.rubber_band_start_x, self.rubber_band_start_y, cur_x, cur_y)

    def _on_canvas_release_for_rubber_band(self, event):
        if self.rubber_band_rect:
            self.canvas.delete(self.rubber_band_rect)
            self.rubber_band_rect = None
            end_x = self.canvas.canvasx(event.x)
            end_y = self.canvas.canvasy(event.y)

            sel_x1 = min(self.rubber_band_start_x, end_x)
            sel_y1 = min(self.rubber_band_start_y, end_y)
            sel_x2 = max(self.rubber_band_start_x, end_x)
            sel_y2 = max(self.rubber_band_start_y, end_y)

            newly_selected_paths = set()
            for item_path, info in self.items_in_view.items():
                widget = info['widget']
                if not widget.winfo_exists(): continue
                
                x, y = widget.winfo_x(), widget.winfo_y() 
                w, h = widget.winfo_width(), widget.winfo_height()
                
                if not (sel_x2 < x or sel_x1 > x + w or sel_y2 < y or sel_y1 > y + h):
                    newly_selected_paths.add(item_path)
            
            if newly_selected_paths:
                self.selected_item_paths = newly_selected_paths 
                for path in self.selected_item_paths: 
                    if path in self.items_in_view and self.items_in_view[path]['widget'].winfo_exists():
                        style = self._get_item_style(path, self.items_in_view[path]) 
                        self.items_in_view[path]['widget'].configure(style=style)
            
            self.update_preview_and_info()
            self.update_ui_state()

    def select_root_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path: 
            self.folder_history = []
            self.load_items(folder_path)

    def navigate_to_folder(self, folder_path):
        if os.path.isdir(folder_path) and self.current_folder.get() != folder_path:
            self.folder_history.append(self.current_folder.get())
            self.load_items(folder_path)
        elif not os.path.isdir(folder_path): messagebox.showerror("Error", "Not a valid folder.")

    def navigate_up(self):
        if self.folder_history: 
            self.load_items(self.folder_history.pop())

    def _thumbnail_generator_thread(self, items_to_process, cancel_event):
        for item in items_to_process:
            if cancel_event.is_set(): break
            thumb_image, error_flag = None, False
            try:
                if item['type'] == 'file':
                    _, ext = os.path.splitext(item['name']); ext_lower = ext.lower()
                    if ext_lower in IMAGE_EXTENSIONS:
                        img = Image.open(item['path'])
                        try: 
                            exif = img.getexif(); ot = 274 
                            if ot in exif:
                                o = exif[ot]
                                if o == 3: img = img.rotate(180, expand=True)
                                elif o == 6: img = img.rotate(-90, expand=True)
                                elif o == 8: img = img.rotate(90, expand=True)
                        except Exception: pass 
                        img.thumbnail(GRID_THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                        if img.mode not in ('RGB', 'RGBA'): img = img.convert('RGB')
                        thumb_image = img
                    elif ext_lower in VIDEO_EXTENSIONS and cv2:
                        try:
                            cap = cv2.VideoCapture(item['path'])
                            if cap.isOpened():
                                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                                frame_no = min(frame_count // 10, 100) if frame_count > 10 else 0
                                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
                                ret, frame = cap.read() 
                                if ret:
                                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                    img = Image.fromarray(frame_rgb)
                                    img.thumbnail(GRID_THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                                    thumb_image = img
                            if cap: cap.release() 
                        except Exception as e_vid: print(f"Vid thumb error {item['path']}: {e_vid}")
                self.thumbnail_queue.put({'path': item['path'], 'image': thumb_image, 'error': error_flag, 'type': item['type']})
            except UnidentifiedImageError: self.thumbnail_queue.put({'path': item['path'], 'image': None, 'error': True, 'type': item['type']})
            except Exception as e: print(f"Thumb gen error {item['path']}: {e}"); self.thumbnail_queue.put({'path': item['path'], 'image': None, 'error': True, 'type': item['type']})

    def _get_item_style(self, item_path, item_info):
        is_selected = item_path in self.selected_item_paths
        is_similar = item_path in self.marked_similar_paths
        is_error = item_info.get('is_error', False)
        item_type = item_info['type']

        if is_selected: return "Selected.TFrame"
        if is_similar and item_type == 'file': return "Similar.TFrame" 
        
        if item_type == 'folder': return "Folder.TFrame"
        elif item_type == 'file':
            if is_error: return "Error.TFrame"
            has_thumb_image = 'thumb_label' in item_info and \
                              item_info['thumb_label'].winfo_exists() and \
                              item_info['thumb_label'].cget("image") 
            return "ItemLoaded.TFrame" if has_thumb_image else "Item.TFrame"
        return "Item.TFrame"

    def _process_thumbnail_queue(self):
        max_updates_per_cycle = 10; processed_count = 0
        try:
            while not self.thumbnail_queue.empty() and processed_count < max_updates_per_cycle:
                result = self.thumbnail_queue.get_nowait(); processed_count += 1
                item_path = result['path']
                if item_path in self.items_in_view: 
                    widget_info = self.items_in_view[item_path]
                    widget_frame, thumb_label = widget_info['widget'], widget_info['thumb_label']
                    widget_info['is_error'] = result['error']

                    if widget_frame.winfo_exists() and thumb_label.winfo_exists():
                        final_style = self._get_item_style(item_path, widget_info)
                        widget_frame.configure(style=final_style)

                        if result['error']:
                            thumb_label.config(image='', text="Error", font=("Arial", 9, "bold"), foreground="red")
                            if hasattr(thumb_label, 'image'): thumb_label.image = None
                        elif result['image']:
                            try:
                                 tk_image = ImageTk.PhotoImage(result['image'])
                                 thumb_label.image = tk_image; 
                                 thumb_label.config(image=tk_image, text="")
                            except Exception as e:
                                 print(f"Tkinter PhotoImage error for {item_path}: {e}")
                                 thumb_label.config(image='', text="Display Err", font=("Arial", 8))
                                 widget_info['is_error'] = True
                                 widget_frame.configure(style=self._get_item_style(item_path, widget_info))
                                 if hasattr(thumb_label, 'image'): thumb_label.image = None
                        else: 
                            if item_path.lower().endswith(VIDEO_EXTENSIONS):
                                thumb_label.config(image='', text="📹 Video", font=("Arial", 10, "bold"))
                            if hasattr(thumb_label, 'image'): 
                                thumb_label.image = None
        except queue.Empty: pass
        except Exception as e: print(f"Error processing thumbnail queue: {e}")
        finally: self.root.after(100, self._process_thumbnail_queue)

    def load_items(self, folder_path):
        is_new_folder_context = self.current_folder.get() != folder_path or not self.all_folder_items_raw
        
        if is_new_folder_context:
            self.similar_image_groups = []
            self.image_hashes_cache = {}
            self.marked_similar_paths = set()
            self._similarity_scan_done_for_current_folder = False
            if hasattr(self, 'status_label') and self.status_label: self.status_label.config(text="")
            self._was_filter_active_before_style_refresh = self.show_only_similar_var.get()

        if not os.path.isdir(folder_path): 
            messagebox.showerror("Error", "Cannot access folder.")
            if is_new_folder_context: self.current_folder.set("No folder selected")
            return

        if self.active_thumbnail_thread and self.active_thumbnail_thread.is_alive(): 
            self.cancel_long_operation.set() 
        self.cancel_long_operation.clear()
        
        while not self.thumbnail_queue.empty():
            try: self.thumbnail_queue.get_nowait()
            except queue.Empty: break
        
        self.current_folder.set(folder_path)
        self.clear_view()

        current_raw_items = []
        try:
            for entry in os.scandir(folder_path):
                try: 
                    is_dir, is_file = entry.is_dir(), entry.is_file()
                except OSError: continue
                
                item_type = 'folder' if is_dir else ('file' if is_file else 'other')
                if item_type == 'other': continue
                
                if item_type == 'file':
                    _, ext = os.path.splitext(entry.name); ext_lower = ext.lower()
                    is_image = ext_lower in IMAGE_EXTENSIONS
                    is_video = ext_lower in VIDEO_EXTENSIONS
                    if not ((self.show_images_var.get() and is_image) or \
                            (self.show_videos_var.get() and is_video)):
                        continue 
                current_raw_items.append({'path': entry.path, 'name': entry.name, 'type': item_type, 'is_error': False})
        except OSError as e: 
            messagebox.showerror("Error", f"Error reading folder: {e}")
            self.current_folder.set("Error reading folder"); return
        
        current_raw_items.sort(key=lambda x: (x['type'] != 'folder', x['name'].lower()))
        self.all_folder_items_raw = current_raw_items

        if self.show_only_similar_var.get() and self.marked_similar_paths:
            self.all_folder_items = [
                item for item in self.all_folder_items_raw 
                if item['type'] == 'folder' or \
                   (item['type'] == 'file' and item['path'] in self.marked_similar_paths)
            ]
        else:
            self.all_folder_items = list(self.all_folder_items_raw)

        if self.all_folder_items: 
            self._load_next_batch_of_items()
        else: 
            self.item_frame.update_idletasks()
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
        self.update_ui_state()

    def _load_next_batch_of_items(self):
        if self.is_loading_batch or self.displayed_item_count >= len(self.all_folder_items): return
        self.is_loading_batch = True
        start_index = self.displayed_item_count
        end_index = min(len(self.all_folder_items), start_index + LAZY_LOAD_BATCH_SIZE)
        items_for_this_batch = self.all_folder_items[start_index:end_index]
        
        if not items_for_this_batch: 
            self.is_loading_batch = False; return
            
        self._populate_grid_with_batch(items_for_this_batch)
        self.displayed_item_count = end_index
        
        files_to_process_this_batch = [item for item in items_for_this_batch if item['type'] == 'file']
        if files_to_process_this_batch:
            thread = threading.Thread(target=self._thumbnail_generator_thread, 
                                      args=(files_to_process_this_batch, self.cancel_long_operation), 
                                      daemon=True)
            self.active_thumbnail_thread = thread; thread.start()
            
        self.is_loading_batch = False
        self.root.after_idle(self.on_scroll_check_lazy_load)

    def _populate_grid_with_batch(self, items_in_batch):
        for item in items_in_batch:
            widget_info = self._create_placeholder_widget(self.item_frame, item)
            widget_info['widget'].grid(row=self.current_grid_row, column=self.current_grid_col, padx=5, pady=5, sticky="nsew")
            
            for w in [widget_info['widget'], widget_info['thumb_label'], widget_info['name_label']]:
                w.bind("<Button-1>", lambda e, p=item['path'], wf=widget_info['widget']: 
                    self._on_item_click_for_selection(e, p, wf))
                if item['type'] == 'folder':
                    w.bind("<Double-Button-1>", lambda e, p=item['path']: self.navigate_to_folder(p))
                elif item['type'] == 'file':
                    if item['path'].lower().endswith(IMAGE_EXTENSIONS):
                        w.bind("<Double-Button-1>", lambda e, p=item['path']: self._open_image_viewer_action(p))
                    elif item['path'].lower().endswith(VIDEO_EXTENSIONS):
                        w.bind("<Double-Button-1>", lambda e, p=item['path']: 
                            self._open_video_viewer_action(p) if vlc else self._open_with_system(p))
            
            self.items_in_view[item['path']] = {**widget_info, 'type': item['type'], 'is_error': False}
            self.current_grid_col += 1
            if self.current_grid_col >= GRID_COLUMNS: 
                self.current_grid_col = 0; self.current_grid_row += 1

        for c in range(GRID_COLUMNS): self.item_frame.grid_columnconfigure(c, weight=1)
        self.item_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _create_placeholder_widget(self, parent, item):
        item_path, item_name, item_type = item['path'], item['name'], item['type']
        initial_style_info = {'type': item_type, 'is_error': False}
        style = self._get_item_style(item_path, initial_style_info)

        widget_frame = ttk.Frame(parent, style=style, padding=3)
        thumb_label = ttk.Label(widget_frame, anchor='center')
        thumb_label.pack(fill=tk.BOTH, expand=True)
        name_label = ttk.Label(widget_frame, text=item_name, anchor='center', wraplength=GRID_THUMBNAIL_SIZE[0]-10)
        name_label.pack(fill=tk.X, side=tk.BOTTOM)

        if item_type == 'folder': 
            thumb_label.config(text="FOLDER", font=("Arial", 10, "bold"))
        else: 
            thumb_label.config(text=LOADING_TEXT, font=("Arial", 10))
        
        return {'widget': widget_frame, 'thumb_label': thumb_label, 'name_label': name_label}

    def clear_view(self):
        for widget_info in self.items_in_view.values():
            if widget_info['widget'].winfo_exists(): widget_info['widget'].destroy()
        self.items_in_view.clear(); self.selected_item_paths.clear(); self.reset_preview()
        self.canvas.yview_moveto(0); self.canvas.xview_moveto(0)
        self.item_frame.update_idletasks(); self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.displayed_item_count = 0; self.current_grid_row = 0; self.current_grid_col = 0
        self.is_loading_batch = False

    def _clear_all_selection_visuals(self):
        paths_to_restyle = list(self.selected_item_paths)
        for path in paths_to_restyle:
            if path in self.items_in_view:
                info = self.items_in_view[path]; widget = info['widget']
                if widget.winfo_exists():
                    style = self._get_item_style(path, info) 
                    try: widget.configure(style=style)
                    except tk.TclError: pass

    def _on_item_click_for_selection(self, event, item_path, widget_frame):
        self._clear_all_selection_visuals() 
        self.selected_item_paths = {item_path} 
        if widget_frame.winfo_exists(): 
            style = self._get_item_style(item_path, self.items_in_view[item_path])
            widget_frame.configure(style=style)
        self.update_preview_and_info(); self.update_ui_state()

    def reset_preview(self): 
        # print("DEBUG_PREVIEW: reset_preview called")
        self.preview_label.config(image='', text="Select an item", background="lightgrey")
        self.preview_image_obj = None 
        self.info_name_label.config(text="Name: -")
        self.info_size_label.config(text="Size: -")
        self.info_type_label.config(text="Type: -")

    def update_preview_and_info(self): 
        if not self.selected_item_paths: 
            self.reset_preview()
            return

        if len(self.selected_item_paths) == 1:
            item_path = list(self.selected_item_paths)[0]
            item_info = self.items_in_view.get(item_path) 
            
            # print(f"DEBUG_PREVIEW: Updating for single item: {item_path}") 

            if not item_info or not os.path.exists(item_path):
                # print(f"DEBUG_PREVIEW: Item not in view or does not exist: {item_path}") 
                self.reset_preview()
                self.info_name_label.config(text="Name: Error/Not Found")
                return

            item_type = item_info['type']
            file_name = os.path.basename(item_path)
            self.info_name_label.config(text=f"Name: {file_name}")
            self.info_type_label.config(text=f"Type: {item_type.capitalize()}")

            if item_type == 'file':
                try:
                    size_bytes = os.path.getsize(item_path)
                    self.info_size_label.config(text=f"Size: {size_bytes/(1024*1024):.2f}MB" if size_bytes > 1024*1024 else f"{size_bytes/1024:.1f}KB")
                    
                    # Default to lightgrey, change if image/video thumb is successful
                    preview_bg_color = "lightgrey" 
                    preview_text = "No preview"

                    if item_path.lower().endswith(IMAGE_EXTENSIONS):
                        # print(f"DEBUG_PREVIEW: Is image file for preview: {item_path}") 
                        img_raw = Image.open(item_path)
                        img_prev = img_raw.copy()
                        # print(f"DEBUG_PREVIEW: Opened with Pillow for preview. Mode: {img_prev.mode}, Size: {img_prev.size}") 
                        
                        img_prev.thumbnail(PREVIEW_THUMBNAIL_SIZE, Image.Resampling.LANCZOS) 
                        # print(f"DEBUG_PREVIEW: Thumbnail for preview generated. New size: {img_prev.size}") 
                        
                        if img_prev.mode not in ('RGB','RGBA'): 
                            img_prev = img_prev.convert('RGB')
                            # print(f"DEBUG_PREVIEW: Converted to RGB for preview. New mode: {img_prev.mode}") 
                        
                        self.preview_image_obj = ImageTk.PhotoImage(img_prev) 
                        # print("DEBUG_PREVIEW: ImageTk.PhotoImage for preview created.") 
                        
                        self.preview_label.config(image=self.preview_image_obj, text="")
                        # Use a theme-appropriate background for images, or a specific one like IMAGE_VIEWER_BG
                        # For now, let's use the container's default or a neutral color
                        style = ttk.Style()
                        preview_bg_color = style.lookup("TFrame", "background") # Get default TFrame background
                        # print("DEBUG_PREVIEW: Preview label configured with image.") 

                    elif item_path.lower().endswith(VIDEO_EXTENSIONS) and cv2:
                        # print(f"DEBUG_PREVIEW: Is video file for preview: {item_path}")
                        cap = None
                        try:
                            cap = cv2.VideoCapture(item_path)
                            if cap.isOpened():
                                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                                frame_no = min(frame_count // 10, 100) if frame_count > 10 else 0
                                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
                                ret, frame = cap.read()
                                if ret:
                                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                    img = Image.fromarray(frame_rgb)
                                    img.thumbnail(PREVIEW_THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                                    self.preview_image_obj = ImageTk.PhotoImage(img)
                                    self.preview_label.config(image=self.preview_image_obj, text="")
                                    style = ttk.Style()
                                    preview_bg_color = style.lookup("TFrame", "background")
                                    preview_text = "" # Clear text if image shown
                                    # print("DEBUG_PREVIEW: Video thumbnail for preview created and set.")
                                else:
                                    # print(f"DEBUG_PREVIEW: Video thumbnail - cap.read() failed for {item_path}")
                                    preview_text = "Video (no thumb)"
                            else:
                                # print(f"DEBUG_PREVIEW: Video thumbnail - cap.isOpened() failed for {item_path}")
                                preview_text = "Video (no thumb)"
                        except Exception as e_vid_preview:
                            print(f"DEBUG_PREVIEW: Error generating video preview for {item_path}: {e_vid_preview}")
                            preview_text = "Video (thumb error)"
                            preview_bg_color = ERROR_COLOR # Indicate error
                        finally:
                            if cap: cap.release()
                    
                    self.preview_label.config(text=preview_text, background=preview_bg_color)
                    if not self.preview_image_obj: # If no image was set (e.g. video thumb failed or not image)
                         self.preview_label.config(image='')


                except UnidentifiedImageError:
                    # print(f"DEBUG_PREVIEW: UnidentifiedImageError for preview {item_path}") 
                    self.preview_label.config(image='',text="Preview Error (Format?)", background=ERROR_COLOR)
                    self.preview_image_obj=None
                except Exception as e:
                    # print(f"DEBUG_PREVIEW: Error updating preview for {item_path}: {e}") 
                    # import traceback; traceback.print_exc() 
                    self.preview_label.config(image='',text="Preview Error", background=ERROR_COLOR) 
                    self.preview_image_obj=None
            elif item_type == 'folder':
                # print(f"DEBUG_PREVIEW: Item is a folder: {item_path}") 
                self.info_size_label.config(text="Size: -")
                self.preview_label.config(image='', text="Folder Selected", background="lightgrey")
                self.preview_image_obj=None
        else: 
            # print(f"DEBUG_PREVIEW: Multiple items selected ({len(self.selected_item_paths)})") 
            self.preview_label.config(image='', text=f"{len(self.selected_item_paths)} items selected", background="lightgrey")
            self.preview_image_obj=None
            self.info_name_label.config(text="Name: Multiple items")
            self.info_size_label.config(text="Size: -"); self.info_type_label.config(text="Type: Mixed")

    def _open_image_viewer_action(self, image_path_to_open):
        all_images_in_current_folder = [
            item['path'] for item in self.all_folder_items_raw 
            if item['type'] == 'file' and item['path'].lower().endswith(IMAGE_EXTENSIONS) and os.path.exists(item['path'])
        ]
        if not all_images_in_current_folder:
            if os.path.exists(image_path_to_open): all_images_in_current_folder = [image_path_to_open]
            else: messagebox.showinfo("Viewer", "No images to view."); return
        
        try: current_idx = all_images_in_current_folder.index(image_path_to_open)
        except ValueError:
            if os.path.exists(image_path_to_open):
                all_images_in_current_folder.append(image_path_to_open)
                current_idx = len(all_images_in_current_folder) -1
            else: messagebox.showerror("Error", "Cannot find image for viewer."); return
        ImageViewerWindow(self.root, all_images_in_current_folder, current_idx, self)

    def _open_video_viewer_action(self, video_path_to_open):
        all_videos_in_current_folder = [
            item['path'] for item in self.all_folder_items_raw 
            if item['type'] == 'file' and item['path'].lower().endswith(VIDEO_EXTENSIONS) and os.path.exists(item['path'])
        ]
        if not all_videos_in_current_folder:
            if os.path.exists(video_path_to_open): all_videos_in_current_folder = [video_path_to_open]
            else: messagebox.showinfo("Viewer", "No videos to view."); return
        
        try: current_idx = all_videos_in_current_folder.index(video_path_to_open)
        except ValueError:
            if os.path.exists(video_path_to_open):
                all_videos_in_current_folder.append(video_path_to_open)
                current_idx = len(all_videos_in_current_folder) - 1
            else: messagebox.showerror("Error", "Cannot find video for viewer."); return
        VideoViewerWindow(self.root, all_videos_in_current_folder, current_idx, self)

    def open_selected_item_action(self):
        if not self.selected_item_paths or len(self.selected_item_paths) != 1: return
        item_path = list(self.selected_item_paths)[0]
        item_info = self.items_in_view.get(item_path)
        if not item_info or not os.path.exists(item_path): return
        
        item_type = item_info['type']
        if item_type == 'folder': self.navigate_to_folder(item_path)
        elif item_type == 'file':
            if item_path.lower().endswith(IMAGE_EXTENSIONS): self._open_image_viewer_action(item_path)
            elif item_path.lower().endswith(VIDEO_EXTENSIONS):
                if vlc: self._open_video_viewer_action(item_path)
                else: self._open_with_system(item_path)
            else: self._open_with_system(item_path)

    def _open_with_system(self, path):
        try:
            if sys.platform == "win32": os.startfile(path)
            elif sys.platform == "darwin": subprocess.Popen(["open", path])
            else: subprocess.Popen(["xdg-open", path])
        except Exception as e: messagebox.showerror("Error", f"Could not open: {e}")

    def _add_to_undo_stack(self, action_type, **kwargs):
        self.undo_stack.append({'action_type': action_type, **kwargs})
        self.update_ui_state()

    def _undo_last_action(self): # MODIFIED to attempt scroll restoration
        if not self.undo_stack: return
        
        current_scroll_y = self.canvas.yview()[0]
        current_scroll_x = self.canvas.xview()[0]

        last_action = self.undo_stack.pop()
        action_type = last_action['action_type']
        restored_count = 0
        try:
            if action_type == 'delete_items':
                for original_path, trashed_path in last_action['items']:
                    if os.path.exists(trashed_path):
                        os.makedirs(os.path.dirname(original_path), exist_ok=True)
                        shutil.move(trashed_path, original_path)
                        restored_count +=1
                if restored_count > 0:
                    messagebox.showinfo("Undo", f"Restored {restored_count} item(s).")
        except Exception as e: 
            messagebox.showerror("Undo Error", f"Could not undo: {e}")

        self.load_items(self.current_folder.get()) 
        
        self.canvas.update_idletasks() 
        self.canvas.yview_moveto(current_scroll_y)
        self.canvas.xview_moveto(current_scroll_x)
        
        self.update_ui_state() 

    def on_delete_key_press(self, event=None):
        self.delete_selected_items_action()

    def delete_selected_items_action(self, items_to_delete_override=None, from_viewer=False): # MODIFIED
        paths_to_process = items_to_delete_override if items_to_delete_override else self.selected_item_paths.copy()
        if not paths_to_process: 
            return False

        deleted_for_undo = []
        actually_deleted_count = 0
        items_visually_removed = False

        current_scroll_y = self.canvas.yview()[0] 
        current_scroll_x = self.canvas.xview()[0]

        for item_path in list(paths_to_process): 
            trashed_path_for_undo = None
            if os.path.exists(item_path):
                item_name = os.path.basename(item_path)
                try:
                    trashed_filename = f"{int(time.time())}_{item_name}"
                    actual_trashed_path = os.path.join(self.TRASH_DIR, trashed_filename)
                    
                    self.root.config(cursor="watch"); self.root.update_idletasks()
                    shutil.move(item_path, actual_trashed_path)
                    self.root.config(cursor="")
                    
                    trashed_path_for_undo = actual_trashed_path 
                    deleted_for_undo.append((item_path, trashed_path_for_undo))
                    actually_deleted_count += 1
                except Exception as e:
                    self.root.config(cursor="")
                    messagebox.showerror("Delete Error", f"Could not move '{item_name}' to trash:\n{e}")
                    continue 
            
            if item_path in self.items_in_view:
                widget_info = self.items_in_view.pop(item_path)
                if widget_info['widget'].winfo_exists():
                    widget_info['widget'].destroy()
                items_visually_removed = True
            
            if item_path in self.selected_item_paths:
                self.selected_item_paths.discard(item_path)
            
            self.all_folder_items_raw = [item for item in self.all_folder_items_raw if item['path'] != item_path]
            self.all_folder_items = [item for item in self.all_folder_items if item['path'] != item_path]
            
            if item_path in self.marked_similar_paths:
                self.marked_similar_paths.discard(item_path)
            for group in self.similar_image_groups:
                group.discard(item_path)
            self.similar_image_groups = [g for g in self.similar_image_groups if len(g) > 1]
        
        if deleted_for_undo: 
            self._add_to_undo_stack('delete_items', items=deleted_for_undo)
        
        if not from_viewer: 
            if items_visually_removed:
                self.displayed_item_count = len(self.items_in_view) 
                
                self.item_frame.update_idletasks() 
                self.on_frame_configure() 

                self.canvas.yview_moveto(current_scroll_y)
                self.canvas.xview_moveto(current_scroll_x)

                self.root.after_idle(self.on_scroll_check_lazy_load)

            self.update_preview_and_info() 
            self.update_ui_state() 

        return actually_deleted_count > 0

    def _get_errored_item_paths(self):
        return [path for path, info in self.items_in_view.items() if info.get('is_error') and os.path.exists(path)]

    def _delete_all_errored_action(self):
        errored_paths = self._get_errored_item_paths()
        if not errored_paths: messagebox.showinfo("Info", "No errored items found."); return
        if messagebox.askyesno("Confirm Delete Errored", f"Delete {len(errored_paths)} errored item(s)? (Undoable)", icon='warning'):
            self.delete_selected_items_action(items_to_delete_override=set(errored_paths))

    def _move_all_errored_action(self):
        errored_paths = self._get_errored_item_paths()
        if not errored_paths: messagebox.showinfo("Info", "No errored items found."); return
        dest_folder = filedialog.askdirectory(title=f"Move {len(errored_paths)} errored item(s) to:", mustexist=True)
        if dest_folder and os.path.isdir(dest_folder):
            moved_count = 0
            for item_path in errored_paths:
                item_name = os.path.basename(item_path)
                dest_path = os.path.join(dest_folder, item_name)
                try:
                    if os.path.exists(dest_path): continue 
                    self.root.config(cursor="watch"); self.root.update_idletasks()
                    shutil.move(item_path, dest_path) 
                    moved_count += 1
                except Exception as e: messagebox.showerror("Move Error", f"Could not move '{item_name}':\n{e}"); break
            self.root.config(cursor="")
            if moved_count > 0: messagebox.showinfo("Success", f"{moved_count} item(s) moved."); self.load_items(self.current_folder.get())

    def update_ui_state(self):
        self.up_button.config(state=tk.NORMAL if self.folder_history else tk.DISABLED)
        num_selected = len(self.selected_item_paths)
        can_open_single = num_selected == 1
        can_delete_any = num_selected > 0
        
        self.open_button.config(state=tk.NORMAL if can_open_single else tk.DISABLED)
        self.delete_button.config(state=tk.NORMAL if can_delete_any else tk.DISABLED)
        
        undo_state = tk.NORMAL if self.undo_stack else tk.DISABLED
        self.undo_button.config(state=undo_state)
        if hasattr(self, 'edit_menu'):
            self.edit_menu.entryconfigure("Undo", state=undo_state)

    def handle_show_similar_toggle(self):
        if self.show_only_similar_var.get() and not self._similarity_scan_done_for_current_folder and not self.is_finding_similar:
            if imagehash:
                self.status_label.config(text="Auto-scan for similar...")
                self._find_similar_images_action(triggered_by_filter_toggle=True)
            else:
                messagebox.showwarning("ImageHash Missing", "ImageHash library not found. Cannot find similar images.", parent=self.root)
                self.show_only_similar_var.set(False)
                return
        else:
            self.apply_all_filters_and_refresh()

    def apply_all_filters_and_refresh(self): # This will still cause a full reload
        current_scroll_y = self.canvas.yview()[0]
        current_scroll_x = self.canvas.xview()[0]
        
        current_folder = self.current_folder.get()
        if os.path.isdir(current_folder):
            self.load_items(current_folder) # Full reload for filter changes
        
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(current_scroll_y)
        self.canvas.xview_moveto(current_scroll_x)
        self._was_filter_active_before_style_refresh = self.show_only_similar_var.get()

    def _find_similar_images_action(self, triggered_by_filter_toggle=False):
        if imagehash is None:
            if not triggered_by_filter_toggle:
                messagebox.showerror("Error", "The 'imagehash' library is required for this feature.\nPlease install it: pip install imagehash", parent=self.root)
            return
        if self.is_finding_similar:
            if not triggered_by_filter_toggle:
                messagebox.showinfo("Info", "Already searching for similar images.", parent=self.root)
            return
        
        image_items = [item for item in self.all_folder_items_raw if item['type'] == 'file' and item['path'].lower().endswith(IMAGE_EXTENSIONS)]
        if not image_items:
            if not triggered_by_filter_toggle:
                messagebox.showinfo("Info", "No images in the current folder to compare.", parent=self.root)
            self.status_label.config(text="No images to compare.")
            self._similarity_scan_done_for_current_folder = True
            if triggered_by_filter_toggle:
                self.show_only_similar_var.set(False)
                self.apply_all_filters_and_refresh()
            return

        self.is_finding_similar = True
        self.status_label.config(text="Finding similar images...")
        self.cancel_long_operation.clear()
        
        thread = threading.Thread(target=self._find_similar_images_thread_worker, args=(image_items, triggered_by_filter_toggle), daemon=True)
        thread.start()

    def _find_similar_images_thread_worker(self, image_items_to_process, triggered_by_filter_toggle=False):
        self.image_hashes_cache.clear() 
        item_hashes = []
        total_images = len(image_items_to_process)

        for i, item_data in enumerate(image_items_to_process):
            if self.cancel_long_operation.is_set():
                self.root.after(0, lambda: self.status_label.config(text="Similarity scan cancelled."))
                self.is_finding_similar = False
                return
            path = item_data['path']
            if i % 10 == 0 or i == total_images -1 :
                self.root.after(0, lambda i=i, total=total_images: self.status_label.config(text=f"Hashing {i+1}/{total}"))
            try:
                img = Image.open(path)
                img_hash = imagehash.dhash(img)
                self.image_hashes_cache[path] = img_hash
                item_hashes.append((path, img_hash))
            except Exception as e:
                print(f"Could not hash {path}: {e}")
        
        parent = {path: path for path, _ in item_hashes}
        def find_set(item_path):
            if parent[item_path] == item_path: return item_path
            parent[item_path] = find_set(parent[item_path])
            return parent[item_path]
        def unite_sets(path1, path2):
            path1_root, path2_root = find_set(path1), find_set(path2)
            if path1_root != path2_root: parent[path2_root] = path1_root
        
        num_item_hashes = len(item_hashes)
        for i in range(num_item_hashes):
            if self.cancel_long_operation.is_set():
                self.root.after(0, lambda: self.status_label.config(text="Similarity scan cancelled."))
                self.is_finding_similar = False
                return
            if i % 10 == 0 or i == num_item_hashes -1:
                self.root.after(0, lambda i=i, total=num_item_hashes: self.status_label.config(text=f"Comparing {i+1}/{total}"))
            path1, hash1 = item_hashes[i]
            for j in range(i + 1, num_item_hashes):
                path2, hash2 = item_hashes[j]
                if (hash1 - hash2) <= self.similarity_threshold:
                    unite_sets(path1, path2)

        groups_map = {}
        for path, _ in item_hashes:
            root_path = find_set(path)
            groups_map.setdefault(root_path, set()).add(path)
        
        self.similar_image_groups = [group for group in groups_map.values() if len(group) > 1]
        self.marked_similar_paths.clear()
        for group in self.similar_image_groups:
            self.marked_similar_paths.update(group)

        self.is_finding_similar = False
        self._similarity_scan_done_for_current_folder = True
        msg = f"Found {len(self.similar_image_groups)} groups of similar images."
        self.root.after(0, lambda: self.status_label.config(text=msg))
        
        if not triggered_by_filter_toggle:
            self.root.after(0, lambda: messagebox.showinfo("Similarity Check Complete", msg, parent=self.root))
        
        self.root.after(0, self.apply_all_filters_and_refresh) 

    def _refresh_all_item_visuals(self):
        for path, item_info in self.items_in_view.items():
            if item_info['widget'].winfo_exists():
                style = self._get_item_style(path, item_info)
                try:
                    item_info['widget'].configure(style=style)
                except tk.TclError as e:
                    print(f"Error applying style {style} to {path}: {e}")

    def _consolidate_media_action(self):
        current_root_folder = self.current_folder.get()
        if not os.path.isdir(current_root_folder) or current_root_folder == "No folder selected":
            messagebox.showerror("Error", "Please select a valid root folder first.", parent=self.root)
            return

        destination_folder = filedialog.askdirectory(
            title="Select Destination Folder for All Media",
            parent=self.root
        )
        if not destination_folder:
            return 

        if os.path.abspath(destination_folder).startswith(os.path.abspath(current_root_folder)) and \
           os.path.abspath(destination_folder) != os.path.abspath(current_root_folder):
            if os.path.realpath(destination_folder) == os.path.realpath(current_root_folder):
                 if not messagebox.askyesno("Warning", "Destination is the same as the root folder. This will effectively do nothing but might rename files if conflicts exist. Continue?", parent=self.root):
                     return
            else:
                messagebox.showerror("Error", "Destination folder cannot be inside the current root folder or its subdirectories (unless it's the root itself, which is not recommended).", parent=self.root)
                return

        dialog = tk.Toplevel(self.root)
        dialog.title("Consolidation Options")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text=f"Consolidate media from:\n{current_root_folder}\n\nTo destination:\n{destination_folder}\n").pack(padx=10, pady=10)
        
        action_type_var = tk.StringVar(value="move") 
        ttk.Radiobutton(dialog, text="Move media (original files will be deleted)", variable=action_type_var, value="move").pack(anchor="w", padx=10)
        ttk.Radiobutton(dialog, text="Copy media (original files will be kept)", variable=action_type_var, value="copy").pack(anchor="w", padx=10)
        
        media_to_consolidate_frame = ttk.LabelFrame(dialog, text="Media Types to Consolidate")
        media_to_consolidate_frame.pack(padx=10, pady=5, fill="x")
        consolidate_images_var = tk.BooleanVar(value=True)
        consolidate_videos_var = tk.BooleanVar(value=True) 
        ttk.Checkbutton(media_to_consolidate_frame, text="Images", variable=consolidate_images_var).pack(anchor="w", padx=5)
        ttk.Checkbutton(media_to_consolidate_frame, text="Videos", variable=consolidate_videos_var).pack(anchor="w", padx=5)

        ttk.Label(dialog, text="Handle filename conflicts by:").pack(anchor="w", padx=10, pady=(10,0))
        conflict_resolution_var = tk.StringVar(value="rename") 
        ttk.Radiobutton(dialog, text="Renaming (e.g., file.jpg -> file (1).jpg)", variable=conflict_resolution_var, value="rename").pack(anchor="w", padx=10)
        ttk.Radiobutton(dialog, text="Skipping duplicates", variable=conflict_resolution_var, value="skip").pack(anchor="w", padx=10)
        ttk.Radiobutton(dialog, text="Overwriting duplicates (DANGEROUS!)", variable=conflict_resolution_var, value="overwrite").pack(anchor="w", padx=10)

        def on_proceed():
            action = action_type_var.get()
            conflict_resolution = conflict_resolution_var.get()
            include_images = consolidate_images_var.get()
            include_videos = consolidate_videos_var.get()
            dialog.destroy()

            if not include_images and not include_videos:
                messagebox.showinfo("Info", "No media types selected for consolidation.", parent=self.root)
                return
            
            media_types_str = []
            if include_images: media_types_str.append("images")
            if include_videos: media_types_str.append("videos")
            media_types_display = " and ".join(media_types_str)

            warning_message = (
                f"This will {action} ALL selected {media_types_display} from '{current_root_folder}' and its subfolders "
                f"into '{destination_folder}'.\n"
                "This operation can be very intensive and may take a long time.\n"
                "Original folder structure will NOT be preserved in the destination.\n\n"
                "ARE YOU SURE YOU WANT TO PROCEED?"
            )
            if not messagebox.askyesno("Confirm Consolidation", warning_message, icon='warning', parent=self.root):
                return

            self.status_label.config(text=f"{action.capitalize()}ing {media_types_display}...")
            self.root.config(cursor="watch")
            self.cancel_long_operation.clear() 
            
            thread = threading.Thread(
                target=self._consolidate_media_worker,
                args=(current_root_folder, destination_folder, action, conflict_resolution, include_images, include_videos),
                daemon=True
            )
            thread.start()

        def on_cancel():
            dialog.destroy()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="Proceed", command=on_proceed).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT, padx=5)
        
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

    def _consolidate_media_worker(self, root_dir, dest_dir, action_type, conflict_resolution, include_images, include_videos):
        action_count = 0
        skipped_count = 0
        error_count = 0
        processed_for_status = 0

        found_media = []
        for dirpath, _, filenames in os.walk(root_dir):
            if os.path.commonpath([dirpath, dest_dir]) == os.path.abspath(dest_dir) and os.path.abspath(dirpath) != os.path.abspath(dest_dir):
                continue
            for filename in filenames:
                ext_lower = os.path.splitext(filename)[1].lower()
                is_image = ext_lower in IMAGE_EXTENSIONS
                is_video = ext_lower in VIDEO_EXTENSIONS
                
                if (include_images and is_image) or (include_videos and is_video):
                    found_media.append(os.path.join(dirpath, filename))
        
        total_media_to_process = len(found_media)
        if total_media_to_process == 0:
            self.root.after(0, lambda: self.status_label.config(text="No selected media found to consolidate."))
            self.root.after(0, lambda: self.root.config(cursor=""))
            self.root.after(0, lambda: messagebox.showinfo("Consolidation Complete", "No selected media types found.", parent=self.root))
            return

        for src_path in found_media:
            if self.cancel_long_operation.is_set(): 
                self.root.after(0, lambda: self.status_label.config(text="Consolidation cancelled."))
                break
            
            processed_for_status += 1
            self.root.after(0, lambda current=processed_for_status, total=total_media_to_process: 
                            self.status_label.config(text=f"{action_type.capitalize()}ing: {current}/{total}"))
            
            if os.path.commonpath([src_path, dest_dir]) == os.path.abspath(dest_dir):
                if os.path.dirname(src_path) == os.path.abspath(dest_dir): 
                    skipped_count +=1 
                    continue

            filename = os.path.basename(src_path)
            current_dest_path = os.path.join(dest_dir, filename)

            if os.path.abspath(src_path) == os.path.abspath(current_dest_path):
                skipped_count +=1
                continue

            if os.path.exists(current_dest_path):
                if conflict_resolution == "skip":
                    skipped_count += 1
                    continue
                elif conflict_resolution == "overwrite":
                    pass 
                elif conflict_resolution == "rename":
                    base, ext = os.path.splitext(filename)
                    count = 1
                    while os.path.exists(current_dest_path):
                        current_dest_path = os.path.join(dest_dir, f"{base} ({count}){ext}")
                        count += 1
            
            try:
                if action_type == "move":
                    shutil.move(src_path, current_dest_path)
                elif action_type == "copy":
                    shutil.copy2(src_path, current_dest_path) 
                action_count += 1
            except Exception as e:
                print(f"Error {action_type}ing {src_path} to {current_dest_path}: {e}")
                error_count += 1
            
        self.root.after(0, lambda: self.root.config(cursor=""))
        
        summary_message = f"Media Consolidation Complete!\n\n"
        summary_message += f"Successfully {action_type}d: {action_count}\n"
        summary_message += f"Skipped (already in dest or conflict): {skipped_count}\n"
        summary_message += f"Errors: {error_count}\n"
        summary_message += f"Total media files found: {total_media_to_process}"

        self.root.after(0, lambda msg=summary_message: self.status_label.config(text="Consolidation finished."))
        self.root.after(0, lambda msg=summary_message: messagebox.showinfo("Consolidation Result", msg, parent=self.root))
        
        if os.path.isdir(self.current_folder.get()):
            self.root.after(0, lambda: self.load_items(self.current_folder.get()))

    def _get_media_date(self, file_path):
        ext_lower = os.path.splitext(file_path)[1].lower()
        date_to_use = None

        if ext_lower in IMAGE_EXTENSIONS:
            try:
                img = Image.open(file_path)
                exif_data = img._getexif() 

                if exif_data:
                    date_str = None
                    if 36867 in exif_data: date_str = exif_data[36867] 
                    elif 36868 in exif_data: date_str = exif_data[36868] 
                    elif 306 in exif_data: date_str = exif_data[306] 
                    
                    if date_str and isinstance(date_str, str):
                        date_str_cleaned = date_str.split('\x00')[0].strip()
                        try:
                            date_to_use = datetime.strptime(date_str_cleaned, '%Y:%m:%d %H:%M:%S')
                        except ValueError:
                            try:
                                date_to_use = datetime.strptime(date_str_cleaned, '%Y-%m-%d %H:%M:%S')
                            except ValueError:
                                print(f"Could not parse EXIF date string '{date_str_cleaned}' for {file_path}")
            except UnidentifiedImageError:
                print(f"Cannot identify image file: {file_path}")
            except Exception:
                pass 
        
        if date_to_use is None:
            try:
                mtime_timestamp = os.path.getmtime(file_path)
                date_to_use = datetime.fromtimestamp(mtime_timestamp)
            except OSError as e:
                print(f"Could not get file system date for {file_path}: {e}")
        
        return date_to_use

    def _organize_media_by_date_action(self):
        current_root_folder = self.current_folder.get()
        if not os.path.isdir(current_root_folder) or current_root_folder == "No folder selected":
            messagebox.showerror("Error", "Please select a valid root folder first.", parent=self.root)
            return

        destination_base_folder = filedialog.askdirectory(
            title="Select Base Destination Folder for Dated Subfolders",
            parent=self.root
        )
        if not destination_base_folder:
            return

        if os.path.abspath(destination_base_folder).startswith(os.path.abspath(current_root_folder)) and \
           os.path.abspath(destination_base_folder) != os.path.abspath(current_root_folder):
            if os.path.realpath(destination_base_folder) == os.path.realpath(current_root_folder):
                 if not messagebox.askyesno("Warning", "Destination is the same as the root folder. This will create dated subfolders within the root. Continue?", parent=self.root):
                     return
            else:
                messagebox.showerror("Error", "Base destination folder cannot be inside the current root folder (unless it's the root itself).", parent=self.root)
                return

        dialog = tk.Toplevel(self.root)
        dialog.title("Date Organization Options")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text=f"Organize media from:\n{current_root_folder}\n\nInto dated subfolders inside:\n{destination_base_folder}\n").pack(padx=10, pady=10)

        action_type_var = tk.StringVar(value="move")
        ttk.Radiobutton(dialog, text="Move media (original files will be deleted)", variable=action_type_var, value="move").pack(anchor="w", padx=10)
        ttk.Radiobutton(dialog, text="Copy media (original files will be kept)", variable=action_type_var, value="copy").pack(anchor="w", padx=10)
        
        media_to_organize_frame = ttk.LabelFrame(dialog, text="Media Types to Organize")
        media_to_organize_frame.pack(padx=10, pady=5, fill="x")
        organize_images_var = tk.BooleanVar(value=True)
        organize_videos_var = tk.BooleanVar(value=True) 
        ttk.Checkbutton(media_to_organize_frame, text="Images", variable=organize_images_var).pack(anchor="w", padx=5)
        ttk.Checkbutton(media_to_organize_frame, text="Videos", variable=organize_videos_var).pack(anchor="w", padx=5)

        ttk.Label(dialog, text="Handle filename conflicts (for new names) by:").pack(anchor="w", padx=10, pady=(10,0))
        conflict_resolution_var = tk.StringVar(value="rename_sequential")
        ttk.Radiobutton(dialog, text="Renaming with sequence (e.g., DD-HHMMSS_seq_Orig.ext)", variable=conflict_resolution_var, value="rename_sequential").pack(anchor="w", padx=10)
        ttk.Radiobutton(dialog, text="Skipping duplicates", variable=conflict_resolution_var, value="skip").pack(anchor="w", padx=10)

        def on_proceed():
            action = action_type_var.get()
            conflict_resolution = conflict_resolution_var.get()
            include_images = organize_images_var.get()
            include_videos = organize_videos_var.get()
            dialog.destroy()

            if not include_images and not include_videos:
                messagebox.showinfo("Info", "No media types selected for organization.", parent=self.root)
                return
            
            media_types_str = []
            if include_images: media_types_str.append("images")
            if include_videos: media_types_str.append("videos")
            media_types_display = " and ".join(media_types_str)

            warning_message = (
                f"This will {action} ALL selected {media_types_display} from '{current_root_folder}' and its subfolders "
                f"into dated subfolders (Year/Month) inside '{destination_base_folder}'.\n"
                f"Files will be renamed (e.g., DD-HHMMSS_OriginalName_seq.ext).\n"
                "This operation can be very intensive.\n\n"
                "ARE YOU SURE YOU WANT TO PROCEED?"
            )
            if not messagebox.askyesno("Confirm Date Organization", warning_message, icon='warning', parent=self.root):
                return

            self.status_label.config(text=f"{action.capitalize()}ing & organizing {media_types_display}...")
            self.root.config(cursor="watch")
            self.cancel_long_operation.clear()

            thread = threading.Thread(
                target=self._organize_media_by_date_worker,
                args=(current_root_folder, destination_base_folder, action, conflict_resolution, include_images, include_videos),
                daemon=True
            )
            thread.start()

        def on_cancel():
            dialog.destroy()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="Proceed", command=on_proceed).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT, padx=5)
        
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

    def _organize_media_by_date_worker(self, root_dir, base_dest_dir, action_type, conflict_resolution, include_images, include_videos):
        action_count = 0
        skipped_count = 0
        error_count = 0
        unknown_date_count = 0
        processed_for_status = 0

        found_media = []
        for dirpath, _, filenames in os.walk(root_dir):
            if os.path.commonpath([dirpath, base_dest_dir]) == os.path.abspath(base_dest_dir) and \
               os.path.abspath(dirpath) != os.path.abspath(base_dest_dir):
                continue

            for filename in filenames:
                ext_lower = os.path.splitext(filename)[1].lower()
                is_image = ext_lower in IMAGE_EXTENSIONS
                is_video = ext_lower in VIDEO_EXTENSIONS
                if (include_images and is_image) or (include_videos and is_video):
                    found_media.append(os.path.join(dirpath, filename))
        
        total_media_to_process = len(found_media)
        if total_media_to_process == 0:
            self.root.after(0, lambda: self.status_label.config(text="No selected media found to organize."))
            self.root.after(0, lambda: self.root.config(cursor=""))
            self.root.after(0, lambda: messagebox.showinfo("Organization Complete", "No selected media found.", parent=self.root))
            return

        for src_path in found_media:
            if self.cancel_long_operation.is_set():
                self.root.after(0, lambda: self.status_label.config(text="Organization cancelled."))
                break
            
            processed_for_status += 1
            self.root.after(0, lambda current=processed_for_status, total=total_media_to_process: 
                            self.status_label.config(text=f"Organizing: {current}/{total}"))

            media_date_dt = self._get_media_date(src_path) 
            
            if not media_date_dt:
                unknown_date_count += 1
                unknown_folder = os.path.join(base_dest_dir, "Unknown_Date")
                os.makedirs(unknown_folder, exist_ok=True)
                filename_original = os.path.basename(src_path)
                dest_path_unknown = os.path.join(unknown_folder, filename_original)
                
                if os.path.realpath(src_path) == os.path.realpath(dest_path_unknown):
                    skipped_count +=1; continue

                if os.path.exists(dest_path_unknown):
                    if conflict_resolution == "skip": skipped_count += 1; continue
                    elif conflict_resolution == "rename_sequential": 
                        base, ext = os.path.splitext(filename_original)
                        count = 1
                        while os.path.exists(dest_path_unknown):
                            dest_path_unknown = os.path.join(unknown_folder, f"{base}_{count}{ext}") 
                            count += 1
                try:
                    if action_type == "move": shutil.move(src_path, dest_path_unknown)
                    else: shutil.copy2(src_path, dest_path_unknown)
                    action_count +=1
                except Exception as e: error_count +=1; print(f"Error for unknown date file {src_path}: {e}")
                continue

            year_str = media_date_dt.strftime("%Y")
            month_str = media_date_dt.strftime("%m") 
            day_str = media_date_dt.strftime("%d")   
            time_str = media_date_dt.strftime("%H%M%S") 

            target_subfolder_path = os.path.join(base_dest_dir, year_str, month_str)
            os.makedirs(target_subfolder_path, exist_ok=True)
            
            original_filename_base, original_ext = os.path.splitext(os.path.basename(src_path))
            safe_original_name = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in original_filename_base)
            safe_original_name = safe_original_name[:30] 

            new_filename_base = f"{day_str}-{time_str}_{safe_original_name}"
            
            seq_count = 0
            dest_path = os.path.join(target_subfolder_path, f"{new_filename_base}{original_ext}")
            
            if os.path.realpath(src_path) == os.path.realpath(dest_path):
                skipped_count +=1
                continue

            if os.path.exists(dest_path):
                if conflict_resolution == "skip":
                    skipped_count += 1
                    continue
                elif conflict_resolution == "rename_sequential":
                    seq_count = 1
                    while os.path.exists(dest_path):
                        dest_path = os.path.join(target_subfolder_path, f"{new_filename_base}_{seq_count}{original_ext}")
                        seq_count += 1
            
            try:
                if action_type == "move":
                    shutil.move(src_path, dest_path)
                elif action_type == "copy":
                    shutil.copy2(src_path, dest_path)
                action_count += 1
            except Exception as e:
                print(f"Error {action_type}ing {src_path} to {dest_path}: {e}")
                error_count += 1

        self.root.after(0, lambda: self.root.config(cursor=""))
        
        summary_message = f"Date Organization Complete!\n\n"
        summary_message += f"Successfully {action_type}d: {action_count}\n"
        summary_message += f"Skipped (conflict/same path): {skipped_count}\n"
        summary_message += f"Media with unknown date (moved to 'Unknown_Date'): {unknown_date_count}\n"
        summary_message += f"Errors: {error_count}\n"
        summary_message += f"Total media files found: {total_media_to_process}"

        self.root.after(0, lambda msg=summary_message: self.status_label.config(text="Organization finished."))
        self.root.after(0, lambda msg=summary_message: messagebox.showinfo("Organization Result", msg, parent=self.root))
        
        if os.path.isdir(self.current_folder.get()):
            self.root.after(0, lambda: self.load_items(self.current_folder.get()))