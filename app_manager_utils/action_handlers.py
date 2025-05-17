# app_manager_utils/action_handlers.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
import shutil
import threading
import time, math



# Import core file operations
from .file_operations import (
    find_similar_images_core,
    consolidate_media_core,
    organize_media_by_date_core
)
# Constants can be imported if needed
# from constants import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from constants import TRASH_MAX_ITEMS

# PIL, imagehash, cv2 will be accessed via app_instance.Image, app_instance.imagehash, app_instance.cv2
# to avoid direct imports here, making this module more about orchestration.

# Modify handle_delete_items to return the count
def handle_delete_items(app_instance, items_to_delete_override=None, from_viewer=False):
    paths_to_process = items_to_delete_override if items_to_delete_override else app_instance.selected_item_paths.copy()
    if not paths_to_process:
        return 0 # Return 0 if no paths to process

    deleted_for_undo = []
    actually_deleted_count = 0
    items_visually_removed = False

    current_scroll_y = app_instance.canvas.yview()[0]
    current_scroll_x = app_instance.canvas.xview()[0]

    for item_path in list(paths_to_process): # Iterate over a copy
        if os.path.exists(item_path):
            item_name = os.path.basename(item_path)
            try:
                trashed_filename = f"{int(time.time())}_{item_name}"
                actual_trashed_path = os.path.join(app_instance.TRASH_DIR, trashed_filename)

                app_instance.root.config(cursor="watch")
                app_instance.root.update_idletasks()
                shutil.move(item_path, actual_trashed_path)
                app_instance.root.config(cursor="")

                deleted_for_undo.append((item_path, actual_trashed_path))
                actually_deleted_count += 1
            except Exception as e:
                app_instance.root.config(cursor="")
                messagebox.showerror("Delete Error", f"Could not move '{item_name}' to trash:\n{e}", parent=app_instance.root)
                continue # Continue with the next item

        # Visual removal and state update (even if file didn't exist, remove from view)
        if item_path in app_instance.items_in_view:
            widget_info = app_instance.items_in_view.pop(item_path, None) # Use pop with default
            if widget_info and widget_info['widget'].winfo_exists():
                widget_info['widget'].destroy()
            items_visually_removed = True

        if item_path in app_instance.selected_item_paths:
            app_instance.selected_item_paths.discard(item_path)

        app_instance.all_folder_items_raw = [item for item in app_instance.all_folder_items_raw if item['path'] != item_path]
        app_instance.all_folder_items = [item for item in app_instance.all_folder_items if item['path'] != item_path]

        if item_path in app_instance.marked_similar_paths:
            app_instance.marked_similar_paths.discard(item_path)
        for group in app_instance.similar_image_groups:
            group.discard(item_path) # discard works on sets
        app_instance.similar_image_groups = [g for g in app_instance.similar_image_groups if len(g) > 1] # Re-filter groups

    if deleted_for_undo:
        app_instance._add_to_undo_stack('delete_items', items=deleted_for_undo)
        _manage_trash_size(app_instance.TRASH_DIR) # Manage trash size after adding to undo

    if not from_viewer:
        if items_visually_removed:
            # Recalculate displayed_item_count based on items_in_view
            app_instance.displayed_item_count = len(app_instance.items_in_view)

            # If items were removed, the grid might need repacking/reindexing if we were to fill gaps.
            # For simplicity, load_items or a more complex re-grid would be needed to fill gaps.
            # Current approach: items are destroyed, scroll region updates. Lazy load handles adding more if space.
            app_instance.item_frame.update_idletasks()
            app_instance.on_frame_configure()

            app_instance.canvas.yview_moveto(current_scroll_y)
            app_instance.canvas.xview_moveto(current_scroll_x)
            app_instance.root.after_idle(app_instance.on_scroll_check_lazy_load)

        app_instance.update_preview_and_info()
        app_instance.update_ui_state()

    return actually_deleted_count # Return the count of successfully deleted items


def _manage_trash_size(trash_dir_path):
    """
    Ensures the trash directory doesn't exceed TRASH_MAX_ITEMS.
    Deletes the oldest items if the limit is surpassed.
    Files in trash are expected to be named "timestamp_originalname".
    """
    if TRASH_MAX_ITEMS <= 0: # If limit is 0 or less, effectively no trash retention beyond current op
        # This part could be enhanced to delete all if TRASH_MAX_ITEMS is 0
        # For now, a positive TRASH_MAX_ITEMS is assumed for FIFO behavior.
        # If TRASH_MAX_ITEMS is 0, all items will be deleted by num_to_delete logic anyway.
        pass

    try:
        trashed_files_with_ts = []
        for f_name in os.listdir(trash_dir_path):
            full_path = os.path.join(trash_dir_path, f_name)
            if os.path.isfile(full_path):
                try:
                    timestamp_str = f_name.split('_', 1)[0]
                    timestamp = int(timestamp_str)
                    trashed_files_with_ts.append({'path': full_path, 'timestamp': timestamp, 'name': f_name})
                except (ValueError, IndexError):
                    print(f"Warning: File in trash without expected timestamp format: {f_name}")

        trashed_files_with_ts.sort(key=lambda x: x['timestamp']) # Sort by timestamp, oldest first

        num_to_permanently_delete = len(trashed_files_with_ts) - TRASH_MAX_ITEMS
        if num_to_permanently_delete > 0:
            for i in range(num_to_permanently_delete):
                item_to_delete = trashed_files_with_ts[i]
                os.remove(item_to_delete['path'])
                # print(f"Permanently deleted from trash (capacity): {item_to_delete['name']}") # Optional debug
    except Exception as e:
        print(f"Error managing trash size in {trash_dir_path}: {e}")


def handle_undo_action(app_instance):
    if not app_instance.undo_stack:
        return

    current_scroll_y = app_instance.canvas.yview()[0]
    current_scroll_x = app_instance.canvas.xview()[0]

    last_action = app_instance.undo_stack.pop()
    action_type = last_action['action_type']
    restored_count = 0
    try:
        if action_type == 'delete_items':
            for original_path, trashed_path in last_action['items']:
                if os.path.exists(trashed_path):
                    os.makedirs(os.path.dirname(original_path), exist_ok=True)
                    shutil.move(trashed_path, original_path)
                    restored_count += 1
                else:
                    print(f"Undo warning: Trashed file {trashed_path} not found. May have been permanently deleted by trash management.")
            if restored_count > 0:
                messagebox.showinfo("Undo", f"Restored {restored_count} item(s).", parent=app_instance.root)
            elif last_action['items']: # Items were expected but none restored
                messagebox.showwarning("Undo Failed", "Could not restore items. They may have been permanently deleted from the trash.", parent=app_instance.root)
    except Exception as e:
        messagebox.showerror("Undo Error", f"Could not undo: {e}", parent=app_instance.root)

    # Refresh view for current folder
    app_instance.load_items(app_instance.current_folder.get())

    # Attempt to restore scroll position after reload
    app_instance.canvas.update_idletasks()
    app_instance.canvas.yview_moveto(current_scroll_y)
    app_instance.canvas.xview_moveto(current_scroll_x)

    app_instance.update_ui_state()


def trigger_find_similar_images(app_instance, triggered_by_filter_toggle=False):
    if app_instance.imagehash is None:
        if not triggered_by_filter_toggle:
            messagebox.showerror("Error", "The 'imagehash' library is required.\nPlease install it: pip install imagehash", parent=app_instance.root)
        return
    if app_instance.is_finding_similar:
        if not triggered_by_filter_toggle:
            messagebox.showinfo("Info", "Already searching for similar images.", parent=app_instance.root)
        return

    image_items = [
        item for item in app_instance.all_folder_items_raw
        if item['type'] == 'file' and item['path'].lower().endswith(app_instance.IMAGE_EXTENSIONS) # Use app_instance const
    ]
    if not image_items:
        if not triggered_by_filter_toggle:
            messagebox.showinfo("Info", "No images in the current folder to compare.", parent=app_instance.root)
        app_instance.status_label.config(text="No images to compare.")
        app_instance._similarity_scan_done_for_current_folder = True
        if triggered_by_filter_toggle:
            app_instance.show_only_similar_var.set(False) # Turn off toggle if no images
            app_instance.apply_all_filters_and_refresh()
        return

    app_instance.is_finding_similar = True
    app_instance.status_label.config(text="Finding similar images...")
    app_instance.cancel_long_operation.clear()

    # Prepare callback for status updates
    def status_update(text):
        if app_instance.root.winfo_exists(): # Check if root window still exists
             app_instance.root.after(0, lambda t=text: app_instance.status_label.config(text=t))

    thread = threading.Thread(
        target=find_similar_images_worker_thread_entry,
        args=(app_instance, image_items, triggered_by_filter_toggle, status_update),
        daemon=True
    )
    thread.start()

def find_similar_images_worker_thread_entry(app_instance, image_items, triggered_by_filter_toggle, status_callback):
    """Wrapper to call the core logic and handle results."""
    app_instance.image_hashes_cache.clear() # Clear old cache

    similar_groups, new_cache, marked_paths = find_similar_images_core(
        image_items,
        app_instance.similarity_threshold,
        app_instance.Image, # Pass Pillow Image
        app_instance.imagehash, # Pass imagehash module
        app_instance.cancel_long_operation,
        status_callback
    )

    if app_instance.cancel_long_operation.is_set():
        app_instance.is_finding_similar = False
        # Status already updated by core function or callback
        return

    app_instance.similar_image_groups = similar_groups
    app_instance.image_hashes_cache = new_cache
    app_instance.marked_similar_paths = marked_paths

    app_instance.is_finding_similar = False
    app_instance._similarity_scan_done_for_current_folder = True

    msg = f"Found {len(app_instance.similar_image_groups)} groups of similar images."
    if app_instance.root.winfo_exists():
        app_instance.root.after(0, lambda m=msg: app_instance.status_label.config(text=m))
        if not triggered_by_filter_toggle:
            app_instance.root.after(0, lambda m=msg: messagebox.showinfo("Similarity Check Complete", m, parent=app_instance.root))

        # Refresh the view to apply styling or filtering
        app_instance.root.after(0, app_instance.apply_all_filters_and_refresh)


def prompt_and_consolidate_media(app_instance):
    current_root_folder = app_instance.current_folder.get()
    if not os.path.isdir(current_root_folder) or current_root_folder == "No folder selected":
        messagebox.showerror("Error", "Please select a valid root folder first.", parent=app_instance.root)
        return

    destination_folder = filedialog.askdirectory(
        title="Select Destination Folder for All Media",
        parent=app_instance.root,
        mustexist=True # Ensure it exists, though worker makes subdirs
    )
    if not destination_folder: return

    # Prevent consolidating into a sub-directory of the root, unless it's the root itself (with warning)
    abs_dest = os.path.abspath(destination_folder)
    abs_root = os.path.abspath(current_root_folder)
    if abs_dest.startswith(abs_root) and abs_dest != abs_root:
        messagebox.showerror("Error", "Destination folder cannot be inside the current root folder's subdirectories (unless it's the root itself, which is not recommended for this operation).", parent=app_instance.root)
        return
    if abs_dest == abs_root:
        if not messagebox.askyesno("Warning", "Destination is the same as the root folder. This will effectively do nothing but might rename files if conflicts exist. Continue?", parent=app_instance.root):
            return

    # Create options dialog (copied and adapted from app_manager.py)
    dialog = tk.Toplevel(app_instance.root)
    dialog.title("Consolidation Options")
    dialog.transient(app_instance.root); dialog.grab_set()
    # ... (rest of dialog creation as in _consolidate_media_action) ...
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
            messagebox.showinfo("Info", "No media types selected for consolidation.", parent=app_instance.root)
            return

        media_types_str = []
        if include_images: media_types_str.append("images")
        if include_videos: media_types_str.append("videos")
        media_types_display = " and ".join(media_types_str)

        warning_message = (
            f"This will {action} ALL selected {media_types_display} from '{current_root_folder}' (and subfolders) "
            f"into '{destination_folder}'.\n"
            "Original folder structure will NOT be preserved.\n"
            "This can be intensive. ARE YOU SURE?"
        )
        if not messagebox.askyesno("Confirm Consolidation", warning_message, icon='warning', parent=app_instance.root):
            return

        app_instance.status_label.config(text=f"{action.capitalize()}ing {media_types_display}...")
        app_instance.root.config(cursor="watch")
        app_instance.cancel_long_operation.clear()

        def status_update(text):
            if app_instance.root.winfo_exists():
                app_instance.root.after(0, lambda t=text: app_instance.status_label.config(text=t))

        thread = threading.Thread(
            target=consolidate_media_worker_thread_entry,
            args=(app_instance, current_root_folder, destination_folder, action, conflict_resolution,
                  include_images, include_videos, status_update),
            daemon=True
        )
        thread.start()

    button_frame = ttk.Frame(dialog)
    button_frame.pack(pady=10)
    ttk.Button(button_frame, text="Proceed", command=on_proceed).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    dialog.update_idletasks()
    x = app_instance.root.winfo_x() + (app_instance.root.winfo_width() - dialog.winfo_width()) // 2
    y = app_instance.root.winfo_y() + (app_instance.root.winfo_height() - dialog.winfo_height()) // 2
    dialog.geometry(f"+{x}+{y}")

def consolidate_media_worker_thread_entry(app_instance, root_dir, dest_dir, action, conflict_res, incl_img, incl_vid, status_cb):
    action_count, skipped_count, error_count, total_found = consolidate_media_core(
        root_dir, dest_dir, action, conflict_res, incl_img, incl_vid,
        app_instance.cancel_long_operation, status_cb
    )

    if app_instance.root.winfo_exists():
        app_instance.root.after(0, lambda: app_instance.root.config(cursor=""))
        summary_message = (
            f"Media Consolidation Complete!\n\n"
            f"Successfully {action}d: {action_count}\n"
            f"Skipped: {skipped_count}\n"
            f"Errors: {error_count}\n"
            f"Total media files processed: {total_found}"
        )
        app_instance.root.after(0, lambda msg=summary_message: app_instance.status_label.config(text="Consolidation finished."))
        app_instance.root.after(0, lambda msg=summary_message: messagebox.showinfo("Consolidation Result", msg, parent=app_instance.root))

        if os.path.isdir(app_instance.current_folder.get()): # Refresh if current view might be affected
            app_instance.root.after(0, lambda: app_instance.load_items(app_instance.current_folder.get()))


def prompt_and_organize_media_by_date(app_instance):
    # Similar structure to prompt_and_consolidate_media
    current_root_folder = app_instance.current_folder.get()
    if not os.path.isdir(current_root_folder) or current_root_folder == "No folder selected":
        messagebox.showerror("Error", "Please select a valid root folder first.", parent=app_instance.root)
        return

    destination_base_folder = filedialog.askdirectory(
        title="Select Base Destination Folder for Dated Subfolders",
        parent=app_instance.root,
        mustexist=True
    )
    if not destination_base_folder: return

    abs_dest_base = os.path.abspath(destination_base_folder)
    abs_root = os.path.abspath(current_root_folder)
    if abs_dest_base.startswith(abs_root) and abs_dest_base != abs_root:
        messagebox.showerror("Error", "Base destination folder cannot be inside the current root folder (unless it's the root itself).", parent=app_instance.root)
        return
    if abs_dest_base == abs_root:
        if not messagebox.askyesno("Warning", "Destination is the same as the root folder. This will create dated subfolders within the root. Continue?", parent=app_instance.root):
            return

    dialog = tk.Toplevel(app_instance.root)
    dialog.title("Date Organization Options")
    dialog.transient(app_instance.root); dialog.grab_set()
    # ... (rest of dialog creation as in _organize_media_by_date_action) ...
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
            messagebox.showinfo("Info", "No media types selected for organization.", parent=app_instance.root)
            return

        media_types_str = []
        if include_images: media_types_str.append("images")
        if include_videos: media_types_str.append("videos")
        media_types_display = " and ".join(media_types_str)

        warning_message = (
            f"This will {action} ALL selected {media_types_display} from '{current_root_folder}' (and subfolders) "
            f"into dated subfolders (Year/Month) inside '{destination_base_folder}'.\n"
            f"Files may be renamed (e.g., DD-HHMMSS_OriginalName_seq.ext).\n"
            "This can be intensive. ARE YOU SURE?"
        )
        if not messagebox.askyesno("Confirm Date Organization", warning_message, icon='warning', parent=app_instance.root):
            return

        app_instance.status_label.config(text=f"{action.capitalize()}ing & organizing {media_types_display}...")
        app_instance.root.config(cursor="watch")
        app_instance.cancel_long_operation.clear()

        def status_update(text):
            if app_instance.root.winfo_exists():
                app_instance.root.after(0, lambda t=text: app_instance.status_label.config(text=t))

        thread = threading.Thread(
            target=organize_media_by_date_worker_thread_entry,
            args=(app_instance, current_root_folder, destination_base_folder, action, conflict_resolution,
                  include_images, include_videos, status_update),
            daemon=True
        )
        thread.start()

    button_frame = ttk.Frame(dialog)
    button_frame.pack(pady=10)
    ttk.Button(button_frame, text="Proceed", command=on_proceed).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    dialog.update_idletasks()
    x = app_instance.root.winfo_x() + (app_instance.root.winfo_width() - dialog.winfo_width()) // 2
    y = app_instance.root.winfo_y() + (app_instance.root.winfo_height() - dialog.winfo_height()) // 2
    dialog.geometry(f"+{x}+{y}")


def organize_media_by_date_worker_thread_entry(app_instance, root_dir, base_dest_dir, action, conflict_res, incl_img, incl_vid, status_cb):
    action_count, skipped_count, error_count, unknown_date_count, total_found = organize_media_by_date_core(
        root_dir, base_dest_dir, action, conflict_res, incl_img, incl_vid,
        app_instance.Image, app_instance.UnidentifiedImageError, # Pass Pillow modules/exceptions
        app_instance.cancel_long_operation, status_cb
    )

    if app_instance.root.winfo_exists():
        app_instance.root.after(0, lambda: app_instance.root.config(cursor=""))
        summary_message = (
            f"Date Organization Complete!\n\n"
            f"Successfully {action}d: {action_count}\n"
            f"Skipped: {skipped_count}\n"
            f"Media with unknown date (moved to 'Unknown_Date'): {unknown_date_count}\n"
            f"Errors: {error_count}\n"
            f"Total media files processed: {total_found}"
        )
        app_instance.root.after(0, lambda msg=summary_message: app_instance.status_label.config(text="Organization finished."))
        app_instance.root.after(0, lambda msg=summary_message: messagebox.showinfo("Organization Result", msg, parent=app_instance.root))

        if os.path.isdir(app_instance.current_folder.get()):
            app_instance.root.after(0, lambda: app_instance.load_items(app_instance.current_folder.get()))


def handle_delete_all_errored(app_instance):
    errored_paths = app_instance._get_errored_item_paths() # This method remains in app_instance
    if not errored_paths:
        messagebox.showinfo("Info", "No errored items found.", parent=app_instance.root)
        return
    if messagebox.askyesno("Confirm Delete Errored", f"Delete {len(errored_paths)} errored item(s)? (Undoable)", icon='warning', parent=app_instance.root):
        handle_delete_items(app_instance, items_to_delete_override=set(errored_paths))

def handle_move_all_errored(app_instance):
    errored_paths = app_instance._get_errored_item_paths() # This method remains in app_instance
    if not errored_paths:
        messagebox.showinfo("Info", "No errored items found.", parent=app_instance.root)
        return
    dest_folder = filedialog.askdirectory(title=f"Move {len(errored_paths)} errored item(s) to:", mustexist=True, parent=app_instance.root)
    if dest_folder and os.path.isdir(dest_folder):
        moved_count = 0
        for item_path in errored_paths:
            item_name = os.path.basename(item_path)
            dest_path = os.path.join(dest_folder, item_name)
            try:
                if os.path.exists(dest_path): continue # Simple skip if exists
                app_instance.root.config(cursor="watch"); app_instance.root.update_idletasks()
                shutil.move(item_path, dest_path)
                moved_count += 1
            except Exception as e:
                messagebox.showerror("Move Error", f"Could not move '{item_name}':\n{e}", parent=app_instance.root)
                break # Stop on first error for this operation
            finally:
                if app_instance.root.winfo_exists(): app_instance.root.config(cursor="")

        if moved_count > 0:
            messagebox.showinfo("Success", f"{moved_count} item(s) moved.", parent=app_instance.root)
            app_instance.load_items(app_instance.current_folder.get()) # Refresh
# New function for auto-deleting similar images
def handle_auto_delete_similar_half(app_instance):
    if not app_instance._similarity_scan_done_for_current_folder:
        messagebox.showinfo("Info", "Please run 'Find Similar Images' in the current folder first.", parent=app_instance.root)
        return

    if not app_instance.similar_image_groups:
        messagebox.showinfo("Info", "No similar image groups found in the current folder.", parent=app_instance.root)
        return

    num_groups = len(app_instance.similar_image_groups)
    paths_to_delete_overall = set()
    num_potentially_deleted = 0

    for group_paths_set in app_instance.similar_image_groups:
        if len(group_paths_set) < 2: # Should not happen if groups are defined as > 1
            continue

        # Sort paths for consistent selection (e.g., alphabetically by full path)
        sorted_group_paths = sorted(list(group_paths_set))

        num_in_group = len(sorted_group_paths)
        num_to_keep = math.ceil(num_in_group / 2.0) # Keep roughly half, biased towards keeping more if odd

        # Identify paths to delete (the latter part of the sorted list)
        # Convert num_to_keep to int for slicing
        paths_to_delete_from_this_group = sorted_group_paths[int(num_to_keep):]

        for path_to_del in paths_to_delete_from_this_group:
            paths_to_delete_overall.add(path_to_del)
            num_potentially_deleted += 1

    if not paths_to_delete_overall:
        messagebox.showinfo("Info", "No images identified for automatic deletion. This might mean all groups would keep at least one image, or groups are too small.", parent=app_instance.root)
        return

    confirmation_message = (
        f"This will attempt to delete {num_potentially_deleted} image(s) from {num_groups} similar group(s).\n"
        f"From each group, images will be deleted to keep approximately half (specifically, keeping the first N/2 after sorting by name).\n"
        "This action is undoable via the Edit > Undo menu.\n\n"
        "ARE YOU SURE you want to proceed?"
    )

    if not messagebox.askyesno("Confirm Auto-Delete Similar Images", confirmation_message, icon='warning', parent=app_instance.root):
        return

    app_instance.root.config(cursor="watch")
    app_instance.status_label.config(text="Auto-deleting similar images...")
    app_instance.root.update_idletasks()

    # Use the modified handle_delete_items which now returns a count
    deleted_count = handle_delete_items(app_instance, items_to_delete_override=paths_to_delete_overall)

    app_instance.root.config(cursor="")
    app_instance.status_label.config(text="Auto-deletion complete.")

    if deleted_count > 0:
        messagebox.showinfo("Auto-Delete Complete", f"{deleted_count} image(s) were moved to trash.", parent=app_instance.root)

        new_similar_groups = []
        new_marked_similar_paths = set()
        for group in app_instance.similar_image_groups:
            updated_group_paths = group.copy()
            updated_group_paths.difference_update(paths_to_delete_overall)
            if len(updated_group_paths) > 1:
                new_similar_groups.append(updated_group_paths)
                new_marked_similar_paths.update(updated_group_paths)
        app_instance.similar_image_groups = new_similar_groups
        app_instance.marked_similar_paths = new_marked_similar_paths

        if app_instance.show_only_similar_var.get():
            app_instance.apply_all_filters_and_refresh()
        else:
            app_instance._refresh_all_item_visuals()
    elif deleted_count == 0 and num_potentially_deleted > 0:
        messagebox.showwarning("Auto-Delete Info", "No images were actually deleted. They might have already been removed or an error occurred during deletion.", parent=app_instance.root)

    app_instance.update_ui_state()