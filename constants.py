# constants.py

import os

# --- File Extensions ---
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp')
VIDEO_EXTENSIONS = ('.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv')

# --- UI Sizes ---
GRID_THUMBNAIL_SIZE = (120, 120)
PREVIEW_THUMBNAIL_SIZE = (350, 350)
PREVIEW_CONTAINER_SIZE = (350, 350)
GRID_COLUMNS = 5

# --- Performance & Limits ---
LAZY_LOAD_BATCH_SIZE = 20
UNDO_STACK_MAX_SIZE = 10

# --- PicsNest Theme Colors ---
PICSNEST_BG_DARK = "#2C3E50"
PICSNEST_BG_MEDIUM = "#34495E"
PICSNEST_BG_LIGHT = "#4A6572"
PICSNEST_TEXT_LIGHT = "#ECF0F1"
PICSNEST_TEXT_DARK = "#2C3E50"
PICSNEST_ACCENT_BLUE = "#3498DB"         # Primary default accent blue
PICSNEST_USER_ACCENT_COLOR = None        # Will be loaded from settings and can override PICSNEST_ACCENT_BLUE logic
PICSNEST_ACCENT_GREEN = "#2ECC71"
PICSNEST_ACCENT_YELLOW = "#F1C40F"
PICSNEST_ACCENT_RED = "#E74C3C"

PICSNEST_BORDER_LIGHT = "#5D737E"

# Function to get the current accent color
def get_current_accent_color():
    return PICSNEST_USER_ACCENT_COLOR if PICSNEST_USER_ACCENT_COLOR else PICSNEST_ACCENT_BLUE

# Specific UI element colors based on the theme
# These will now use get_current_accent_color() where appropriate in ui_creator.py
PICSNEST_SELECTED_BG = None # Will be set by get_current_accent_color() in styles
PICSNEST_SIMILAR_BG = PICSNEST_ACCENT_YELLOW
PICSNEST_ERROR_BG = PICSNEST_ACCENT_RED
PICSNEST_FOLDER_REPRESENTATION_BG = PICSNEST_BG_MEDIUM
PICSNEST_ITEM_PLACEHOLDER_BG = PICSNEST_BG_MEDIUM
PICSNEST_ITEM_LOADED_BG = PICSNEST_BG_MEDIUM

PICSNEST_VIEWER_BG = "#1E2B33"

# --- Icons (Unicode) ---
PICSNEST_FOLDER_ICON = "📁"
PICSNEST_VIDEO_ICON = "🎞️"
PICSNEST_IMAGE_ICON = "🖼️"
PICSNEST_ERROR_ICON_GRID = "⚠️"
PICSNEST_LOADING_TEXT_GRID = "⏳"

IMAGE_VIEWER_BG = PICSNEST_VIEWER_BG
# --- Configuration Paths & Names ---
THEME_SETTINGS_FILENAME = "theme_settings.json"
FOLDER_THUMB_DB_FILENAME = "folder_thumbs.json"
TRASH_DIR_NAME = ".app_trash_v3" # Changed to v3 to avoid conflict if user had v2

# --- Trash Settings ---
TRASH_MAX_ITEMS = -1 # -1 signifies unlimited trash size. Still emptied on app close.

# --- Screenshot/Downloaded Identification ---
# Common filename patterns for screenshots
SCREENSHOT_FILENAME_PATTERNS = [
    "screenshot", "screen_shot", "screen-shot", "capture", "scrn", "vid_cap"
]
# Common filename patterns for downloaded files (less reliable, use with caution)
DOWNLOADED_FILENAME_PATTERNS = [
    "download", "dl", "item" # "item" is very generic, might need refinement
]

# EXIF tags that might indicate a screenshot or specific software
# UserComment (37510), ImageDescription (270), Software (305)
EXIF_SOFTWARE_TAGS_PATTERNS = {
    "screenshot": ["screenshot", "snipping tool", "greenshot", "lightshot", "flameshot", "shutter"],
    "downloaded": ["chrome", "firefox", "edge", "safari", "opera", "downloader"] # Very broad
}
