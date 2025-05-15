# video_viewer.py

import tkinter as tk
from tkinter import ttk, messagebox
import os
import sys 

try:
    import vlc
except ImportError:
    vlc = None 

class VideoViewerWindow(tk.Toplevel):
    def __init__(self, parent, video_paths_list, current_index, main_app_ref):
        super().__init__(parent)
        self.transient(parent); self.grab_set(); self.focus_set()
        self.configure(bg="black") 

        self._vlc_initialized = False; self._vlc_released = False; self._vlc_output_set = False
        self._is_seeking_by_drag = False; self._update_after_id = None
        self._was_playing_before_seek = False; self._is_mouse_pressed_on_seekbar = False
        self.items_deleted_from_viewer = False 

        if not vlc: 
            messagebox.showerror("Error", "VLC (python-vlc) not found. Cannot play video.", parent=self)
            self.after(100, self.destroy_safely); return

        self.video_paths = list(video_paths_list); self.current_video_index = current_index
        self.main_app = main_app_ref
        self.title("Video Viewer"); self.geometry("800x650"); self.minsize(450, 350)

        try:
            self.instance = vlc.Instance()
            if not self.instance: raise vlc.VLCException("Failed VLC instance.")
            self.player = self.instance.media_player_new()
            if not self.player:
                if self.instance: self.instance.release()
                raise vlc.VLCException("Failed VLC media player.")
            self.vlc_event_manager = self.player.event_manager()
            self.vlc_event_manager.event_attach(vlc.EventType.MediaPlayerPositionChanged, self._on_vlc_position_changed)
            self.vlc_event_manager.event_attach(vlc.EventType.MediaPlayerLengthChanged, self._on_vlc_length_changed)
            self.vlc_event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_vlc_end_reached)
            self._vlc_initialized = True
        except Exception as e:
            messagebox.showerror("VLC Error", f"VLC init error: {e}", parent=self); self._vlc_initialized = False
            if hasattr(self, 'player') and self.player: self.player.release()
            if hasattr(self, 'instance') and self.instance: self.instance.release()
            self.after(100, self.destroy_safely); return

        self.video_frame = tk.Frame(self, bg="black") 
        self.video_frame.pack(expand=True, fill=tk.BOTH, padx=0, pady=0)
        self.video_frame.bind("<Map>", self._on_video_frame_map)
        self.video_frame.bind("<Configure>", self._on_video_frame_configure)

        controls_outer_frame = ttk.Frame(self) 
        controls_outer_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(5,10))
        time_seekbar_frame = ttk.Frame(controls_outer_frame)
        time_seekbar_frame.pack(fill=tk.X, padx=10, pady=(0,5))
        self.current_time_label = ttk.Label(time_seekbar_frame, text="00:00"); self.current_time_label.pack(side=tk.LEFT)
        self.seekbar_var = tk.DoubleVar()
        self.seekbar = ttk.Scale(time_seekbar_frame, from_=0, to=1.0, orient=tk.HORIZONTAL, variable=self.seekbar_var, command=self._on_seekbar_drag_command)
        self.seekbar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.seekbar.bind("<ButtonPress-1>", self._on_seekbar_mouse_press)
        self.seekbar.bind("<ButtonRelease-1>", self._on_seekbar_mouse_release)
        self.total_time_label = ttk.Label(time_seekbar_frame, text="00:00"); self.total_time_label.pack(side=tk.RIGHT)
        buttons_frame = ttk.Frame(controls_outer_frame); buttons_frame.pack(fill=tk.X)
        buttons_inner_frame = ttk.Frame(buttons_frame); buttons_inner_frame.pack()
        self.prev_button = ttk.Button(buttons_inner_frame, text="< Vid", command=self.show_prev_video); self.prev_button.pack(side=tk.LEFT, padx=3)
        self.seek_bwd_button = ttk.Button(buttons_inner_frame, text="<< 5s", command=lambda: self.seek_relative(-5000)); self.seek_bwd_button.pack(side=tk.LEFT, padx=2)
        self.play_pause_button = ttk.Button(buttons_inner_frame, text="Play", command=self.toggle_play_pause, width=7); self.play_pause_button.pack(side=tk.LEFT, padx=3)
        self.seek_fwd_button = ttk.Button(buttons_inner_frame, text="5s >>", command=lambda: self.seek_relative(5000)); self.seek_fwd_button.pack(side=tk.LEFT, padx=2)
        self.next_button = ttk.Button(buttons_inner_frame, text="Vid >", command=self.show_next_video); self.next_button.pack(side=tk.LEFT, padx=3)
        self.delete_button = ttk.Button(buttons_inner_frame, text="Delete", command=self.delete_current_video); self.delete_button.pack(side=tk.LEFT, padx=(10,3))
        
        self.bind("<Escape>", lambda e: self.destroy()) # Bind Escape to self.destroy
        self.bind("<Left>", lambda e: self.seek_relative(-5000)) 
        self.bind("<Right>", lambda e: self.seek_relative(5000)) 
        self.bind("<space>", lambda e: self.toggle_play_pause())
        self.bind("<Delete>", lambda e: self.delete_current_video())
        
        self.protocol("WM_DELETE_WINDOW", self.destroy) # Ensure destroy is called on window X button
        
        self.load_and_play_video(); self._update_ui_loop()

    def _format_time(self, ms):
        if ms < 0: ms = 0
        s, m, h = int((ms/1000)%60), int((ms/(1000*60))%60), int((ms/(1000*60*60))%24)
        return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

    def _on_vlc_position_changed(self, event):
        if not self._is_seeking_by_drag and self.winfo_exists(): 
            pos = event.u.new_position
            if 0.0 <= pos <= 1.0: self.seekbar_var.set(pos)

    def _on_vlc_length_changed(self, event):
        if self.winfo_exists():
            l_ms = self.player.get_length()
            self.total_time_label.config(text=self._format_time(l_ms) if l_ms > 0 else "--:--")

    def _on_vlc_end_reached(self, event):
        if self.winfo_exists(): self.play_pause_button.config(text="Play"); self.seekbar_var.set(1.0) 

    def _update_ui_loop(self):
        if not self.winfo_exists() or self._vlc_released or not self._vlc_initialized: return
        if self.player:
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
        if self.player and self.player.is_seekable():
            self._is_mouse_pressed_on_seekbar = True 
            if self.player.is_playing(): self.player.pause(); self._was_playing_before_seek = True
            else: self._was_playing_before_seek = False
            try:
                w = self.seekbar.winfo_width()
                if w > 0:
                    ratio = max(0.0, min(1.0, event.x / w)); self.seekbar_var.set(ratio)
                    l_ms = self.player.get_length()
                    if l_ms > 0 and self.winfo_exists(): self.current_time_label.config(text=self._format_time(int(ratio * l_ms)))
            except Exception as e: print(f"Seekbar press error: {e}")

    def _on_seekbar_mouse_release(self, event):
        if self.player and self.player.is_seekable() and self._is_mouse_pressed_on_seekbar:
            self._is_mouse_pressed_on_seekbar = False 
            if self._is_seeking_by_drag: 
                self._is_seeking_by_drag = False 
                new_pos = self.seekbar_var.get()
                if 0.0 <= new_pos <= 1.0: self.player.set_position(new_pos)
            if self._was_playing_before_seek: self.player.play()
            self._was_playing_before_seek = False
            ct_ms = self.player.get_time()
            if self.winfo_exists():
                self.current_time_label.config(text=self._format_time(ct_ms))
                final_pos = self.player.get_position()
                if 0.0 <= final_pos <= 1.0: self.seekbar_var.set(final_pos)

    def _on_seekbar_drag_command(self, value_str): 
        if self.player and self.player.is_seekable() and self._is_mouse_pressed_on_seekbar:
            self._is_seeking_by_drag = True 
            try:
                new_pos = float(value_str) 
                if 0.0 <= new_pos <= 1.0:
                    l_ms = self.player.get_length()
                    if l_ms > 0 and self.winfo_exists(): self.current_time_label.config(text=self._format_time(int(new_pos * l_ms)))
            except ValueError: pass 

    def seek_relative(self, offset_ms):
        if self.player and self._vlc_initialized and not self._vlc_released and self.player.is_seekable():
            curr_t, vid_l = self.player.get_time(), self.player.get_length()
            new_t = max(0, min(vid_l if vid_l > 0 else curr_t + offset_ms, curr_t + offset_ms))
            self.player.set_time(new_t)
            if self.winfo_exists():
                self.current_time_label.config(text=self._format_time(new_t))
                if vid_l > 0:
                    ratio = float(new_t) / vid_l
                    if 0.0 <= ratio <= 1.0: self.seekbar_var.set(ratio)

    def set_playback_rate(self, rate): 
        if self.player and self._vlc_initialized and not self._vlc_released: self.player.set_rate(rate)

    def _on_video_frame_map(self, event): self._setup_vlc_output()
    def _on_video_frame_configure(self, event):
        if self.winfo_ismapped(): self._setup_vlc_output()

    def _setup_vlc_output(self):
        if not self.winfo_exists() or not self._vlc_initialized or self._vlc_released: return
        try:
            self.update_idletasks(); hwnd = self.video_frame.winfo_id() 
            w, h = self.video_frame.winfo_width(), self.video_frame.winfo_height()
            if hwnd and w > 1 and h > 1: 
                if sys.platform == "win32": self.player.set_hwnd(hwnd)
                else: self.player.set_xwindow(hwnd) 
                self._vlc_output_set = True
                if self.player.get_media() and not self.player.is_playing():
                    state = self.player.get_state()
                    if state not in [vlc.State.Playing, vlc.State.Paused] and not self._was_playing_before_seek:
                        self.player.play()
        except Exception as e: self._vlc_output_set = False; print(f"VLC HWND error: {e}")

    def load_and_play_video(self):
        if not self._vlc_initialized or self._vlc_released: return
        if not self.video_paths or not (0 <= self.current_video_index < len(self.video_paths)): self.destroy_safely(); return 
        if self.winfo_exists(): self.seekbar_var.set(0.0); self.current_time_label.config(text="00:00"); self.total_time_label.config(text="00:00"); self.play_pause_button.config(text="Play")
        path = self.video_paths[self.current_video_index]
        if not os.path.exists(path):
            messagebox.showwarning("Warning", f"File not found:\n{path}", parent=self)
            self.video_paths.pop(self.current_video_index)
            if not self.video_paths: self.destroy_safely(); return
            self.current_video_index = min(self.current_video_index, len(self.video_paths) - 1) 
            self.load_and_play_video(); return 
        self.title(os.path.basename(path))
        try:
            media = self.instance.media_new(path) 
            if not media: print(f"Failed media: {path}"); return
            self.player.set_media(media); media.release() 
            if self._vlc_output_set: self.player.play()
        except Exception as e: messagebox.showerror("VLC Playback Error", f"Error playing {os.path.basename(path)}:\n{e}", parent=self)
        if self.winfo_exists(): self.update_nav_buttons_state()

    def show_prev_video(self):
        if self._vlc_initialized and not self._vlc_released and self.player and self.current_video_index > 0:
            if self.player: self.player.stop() 
            self.current_video_index -= 1; self._vlc_output_set = False; self.load_and_play_video()

    def show_next_video(self):
        if self._vlc_initialized and not self._vlc_released and self.player and self.current_video_index < len(self.video_paths) - 1:
            if self.player: self.player.stop()
            self.current_video_index += 1; self._vlc_output_set = False; self.load_and_play_video()

    def toggle_play_pause(self):
        if self._vlc_initialized and not self._vlc_released and self.player: 
            if self.player.is_playing(): self.player.pause()
            else: self.player.play()

    def delete_current_video(self): 
        if not self._vlc_initialized or self._vlc_released or not self.video_paths or not (0 <= self.current_video_index < len(self.video_paths)): return
        path_del = self.video_paths[self.current_video_index]
        if self.player: self.player.stop() 
        
        deleted_successfully = self.main_app.delete_selected_items_action(items_to_delete_override={path_del}, from_viewer=True)
        
        if deleted_successfully:
            self.items_deleted_from_viewer = True 
            self.video_paths.pop(self.current_video_index)
            if not self.video_paths: self.destroy_safely(); return
            self.current_video_index = min(self.current_video_index, len(self.video_paths) - 1)
            self._vlc_output_set = False; self.load_and_play_video()
        elif self.player and os.path.exists(path_del): 
            self._vlc_output_set = False; self.load_and_play_video()


    def update_nav_buttons_state(self):
        if hasattr(self, 'prev_button') and self.prev_button.winfo_exists(): self.prev_button.config(state=tk.NORMAL if self.current_video_index > 0 else tk.DISABLED)
        if hasattr(self, 'next_button') and self.next_button.winfo_exists(): self.next_button.config(state=tk.NORMAL if self.current_video_index < len(self.video_paths) - 1 else tk.DISABLED)
        if hasattr(self, 'delete_button') and self.delete_button.winfo_exists(): self.delete_button.config(state=tk.NORMAL if self.video_paths else tk.DISABLED)

    def destroy_safely(self): 
        if self.winfo_exists(): self.destroy()

    def destroy(self): # MODIFIED for robust VLC cleanup
        if self._update_after_id: 
            self.after_cancel(self._update_after_id)
            self._update_after_id = None

        if not self._vlc_released: 
            self._vlc_released = True 

            if hasattr(self, 'player') and self.player and self._vlc_initialized:
                try:
                    if self.player.is_playing():
                        self.player.stop()
                except Exception as e:
                    print(f"Error stopping VLC player during destroy: {e}")
                
                # Detach VLC from the window handle BEFORE releasing player
                try:
                    if sys.platform == "win32":
                        self.player.set_hwnd(None)
                    else:
                        self.player.set_xwindow(0) 
                except Exception as e:
                    print(f"Error detaching VLC HWND/XWindow during destroy: {e}")
            
            if hasattr(self, 'vlc_event_manager') and self.vlc_event_manager and self._vlc_initialized:
                try: 
                    self.vlc_event_manager.event_detach(vlc.EventType.MediaPlayerPositionChanged)
                    self.vlc_event_manager.event_detach(vlc.EventType.MediaPlayerLengthChanged)
                    self.vlc_event_manager.event_detach(vlc.EventType.MediaPlayerEndReached)
                except Exception as e:
                    print(f"Error detaching VLC events during destroy: {e}")
            
            if hasattr(self, 'player') and self.player and self._vlc_initialized:
                try:
                    if self.player.get_instance(): 
                        self.player.release()
                except Exception as e:
                    print(f"Error releasing VLC player during destroy: {e}")
                self.player = None 
            
            if hasattr(self, 'instance') and self.instance and self._vlc_initialized:
                try:
                    self.instance.release()
                except Exception as e:
                    print(f"Error releasing VLC instance during destroy: {e}")
                self.instance = None 
        
        if hasattr(self, 'main_app') and self.main_app and self.main_app.root.winfo_exists():
            if self.items_deleted_from_viewer: 
                current_f = self.main_app.current_folder.get()
                if isinstance(current_f, str) and os.path.isdir(current_f): 
                    self.main_app.load_items(current_f) 
            else:
                self.main_app.update_ui_state() 
                
        if self.winfo_exists(): 
            super().destroy()