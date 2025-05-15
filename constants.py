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

# --- Colors & Styles ---
FOLDER_COLOR = "#F4D37B"
PLACEHOLDER_COLOR = "#EAEAEA"
FILE_COLOR = "#FFFFFF"
SELECTED_COLOR = "#ADD8E6"
ERROR_COLOR = "#FF9999"
SIMILAR_COLOR = "#FFD700"
LOADING_TEXT = "..."
IMAGE_VIEWER_BG = "black" 

# --- Configuration Paths & Names ---
FOLDER_THUMB_DB_FILENAME = "folder_thumbs.json"
TRASH_DIR_NAME = ".app_trash_v3"