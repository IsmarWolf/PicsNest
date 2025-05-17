# app_manager_utils/ui_creator.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sys

from constants import (
    PREVIEW_CONTAINER_SIZE, GRID_COLUMNS,
    FOLDER_COLOR, PLACEHOLDER_COLOR, FILE_COLOR, SELECTED_COLOR, ERROR_COLOR, SIMILAR_COLOR
)

def create_menu(app_instance):
    menubar = tk.Menu(app_instance.root)
    app_instance.root.config(menu=menubar)

    file_menu = tk.Menu(menubar, tearoff=0)
    menubar.add_cascade(label="File", menu=file_menu)
    file_menu.add_command(label="Select Root Folder...", command=app_instance.select_root_folder)
    file_menu.add_separator()
    file_menu.add_command(label="Exit", command=app_instance.on_closing)

    app_instance.edit_menu = tk.Menu(menubar, tearoff=0)
    menubar.add_cascade(label="Edit", menu=app_instance.edit_menu)
    app_instance.edit_menu.add_command(label="Undo", command=app_instance._undo_last_action, state=tk.DISABLED)

    app_instance.view_menu = tk.Menu(menubar, tearoff=0)
    menubar.add_cascade(label="View", menu=app_instance.view_menu)
    app_instance.view_menu.add_checkbutton(label="Show Images", variable=app_instance.show_images_var, command=app_instance.apply_all_filters_and_refresh)
    app_instance.view_menu.add_checkbutton(label="Show Videos", variable=app_instance.show_videos_var, command=app_instance.apply_all_filters_and_refresh)
    app_instance.view_menu.add_separator()
    app_instance.view_menu.add_checkbutton(label="Show Only Similar Images", variable=app_instance.show_only_similar_var, command=app_instance.handle_show_similar_toggle)

    tools_menu = tk.Menu(menubar, tearoff=0)
    menubar.add_cascade(label="Tools", menu=tools_menu)
    tools_menu.add_command(label="Find Similar Images in Current Folder", command=app_instance._find_similar_images_action_entry)
    tools_menu.add_command(label="Consolidate Media from Root...", command=app_instance._consolidate_media_action_entry)
    tools_menu.add_command(label="Organize Media by Date from Root...", command=app_instance._organize_media_by_date_action_entry)
    tools_menu.add_separator()
    tools_menu.add_command(label="Auto-Delete Redundant Similar (Keep ~Half per Group)", command=app_instance._auto_delete_similar_half_action_entry)
    tools_menu.add_command(label="Delete All Errored Items...", command=app_instance._delete_all_errored_action_entry)
    tools_menu.add_command(label="Move All Errored Items To...", command=app_instance._move_all_errored_action_entry)


def create_top_bar(app_instance):
    top_frame = ttk.Frame(app_instance.root, padding="5")
    top_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
    
    app_instance.up_button = ttk.Button(top_frame, text="Up", command=app_instance.navigate_up, state=tk.DISABLED)
    app_instance.up_button.pack(side=tk.LEFT, padx=(0, 5))
    
    folder_label = ttk.Label(top_frame, textvariable=app_instance.current_folder, relief="sunken", padding="2")
    folder_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    app_instance.status_label = ttk.Label(top_frame, text="", width=35) 
    app_instance.status_label.pack(side=tk.LEFT, padx=10)

def create_main_content_area(app_instance):
    content_frame = ttk.Frame(app_instance.root, padding=(5, 0, 0, 0))
    content_frame.grid(row=1, column=0, sticky="nsew")
    content_frame.grid_rowconfigure(0, weight=1)
    content_frame.grid_columnconfigure(0, weight=1)
    app_instance.canvas = tk.Canvas(content_frame, borderwidth=0, background="#ffffff")
    app_instance.item_frame = ttk.Frame(app_instance.canvas, padding="5", style="View.TFrame")
    app_instance.canvas.create_window((0, 0), window=app_instance.item_frame, anchor="nw", tags="self.item_frame")
    vsb = ttk.Scrollbar(content_frame, orient="vertical", command=app_instance.canvas.yview)
    hsb = ttk.Scrollbar(content_frame, orient="horizontal", command=app_instance.canvas.xview)
    app_instance.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    app_instance.canvas.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    app_instance.item_frame.bind("<Configure>", app_instance.on_frame_configure)
    if sys.platform == "win32" or sys.platform == "darwin":
            app_instance.canvas.bind_all("<MouseWheel>", app_instance._on_mousewheel)
    else:
            app_instance.canvas.bind_all("<Button-4>", lambda e: app_instance._on_mousewheel(e, direction=-1))
            app_instance.canvas.bind_all("<Button-5>", lambda e: app_instance._on_mousewheel(e, direction=1))
    
    app_instance.canvas.bind("<ButtonPress-1>", app_instance._on_canvas_press_for_rubber_band)
    app_instance.canvas.bind("<B1-Motion>", app_instance._on_canvas_motion_for_rubber_band)
    app_instance.canvas.bind("<ButtonRelease-1>", app_instance._on_canvas_release_for_rubber_band)

def create_preview_area(app_instance): 
    preview_area_lf = ttk.LabelFrame(app_instance.root, text="Preview & Info", padding="10")
    preview_area_lf.grid(row=1, column=1, sticky="nsew", padx=(5, 5), pady=(0, 5))
    preview_area_lf.grid_columnconfigure(0, weight=1)
    preview_area_lf.grid_rowconfigure(0, weight=3) 
    preview_area_lf.grid_rowconfigure(1, weight=1)  

    app_instance.preview_image_container = ttk.Frame(preview_area_lf, 
                                                width=PREVIEW_CONTAINER_SIZE[0], 
                                                height=PREVIEW_CONTAINER_SIZE[1])
    app_instance.preview_image_container.grid_propagate(False) 
    app_instance.preview_image_container.grid(row=0, column=0, sticky="nsew", pady=(0,10))
    
    app_instance.preview_label = ttk.Label(app_instance.preview_image_container, text="Select an item", anchor="center", background="lightgrey")
    app_instance.preview_label.pack(expand=True, fill=tk.BOTH) 
    # app_instance.preview_image_obj = None # This was deprecated for preview_label.image_ref

    info_subframe = ttk.Frame(preview_area_lf)
    info_subframe.grid(row=1, column=0, sticky="nsew", pady=(10,0))
    app_instance.info_name_label = ttk.Label(info_subframe, text="Name: -", wraplength=PREVIEW_CONTAINER_SIZE[0] - 20)
    app_instance.info_name_label.pack(anchor="w", pady=1)
    app_instance.info_size_label = ttk.Label(info_subframe, text="Size: -")
    app_instance.info_size_label.pack(anchor="w", pady=1)
    app_instance.info_type_label = ttk.Label(info_subframe, text="Type: -")
    app_instance.info_type_label.pack(anchor="w", pady=1)

def create_action_bar(app_instance):
    action_frame = ttk.Frame(app_instance.root, padding="5")
    action_frame.grid(row=2, column=0, columnspan=2, sticky="ew")
    app_instance.open_button = ttk.Button(action_frame, text="Open/View", command=app_instance.open_selected_item_action, state=tk.DISABLED)
    app_instance.open_button.pack(side=tk.LEFT, padx=5)
    app_instance.delete_button = ttk.Button(action_frame, text="Delete Selected", command=app_instance.delete_selected_items_action_entry, state=tk.DISABLED)
    app_instance.delete_button.pack(side=tk.LEFT, padx=5)
    app_instance.undo_button = ttk.Button(action_frame, text="Undo", command=app_instance._undo_last_action, state=tk.DISABLED)
    app_instance.undo_button.pack(side=tk.LEFT, padx=5)

def apply_app_styles():
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