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

        self._vlc_initialized = False
        self._vlc_released = False # Flag to ensure cleanup happens only once
        self._vlc_output_set = False # True once player is successfully attached to window
        self._is_seeking_by_drag = False
        self._update_after_id = None
        self._was_playing_before_seek = False
        self._is_mouse_pressed_on_seekbar = False
        self.items_deleted_from_viewer = False 

        if not vlc: 
            messagebox.showerror("Error", "VLC (python-vlc) not found. Cannot play video.", parent=self)
            self.after(100, self.destroy_safely); return # Use destroy_safely for consistent closing

        self.video_paths = list(video_paths_list)
        self.current_video_index = current_index
        self.main_app = main_app_ref
        self.title("Video Viewer")
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
            # Perform partial cleanup if objects were created
            if self.player: self.player.release()
            if self.instance: self.instance.release()
            self.player = None
            self.instance = None
            self.after(100, self.destroy_safely) # Use destroy_safely for consistent closing
            return

        self.video_frame = tk.Frame(self, bg="black") 
        self.video_frame.pack(expand=True, fill=tk.BOTH, padx=0, pady=0)
        # Bindings for when the frame is ready to draw on
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
        
        self.bind("<Escape>", lambda e: self.destroy()) 
        self.bind("<Left>", lambda e: self.seek_relative(-5000)) 
        self.bind("<Right>", lambda e: self.seek_relative(5000)) 
        self.bind("<space>", lambda e: self.toggle_play_pause())
        self.bind("<Delete>", lambda e: self.delete_current_video())
        
        self.protocol("WM_DELETE_WINDOW", self.destroy) 
        
        if self._vlc_initialized:
            self.load_and_play_video()
            self._update_ui_loop()
    
    # ... (other methods like _format_time, _on_vlc_position_changed, etc. remain the same) ...
    def _format_time(self, ms):
        if ms < 0: ms = 0
        s, m, h = int((ms/1000)%60), int((ms/(1000*60))%60), int((ms/(1000*60*60))%24)
        return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

    def _on_vlc_position_changed(self, event):
        if not self._is_seeking_by_drag and self.winfo_exists() and self.player: 
            pos = self.player.get_position() # Get current position from player
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
        if not self.winfo_exists() or self._vlc_released or not self._vlc_initialized or not self.player:
            return
        
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
            if self._was_playing_before_seek:
                self.player.pause()
            
            # Update seekbar position immediately based on click
            try:
                w = self.seekbar.winfo_width()
                if w > 0:
                    ratio = max(0.0, min(1.0, event.x / w))
                    self.seekbar_var.set(ratio) # This will trigger _on_seekbar_drag_command
                    l_ms = self.player.get_length()
                    if l_ms > 0 and self.winfo_exists():
                         self.current_time_label.config(text=self._format_time(int(ratio * l_ms)))
            except Exception as e:
                print(f"Seekbar press error: {e}")

    def _on_seekbar_mouse_release(self, event):
        if self.player and self.player.is_seekable() and self._vlc_initialized and self._is_mouse_pressed_on_seekbar:
            self._is_mouse_pressed_on_seekbar = False 
            
            # _is_seeking_by_drag might not have been set if it was a quick click
            # The actual seek happens here
            new_pos = self.seekbar_var.get()
            if 0.0 <= new_pos <= 1.0:
                self.player.set_position(new_pos)
            
            if self._was_playing_before_seek:
                self.player.play()
            
            self._is_seeking_by_drag = False # Ensure this is reset
            self._was_playing_before_seek = False

            # Update UI elements to reflect actual player state after seek
            # Small delay to allow VLC to catch up
            self.after(50, self._force_ui_update_after_seek)


    def _force_ui_update_after_seek(self):
        if self.player and self.winfo_exists() and self._vlc_initialized:
            ct_ms = self.player.get_time()
            self.current_time_label.config(text=self._format_time(ct_ms))
            final_pos = self.player.get_position()
            if 0.0 <= final_pos <= 1.0:
                self.seekbar_var.set(final_pos)
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
            except ValueError: pass # Ignore if value_str is not a float during drag

    def seek_relative(self, offset_ms):
        if self.player and self._vlc_initialized and not self._vlc_released and self.player.is_seekable():
            curr_t = self.player.get_time()
            vid_l = self.player.get_length()
            
            new_t = curr_t + offset_ms
            if vid_l > 0: # Ensure new_t is within bounds if length is known
                new_t = max(0, min(vid_l, new_t))
            else: # If length is not known, just ensure it's not negative
                new_t = max(0, new_t)
                
            self.player.set_time(new_t)

            # Update UI immediately after setting time
            if self.winfo_exists():
                self.current_time_label.config(text=self._format_time(new_t))
                if vid_l > 0:
                    ratio = float(new_t) / vid_l
                    if 0.0 <= ratio <= 1.0:
                        self.seekbar_var.set(ratio)
                # Also update play/pause button state as seeking might affect it
                self.play_pause_button.config(text="Pause" if self.player.is_playing() else "Play")


    def set_playback_rate(self, rate): 
        if self.player and self._vlc_initialized and not self._vlc_released: self.player.set_rate(rate)

    def _on_video_frame_map(self, event): 
        if self.winfo_ismapped(): # Ensure it's actually mapped
            self._setup_vlc_output()

    def _on_video_frame_configure(self, event):
        # This can be called frequently. Only setup output if necessary.
        if self.winfo_ismapped() and not self._vlc_output_set:
            self._setup_vlc_output()

    def _setup_vlc_output(self):
        if not self.winfo_exists() or not self._vlc_initialized or self._vlc_released or not self.player:
            return
        if self._vlc_output_set: # Already set up
             return
        try:
            self.update_idletasks() # Ensure winfo_id is current
            hwnd = self.video_frame.winfo_id() 
            # Frame width/height might be 1 initially, wait for proper configure
            w, h = self.video_frame.winfo_width(), self.video_frame.winfo_height()

            if hwnd and w > 1 and h > 1 : 
                if sys.platform == "win32":
                    self.player.set_hwnd(hwnd)
                else: # Linux, macOS
                    self.player.set_xwindow(hwnd) 
                self._vlc_output_set = True
                
                # If media was loaded but couldn't play because output wasn't set, try playing now.
                current_media = self.player.get_media()
                if current_media and not self.player.is_playing():
                    state = self.player.get_state()
                    # Play if stopped, new, or ended. Don't interfere if paused by user.
                    if state in [vlc.State.NothingSpecial, vlc.State.Opening, vlc.State.Buffering, vlc.State.Ended, vlc.State.Error, vlc.State.Stopped]:
                        self.player.play()
        except Exception as e:
            self._vlc_output_set = False
            print(f"VLC HWND/XWindow assignment error: {e}")

    def load_and_play_video(self):
        if not self._vlc_initialized or self._vlc_released or not self.player: return
        
        if not self.video_paths or not (0 <= self.current_video_index < len(self.video_paths)):
            self.destroy_safely() # No videos left or invalid index
            return 
        
        if self.winfo_exists(): # Reset UI for new video
            self.seekbar_var.set(0.0)
            self.current_time_label.config(text="00:00")
            self.total_time_label.config(text="00:00")
            self.play_pause_button.config(text="Play")
        
        path = self.video_paths[self.current_video_index]
        
        if not os.path.exists(path):
            messagebox.showwarning("File Not Found", f"Video file not found:\n{path}", parent=self)
            self.video_paths.pop(self.current_video_index) # Remove missing file
            if not self.video_paths:
                self.destroy_safely()
                return
            # Adjust index if last item was removed
            self.current_video_index = min(self.current_video_index, len(self.video_paths) - 1) 
            self.load_and_play_video() # Try loading the (new) current video
            return 
            
        self.title(f"Video Viewer - {os.path.basename(path)}")
        
        try:
            media = self.instance.media_new(path) 
            if not media:
                print(f"Failed to create VLC media object for: {path}")
                messagebox.showerror("VLC Error", f"Could not load media: {os.path.basename(path)}", parent=self)
                return
            
            self.player.set_media(media)
            media.release() # Media is now owned by player
            
            # Crucial: VLC output might not be set yet if video_frame wasn't mapped.
            # _setup_vlc_output (called on <Map>) will handle playing if output is ready.
            # If output is already set (e.g., navigating videos), play directly.
            if self._vlc_output_set:
                self.player.play()
            else:
                # Output not set, _on_video_frame_map will trigger play when ready
                pass

        except Exception as e:
            messagebox.showerror("VLC Playback Error", f"Error playing {os.path.basename(path)}:\n{e}", parent=self)
        
        if self.winfo_exists():
            self.update_nav_buttons_state()

    def show_prev_video(self):
        if self._vlc_initialized and not self._vlc_released and self.player and self.current_video_index > 0:
            if self.player.is_playing(): self.player.stop() 
            self.current_video_index -= 1
            self._vlc_output_set = False # Force re-check of output for new video context
            self.load_and_play_video()

    def show_next_video(self):
        if self._vlc_initialized and not self._vlc_released and self.player and self.current_video_index < len(self.video_paths) - 1:
            if self.player.is_playing(): self.player.stop()
            self.current_video_index += 1
            self._vlc_output_set = False
            self.load_and_play_video()

    def toggle_play_pause(self):
        if self._vlc_initialized and not self._vlc_released and self.player: 
            if self.player.get_media(): # Only toggle if media is loaded
                if self.player.is_playing():
                    self.player.pause()
                    if self.winfo_exists(): self.play_pause_button.config(text="Play")
                else:
                    self.player.play()
                    if self.winfo_exists(): self.play_pause_button.config(text="Pause")

    def delete_current_video(self): 
        if not self._vlc_initialized or self._vlc_released or not self.player or \
           not self.video_paths or not (0 <= self.current_video_index < len(self.video_paths)):
            return
        
        path_del = self.video_paths[self.current_video_index]
        
        was_playing = self.player.is_playing()
        if was_playing: self.player.stop() 
        
        # Important: Release media from player *before* deleting the file
        self.player.set_media(None) 
        
       # Corrected method name from delete_selected_items_action to delete_selected_items_action_entry
        deleted_successfully = self.main_app.delete_selected_items_action_entry(
            items_to_delete_override={path_del},
            from_viewer=True
        )

        
        if deleted_successfully:
            self.items_deleted_from_viewer = True 
            original_len = len(self.video_paths)
            self.video_paths.pop(self.current_video_index)
            
            if not self.video_paths: # No videos left
                self.destroy_safely()
                return

            # Adjust index: if last item deleted, move to new last. Otherwise, stay at current (new video).
            if self.current_video_index >= len(self.video_paths) and len(self.video_paths) > 0 :
                 self.current_video_index = len(self.video_paths) - 1
            
            self._vlc_output_set = False # Reset for next video load
            self.load_and_play_video()
        else: # Deletion failed, try to reload the video if it still exists
            if os.path.exists(path_del):
                self._vlc_output_set = False
                self.load_and_play_video()
                if was_playing and self.player.get_media():
                    self.player.play() # Try to resume playback
            else: # File is gone but not through our mechanism - treat as if deleted
                self.items_deleted_from_viewer = True # Assume it's effectively gone
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
        # This method ensures destroy is called, which then handles VLC cleanup.
        if self.winfo_exists():
            self.destroy()

    def destroy(self):
        # print("VideoViewerWindow: destroy() called")
        if self._vlc_released: # Prevent double execution
            # print("VideoViewerWindow: Already released, returning.")
            if self.winfo_exists(): super().destroy() # Still destroy Tk window if not done
            return
        self._vlc_released = True

        # 1. Cancel any pending 'after' jobs
        if self._update_after_id:
            self.after_cancel(self._update_after_id)
            self._update_after_id = None
            # print("VideoViewerWindow: Cancelled _update_ui_loop")

        # 2. Stop and detach player from window (if initialized and player exists)
        if self._vlc_initialized and self.player:
            try:
                if self.player.is_playing():
                    self.player.stop()
                    # print("VideoViewerWindow: Player stopped.")
                
                # Detach from window handle - CRITICAL
                if self._vlc_output_set: # Only if it was set
                    if sys.platform == "win32":
                        self.player.set_hwnd(None)
                    else:
                        self.player.set_xwindow(0) # Use 0 for detaching on X systems
                    # print("VideoViewerWindow: Player detached from HWND/XWindow.")
                    self._vlc_output_set = False # Mark as detached
            except Exception as e:
                print(f"VideoViewerWindow: Error stopping/detaching player: {e}")

        # 3. Detach VLC events (if event manager exists)
        if self._vlc_initialized and self.vlc_event_manager:
            try: 
                self.vlc_event_manager.event_detach(vlc.EventType.MediaPlayerPositionChanged)
                self.vlc_event_manager.event_detach(vlc.EventType.MediaPlayerLengthChanged)
                self.vlc_event_manager.event_detach(vlc.EventType.MediaPlayerEndReached)
                # print("VideoViewerWindow: VLC events detached.")
            except Exception as e:
                print(f"VideoViewerWindow: Error detaching VLC events: {e}")
        
        # 4. Release VLC player (if exists)
        if self._vlc_initialized and self.player:
            try:
                # Ensure media is cleared from player before releasing player
                # This can sometimes help with stubborn crashes.
                current_media = self.player.get_media()
                if current_media:
                    self.player.set_media(None)
                    # print("VideoViewerWindow: Media cleared from player.")
                
                self.player.release()
                # print("VideoViewerWindow: Player released.")
            except Exception as e:
                print(f"VideoViewerWindow: Error releasing VLC player: {e}")
            self.player = None 
        
        # 5. Release VLC instance (if exists)
        if self._vlc_initialized and self.instance:
            try:
                self.instance.release()
                # print("VideoViewerWindow: Instance released.")
            except Exception as e:
                print(f"VideoViewerWindow: Error releasing VLC instance: {e}")
            self.instance = None
        
        # print("VideoViewerWindow: VLC cleanup complete.")

        # 6. Update main application (if it exists)
        if hasattr(self, 'main_app') and self.main_app and self.main_app.root.winfo_exists():
            if self.items_deleted_from_viewer: 
                current_f = self.main_app.current_folder.get()
                if isinstance(current_f, str) and os.path.isdir(current_f): 
                    self.main_app.load_items(current_f) 
            else:
                self.main_app.update_ui_state() 
        
        # 7. Destroy the Tkinter window
        if self.winfo_exists(): 
            # print("VideoViewerWindow: Calling super().destroy()")
            super().destroy()
        # print("VideoViewerWindow: destroy() finished.")