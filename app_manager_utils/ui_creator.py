
# app_manager_utils/ui_creator.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sys
import os

from constants import (
    PICSNEST_ACCENT_BLUE, PREVIEW_CONTAINER_SIZE, GRID_COLUMNS,
    PICSNEST_BG_DARK, PICSNEST_BG_MEDIUM, PICSNEST_BG_LIGHT,
    PICSNEST_TEXT_LIGHT, PICSNEST_ACCENT_GREEN, PICSNEST_ACCENT_YELLOW, PICSNEST_ACCENT_RED,
    PICSNEST_BORDER_LIGHT, PICSNEST_FOLDER_REPRESENTATION_BG, PICSNEST_ITEM_PLACEHOLDER_BG,
    PICSNEST_ITEM_LOADED_BG, PICSNEST_SELECTED_BG, PICSNEST_SIMILAR_BG, PICSNEST_ERROR_BG,
    PICSNEST_VIEWER_BG, get_current_accent_color
)

def create_menu(app_instance):
    current_accent = get_current_accent_color()
    menubar = tk.Menu(app_instance.root,
                      bg=PICSNEST_BG_DARK, fg=PICSNEST_TEXT_LIGHT,
                      activebackground=current_accent, activeforeground=PICSNEST_TEXT_LIGHT,
                      bd=0)
    app_instance.root.config(menu=menubar)

    menu_options = {
        "tearoff": 0, "background": PICSNEST_BG_MEDIUM, "foreground": PICSNEST_TEXT_LIGHT,
        "activebackground": current_accent, "activeforeground": PICSNEST_TEXT_LIGHT,
        "relief": tk.FLAT, "borderwidth": 0
    }

    file_menu = tk.Menu(menubar, **menu_options)
    menubar.add_cascade(label="File", menu=file_menu)
    file_menu.add_command(label="Select Root Folder...", command=app_instance.select_root_folder)
    file_menu.add_separator(background=PICSNEST_BORDER_LIGHT)
    file_menu.add_command(label="Exit", command=app_instance.on_closing)

    app_instance.edit_menu = tk.Menu(menubar, **menu_options)
    menubar.add_cascade(label="Edit", menu=app_instance.edit_menu)
    app_instance.edit_menu.add_command(label="Undo", command=app_instance._undo_last_action, state=tk.DISABLED)
    app_instance.edit_menu.add_command(label="Rename Selected (F2)", command=app_instance.on_f2_key_press)

    app_instance.view_menu = tk.Menu(menubar, **menu_options)
    menubar.add_cascade(label="View", menu=app_instance.view_menu)
    app_instance.view_menu.add_checkbutton(label="Show Images", variable=app_instance.show_images_var, command=app_instance.apply_all_filters_and_refresh)
    app_instance.view_menu.add_checkbutton(label="Show Videos", variable=app_instance.show_videos_var, command=app_instance.apply_all_filters_and_refresh)
    app_instance.view_menu.add_separator(background=PICSNEST_BORDER_LIGHT)
    app_instance.view_menu.add_checkbutton(label="Show Only Similar Images", variable=app_instance.show_only_similar_var, command=app_instance.handle_show_similar_toggle)
    app_instance.view_menu.add_checkbutton(label="Show Only Screenshots/Downloads", variable=app_instance.show_only_screenshots_downloads_var, command=app_instance.apply_all_filters_and_refresh)


    tools_menu = tk.Menu(menubar, **menu_options)
    menubar.add_cascade(label="Tools", menu=tools_menu)
    tools_menu.add_command(label="Find Similar Images in Current Folder", command=app_instance._find_similar_images_action_entry)
    tools_menu.add_command(label="Consolidate Media from Root...", command=app_instance._consolidate_media_action_entry)
    tools_menu.add_command(label="Organize Media by Date from Root...", command=app_instance._organize_media_by_date_action_entry)
    tools_menu.add_command(label="Separate Screenshots/Videos from Root...", command=app_instance._separate_files_action_entry) # New Tool
    tools_menu.add_separator(background=PICSNEST_BORDER_LIGHT)
    tools_menu.add_command(label="Auto-Delete Redundant Similar (Keep ~Half)", command=app_instance._auto_delete_similar_half_action_entry)
    tools_menu.add_command(label="Delete All Errored Items...", command=app_instance._delete_all_errored_action_entry)
    tools_menu.add_command(label="Move All Errored Items To...", command=app_instance._move_all_errored_action_entry)

    settings_menu = tk.Menu(menubar, **menu_options)
    menubar.add_cascade(label="Settings", menu=settings_menu)
    settings_menu.add_command(label="Change Accent Color...", command=app_instance.change_accent_color_action)


def create_top_bar(app_instance):
    top_frame = ttk.Frame(app_instance.root, padding="5 5 5 5", style="PicsNest.Dark.TFrame")
    top_frame.grid(row=0, column=0, columnspan=2, sticky="ew")

    app_instance.up_button = ttk.Button(top_frame, text="⬆ Up", command=app_instance.navigate_up, state=tk.DISABLED, style="PicsNest.Tool.TButton")
    app_instance.up_button.pack(side=tk.LEFT, padx=(0, 10))

    folder_label = ttk.Label(top_frame, textvariable=app_instance.current_folder,
                             style="PicsNest.Path.TLabel", padding="5 2 5 2", relief=tk.FLAT, anchor=tk.W)
    folder_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    app_instance.status_label = ttk.Label(top_frame, text="", width=40, style="PicsNest.Status.TLabel", anchor=tk.E)
    app_instance.status_label.pack(side=tk.RIGHT, padx=10)

def create_main_content_area(app_instance):
    content_frame_parent = ttk.Frame(app_instance.root, style="PicsNest.Dark.TFrame")
    content_frame_parent.grid(row=1, column=0, sticky="nsew")
    content_frame_parent.grid_rowconfigure(0, weight=1)
    content_frame_parent.grid_columnconfigure(0, weight=1)

    app_instance.welcome_frame = ttk.Frame(content_frame_parent, style="PicsNest.Dark.TFrame", padding=20)
    app_instance.welcome_frame.grid(row=0, column=0, sticky="nsew")
    app_instance.welcome_frame.grid_columnconfigure(0, weight=1)
    app_instance.welcome_frame.grid_rowconfigure(0, weight=1)
    app_instance.welcome_frame.grid_rowconfigure(1, weight=0)
    app_instance.welcome_frame.grid_rowconfigure(2, weight=0)
    app_instance.welcome_frame.grid_rowconfigure(3, weight=1)

    welcome_label = ttk.Label(app_instance.welcome_frame, text="Welcome to PicsNest!",
                              style="PicsNest.LargeTitle.TLabel", anchor="center")
    welcome_label.grid(row=0, column=0, sticky="s", pady=(0,20))

    try:
        # Assumes logo is in the same directory as app_manager.py
        # For PyInstaller, you'd use resource_path() here.
        logo_base_dir = os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__)) # Project root where main.py is
        if getattr(sys, 'frozen', False): # If running as a PyInstaller bundle
             logo_base_dir = sys._MEIPASS

        logo_path_png_welcome = os.path.join(logo_base_dir, 'picsnest_logo_large.png')

        if os.path.exists(logo_path_png_welcome) and app_instance.ImageTk:
            pil_img = app_instance.Image.open(logo_path_png_welcome)
            pil_img.thumbnail((128, 128), app_instance.Image.Resampling.LANCZOS)
            app_instance.welcome_logo_img = app_instance.ImageTk.PhotoImage(pil_img)
            logo_label = ttk.Label(app_instance.welcome_frame, image=app_instance.welcome_logo_img, style="PicsNest.Dark.TLabel")
            logo_label.grid(row=1, column=0, pady=10)
        else:
            logo_label = ttk.Label(app_instance.welcome_frame, text="🖼️", style="PicsNest.HugeIcon.TLabel")
            logo_label.grid(row=1, column=0, pady=10)
            if not os.path.exists(logo_path_png_welcome):
                print(f"INFO: Welcome screen logo '{logo_path_png_welcome}' not found.")
    except Exception as e:
        print(f"Error loading welcome screen logo: {e}")
        logo_label = ttk.Label(app_instance.welcome_frame, text="PicsNest", style="PicsNest.LargeTitle.TLabel")
        logo_label.grid(row=1, column=0, pady=10)

    select_folder_button_welcome = ttk.Button(app_instance.welcome_frame, text="📂 Select Root Folder to Begin",
                                     command=app_instance.select_root_folder, style="PicsNest.Welcome.TButton")
    select_folder_button_welcome.grid(row=2, column=0, sticky="n", pady=20)

    app_instance.canvas_content_frame = ttk.Frame(content_frame_parent, padding=(0,0,0,0), style="PicsNest.Dark.TFrame")
    app_instance.canvas_content_frame.grid(row=0, column=0, sticky="nsew")
    app_instance.canvas_content_frame.grid_rowconfigure(0, weight=1)
    app_instance.canvas_content_frame.grid_columnconfigure(0, weight=1)

    app_instance.canvas = tk.Canvas(app_instance.canvas_content_frame, borderwidth=0, background=PICSNEST_BG_DARK, highlightthickness=0)
    app_instance.item_frame = ttk.Frame(app_instance.canvas, padding="10", style="PicsNest.Dark.TFrame")
    app_instance.canvas.create_window((0, 0), window=app_instance.item_frame, anchor="nw", tags="self.item_frame")

    app_instance.canvas_vsb = ttk.Scrollbar(app_instance.canvas_content_frame, orient="vertical", command=app_instance.canvas.yview, style="PicsNest.Vertical.TScrollbar")
    app_instance.canvas_hsb = ttk.Scrollbar(app_instance.canvas_content_frame, orient="horizontal", command=app_instance.canvas.xview, style="PicsNest.Horizontal.TScrollbar")
    app_instance.canvas.configure(yscrollcommand=app_instance.canvas_vsb.set, xscrollcommand=app_instance.canvas_hsb.set)

    app_instance.canvas.grid(row=0, column=0, sticky="nsew")
    app_instance.canvas_vsb.grid(row=0, column=1, sticky="ns")
    app_instance.canvas_hsb.grid(row=1, column=0, sticky="ew")

    app_instance.item_frame.bind("<Configure>", app_instance.on_frame_configure)

    app_instance.canvas.bind("<ButtonPress-1>", app_instance._on_canvas_press_for_rubber_band)
    app_instance.canvas.bind("<B1-Motion>", app_instance._on_canvas_motion_for_rubber_band)
    app_instance.canvas.bind("<ButtonRelease-1>", app_instance._on_canvas_release_for_rubber_band)

    app_instance.canvas_content_frame.grid_remove()


def create_preview_area(app_instance):
    preview_area_lf = ttk.LabelFrame(app_instance.root, text="Preview & Info", padding="10", style="PicsNest.Preview.TLabelframe")
    preview_area_lf.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=(0, 10))
    preview_area_lf.grid_columnconfigure(0, weight=1)
    preview_area_lf.grid_rowconfigure(0, weight=3)
    preview_area_lf.grid_rowconfigure(1, weight=1)

    app_instance.preview_image_container = ttk.Frame(preview_area_lf,
                                                width=PREVIEW_CONTAINER_SIZE[0],
                                                height=PREVIEW_CONTAINER_SIZE[1],
                                                style="PicsNest.PreviewContainer.TFrame")
    app_instance.preview_image_container.grid_propagate(False)
    app_instance.preview_image_container.grid(row=0, column=0, sticky="nsew", pady=(0,10))

    app_instance.preview_label = ttk.Label(app_instance.preview_image_container, text="Select an item",
                                          anchor="center", style="PicsNest.PreviewPlaceholder.TLabel")
    app_instance.preview_label.pack(expand=True, fill=tk.BOTH)

    info_subframe = ttk.Frame(preview_area_lf, style="PicsNest.Dark.TFrame")
    info_subframe.grid(row=1, column=0, sticky="nsew", pady=(10,0))

    info_label_style = "PicsNest.Info.TLabel"
    app_instance.info_name_label = ttk.Label(info_subframe, text="Name: -", wraplength=PREVIEW_CONTAINER_SIZE[0] - 20, style=info_label_style)
    app_instance.info_name_label.pack(anchor="w", pady=2)
    app_instance.info_size_label = ttk.Label(info_subframe, text="Size: -", style=info_label_style)
    app_instance.info_size_label.pack(anchor="w", pady=2)
    app_instance.info_type_label = ttk.Label(info_subframe, text="Type: -", style=info_label_style)
    app_instance.info_type_label.pack(anchor="w", pady=2)
    app_instance.info_source_label = ttk.Label(info_subframe, text="Source: -", style=info_label_style) # New label for source
    app_instance.info_source_label.pack(anchor="w", pady=2)


def create_action_bar(app_instance):
    action_frame = ttk.Frame(app_instance.root, padding="10 5 10 5", style="PicsNest.Dark.TFrame")
    action_frame.grid(row=2, column=0, columnspan=2, sticky="ew")

    app_instance.open_button = ttk.Button(action_frame, text="🖼️ Open/View", command=app_instance.open_selected_item_action, state=tk.DISABLED, style="PicsNest.Primary.TButton")
    app_instance.open_button.pack(side=tk.LEFT, padx=5)

    app_instance.delete_button = ttk.Button(action_frame, text="🗑️ Delete", command=app_instance.delete_selected_items_action_entry, state=tk.DISABLED, style="PicsNest.Danger.TButton")
    app_instance.delete_button.pack(side=tk.LEFT, padx=5)

    app_instance.undo_button = ttk.Button(action_frame, text="↩️ Undo", command=app_instance._undo_last_action, state=tk.DISABLED, style="PicsNest.Tool.TButton")
    app_instance.undo_button.pack(side=tk.LEFT, padx=5)

def apply_app_styles(app_instance):
    style = ttk.Style()
    current_accent = get_current_accent_color()

    try:
        if 'clam' in style.theme_names(): style.theme_use('clam')
        elif 'alt' in style.theme_names(): style.theme_use('alt')
    except tk.TclError:
        print("Warning: Could not set 'clam' or 'alt' theme. Using default.")

    style.configure(".", background=PICSNEST_BG_DARK, foreground=PICSNEST_TEXT_LIGHT,
                    borderwidth=0, relief=tk.FLAT, highlightthickness=0,
                    font=('Segoe UI', 10))
    style.configure("TFrame", background=PICSNEST_BG_DARK)
    style.configure("TLabel", background=PICSNEST_BG_DARK, foreground=PICSNEST_TEXT_LIGHT, padding=2)
    style.configure("TButton", background=PICSNEST_BG_MEDIUM, foreground=PICSNEST_TEXT_LIGHT,
                    relief=tk.FLAT, borderwidth=1, padding="5 3", font=('Segoe UI', 9, 'bold'))
    style.map("TButton",
              background=[('active', PICSNEST_BG_LIGHT), ('disabled', PICSNEST_BG_MEDIUM)],
              foreground=[('disabled', PICSNEST_BORDER_LIGHT)])

    style.configure("TCheckbutton", background=PICSNEST_BG_DARK, foreground=PICSNEST_TEXT_LIGHT, indicatorcolor=PICSNEST_TEXT_LIGHT)
    style.map("TCheckbutton",
        background=[('active', PICSNEST_BG_LIGHT)],
        indicatorcolor=[("selected", current_accent), ("pressed", current_accent)])

    style.configure("TLabelframe", background=PICSNEST_BG_DARK, foreground=PICSNEST_TEXT_LIGHT, borderwidth=1, relief=tk.SOLID)
    style.configure("TLabelframe.Label", background=PICSNEST_BG_DARK, foreground=PICSNEST_TEXT_LIGHT, font=('Segoe UI', 10, 'bold'))

    style.configure("TScrollbar", gripcount=0, relief=tk.FLAT,
                    background=PICSNEST_BG_MEDIUM, troughcolor=PICSNEST_BG_DARK, bordercolor=PICSNEST_BG_DARK,
                    arrowcolor=PICSNEST_TEXT_LIGHT, arrowsize=12)
    style.map("TScrollbar", background=[('active', PICSNEST_BG_LIGHT)])
    style.configure("PicsNest.Vertical.TScrollbar", width=15)
    style.configure("PicsNest.Horizontal.TScrollbar", height=15)

    style.configure("PicsNest.Dark.TFrame", background=PICSNEST_BG_DARK)

    style.configure("PicsNest.Path.TLabel", background=PICSNEST_BG_MEDIUM, foreground=PICSNEST_TEXT_LIGHT, font=('Segoe UI', 9))
    style.configure("PicsNest.Status.TLabel", background=PICSNEST_BG_DARK, foreground=PICSNEST_TEXT_LIGHT, font=('Segoe UI', 9, 'italic'))
    style.configure("PicsNest.LargeTitle.TLabel", background=PICSNEST_BG_DARK, foreground=PICSNEST_TEXT_LIGHT, font=('Segoe UI', 24, 'bold'))
    style.configure("PicsNest.HugeIcon.TLabel", background=PICSNEST_BG_DARK, foreground=current_accent, font=('Segoe UI Symbol', 64))

    style.configure("PicsNest.Tool.TButton", background=PICSNEST_BG_MEDIUM, foreground=PICSNEST_TEXT_LIGHT, font=('Segoe UI', 10))
    style.map("PicsNest.Tool.TButton", background=[('active', PICSNEST_BG_LIGHT)])

    style.configure("PicsNest.Welcome.TButton", background=current_accent, foreground=PICSNEST_TEXT_LIGHT, font=('Segoe UI', 12, 'bold'), padding="10 5")
    style.map("PicsNest.Welcome.TButton", background=[('active', PICSNEST_BG_LIGHT)])


    style.configure("PicsNest.Primary.TButton", background=PICSNEST_ACCENT_GREEN, foreground=PICSNEST_TEXT_LIGHT, font=('Segoe UI', 10))
    style.map("PicsNest.Primary.TButton", background=[('active', '#27ae60')])

    style.configure("PicsNest.Danger.TButton", background=PICSNEST_ACCENT_RED, foreground=PICSNEST_TEXT_LIGHT, font=('Segoe UI', 10))
    style.map("PicsNest.Danger.TButton", background=[('active', '#c0392b')])

    item_frame_common_dict = {"relief": tk.SOLID, "padding": 2}

    style.configure("PicsNest.Item.TFrame", background=PICSNEST_ITEM_PLACEHOLDER_BG, bordercolor=PICSNEST_BORDER_LIGHT, borderwidth=1, **item_frame_common_dict)
    style.configure("PicsNest.ItemLoaded.TFrame", background=PICSNEST_ITEM_LOADED_BG, bordercolor=PICSNEST_BORDER_LIGHT, borderwidth=1, **item_frame_common_dict)
    style.configure("PicsNest.Folder.TFrame", background=PICSNEST_FOLDER_REPRESENTATION_BG, bordercolor=current_accent, borderwidth=1, **item_frame_common_dict)
    style.configure("PicsNest.VideoItem.TFrame", background=PICSNEST_ITEM_LOADED_BG, bordercolor=PICSNEST_BORDER_LIGHT, borderwidth=1, **item_frame_common_dict)
    style.configure("PicsNest.VideoPlaceholder.TFrame", background=PICSNEST_ITEM_PLACEHOLDER_BG, bordercolor=PICSNEST_BORDER_LIGHT, borderwidth=1, **item_frame_common_dict)

    style.configure("PicsNest.Selected.TFrame", background=current_accent, bordercolor=PICSNEST_TEXT_LIGHT,
                    relief=tk.SOLID, padding=2, borderwidth=2)
    style.configure("PicsNest.Similar.TFrame", background=PICSNEST_BG_MEDIUM, bordercolor=PICSNEST_SIMILAR_BG,
                    relief=tk.SOLID, padding=2, borderwidth=2)
    # New style for Screenshot/Downloaded items (can be same as Similar or unique)
    style.configure("PicsNest.ScreenshotDownloaded.TFrame", background=PICSNEST_BG_MEDIUM, bordercolor=PICSNEST_ACCENT_BLUE, # Example: Blue border
                    relief=tk.SOLID, padding=2, borderwidth=2)


    style.configure("PicsNest.Error.TFrame", background=PICSNEST_ERROR_BG, bordercolor=PICSNEST_TEXT_LIGHT, borderwidth=1, **item_frame_common_dict)

    style.configure("PicsNest.ItemThumb.TLabel", background=PICSNEST_BG_MEDIUM, foreground=PICSNEST_TEXT_LIGHT)
    style.configure("PicsNest.ItemName.TLabel", background="parent", foreground=PICSNEST_TEXT_LIGHT, font=('Segoe UI', 9)) # Font size increased
    style.configure("PicsNest.ErrorIcon.TLabel", background="parent", foreground=PICSNEST_ACCENT_RED)
    style.configure("PicsNest.PlaceholderIcon.TLabel", background="parent", foreground=PICSNEST_TEXT_LIGHT)

    style.configure("PicsNest.Preview.TLabelframe", background=PICSNEST_BG_DARK, relief=tk.SOLID, borderwidth=1)
    style.configure("PicsNest.Preview.TLabelframe.Label", foreground=current_accent, background=PICSNEST_BG_DARK, font=('Segoe UI', 11, 'bold'))
    style.configure("PicsNest.PreviewContainer.TFrame", background=PICSNEST_BG_MEDIUM)
    style.configure("PicsNest.PreviewPlaceholder.TLabel", background=PICSNEST_BG_MEDIUM, foreground=PICSNEST_TEXT_LIGHT, font=('Segoe UI', 10, 'italic'))
    style.configure("PicsNest.PreviewImage.TLabel", background=PICSNEST_VIEWER_BG)
    style.configure("PicsNest.PreviewError.TLabel", background=PICSNEST_BG_MEDIUM, foreground=PICSNEST_ACCENT_RED)
    style.configure("PicsNest.Info.TLabel", background=PICSNEST_BG_DARK, foreground=PICSNEST_TEXT_LIGHT, font=('Segoe UI', 9))

    style.configure("PicsNest.Rename.TEntry",
                    fieldbackground=PICSNEST_BG_LIGHT,
                    foreground=PICSNEST_TEXT_LIGHT,
                    insertcolor=PICSNEST_TEXT_LIGHT,
                    bordercolor=current_accent,
                    lightcolor=PICSNEST_BG_MEDIUM,
                    darkcolor=PICSNEST_BG_DARK,
                    borderwidth=1)
    style.map("PicsNest.Rename.TEntry",
              bordercolor=[('focus', current_accent)],
              fieldbackground=[('focus', PICSNEST_BG_MEDIUM)])
