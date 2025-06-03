
# app_manager_utils/__init__.py
# This file can be empty. It makes 'app_manager_utils' a Python package.
# app_manager_utils/file_operations.py
import os
import shutil
from datetime import datetime
import threading # Only for type hinting if needed, actual threading is in app_manager
# import imagehash # For type hinting if needed; imagehash_module is passed

# PIL and OpenCV are passed as arguments to avoid circular dependencies or import issues if not installed
# from PIL import Image, UnidentifiedImageError
# import cv2

from constants import (
    IMAGE_EXTENSIONS, VIDEO_EXTENSIONS,
    SCREENSHOT_FILENAME_PATTERNS, DOWNLOADED_FILENAME_PATTERNS,
    EXIF_SOFTWARE_TAGS_PATTERNS
)


def generate_single_thumbnail(item_data, grid_thumbnail_size,
                              PillowImage, PillowUnidentifiedImageError, cv2_module):
    """
    Generates a thumbnail for a single image or video file.
    item_data: dict {'path': str, 'name': str, 'type': str}
    Returns: (PIL.Image object or None, error_flag_boolean)
    """
    thumb_image, error_flag = None, False
    try:
        if item_data['type'] == 'file':
            _, ext = os.path.splitext(item_data['name'])
            ext_lower = ext.lower()

            if ext_lower in IMAGE_EXTENSIONS: # Uses imported constant
                img = PillowImage.open(item_data['path'])
                try:
                    exif = img.getexif()
                    orientation_tag = 274
                    if orientation_tag in exif:
                        orientation = exif[orientation_tag]
                        if orientation == 3: img = img.rotate(180, expand=True)
                        elif orientation == 6: img = img.rotate(-90, expand=True)
                        elif orientation == 8: img = img.rotate(90, expand=True)
                except Exception: pass # Ignore EXIF errors

                img.thumbnail(grid_thumbnail_size, PillowImage.Resampling.LANCZOS)
                if img.mode not in ('RGB', 'RGBA'): img = img.convert('RGB')
                thumb_image = img

            elif ext_lower in VIDEO_EXTENSIONS and cv2_module: # Uses imported constant
                cap = None
                try:
                    cap = cv2_module.VideoCapture(item_data['path'])
                    if cap.isOpened():
                        frame_count = int(cap.get(cv2_module.CAP_PROP_FRAME_COUNT))
                        frame_no = min(frame_count // 10, 100) if frame_count > 10 else 0
                        cap.set(cv2_module.CAP_PROP_POS_FRAMES, frame_no)
                        ret, frame = cap.read()
                        if ret:
                            frame_rgb = cv2_module.cvtColor(frame, cv2_module.COLOR_BGR2RGB)
                            img = PillowImage.fromarray(frame_rgb)
                            img.thumbnail(grid_thumbnail_size, PillowImage.Resampling.LANCZOS)
                            thumb_image = img
                except Exception as e_vid:
                    print(f"Video thumbnail error for {item_data['path']}: {e_vid}")
                    error_flag = True
                finally:
                    if cap: cap.release()

    except PillowUnidentifiedImageError:
        error_flag = True
    except Exception as e:
        print(f"Thumbnail generation error for {item_data['path']}: {e}")
        error_flag = True

    return thumb_image, error_flag


def get_media_creation_date(file_path, PillowImage, PillowUnidentifiedImageError):
    """
    Tries to get the creation date from EXIF for images, otherwise filesystem mtime.
    """
    ext_lower = os.path.splitext(file_path)[1].lower()
    date_to_use = None

    if ext_lower in IMAGE_EXTENSIONS: # Uses imported constant
        try:
            img = PillowImage.open(file_path)
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
                            pass # print(f"Could not parse EXIF date string '{date_str_cleaned}' for {file_path}")
        except PillowUnidentifiedImageError:
            pass # print(f"Cannot identify image file (for date): {file_path}")
        except Exception:
            pass

    if date_to_use is None:
        try:
            mtime_timestamp = os.path.getmtime(file_path)
            date_to_use = datetime.fromtimestamp(mtime_timestamp)
        except OSError as e:
            print(f"Could not get file system date for {file_path}: {e}")

    return date_to_use


def find_similar_images_core(image_items_to_process, similarity_threshold,
                             PillowImage, imagehash_module, # Pass the module itself
                             cancel_event, status_callback_fn):
    if imagehash_module is None: # Check passed module
        status_callback_fn("ImageHash library not available.")
        return [], {}, set()

    image_hashes_cache = {}
    item_hashes = []
    total_images = len(image_items_to_process)

    for i, item_data in enumerate(image_items_to_process):
        if cancel_event.is_set():
            status_callback_fn("Similarity scan cancelled (hashing).")
            return [], image_hashes_cache, set()

        path = item_data['path']
        if (i % 10 == 0) or (i == total_images - 1):
            status_callback_fn(f"Hashing {i+1}/{total_images}")

        try:
            img = PillowImage.open(path)
            img_hash = imagehash_module.dhash(img) # Use the passed module
            image_hashes_cache[path] = img_hash
            item_hashes.append((path, img_hash))
        except Exception as e:
            print(f"Could not hash {path}: {e}")

    parent = {path: path for path, _ in item_hashes}
    def find_set(item_path):
        if parent[item_path] == item_path: return item_path
        parent[item_path] = find_set(parent[item_path])
        return parent[item_path]

    def unite_sets(path1, path2):
        path1_root = find_set(path1)
        path2_root = find_set(path2)
        if path1_root != path2_root:
            parent[path2_root] = path1_root

    num_item_hashes = len(item_hashes)
    for i in range(num_item_hashes):
        if cancel_event.is_set():
            status_callback_fn("Similarity scan cancelled (comparing).")
            return [], image_hashes_cache, set()

        if (i % 10 == 0) or (i == num_item_hashes -1) :
             status_callback_fn(f"Comparing {i+1}/{num_item_hashes}")

        path1, hash1 = item_hashes[i]
        for j in range(i + 1, num_item_hashes):
            path2, hash2 = item_hashes[j]
            if (hash1 - hash2) <= similarity_threshold:
                unite_sets(path1, path2)

    groups_map = {}
    for path, _ in item_hashes:
        root_path = find_set(path)
        groups_map.setdefault(root_path, set()).add(path)

    similar_image_groups = [group for group in groups_map.values() if len(group) > 1]

    marked_similar_paths = set()
    for group in similar_image_groups:
        marked_similar_paths.update(group)

    return similar_image_groups, image_hashes_cache, marked_similar_paths


def consolidate_media_core(root_dir, dest_dir, action_type, conflict_resolution,
                           include_images, include_videos,
                           cancel_event, progress_callback_fn):
    action_count = 0
    skipped_count = 0
    error_count = 0

    found_media = []
    for dirpath, _, filenames in os.walk(root_dir):
        if os.path.commonpath([dirpath, dest_dir]) == os.path.abspath(dest_dir) and \
           os.path.abspath(dirpath) != os.path.abspath(dest_dir):
            continue
        for filename in filenames:
            ext_lower = os.path.splitext(filename)[1].lower()
            is_image = ext_lower in IMAGE_EXTENSIONS # Uses imported constant
            is_video = ext_lower in VIDEO_EXTENSIONS # Uses imported constant

            if (include_images and is_image) or (include_videos and is_video):
                found_media.append(os.path.join(dirpath, filename))

    total_media_to_process = len(found_media)
    if total_media_to_process == 0:
        progress_callback_fn(f"No media found to {action_type}.")
        return 0, 0, 0, total_media_to_process

    for idx, src_path in enumerate(found_media):
        if cancel_event.is_set():
            progress_callback_fn(f"Consolidation cancelled ({idx}/{total_media_to_process}).")
            break

        progress_callback_fn(f"{action_type.capitalize()}ing: {idx+1}/{total_media_to_process}")

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
                try:
                    if os.path.isdir(current_dest_path): shutil.rmtree(current_dest_path)
                    else: os.remove(current_dest_path)
                except Exception as e_del:
                    print(f"Error overwriting {current_dest_path}: {e_del}")
                    error_count += 1
                    continue
            elif conflict_resolution == "rename":
                base, ext = os.path.splitext(filename)
                count = 1
                while os.path.exists(current_dest_path):
                    current_dest_path = os.path.join(dest_dir, f"{base} ({count}){ext}")
                    count += 1

        try:
            os.makedirs(os.path.dirname(current_dest_path), exist_ok=True)
            if action_type == "move":
                shutil.move(src_path, current_dest_path)
            elif action_type == "copy":
                shutil.copy2(src_path, current_dest_path)
            action_count += 1
        except Exception as e:
            print(f"Error {action_type}ing {src_path} to {current_dest_path}: {e}")
            error_count += 1

    return action_count, skipped_count, error_count, total_media_to_process

def organize_media_by_date_core(root_dir, base_dest_dir, action_type, conflict_resolution,
                                include_images, include_videos, PillowImage, PillowUnidentifiedImageError,
                                cancel_event, progress_callback_fn):
    action_count = 0
    skipped_count = 0
    error_count = 0
    unknown_date_count = 0

    found_media = []
    for dirpath, _, filenames in os.walk(root_dir):
        if os.path.commonpath([dirpath, base_dest_dir]) == os.path.abspath(base_dest_dir) and \
           os.path.abspath(dirpath) != os.path.abspath(base_dest_dir):
            continue
        for filename in filenames:
            ext_lower = os.path.splitext(filename)[1].lower()
            is_image = ext_lower in IMAGE_EXTENSIONS # Uses imported constant
            is_video = ext_lower in VIDEO_EXTENSIONS # Uses imported constant
            if (include_images and is_image) or (include_videos and is_video):
                found_media.append(os.path.join(dirpath, filename))

    total_media_to_process = len(found_media)
    if total_media_to_process == 0:
        progress_callback_fn("No media found to organize.")
        return 0,0,0,0, total_media_to_process

    for idx, src_path in enumerate(found_media):
        if cancel_event.is_set():
            progress_callback_fn(f"Organization cancelled ({idx}/{total_media_to_process}).")
            break

        progress_callback_fn(f"Organizing: {idx+1}/{total_media_to_process}")

        media_date_dt = get_media_creation_date(src_path, PillowImage, PillowUnidentifiedImageError)

        target_subfolder_path = ""
        new_filename_base = ""
        original_filename_base, original_ext = os.path.splitext(os.path.basename(src_path))

        if not media_date_dt:
            unknown_date_count += 1
            target_subfolder_path = os.path.join(base_dest_dir, "Unknown_Date")
            new_filename_base = original_filename_base
        else:
            year_str = media_date_dt.strftime("%Y")
            month_str = media_date_dt.strftime("%m")
            day_str = media_date_dt.strftime("%d")
            time_str = media_date_dt.strftime("%H%M%S")

            target_subfolder_path = os.path.join(base_dest_dir, year_str, month_str)

            safe_original_name = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in original_filename_base)
            safe_original_name = safe_original_name[:30]
            new_filename_base = f"{day_str}-{time_str}_{safe_original_name}"

        os.makedirs(target_subfolder_path, exist_ok=True)

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
                temp_dest_path = dest_path # Store original attempt
                while os.path.exists(temp_dest_path): # Check existence of modified path
                    temp_dest_path = os.path.join(target_subfolder_path, f"{new_filename_base}_{seq_count}{original_ext}")
                    seq_count += 1
                dest_path = temp_dest_path # Assign the non-conflicting path

        try:
            if action_type == "move":
                shutil.move(src_path, dest_path)
            elif action_type == "copy":
                shutil.copy2(src_path, dest_path)
            action_count += 1
        except Exception as e:
            print(f"Error {action_type}ing {src_path} to {dest_path}: {e}")
            error_count += 1

    return action_count, skipped_count, error_count, unknown_date_count, total_media_to_process


def is_likely_screenshot_or_downloaded(file_path, PillowImage, PillowUnidentifiedImageError):
    """
    Heuristically determines if an image is a screenshot or downloaded.
    Returns: 'screenshot', 'downloaded', or None
    """
    filename_lower = os.path.basename(file_path).lower()

    # Check filename patterns for screenshots
    for pattern in SCREENSHOT_FILENAME_PATTERNS:
        if pattern in filename_lower:
            return 'screenshot'

    # Check filename patterns for downloads (less reliable)
    # We will check this again later if EXIF doesn't give a clue
    filename_suggests_download = False
    for pattern in DOWNLOADED_FILENAME_PATTERNS:
        if pattern in filename_lower:
            filename_suggests_download = True
            break


    # Check EXIF data
    ext_lower = os.path.splitext(file_path)[1].lower()
    if ext_lower in IMAGE_EXTENSIONS:
        try:
            img = PillowImage.open(file_path)
            exif_data = img._getexif() # Use the public method if available, otherwise fallback
            if exif_data is None: # Some images might not have EXIF or it's not parsable by _getexif
                exif_data = {} # Ensure it's an empty dict for safe .get()

            # Check Software tag (305)
            software_tag_value = str(exif_data.get(305, "")).lower() # Ensure string for .lower()
            for pattern in EXIF_SOFTWARE_TAGS_PATTERNS.get("screenshot", []):
                if pattern in software_tag_value:
                    return 'screenshot'
            for pattern in EXIF_SOFTWARE_TAGS_PATTERNS.get("downloaded", []):
                if pattern in software_tag_value:
                    return 'downloaded'

            # Check UserComment (37510) or ImageDescription (270)
            desc_tag_value = str(exif_data.get(270, "")).lower()
            if "screenshot" in desc_tag_value:
                return 'screenshot'

            user_comment_value = str(exif_data.get(37510, "")).lower()
            # Example: Some systems might put "screenshot" in user comments
            if "screenshot" in user_comment_value:
                return 'screenshot'

        except PillowUnidentifiedImageError:
            pass # Cannot read image, rely on filename
        except AttributeError: # Handles cases where _getexif might not be available or returns None
            pass
        except Exception: # Other EXIF errors
            pass

    # If filename matched "downloaded" earlier and EXIF didn't override, return "downloaded"
    if filename_suggests_download:
        return 'downloaded'

    return None


def separate_files_core(root_dir, dest_dir_screenshots, dest_dir_videos, action_type, conflict_resolution,
                        separate_screenshots, separate_videos,
                        PillowImage, PillowUnidentifiedImageError, # For screenshot detection
                        cancel_event, progress_callback_fn):
    action_count_screenshots = 0
    action_count_videos = 0
    skipped_count = 0
    error_count = 0

    found_media = []
    for dirpath, _, filenames in os.walk(root_dir):
        abs_dirpath = os.path.abspath(dirpath)
        if separate_screenshots and dest_dir_screenshots and \
           os.path.commonpath([abs_dirpath, os.path.abspath(dest_dir_screenshots)]) == os.path.abspath(dest_dir_screenshots) and \
           abs_dirpath != os.path.abspath(dest_dir_screenshots): # Exclude the target screenshot dir itself
            continue
        if separate_videos and dest_dir_videos and \
           os.path.commonpath([abs_dirpath, os.path.abspath(dest_dir_videos)]) == os.path.abspath(dest_dir_videos) and \
           abs_dirpath != os.path.abspath(dest_dir_videos): # Exclude the target video dir itself
            continue

        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            ext_lower = os.path.splitext(filename)[1].lower()
            is_image = ext_lower in IMAGE_EXTENSIONS
            is_video = ext_lower in VIDEO_EXTENSIONS

            if (separate_screenshots and is_image) or (separate_videos and is_video):
                found_media.append(full_path)

    total_media_to_process = len(found_media)
    if total_media_to_process == 0:
        progress_callback_fn("No relevant media found to separate.")
        return 0, 0, 0, 0, total_media_to_process

    for idx, src_path in enumerate(found_media):
        if cancel_event.is_set():
            progress_callback_fn(f"Separation cancelled ({idx}/{total_media_to_process}).")
            break

        progress_callback_fn(f"Processing for separation: {idx+1}/{total_media_to_process}")

        filename = os.path.basename(src_path)
        ext_lower = os.path.splitext(filename)[1].lower()
        current_dest_dir = None
        is_target_type = False

        if separate_videos and ext_lower in VIDEO_EXTENSIONS:
            current_dest_dir = dest_dir_videos
            is_target_type = True
        elif separate_screenshots and ext_lower in IMAGE_EXTENSIONS:
            source_type = is_likely_screenshot_or_downloaded(src_path, PillowImage, PillowUnidentifiedImageError)
            if source_type == 'screenshot':
                current_dest_dir = dest_dir_screenshots
                is_target_type = True

        if not is_target_type or not current_dest_dir:
            continue

        if os.path.dirname(os.path.abspath(src_path)) == os.path.abspath(current_dest_dir):
            skipped_count += 1
            continue

        current_dest_path = os.path.join(current_dest_dir, filename)

        if os.path.abspath(src_path) == os.path.abspath(current_dest_path):
            skipped_count +=1
            continue

        if os.path.exists(current_dest_path):
            if conflict_resolution == "skip":
                skipped_count += 1
                continue
            elif conflict_resolution == "overwrite":
                try:
                    if os.path.isdir(current_dest_path): shutil.rmtree(current_dest_path)
                    else: os.remove(current_dest_path)
                except Exception as e_del:
                    print(f"Error overwriting {current_dest_path}: {e_del}")
                    error_count += 1
                    continue
            elif conflict_resolution == "rename":
                base, ext = os.path.splitext(filename)
                count = 1
                while os.path.exists(current_dest_path):
                    current_dest_path = os.path.join(current_dest_dir, f"{base} ({count}){ext}")
                    count += 1

        try:
            os.makedirs(os.path.dirname(current_dest_path), exist_ok=True)
            if action_type == "move":
                shutil.move(src_path, current_dest_path)
            elif action_type == "copy":
                shutil.copy2(src_path, current_dest_path)

            if current_dest_dir == dest_dir_screenshots:
                action_count_screenshots += 1
            elif current_dest_dir == dest_dir_videos:
                action_count_videos += 1

        except Exception as e:
            print(f"Error {action_type}ing {src_path} to {current_dest_path}: {e}")
            error_count += 1

    return action_count_screenshots, action_count_videos, skipped_count, error_count, total_media_to_process
