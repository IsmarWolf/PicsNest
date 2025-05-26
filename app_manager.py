#app_manager.py
# --- Imports ---
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser
import os
import sys
import subprocess
import threading
import queue
import time
import json, math, shutil
import collections
from datetime import datetime
import hashlib # Add hashlib for generating unique icon filenames

from image_viewer import ImageViewerWindow
from video_viewer import VideoViewerWindow
from constants import *
from constants import TRASH_MAX_ITEMS, THEME_SETTINGS_FILENAME, CUSTOM_FOLDER_ICONS_DIR_NAME # Add CUSTOM_FOLDER_ICONS_DIR_NAME

try:
    from PIL import Image, ImageTk, UnidentifiedImageError
except ImportError:
    Image = None
    ImageTk = None
    UnidentifiedImageError = None

try:
    import vlc as vlc_module
except ImportError:
    vlc_module = None

try:
    import imagehash as imagehash_module
except ImportError:
    imagehash_module = None

try:
    import cv2 as cv2_module
except ImportError:
    cv2_module = None

from app_manager_utils import ui_creator, file_operations, action_handlers


class PhotoVideoManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PicsNest - Media Manager")
        self.root.geometry("1350x850")

        # Define CONFIG_DIR earlier
        self.CONFIG_DIR = os.path.dirname(os.path.abspath(__file__)) 

        self._load_theme_settings() # Now CONFIG_DIR is available
        self.root.configure(bg=PICSNEST_BG_DARK)
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            logo_path_ico = os.path.join(base_dir, 'picsnest_logo.ico')
            logo_path_png = os.path.join(base_dir, 'picsnest_logo.png')

            if sys.platform == "win32" and os.path.exists(logo_path_ico):
                self.root.iconbitmap(logo_path_ico)
            elif os.path.exists(logo_path_png):
                img = tk.PhotoImage(file=logo_path_png)
                self.root.tk.call('wm', 'iconphoto', self.root._w, img)
            else:
                print("INFO: Window icon file (picsnest_logo.ico/png) not found in app directory. Using default window icon.")
        except tk.TclError as e:
            print(f"INFO: Could not set application window icon: {e}")


        self.Image = Image
        self.ImageTk = ImageTk
        self.UnidentifiedImageError = UnidentifiedImageError
        self.vlc = vlc_module
        self.imagehash = imagehash_module
        self.cv2 = cv2_module

        self.IMAGE_EXTENSIONS = IMAGE_EXTENSIONS
        self.VIDEO_EXTENSIONS = VIDEO_EXTENSIONS
        self.TRASH_MAX_ITEMS = TRASH_MAX_ITEMS

        self.CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
        self.THEME_SETTINGS_FILE = os.path.join(self.CONFIG_DIR, THEME_SETTINGS_FILENAME)
        self.FOLDER_THUMB_DB_FILE = os.path.join(self.CONFIG_DIR, FOLDER_THUMB_DB_FILENAME)
        self.TRASH_DIR = os.path.join(self.CONFIG_DIR, TRASH_DIR_NAME)
        os.makedirs(self.TRASH_DIR, exist_ok=True)

        # New: Directory for custom folder icons
        self.CUSTOM_FOLDER_ICONS_DIR = os.path.join(self.CONFIG_DIR, CUSTOM_FOLDER_ICONS_DIR_NAME)
        os.makedirs(self.CUSTOM_FOLDER_ICONS_DIR, exist_ok=True)


        self.current_folder = tk.StringVar(value="No folder selected")
        self.folder_history = []
        self.items_in_view = {}

        self.selected_item_paths = set()
        self.renaming_item_path = None
        self.name_edit_entry = None
        self.original_name_label = None

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
        self.show_only_screenshots_downloads_var = tk.BooleanVar(value=False) # New filter variable

        self.similar_image_groups = []
        self.image_hashes_cache = {}
        self.marked_similar_paths = set()
        self.marked_screenshot_download_paths = set() # New set for screenshot/download filter
        self.is_finding_similar = False
        self.similarity_threshold = 5
        self._was_filter_active_before_style_refresh = False
        self._similarity_scan_done_for_current_folder = False

        self.root.grid_columnconfigure(0, weight=3)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        ui_creator.apply_app_styles(self)

        ui_creator.create_menu(self)
        ui_creator.create_top_bar(self)
        ui_creator.create_main_content_area(self)
        ui_creator.create_preview_area(self)
        ui_creator.create_action_bar(self)

        self.root.after(100, self._process_thumbnail_queue)
        self.update_ui_state()
        self.show_initial_view()


        self.root.bind("<Delete>", self.on_delete_key_press)
        self.root.bind("<F2>", self.on_f2_key_press)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        if self.vlc is None:
            messagebox.showwarning("VLC Warning", "VLC library (python-vlc) not found. Video playback features will be limited or disabled.\nPlease install it for full video support (e.g., 'pip install python-vlc').", parent=self.root)
        if self.imagehash is None:
             messagebox.showwarning("ImageHash Warning", "The 'imagehash' library is not found. 'Find Similar Images' feature will be disabled.\nPlease install it: pip install imagehash", parent=self.root)
        if self.cv2 is None:
            messagebox.showwarning("OpenCV Warning", "The 'opencv-python' (cv2) library is not found. Video thumbnails will not be generated.\nPlease install it: pip install opencv-python", parent=self.root)
        if self.Image is None or self.ImageTk is None:
            messagebox.showerror("Critical Error", "Pillow library failed to load. Application cannot continue.", parent=self.root)
            self.root.destroy()
            sys.exit(1)

    def _load_theme_settings(self):
        global PICSNEST_USER_ACCENT_COLOR
        try:
            theme_settings_path = os.path.join(self.CONFIG_DIR, THEME_SETTINGS_FILENAME)
            if os.path.exists(theme_settings_path):
                with open(theme_settings_path, 'r') as f:
                    content = f.read()
                    if content.strip():
                        settings = json.loads(content)
                        PICSNEST_USER_ACCENT_COLOR = settings.get("accent_color", PICSNEST_ACCENT_BLUE)
                    else:
                        PICSNEST_USER_ACCENT_COLOR = PICSNEST_ACCENT_BLUE
            else:
                PICSNEST_USER_ACCENT_COLOR = PICSNEST_ACCENT_BLUE
                self._save_theme_settings()
        except json.JSONDecodeError:
            print(f"Error decoding theme settings from {THEME_SETTINGS_FILENAME}. Using default accent.")
            PICSNEST_USER_ACCENT_COLOR = PICSNEST_ACCENT_BLUE
            self._save_theme_settings()
        except Exception as e:
            print(f"Error loading theme settings: {e}. Using default accent.")
            PICSNEST_USER_ACCENT_COLOR = PICSNEST_ACCENT_BLUE

    def _save_theme_settings(self):
        try:
            theme_settings_path = os.path.join(self.CONFIG_DIR, THEME_SETTINGS_FILENAME)
            color_to_save = PICSNEST_USER_ACCENT_COLOR if PICSNEST_USER_ACCENT_COLOR else PICSNEST_ACCENT_BLUE
            settings = {"accent_color": color_to_save}
            with open(theme_settings_path, 'w') as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            print(f"Error saving theme settings: {e}")

    def change_accent_color_action(self):
        global PICSNEST_USER_ACCENT_COLOR
        current_color = get_current_accent_color()
        new_color_tuple = colorchooser.askcolor(color=current_color, title="Choose Accent Color", parent=self.root)
        if new_color_tuple and new_color_tuple[1]:
            PICSNEST_USER_ACCENT_COLOR = new_color_tuple[1]
            self._save_theme_settings()
            ui_creator.apply_app_styles(self) 
            self._refresh_all_item_visuals() 
            self.update_preview_and_info()
            messagebox.showinfo("Accent Color Changed",
                                "Accent color updated. Some changes may require an application restart to fully apply.",
                                parent=self.root)


    def show_initial_view(self):
        should_show_welcome = (
            self.current_folder.get() == "No folder selected" or
            (os.path.isdir(self.current_folder.get()) and not self.all_folder_items)
        )

        if should_show_welcome:
            if hasattr(self, 'canvas_content_frame') and self.canvas_content_frame.winfo_ismapped():
                self.canvas_content_frame.grid_remove()
            if hasattr(self, 'welcome_frame') and not self.welcome_frame.winfo_ismapped():
                self.welcome_frame.grid()
        else:
            if hasattr(self, 'welcome_frame') and self.welcome_frame.winfo_ismapped():
                self.welcome_frame.grid_remove()
            if hasattr(self, 'canvas_content_frame') and not self.canvas_content_frame.winfo_ismapped():
                 self.canvas_content_frame.grid()


    def on_closing(self):
        self._save_folder_thumb_db()
        self.cancel_long_operation.set()
        if self.active_thumbnail_thread and self.active_thumbnail_thread.is_alive():
            self.active_thumbnail_thread.join(timeout=0.5)
        self._empty_trash_permanently()
        self.root.destroy()

    def _empty_trash_permanently(self):
        if not os.path.isdir(self.TRASH_DIR): return
        items_deleted_count = 0
        items_failed_count = 0
        print(f"Emptying trash directory: {self.TRASH_DIR}")
        for item_name in os.listdir(self.TRASH_DIR):
            item_path = os.path.join(self.TRASH_DIR, item_name)
            try:
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.unlink(item_path)
                    items_deleted_count += 1
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    items_deleted_count += 1
            except Exception as e:
                items_failed_count += 1
                print(f"Error deleting {item_path} from trash: {e}")
        print(f"Trash emptying complete. Deleted: {items_deleted_count}, Failed: {items_failed_count}")
        if items_failed_count > 0 and self.root.winfo_exists():
             messagebox.showwarning("Trash Emptying Issue",
                                   f"Could not delete all items from trash. {items_failed_count} items may remain in {self.TRASH_DIR}",
                                   parent=self.root)

    def _load_folder_thumb_db(self):
        try:
            if os.path.exists(self.FOLDER_THUMB_DB_FILE):
                with open(self.FOLDER_THUMB_DB_FILE, 'r') as f:
                    content = f.read()
                    db = json.loads(content if content else '{}')
                    migrated_db = {}
                    for key, value in db.items():
                        if isinstance(value, dict):
                            migrated_db[key] = value
                        elif isinstance(value, str): 
                            migrated_db[key] = {'cover_image_path': value} 
                        else:
                            migrated_db[key] = {}
                    return migrated_db
            return {}
        except json.JSONDecodeError:
            print(f"Error decoding JSON from {self.FOLDER_THUMB_DB_FILE}. Returning empty DB.")
            return {}
        except Exception as e:
            print(f"Error loading folder thumb DB: {e}")
            return {}

    def _save_folder_thumb_db(self):
        try:
            db_to_save = {
                k: v for k, v in self.folder_thumb_db.items() if v
            }
            with open(self.FOLDER_THUMB_DB_FILE, 'w') as f:
                json.dump(db_to_save, f, indent=4)
        except Exception as e:
            print(f"Error saving folder thumb DB: {e}")


    def on_frame_configure(self, event=None):
        if hasattr(self, 'canvas') and self.canvas.winfo_exists():
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_mousewheel(self, event, direction=None):
        if not (hasattr(self, 'canvas_content_frame') and self.canvas_content_frame.winfo_ismapped()):
            return
        delta = 0
        if direction is not None: delta = direction
        elif sys.platform == "win32": delta = -1 * int(event.delta / 120)
        elif sys.platform == "darwin": delta = event.delta
        if delta != 0:
            self.canvas.yview_scroll(delta, "units")
            self.root.after_idle(self.on_scroll_check_lazy_load)

    def on_scroll_check_lazy_load(self):
        if self.is_loading_batch or self.displayed_item_count >= len(self.all_folder_items): return
        if not (hasattr(self, 'canvas_content_frame') and self.canvas_content_frame.winfo_ismapped()):
            return
        self.canvas.update_idletasks()
        scroll_info = self.canvas.yview()
        if (scroll_info[1] > 0.85 or \
           (scroll_info[0] == 0.0 and scroll_info[1] == 1.0 and self.item_frame.winfo_height() < self.canvas.winfo_height())) \
           and self.displayed_item_count < len(self.all_folder_items):
            self._load_next_batch_of_items()

    def _on_canvas_press_for_rubber_band(self, event):
        clicked_widget = event.widget
        if clicked_widget == self.canvas:
            self._clear_all_selection_visuals()
            self.selected_item_paths.clear()
            self.rubber_band_start_x = self.canvas.canvasx(event.x)
            self.rubber_band_start_y = self.canvas.canvasy(event.y)
            if self.rubber_band_rect:
                self.canvas.delete(self.rubber_band_rect)
            self.rubber_band_rect = self.canvas.create_rectangle(
                self.rubber_band_start_x, self.rubber_band_start_y,
                self.rubber_band_start_x, self.rubber_band_start_y,
                outline=get_current_accent_color(), width=1, dash=(4, 2), tags="rubber_band_tag"
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
            self.canvas.itemconfigure("rubber_band_tag", state='hidden')
            end_x = self.canvas.canvasx(event.x)
            end_y = self.canvas.canvasy(event.y)
            sel_x1 = min(self.rubber_band_start_x, end_x)
            sel_y1 = min(self.rubber_band_start_y, end_y)
            sel_x2 = max(self.rubber_band_start_x, end_x)
            sel_y2 = max(self.rubber_band_start_y, end_y)
            if abs(sel_x1 - sel_x2) < 5 and abs(sel_y1 - sel_y2) < 5:
                self.canvas.delete(self.rubber_band_rect)
                self.rubber_band_rect = None
                self.update_preview_and_info()
                self.update_ui_state()
                return
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
                        self._refresh_single_item_visual(path) 
            self.canvas.delete(self.rubber_band_rect)
            self.rubber_band_rect = None
            self.update_preview_and_info()
            self.update_ui_state()

    def select_root_folder(self):
        folder_path = filedialog.askdirectory(parent=self.root)
        if folder_path:
            self.folder_history = []
            self.load_items(folder_path)

    def navigate_to_folder(self, folder_path):
        if os.path.isdir(folder_path) and self.current_folder.get() != folder_path:
            self.folder_history.append(self.current_folder.get())
            self.load_items(folder_path)
        elif not os.path.isdir(folder_path):
            messagebox.showerror("Error", "Not a valid folder.", parent=self.root)

    def navigate_up(self):
        if self.folder_history:
            prev_folder = self.folder_history.pop()
            self.load_items(prev_folder)

    def load_items(self, folder_path):
        is_new_folder_context = self.current_folder.get() != folder_path or not self.all_folder_items_raw

        if is_new_folder_context:
            self.similar_image_groups = []
            self.image_hashes_cache = {}
            self.marked_similar_paths = set()
            self.marked_screenshot_download_paths = set()
            self._similarity_scan_done_for_current_folder = False
            if hasattr(self, 'status_label') and self.status_label: self.status_label.config(text="")
            self._was_filter_active_before_style_refresh = self.show_only_similar_var.get() or self.show_only_screenshots_downloads_var.get()

        if not os.path.isdir(folder_path):
            messagebox.showerror("Error", "Cannot access folder.", parent=self.root)
            if is_new_folder_context: self.current_folder.set("No folder selected")
            self.all_folder_items_raw = []
            self.all_folder_items = []
            self.clear_view()
            self.update_ui_state()
            self.show_initial_view()
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
                current_raw_items.append({'path': entry.path, 'name': entry.name, 'type': item_type, 'is_error': False})
        except OSError as e:
            messagebox.showerror("Error", f"Error reading folder: {e}", parent=self.root)
            self.current_folder.set("Error reading folder")
            self.all_folder_items_raw = []
            self.all_folder_items = []
            self.update_ui_state()
            self.show_initial_view()
            return

        current_raw_items.sort(key=lambda x: (x['type'] != 'folder', x['name'].lower()))
        self.all_folder_items_raw = current_raw_items
        self._apply_type_filters_to_items_list()

        if self.all_folder_items:
            self.show_initial_view()
            self._load_next_batch_of_items()
        else:
            if hasattr(self, 'item_frame'): self.item_frame.update_idletasks()
            if hasattr(self, 'canvas'): self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            self.show_initial_view()

        self.update_ui_state()

    def _apply_type_filters_to_items_list(self):
        temp_filtered_items = []
        self.marked_screenshot_download_paths.clear()

        for item in self.all_folder_items_raw:
            if item['type'] == 'folder':
                if not self.show_only_similar_var.get() and not self.show_only_screenshots_downloads_var.get():
                    temp_filtered_items.append(item)
                elif self.show_only_similar_var.get() and not self.show_only_screenshots_downloads_var.get():
                     temp_filtered_items.append(item)
                continue

            if item['type'] == 'file':
                _, ext = os.path.splitext(item['name'])
                ext_lower = ext.lower()
                is_image = ext_lower in IMAGE_EXTENSIONS
                is_video = ext_lower in VIDEO_EXTENSIONS

                passes_basic_type_filter = (self.show_images_var.get() and is_image) or \
                                           (self.show_videos_var.get() and is_video)
                if not passes_basic_type_filter:
                    continue

                is_ss_or_dl = None
                if is_image:
                    is_ss_or_dl = file_operations.is_likely_screenshot_or_downloaded(
                        item['path'], self.Image, self.UnidentifiedImageError
                    )
                    if is_ss_or_dl:
                        self.marked_screenshot_download_paths.add(item['path'])
                        item['source_type'] = is_ss_or_dl

                if self.show_only_screenshots_downloads_var.get():
                    if not is_ss_or_dl:
                        continue

                if self.show_only_similar_var.get() and not self.show_only_screenshots_downloads_var.get():
                    if not (is_image and item['path'] in self.marked_similar_paths):
                        continue

                temp_filtered_items.append(item)

        self.all_folder_items = temp_filtered_items

        if self.show_only_similar_var.get() and not self.show_only_screenshots_downloads_var.get():
            folders_in_view = [item_data for item_data in self.all_folder_items if item_data['type'] == 'folder']
            path_to_item_data_map = {item_data['path']: item_data for item_data in self.all_folder_items if item_data['type'] == 'file'}
            grouped_similar_items_display_list = []

            sorted_similar_groups = sorted(
                list(self.similar_image_groups),
                key=lambda g: sorted(list(g))[0] if g else ""
            )
            for group_paths_set in sorted_similar_groups:
                current_group_batch = []
                for path in sorted(list(group_paths_set)):
                    if path in path_to_item_data_map:
                        current_group_batch.append(path_to_item_data_map[path])
                if current_group_batch:
                    grouped_similar_items_display_list.extend(current_group_batch)
            self.all_folder_items = folders_in_view + grouped_similar_items_display_list


    def _load_next_batch_of_items(self):
        if self.is_loading_batch or self.displayed_item_count >= len(self.all_folder_items): return
        self.is_loading_batch = True
        start_index = self.displayed_item_count
        end_index = min(len(self.all_folder_items), start_index + LAZY_LOAD_BATCH_SIZE)
        items_for_this_batch = self.all_folder_items[start_index:end_index]
        if not items_for_this_batch:
            self.is_loading_batch = False
            return
        self._populate_grid_with_batch(items_for_this_batch)
        self.displayed_item_count = end_index
        files_to_process_this_batch = [item for item in items_for_this_batch if item['type'] == 'file']
        if files_to_process_this_batch:
            thumb_thread = threading.Thread(target=self._thumbnail_generator_thread_runner,
                                      args=(files_to_process_this_batch, self.cancel_long_operation),
                                      daemon=True)
            self.active_thumbnail_thread = thumb_thread
            thumb_thread.start()
        self.is_loading_batch = False
        self.root.after_idle(self.on_scroll_check_lazy_load)

    def _populate_grid_with_batch(self, items_in_batch):
        for item_data in items_in_batch:
            widget_info = self._create_placeholder_widget(self.item_frame, item_data)
            widget_info['widget'].grid(row=self.current_grid_row, column=self.current_grid_col, padx=7, pady=7, sticky="nsew")

            for widget_element in [widget_info['widget'], widget_info['thumb_label'], widget_info['name_label']]:
                widget_element.bind("<Button-1>", lambda e, p=item_data['path'], wf=widget_info['widget']:
                    self._on_item_click_for_selection(e, p, wf))
                if item_data['type'] == 'folder':
                    widget_element.bind("<Double-Button-1>", lambda e, p=item_data['path']: self.navigate_to_folder(p))
                    widget_element.bind("<Button-3>", lambda e, p=item_data['path']: self._on_folder_right_click(e, p)) 
                elif item_data['type'] == 'file':
                    if item_data['path'].lower().endswith(IMAGE_EXTENSIONS):
                        widget_element.bind("<Double-Button-1>", lambda e, p=item_data['path']: self._open_image_viewer_action(p))
                    elif item_data['path'].lower().endswith(VIDEO_EXTENSIONS):
                        widget_element.bind("<Double-Button-1>", lambda e, p=item_data['path']:
                            self._open_video_viewer_action(p) if self.vlc else self._open_with_system(p))
            
            self.items_in_view[item_data['path']] = {
                **widget_info,
                'type': item_data['type'],
                'is_error': False,
                'source_type': item_data.get('source_type')
            }
            
            self._apply_initial_folder_customizations(item_data['path'])

            self.current_grid_col += 1
            if self.current_grid_col >= GRID_COLUMNS:
                self.current_grid_col = 0
                self.current_grid_row += 1
        for c_idx in range(GRID_COLUMNS): self.item_frame.grid_columnconfigure(c_idx, weight=1)
        self.item_frame.update_idletasks()
        if hasattr(self, 'canvas') and self.canvas.winfo_exists():
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

# In class PhotoVideoManagerApp:

    def _apply_initial_folder_customizations(self, item_path):
        if item_path in self.items_in_view:
            widget_info = self.items_in_view[item_path]
            if widget_info['type'] == 'folder':
                widget_frame = widget_info['widget']
                thumb_label = widget_info['thumb_label']
                name_label = widget_info['name_label']

                custom_data = self.folder_thumb_db.get(item_path, {})
                custom_icon_path = custom_data.get('item_icon_path')
                custom_bg_color_from_db = custom_data.get('item_bg_color')
                is_selected = item_path in self.selected_item_paths

                # Determine background and border for the tk.Frame
                current_bg_to_apply = PICSNEST_FOLDER_REPRESENTATION_BG 
                current_border_color = PICSNEST_BORDER_LIGHT # Default border for non-selected folder

                if is_selected:
                    current_bg_to_apply = get_current_accent_color()
                    current_border_color = PICSNEST_TEXT_LIGHT # Selected border
                    widget_frame.configure(borderwidth=2)
                elif custom_bg_color_from_db:
                    current_bg_to_apply = custom_bg_color_from_db
                    current_border_color = get_current_accent_color() # Custom color gets accent border
                    widget_frame.configure(borderwidth=1)
                else: # Default folder
                    widget_frame.configure(borderwidth=1)


                widget_frame.configure(background=current_bg_to_apply, highlightbackground=current_border_color, highlightcolor=current_border_color, highlightthickness=widget_frame.cget('borderwidth'))
                thumb_label.configure(background=current_bg_to_apply)
                name_label.configure(background=current_bg_to_apply, foreground=PICSNEST_TEXT_LIGHT)

                # Icon loading logic (same as before, but ensures it's applied after background)
                loaded_custom_icon = False
                if custom_icon_path and os.path.exists(custom_icon_path):
                    try:
                        img_pil = self.Image.open(custom_icon_path)
                        widget_frame.update_idletasks()
                        name_label_h = name_label.winfo_height() if name_label.winfo_ismapped() else 20
                        
                        icon_width_limit = GRID_THUMBNAIL_SIZE[0] - 10
                        icon_height_limit = GRID_THUMBNAIL_SIZE[1] - name_label_h - 10

                        img_pil.thumbnail((icon_width_limit, max(10, icon_height_limit)), self.Image.Resampling.LANCZOS)
                        tk_image = self.ImageTk.PhotoImage(img_pil)
                        thumb_label.config(image=tk_image, text="", font=None)
                        thumb_label.custom_icon_ref = tk_image
                        loaded_custom_icon = True
                    except Exception as e:
                        print(f"Error applying initial custom folder icon {custom_icon_path}: {e}")
                
                if not loaded_custom_icon:
                    icon_font = ("Segoe UI Symbol", 36)
                    thumb_label.config(image='', text=PICSNEST_FOLDER_ICON, font=icon_font)
                    if hasattr(thumb_label, 'custom_icon_ref'): del thumb_label.custom_icon_ref

    def _create_placeholder_widget(self, parent_frame, item_data):
        item_path, item_name, item_type = item_data['path'], item_data['name'], item_data['type']
        initial_style_info = {'type': item_type, 'is_error': False, 'source_type': item_data.get('source_type')}
        
        # --- FRAME CREATION MODIFICATION ---
        if item_type == 'folder':
            # For folders, use tk.Frame to allow direct background configuration
            # We'll manually set border and relief to mimic ttk style if needed
            widget_frame = tk.Frame(parent_frame, relief=tk.SOLID, borderwidth=1, padx=4, pady=4)
            # Initial background will be set by _apply_initial_folder_customizations
        else:
            # For files, continue using ttk.Frame with its style
            style_name = self._get_item_style(item_path, initial_style_info)
            widget_frame = ttk.Frame(parent_frame, style=style_name, padding=5)
        # --- END FRAME CREATION MODIFICATION ---

        thumb_label = ttk.Label(widget_frame, anchor='center', style="PicsNest.ItemThumb.TLabel")
        name_label = ttk.Label(widget_frame, text=item_name, anchor='center',
                               wraplength=GRID_THUMBNAIL_SIZE[0] - 10, 
                               style="PicsNest.ItemName.TLabel",
                               justify=tk.CENTER)
        
        name_label.configure(foreground=PICSNEST_TEXT_LIGHT) # Ensure text is visible

        icon_font_size = 36
        icon_font = ("Segoe UI Symbol", icon_font_size)

        if item_type == 'folder':
            name_label.pack(side=tk.BOTTOM, fill=tk.X, pady=(1, 0)) # Minimal pady for name

            # Default folder icon setup
            thumb_label.config(text=PICSNEST_FOLDER_ICON, font=icon_font)
            thumb_label.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(4, 1))

        elif item_type == 'file':
            placeholder_text = PICSNEST_LOADING_TEXT_GRID
            ext_lower = os.path.splitext(item_name)[1].lower()
            if ext_lower in VIDEO_EXTENSIONS:
                placeholder_text = PICSNEST_VIDEO_ICON
            elif ext_lower in IMAGE_EXTENSIONS:
                placeholder_text = PICSNEST_IMAGE_ICON
            
            thumb_label.config(text=placeholder_text, font=icon_font)
            thumb_label.pack(fill=tk.BOTH, expand=True, pady=(0, 3))
            name_label.pack(fill=tk.X, side=tk.BOTTOM, pady=(1,0))
        
        return {'widget': widget_frame, 'thumb_label': thumb_label, 'name_label': name_label}
    def _thumbnail_generator_thread_runner(self, items_to_process_batch, cancel_event_ref):
        for item_data in items_to_process_batch:
            if cancel_event_ref.is_set(): break
            thumb_image, error_flag = file_operations.generate_single_thumbnail(
                item_data, GRID_THUMBNAIL_SIZE, self.Image,
                self.UnidentifiedImageError, self.cv2
            )
            self.thumbnail_queue.put({
                'path': item_data['path'], 'image': thumb_image,
                'error': error_flag, 'type': item_data['type']
            })

    def _process_thumbnail_queue(self):
        max_updates_per_cycle = 10
        processed_count = 0
        try:
            while not self.thumbnail_queue.empty() and processed_count < max_updates_per_cycle:
                result = self.thumbnail_queue.get_nowait()
                processed_count += 1
                item_path = result['path']
                if item_path in self.items_in_view:
                    widget_info = self.items_in_view[item_path]
                    widget_frame = widget_info['widget']
                    thumb_display_label = widget_info['thumb_label']
                    widget_info['is_error'] = result['error']

                    if widget_frame.winfo_exists() and thumb_display_label.winfo_exists():
                        self._refresh_single_item_visual(item_path) # Handles style and folder custom BG/Icon

                        if result['type'] == 'file': # Only update thumb_display_label for files from this queue
                            if result['error']:
                                thumb_display_label.config(image='', text=PICSNEST_ERROR_ICON_GRID, font=("Arial", 28), style="PicsNest.ErrorIcon.TLabel")
                                if hasattr(thumb_display_label, 'image_ref'): thumb_display_label.image_ref = None
                            elif result['image']:
                                try:
                                     tk_image = self.ImageTk.PhotoImage(result['image'])
                                     thumb_display_label.image_ref = tk_image
                                     thumb_display_label.config(image=tk_image, text="", style="PicsNest.ItemThumb.TLabel")
                                except Exception as e_tk:
                                     print(f"Tkinter PhotoImage error for {item_path}: {e_tk}")
                                     thumb_display_label.config(image='', text=PICSNEST_ERROR_ICON_GRID, font=("Arial", 18), style="PicsNest.ErrorIcon.TLabel")
                                     widget_info['is_error'] = True
                                     self._refresh_single_item_visual(item_path) 
                                     if hasattr(thumb_display_label, 'image_ref'): thumb_display_label.image_ref = None
                            # else: File placeholder icon already set by _create_placeholder_widget
        except queue.Empty: pass
        except Exception as e:
            print(f"Error processing thumbnail queue: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.root.after(100, self._process_thumbnail_queue)

    def clear_view(self):
        for item_path_in_view in list(self.items_in_view.keys()):
            widget_info = self.items_in_view.pop(item_path_in_view, None)
            if widget_info and widget_info['widget'].winfo_exists():
                widget_info['widget'].destroy()
        self.items_in_view.clear()
        self.selected_item_paths.clear()
        self.reset_preview()
        self.displayed_item_count = 0
        self.current_grid_row = 0
        self.current_grid_col = 0
        self.is_loading_batch = False

        if hasattr(self, 'canvas') and self.canvas.winfo_exists():
            self.canvas.yview_moveto(0)
            self.canvas.xview_moveto(0)
        if hasattr(self, 'item_frame'):
            self.item_frame.update_idletasks()
        if hasattr(self, 'canvas') and self.canvas.winfo_exists():
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _clear_all_selection_visuals(self):
        paths_to_restyle = list(self.selected_item_paths)
        for path_to_clear_sel in paths_to_restyle:
            if path_to_clear_sel in self.items_in_view:
                self._refresh_single_item_visual(path_to_clear_sel) 

    def _get_item_style(self, item_path, item_info, force_deselected=False):
        is_selected = (item_path in self.selected_item_paths) and not force_deselected
        is_similar = item_path in self.marked_similar_paths
        is_ss_dl = item_path in self.marked_screenshot_download_paths
        is_error = item_info.get('is_error', False)
        item_type = item_info['type']

        if is_selected: return "PicsNest.Selected.TFrame"

        if self.show_only_screenshots_downloads_var.get() and is_ss_dl and item_type == 'file':
            return "PicsNest.ScreenshotDownloaded.TFrame"

        if is_similar and item_type == 'file': return "PicsNest.Similar.TFrame"
        
        if item_type == 'folder':
            return "PicsNest.Folder.TFrame" 

        if item_type == 'file':
            if is_error: return "PicsNest.Error.TFrame"
            has_thumb_image_displayed = False
            if 'thumb_label' in item_info and item_info['thumb_label'].winfo_exists():
                if hasattr(item_info['thumb_label'], 'image_ref') and item_info['thumb_label'].image_ref:
                    has_thumb_image_displayed = True
            item_ext = os.path.splitext(item_path)[1].lower()
            if item_ext in VIDEO_EXTENSIONS:
                 return "PicsNest.VideoItem.TFrame" if has_thumb_image_displayed else "PicsNest.VideoPlaceholder.TFrame"
            return "PicsNest.ItemLoaded.TFrame" if has_thumb_image_displayed else "PicsNest.ItemPlaceholder.TFrame"
        return "PicsNest.Item.TFrame"

    def _on_item_click_for_selection(self, event, item_path_clicked, widget_frame_clicked):
        if self.name_edit_entry and self.name_edit_entry.winfo_exists():
            return

        self._clear_all_selection_visuals() 
        self.selected_item_paths = {item_path_clicked}
        if item_path_clicked in self.items_in_view and widget_frame_clicked.winfo_exists():
            self._refresh_single_item_visual(item_path_clicked) 
        self.update_preview_and_info()
        self.update_ui_state()

    def reset_preview(self):
        self.preview_label.config(image='', text="Select an item", style="PicsNest.PreviewPlaceholder.TLabel")
        if hasattr(self.preview_label, 'image_ref'): self.preview_label.image_ref = None
        self.info_name_label.config(text="Name: -")
        self.info_size_label.config(text="Size: -")
        self.info_type_label.config(text="Type: -")
        self.info_source_label.config(text="Source: -")

    def update_preview_and_info(self):
        if not self.selected_item_paths:
            self.reset_preview()
            return

        if len(self.selected_item_paths) == 1:
            item_path = list(self.selected_item_paths)[0]
            item_info_from_view = self.items_in_view.get(item_path)

            if not item_info_from_view or not os.path.exists(item_path):
                self.reset_preview()
                self.info_name_label.config(text="Name: Error/Not Found")
                return

            item_type = item_info_from_view['type']
            file_name = os.path.basename(item_path)
            self.info_name_label.config(text=f"Name: {file_name}")
            self.info_type_label.config(text=f"Type: {item_type.capitalize()}")

            source_text = "-"
            if item_type == 'file' and item_path.lower().endswith(IMAGE_EXTENSIONS):
                source_type_val = item_info_from_view.get('source_type')
                if not source_type_val:
                     source_type_val = file_operations.is_likely_screenshot_or_downloaded(
                        item_path, self.Image, self.UnidentifiedImageError
                    )
                if source_type_val:
                    source_text = source_type_val.capitalize()
            self.info_source_label.config(text=f"Source: {source_text}")


            self.preview_label.config(style="PicsNest.PreviewImage.TLabel")
            if item_type == 'file':
                try:
                    size_bytes = os.path.getsize(item_path)
                    size_mb = size_bytes / (1024*1024); size_kb = size_bytes / 1024
                    self.info_size_label.config(text=f"Size: {size_mb:.2f} MB" if size_mb >= 1.0 else f"{size_kb:.1f} KB")
                    preview_text_content = "No preview"
                    generated_preview_image = None
                    if item_path.lower().endswith(IMAGE_EXTENSIONS):
                        img_pil_preview = self.Image.open(item_path)
                        img_pil_preview.thumbnail(PREVIEW_THUMBNAIL_SIZE, self.Image.Resampling.LANCZOS)
                        if img_pil_preview.mode not in ('RGB','RGBA'): img_pil_preview = img_pil_preview.convert('RGB')
                        generated_preview_image = self.ImageTk.PhotoImage(img_pil_preview)
                        preview_text_content = ""
                    elif item_path.lower().endswith(VIDEO_EXTENSIONS) and self.cv2:
                        cap = None
                        try:
                            cap = self.cv2.VideoCapture(item_path)
                            if cap.isOpened():
                                frame_count = int(cap.get(self.cv2.CAP_PROP_FRAME_COUNT))
                                frame_no = min(frame_count // 10, 100) if frame_count > 10 else 0
                                cap.set(self.cv2.CAP_PROP_POS_FRAMES, frame_no); ret, frame = cap.read()
                                if ret:
                                    frame_rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
                                    img_pil_video_thumb = self.Image.fromarray(frame_rgb)
                                    img_pil_video_thumb.thumbnail(PREVIEW_THUMBNAIL_SIZE, self.Image.Resampling.LANCZOS)
                                    generated_preview_image = self.ImageTk.PhotoImage(img_pil_video_thumb)
                                    preview_text_content = ""
                                else: preview_text_content = "Video (thumb failed)"
                            else: preview_text_content = "Video (cannot open)"
                        except Exception as e_vid_prev:
                            print(f"Video preview error for {item_path}: {e_vid_prev}")
                            preview_text_content = "Video (thumb error)"
                            self.preview_label.config(style="PicsNest.PreviewError.TLabel")
                        finally:
                            if cap: cap.release()
                    self.preview_label.config(text=preview_text_content)
                    if generated_preview_image:
                        self.preview_label.config(image=generated_preview_image)
                        self.preview_label.image_ref = generated_preview_image
                    else:
                        self.preview_label.config(image='')
                        if hasattr(self.preview_label, 'image_ref'): self.preview_label.image_ref = None
                        if not item_path.lower().endswith(IMAGE_EXTENSIONS) and not item_path.lower().endswith(VIDEO_EXTENSIONS):
                             self.preview_label.config(text="No preview for this file type.", style="PicsNest.PreviewPlaceholder.TLabel")
                        elif preview_text_content == "No preview":
                             self.preview_label.config(style="PicsNest.PreviewPlaceholder.TLabel")
                except self.UnidentifiedImageError:
                    self.preview_label.config(image='', text="Preview Error (Format?)", style="PicsNest.PreviewError.TLabel")
                    if hasattr(self.preview_label, 'image_ref'): self.preview_label.image_ref = None
                except Exception as e_prev:
                    print(f"Error updating preview for {item_path}: {e_prev}")
                    self.preview_label.config(image='', text="Preview Error", style="PicsNest.PreviewError.TLabel")
                    if hasattr(self.preview_label, 'image_ref'): self.preview_label.image_ref = None
            elif item_type == 'folder':
                self.info_size_label.config(text="Size: -")
                self.info_source_label.config(text="Source: -") 
                custom_data = self.folder_thumb_db.get(item_path, {})
                custom_icon_path = custom_data.get('item_icon_path')
                if custom_icon_path and os.path.exists(custom_icon_path):
                    try:
                        img_pil_preview = self.Image.open(custom_icon_path)
                        img_pil_preview.thumbnail(PREVIEW_THUMBNAIL_SIZE, self.Image.Resampling.LANCZOS)
                        tk_image_preview = self.ImageTk.PhotoImage(img_pil_preview)
                        self.preview_label.config(image=tk_image_preview, text="")
                        self.preview_label.image_ref = tk_image_preview
                    except Exception:
                        self.preview_label.config(image='', text="Folder (custom icon error)", style="PicsNest.PreviewPlaceholder.TLabel")
                        if hasattr(self.preview_label, 'image_ref'): self.preview_label.image_ref = None
                else:
                    self.preview_label.config(image='', text="Folder Selected", style="PicsNest.PreviewPlaceholder.TLabel")
                    if hasattr(self.preview_label, 'image_ref'): self.preview_label.image_ref = None
        else:
            self.preview_label.config(image='', text=f"{len(self.selected_item_paths)} items selected", style="PicsNest.PreviewPlaceholder.TLabel")
            if hasattr(self.preview_label, 'image_ref'): self.preview_label.image_ref = None
            self.info_name_label.config(text="Name: Multiple items")
            self.info_size_label.config(text="Size: -")
            self.info_type_label.config(text="Type: Mixed")
            self.info_source_label.config(text="Source: -")


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
            try: self.edit_menu.entryconfigure("Undo", state=undo_state)
            except tk.TclError: pass

    def _open_image_viewer_action(self, image_path_to_open):
        all_images_in_current_view = [
            item['path'] for item in self.all_folder_items
            if item['type'] == 'file' and item['path'].lower().endswith(IMAGE_EXTENSIONS) and os.path.exists(item['path'])
        ]
        if not all_images_in_current_view:
            if os.path.exists(image_path_to_open) and image_path_to_open.lower().endswith(IMAGE_EXTENSIONS):
                 all_images_in_current_view = [image_path_to_open]
            else:
                messagebox.showinfo("Viewer", "No suitable images to view in the current filter context.", parent=self.root)
                return
        try:
            current_idx = all_images_in_current_view.index(image_path_to_open)
        except ValueError:
            if os.path.exists(image_path_to_open) and image_path_to_open.lower().endswith(IMAGE_EXTENSIONS):
                all_images_in_current_view.append(image_path_to_open)
                current_idx = len(all_images_in_current_view) - 1
            else:
                messagebox.showerror("Error", "Cannot find the selected image for the viewer.", parent=self.root)
                return
        ImageViewerWindow(self.root, all_images_in_current_view, current_idx, self)

    def _open_video_viewer_action(self, video_path_to_open):
        all_videos_in_current_view = [
            item['path'] for item in self.all_folder_items
            if item['type'] == 'file' and item['path'].lower().endswith(VIDEO_EXTENSIONS) and os.path.exists(item['path'])
        ]
        if not all_videos_in_current_view:
            if os.path.exists(video_path_to_open) and video_path_to_open.lower().endswith(VIDEO_EXTENSIONS):
                all_videos_in_current_view = [video_path_to_open]
            else:
                messagebox.showinfo("Viewer", "No suitable videos to view in the current filter context.", parent=self.root)
                return
        try:
            current_idx = all_videos_in_current_view.index(video_path_to_open)
        except ValueError:
            if os.path.exists(video_path_to_open) and video_path_to_open.lower().endswith(VIDEO_EXTENSIONS):
                all_videos_in_current_view.append(video_path_to_open)
                current_idx = len(all_videos_in_current_view) - 1
            else:
                messagebox.showerror("Error", "Cannot find the selected video for the viewer.", parent=self.root)
                return
        VideoViewerWindow(self.root, all_videos_in_current_view, current_idx, self)

    def open_selected_item_action(self):
        if not self.selected_item_paths or len(self.selected_item_paths) != 1: return
        item_path = list(self.selected_item_paths)[0]
        item_info_from_view = self.items_in_view.get(item_path)
        if not item_info_from_view or not os.path.exists(item_path):
            messagebox.showerror("Error", "Selected item not found or no longer exists.", parent=self.root)
            return
        item_type = item_info_from_view['type']
        if item_type == 'folder':
            self.navigate_to_folder(item_path)
        elif item_type == 'file':
            if item_path.lower().endswith(IMAGE_EXTENSIONS):
                self._open_image_viewer_action(item_path)
            elif item_path.lower().endswith(VIDEO_EXTENSIONS):
                if self.vlc:
                    self._open_video_viewer_action(item_path)
                else:
                    self._open_with_system(item_path)
            else:
                self._open_with_system(item_path)

    def _open_with_system(self, path_to_open):
        try:
            if sys.platform == "win32": os.startfile(os.path.realpath(path_to_open))
            elif sys.platform == "darwin": subprocess.Popen(["open", path_to_open])
            else: subprocess.Popen(["xdg-open", path_to_open])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open file/folder with system default: {e}", parent=self.root)

    def on_delete_key_press(self, event=None):
        if self.name_edit_entry and self.name_edit_entry.winfo_exists():
            return "break"
        self.delete_selected_items_action_entry()
        return "break"

    def on_f2_key_press(self, event=None):
        if not self.selected_item_paths or len(self.selected_item_paths) != 1:
            return

        self.renaming_item_path = list(self.selected_item_paths)[0]
        if self.renaming_item_path not in self.items_in_view:
            return

        item_widget_info = self.items_in_view[self.renaming_item_path]
        self.original_name_label = item_widget_info['name_label']
        item_frame = item_widget_info['widget']

        if not self.original_name_label.winfo_exists(): return

        original_name = os.path.basename(self.renaming_item_path)

        # For F2, ensure the name_label is visible before trying to hide it for the entry
        # This is important if it was previously hidden or not packed correctly
        if not self.original_name_label.winfo_ismapped():
            self.original_name_label.pack(side=tk.BOTTOM, fill=tk.X, pady=(1,1), ipady=1) # Re-pack if needed
            item_frame.update_idletasks()


        self.original_name_label.pack_forget()

        self.name_edit_entry = ttk.Entry(item_frame, style="PicsNest.Rename.TEntry")
        self.name_edit_entry.insert(0, original_name)
        # Pack the entry where the name label was, ensuring it's after the thumb_label
        # If thumb_label was packed TOP, entry should be packed BOTTOM.
        self.name_edit_entry.pack(side=tk.BOTTOM, fill=tk.X, pady=(1,1), ipady=1) 
        
        self.name_edit_entry.select_range(0, tk.END)
        self.name_edit_entry.focus_set()

        self.name_edit_entry.bind("<Return>", self._finish_rename)
        self.name_edit_entry.bind("<Escape>", self._cancel_rename)
        self.name_edit_entry.bind("<FocusOut>", self._cancel_rename_on_focus_out)
        return "break"

    def _finish_rename(self, event=None):
        if not self.name_edit_entry or not self.renaming_item_path: return "break"

        new_name = self.name_edit_entry.get().strip()
        self.name_edit_entry.destroy()
        self.name_edit_entry = None

        if self.original_name_label and self.original_name_label.winfo_exists():
             self.original_name_label.pack(side=tk.BOTTOM, fill=tk.X, pady=(1,1), ipady=1)


        if not new_name or new_name == os.path.basename(self.renaming_item_path):
            self.renaming_item_path = None
            self.original_name_label = None
            return "break"

        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        if any(char in new_name for char in invalid_chars):
            messagebox.showerror("Rename Error", f"Filename cannot contain: {' '.join(invalid_chars)}", parent=self.root)
            self.renaming_item_path = None
            self.original_name_label = None
            return "break"

        current_dir = os.path.dirname(self.renaming_item_path)
        new_path = os.path.join(current_dir, new_name)

        if os.path.exists(new_path):
            messagebox.showerror("Rename Error", f"A file or folder named '{new_name}' already exists.", parent=self.root)
            self.renaming_item_path = None
            self.original_name_label = None
            return "break"

        try:
            os.rename(self.renaming_item_path, new_path)
            if self.renaming_item_path in self.folder_thumb_db:
                self.folder_thumb_db[new_path] = self.folder_thumb_db.pop(self.renaming_item_path)
                self._save_folder_thumb_db()

            self.load_items(self.current_folder.get()) 

        except OSError as e:
            messagebox.showerror("Rename Error", f"Could not rename: {e}", parent=self.root)
        finally:
            self.renaming_item_path = None
            self.original_name_label = None
        return "break"

    def _cancel_rename(self, event=None):
        if self.name_edit_entry and self.name_edit_entry.winfo_exists():
            self.name_edit_entry.destroy()
            self.name_edit_entry = None
        if self.original_name_label and self.original_name_label.winfo_exists():
            if not self.original_name_label.winfo_ismapped(): # Repack if it was forgotten
                 self.original_name_label.pack(side=tk.BOTTOM, fill=tk.X, pady=(1,1), ipady=1)
        self.renaming_item_path = None
        self.original_name_label = None
        return "break"

    def _cancel_rename_on_focus_out(self, event=None):
        focused_widget = self.root.focus_get()
        if self.name_edit_entry and focused_widget != self.name_edit_entry:
            self._cancel_rename()


    def _add_to_undo_stack(self, action_type_str, **kwargs_action_data):
        self.undo_stack.append({'action_type': action_type_str, **kwargs_action_data})
        self.update_ui_state()

    def handle_show_similar_toggle(self):
        if self.show_only_similar_var.get():
            if self.show_only_screenshots_downloads_var.get():
                self.show_only_screenshots_downloads_var.set(False)

            if not self._similarity_scan_done_for_current_folder and not self.is_finding_similar:
                if self.imagehash:
                    self.status_label.config(text="Auto-scan for similar...")
                    self._find_similar_images_action_entry(triggered_by_filter_toggle=True)
                else:
                    messagebox.showwarning("ImageHash Missing", "ImageHash library not found. Cannot find/show similar images.", parent=self.root)
                    self.show_only_similar_var.set(False)
                    return
            else:
                self.apply_all_filters_and_refresh()
        else:
            self.apply_all_filters_and_refresh()


    def apply_all_filters_and_refresh(self):
        if self.show_only_screenshots_downloads_var.get() and self.show_only_similar_var.get():
            self.show_only_similar_var.set(False)

        current_scroll_y = 0.0
        current_scroll_x = 0.0
        if hasattr(self, 'canvas_content_frame') and self.canvas_content_frame.winfo_ismapped():
            current_scroll_y = self.canvas.yview()[0]
            current_scroll_x = self.canvas.xview()[0]

        current_folder_path = self.current_folder.get()

        if os.path.isdir(current_folder_path) and current_folder_path != "No folder selected":
            self.load_items(current_folder_path)
        else:
            self.all_folder_items = []
            self.clear_view()
            self.update_ui_state()
            self.show_initial_view()

        if hasattr(self, 'canvas_content_frame') and self.canvas_content_frame.winfo_ismapped():
            self.canvas.update_idletasks()
            self.canvas.yview_moveto(current_scroll_y)
            self.canvas.xview_moveto(current_scroll_x)

        self._was_filter_active_before_style_refresh = self.show_only_similar_var.get() or self.show_only_screenshots_downloads_var.get()


    def _refresh_all_item_visuals(self):
        for path, item_info_dict in self.items_in_view.items():
            if item_info_dict['widget'].winfo_exists():
                self._refresh_single_item_visual(path)

    def _get_errored_item_paths(self):
        return [
            path for path, info in self.items_in_view.items()
            if info.get('is_error', False) and os.path.exists(path)
        ]

    def _on_folder_right_click(self, event, item_path):
        if self.renaming_item_path:
            return

        self._clear_all_selection_visuals()
        self.selected_item_paths = {item_path}
        if item_path in self.items_in_view:
            self._refresh_single_item_visual(item_path) 
        self.update_preview_and_info()
        self.update_ui_state()

        context_menu = tk.Menu(self.root, tearoff=0,
                               bg=PICSNEST_BG_MEDIUM, fg=PICSNEST_TEXT_LIGHT,
                               activebackground=get_current_accent_color(),
                               activeforeground=PICSNEST_TEXT_LIGHT)
        context_menu.add_command(label="Rename", command=lambda p=item_path: self._rename_folder_item_action(p))
        context_menu.add_command(label="Set Custom Icon...", command=lambda p=item_path: self._change_folder_icon_action(p))
        context_menu.add_command(label="Set Background Color...", command=lambda p=item_path: self._change_folder_bg_color_action(p))
        context_menu.add_separator(background=PICSNEST_BORDER_LIGHT)
        context_menu.add_command(label="Reset Customizations", command=lambda p=item_path: self._reset_folder_customizations_action(p))

        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def _rename_folder_item_action(self, item_path):
        if item_path not in self.items_in_view:
            return
        self.on_f2_key_press()

    def _change_folder_icon_action(self, item_path):
        if not os.path.isdir(item_path): return

        image_filetypes = [('Image files', '.png .jpg .jpeg .gif .bmp .ico'), ('All files', '*.*')]
        new_icon_path_original = filedialog.askopenfilename(title="Select Custom Icon for Folder",
                                                            filetypes=image_filetypes,
                                                            parent=self.root)
        if not new_icon_path_original:
            return

        try:
            folder_path_hash = hashlib.md5(item_path.encode('utf-8')).hexdigest()
            original_ext = os.path.splitext(new_icon_path_original)[1]
            custom_icon_filename = f"folder_{folder_path_hash}{original_ext}"
            persistent_icon_path = os.path.join(self.CUSTOM_FOLDER_ICONS_DIR, custom_icon_filename)

            shutil.copy2(new_icon_path_original, persistent_icon_path)

            if item_path not in self.folder_thumb_db:
                self.folder_thumb_db[item_path] = {}
            self.folder_thumb_db[item_path]['item_icon_path'] = persistent_icon_path
            self._save_folder_thumb_db()

            self._refresh_single_item_visual(item_path)
            self.update_preview_and_info()

        except Exception as e:
            messagebox.showerror("Error Setting Icon", f"Could not set custom folder icon: {e}", parent=self.root)

    def _change_folder_bg_color_action(self, item_path):
        if not os.path.isdir(item_path): return

        current_customizations = self.folder_thumb_db.get(item_path, {})
        initial_color = current_customizations.get('item_bg_color', PICSNEST_FOLDER_REPRESENTATION_BG)

        new_color_tuple = colorchooser.askcolor(color=initial_color, title="Choose Folder Background Color", parent=self.root)
        if new_color_tuple and new_color_tuple[1]:
            new_color_hex = new_color_tuple[1]
            if item_path not in self.folder_thumb_db:
                self.folder_thumb_db[item_path] = {}
            self.folder_thumb_db[item_path]['item_bg_color'] = new_color_hex
            self._save_folder_thumb_db()
            self._refresh_single_item_visual(item_path)

    def _reset_folder_customizations_action(self, item_path):
        if item_path not in self.folder_thumb_db or not self.folder_thumb_db[item_path]: 
            messagebox.showinfo("Info", "No customizations to reset for this folder.", parent=self.root)
            return

        custom_data = self.folder_thumb_db.get(item_path, {})
        icon_path_to_delete = custom_data.pop('item_icon_path', None)
        custom_data.pop('item_bg_color', None)

        if not custom_data:
            del self.folder_thumb_db[item_path]
        else:
            self.folder_thumb_db[item_path] = custom_data 

        if icon_path_to_delete and os.path.exists(icon_path_to_delete):
            try:
                os.remove(icon_path_to_delete)
            except Exception as e:
                print(f"Could not delete custom icon file {icon_path_to_delete}: {e}")

        self._save_folder_thumb_db()
        self._refresh_single_item_visual(item_path)
        self.update_preview_and_info() 
        messagebox.showinfo("Customizations Reset", "Folder icon and color have been reset.", parent=self.root)

    def _refresh_single_item_visual(self, item_path):
        if item_path in self.items_in_view:
            widget_info = self.items_in_view[item_path]
            widget_frame = widget_info['widget']
            thumb_label = widget_info['thumb_label']
            name_label = widget_info['name_label'] 

            if not widget_frame.winfo_exists():
                return

            item_name_for_refresh = os.path.basename(item_path) 
            name_label.configure(text=item_name_for_refresh) 

            if widget_info['type'] == 'folder':
                # This is now a tk.Frame, so we configure it directly
                custom_data = self.folder_thumb_db.get(item_path, {})
                custom_icon_path = custom_data.get('item_icon_path')
                custom_bg_color_from_db = custom_data.get('item_bg_color')
                is_selected = item_path in self.selected_item_paths
                # is_similar and is_ss_dl are not typically applied to folders, but check if needed
                
                current_bg_to_apply = PICSNEST_FOLDER_REPRESENTATION_BG
                current_border_color = PICSNEST_BORDER_LIGHT 
                current_borderwidth = 1

                if is_selected:
                    current_bg_to_apply = get_current_accent_color()
                    current_border_color = PICSNEST_TEXT_LIGHT 
                    current_borderwidth = 2
                elif custom_bg_color_from_db:
                    current_bg_to_apply = custom_bg_color_from_db
                    current_border_color = get_current_accent_color() # Or a fixed border for custom colored folders
                    current_borderwidth = 1 
                # else: default folder bg and border already set

                widget_frame.configure(
                    background=current_bg_to_apply, 
                    highlightbackground=current_border_color, 
                    highlightcolor=current_border_color, # For focus
                    highlightthickness=current_borderwidth,
                    borderwidth=current_borderwidth # Ensure borderwidth is also set if relief is SOLID
                )
                thumb_label.configure(background=current_bg_to_apply)
                name_label.configure(background=current_bg_to_apply, foreground=PICSNEST_TEXT_LIGHT)

                # Icon loading logic
                loaded_custom_icon = False
                if custom_icon_path and os.path.exists(custom_icon_path):
                    try:
                        img_pil = self.Image.open(custom_icon_path)
                        widget_frame.update_idletasks()
                        name_label_h = name_label.winfo_height() if name_label.winfo_ismapped() else 20
                        
                        target_h = GRID_THUMBNAIL_SIZE[1] - name_label_h - 10 
                        target_w = GRID_THUMBNAIL_SIZE[0] - 10
                        img_pil.thumbnail((target_w, max(10, target_h)), self.Image.Resampling.LANCZOS)
                        tk_image = self.ImageTk.PhotoImage(img_pil)
                        thumb_label.configure(image=tk_image, text="", font=None)
                        thumb_label.custom_icon_ref = tk_image
                        loaded_custom_icon = True
                    except Exception as e:
                        print(f"Error refreshing custom folder icon {custom_icon_path}: {e}")
                
                if not loaded_custom_icon:
                    icon_font_size = 36
                    icon_font = ("Segoe UI Symbol", icon_font_size)
                    thumb_label.configure(image='', text=PICSNEST_FOLDER_ICON, font=icon_font)
                    if hasattr(thumb_label, 'custom_icon_ref'): del thumb_label.custom_icon_ref
            
            elif widget_info['type'] == 'file':
                # For files (ttk.Frame), rely on style changes
                style_name = self._get_item_style(item_path, widget_info)
                widget_frame.configure(style=style_name)
                # Ensure name label text color is correct for files too
                name_label.configure(foreground=PICSNEST_TEXT_LIGHT)
                # Child label backgrounds for files should be handled by their own styles
                # or set to match the file item's styled background if necessary.
                # Typically, "PicsNest.ItemThumb.TLabel" and "PicsNest.ItemName.TLabel"
                # would have `background="parent"` or a specific color from the theme.

            widget_frame.update_idletasks()

    def delete_selected_items_action_entry(self, items_to_delete_override=None, from_viewer=False):
        return action_handlers.handle_delete_items(self, items_to_delete_override, from_viewer)
    def _undo_last_action(self):
        action_handlers.handle_undo_action(self)
    def _find_similar_images_action_entry(self, triggered_by_filter_toggle=False):
        action_handlers.trigger_find_similar_images(self, triggered_by_filter_toggle)
    def _consolidate_media_action_entry(self):
        action_handlers.prompt_and_consolidate_media(self)
    def _organize_media_by_date_action_entry(self):
        action_handlers.prompt_and_organize_media_by_date(self)
    def _auto_delete_similar_half_action_entry(self):
        action_handlers.handle_auto_delete_similar_half(self)
    def _delete_all_errored_action_entry(self):
        action_handlers.handle_delete_all_errored(self)
    def _move_all_errored_action_entry(self):
        action_handlers.handle_move_all_errored(self)
    def _separate_files_action_entry(self):
        action_handlers.prompt_and_separate_files(self)


if __name__ == "__main__":
    if Image is None or ImageTk is None:
        try:
            root_check = tk.Tk()
            root_check.withdraw()
            messagebox.showerror("Critical Error", "Pillow library not found.\nPlease install it using: pip install Pillow", parent=root_check)
            root_check.destroy()
        except tk.TclError:
            print("CRITICAL ERROR: Pillow library not found. Please install it using: pip install Pillow")
        sys.exit(1)
    root_app = tk.Tk()
    app_instance = PhotoVideoManagerApp(root_app)
    root_app.mainloop()