# constants.py

import os

# --- File Extensions ---
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp')
VIDEO_EXTENSIONS = ('.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv')

# --- UI Sizes ---
GRID_THUMBNAIL_SIZE = (120, 120)
PREVIEW_THUMBNAIL_SIZE = (350, 350)
PREVIEW_CONTAINER_SIZE = (350, 350) # Maintained for preview area sizing
GRID_COLUMNS = 5

# --- Performance & Limits ---
LAZY_LOAD_BATCH_SIZE = 20
UNDO_STACK_MAX_SIZE = 10

# --- PicsNest Theme Colors ---
PICSNEST_BG_DARK = "#2C3E50"        # Dark Slate Grey (Primary Background)
PICSNEST_BG_MEDIUM = "#34495E"      # Wet Asphalt (Slightly Lighter Backgrounds, e.g., item frames)
PICSNEST_BG_LIGHT = "#4A6572"       # Lighter shade for UI elements or hover
PICSNEST_TEXT_LIGHT = "#ECF0F1"     # Clouds (Primary Text Color on Dark BG)
PICSNEST_TEXT_DARK = "#2C3E50"      # For text on light backgrounds (less used in dark theme)
PICSNEST_ACCENT_BLUE = "#3498DB"    # Peter River Blue (Primary Accent, Selection)
PICSNEST_ACCENT_GREEN = "#2ECC71"   # Emerald Green (Success, Open actions)
PICSNEST_ACCENT_YELLOW = "#F1C40F"  # Sun Flower (Similarity, Warnings)
PICSNEST_ACCENT_RED = "#E74C3C"      # Alizarin Red (Errors, Delete actions)

PICSNEST_BORDER_LIGHT = "#5D737E"   # For subtle borders on dark elements

# Specific UI element colors based on the theme
PICSNEST_SELECTED_BG = PICSNEST_ACCENT_BLUE
PICSNEST_SIMILAR_BG = PICSNEST_ACCENT_YELLOW # Consider border or subtle BG
PICSNEST_ERROR_BG = PICSNEST_ACCENT_RED
PICSNEST_FOLDER_REPRESENTATION_BG = PICSNEST_BG_MEDIUM # For folder item frames
PICSNEST_ITEM_PLACEHOLDER_BG = PICSNEST_BG_MEDIUM
PICSNEST_ITEM_LOADED_BG = PICSNEST_BG_MEDIUM

PICSNEST_VIEWER_BG = "#1E2B33" # Even darker for immersive viewing

# --- Icons (Unicode) ---
PICSNEST_FOLDER_ICON = "📁"  # U+1F4C1
PICSNEST_VIDEO_ICON = "🎞️"  # U+1F39E (Film Frames) or 🎬 U+1F3AC (Clapper Board)
PICSNEST_IMAGE_ICON = "🖼️"  # U+1F5BC (Frame with Picture)
PICSNEST_ERROR_ICON_GRID = "⚠️" # U+26A0
PICSNEST_LOADING_TEXT_GRID = "⏳" # U+23F3 or "..."

# --- Old Colors (to be phased out or re-evaluated if still used by non-ttk components) ---
IMAGE_VIEWER_BG = PICSNEST_VIEWER_BG # Updated
# --- Configuration Paths & Names ---
FOLDER_THUMB_DB_FILENAME = "folder_thumbs.json"
TRASH_DIR_NAME = ".app_trash_v3"

# --- Trash Settings ---
TRASH_MAX_ITEMS = 3