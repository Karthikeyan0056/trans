import threading
import time
import tkinter as tk
import os
import json
import sys
import platform
import ctypes
import urllib.request
import urllib.error

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import keyboard as kb
    HAS_KB = True
except ImportError:
    HAS_KB = False

CLIP_ICON_B64 = "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAYElEQVR4nGNgoBAwYhU9k/Yfq7jJLAz1LDiNNlZC5Z+9h1UZEwOFgIUop6PLI3mFBavTQc7F5mSYHE4X4PI/HsCCTZBXqB+r4s/vCokz4DMWhaMuwA2onBJBAEeapxkAAKPOIgT85dQVAAAAAElFTkSuQmCC"
# Public relay URL (Render.com - free forever)
RELAY_URL = "https://clipboard-relay-ra48.onrender.com"
RELAY_POLL_SECONDS = 0.5
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receiver_config.json")

BG = "#0d1117"
FG = "#00ff88"
MUTED = "#8b949e"
BORDER = "#30363d"
FONT_FAM = "Consolas" if platform.system() == "Windows" else "Menlo"
FONT = (FONT_FAM, 11)
SMALL_FONT = (FONT_FAM, 9)


def enable_acrylic(hwnd):
    try:
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.c_int(2), ctypes.sizeof(ctypes.c_int))
        return True
    except Exception:
        pass
    try:
        class ACCENTPOLICY(ctypes.Structure):
            _fields_ = [("AccentState", ctypes.c_uint), ("AccentFlags", ctypes.c_uint),
                        ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_uint)]
        class WINCOMPATTR(ctypes.Structure):
            _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.POINTER(ACCENTPOLICY)),
                        ("SizeOfData", ctypes.c_size_t)]
        accent = ACCENTPOLICY(AccentState=3, AccentFlags=0x20, GradientColor=0xCC0D1117, AnimationId=0)
        attr = WINCOMPATTR(Attribute=19, Data=ctypes.pointer(accent), SizeOfData=ctypes.sizeof(accent))
        ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(attr))
        return True
    except Exception:
        pass
    return False


class ClipboardReceiver:
    def __init__(self, relay_url=RELAY_URL, room=""):
        self.relay_url = relay_url
        self.room = room
        self.running = True
        self._last_ts = 0.0
        self._last_text = ""
        self._locked = False
        self._maximized = False
        self._min_w = 280
        self._min_h = 150
        self._normal_geo = None
        self._transparency = 75
        self._step_dir = None
        self.STEP_PX = 50
        self._init_w = 320
        self._init_h = 510

        self.root = tk.Tk()
        self.root.title("")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.75)
        self.root.configure(bg=BG)
        if platform.system() == "Windows":
            self.root.after(100, lambda: enable_acrylic(self.root.winfo_id()))
        sw_ = self.root.winfo_screenwidth()
        sh_ = self.root.winfo_screenheight()
        self.root.geometry(f"{self._init_w}x{self._init_h}+{(sw_ - self._init_w) // 2}+{(sh_ - self._init_h) // 2}")

        self._drag_data = {"x": 0, "y": 0}
        self._resize_data = {"x": 0, "y": 0, "w": 0, "h": 0}
        self._resize_edge = None
        self.RESIZE_MARGIN = 6

        self.root.bind('<Button-1>', self._on_click)
        self.root.bind('<B1-Motion>', self._on_drag)
        self.root.bind('<ButtonRelease-1>', self._on_release)
        self.root.bind('<Motion>', self._on_motion)

        self._build_ui()
        self.root.update_idletasks()
        self.root.update()

        if HAS_KB:
            kb.add_hotkey('ctrl+shift+z', self._toggle_visibility)
            kb.add_hotkey('ctrl+shift+up', self._move_top_center)
            kb.add_hotkey('ctrl+shift+left', lambda: self._top_step('left'))
            kb.add_hotkey('ctrl+shift+right', lambda: self._top_step('right'))

        if self.room:
            self._save_config()
            self._set_status(f"Room: {room} \u2713", FG)
            threading.Thread(target=self._poll_loop, daemon=True).start()
        else:
            self.root.after(100, self._prompt_for_code)

        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    def _prompt_for_code(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("")
        dlg.overrideredirect(True)
        dlg.attributes('-topmost', True)
        dlg.configure(bg=BG)
        dlg.geometry("420x200+280+280")

        outer = tk.Frame(dlg, bg=BORDER)
        outer.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        main = tk.Frame(outer, bg=BG)
        main.pack(fill=tk.BOTH, expand=True)

        hdr = tk.Frame(main, bg=BG)
        hdr.pack(fill=tk.X, padx=8, pady=(6, 0))

        tk.Label(hdr, text="Clipboard Receiver", bg=BG, fg=FG,
                 font=(FONT_FAM, 14, "bold")).pack(side=tk.LEFT)

        dlg_close_btn = tk.Label(hdr, text="\u2716", bg=BG, fg="#ff6b6b",
                                 font=(FONT_FAM, 12), cursor="hand2", padx=6)
        dlg_close_btn.pack(side=tk.RIGHT)
        dlg_close_btn.bind('<Button-1>', lambda e: dlg.destroy())

        body = tk.Frame(main, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(4, 12))

        tk.Label(body, text="Enter the pairing code from the Sender:", bg=BG, fg=MUTED,
                 font=SMALL_FONT).pack()

        entry = tk.Entry(body, bg="#161b22", fg="#e6edf3", font=(FONT_FAM, 20, "bold"),
                          insertbackground="#e6edf3", relief=tk.FLAT, bd=6, justify=tk.CENTER,
                          highlightthickness=1, highlightcolor=BORDER, highlightbackground=BORDER)
        entry.pack(fill=tk.X, ipady=8, pady=8)

        err_lbl = tk.Label(body, text="", bg=BG, fg="#ff6b6b", font=SMALL_FONT)
        err_lbl.pack()

        def connect():
            code = entry.get().strip().upper()
            if not code:
                err_lbl.config(text="Please enter the code")
                return
            self.room = code
            self._save_config()
            dlg.destroy()
            self._set_status(f"Room: {code} \u2713", FG)
            threading.Thread(target=self._poll_loop, daemon=True).start()

        tk.Button(body, text="CONNECT", bg="#238636", fg="white",
                  font=(FONT_FAM, 10, "bold"), relief=tk.FLAT,
                  activebackground="#2ea043", cursor="hand2",
                  command=connect).pack(pady=(4, 0))

        entry.bind('<Return>', lambda e: connect())
        entry.focus_force()
        dlg.grab_set()

    def _build_ui(self):
        self._icon_img = None
        if HAS_PIL:
            try:
                import base64, io
                data = base64.b64decode(CLIP_ICON_B64)
                pil = Image.open(io.BytesIO(data))
                self._icon_img = ImageTk.PhotoImage(pil)
            except Exception:
                pass

        outer = tk.Frame(self.root, bg=BORDER)
        outer.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        main = tk.Frame(outer, bg=BG)
        main.pack(fill=tk.BOTH, expand=True)

        hdr = tk.Frame(main, bg=BG, height=28)
        hdr.pack(fill=tk.X, padx=0, pady=(0, 0))
        hdr.pack_propagate(False)

        icon_label = tk.Label(hdr, image=self._icon_img, bg=BG, cursor="hand2") if self._icon_img else \
                     tk.Label(hdr, text="\u25C9", bg=BG, fg=FG, font=(FONT_FAM, 12), cursor="hand2")
        icon_label.pack(side=tk.LEFT, padx=(6, 2))

        self._lock_btn = tk.Label(hdr, text="\u25C9", bg=BG, fg=MUTED,
                                  font=(FONT_FAM, 8), cursor="hand2")
        self._lock_btn.pack(side=tk.LEFT, padx=(8, 2))
        self._lock_btn.bind('<Button-1>', lambda e: self._toggle_lock())

        tk.Label(hdr, text="Clipboard Receiver", bg=BG, fg=FG,
                 font=(FONT_FAM, 10, "bold")).pack(side=tk.LEFT, padx=(2, 6))

        self._status = tk.Label(hdr, text="Enter pairing code", bg=BG, fg=MUTED, font=SMALL_FONT)
        self._status.pack(side=tk.LEFT)

        btn_frame = tk.Frame(hdr, bg=BG)
        btn_frame.pack(side=tk.RIGHT, padx=(0, 6))

        min_btn = tk.Label(btn_frame, text="\u2014", bg=BG, fg=MUTED,
                           font=(FONT_FAM, 11), cursor="hand2", width=2)
        min_btn.pack(side=tk.LEFT)
        min_btn.bind('<Button-1>', lambda e: self._toggle_visibility())

        self._max_btn = tk.Label(btn_frame, text="\u25A1", bg=BG, fg=MUTED,
                                 font=(FONT_FAM, 10), cursor="hand2", width=2)
        self._max_btn.pack(side=tk.LEFT)
        self._max_btn.bind('<Button-1>', lambda e: self._toggle_maximize())

        close_btn = tk.Label(btn_frame, text="\u2716", bg=BG, fg="#ff6b6b",
                             font=(FONT_FAM, 10), cursor="hand2", width=2)
        close_btn.pack(side=tk.LEFT)
        close_btn.bind('<Button-1>', lambda e: self._quit())

        tk.Frame(main, bg=BORDER, height=1).pack(fill=tk.X, padx=0, pady=0)

        self._text = tk.Text(main, bg="#161b22", fg="#e6edf3", font=FONT,
                              wrap=tk.WORD, highlightthickness=0, borderwidth=0,
                              padx=8, pady=8, relief=tk.FLAT, state=tk.DISABLED)
        self._text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))

        bot_bar = tk.Frame(main, bg=BG, height=22)
        bot_bar.pack(fill=tk.X, padx=8, pady=(2, 4))
        bot_bar.pack_propagate(False)

        self._size_label = tk.Label(bot_bar, text=f"{self._init_w}\u00d7{self._init_h}",
                                     bg=BG, fg=MUTED, font=SMALL_FONT)
        self._size_label.pack(side=tk.LEFT)

        tk.Label(bot_bar, text="Opacity:", bg=BG, fg=MUTED, font=SMALL_FONT).pack(side=tk.LEFT, padx=(12, 2))
        self._alpha_slider = tk.Scale(bot_bar, from_=10, to=100, orient=tk.HORIZONTAL,
                                       bg=BG, fg=FG, highlightthickness=0, borderwidth=0,
                                       length=80, font=SMALL_FONT, troughcolor="#161b22",
                                       activebackground=FG, showvalue=0)
        self._alpha_slider.set(75)
        self._alpha_slider.pack(side=tk.LEFT, padx=(0, 2))
        self._alpha_slider.bind('<Motion>', self._on_alpha_change)
        self._alpha_slider.bind('<ButtonRelease-1>', self._on_alpha_change)
        self._alpha_label = tk.Label(bot_bar, text="75%", bg=BG, fg=MUTED, font=SMALL_FONT, width=4)
        self._alpha_label.pack(side=tk.LEFT)

    def _on_alpha_change(self, event=None):
        val = self._alpha_slider.get()
        self._transparency = val
        self.root.attributes('-alpha', val / 100.0)
        self._alpha_label.config(text=f"{val}%")

    def _toggle_lock(self):
        self._locked = not self._locked
        self._lock_btn.config(text="\u25CE" if self._locked else "\u25C9", fg=FG if self._locked else MUTED)

    def _toggle_maximize(self):
        if self._maximized:
            if self._normal_geo:
                self.root.geometry(self._normal_geo)
            self._max_btn.config(text="\u25A1")
            self._maximized = False
        else:
            self._normal_geo = f"{self.root.winfo_width()}x{self.root.winfo_height()}+{self.root.winfo_x()}+{self.root.winfo_y()}"
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            w = int(sw * 0.7)
            h = int(sh * 0.7)
            x = (sw - w) // 2
            y = (sh - h) // 2
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self._max_btn.config(text="\u25B3")
            self._maximized = True
        self._size_label.config(text=f"{self.root.winfo_width()}\u00d7{self.root.winfo_height()}")

    def _get_resize_edge(self, x, y):
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        m = self.RESIZE_MARGIN
        on_left = x <= m
        on_right = x >= w - m
        on_top = y <= m
        on_bottom = y >= h - m
        if on_left and on_top: return "nw"
        if on_right and on_top: return "ne"
        if on_left and on_bottom: return "sw"
        if on_right and on_bottom: return "se"
        if on_left: return "w"
        if on_right: return "e"
        if on_top: return "n"
        if on_bottom: return "s"
        return None

    def _get_cursor(self, edge):
        return {"nw": "size_nw_se", "ne": "size_ne_sw", "sw": "size_ne_sw",
                "se": "size_nw_se", "n": "sb_v_double_arrow", "s": "sb_v_double_arrow",
                "w": "sb_h_double_arrow", "e": "sb_h_double_arrow"}.get(edge, "")

    def _on_motion(self, event):
        if not self._locked:
            edge = self._get_resize_edge(event.x, event.y)
            self.root.config(cursor=self._get_cursor(edge) if edge else "")

    def _on_click(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
        edge = self._get_resize_edge(event.x, event.y)
        if edge and not self._locked:
            self._resize_edge = edge
            self._resize_data["x"] = event.x_root
            self._resize_data["y"] = event.y_root
            self._resize_data["w"] = self.root.winfo_width()
            self._resize_data["h"] = self.root.winfo_height()
            self._resize_data["rx"] = self.root.winfo_x()
            self._resize_data["ry"] = self.root.winfo_y()
        else:
            self._resize_edge = None

    def _on_drag(self, event):
        if self._resize_edge and not self._locked:
            self._do_resize(event)
        elif not self._locked:
            self._do_drag(event)

    def _on_release(self, event):
        self._resize_edge = None
        if not self._maximized:
            self._size_label.config(text=f"{self.root.winfo_width()}\u00d7{self.root.winfo_height()}")

    def _do_drag(self, event):
        self.root.geometry(f"+{self.root.winfo_x() + event.x - self._drag_data['x']}"
                           f"+{self.root.winfo_y() + event.y - self._drag_data['y']}")

    def _do_resize(self, event):
        dx = event.x_root - self._resize_data["x"]
        dy = event.y_root - self._resize_data["y"]
        new_w = self._resize_data["w"]
        new_h = self._resize_data["h"]
        new_x = self._resize_data["rx"]
        new_y = self._resize_data["ry"]
        e = self._resize_edge
        if "e" in e: new_w = max(self._min_w, self._resize_data["w"] + dx)
        if "w" in e:
            new_w = max(self._min_w, self._resize_data["w"] - dx)
            if new_w > self._min_w: new_x = self._resize_data["rx"] + dx
        if "s" in e: new_h = max(self._min_h, self._resize_data["h"] + dy)
        if "n" in e:
            new_h = max(self._min_h, self._resize_data["h"] - dy)
            if new_h > self._min_h: new_y = self._resize_data["ry"] + dy
        self.root.geometry(f"{new_w}x{new_h}+{new_x}+{new_y}")

    def _toggle_visibility(self):
        if self.root.winfo_viewable():
            self.root.withdraw()
        else:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes('-topmost', True)
            if not self.room:
                self.root.after(200, self._prompt_for_code)

    # ------------------------------------------------------------------
    # Window positioning shortcuts
    # ------------------------------------------------------------------
    def _move_window(self, x, y):
        """Clamp (x,y) inside the screen and move the window there immediately."""
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h))
        self.root.geometry(f"+{x}+{y}")

    def _reset_step(self, d):
        """Disarm the 'second press = full move' state for direction d."""
        if self._step_dir == d:
            self._step_dir = None

    def _top_step(self, d):
        """First press steps 50px toward a top corner; same-direction next press goes fully there."""
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        if self._step_dir == d:
            # Already armed in this direction -> jump fully to the corner.
            x, y = (0, 0) if d == 'left' else (sw - w, 0)
            self._step_dir = None
        else:
            # Single step toward the requested top corner and arm the direction.
            cx = self.root.winfo_x()
            cy = self.root.winfo_y()
            x = cx - self.STEP_PX if d == 'left' else cx + self.STEP_PX
            y = cy - self.STEP_PX
            self._step_dir = d
            self.root.after(2000, lambda: self._reset_step(d))
        self._move_window(x, y)

    def _move_top_center(self):
        """Snap the window to the horizontal center at the top of the screen."""
        w = self.root.winfo_width()
        sw = self.root.winfo_screenwidth()
        self._step_dir = None
        self._move_window((sw - w) // 2, 0)

    def _set_status(self, text, color):
        self._status.config(text=text, fg=color)

    def _set_text(self, text):
        self._text.config(state=tk.NORMAL)
        self._text.delete(1.0, tk.END)
        self._text.insert(tk.END, text)
        self._text.config(state=tk.DISABLED)
        self._text.see(1.0)

    def _on_data(self, text):
        self._set_text(text)

    def _poll_loop(self):
        while self.running and self.room:
            url = f"{self.relay_url.rstrip('/')}/receive/{self.room}"
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read())
                    text = data.get("text", "")
                    if text and text != self._last_text:
                        self._last_text = text
                        self.root.after(0, self._set_status, f"Room {self.room} \u2713", FG)
                        self.root.after(0, self._on_data, text)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    self.root.after(0, self._set_status, f"Room {self.room}: no data yet", "#ffa500")
                else:
                    self.root.after(0, self._set_status, f"HTTP {e.code}", "#ff6b6b")
            except Exception:
                self.root.after(0, self._set_status, f"Waiting for room {self.room}...", "#ffa500")
            time.sleep(RELAY_POLL_SECONDS)

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({"relay_url": self.relay_url, "room": self.room}, f, indent=4)
        except Exception:
            pass

    def _quit(self):
        self.running = False
        if HAS_KB:
            try:
                kb.remove_all_hotkeys()
            except Exception:
                pass
        self.root.quit()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def print_help():
    print(__doc__)
    sys.exit(0)


if __name__ == "__main__":
    cfg = __import__("json").load(open(CONFIG_FILE)) if os.path.exists(CONFIG_FILE) else {}
    room = cfg.get("room", "")
    relay_url = cfg.get("relay_url", RELAY_URL)

    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print_help()

    for i, arg in enumerate(args):
        if arg == "--url" and i + 1 < len(args):
            relay_url = args[i + 1]
        if arg == "--room" and i + 1 < len(args):
            room = args[i + 1]

    app = ClipboardReceiver(relay_url=relay_url, room=room)
    app.run()
