#app_manager.py
# --- Imports ---
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
import sys
import subprocess
import threading
import queue
import time
import json, math, shutil # Ensure shutil is imported
# import math # Keep if still used directly, otherwise remove
import collections # For deque (Undo stack)
from datetime import datetime

# Local imports for viewers and constants
from image_viewer import ImageViewerWindow
from video_viewer import VideoViewerWindow
from constants import * # Import all constants
from constants import TRASH_MAX_ITEMS # Specifically for app_manager if needed, or rely on action_handlers

# --- External Libraries ---
# These are checked and messages shown in __init__
try:
    from PIL import Image, ImageTk, UnidentifiedImageError
except ImportError:
    Image = None
    ImageTk = None
    UnidentifiedImageError = None
    # Critical error handled in main.py

try:
    import vlc as vlc_module # Alias to avoid conflict if vlc is also a var name
except ImportError:
    vlc_module = None

try:
    import imagehash as imagehash_module # Alias
except ImportError:
    imagehash_module = None

try:
    import cv2 as cv2_module # Alias
except ImportError:
    cv2_module = None

# --- Modularized Utilities ---
from app_manager_utils import ui_creator, file_operations, action_handlers


# --- Application Class ---
class PhotoVideoManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Photo & Video Manager")
        self.root.geometry("1250x800")

        # Store library references for other modules to access via app_instance
        self.Image = Image
        self.ImageTk = ImageTk
        self.UnidentifiedImageError = UnidentifiedImageError
        self.vlc = vlc_module # Use the aliased import
        self.imagehash = imagehash_module # Use the aliased import
        self.cv2 = cv2_module # Use the aliased import

        # Add constants here to be accessible via app_instance as used in action_handlers.py
        self.IMAGE_EXTENSIONS = IMAGE_EXTENSIONS
        self.VIDEO_EXTENSIONS = VIDEO_EXTENSIONS
        # Other constants from constants.py can be added here if needed by helper modules via app_instance
        self.TRASH_MAX_ITEMS = TRASH_MAX_ITEMS # Make accessible if needed

        # Config paths
        self.CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
        self.FOLDER_THUMB_DB_FILE = os.path.join(self.CONFIG_DIR, FOLDER_THUMB_DB_FILENAME)
        self.TRASH_DIR = os.path.join(self.CONFIG_DIR, TRASH_DIR_NAME)
        os.makedirs(self.TRASH_DIR, exist_ok=True)

        # Core State Variables
        self.current_folder = tk.StringVar(value="No folder selected")
        self.folder_history = []
        self.items_in_view = {} # path: {widget, thumb_label, name_label, type, is_error, etc.}

        self.selected_item_paths = set()

        self.thumbnail_queue = queue.Queue()
        self.active_thumbnail_thread = None # Thread for batch thumbnail generation
        self.cancel_long_operation = threading.Event() # For any long task

        self.folder_thumb_db = self._load_folder_thumb_db()

        self.all_folder_items_raw = [] # All items scanned from folder, before any filtering
        self.all_folder_items = []     # Items after type filtering (image/video) but before similarity filter
        self.displayed_item_count = 0
        self.current_grid_row = 0
        self.current_grid_col = 0
        self.is_loading_batch = False

        # Rubber band selection
        self.rubber_band_rect = None
        self.rubber_band_start_x = 0
        self.rubber_band_start_y = 0

        self.undo_stack = collections.deque(maxlen=UNDO_STACK_MAX_SIZE)

        # Filter and View Variables
        self.show_only_similar_var = tk.BooleanVar(value=False)
        self.show_images_var = tk.BooleanVar(value=True)
        self.show_videos_var = tk.BooleanVar(value=True)

        # Similarity Search State
        self.similar_image_groups = []    # List of sets, where each set contains paths of similar images
        self.image_hashes_cache = {}      # path: image_hash_object
        self.marked_similar_paths = set() # All paths that are part of any similar group
        self.is_finding_similar = False   # Flag to prevent multiple concurrent searches
        self.similarity_threshold = 5     # Imagehash difference threshold
        self._was_filter_active_before_style_refresh = False # Internal state for UI refresh
        self._similarity_scan_done_for_current_folder = False # Flag per folder

        # --- UI Creation using ui_creator ---
        self.root.grid_columnconfigure(0, weight=3)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        ui_creator.create_menu(self)
        ui_creator.create_top_bar(self)
        ui_creator.create_main_content_area(self)
        ui_creator.create_preview_area(self)
        ui_creator.create_action_bar(self)
        ui_creator.apply_app_styles()

        # --- Post-UI Initialization ---
        self.root.after(100, self._process_thumbnail_queue)
        self.update_ui_state()

        # --- Global Event Bindings ---
        self.root.bind("<Delete>", self.on_delete_key_press)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- Library Warnings ---
        if self.vlc is None:
            messagebox.showwarning("VLC Warning", "VLC library (python-vlc) not found. Video playback features will be limited or disabled.\nPlease install it for full video support (e.g., 'pip install python-vlc').", parent=self.root)
        if self.imagehash is None:
             messagebox.showwarning("ImageHash Warning", "The 'imagehash' library is not found. 'Find Similar Images' feature will be disabled.\nPlease install it: pip install imagehash", parent=self.root)
        if self.cv2 is None:
            messagebox.showwarning("OpenCV Warning", "The 'opencv-python' (cv2) library is not found. Video thumbnails will not be generated.\nPlease install it: pip install opencv-python", parent=self.root)
        if self.Image is None or self.ImageTk is None: # Should be caught by main.py but good to check
            messagebox.showerror("Critical Error", "Pillow library failed to load. Application cannot continue.", parent=self.root)
            self.root.destroy()
            sys.exit(1)


    # --- Application Lifecycle & Configuration ---
    def on_closing(self):
        self._save_folder_thumb_db()
        self.cancel_long_operation.set()
        # Ensure any running threads are signaled to stop
        if self.active_thumbnail_thread and self.active_thumbnail_thread.is_alive():
            self.active_thumbnail_thread.join(timeout=0.5) # Brief wait
        # Add joins for other potential long-running threads if necessary

        self._empty_trash_permanently() # Empty the trash before destroying the root window

        self.root.destroy()

    def _empty_trash_permanently(self):
        """Permanently deletes all items in the application's trash directory."""
        if not os.path.isdir(self.TRASH_DIR):
            # print(f"Trash directory {self.TRASH_DIR} not found. Nothing to empty.")
            return

        # print(f"Attempting to empty trash directory: {self.TRASH_DIR}")
        items_deleted_count = 0
        items_failed_count = 0

        for item_name in os.listdir(self.TRASH_DIR):
            item_path = os.path.join(self.TRASH_DIR, item_name)
            try:
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.unlink(item_path)
                    items_deleted_count += 1
                elif os.path.isdir(item_path): # Should not happen with current trash logic
                    shutil.rmtree(item_path)
                    items_deleted_count += 1
            except Exception as e:
                items_failed_count += 1
                print(f"Error deleting {item_path} from trash: {e}")

        # if items_deleted_count > 0 or items_failed_count > 0:
            # print(f"Trash emptying complete. Deleted: {items_deleted_count}, Failed: {items_failed_count}.")
        if items_failed_count > 0 and self.root.winfo_exists(): # Only show message if app window still there
             messagebox.showwarning("Trash Emptying Issue",
                                   f"Could not delete all items from trash. {items_failed_count} items may remain in {self.TRASH_DIR}",
                                   parent=self.root)

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

    # --- UI Event Handlers & Callbacks (Canvas, Frame, Mousewheel) ---
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
        # Condition to load more: near bottom or if content is smaller than canvas
        if (scroll_info[1] > 0.85 or \
           (scroll_info[0] == 0.0 and scroll_info[1] == 1.0 and self.item_frame.winfo_height() < self.canvas.winfo_height())) \
           and self.displayed_item_count < len(self.all_folder_items):
            self._load_next_batch_of_items()

    def _on_canvas_press_for_rubber_band(self, event):
        # Click on canvas directly (not on an item) clears selection for rubber band
        clicked_widget = event.widget
        if clicked_widget == self.canvas: # Only if click is directly on canvas
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
            self.canvas.itemconfigure("rubber_band_tag", state='hidden') # Hide then delete
            end_x = self.canvas.canvasx(event.x)
            end_y = self.canvas.canvasy(event.y)

            sel_x1 = min(self.rubber_band_start_x, end_x)
            sel_y1 = min(self.rubber_band_start_y, end_y)
            sel_x2 = max(self.rubber_band_start_x, end_x)
            sel_y2 = max(self.rubber_band_start_y, end_y)

            # Check if it was a click (small area) vs a drag
            if abs(sel_x1 - sel_x2) < 5 and abs(sel_y1 - sel_y2) < 5:
                # It was a click on canvas, selection already cleared by _on_canvas_press_for_rubber_band
                self.canvas.delete(self.rubber_band_rect)
                self.rubber_band_rect = None
                self.update_preview_and_info()
                self.update_ui_state()
                return

            newly_selected_paths = set()
            for item_path, info in self.items_in_view.items():
                widget = info['widget']
                if not widget.winfo_exists(): continue

                # Get widget geometry relative to the canvas
                # widget.winfo_rootx/y() are screen coords. We need canvas coords.
                # Item frame is the direct child of canvas window.
                # So widget.winfo_x/y() should be relative to item_frame.
                # Add item_frame's position if it's not (0,0) in canvas scrollregion.
                # However, since canvas.create_window places item_frame at (0,0) initially
                # and scrollregion handles the view, widget.winfo_x/y directly should be okay
                # if the rubber band coords are also canvas coords (which they are via canvasx/y).

                x, y = widget.winfo_x(), widget.winfo_y()
                w, h = widget.winfo_width(), widget.winfo_height()

                # Check for overlap
                if not (sel_x2 < x or sel_x1 > x + w or sel_y2 < y or sel_y1 > y + h):
                    newly_selected_paths.add(item_path)

            if newly_selected_paths:
                self.selected_item_paths = newly_selected_paths # Replace selection
                for path in self.selected_item_paths:
                    if path in self.items_in_view and self.items_in_view[path]['widget'].winfo_exists():
                        style = self._get_item_style(path, self.items_in_view[path])
                        self.items_in_view[path]['widget'].configure(style=style)

            self.canvas.delete(self.rubber_band_rect) # Ensure it's deleted
            self.rubber_band_rect = None
            self.update_preview_and_info()
            self.update_ui_state()

    # --- Folder Navigation & Loading ---
    def select_root_folder(self):
        folder_path = filedialog.askdirectory(parent=self.root)
        if folder_path:
            self.folder_history = [] # Reset history for a new root
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
            self._similarity_scan_done_for_current_folder = False
            if hasattr(self, 'status_label') and self.status_label: self.status_label.config(text="")
            self._was_filter_active_before_style_refresh = self.show_only_similar_var.get()

        if not os.path.isdir(folder_path):
            messagebox.showerror("Error", "Cannot access folder.", parent=self.root)
            if is_new_folder_context: self.current_folder.set("No folder selected")
            self.all_folder_items_raw = []
            self.all_folder_items = []
            self.clear_view()
            self.update_ui_state()
            return

        # Cancel any ongoing thumbnail generation for the previous folder
        if self.active_thumbnail_thread and self.active_thumbnail_thread.is_alive():
            self.cancel_long_operation.set()
            # self.active_thumbnail_thread.join(timeout=0.2) # Brief wait
        self.cancel_long_operation.clear() # Reset for new operations

        # Clear the thumbnail queue
        while not self.thumbnail_queue.empty():
            try: self.thumbnail_queue.get_nowait()
            except queue.Empty: break

        self.current_folder.set(folder_path)
        self.clear_view() # Clears displayed items, selected_item_paths, resets grid counters

        current_raw_items = []
        try:
            for entry in os.scandir(folder_path):
                try:
                    is_dir, is_file = entry.is_dir(), entry.is_file()
                except OSError: continue # Skip if cannot determine type (e.g. permission denied early)

                item_type = 'folder' if is_dir else ('file' if is_file else 'other')
                if item_type == 'other': continue

                current_raw_items.append({'path': entry.path, 'name': entry.name, 'type': item_type, 'is_error': False})
        except OSError as e:
            messagebox.showerror("Error", f"Error reading folder: {e}", parent=self.root)
            self.current_folder.set("Error reading folder")
            self.all_folder_items_raw = []
            self.all_folder_items = []
            self.update_ui_state()
            return

        # Sort folders first, then files, alphabetically
        current_raw_items.sort(key=lambda x: (x['type'] != 'folder', x['name'].lower()))
        self.all_folder_items_raw = current_raw_items

        # Apply view filters (Show Images/Videos)
        self._apply_type_filters_to_items_list()

        # --- START OF MODIFIED SECTION FOR SIMILARITY FILTERING AND ORDERING ---
        if self.show_only_similar_var.get():
            if self._similarity_scan_done_for_current_folder and self.marked_similar_paths and self.similar_image_groups:
                # "Show Only Similar" is ON, scan is done, and similar images were found.
                # Reorder self.all_folder_items: folders first, then groups of similar images.

                folders_in_view = [item for item in self.all_folder_items if item['type'] == 'folder']

                # Create a lookup for quick access to item data from self.all_folder_items.
                # This list (self.all_folder_items) has already been type-filtered by _apply_type_filters_to_items_list.
                path_to_item_data_map = {item['path']: item for item in self.all_folder_items if item['type'] == 'file'}

                grouped_similar_items_display_list = []

                # Sort the groups themselves for a consistent order of groups.
                # Each group is a set of paths. Sort by the first path in each (sorted) group.
                sorted_similar_groups = sorted(
                    list(self.similar_image_groups),
                    key=lambda g: sorted(list(g))[0] if g else ""
                )

                for group_paths_set in sorted_similar_groups:
                    current_group_batch = []
                    # Sort paths within each group for consistent order of items within a group.
                    for path in sorted(list(group_paths_set)):
                        if path in path_to_item_data_map: # Ensure item is valid and passed type filters
                            current_group_batch.append(path_to_item_data_map[path])

                    if current_group_batch: # Only add if the group has items visible after type filtering
                        grouped_similar_items_display_list.extend(current_group_batch)

                self.all_folder_items = folders_in_view + grouped_similar_items_display_list
            else:
                # "Show Only Similar" is ON, but either scan not done, no similar paths marked, or no groups.
                # In this case, show only folders. self.all_folder_items is already type-filtered.
                self.all_folder_items = [item for item in self.all_folder_items if item['type'] == 'folder']
        # else: (show_only_similar_var is OFF)
            # self.all_folder_items is already correctly populated by _apply_type_filters_to_items_list().
            # No special reordering for similarity is done here, but items will still be *styled* as similar.
            # So, no specific 'else' block needed here; self.all_folder_items remains as is from type filtering.
        if self.all_folder_items:
            self._load_next_batch_of_items()
        else:
            # Ensure canvas scroll region is updated even if no items
            self.item_frame.update_idletasks()
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        self.update_ui_state()

    def _apply_type_filters_to_items_list(self):
        """Filters all_folder_items_raw based on show_images_var and show_videos_var."""
        temp_filtered_items = []
        for item in self.all_folder_items_raw:
            if item['type'] == 'folder':
                temp_filtered_items.append(item)
                continue
            if item['type'] == 'file':
                _, ext = os.path.splitext(item['name'])
                ext_lower = ext.lower()
                is_image = ext_lower in IMAGE_EXTENSIONS
                is_video = ext_lower in VIDEO_EXTENSIONS

                if (self.show_images_var.get() and is_image) or \
                   (self.show_videos_var.get() and is_video):
                    temp_filtered_items.append(item)
        self.all_folder_items = temp_filtered_items


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
        self.displayed_item_count = end_index # Update count of displayed items from all_folder_items

        # Files to process for thumbnails in this batch
        files_to_process_this_batch = [item for item in items_for_this_batch if item['type'] == 'file']
        if files_to_process_this_batch:
            # Start a new thumbnail thread for this batch
            # Cancel previous one if it was still running (already done in load_items)
            thumb_thread = threading.Thread(target=self._thumbnail_generator_thread_runner,
                                      args=(files_to_process_this_batch, self.cancel_long_operation),
                                      daemon=True)
            self.active_thumbnail_thread = thumb_thread # Store reference to the new thread
            thumb_thread.start()

        self.is_loading_batch = False
        self.root.after_idle(self.on_scroll_check_lazy_load) # Check if more can be loaded immediately

    def _populate_grid_with_batch(self, items_in_batch):
        for item_data in items_in_batch:
            widget_info = self._create_placeholder_widget(self.item_frame, item_data)
            widget_info['widget'].grid(row=self.current_grid_row, column=self.current_grid_col, padx=5, pady=5, sticky="nsew")

            # Bindings for selection and double-click
            # Path must be passed correctly to lambda
            for widget_element in [widget_info['widget'], widget_info['thumb_label'], widget_info['name_label']]:
                widget_element.bind("<Button-1>", lambda e, p=item_data['path'], wf=widget_info['widget']:
                    self._on_item_click_for_selection(e, p, wf))

                if item_data['type'] == 'folder':
                    widget_element.bind("<Double-Button-1>", lambda e, p=item_data['path']: self.navigate_to_folder(p))
                elif item_data['type'] == 'file':
                    if item_data['path'].lower().endswith(IMAGE_EXTENSIONS):
                        widget_element.bind("<Double-Button-1>", lambda e, p=item_data['path']: self._open_image_viewer_action(p))
                    elif item_data['path'].lower().endswith(VIDEO_EXTENSIONS):
                        widget_element.bind("<Double-Button-1>", lambda e, p=item_data['path']:
                            self._open_video_viewer_action(p) if self.vlc else self._open_with_system(p))

            self.items_in_view[item_data['path']] = {
                **widget_info,  # Contains 'widget', 'thumb_label', 'name_label'
                'type': item_data['type'],
                'is_error': False # Initial state, updated by thumbnail processor
            }

            self.current_grid_col += 1
            if self.current_grid_col >= GRID_COLUMNS:
                self.current_grid_col = 0
                self.current_grid_row += 1

        for c_idx in range(GRID_COLUMNS): self.item_frame.grid_columnconfigure(c_idx, weight=1)
        self.item_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))


    def _create_placeholder_widget(self, parent_frame, item_data):
        item_path, item_name, item_type = item_data['path'], item_data['name'], item_data['type']

        # Initial style determination (might be updated once thumbnail loads)
        initial_style_info = {'type': item_type, 'is_error': False} # Base info for style
        style_name = self._get_item_style(item_path, initial_style_info)

        widget_frame = ttk.Frame(parent_frame, style=style_name, padding=3)

        thumb_label = ttk.Label(widget_frame, anchor='center')
        thumb_label.pack(fill=tk.BOTH, expand=True) # Fill available space for thumb

        name_label = ttk.Label(widget_frame, text=item_name, anchor='center', wraplength=GRID_THUMBNAIL_SIZE[0]-10)
        name_label.pack(fill=tk.X, side=tk.BOTTOM)

        if item_type == 'folder':
            thumb_label.config(text="FOLDER", font=("Arial", 10, "bold")) # Placeholder text
        else: # For files
            thumb_label.config(text=LOADING_TEXT, font=("Arial", 10))

        return {'widget': widget_frame, 'thumb_label': thumb_label, 'name_label': name_label}

    # --- Thumbnail Generation & Processing ---
    def _thumbnail_generator_thread_runner(self, items_to_process_batch, cancel_event_ref):
        """
        Thread worker that iterates through a batch of items and generates thumbnails.
        Uses file_operations.generate_single_thumbnail.
        """
        for item_data in items_to_process_batch:
            if cancel_event_ref.is_set():
                # print(f"Thumbnail generation cancelled for batch.")
                break # Exit if cancellation is requested

            # Call the core thumbnail generation function from file_operations
            thumb_image, error_flag = file_operations.generate_single_thumbnail(
                item_data,
                GRID_THUMBNAIL_SIZE,
                self.Image, # Pass PIL.Image
                self.UnidentifiedImageError, # Pass PIL.UnidentifiedImageError
                self.cv2     # Pass cv2 module
            )

            # Add to queue for UI update in main thread
            self.thumbnail_queue.put({
                'path': item_data['path'],
                'image': thumb_image,
                'error': error_flag,
                'type': item_data['type'] # Keep type for context if needed
            })
        # print(f"Thumbnail thread finished for a batch.")


    def _process_thumbnail_queue(self):
        max_updates_per_cycle = 10 # Limit updates per call to keep UI responsive
        processed_count = 0
        try:
            while not self.thumbnail_queue.empty() and processed_count < max_updates_per_cycle:
                result = self.thumbnail_queue.get_nowait()
                processed_count += 1

                item_path = result['path']
                if item_path in self.items_in_view:
                    widget_info = self.items_in_view[item_path]
                    widget_frame = widget_info['widget']
                    thumb_display_label = widget_info['thumb_label'] # This is the ttk.Label for the image

                    # Update error state based on thumbnail generation result
                    widget_info['is_error'] = result['error']

                    if widget_frame.winfo_exists() and thumb_display_label.winfo_exists():
                        # Get the correct style based on new error state, selection, similarity
                        final_style = self._get_item_style(item_path, widget_info)
                        widget_frame.configure(style=final_style)

                        if result['error']:
                            thumb_display_label.config(image='', text="Error", font=("Arial", 9, "bold"), foreground="red")
                            if hasattr(thumb_display_label, 'image_ref'): # Keep PhotoImage ref
                                thumb_display_label.image_ref = None
                        elif result['image']: # Successfully generated PIL image
                            try:
                                 tk_image = self.ImageTk.PhotoImage(result['image'])
                                 thumb_display_label.image_ref = tk_image # Store reference
                                 thumb_display_label.config(image=tk_image, text="")
                            except Exception as e_tk: # Error converting PIL to Tk PhotoImage
                                 print(f"Tkinter PhotoImage error for {item_path}: {e_tk}")
                                 thumb_display_label.config(image='', text="Display Err", font=("Arial", 8))
                                 widget_info['is_error'] = True # Mark as error for styling
                                 widget_frame.configure(style=self._get_item_style(item_path, widget_info))
                                 if hasattr(thumb_display_label, 'image_ref'):
                                     thumb_display_label.image_ref = None
                        else: # No image generated, but not an error (e.g., video without cv2, or non-media file)
                            if item_path.lower().endswith(VIDEO_EXTENSIONS):
                                thumb_display_label.config(image='', text="📹 Video", font=("Arial", 10, "bold"))
                            # Could add more specific placeholders for other file types if needed
                            if hasattr(thumb_display_label, 'image_ref'):
                                thumb_display_label.image_ref = None
        except queue.Empty:
            pass # No items in queue
        except Exception as e:
            print(f"Error processing thumbnail queue: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.root.after(100, self._process_thumbnail_queue) # Schedule next check


    # --- UI Update & State Management ---
    def clear_view(self):
        for item_path_in_view in list(self.items_in_view.keys()): # Iterate over keys copy
            widget_info = self.items_in_view.pop(item_path_in_view, None)
            if widget_info and widget_info['widget'].winfo_exists():
                widget_info['widget'].destroy()

        self.items_in_view.clear()
        self.selected_item_paths.clear()
        self.reset_preview()

        # Reset grid layout counters
        self.displayed_item_count = 0
        self.current_grid_row = 0
        self.current_grid_col = 0
        self.is_loading_batch = False # Ensure this is reset

        # Reset canvas scroll position and region
        self.canvas.yview_moveto(0)
        self.canvas.xview_moveto(0)
        self.item_frame.update_idletasks() # Ensure item_frame size is calculated if empty
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _clear_all_selection_visuals(self):
        # Iterate over a copy of selected_item_paths in case it's modified elsewhere (though unlikely here)
        paths_to_restyle = list(self.selected_item_paths)
        for path_to_clear_sel in paths_to_restyle:
            if path_to_clear_sel in self.items_in_view:
                info = self.items_in_view[path_to_clear_sel]
                widget = info['widget']
                if widget.winfo_exists():
                    # Get style WITHOUT selection, but considering other states (error, similar, type)
                    style_name = self._get_item_style(path_to_clear_sel, info, force_deselected=True)
                    try:
                        widget.configure(style=style_name)
                    except tk.TclError: # Handle if widget is destroyed mid-operation
                        pass

    def _get_item_style(self, item_path, item_info, force_deselected=False):
        is_selected = (item_path in self.selected_item_paths) and not force_deselected
        is_similar = item_path in self.marked_similar_paths # Assumes marked_similar_paths is current
        is_error = item_info.get('is_error', False)
        item_type = item_info['type']

        if is_selected: return "Selected.TFrame"
        # Similar style only applies if not selected, and item is a file
        if is_similar and item_type == 'file': return "Similar.TFrame"

        if item_type == 'folder': return "Folder.TFrame"
        elif item_type == 'file':
            if is_error: return "Error.TFrame"
            # Check if a thumbnail image is actually displayed on the label
            has_thumb_image_displayed = False
            if 'thumb_label' in item_info and item_info['thumb_label'].winfo_exists():
                # Check if the label has an image attribute and it's set
                if hasattr(item_info['thumb_label'], 'image_ref') and item_info['thumb_label'].image_ref:
                    has_thumb_image_displayed = True

            return "ItemLoaded.TFrame" if has_thumb_image_displayed else "Item.TFrame" # Item.TFrame is placeholder
        return "Item.TFrame" # Default fallback

    def _on_item_click_for_selection(self, event, item_path_clicked, widget_frame_clicked):
        # Handle Ctrl/Shift for multi-selection later if desired. For now, single selection.

        # First, clear visuals of previously selected items
        self._clear_all_selection_visuals()

        # Then, set the new selection
        self.selected_item_paths = {item_path_clicked} # Replace current selection

        # Apply 'selected' style to the newly clicked item's frame
        if item_path_clicked in self.items_in_view and widget_frame_clicked.winfo_exists():
            item_info = self.items_in_view[item_path_clicked]
            style_name = self._get_item_style(item_path_clicked, item_info) # This will now include "Selected.TFrame"
            widget_frame_clicked.configure(style=style_name)

        self.update_preview_and_info()
        self.update_ui_state()

    def reset_preview(self):
        self.preview_label.config(image='', text="Select an item", background="lightgrey")
        if hasattr(self.preview_label, 'image_ref'): self.preview_label.image_ref = None
        self.preview_image_obj = None # Deprecate in favor of image_ref on label itself

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

            if not item_info or not os.path.exists(item_path):
                self.reset_preview()
                self.info_name_label.config(text="Name: Error/Not Found")
                return

            item_type = item_info['type']
            file_name = os.path.basename(item_path)
            self.info_name_label.config(text=f"Name: {file_name}")
            self.info_type_label.config(text=f"Type: {item_type.capitalize()}")

            preview_bg_color_default = ttk.Style().lookup("TFrame", "background") # Default background

            if item_type == 'file':
                try:
                    size_bytes = os.path.getsize(item_path)
                    size_mb = size_bytes / (1024*1024)
                    size_kb = size_bytes / 1024
                    self.info_size_label.config(text=f"Size: {size_mb:.2f} MB" if size_mb >= 1.0 else f"{size_kb:.1f} KB")

                    preview_text_content = "No preview available"
                    preview_final_bg = preview_bg_color_default
                    generated_preview_image = None

                    if item_path.lower().endswith(IMAGE_EXTENSIONS):
                        img_pil_preview = self.Image.open(item_path)
                        img_pil_preview.thumbnail(PREVIEW_THUMBNAIL_SIZE, self.Image.Resampling.LANCZOS)
                        if img_pil_preview.mode not in ('RGB','RGBA'): img_pil_preview = img_pil_preview.convert('RGB')
                        generated_preview_image = self.ImageTk.PhotoImage(img_pil_preview)
                        preview_text_content = "" # Clear text if image is shown
                        # preview_final_bg = IMAGE_VIEWER_BG # Optional: use specific bg for images

                    elif item_path.lower().endswith(VIDEO_EXTENSIONS) and self.cv2:
                        cap = None
                        try:
                            cap = self.cv2.VideoCapture(item_path)
                            if cap.isOpened():
                                frame_count = int(cap.get(self.cv2.CAP_PROP_FRAME_COUNT))
                                frame_no = min(frame_count // 10, 100) if frame_count > 10 else 0
                                cap.set(self.cv2.CAP_PROP_POS_FRAMES, frame_no)
                                ret, frame = cap.read()
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
                            preview_final_bg = ERROR_COLOR
                        finally:
                            if cap: cap.release()

                    self.preview_label.config(text=preview_text_content, background=preview_final_bg)
                    if generated_preview_image:
                        self.preview_label.config(image=generated_preview_image)
                        self.preview_label.image_ref = generated_preview_image # Keep ref
                    else:
                        self.preview_label.config(image='')
                        if hasattr(self.preview_label, 'image_ref'): self.preview_label.image_ref = None

                except self.UnidentifiedImageError:
                    self.preview_label.config(image='', text="Preview Error (Format?)", background=ERROR_COLOR)
                    if hasattr(self.preview_label, 'image_ref'): self.preview_label.image_ref = None
                except Exception as e_prev:
                    print(f"Error updating preview for {item_path}: {e_prev}")
                    self.preview_label.config(image='', text="Preview Error", background=ERROR_COLOR)
                    if hasattr(self.preview_label, 'image_ref'): self.preview_label.image_ref = None

            elif item_type == 'folder':
                self.info_size_label.config(text="Size: -") # Folders don't show size here
                self.preview_label.config(image='', text="Folder Selected", background=preview_bg_color_default)
                if hasattr(self.preview_label, 'image_ref'): self.preview_label.image_ref = None
        else: # Multiple items selected
            self.preview_label.config(image='', text=f"{len(self.selected_item_paths)} items selected", background=preview_bg_color_default)
            if hasattr(self.preview_label, 'image_ref'): self.preview_label.image_ref = None
            self.info_name_label.config(text="Name: Multiple items")
            self.info_size_label.config(text="Size: -")
            self.info_type_label.config(text="Type: Mixed")

    def update_ui_state(self):
        # Up button
        self.up_button.config(state=tk.NORMAL if self.folder_history else tk.DISABLED)

        num_selected = len(self.selected_item_paths)
        can_open_single = num_selected == 1
        can_delete_any = num_selected > 0

        # Action buttons
        self.open_button.config(state=tk.NORMAL if can_open_single else tk.DISABLED)
        self.delete_button.config(state=tk.NORMAL if can_delete_any else tk.DISABLED)

        # Undo functionality
        undo_state = tk.NORMAL if self.undo_stack else tk.DISABLED
        self.undo_button.config(state=undo_state)
        if hasattr(self, 'edit_menu'): # Check if menu exists
            try:
                self.edit_menu.entryconfigure("Undo", state=undo_state)
            except tk.TclError: # Menu might not be fully initialized yet or destroyed
                pass


    # --- Item Actions (Open, Delete via key) ---
    def _open_image_viewer_action(self, image_path_to_open):
        # Collect all *currently visible and valid* images from self.all_folder_items
        # This list respects the current type (image/video) filters.
        all_images_in_current_view = [
            item['path'] for item in self.all_folder_items # Use filtered list for viewer context
            if item['type'] == 'file' and item['path'].lower().endswith(IMAGE_EXTENSIONS) and os.path.exists(item['path'])
        ]
        if not all_images_in_current_view:
            if os.path.exists(image_path_to_open) and image_path_to_open.lower().endswith(IMAGE_EXTENSIONS):
                 all_images_in_current_view = [image_path_to_open] # Fallback if only the clicked one is valid
            else:
                messagebox.showinfo("Viewer", "No suitable images to view in the current filter context.", parent=self.root)
                return

        try:
            current_idx = all_images_in_current_view.index(image_path_to_open)
        except ValueError: # If the double-clicked item isn't in the filtered list (should not happen if logic is correct)
            if os.path.exists(image_path_to_open) and image_path_to_open.lower().endswith(IMAGE_EXTENSIONS):
                # This case is tricky: if it was filtered out, should we add it?
                # For now, let's assume if it was double-clicked, it should be viewable if it's an image.
                # A cleaner approach might be to ensure _populate_grid_with_batch only uses self.all_folder_items.
                all_images_in_current_view.append(image_path_to_open) # Add it if valid but not found
                current_idx = len(all_images_in_current_view) - 1
            else:
                messagebox.showerror("Error", "Cannot find the selected image for the viewer.", parent=self.root)
                return
        ImageViewerWindow(self.root, all_images_in_current_view, current_idx, self)

    def _open_video_viewer_action(self, video_path_to_open):
        # Similar logic to image viewer for collecting video paths
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


    def open_selected_item_action(self): # Invoked by "Open/View" button
        if not self.selected_item_paths or len(self.selected_item_paths) != 1: return
        item_path = list(self.selected_item_paths)[0]

        # Get info from items_in_view, not all_folder_items, as it's about the *displayed* item
        item_info_from_view = self.items_in_view.get(item_path)
        if not item_info_from_view or not os.path.exists(item_path):
            messagebox.showerror("Error", "Selected item not found or no longer exists.", parent=self.root)
            # Optionally, refresh view if item is missing
            # self.load_items(self.current_folder.get())
            return

        item_type = item_info_from_view['type']
        if item_type == 'folder':
            self.navigate_to_folder(item_path)
        elif item_type == 'file':
            if item_path.lower().endswith(IMAGE_EXTENSIONS):
                self._open_image_viewer_action(item_path)
            elif item_path.lower().endswith(VIDEO_EXTENSIONS):
                if self.vlc: # Check if VLC library is available
                    self._open_video_viewer_action(item_path)
                else:
                    self._open_with_system(item_path) # Fallback if VLC not present
            else: # Other file types
                self._open_with_system(item_path)

    def _open_with_system(self, path_to_open):
        try:
            if sys.platform == "win32":
                os.startfile(os.path.realpath(path_to_open)) # realpath for symlinks
            elif sys.platform == "darwin": # macOS
                subprocess.Popen(["open", path_to_open])
            else: # Linux and other Unix-like
                subprocess.Popen(["xdg-open", path_to_open])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open file/folder with system default: {e}", parent=self.root)

    def on_delete_key_press(self, event=None):
        # This now calls the entry point which then calls the action_handler
        self.delete_selected_items_action_entry()

    # --- Undo Stack Management ---
    def _add_to_undo_stack(self, action_type_str, **kwargs_action_data):
        self.undo_stack.append({'action_type': action_type_str, **kwargs_action_data})
        self.update_ui_state() # Update Undo button state


    # --- Filtering and View Refresh ---
    def handle_show_similar_toggle(self):
        # If "Show Only Similar" is Toggled ON AND a scan hasn't been done for this folder
        if self.show_only_similar_var.get() and not self._similarity_scan_done_for_current_folder and not self.is_finding_similar:
            if self.imagehash: # Check if library is available
                self.status_label.config(text="Auto-scan for similar...")
                # Call the entry point for finding similar images
                self._find_similar_images_action_entry(triggered_by_filter_toggle=True)
            else:
                messagebox.showwarning("ImageHash Missing", "ImageHash library not found. Cannot find/show similar images.", parent=self.root)
                self.show_only_similar_var.set(False) # Revert toggle
                return # Don't proceed to refresh
        else:
            # If toggled OFF, or scan already done, or scan in progress (will refresh on completion)
            # Just apply all filters and refresh the view.
            self.apply_all_filters_and_refresh()

    def apply_all_filters_and_refresh(self):
        # This method re-triggers load_items which will:
        # 1. Re-scan the directory (for self.all_folder_items_raw)
        # 2. Apply type filters (show_images_var, show_videos_var)
        # 3. Apply similarity filter (show_only_similar_var) if active and data available
        # 4. Reload the grid display.

        current_scroll_y = self.canvas.yview()[0]
        current_scroll_x = self.canvas.xview()[0]

        current_folder_path = self.current_folder.get()
        if os.path.isdir(current_folder_path): # Ensure current folder is valid
            self.load_items(current_folder_path)
        else:
            # Handle case where current folder is no longer valid (e.g., "No folder selected")
            self.clear_view()
            self.update_ui_state()

        # Attempt to restore scroll position after reload
        self.canvas.update_idletasks() # Ensure canvas is up-to-date
        self.canvas.yview_moveto(current_scroll_y)
        self.canvas.xview_moveto(current_scroll_x)

        self._was_filter_active_before_style_refresh = self.show_only_similar_var.get()


    def _refresh_all_item_visuals(self): # Used after some operations that change item states globally
        # Example: after a similarity scan, or if styles themselves changed.
        for path, item_info_dict in self.items_in_view.items():
            if item_info_dict['widget'].winfo_exists():
                style_name = self._get_item_style(path, item_info_dict)
                try:
                    item_info_dict['widget'].configure(style=style_name)
                except tk.TclError as e_style:
                    print(f"Error applying style {style_name} to {path}: {e_style}")

    def _get_errored_item_paths(self):
        """Returns a list of paths for items currently marked as errored in the view."""
        return [
            path for path, info in self.items_in_view.items()
            if info.get('is_error', False) and os.path.exists(path) # Ensure file still exists
        ]

    # --- Entry Point Methods for Action Handlers (called by UI elements) ---
    # These methods bridge the UI commands (often set up in ui_creator) to the
    # more complex logic now residing in action_handlers.py.

    def delete_selected_items_action_entry(self, items_to_delete_override=None, from_viewer=False):
        # `self` (app_instance) is passed implicitly to action_handlers.handle_delete_items
        return action_handlers.handle_delete_items(self, items_to_delete_override, from_viewer)

    def _undo_last_action(self): # This is directly called by menu/button
        action_handlers.handle_undo_action(self)

    def _find_similar_images_action_entry(self, triggered_by_filter_toggle=False):
        action_handlers.trigger_find_similar_images(self, triggered_by_filter_toggle)

    def _consolidate_media_action_entry(self):
        action_handlers.prompt_and_consolidate_media(self)

    def _organize_media_by_date_action_entry(self):
        action_handlers.prompt_and_organize_media_by_date(self)

    # New entry point method:
    def _auto_delete_similar_half_action_entry(self):
        action_handlers.handle_auto_delete_similar_half(self)

    def _delete_all_errored_action_entry(self):
        action_handlers.handle_delete_all_errored(self)

    def _move_all_errored_action_entry(self):
        action_handlers.handle_move_all_errored(self)


if __name__ == "__main__":
    # This part is usually in main.py, but can be here for direct testing
    if Image is None or ImageTk is None:
         # Try a Tkinter messagebox if possible before full app init
        try:
            root_check = tk.Tk()
            root_check.withdraw() # Hide the main window
            messagebox.showerror("Critical Error", "Pillow library not found.\nPlease install it using: pip install Pillow", parent=root_check)
            root_check.destroy()
        except tk.TclError: # Fallback if even basic Tk fails
            print("CRITICAL ERROR: Pillow library not found. Please install it using: pip install Pillow")
        sys.exit(1)

    root_app = tk.Tk()
    app_instance = PhotoVideoManagerApp(root_app)
    root_app.mainloop()