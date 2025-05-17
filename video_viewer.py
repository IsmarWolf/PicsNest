# video_viewer.py

import tkinter as tk
from tkinter import ttk, messagebox
import os
import sys
from constants import PICSNEST_VIEWER_BG, PICSNEST_TEXT_LIGHT, PICSNEST_BG_DARK, PICSNEST_BG_MEDIUM

try:
    import vlc
except ImportError:
    vlc = None

class VideoViewerWindow(tk.Toplevel):
    def __init__(self, parent, video_paths_list, current_index, main_app_ref):
        super().__init__(parent)
        self.transient(parent); self.grab_set(); self.focus_set()
        self.configure(bg=PICSNEST_VIEWER_BG)

        self._vlc_initialized = False
        self._vlc_released = False
        self._vlc_output_set = False
        self._is_seeking_by_drag = False
        self._update_after_id = None
        self._was_playing_before_seek = False
        self._is_mouse_pressed_on_seekbar = False
        self.items_deleted_from_viewer = False

        if not vlc:
            messagebox.showerror("Error", "VLC (python-vlc) not found. Cannot play video.", parent=self)
            self.after(100, self.destroy_safely); return

        self.video_paths = list(video_paths_list)
        self.current_video_index = current_index
        self.main_app = main_app_ref
        self.title("PicsNest - Video Viewer")
        self.geometry("800x650")
        self.minsize(450, 350)

        self.instance = None
        self.player = None
        self.vlc_event_manager = None

        try:
            self.instance = vlc.Instance()
            if not self.instance: raise vlc.VLCException("Failed to create VLC instance.")
            self.player = self.instance.media_player_new()
            if not self.player: raise vlc.VLCException("Failed to create VLC media player.")
            self.vlc_event_manager = self.player.event_manager()
            if not self.vlc_event_manager: raise vlc.VLCException("Failed to get VLC event manager.")
            self.vlc_event_manager.event_attach(vlc.EventType.MediaPlayerPositionChanged, self._on_vlc_position_changed)
            self.vlc_event_manager.event_attach(vlc.EventType.MediaPlayerLengthChanged, self._on_vlc_length_changed)
            self.vlc_event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_vlc_end_reached)
            self._vlc_initialized = True
        except Exception as e:
            messagebox.showerror("VLC Initialization Error", f"VLC could not be initialized: {e}", parent=self)
            self._vlc_initialized = False
            if self.player: self.player.release()
            if self.instance: self.instance.release()
            self.player = None; self.instance = None
            self.after(100, self.destroy_safely)
            return

        self.video_frame = tk.Frame(self, bg=PICSNEST_VIEWER_BG) # Video itself plays on this
        self.video_frame.pack(expand=True, fill=tk.BOTH, padx=0, pady=0)
        self.video_frame.bind("<Map>", self._on_video_frame_map)
        self.video_frame.bind("<Configure>", self._on_video_frame_configure)

        # Controls Styling
        label_style = "PicsNest.Info.TLabel" # Consistent with main app's info labels
        button_style = "PicsNest.Tool.TButton"
        danger_button_style = "PicsNest.Danger.TButton"
        seekbar_style = "PicsNest.Horizontal.TScrollbar" # Use TScrollbar style for Scale if compatible

        controls_outer_frame = ttk.Frame(self, style="PicsNest.Dark.TFrame")
        controls_outer_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(5,10))

        time_seekbar_frame = ttk.Frame(controls_outer_frame, style="PicsNest.Dark.TFrame")
        time_seekbar_frame.pack(fill=tk.X, padx=10, pady=(0,5))
        self.current_time_label = ttk.Label(time_seekbar_frame, text="00:00", style=label_style); self.current_time_label.pack(side=tk.LEFT)
        self.seekbar_var = tk.DoubleVar()
        self.seekbar = ttk.Scale(time_seekbar_frame, from_=0, to=1.0, orient=tk.HORIZONTAL, variable=self.seekbar_var, command=self._on_seekbar_drag_command, style=seekbar_style) # Apply style
        self.seekbar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.seekbar.bind("<ButtonPress-1>", self._on_seekbar_mouse_press)
        self.seekbar.bind("<ButtonRelease-1>", self._on_seekbar_mouse_release)
        self.total_time_label = ttk.Label(time_seekbar_frame, text="00:00", style=label_style); self.total_time_label.pack(side=tk.RIGHT)

        buttons_frame = ttk.Frame(controls_outer_frame, style="PicsNest.Dark.TFrame"); buttons_frame.pack(fill=tk.X)
        buttons_inner_frame = ttk.Frame(buttons_frame, style="PicsNest.Dark.TFrame"); buttons_inner_frame.pack()
        self.prev_button = ttk.Button(buttons_inner_frame, text="< Vid", command=self.show_prev_video, style=button_style); self.prev_button.pack(side=tk.LEFT, padx=3)
        self.seek_bwd_button = ttk.Button(buttons_inner_frame, text="<< 5s", command=lambda: self.seek_relative(-5000), style=button_style); self.seek_bwd_button.pack(side=tk.LEFT, padx=2)
        self.play_pause_button = ttk.Button(buttons_inner_frame, text="Play", command=self.toggle_play_pause, width=7, style=button_style); self.play_pause_button.pack(side=tk.LEFT, padx=3)
        self.seek_fwd_button = ttk.Button(buttons_inner_frame, text="5s >>", command=lambda: self.seek_relative(5000), style=button_style); self.seek_fwd_button.pack(side=tk.LEFT, padx=2)
        self.next_button = ttk.Button(buttons_inner_frame, text="Vid >", command=self.show_next_video, style=button_style); self.next_button.pack(side=tk.LEFT, padx=3)
        self.delete_button = ttk.Button(buttons_inner_frame, text="Delete", command=self.delete_current_video, style=danger_button_style); self.delete_button.pack(side=tk.LEFT, padx=(10,3))

        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Left>", lambda e: self.seek_relative(-5000))
        self.bind("<Right>", lambda e: self.seek_relative(5000))
        self.bind("<space>", lambda e: self.toggle_play_pause())
        self.bind("<Delete>", lambda e: self.delete_current_video())

        self.protocol("WM_DELETE_WINDOW", self.destroy)

        if self._vlc_initialized:
            self.load_and_play_video()
            self._update_ui_loop()

    def _format_time(self, ms):
        if ms < 0: ms = 0
        s, m, h = int((ms/1000)%60), int((ms/(1000*60))%60), int((ms/(1000*60*60))%24)
        return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

    def _on_vlc_position_changed(self, event):
        if not self._is_seeking_by_drag and self.winfo_exists() and self.player:
            pos = self.player.get_position()
            if 0.0 <= pos <= 1.0: self.seekbar_var.set(pos)

    def _on_vlc_length_changed(self, event):
        if self.winfo_exists() and self.player:
            l_ms = self.player.get_length()
            self.total_time_label.config(text=self._format_time(l_ms) if l_ms > 0 else "--:--")

    def _on_vlc_end_reached(self, event):
        if self.winfo_exists():
            self.play_pause_button.config(text="Play")
            self.seekbar_var.set(1.0)

    def _update_ui_loop(self):
        if not self.winfo_exists() or self._vlc_released or not self._vlc_initialized or not self.player: return
        ct_ms = self.player.get_time()
        if self.winfo_exists(): self.current_time_label.config(text=self._format_time(ct_ms))
        if not self._is_seeking_by_drag:
            pos = self.player.get_position()
            if 0.0 <= pos <= 1.0 and self.winfo_exists(): self.seekbar_var.set(pos)
        if self.winfo_exists(): self.play_pause_button.config(text="Pause" if self.player.is_playing() else "Play")
        l_ms = self.player.get_length()
        if l_ms > 0 and self.total_time_label.cget("text") in ["00:00", "--:--"] and self.winfo_exists():
                self.total_time_label.config(text=self._format_time(l_ms))
        self._update_after_id = self.after(250, self._update_ui_loop)

    def _on_seekbar_mouse_press(self, event):
        if self.player and self.player.is_seekable() and self._vlc_initialized:
            self._is_mouse_pressed_on_seekbar = True
            self._was_playing_before_seek = self.player.is_playing()
            if self._was_playing_before_seek: self.player.pause()
            try:
                w = self.seekbar.winfo_width()
                if w > 0:
                    ratio = max(0.0, min(1.0, event.x / w))
                    self.seekbar_var.set(ratio)
                    l_ms = self.player.get_length()
                    if l_ms > 0 and self.winfo_exists():
                         self.current_time_label.config(text=self._format_time(int(ratio * l_ms)))
            except Exception as e: print(f"Seekbar press error: {e}")

    def _on_seekbar_mouse_release(self, event):
        if self.player and self.player.is_seekable() and self._vlc_initialized and self._is_mouse_pressed_on_seekbar:
            self._is_mouse_pressed_on_seekbar = False
            new_pos = self.seekbar_var.get()
            if 0.0 <= new_pos <= 1.0: self.player.set_position(new_pos)
            if self._was_playing_before_seek: self.player.play()
            self._is_seeking_by_drag = False
            self._was_playing_before_seek = False
            self.after(50, self._force_ui_update_after_seek)

    def _force_ui_update_after_seek(self):
        if self.player and self.winfo_exists() and self._vlc_initialized:
            ct_ms = self.player.get_time()
            self.current_time_label.config(text=self._format_time(ct_ms))
            final_pos = self.player.get_position()
            if 0.0 <= final_pos <= 1.0: self.seekbar_var.set(final_pos)
            self.play_pause_button.config(text="Pause" if self.player.is_playing() else "Play")

    def _on_seekbar_drag_command(self, value_str):
        if self.player and self.player.is_seekable() and self._vlc_initialized and self._is_mouse_pressed_on_seekbar:
            self._is_seeking_by_drag = True
            try:
                new_pos = float(value_str)
                if 0.0 <= new_pos <= 1.0:
                    l_ms = self.player.get_length()
                    if l_ms > 0 and self.winfo_exists():
                        self.current_time_label.config(text=self._format_time(int(new_pos * l_ms)))
            except ValueError: pass

    def seek_relative(self, offset_ms):
        if self.player and self._vlc_initialized and not self._vlc_released and self.player.is_seekable():
            curr_t = self.player.get_time(); vid_l = self.player.get_length()
            new_t = curr_t + offset_ms
            if vid_l > 0: new_t = max(0, min(vid_l, new_t))
            else: new_t = max(0, new_t)
            self.player.set_time(new_t)
            if self.winfo_exists():
                self.current_time_label.config(text=self._format_time(new_t))
                if vid_l > 0:
                    ratio = float(new_t) / vid_l
                    if 0.0 <= ratio <= 1.0: self.seekbar_var.set(ratio)
                self.play_pause_button.config(text="Pause" if self.player.is_playing() else "Play")

    def set_playback_rate(self, rate):
        if self.player and self._vlc_initialized and not self._vlc_released: self.player.set_rate(rate)

    def _on_video_frame_map(self, event):
        if self.winfo_ismapped(): self._setup_vlc_output()

    def _on_video_frame_configure(self, event):
        if self.winfo_ismapped() and not self._vlc_output_set: self._setup_vlc_output()

    def _setup_vlc_output(self):
        if not self.winfo_exists() or not self._vlc_initialized or self._vlc_released or not self.player: return
        if self._vlc_output_set: return
        try:
            self.update_idletasks(); hwnd = self.video_frame.winfo_id()
            w, h = self.video_frame.winfo_width(), self.video_frame.winfo_height()
            if hwnd and w > 1 and h > 1 :
                if sys.platform == "win32": self.player.set_hwnd(hwnd)
                else: self.player.set_xwindow(hwnd)
                self._vlc_output_set = True
                current_media = self.player.get_media()
                if current_media and not self.player.is_playing():
                    state = self.player.get_state()
                    if state in [vlc.State.NothingSpecial, vlc.State.Opening, vlc.State.Buffering, vlc.State.Ended, vlc.State.Error, vlc.State.Stopped]:
                        self.player.play()
        except Exception as e:
            self._vlc_output_set = False
            print(f"VLC HWND/XWindow assignment error: {e}")

    def load_and_play_video(self):
        if not self._vlc_initialized or self._vlc_released or not self.player: return
        if not self.video_paths or not (0 <= self.current_video_index < len(self.video_paths)):
            self.destroy_safely(); return
        if self.winfo_exists():
            self.seekbar_var.set(0.0)
            self.current_time_label.config(text="00:00")
            self.total_time_label.config(text="00:00")
            self.play_pause_button.config(text="Play")
        path = self.video_paths[self.current_video_index]
        if not os.path.exists(path):
            messagebox.showwarning("File Not Found", f"Video file not found:\n{path}", parent=self)
            self.video_paths.pop(self.current_video_index)
            if not self.video_paths: self.destroy_safely(); return
            self.current_video_index = min(self.current_video_index, len(self.video_paths) - 1)
            self.load_and_play_video()
            return
        self.title(f"PicsNest - {os.path.basename(path)}")
        try:
            media = self.instance.media_new(path)
            if not media:
                print(f"Failed to create VLC media object for: {path}")
                messagebox.showerror("VLC Error", f"Could not load media: {os.path.basename(path)}", parent=self)
                return
            self.player.set_media(media); media.release()
            if self._vlc_output_set: self.player.play()
        except Exception as e:
            messagebox.showerror("VLC Playback Error", f"Error playing {os.path.basename(path)}:\n{e}", parent=self)
        if self.winfo_exists(): self.update_nav_buttons_state()

    def show_prev_video(self):
        if self._vlc_initialized and not self._vlc_released and self.player and self.current_video_index > 0:
            if self.player.is_playing(): self.player.stop()
            self.current_video_index -= 1
            self._vlc_output_set = False
            self.load_and_play_video()

    def show_next_video(self):
        if self._vlc_initialized and not self._vlc_released and self.player and self.current_video_index < len(self.video_paths) - 1:
            if self.player.is_playing(): self.player.stop()
            self.current_video_index += 1
            self._vlc_output_set = False
            self.load_and_play_video()

    def toggle_play_pause(self):
        if self._vlc_initialized and not self._vlc_released and self.player:
            if self.player.get_media():
                if self.player.is_playing():
                    self.player.pause()
                    if self.winfo_exists(): self.play_pause_button.config(text="Play")
                else:
                    self.player.play()
                    if self.winfo_exists(): self.play_pause_button.config(text="Pause")

    def delete_current_video(self):
        if not self._vlc_initialized or self._vlc_released or not self.player or \
           not self.video_paths or not (0 <= self.current_video_index < len(self.video_paths)): return
        path_del = self.video_paths[self.current_video_index]
        was_playing = self.player.is_playing()
        if was_playing: self.player.stop()
        self.player.set_media(None)
        deleted_successfully = self.main_app.delete_selected_items_action_entry(
            items_to_delete_override={path_del}, from_viewer=True
        )
        if deleted_successfully:
            self.items_deleted_from_viewer = True
            self.video_paths.pop(self.current_video_index)
            if not self.video_paths: self.destroy_safely(); return
            if self.current_video_index >= len(self.video_paths) and len(self.video_paths) > 0 :
                 self.current_video_index = len(self.video_paths) - 1
            self._vlc_output_set = False; self.load_and_play_video()
        else:
            if os.path.exists(path_del): # If deletion failed but file still exists, try to reload it
                self._vlc_output_set = False; self.load_and_play_video()
                if was_playing and self.player.get_media(): self.player.play()
            else: # File was deleted by other means or deletion failed and file is gone
                self.items_deleted_from_viewer = True
                self.video_paths.pop(self.current_video_index)
                if not self.video_paths: self.destroy_safely(); return
                if self.current_video_index >= len(self.video_paths) and len(self.video_paths) > 0 :
                    self.current_video_index = len(self.video_paths) - 1
                self._vlc_output_set = False; self.load_and_play_video()

    def update_nav_buttons_state(self):
        if hasattr(self, 'prev_button') and self.prev_button.winfo_exists():
            self.prev_button.config(state=tk.NORMAL if self.current_video_index > 0 else tk.DISABLED)
        if hasattr(self, 'next_button') and self.next_button.winfo_exists():
            self.next_button.config(state=tk.NORMAL if self.current_video_index < len(self.video_paths) - 1 else tk.DISABLED)
        if hasattr(self, 'delete_button') and self.delete_button.winfo_exists():
            self.delete_button.config(state=tk.NORMAL if self.video_paths else tk.DISABLED)

    def destroy_safely(self):
        if self.winfo_exists(): self.destroy()

    def destroy(self):
        if self._vlc_released:
            if self.winfo_exists():
                try:
                    super().destroy()
                except tk.TclError: # Window might already be gone
                    pass
            return

        self._vlc_released = True # Mark as released early

        if self._update_after_id:
            self.after_cancel(self._update_after_id)
            self._update_after_id = None

        if self._vlc_initialized: # Only proceed with VLC cleanup if it was initialized
            if self.player:
                try:
                    if self.player.is_playing():
                        self.player.stop()
                    if self._vlc_output_set: # Check if output was ever set
                        if sys.platform == "win32":
                            self.player.set_hwnd(None)
                        else:
                            self.player.set_xwindow(0) # Use 0 for X11
                        self._vlc_output_set = False
                except Exception as e:
                    print(f"VideoViewerWindow: Error stopping/detaching player output: {e}")

            if self.vlc_event_manager:
                try:
                    self.vlc_event_manager.event_detach(vlc.EventType.MediaPlayerPositionChanged)
                    self.vlc_event_manager.event_detach(vlc.EventType.MediaPlayerLengthChanged)
                    self.vlc_event_manager.event_detach(vlc.EventType.MediaPlayerEndReached)
                except Exception as e:
                    print(f"VideoViewerWindow: Error detaching VLC events: {e}")
                self.vlc_event_manager = None # Clear reference

            if self.player:
                try:
                    current_media = self.player.get_media()
                    if current_media:
                        self.player.set_media(None) # Release media from player
                except Exception as e:
                    print(f"VideoViewerWindow: Error clearing media from player: {e}")
                try:
                    self.player.release()
                except Exception as e:
                    print(f"VideoViewerWindow: Error releasing VLC player: {e}")
                self.player = None # Clear reference

            if self.instance:
                try:
                    self.instance.release()
                except Exception as e:
                    print(f"VideoViewerWindow: Error releasing VLC instance: {e}")
                self.instance = None # Clear reference

        # Handle main app updates after VLC resources are dealt with
        # Schedule these updates to run in the main app's event loop,
        # preventing direct calls during Toplevel destruction.
        if hasattr(self, 'main_app') and self.main_app and self.main_app.root.winfo_exists():
            if self.items_deleted_from_viewer:
                current_f = self.main_app.current_folder.get()
                if isinstance(current_f, str) and os.path.isdir(current_f):
                    self.main_app.root.after(0, lambda cf=current_f: self.main_app.load_items(cf))
            else:
                self.main_app.root.after(0, self.main_app.update_ui_state)

        if self.winfo_exists():
            try:
                super().destroy()
            except tk.TclError: # Window might already be gone due to other events
                pass
