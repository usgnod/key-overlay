"""
키 입력 표시기 (Windows)
------------------------
지금 누르고 있는 키를 화면 위에 반투명 키보드로 실시간 표시합니다.
다른 프로그램을 사용하는 중에도 항상 맨 위에 떠 있습니다.

필요한 것:  Python 3.8 이상,  pip install pynput

조작법
  - 왼쪽 버튼 드래그 : 창 이동
  - 마우스 휠         : 투명도 조절 (5%씩)
  - 오른쪽 클릭       : 메뉴 (설정, 크기, 투명도, 표시 옵션, 종료)

설정은 사용자 폴더의 .key_overlay.json 에 자동 저장됩니다.
이 프로그램은 키 입력을 화면에 보여주기만 하며, 어디에도 기록하거나 전송하지 않습니다.
"""

import ctypes
import json
import os
import queue
import sys
import time
import tkinter as tk
from tkinter import messagebox

IS_WINDOWS = sys.platform == "win32"

# 고해상도(배율 125%/150% 등) 화면에서 글자가 흐려지지 않도록 DPI 인식 설정
if IS_WINDOWS:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

try:
    from pynput import keyboard
except ImportError:
    _r = tk.Tk()
    _r.withdraw()
    messagebox.showerror(
        "키 입력 표시기",
        "pynput 라이브러리가 필요합니다.\n\n명령 프롬프트에서 다음을 실행하세요:\n\npip install pynput",
    )
    sys.exit(1)


# ─────────────────────────── 설정 ───────────────────────────

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".key_overlay.json")

SIZES = {"아주 작게": 18, "작게": 24, "보통": 34, "크게": 46, "아주 크게": 60}

DEFAULTS = {
    "opacity": 85,           # 20 ~ 100 (%)
    "size": "보통",
    "show_nav": True,        # 방향키/편집키 영역 표시
    "show_combo": True,      # 아래쪽에 "Ctrl + Shift + S" 같은 조합 텍스트 표시
    "transparent_bg": False, # 키 사이 배경을 완전히 투명하게
    "hold_seconds": 1.5,     # 키를 뗀 뒤 조합 텍스트를 유지할 시간
    "x": None,
    "y": None,
}

FONT = "Malgun Gothic"

COLORS = {
    "panel": "#18181c",
    "panel_outline": "#2e2e36",
    "key": "#2b2b33",
    "key_outline": "#44444f",
    "text": "#d6d6de",
    "pressed": "#38bdf8",
    "pressed_outline": "#bae6fd",
    "pressed_text": "#04121b",
    "combo_bg": "#0f0f12",
    "combo_text": "#ffffff",
}

# 이 색으로 칠한 부분은 완전히 투명해지고 클릭도 통과됩니다.
TRANSPARENT_KEY = "#000001"


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        for k in DEFAULTS:
            if k in saved:
                cfg[k] = saved[k]
    except Exception:
        pass
    if cfg["size"] not in SIZES:
        cfg["size"] = DEFAULTS["size"]
    try:
        cfg["opacity"] = max(20, min(100, int(cfg["opacity"])))
    except Exception:
        cfg["opacity"] = DEFAULTS["opacity"]
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ─────────────────────────── 키보드 배열 ───────────────────────────
# 각 항목: (표시 글자, 가상키코드 또는 코드 튜플, 너비[키 단위])
# 표시 글자가 None 이면 빈 칸(간격)입니다.

def _gap(w):
    return (None, None, w)


def _f(n):
    return (f"F{n}", 0x6F + n, 1)


def _chars(s):
    return [(c, ord(c), 1) for c in s]


MAIN_ROWS = [
    (0.0, [("Esc", 0x1B, 1), _gap(1), _f(1), _f(2), _f(3), _f(4), _gap(0.5),
           _f(5), _f(6), _f(7), _f(8), _gap(0.5), _f(9), _f(10), _f(11), _f(12)]),
    (1.5, [("`", 0xC0, 1)] + _chars("1234567890") +
          [("-", 0xBD, 1), ("=", 0xBB, 1), ("Backspace", 0x08, 2)]),
    (2.5, [("Tab", 0x09, 1.5)] + _chars("QWERTYUIOP") +
          [("[", 0xDB, 1), ("]", 0xDD, 1), ("\\", 0xDC, 1.5)]),
    (3.5, [("Caps", 0x14, 1.75)] + _chars("ASDFGHJKL") +
          [(";", 0xBA, 1), ("'", 0xDE, 1), ("Enter", 0x0D, 2.25)]),
    (4.5, [("Shift", 0xA0, 2.25)] + _chars("ZXCVBNM") +
          [(",", 0xBC, 1), (".", 0xBE, 1), ("/", 0xBF, 1), ("Shift", 0xA1, 2.75)]),
    (5.5, [("Ctrl", 0xA2, 1.25), ("Win", 0x5B, 1.25), ("Alt", 0xA4, 1.25),
           ("Space", 0x20, 6.25),
           ("한/영", (0x15, 0xA5), 1.25), ("Win", 0x5C, 1.25),
           ("Menu", 0x5D, 1.25), ("한자", (0x19, 0xA3), 1.25)]),
]

NAV_X = 15.25
NAV_ROWS = [
    (0.0, [("PrtSc", 0x2C, 1), ("ScrLk", 0x91, 1), ("Pause", 0x13, 1)]),
    (1.5, [("Ins", 0x2D, 1), ("Home", 0x24, 1), ("PgUp", 0x21, 1)]),
    (2.5, [("Del", 0x2E, 1), ("End", 0x23, 1), ("PgDn", 0x22, 1)]),
    (4.5, [_gap(1), ("↑", 0x26, 1)]),
    (5.5, [("←", 0x25, 1), ("↓", 0x28, 1), ("→", 0x27, 1)]),
]


def build_layout(show_nav):
    """[(label, (vk, ...), x, y, w, h), ...] 형태로 반환 (단위: 키 1칸)"""
    keys = []

    def add_rows(rows, x_start):
        for y, items in rows:
            x = x_start
            for label, vk, w in items:
                if label is not None:
                    vks = vk if isinstance(vk, tuple) else (vk,)
                    keys.append((label, vks, x, y, w, 1.0))
                x += w

    add_rows(MAIN_ROWS, 0.0)
    if show_nav:
        add_rows(NAV_ROWS, NAV_X)
    return keys


# 조합 텍스트에 쓸 이름
NAME_OVERRIDE = {
    0xA0: "Shift", 0xA1: "Shift", 0xA2: "Ctrl", 0xA3: "Ctrl",
    0xA4: "Alt", 0xA5: "Alt", 0x5B: "Win", 0x5C: "Win",
    0x15: "한/영", 0x19: "한자", 0x14: "CapsLock", 0x20: "Space",
    0x0D: "Enter", 0x08: "Backspace", 0x2C: "PrtSc", 0x5D: "Menu",
    0x90: "NumLock", 0x6A: "Num *", 0x6B: "Num +", 0x6D: "Num -",
    0x6E: "Num .", 0x6F: "Num /",
}
for _i in range(10):
    NAME_OVERRIDE[0x60 + _i] = f"Num {_i}"
for _i in range(13, 25):
    NAME_OVERRIDE[0x6F + _i] = f"F{_i}"

# 조합 텍스트에서 앞에 올 보조키 (순서대로)
MODIFIER_GROUPS = [
    ("Ctrl", {0xA2, 0xA3}),
    ("Shift", {0xA0, 0xA1}),
    ("Alt", {0xA4, 0xA5}),
    ("Win", {0x5B, 0x5C}),
]
MODIFIER_VKS = set().union(*(g for _, g in MODIFIER_GROUPS))

# pynput 이 좌/우 구분 없는 코드를 줄 때 왼쪽 키로 맞춤
VK_NORMALIZE = {0x10: 0xA0, 0x11: 0xA2, 0x12: 0xA4}


def vk_of(key):
    vk = None
    if isinstance(key, keyboard.Key):
        vk = getattr(key.value, "vk", None)
    else:
        vk = getattr(key, "vk", None)
        if vk is None:
            ch = getattr(key, "char", None)
            if ch and len(ch) == 1 and ch.isascii() and ch.isalnum():
                vk = ord(ch.upper())
    if vk is None:
        return None
    return VK_NORMALIZE.get(vk, vk)


def round_rect(canvas, x0, y0, x1, y1, r, **kw):
    r = max(0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return canvas.create_polygon(pts, smooth=True, **kw)


# ─────────────────────────── 메인 창 ───────────────────────────

class KeyOverlay:
    def __init__(self):
        self.cfg = load_config()
        self.events = queue.Queue()
        self.pressed = {}            # vk -> 누른 시각
        self.combo_text = ""
        self.combo_until = 0.0
        self.shown_combo = None
        self.key_items = []          # [(vks, rect_id, text_id, is_on)]
        self.vk_labels = {}
        self.settings_win = None
        self._save_job = None

        root = self.root = tk.Tk()
        root.title("키 입력 표시기")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", self.cfg["opacity"] / 100)
        try:
            root.attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError:
            pass
        self.dpi_scale = max(1.0, root.winfo_fpixels("1i") / 96.0)

        # 메뉴/설정창과 공유하는 값
        self.opacity_var = tk.IntVar(value=self.cfg["opacity"])
        self.size_var = tk.StringVar(value=self.cfg["size"])
        self.nav_var = tk.BooleanVar(value=self.cfg["show_nav"])
        self.combo_var = tk.BooleanVar(value=self.cfg["show_combo"])
        self.transp_var = tk.BooleanVar(value=self.cfg["transparent_bg"])

        self.canvas = tk.Canvas(root, highlightthickness=0, bd=0, bg=TRANSPARENT_KEY)
        self.canvas.pack()

        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)
        self.canvas.bind("<Button-3>", self._show_menu)
        self.canvas.bind("<MouseWheel>", self._wheel)

        self._build_menu()
        self.redraw()
        self._place_initial()
        self._make_no_activate()

        self.listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self.listener.daemon = True
        self.listener.start()

        self._stale_ticks = 0
        root.after(15, self._poll)
        root.after(300, self._check_stale)

    # ── 키 이벤트 (별도 스레드) → 큐 ──
    def _on_press(self, key):
        vk = vk_of(key)
        if vk is not None:
            self.events.put((vk, True))

    def _on_release(self, key):
        vk = vk_of(key)
        if vk is not None:
            self.events.put((vk, False))

    # ── 화면 갱신 (메인 스레드) ──
    def _poll(self):
        changed = False
        now = time.monotonic()
        while True:
            try:
                vk, down = self.events.get_nowait()
            except queue.Empty:
                break
            if down:
                if vk not in self.pressed:
                    self.pressed[vk] = now
                    self.combo_text = self._combo_for(vk)
                    changed = True
            else:
                if self.pressed.pop(vk, None) is not None:
                    changed = True
                if not self.pressed:
                    self.combo_until = now + float(self.cfg["hold_seconds"])
        if changed:
            self._update_highlight()
        self._update_combo(now)
        self.root.after(15, self._poll)

    def _name(self, vk):
        if vk in NAME_OVERRIDE:
            return NAME_OVERRIDE[vk]
        if vk in self.vk_labels:
            return self.vk_labels[vk]
        return f"0x{vk:02X}"

    def _combo_for(self, new_vk):
        names = [name for name, group in MODIFIER_GROUPS if group & self.pressed.keys()]
        if new_vk not in MODIFIER_VKS:
            names.append(self._name(new_vk))
        return " + ".join(names)

    def _update_highlight(self):
        down = self.pressed.keys()
        for i, (vks, rect, text, was_on) in enumerate(self.key_items):
            on = any(v in down for v in vks)
            if on != was_on:
                if on:
                    self.canvas.itemconfig(rect, fill=COLORS["pressed"], outline=COLORS["pressed_outline"])
                    self.canvas.itemconfig(text, fill=COLORS["pressed_text"])
                else:
                    self.canvas.itemconfig(rect, fill=COLORS["key"], outline=COLORS["key_outline"])
                    self.canvas.itemconfig(text, fill=COLORS["text"])
                self.key_items[i] = (vks, rect, text, on)

    def _update_combo(self, now):
        if not self.cfg["show_combo"]:
            return
        text = self.combo_text if (self.pressed or now < self.combo_until) else ""
        if text == self.shown_combo:
            return
        self.shown_combo = text
        c = self.canvas
        c.delete("combo")
        if not text:
            return
        cx, cy, h = self.combo_center
        t = c.create_text(cx, cy, text=text, fill=COLORS["combo_text"],
                          font=(FONT, -round(h * 0.5), "bold"), tags="combo")
        x0, y0, x1, y1 = c.bbox(t)
        padx = h * 0.45
        bg = round_rect(c, x0 - padx, cy - h / 2, x1 + padx, cy + h / 2, h * 0.3,
                        fill=COLORS["combo_bg"], outline=COLORS["panel_outline"], tags="combo")
        c.tag_lower(bg, t)

    def _check_stale(self):
        # 잠금화면(Win+L) 등으로 '뗌' 신호를 놓쳐 키가 눌린 채 남는 것을 방지
        if IS_WINDOWS and self.pressed:
            gas = ctypes.windll.user32.GetAsyncKeyState
            now = time.monotonic()
            stale = [vk for vk, t in self.pressed.items()
                     if now - t > 0.5 and not (gas(vk) & 0x8000)]
            if stale:
                for vk in stale:
                    self.pressed.pop(vk, None)
                if not self.pressed:
                    self.combo_until = now + float(self.cfg["hold_seconds"])
                self._update_highlight()
        self._stale_ticks += 1
        if self._stale_ticks % 10 == 0:
            # 다른 '항상 위' 창에 밀리지 않도록 주기적으로 다시 설정
            self.root.attributes("-topmost", True)
        self.root.after(300, self._check_stale)

    # ── 그리기 ──
    def redraw(self):
        c = self.canvas
        c.delete("all")
        self.key_items = []
        self.vk_labels = {}
        self.shown_combo = None

        unit = SIZES[self.cfg["size"]] * self.dpi_scale
        pad = unit * 0.35
        gap = max(2.0, unit * 0.09)
        layout = build_layout(self.cfg["show_nav"])
        max_x = max(x + w for _, _, x, _, w, _ in layout)
        max_y = max(y + h for _, _, _, y, _, h in layout)

        kb_w = max_x * unit
        kb_h = max_y * unit
        combo_h = unit * 1.1 if self.cfg["show_combo"] else 0
        W = round(kb_w + pad * 2)
        H = round(kb_h + pad * 2 + (combo_h + pad * 0.6 if combo_h else 0))
        c.config(width=W, height=H)

        if not self.cfg["transparent_bg"]:
            round_rect(c, 1, 1, W - 1, H - 1, unit * 0.4,
                       fill=COLORS["panel"], outline=COLORS["panel_outline"])

        base_font = unit * 0.36
        for label, vks, x, y, w, h in layout:
            x0 = pad + x * unit + gap / 2
            y0 = pad + y * unit + gap / 2
            x1 = pad + (x + w) * unit - gap / 2
            y1 = pad + (y + h) * unit - gap / 2
            rect = round_rect(c, x0, y0, x1, y1, unit * 0.16,
                              fill=COLORS["key"], outline=COLORS["key_outline"])
            # 긴 이름은 키 너비에 맞게 글자 크기를 줄임
            fit = (x1 - x0) * 0.82 / max(1, len(label) * 0.62)
            size = max(6, round(min(base_font, fit)))
            text = c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=label,
                                 fill=COLORS["text"], font=(FONT, -size))
            self.key_items.append((vks, rect, text, False))
            for v in vks:
                self.vk_labels.setdefault(v, label)

        if combo_h:
            self.combo_center = (W / 2, pad + kb_h + pad * 0.6 + combo_h / 2, combo_h)

        self.root.geometry(f"{W}x{H}")
        self._update_highlight()
        self._update_combo(time.monotonic())

    # ── 창 위치/이동 ──
    def _place_initial(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = self.cfg.get("x"), self.cfg.get("y")
        if not isinstance(x, int) or not isinstance(y, int) or not (-w < x < sw and 0 <= y < sh):
            x, y = sw - w - 40, sh - h - 90
        self.root.geometry(f"+{x}+{y}")

    def _reset_position(self):
        self.cfg["x"] = self.cfg["y"] = None
        self._place_initial()
        self._schedule_save()

    def _drag_start(self, e):
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _drag_end(self, e):
        self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
        self._schedule_save()

    def _wheel(self, e):
        step = 5 if e.delta > 0 else -5
        self.opacity_var.set(max(20, min(100, self.opacity_var.get() + step)))
        self.apply()

    def _make_no_activate(self):
        # 표시기를 클릭해도 작업 중인 프로그램에서 포커스를 빼앗지 않도록 설정
        if not IS_WINDOWS:
            return
        try:
            self.root.update_idletasks()
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOOLWINDOW = 0x00000080
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        except Exception:
            pass

    # ── 메뉴 / 설정 ──
    def _build_menu(self):
        m = self.menu = tk.Menu(self.root, tearoff=0)
        m.add_command(label="설정...", command=self.open_settings)
        m.add_separator()

        size_menu = tk.Menu(m, tearoff=0)
        for name in SIZES:
            size_menu.add_radiobutton(label=name, value=name, variable=self.size_var, command=self.apply)
        m.add_cascade(label="키보드 크기", menu=size_menu)

        op_menu = tk.Menu(m, tearoff=0)
        for p in range(100, 19, -10):
            op_menu.add_radiobutton(label=f"{p}%", value=p, variable=self.opacity_var, command=self.apply)
        m.add_cascade(label="불투명도", menu=op_menu)

        m.add_checkbutton(label="방향키/편집키 표시", variable=self.nav_var, command=self.apply)
        m.add_checkbutton(label="키 조합 텍스트 표시", variable=self.combo_var, command=self.apply)
        m.add_checkbutton(label="배경 완전 투명", variable=self.transp_var, command=self.apply)
        m.add_separator()
        m.add_command(label="위치 초기화", command=self._reset_position)
        m.add_command(label="종료", command=self.quit)

    def _show_menu(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def open_settings(self):
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.lift()
            return
        win = self.settings_win = tk.Toplevel(self.root)
        win.title("키 입력 표시기 설정")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        body = tk.Frame(win, padx=16, pady=12)
        body.pack()

        tk.Label(body, text="불투명도 (%)", font=(FONT, 10, "bold")).grid(row=0, column=0, sticky="w")
        tk.Scale(body, from_=20, to=100, resolution=5, orient="horizontal", length=260,
                 variable=self.opacity_var, command=lambda _v: self.apply()).grid(
            row=1, column=0, columnspan=3, sticky="we", pady=(0, 10))

        tk.Label(body, text="키보드 크기", font=(FONT, 10, "bold")).grid(row=2, column=0, sticky="w")
        sf = tk.Frame(body)
        sf.grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 10))
        for name in SIZES:
            tk.Radiobutton(sf, text=name, value=name, variable=self.size_var,
                           command=self.apply).pack(side="left", padx=(0, 6))

        tk.Label(body, text="표시 옵션", font=(FONT, 10, "bold")).grid(row=4, column=0, sticky="w")
        tk.Checkbutton(body, text="방향키/편집키 표시", variable=self.nav_var,
                       command=self.apply).grid(row=5, column=0, columnspan=3, sticky="w")
        tk.Checkbutton(body, text="키 조합 텍스트 표시 (예: Ctrl + Shift + S)", variable=self.combo_var,
                       command=self.apply).grid(row=6, column=0, columnspan=3, sticky="w")
        tk.Checkbutton(body, text="배경 완전 투명 (키만 보이게)", variable=self.transp_var,
                       command=self.apply).grid(row=7, column=0, columnspan=3, sticky="w")

        tk.Label(body, text="팁: 표시기 위에서 마우스 휠로도 불투명도를 바꿀 수 있어요.",
                 fg="#666").grid(row=8, column=0, columnspan=3, sticky="w", pady=(10, 4))
        tk.Button(body, text="닫기", width=10, command=win.destroy).grid(row=9, column=2, sticky="e")

    def apply(self):
        try:
            op = max(20, min(100, int(self.opacity_var.get())))
        except (tk.TclError, ValueError):
            op = self.cfg["opacity"]
        self.cfg["opacity"] = op
        self.root.attributes("-alpha", op / 100)

        new = {
            "size": self.size_var.get(),
            "show_nav": bool(self.nav_var.get()),
            "show_combo": bool(self.combo_var.get()),
            "transparent_bg": bool(self.transp_var.get()),
        }
        if any(self.cfg[k] != v for k, v in new.items()):
            self.cfg.update(new)
            self.redraw()
        self._schedule_save()

    def _schedule_save(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(500, lambda: save_config(self.cfg))

    def quit(self):
        self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
        save_config(self.cfg)
        try:
            self.listener.stop()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    KeyOverlay().run()
