import math
import os
import random
import shutil
import subprocess
import sys
import threading

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    import customtkinter as ctk
    import tkinter as tk
    from tkinter import colorchooser, filedialog, messagebox
    from PIL import ImageTk
except ImportError:
    ctk = None

DEFAULT_CONFIG = {
    "title_fade_in":  2.8,
    "title_hold":     5.0,
    "title_fade_out": 5.5,
    "scroll_speed":   80,
    "tail_seconds":   2.0,
    "end_fade_in":    2.0,
    "end_hold":       3.0,

    "title_size": 110,
    "role_size":  34,
    "name_size":  52,
    "end_size":   90,

    "bar_w":   120,
    "bar_h":   5,
    "bar_dot": 5,

    "block_gap": 150,
    "bar_gap":   38,
    "role_gap":  26,
    "name_gap":  16,
}

PARAM_FIELDS = [
    ("тайминги", None, None, None),
    ("title_fade_in",  "появление названия, сек",          0.1, 1),
    ("title_hold",     "название висит до титров, сек",    0.5, 1),
    ("title_fade_out", "исчезновение названия, сек",       0.1, 1),
    ("scroll_speed",   "скорость титров, пикс/сек",        5,   0),
    ("tail_seconds",   "пауза после титров, сек",          0.5, 1),
    ("end_fade_in",    "появление финальной надписи, сек", 0.1, 1),
    ("end_hold",       "финальная надпись висит, сек",     0.5, 1),
    ("размеры шрифтов, пикс", None, None, None),
    ("title_size", "название",          2, 0),
    ("name_size",  "имена",             2, 0),
    ("role_size",  "заголовки ролей",   2, 0),
    ("end_size",   "финальная надпись", 2, 0),
    ("полоска", None, None, None),
    ("bar_w",   "ширина полоски",  5, 0),
    ("bar_h",   "толщина полоски", 1, 0),
    ("bar_dot", "начальная точка", 1, 0),
    ("отступы, пикс", None, None, None),
    ("block_gap", "между блоками",  5, 0),
    ("bar_gap",   "полоска - роль", 2, 0),
    ("role_gap",  "роль - имена",   2, 0),
    ("name_gap",  "между именами",  2, 0),
]

RESOLUTIONS = {
    "1920×1080 30 fps": (1920, 1080, 30),
    "1920×1080 60 fps": (1920, 1080, 60),
    "3840×2160 30 fps": (3840, 2160, 30),
    "1080×1920 (верт.) 30 fps": (1080, 1920, 30),
    "1280×720 30 fps": (1280, 720, 30),
}

SCHEMES = {
    "dark":  {"bg": (0, 0, 0),       "fg": (255, 255, 255), "dim": (160, 160, 160)},
    "light": {"bg": (255, 255, 255), "fg": (0, 0, 0),       "dim": (110, 110, 110)},
}

UI = {
    "bg":        "#0c0f22",
    "bg2":       "#181c42",
    "glass":     "#181d3a",
    "glass_hi":  "#20264c",
    "field":     "#232a52",
    "field_hi":  "#2b3363",
    "border":    "#343d74",
    "accent":    "#8b7bff",
    "accent_hi": "#a89bff",
    "text":      "#eef0ff",
    "muted":     "#9aa0c8",
    "danger":    "#ff5c7a",
}

BLOB_COLORS = [
    (139, 123, 255),
    (66, 156, 255),
    (255, 110, 199),
    (74, 222, 222),
]


def ease_out_cubic(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


def find_default_font():
    candidates = [
        "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/georgia.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        "/usr/share/fonts/truetype/custom/Montserrat-VariableFont_wght.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


class CreditsRenderer:
    def __init__(self, title, blocks, scheme="dark",
                 title_font=None, body_font=None,
                 width=1920, height=1080, fps=30,
                 config=None, end_text="", transparent=False):
        self.title = title
        self.blocks = blocks
        self.scheme = SCHEMES[scheme] if isinstance(scheme, str) else dict(scheme)
        self.w, self.h, self.fps = width, height, fps
        self.end_text = end_text.strip()
        self.transparent = transparent

        cfg = dict(DEFAULT_CONFIG)
        if config:
            cfg.update(config)
        self.cfg = cfg
        self.k = min(self.w, self.h) / 1080.0

        title_path = title_font or find_default_font()
        body_path = body_font or find_default_font()
        if not title_path or not body_path:
            raise RuntimeError("не найден ни один ttf укажите файл шрифта")
        self.f_title = ImageFont.truetype(title_path, max(4, int(cfg["title_size"] * self.k)))
        self.f_role = ImageFont.truetype(body_path, max(4, int(cfg["role_size"] * self.k)))
        self.f_name = ImageFont.truetype(body_path, max(4, int(cfg["name_size"] * self.k)))
        self.f_end = ImageFont.truetype(title_path, max(4, int(cfg["end_size"] * self.k)))

        self._layout()

    def _layout(self):
        cfg, k = self.cfg, self.k
        y = 0.0
        self.items = []
        for block in self.blocks:
            if block.get("bar", True):
                self.items.append(("bar", y, None))
                y += (cfg["bar_h"] + cfg["bar_gap"]) * k
            role = block.get("role", "").strip()
            if role:
                self.items.append(("role", y, role.upper()))
                y += (cfg["role_size"] + cfg["role_gap"]) * k
            for name in block.get("names", []):
                if name.strip():
                    self.items.append(("name", y, name.strip()))
                    y += (cfg["name_size"] + cfg["name_gap"]) * k
            y += cfg["block_gap"] * k
        self.strip_height = y

        self.t_scroll_start = cfg["title_hold"]
        speed = cfg["scroll_speed"] * k
        travel = self.h + self.strip_height
        self.t_scroll_end = self.t_scroll_start + travel / max(1e-6, speed)
        self.t_end_start = self.t_scroll_end + cfg["tail_seconds"]
        if self.end_text:
            self.duration = self.t_end_start + cfg["end_fade_in"] + cfg["end_hold"]
        else:
            self.duration = self.t_end_start

    def frame(self, t):
        scheme, cfg, k = self.scheme, self.cfg, self.k
        if self.transparent:
            img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        else:
            img = Image.new("RGB", (self.w, self.h), scheme["bg"])
        draw = ImageDraw.Draw(img)
        cx = self.w // 2

        def faded(base, a):
            if self.transparent:
                return tuple(base) + (int(255 * a),)
            return tuple(int(bgc + (c - bgc) * a)
                         for bgc, c in zip(scheme["bg"], base))

        if self.title.strip():
            fi, fo = cfg["title_fade_in"], cfg["title_fade_out"]
            fade_out_start = self.t_scroll_start + 0.6
            if t < fi:
                a = ease_out_cubic(t / max(1e-6, fi))
            elif t < fade_out_start:
                a = 1.0
            else:
                a = 1.0 - min(1.0, (t - fade_out_start) / max(1e-6, fo))
            if a > 0:
                dy = int((1 - ease_out_cubic(min(1.0, t / max(1e-6, fi)))) * 18 * k)
                draw.text((cx, self.h // 2 + dy), self.title,
                          font=self.f_title, fill=faded(scheme["fg"], a), anchor="mm")

        if t >= self.t_scroll_start:
            speed = cfg["scroll_speed"] * k
            offset = (t - self.t_scroll_start) * speed
            top = self.h - offset
            margin = 200 * k
            for kind, iy, data in self.items:
                y = top + iy
                if y < -margin or y > self.h + margin:
                    continue
                if kind == "bar":
                    p = ease_out_cubic((self.h - y) / (self.h * 0.30))
                    bw = (cfg["bar_dot"] + (cfg["bar_w"] - cfg["bar_dot"]) * p) * k
                    bh = max(cfg["bar_h"] * k,
                             (cfg["bar_dot"] * (1 - p) + cfg["bar_h"] * p) * k)
                    draw.rounded_rectangle(
                        [cx - bw / 2, y, cx + bw / 2, y + bh],
                        radius=bh / 2, fill=faded(scheme["fg"], 1.0))
                elif kind == "role":
                    draw.text((cx, y), data, font=self.f_role,
                              fill=faded(scheme["dim"], 1.0), anchor="ma")
                elif kind == "name":
                    draw.text((cx, y), data, font=self.f_name,
                              fill=faded(scheme["fg"], 1.0), anchor="ma")

        if self.end_text and t >= self.t_end_start:
            a = ease_out_cubic((t - self.t_end_start) / max(1e-6, cfg["end_fade_in"]))
            if a > 0:
                draw.text((cx, self.h // 2), self.end_text,
                          font=self.f_end, fill=faded(scheme["fg"], a), anchor="mm")
        return img

    def render(self, path, progress_cb=None):
        if self.transparent:
            self._render_transparent(path, progress_cb)
        else:
            self._render_mp4(path, progress_cb)

    def _render_mp4(self, path, progress_cb):
        total = int(self.duration * self.fps)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(path, fourcc, self.fps, (self.w, self.h))
        if not writer.isOpened():
            raise RuntimeError("не удалось открыть videowriter (проверь opencv олень)")
        try:
            for i in range(total):
                img = self.frame(i / self.fps)
                writer.write(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR))
                if progress_cb and i % self.fps == 0:
                    progress_cb(i / total)
        finally:
            writer.release()
        if progress_cb:
            progress_cb(1.0)

    def _render_transparent(self, path, progress_cb):
        if not shutil.which("ffmpeg"):
            raise RuntimeError(
                "для экспорта с прозрачным фоном нужен ffmpeg\n"
                "установите его и добавьте в патч ffmpeg.org")
        total = int(self.duration * self.fps)
        cmd = ["ffmpeg", "-y", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgba",
               "-s", f"{self.w}x{self.h}", "-r", str(self.fps), "-i", "-",
               "-c:v", "qtrle", "-pix_fmt", "argb", path]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            for i in range(total):
                img = self.frame(i / self.fps)
                proc.stdin.write(np.array(img, dtype=np.uint8).tobytes())
                if progress_cb and i % self.fps == 0:
                    progress_cb(i / total)
        finally:
            proc.stdin.close()
            proc.wait()
        if proc.returncode != 0:
            raise RuntimeError("ffmpeg завершился с ошибкой")
        if progress_cb:
            progress_cb(1.0)


class Blob:
    def __init__(self, area, first=False):
        self.area = area
        self._respawn(first)

    def _respawn(self, first=False):
        w, h = self.area
        self.color = np.array(random.choice(BLOB_COLORS), dtype=np.float32)
        self.radius = max(6, int(random.uniform(0.35, 0.62) * min(w, h)))
        self.sprite = self._make_sprite(self.radius)
        self.target = (random.uniform(0.12, 0.88) * w,
                       random.uniform(0.15, 0.85) * h)
        self.entry = self._edge_point()
        self.leave = self._edge_point()
        self.t_enter = random.uniform(1.6, 2.4)
        self.t_hold = random.uniform(2.0, 3.4)
        self.t_exit = random.uniform(1.6, 2.4)
        self.delay = random.uniform(0.0, 4.0) if first else random.uniform(0.4, 3.0)
        self.drift_phase = random.uniform(0, math.tau)
        self.drift_amp = self.radius * 0.12
        self.clock = 0.0

    @staticmethod
    def _make_sprite(radius):
        size = radius * 2
        yy, xx = np.ogrid[:size, :size]
        dist = np.sqrt((xx - radius) ** 2 + (yy - radius) ** 2) / radius
        return (np.clip(1.0 - dist, 0.0, 1.0) ** 2 * 0.55).astype(np.float32)

    def _edge_point(self):
        w, h = self.area
        pad = self.radius * 1.4
        side = random.randrange(4)
        if side == 0:
            return (-pad, random.uniform(0, h))
        if side == 1:
            return (w + pad, random.uniform(0, h))
        if side == 2:
            return (random.uniform(0, w), -pad)
        return (random.uniform(0, w), h + pad)

    def _drift(self, t):
        return (math.sin(t * 0.8 + self.drift_phase) * self.drift_amp,
                math.cos(t * 0.6 + self.drift_phase) * self.drift_amp)

    def step(self, dt):
        self.clock += dt
        t = self.clock - self.delay
        if t < 0:
            return None
        if t < self.t_enter:
            k = smoothstep(t / self.t_enter)
            x = self.entry[0] + (self.target[0] - self.entry[0]) * k
            y = self.entry[1] + (self.target[1] - self.entry[1]) * k
            return (x, y), k
        t -= self.t_enter
        if t < self.t_hold:
            dx, dy = self._drift(t)
            return (self.target[0] + dx, self.target[1] + dy), 1.0
        t -= self.t_hold
        if t < self.t_exit:
            dx, dy = self._drift(self.t_hold)
            sx, sy = self.target[0] + dx, self.target[1] + dy
            k = smoothstep(t / self.t_exit)
            x = sx + (self.leave[0] - sx) * k
            y = sy + (self.leave[1] - sy) * k
            return (x, y), 1.0 - k
        self._respawn()
        return None


class AuroraBackdrop:
    def __init__(self, master, fps=30, downscale=6, count=4):
        self.master = master
        self.fps = fps
        self.downscale = downscale
        self.count = count
        self.size = (0, 0)
        self.base = None
        self.blobs = []
        self.photo = None
        self.label = tk.Label(master, bd=0, bg=UI["bg"])
        self.label.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.label.lower()
        master.bind("<Configure>", self._on_resize, add="+")
        self._tick()

    def _on_resize(self, event):
        if event.widget is not self.master:
            return
        size = (event.width, event.height)
        if (abs(size[0] - self.size[0]) < 4
                and abs(size[1] - self.size[1]) < 4):
            return
        self.size = size
        lw = max(4, size[0] // self.downscale)
        lh = max(4, size[1] // self.downscale)
        top = np.array(hex_to_rgb(UI["bg"]), dtype=np.float32)
        bottom = np.array(hex_to_rgb(UI["bg2"]), dtype=np.float32)
        grad = np.linspace(0.0, 1.0, lh, dtype=np.float32)[:, None, None]
        self.base = top * (1 - grad) + bottom * grad
        self.base = np.broadcast_to(self.base, (lh, lw, 3)).copy()
        self.blobs = [Blob((lw, lh), first=True) for _ in range(self.count)]

    def _stamp(self, frame, blob, pos, alpha):
        r = blob.radius
        x, y = int(pos[0]) - r, int(pos[1]) - r
        h, w = frame.shape[:2]
        size = blob.sprite.shape[0]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(w, x + size), min(h, y + size)
        if x0 >= x1 or y0 >= y1:
            return
        patch = blob.sprite[y0 - y:y1 - y, x0 - x:x1 - x, None] * alpha
        frame[y0:y1, x0:x1] += patch * blob.color

    def _tick(self):
        if self.base is not None:
            frame = self.base.copy()
            for blob in self.blobs:
                state = blob.step(1.0 / self.fps)
                if state:
                    self._stamp(frame, blob, *state)
            arr = np.clip(frame, 0, 255).astype(np.uint8)
            img = Image.fromarray(arr).resize(self.size, Image.BILINEAR)
            self.photo = ImageTk.PhotoImage(img)
            self.label.configure(image=self.photo)
        self.master.after(max(15, int(1000 / self.fps)), self._tick)


class StudioApp:
    PREVIEW_W = 420
    PREVIEW_H = 236

    def __init__(self):
        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk(fg_color=UI["bg"])
        self.root.title("студия микрозаймов или кредитов хз")
        self.root.geometry("1220x800")

        self.blocks = [
            {"role": "хуесос1", "names": ["да"], "bar": True},
            {"role": "уууу", "names": ["нет"], "bar": True},
            {"role": "дада", "names": ["да будет свет", "нет нет"], "bar": True},
        ]
        self.fonts = {"title": find_default_font(), "body": find_default_font()}
        self.colors = dict(SCHEMES["dark"])
        self.config = dict(DEFAULT_CONFIG)
        self.selected = None
        self.row_widgets = []
        self.swatches = {}
        self.preview_job = None

        self.font_h1 = ctk.CTkFont(size=22, weight="bold")
        self.font_s = ctk.CTkFont(size=12)
        self.font_xs = ctk.CTkFont(size=11)

        self.backdrop = AuroraBackdrop(self.root)

        self._build_header()
        self._build_layout()
        self._build_left()
        self._build_right()

        self._refresh_list()
        self._apply_colors()
        self.root.after(250, self._update_preview)
        self._fade_in()

    def run(self):
        self.root.mainloop()

    def _fade_in(self, step=0):
        try:
            self.root.attributes("-alpha", min(0.97, step))
        except tk.TclError:
            return
        if step < 0.97:
            self.root.after(16, self._fade_in, step + 0.08)

    def _card(self, parent, **kw):
        return ctk.CTkFrame(parent, fg_color=UI["glass"], corner_radius=18,
                            border_width=1, border_color=UI["border"], **kw)

    def _section_label(self, parent, text):
        return ctk.CTkLabel(parent, text=text.upper(), font=self.font_xs,
                            text_color=UI["muted"])

    def _mini_btn(self, parent, text, cmd, danger=False):
        return ctk.CTkButton(
            parent, text=text, command=cmd, height=32, corner_radius=10,
            font=self.font_s, width=10,
            fg_color=UI["field"] if not danger else "transparent",
            hover_color=UI["field_hi"] if not danger else "#2a1520",
            border_width=1,
            border_color=UI["border"] if not danger else UI["danger"],
            text_color=UI["text"] if not danger else UI["danger"])

    def _entry(self, parent, placeholder, height=38):
        return ctk.CTkEntry(parent, placeholder_text=placeholder,
                            fg_color=UI["field"], border_color=UI["border"],
                            corner_radius=10, height=height, font=self.font_s)

    def _build_header(self):
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(fill="x", padx=26, pady=(18, 6))
        ctk.CTkLabel(header, text="студия кредитов или микрозаймов", font=self.font_h1,
                     text_color=UI["text"]).pack(side="left")
        ctk.CTkLabel(header, text="генератор конечных титров",
                     font=self.font_s, text_color=UI["muted"]
                     ).pack(side="left", padx=12, pady=(6, 0))

    def _build_layout(self):
        self.body = ctk.CTkFrame(self.root, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=20, pady=(4, 18))
        self.body.grid_columnconfigure(0, weight=5)
        self.body.grid_columnconfigure(1, weight=4)
        self.body.grid_rowconfigure(0, weight=1)

    def _build_left(self):
        left = ctk.CTkScrollableFrame(self.body, fg_color="transparent",
                                      scrollbar_button_color=UI["field"],
                                      scrollbar_button_hover_color=UI["field_hi"])
        left.grid(row=0, column=0, sticky="nsew", padx=(6, 10))

        card = self._card(left)
        card.pack(fill="x", pady=6)
        self._section_label(card, "текст").pack(anchor="w", padx=16, pady=(12, 4))
        self.e_title = self._entry(card, "нвазание")
        self.e_title.insert(0, "gmae")
        self.e_title.pack(fill="x", padx=16, pady=4)
        self.e_end = self._entry(card, "надпись в конце(еслипусто значит её нема будет)")
        self.e_end.insert(0, "канец")
        self.e_end.pack(fill="x", padx=16, pady=(4, 14))
        self.e_title.bind("<KeyRelease>", self._schedule_preview)
        self.e_end.bind("<KeyRelease>", self._schedule_preview)

        card = self._card(left)
        card.pack(fill="x", pady=6)
        self._section_label(card, "блок титров").pack(anchor="w", padx=16, pady=(12, 4))

        self.list_holder = ctk.CTkFrame(card, fg_color="transparent")
        self.list_holder.pack(fill="x", padx=16, pady=2)

        add_holder = ctk.CTkFrame(card, fg_color="transparent")
        add_holder.pack(fill="x", padx=16, pady=(8, 4))
        self.e_role = self._entry(add_holder, "роль", height=34)
        self.e_role.pack(fill="x", pady=2)
        self.t_names = ctk.CTkTextbox(add_holder, height=64, fg_color=UI["field"],
                                      border_color=UI["border"], border_width=1,
                                      corner_radius=10, font=self.font_s)
        self.t_names.pack(fill="x", pady=2)
        ctk.CTkLabel(add_holder, text="имена или ники, одно в строке, типо один ник в первой строке второй во второй",
                     font=self.font_xs, text_color=UI["muted"]).pack(anchor="w")
        self.bar_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(add_holder, text="полоска над блоком", variable=self.bar_var,
                        font=self.font_s, checkbox_width=20, checkbox_height=20,
                        fg_color=UI["accent"], hover_color=UI["accent_hi"]
                        ).pack(anchor="w", pady=4)

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=(2, 14))
        ctk.CTkButton(btns, text="добавить блок", command=self._add_block,
                      height=32, corner_radius=10, font=self.font_s,
                      fg_color=UI["accent"], hover_color=UI["accent_hi"]
                      ).pack(side="left", padx=(0, 6))
        self._mini_btn(btns, "вверх", lambda: self._move(-1)).pack(side="left", padx=2)
        self._mini_btn(btns, "вниз", lambda: self._move(1)).pack(side="left", padx=2)
        self._mini_btn(btns, "Удалить", self._remove_block,
                       danger=True).pack(side="right")

        card = self._card(left)
        card.pack(fill="x", pady=6)
        self._section_label(card, "цвета").pack(anchor="w", padx=16, pady=(12, 4))
        presets = ctk.CTkFrame(card, fg_color="transparent")
        presets.pack(fill="x", padx=16, pady=2)
        self._mini_btn(presets, "тёмный",
                       lambda: self._set_preset("dark")).pack(side="left", padx=(0, 6))
        self._mini_btn(presets, "светлый",
                       lambda: self._set_preset("light")).pack(side="left")
        self._color_row(card, "фон", "bg")
        self._color_row(card, "имена, название, полоска", "fg")
        self._color_row(card, "заголовки ролей", "dim")
        ctk.CTkFrame(card, fg_color="transparent", height=10).pack()

        card = self._card(left)
        card.pack(fill="x", pady=6)
        self._section_label(card, "шрифты").pack(anchor="w", padx=16, pady=(12, 4))
        self._font_row(card, "название", "title")
        self._font_row(card, "ттитры", "body")
        ctk.CTkFrame(card, fg_color="transparent", height=10).pack()

    def _build_right(self):
        right = ctk.CTkFrame(self.body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 6))

        card = self._card(right)
        card.pack(fill="x", pady=6)
        self._section_label(card, "предпросмотр").pack(anchor="w", padx=16, pady=(12, 6))
        holder = ctk.CTkFrame(card, fg_color="#000000", corner_radius=12,
                              width=self.PREVIEW_W, height=self.PREVIEW_H)
        holder.pack(padx=16)
        holder.pack_propagate(False)
        self.lbl_prev = ctk.CTkLabel(holder, text="")
        self.lbl_prev.pack(expand=True)

        self.lbl_time = ctk.CTkLabel(card, text="t = 1.5 c", font=self.font_xs,
                                     text_color=UI["muted"])
        self.lbl_time.pack(pady=(6, 0))
        self.time_var = tk.DoubleVar(value=1.5)
        self.sl_time = ctk.CTkSlider(card, from_=0, to=30, variable=self.time_var,
                                     button_color=UI["accent"],
                                     button_hover_color=UI["accent_hi"],
                                     progress_color=UI["accent"],
                                     command=lambda _v: self._schedule_preview())
        self.sl_time.pack(fill="x", padx=16, pady=(2, 14))

        card = self._card(right)
        card.pack(fill="x", pady=6)
        self._section_label(card, "вывод").pack(anchor="w", padx=16, pady=(12, 4))

        self.res_var = tk.StringVar(value=list(RESOLUTIONS)[0])
        ctk.CTkOptionMenu(card, variable=self.res_var, values=list(RESOLUTIONS),
                          fg_color=UI["field"], button_color=UI["field"],
                          button_hover_color=UI["field_hi"],
                          dropdown_fg_color=UI["glass"], corner_radius=10,
                          font=self.font_s, dropdown_font=self.font_s,
                          command=lambda _v: self._schedule_preview()
                          ).pack(fill="x", padx=16, pady=4)

        self.transparent_var = tk.BooleanVar(value=False)
        ctk.CTkSwitch(card, text="прозрачный фон mov, нужен ffmpeg",
                      variable=self.transparent_var, font=self.font_s,
                      progress_color=UI["accent"]).pack(anchor="w", padx=16, pady=6)

        ctk.CTkButton(card, text="настройки", command=self._open_params,
                      height=36, corner_radius=10, font=self.font_s,
                      fg_color=UI["field"], hover_color=UI["field_hi"],
                      border_width=1, border_color=UI["border"]
                      ).pack(fill="x", padx=16, pady=4)

        self.pb = ctk.CTkProgressBar(card, progress_color=UI["accent"])
        self.pb.set(0)
        self.pb.pack(fill="x", padx=16, pady=(8, 4))

        self.btn_render = ctk.CTkButton(
            card, text="сохранить видео", command=self._do_render,
            height=44, corner_radius=12,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=UI["accent"], hover_color=UI["accent_hi"])
        self.btn_render.pack(fill="x", padx=16, pady=(4, 16))

    def _color_row(self, parent, label, key):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=3)
        sw = ctk.CTkButton(row, text="", width=34, height=26, corner_radius=8,
                           border_width=1, border_color=UI["border"])
        sw.pack(side="left")
        self.swatches[key] = sw
        ctk.CTkLabel(row, text=label, font=self.font_s,
                     text_color=UI["text"]).pack(side="left", padx=10)

        def choose():
            rgb, _ = colorchooser.askcolor(color=rgb_to_hex(self.colors[key]),
                                           title=label)
            if rgb:
                self.colors[key] = tuple(int(v) for v in rgb)
                self._apply_colors()

        sw.configure(command=choose)

    def _font_row(self, parent, label, key):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=3)
        ctk.CTkLabel(row, text=label, font=self.font_s, width=120, anchor="w",
                     text_color=UI["text"]).pack(side="left")
        var = tk.StringVar(value=os.path.basename(self.fonts[key] or "не найден"))
        ctk.CTkLabel(row, textvariable=var, font=self.font_xs,
                     text_color=UI["muted"]).pack(side="left", fill="x",
                                                  expand=True, padx=8)

        def choose():
            path = filedialog.askopenfilename(
                title="выберите шрифт",
                filetypes=[("шрифты", "*.ttf *.otf"), ("все файлы", "*.*")])
            if path:
                self.fonts[key] = path
                var.set(os.path.basename(path))
                self._schedule_preview()

        self._mini_btn(row, "выбрат", choose).pack(side="right")

    def _refresh_list(self):
        for widget in self.row_widgets:
            widget.destroy()
        self.row_widgets.clear()
        for i, block in enumerate(self.blocks):
            is_sel = (self.selected == i)
            row = ctk.CTkFrame(self.list_holder, corner_radius=10,
                               fg_color=UI["accent"] if is_sel else UI["field"])
            row.pack(fill="x", pady=2)
            mark = "—" if block["bar"] else "·"
            text = f'{mark}  {block["role"]}   ·   {", ".join(block["names"])}'
            lbl = ctk.CTkLabel(row, text=text, font=self.font_s, anchor="w",
                               text_color="#ffffff" if is_sel else UI["text"])
            lbl.pack(side="left", fill="x", expand=True, padx=12, pady=7)
            for widget in (row, lbl):
                widget.bind("<Button-1>", lambda _e, idx=i: self._select_block(idx))
                if not is_sel:
                    widget.bind("<Enter>",
                                lambda _e, r=row: r.configure(fg_color=UI["field_hi"]))
                    widget.bind("<Leave>",
                                lambda _e, r=row: r.configure(fg_color=UI["field"]))
            self.row_widgets.append(row)
        self._schedule_preview()

    def _select_block(self, i):
        self.selected = None if self.selected == i else i
        self._refresh_list()

    def _add_block(self):
        role = self.e_role.get().strip()
        names = [s for s in self.t_names.get("1.0", "end").splitlines() if s.strip()]
        if not role and not names:
            return
        self.blocks.append({"role": role, "names": names, "bar": self.bar_var.get()})
        self.e_role.delete(0, "end")
        self.t_names.delete("1.0", "end")
        self._refresh_list()

    def _remove_block(self):
        if self.selected is not None and 0 <= self.selected < len(self.blocks):
            self.blocks.pop(self.selected)
            self.selected = None
            self._refresh_list()

    def _move(self, delta):
        i = self.selected
        if i is None:
            return
        j = i + delta
        if 0 <= j < len(self.blocks):
            self.blocks[i], self.blocks[j] = self.blocks[j], self.blocks[i]
            self.selected = j
            self._refresh_list()

    def _set_preset(self, name):
        self.colors.update(SCHEMES[name])
        self._apply_colors()

    def _apply_colors(self):
        for key, btn in self.swatches.items():
            btn.configure(fg_color=rgb_to_hex(self.colors[key]),
                          hover_color=rgb_to_hex(self.colors[key]))
        self._schedule_preview()

    def _build_renderer(self, transparent=False):
        w, h, fps = RESOLUTIONS[self.res_var.get()]
        return CreditsRenderer(
            self.e_title.get(), self.blocks, dict(self.colors),
            title_font=self.fonts["title"], body_font=self.fonts["body"],
            width=w, height=h, fps=fps,
            config=dict(self.config), end_text=self.e_end.get(),
            transparent=transparent)

    def _schedule_preview(self, *_):
        if self.preview_job:
            self.root.after_cancel(self.preview_job)
        self.preview_job = self.root.after(120, self._update_preview)

    def _update_preview(self):
        self.preview_job = None
        try:
            renderer = self._build_renderer()
        except Exception:
            return
        self.sl_time.configure(to=max(1.0, renderer.duration))
        t = min(self.time_var.get(), renderer.duration)
        self.lbl_time.configure(
            text=f"t = {t:.1f} c длительность {renderer.duration:.1f} c")
        img = renderer.frame(t).convert("RGB")
        ratio = min(self.PREVIEW_W / img.width, self.PREVIEW_H / img.height)
        size = (max(1, int(img.width * ratio)), max(1, int(img.height * ratio)))
        cimg = ctk.CTkImage(light_image=img, dark_image=img, size=size)
        self.lbl_prev.configure(image=cimg, text="")
        self.lbl_prev.image = cimg

    def _do_render(self):
        if not self.blocks:
            messagebox.showwarning("титры", "добавьте хотя бы один блок титров")
            return
        transparent = self.transparent_var.get()
        if transparent:
            path = filedialog.asksaveasfilename(
                defaultextension=".mov",
                filetypes=[("квиктайм mov, с альфой", "*.mov")],
                initialfile="credits.mov")
        else:
            path = filedialog.asksaveasfilename(
                defaultextension=".mp4", filetypes=[("видео мп4", "*.mp4")],
                initialfile="credits.mp4")
        if not path:
            return
        self.btn_render.configure(state="disabled", text="рендер")

        def worker():
            try:
                renderer = self._build_renderer(transparent=transparent)
                renderer.render(path,
                                progress_cb=lambda p: self.root.after(0, self.pb.set, p))
                self.root.after(0, lambda: messagebox.showinfo(
                    "гатово",
                    f"видео сохранено:\n{path}\n"
                    f"длительность: {renderer.duration:.1f} cек"))
            except Exception as exc:
                self.root.after(0, lambda e=exc: messagebox.showerror("ошипка", str(e)))
            finally:
                self.root.after(0, lambda: self.btn_render.configure(
                    state="normal", text="сохранить видео"))

        threading.Thread(target=worker, daemon=True).start()

    def _open_params(self):
        win = ctk.CTkToplevel(self.root, fg_color=UI["bg"])
        win.title("настройки")
        win.geometry("420x640")
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.0)

            def fade(step=0.0):
                try:
                    win.attributes("-alpha", min(0.98, step))
                except tk.TclError:
                    return
                if step < 0.98:
                    win.after(16, fade, step + 0.12)

            fade()
        except tk.TclError:
            pass

        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        entries = {}
        for key, label, step, prec in PARAM_FIELDS:
            if label is None:
                self._section_label(scroll, key).pack(anchor="w", padx=6, pady=(14, 4))
                continue
            row = ctk.CTkFrame(scroll, fg_color=UI["glass"], corner_radius=10,
                               border_width=1, border_color=UI["border"])
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=label, font=self.font_s,
                         text_color=UI["text"]).pack(side="left", padx=12, pady=7)
            ent = ctk.CTkEntry(row, width=80, height=28, corner_radius=8,
                               fg_color=UI["field"], border_color=UI["border"],
                               font=self.font_s, justify="right")
            val = self.config[key]
            ent.insert(0, f"{val:.{prec}f}" if prec else str(int(val)))
            ent.pack(side="right", padx=10)
            entries[key] = ent

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=10, pady=(0, 12))

        def save():
            try:
                for key, ent in entries.items():
                    self.config[key] = float(ent.get().replace(",", "."))
            except ValueError:
                messagebox.showerror("настойки",
                                     "некорректное число в одном из полей",
                                     parent=win)
                return
            win.destroy()
            self._schedule_preview()

        def reset():
            for key, ent in entries.items():
                ent.delete(0, "end")
                ent.insert(0, str(DEFAULT_CONFIG[key]))

        self._mini_btn(bar, "Сбросить", reset).pack(side="left")
        ctk.CTkButton(bar, text="Применить", command=save, height=32,
                      corner_radius=10, font=self.font_s,
                      fg_color=UI["accent"], hover_color=UI["accent_hi"]
                      ).pack(side="right")


def run_gui():
    if ctk is None:
        print("нужен пакет customtkinter установите его командой:")
        print("    pip " + "install customtkinter")
        sys.exit(1)
    StudioApp().run()


def run_cli():
    demo = [
        {"role": "уап", "names": ["уап"], "bar": True},
        {"role": "неи", "names": ["не"], "bar": True},
        {"role": "разработка", "names": ["да", "пидорас"], "bar": True},
        {"role": "неиу", "names": ["пошёлназуй", "ацуа"], "bar": True},
    ]
    renderer = CreditsRenderer("gaem", demo, "dark", end_text="пошелнахуй")
    print(f"длительность: {renderer.duration:.1f} c")
    renderer.render("credits_test.mp4",
                    progress_cb=lambda p: print(f"{p*100:.0f}%", end=" "))
    print("\nГотово: credits_test.mp4")


if __name__ == "__main__":
    if "--nogui" in sys.argv:
        run_cli()
    else:
        run_gui()
