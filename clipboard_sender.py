import threading
import time
import os
import json
import sys
import urllib.request
import urllib.error
import platform
import ctypes
import tkinter as tk
import random as _r
import win32clipboard
import win32con

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
PKG_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(PKG_DIR, "sender_config.json")

BG = "#0d1117"
FG = "#00ff88"
MUTED = "#8b949e"
BORDER = "#30363d"
FONT_FAM = "Consolas" if platform.system() == "Windows" else "Menlo"
FONT = (FONT_FAM, 11)
SMALL_FONT = (FONT_FAM, 9)

CLIPBOARD_POLL_MS = 150


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


def hide_from_taskbar(hwnd):
    try:
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00000080)
    except Exception:
        pass


def read_clipboard():
    for attempt in range(3):
        try:
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                    text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                    if text:
                        return text.strip()
                if win32clipboard.IsClipboardFormatAvailable(win32con.CF_TEXT):
                    text = win32clipboard.GetClipboardData(win32con.CF_TEXT)
                    if text:
                        if isinstance(text, bytes):
                            text = text.decode("utf-8", errors="replace")
                        return text.strip()
                return ""
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            time.sleep(0.01)
    return ""


class ClipboardSender:
    def __init__(self):
        self.running = True
        self.last_sent = ""
        self.last_clip = ""
        self.relay_url = RELAY_URL
        self.room_code = ""
        self._locked = False
        self._maximized = False
        self._normal_geo = None
        self._min_w = 300
        self._min_h = 200

        self.root = tk.Tk()
        self.root.title("")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg=BG)
        self.root.geometry("420x320+150+150")
        if platform.system() == "Windows":
            self.root.after(50, lambda: hide_from_taskbar(self.root.winfo_id()))
            self.root.after(100, lambda: enable_acrylic(self.root.winfo_id()))

        self._drag_data = {"x": 0, "y": 0}
        self._resize_data = {"x": 0, "y": 0, "w": 0, "h": 0}
        self._resize_edge = None
        self.RESIZE_MARGIN = 6

        self.root.bind('<Button-1>', self._on_click)
        self.root.bind('<B1-Motion>', self._on_drag)
        self.root.bind('<ButtonRelease-1>', self._on_release)
        self.root.bind('<Motion>', self._on_motion)

        self._build_code_ui()
        self._build_input_window()

        if HAS_KB:
            kb.add_hotkey('ctrl+shift+z', self._hotkey_toggle)

    def _hotkey_toggle(self):
        target = getattr(self, '_input_win', None)
        if target is not None:
            if target.winfo_viewable():
                target.withdraw()
            else:
                target.deiconify()
                target.lift()
                target.attributes('-topmost', True)
        elif self.root.winfo_viewable():
            self.root.withdraw()
        else:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes('-topmost', True)

    def _build_code_ui(self):
        outer = tk.Frame(self.root, bg=BORDER)
        outer.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        main = tk.Frame(outer, bg=BG)
        main.pack(fill=tk.BOTH, expand=True)

        hdr = tk.Frame(main, bg=BG, height=28)
        hdr.pack(fill=tk.X, padx=0, pady=(0, 0))
        hdr.pack_propagate(False)

        self._lock_btn = tk.Label(hdr, text="\u25C9", bg=BG, fg=MUTED,
                                  font=(FONT_FAM, 10), cursor="hand2")
        self._lock_btn.pack(side=tk.LEFT, padx=(8, 2))
        self._lock_btn.bind('<Button-1>', lambda e: self._toggle_lock())

        tk.Label(hdr, text="Clipboard Sender", bg=BG, fg=FG,
                 font=(FONT_FAM, 10, "bold")).pack(side=tk.LEFT, padx=(2, 6))

        self._status = tk.Label(hdr, text="Idle", bg=BG, fg=MUTED, font=SMALL_FONT)
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
        close_btn.bind('<Button-1>', lambda e: self._confirm_close())

        tk.Frame(main, bg=BORDER, height=1).pack(fill=tk.X, padx=0, pady=0)

        self._gen_btn = tk.Button(main, text="GENERATE CODE", bg="#238636", fg="white",
                                  font=(FONT_FAM, 11, "bold"), relief=tk.FLAT,
                                  activebackground="#2ea043", cursor="hand2",
                                  command=self._generate_code)
        self._gen_btn.pack(fill=tk.X, padx=12, ipady=8, pady=(12, 6))

        code_f = tk.Frame(main, bg=BORDER)
        code_f.pack(fill=tk.X, padx=12)
        self._code_label = tk.Label(code_f, text="[ Press GENERATE ]", bg="#161b22", fg=MUTED,
                                    font=(FONT_FAM, 20, "bold"), anchor=tk.CENTER, height=2)
        self._code_label.pack(fill=tk.X, padx=1, pady=1)

        cfgi = self._load_config()
        if cfgi and cfgi.get("relay_url"):
            self.relay_url = cfgi["relay_url"]

        rl = tk.Frame(main, bg=BG)
        rl.pack(fill=tk.X, padx=12, pady=(4, 2))
        tk.Label(rl, text="Relay:", bg=BG, fg=MUTED, font=SMALL_FONT).pack(anchor=tk.W)
        self._relay_entry = tk.Entry(rl, bg="#161b22", fg="#e6edf3", font=(FONT_FAM, 9),
                                     insertbackground="#e6edf3", relief=tk.FLAT, bd=5,
                                     highlightthickness=1, highlightcolor=BORDER, highlightbackground=BORDER)
        self._relay_entry.insert(0, self.relay_url)
        self._relay_entry.pack(fill=tk.X, ipady=3)
        self._relay_entry.bind('<FocusOut>', self._on_relay_change)

        bot_bar = tk.Frame(main, bg=BG, height=22)
        bot_bar.pack(fill=tk.X, padx=8, pady=(6, 2))
        bot_bar.pack_propagate(False)

        self._size_label = tk.Label(bot_bar, text="420x320", bg=BG, fg=MUTED, font=SMALL_FONT)
        self._size_label.pack(side=tk.LEFT)

        tk.Label(bot_bar, text="Opacity:", bg=BG, fg=MUTED, font=SMALL_FONT).pack(side=tk.LEFT, padx=(12, 2))
        self._alpha_slider = tk.Scale(bot_bar, from_=10, to=100, orient=tk.HORIZONTAL,
                                       bg=BG, fg=FG, highlightthickness=0, borderwidth=0,
                                       length=70, font=SMALL_FONT, troughcolor="#161b22",
                                       activebackground=FG, showvalue=0)
        self._alpha_slider.set(100)
        self._alpha_slider.pack(side=tk.LEFT, padx=(0, 2))
        self._alpha_slider.bind('<ButtonRelease-1>', self._on_alpha_change)
        self._alpha_label = tk.Label(bot_bar, text="100%", bg=BG, fg=MUTED, font=SMALL_FONT, width=4)
        self._alpha_label.pack(side=tk.LEFT)

        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    def _build_input_window(self):
        win = tk.Toplevel(self.root)
        win.title("")
        win.overrideredirect(True)
        win.attributes('-topmost', True)
        win.configure(bg=BG)
        win.geometry("420x280+580+200")
        win.withdraw()
        if platform.system() == "Windows":
            win.after(50, lambda: hide_from_taskbar(win.winfo_id()))
            win.after(100, lambda: enable_acrylic(win.winfo_id()))

        self._inp_icon_img = None
        if HAS_PIL:
            try:
                import base64, io
                data = base64.b64decode(CLIP_ICON_B64)
                pil = Image.open(io.BytesIO(data))
                self._inp_icon_img = ImageTk.PhotoImage(pil)
            except Exception:
                pass

        inp_drag = {"x": 0, "y": 0}
        inp_resize = {"x": 0, "y": 0, "w": 0, "h": 0, "rx": 0, "ry": 0, "edge": None}
        RESIZE_MARGIN = 6

        def get_edge(x, y):
            w = win.winfo_width(); h = win.winfo_height(); m = 6
            l = x <= m; r = x >= w - m; t = y <= m; b = y >= h - m
            if l and t: return "nw"
            if r and t: return "ne"
            if l and b: return "sw"
            if r and b: return "se"
            if l: return "w"
            if r: return "e"
            if t: return "n"
            if b: return "s"
            return None

        def cur(e):
            return {"nw":"size_nw_se","ne":"size_ne_sw","sw":"size_ne_sw","se":"size_nw_se",
                    "n":"sb_v_double_arrow","s":"sb_v_double_arrow",
                    "w":"sb_h_double_arrow","e":"sb_h_double_arrow"}.get(e, "")

        def on_motion(e):
            ed = get_edge(e.x, e.y)
            win.config(cursor=cur(ed) if ed else "")

        def on_click(e):
            inp_drag["x"], inp_drag["y"] = e.x, e.y
            ed = get_edge(e.x, e.y)
            if ed:
                inp_resize["edge"] = ed
                inp_resize["x"] = e.x_root
                inp_resize["y"] = e.y_root
                inp_resize["w"] = win.winfo_width()
                inp_resize["h"] = win.winfo_height()
                inp_resize["rx"] = win.winfo_x()
                inp_resize["ry"] = win.winfo_y()
            else:
                inp_resize["edge"] = None

        def on_drag(e):
            if inp_resize["edge"]:
                dx = e.x_root - inp_resize["x"]
                dy = e.y_root - inp_resize["y"]
                nw, nh = inp_resize["w"], inp_resize["h"]
                nx, ny = inp_resize["rx"], inp_resize["ry"]
                ed = inp_resize["edge"]
                if "e" in ed: nw = max(280, inp_resize["w"] + dx)
                if "w" in ed:
                    nw = max(280, inp_resize["w"] - dx)
                    if nw > 280: nx = inp_resize["rx"] + dx
                if "s" in ed: nh = max(150, inp_resize["h"] + dy)
                if "n" in ed:
                    nh = max(150, inp_resize["h"] - dy)
                    if nh > 150: ny = inp_resize["ry"] + dy
                win.geometry(f"{nw}x{nh}+{nx}+{ny}")
            else:
                win.geometry(f"+{win.winfo_x()+e.x-inp_drag['x']}+{win.winfo_y()+e.y-inp_drag['y']}")

        def on_release(e):
            inp_resize["edge"] = None
            if hasattr(self, '_inp_size_label'):
                self._inp_size_label.config(text=f"{win.winfo_width()}x{win.winfo_height()}")

        win.bind('<Motion>', on_motion)
        win.bind('<Button-1>', on_click)
        win.bind('<B1-Motion>', on_drag)
        win.bind('<ButtonRelease-1>', on_release)
        win.bind('<Escape>', lambda e: win.withdraw())

        outer = tk.Frame(win, bg=BORDER)
        outer.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        main = tk.Frame(outer, bg=BG)
        main.pack(fill=tk.BOTH, expand=True)

        hdr = tk.Frame(main, bg=BG, height=24)
        hdr.pack(fill=tk.X, padx=0, pady=(0, 0))
        hdr.pack_propagate(False)

        icon_label = tk.Label(hdr, image=self._inp_icon_img, bg=BG) if self._inp_icon_img else \
                     tk.Label(hdr, text="\u25C9", bg=BG, fg=FG, font=(FONT_FAM, 12))
        icon_label.pack(side=tk.LEFT, padx=(6, 4))

        self._inp_room_label = tk.Label(hdr, text="Notepad", bg=BG, fg=MUTED, font=SMALL_FONT)
        self._inp_room_label.pack(side=tk.LEFT)

        inp_btnf = tk.Frame(hdr, bg=BG)
        inp_btnf.pack(side=tk.RIGHT, padx=(0, 6))

        newcode_btn = tk.Label(inp_btnf, text="\u21BB NEW CODE", bg=BG, fg=FG,
                               font=SMALL_FONT, cursor="hand2", padx=6)
        newcode_btn.pack(side=tk.LEFT)
        newcode_btn.bind('<Button-1>', lambda e: self._generate_code())

        inp_close_btn = tk.Label(inp_btnf, text="\u2716", bg=BG, fg="#ff6b6b",
                                 font=(FONT_FAM, 10), cursor="hand2", padx=4)
        inp_close_btn.pack(side=tk.LEFT)
        inp_close_btn.bind('<Button-1>', lambda e: self._confirm_close())

        tk.Frame(main, bg=BORDER, height=1).pack(fill=tk.X, padx=0, pady=0)

        self._input_text = tk.Text(main, bg="#161b22", fg="#e6edf3", font=FONT,
                                    wrap=tk.WORD, highlightthickness=0, borderwidth=0,
                                    padx=8, pady=8, relief=tk.FLAT, insertbackground="#e6edf3")
        self._input_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))
        self._input_text.bind('<KeyRelease>', self._on_typing)

        bot_bar = tk.Frame(main, bg=BG, height=18)
        bot_bar.pack(fill=tk.X, padx=8, pady=(0, 2))
        bot_bar.pack_propagate(False)

        self._inp_size_label = tk.Label(bot_bar, text="420x280", bg=BG, fg=MUTED, font=SMALL_FONT)
        self._inp_size_label.pack(side=tk.LEFT)

        tk.Label(bot_bar, text="Ctrl+C anywhere \u2192 auto-sends", bg=BG, fg=MUTED,
                 font=SMALL_FONT).pack(side=tk.RIGHT)

        grip = tk.Label(bot_bar, text="\u2923", bg=BG, fg=MUTED,
                        font=(FONT_FAM, 10), cursor="size_nw_se")
        grip.pack(side=tk.RIGHT, padx=(0, 1))
        grip_start = {"x": 0, "y": 0, "w": 0, "h": 0}

        def grip_down(e):
            grip_start["x"], grip_start["y"] = e.x_root, e.y_root
            grip_start["w"], grip_start["h"] = win.winfo_width(), win.winfo_height()

        def grip_move(e):
            nw = max(280, grip_start["w"] + (e.x_root - grip_start["x"]))
            nh = max(150, grip_start["h"] + (e.y_root - grip_start["y"]))
            win.geometry(f"{nw}x{nh}+{win.winfo_x()}+{win.winfo_y()}")
            self._inp_size_label.config(text=f"{nw}x{nh}")

        grip.bind('<Button-1>', grip_down)
        grip.bind('<B1-Motion>', grip_move)

        self._input_win = win

    def _load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({"relay_url": self.relay_url}, f, indent=4)
        except Exception:
            pass

    def _on_relay_change(self, event=None):
        raw = self._relay_entry.get().strip()
        if raw:
            if not raw.startswith("http://") and not raw.startswith("https://"):
                raw = "http://" + raw
            self.relay_url = raw
            self._save_config()

    def _generate_code(self):
        self._on_relay_change()
        self._status.config(text="Checking relay...", fg="#ffa500")
        self.root.update()
        code = "".join(_r.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=6))
        self.room_code = code
        self._code_label.config(text=f"  {code}  ", fg=FG, bg="#0d1117")
        self._gen_btn.config(text="RE-GENERATE")
        self._status.config(text=f"Room: {code}", fg=FG)
        self._inp_room_label.config(text=f"Room {code} \u2192", fg=FG)
        self.last_sent = ""
        self.last_clip = ""
        self._input_text.delete(1.0, tk.END)
        self._input_win.deiconify()
        self._input_win.lift()
        self._input_win.focus_force()
        self.root.withdraw()
        threading.Thread(target=self._clipboard_monitor, daemon=True).start()

    def _on_typing(self, event=None):
        text = self._input_text.get(1.0, tk.END).strip()
        if text and text != self.last_sent and self.room_code:
            self.last_sent = text
            self.last_clip = text
            threading.Thread(target=self._send, args=(text,), daemon=True).start()

    def _on_clipboard_change(self, text):
        if text and text != self.last_sent and self.room_code:
            self.last_sent = text
            self.last_clip = text
            self._input_text.delete(1.0, tk.END)
            self._input_text.insert(tk.END, text)
            self._input_text.see(1.0)
            threading.Thread(target=self._send, args=(text,), daemon=True).start()

    def _clipboard_monitor(self):
        seq = win32clipboard.GetClipboardSequenceNumber()
        while self.running:
            time.sleep(CLIPBOARD_POLL_MS / 1000.0)
            new_seq = win32clipboard.GetClipboardSequenceNumber()
            if new_seq != seq:
                seq = new_seq
                try:
                    text = read_clipboard()
                    if text:
                        self.root.after(0, self._on_clipboard_change, text)
                except Exception:
                    pass

    def _send(self, text):
        url = f"{self.relay_url.rstrip('/')}/send/{self.room_code}"
        body = json.dumps({"text": text}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if json.loads(resp.read()).get("status") == "ok":
                    self.root.after(0, lambda: self._status.config(text="Sent", fg=FG))
                else:
                    self.root.after(0, lambda: self._status.config(text="Failed", fg="#ff6b6b"))
        except urllib.error.HTTPError as e:
            self.root.after(0, lambda: self._status.config(text=f"HTTP {e.code}", fg="#ff6b6b"))
        except Exception:
            self.root.after(0, lambda: self._status.config(text="Relay unreachable", fg="#ff6b6b"))

    def _on_alpha_change(self, event=None):
        val = self._alpha_slider.get()
        self.root.attributes('-alpha', val / 100.0)
        self._alpha_label.config(text=f"{val}%")

    def _toggle_lock(self):
        self._locked = not self._locked
        self._lock_btn.config(text="\u25CE" if self._locked else "\u25C9",
                              fg=FG if self._locked else MUTED)

    def _toggle_visibility(self):
        if self.root.winfo_viewable():
            self.root.withdraw()
        else:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes('-topmost', True)

    def _confirm_close(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("")
        dlg.overrideredirect(True)
        dlg.attributes('-topmost', True)
        dlg.configure(bg=BG)
        dlg.geometry("360x160+300+300")

        outer = tk.Frame(dlg, bg=BORDER)
        outer.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        main = tk.Frame(outer, bg=BG)
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)

        tk.Label(main, text="Do you want to close?", bg=BG, fg="#e6edf3",
                 font=(FONT_FAM, 12, "bold")).pack(pady=(0, 12))

        btnf = tk.Frame(main, bg=BG)
        btnf.pack()

        def do_yes():
            dlg.destroy()
            self._quit()

        tk.Button(btnf, text="YES", bg="#238636", fg="white",
                  font=(FONT_FAM, 10, "bold"), relief=tk.FLAT, width=8,
                  activebackground="#2ea043", cursor="hand2",
                  command=do_yes).pack(side=tk.LEFT, padx=6)

        tk.Button(btnf, text="NO", bg="#21262d", fg="#e6edf3",
                  font=(FONT_FAM, 10, "bold"), relief=tk.FLAT, width=8,
                  activebackground="#30363d", cursor="hand2",
                  command=dlg.destroy).pack(side=tk.LEFT, padx=6)

        dlg.grab_set()
        dlg.focus_force()

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
            self.root.geometry(f"{int(sw*0.7)}x{int(sh*0.7)}+{(sw-int(sw*0.7))//2}+{(sh-int(sh*0.7))//2}")
            self._max_btn.config(text="\u25B3")
            self._maximized = True
        self._size_label.config(text=f"{self.root.winfo_width()}x{self.root.winfo_height()}")

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
            dx = event.x_root - self._resize_data["x"]
            dy = event.y_root - self._resize_data["y"]
            new_w, new_h = self._resize_data["w"], self._resize_data["h"]
            new_x, new_y = self._resize_data["rx"], self._resize_data["ry"]
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
        elif not self._locked:
            self.root.geometry(f"+{self.root.winfo_x()+event.x-self._drag_data['x']}"
                               f"+{self.root.winfo_y()+event.y-self._drag_data['y']}")

    def _on_release(self, event):
        self._resize_edge = None
        if not self._maximized:
            self._size_label.config(text=f"{self.root.winfo_width()}x{self.root.winfo_height()}")

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


if __name__ == "__main__":
    app = ClipboardSender()
    app.run()