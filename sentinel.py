# Arjun's Third Eye  v1.17.2
# motion detection app i made for myself
# uses a trained background model to detect people behind me
# - arjun

import cv2
import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import os
import ctypes
import winsound
from PIL import Image, ImageTk

# hide the console, nobody needs to see that
try:
    ctypes.windll.user32.ShowWindow(
        ctypes.windll.kernel32.GetConsoleWindow(), 0)
except Exception:
    pass

# load pygame for mp3 alert sound, fall back to beep if not installed
try:
    import pygame
    pygame.mixer.init()
    _PYGAME_OK = True
except Exception:
    _PYGAME_OK = False

import sys

# works both when running as .py and when packaged as .exe with pyinstaller
def _resource(name):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

def _appdata(name):
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)

ALERT_SOUND = _resource("alert.mp3")
_MP3_PATH   = ALERT_SOUND  # alias used elsewhere

# camera processing resolution - lower = faster, 320x240 is plenty
CAM_PROC_W, CAM_PROC_H = 320, 240
PROC_W, PROC_H = CAM_PROC_W, CAM_PROC_H

# display size in the gui panel
DISP_W, DISP_H = 480, 360

# how many frames in a row must show motion before we actually alert
# this kills single-frame noise/false triggers
CONFIRM_FRAMES = 4

# ignore first N processed frames on startup - camera needs to settle
WARMUP_FRAMES = 20

# only run detection every 2nd frame to save cpu
SKIP_FRAMES = 2

# gui refresh rate cap
GUI_FPS = 15

# if more than 45% of the diff fires at once, camera probably shook
SHAKE_THRESHOLD = 0.45

# if global brightness jumps more than this between frames, its a light change not motion
LIGHT_CHANGE_THR = 15
GLOBAL_LIGHT_THR = LIGHT_CHANGE_THR  # alias

# how long between repeated alert sounds (seconds)
ALERT_COOLDOWN = 3.0

# min detection box size in pixels - filters out tiny edge noise
MIN_BOX_W = 25
MIN_BOX_H = 30

# window minimum size
MIN_W, MIN_H = 780, 580

# training config - records 60 frames of empty room to build background model
TRAIN_FRAMES = 60
TRAIN_FPS    = 15

# sensitivity settings: (variance multiplier, min blob area in pixels)
# lower multiplier = more sensitive = more false triggers too
SENSITIVITY_MAP = {
    "Low"   : (3.5, 5000),
    "Medium": (2.2, 3000),
    "High"  : (1.4, 1500),
}

SOUND_PRESETS = {
    "Custom MP3"  : "MP3",
    "Beep x3"     : [(1000, 200, 3, 100)],
    "Alarm Siren" : [(800,100,1,0),(1200,100,1,0),(800,100,1,0),(1200,100,1,0)],
    "Low Buzz"    : [(400, 500, 2, 100)],
    "High Ping"   : [(1800, 80, 4, 60)],
    "SOS"         : [(900,100,3,80),(900,300,3,80),(900,100,3,80)],
    "Doorbell"    : [(880,200,1,50),(660,300,1,0)],
    "No Sound"    : [],
}

# default profile save path (next to the exe / script)
_PROFILE_DIR = _appdata("profiles")


# ──────────────────────────────────────────────────────────────
# CAMERA DISCOVERY
# ──────────────────────────────────────────────────────────────
def list_cameras(max_check=5):
    found = []
    for i in range(max_check):
        cap = cv2.VideoCapture(i, cv2.CAP_MSMF)
        if cap.isOpened():
            found.append((i, f"Camera {i}"))
            cap.release()
        else:
            cap.release()
    return found or [(0, "Camera 0")]


def open_camera(index):
    for backend, name in [(cv2.CAP_MSMF,"MSMF"),(cv2.CAP_DSHOW,"DShow"),(cv2.CAP_ANY,"Auto")]:
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            cap.release(); continue
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        for _ in range(4): cap.grab()
        ret, frame = cap.read()
        if ret and frame is not None and frame.max() > 0:
            return cap, name
        cap.release()
    raise RuntimeError(
        f"Camera {index} gave no image.\n"
        "• Try a different camera in the dropdown\n"
        "• Close Teams/Zoom/OBS\n"
        "• Settings → Privacy → Camera → allow desktop apps"
    )


# ──────────────────────────────────────────────────────────────
# DESKTOP SWITCH
# ──────────────────────────────────────────────────────────────
_VK_LWIN    = 0x5B
_VK_CONTROL = 0x11
_VK_RIGHT   = 0x27
_VK_LEFT    = 0x25
_KEYUP      = 0x0002
_keybd      = ctypes.windll.user32.keybd_event

def _switch_desktop(direction="next"):
    arrow = _VK_RIGHT if direction == "next" else _VK_LEFT
    _keybd(_VK_LWIN,0,0,0); _keybd(_VK_CONTROL,0,0,0); _keybd(arrow,0,0,0)
    time.sleep(0.05)
    _keybd(arrow,0,_KEYUP,0); _keybd(_VK_CONTROL,0,_KEYUP,0); _keybd(_VK_LWIN,0,_KEYUP,0)


# ──────────────────────────────────────────────────────────────
# SOUND
# ──────────────────────────────────────────────────────────────
def play_sound(preset):
    def _go():
        val = SOUND_PRESETS.get(preset, [])
        if val == "MP3":
            if _PYGAME_OK and os.path.exists(_MP3_PATH):
                try:
                    pygame.mixer.music.load(_MP3_PATH)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy(): time.sleep(0.05)
                    return
                except Exception: pass
            winsound.Beep(1000, 400); return
        if not val: return
        for freq, dur, reps, gap in val:
            for _ in range(reps):
                winsound.Beep(freq, dur)
                if gap: time.sleep(gap/1000)
    threading.Thread(target=_go, daemon=True).start()


# ──────────────────────────────────────────────────────────────
# ROOM MODEL  —  the trained background
# ──────────────────────────────────────────────────────────────
class RoomModel:
    """
    Trained background model built from N frames of your empty room.

    Stores per-pixel mean and standard deviation.
    A pixel is "changed" if  |current - mean| > k * std
    where k comes from the sensitivity setting.

    This means:
    - Naturally noisy pixels (curtain, window) automatically get
      a wider tolerance — they won't trigger unless something
      REALLY changes.
    - Rock-steady pixels (plain wall) have a very tight tolerance
      and will detect even subtle movement.
    """
    def __init__(self):
        self.mean  = None   # float32 (PROC_H, PROC_W)
        self.std   = None   # float32 (PROC_H, PROC_W)
        self.ready = False
        self.name  = "untrained"

    # ── build from a list of gray frames ─────────────────────
    def train(self, frames_gray):
        """frames_gray: list of uint8 (PROC_H, PROC_W) arrays."""
        stack      = np.stack(frames_gray, axis=0).astype(np.float32)
        self.mean  = np.mean(stack, axis=0)
        raw_std    = np.std(stack, axis=0)
        # floor the std at 4 intensity units so even dead-stable pixels
        # have some tolerance — prevents ultra-noisy camera triggering
        self.std   = np.clip(raw_std, 4.0, 80.0)
        self.ready = True

    # ── single-snapshot fallback (old behaviour) ─────────────
    def from_single(self, gray):
        self.mean  = gray.astype(np.float32)
        self.std   = np.full_like(self.mean, 8.0)  # flat tolerance
        self.ready = True

    # ── compute threshold mask for current frame ──────────────
    def diff_mask(self, gray_norm, k):
        """Return binary mask where pixel differs from background by > k*std."""
        diff = np.abs(gray_norm.astype(np.float32) - self.mean)
        mask = (diff > k * self.std).astype(np.uint8) * 255
        return mask

    # ── save / load ──────────────────────────────────────────
    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        np.savez_compressed(path, mean=self.mean, std=self.std)

    def load(self, path):
        data = np.load(path)
        self.mean  = data["mean"]
        self.std   = data["std"]
        self.ready = True

    # ── preview image (shows what the model looks like) ───────
    def preview_bgr(self):
        """Return a clean grayscale BGR image of the trained mean — for display only."""
        if not self.ready: return None
        mean_u8 = np.clip(self.mean, 0, 255).astype(np.uint8)
        # resize back to a sensible display size
        disp    = cv2.resize(mean_u8, (PROC_W*2, PROC_H*2))
        return cv2.cvtColor(disp, cv2.COLOR_GRAY2BGR)

    def heatmap_bgr(self):
        """Return std heatmap for overlay — shows noisy vs stable regions."""
        if not self.ready: return None
        std_norm = (np.clip(self.std, 4, 40) - 4) / 36
        heat     = (std_norm * 255).astype(np.uint8)
        heat_bgr = cv2.applyColorMap(heat, cv2.COLORMAP_COOL)
        mean_u8  = np.clip(self.mean, 0, 255).astype(np.uint8)
        bgr      = cv2.cvtColor(mean_u8, cv2.COLOR_GRAY2BGR)
        blended  = cv2.addWeighted(bgr, 0.55, heat_bgr, 0.45, 0)
        return cv2.resize(blended, (PROC_W*2, PROC_H*2))


# ──────────────────────────────────────────────────────────────
# MOTION DETECTOR
# ──────────────────────────────────────────────────────────────
class MotionDetector:
    def __init__(self, on_frame, on_error, on_train_progress=None):
        self.on_frame          = on_frame
        self.on_error          = on_error
        self.on_train_progress = on_train_progress  # callback(n, total)

        self._running       = False
        self.model          = RoomModel()
        self._prev_gray     = None
        self._prev_prep     = None
        self.sensitivity    = "Medium"
        self.camera_index   = 0
        self._last_alert    = 0.0
        self._last_gui      = 0.0
        self.sound_enabled  = True
        self.sound_preset   = "Beep x3"
        self.vd_enabled     = False
        self.vd_direction   = "next"
        self.vd_cooldown    = 5.0
        self._last_vd       = 0.0
        self._frame_count   = 0
        self._proc_count    = 0
        self._motion_streak = 0

        # training state
        self._training      = False
        self._train_frames  = []

    # ── background loading (single image fallback) ────────────
    def load_background(self, path_or_array):
        if isinstance(path_or_array, str):
            img = cv2.imread(path_or_array)
            if img is None: raise ValueError(f"Cannot read:\n{path_or_array}")
        else:
            img = path_or_array
        small = cv2.resize(img, (PROC_W, PROC_H))
        gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        # normalize before feeding to model — must match detection pipeline
        norm  = self._prep(gray)
        self.model.from_single(norm)
        self._prev_gray = None; self._prev_prep = None
        return img

    # ── start room training (collects frames in background) ───
    def start_training(self, cap):
        """Called with an open cap. Collects TRAIN_FRAMES frames, builds model."""
        self._training     = True
        self._train_frames = []
        threading.Thread(target=self._train_loop, args=(cap,), daemon=True).start()

    def _train_loop(self, cap):
        interval = 1.0 / TRAIN_FPS
        while self._training and len(self._train_frames) < TRAIN_FRAMES:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.03); continue
            small = cv2.resize(frame, (PROC_W, PROC_H))
            gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            # CRITICAL: normalize before storing — must match detection pipeline exactly
            # Detection compares cur_norm against model.mean, so training must
            # also store normalized frames, not raw gray
            norm  = self._prep(gray)
            self._train_frames.append(norm)
            n = len(self._train_frames)
            if self.on_train_progress:
                self.on_train_progress(n, TRAIN_FRAMES)
            rgb = cv2.cvtColor(cv2.resize(frame,(DISP_W,DISP_H)), cv2.COLOR_BGR2RGB)
            self.on_frame(rgb, False, 0)
            time.sleep(interval)

        if self._training and len(self._train_frames) >= TRAIN_FRAMES:
            self.model.train(self._train_frames)
            self._prev_gray = None; self._prev_prep = None
        self._training = False

    def stop_training(self):
        self._training = False

    @staticmethod
    def _prep(gray):
        """Prepare a frame for comparison: blur to reduce noise and
        equalize histogram so minor lighting shifts don't matter."""
        blurred = cv2.GaussianBlur(gray, (7, 7), 0)
        equalized = cv2.equalizeHist(blurred)
        return equalized

    def start(self):
        if self._running: return
        self._running = True
        self._frame_count   = 0
        self._proc_count    = 0
        self._motion_streak = 0
        self._prev_gray     = None
        self._prev_prep     = None
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running  = False
        self._training = False

    def _loop(self):
        try:
            cap, backend = open_camera(self.camera_index)
        except RuntimeError as e:
            self.on_error(str(e)); return

        self.on_frame(None, False, 0, info=f"[{backend}]")
        gui_interval = 1.0 / GUI_FPS

        while self._running:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.03); continue

            self._frame_count += 1

            alert, pct, boxes = False, 0.0, []

            if self._frame_count % SKIP_FRAMES == 0 and self.model.ready:
                self._proc_count += 1

                small    = cv2.resize(frame, (PROC_W, PROC_H))
                gray     = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                cur_prep = self._prep(gray)

                k, area_tv = SENSITIVITY_MAP[self.sensitivity]

                # ── GLOBAL LIGHTING GUARD ─────────────────────────
                # Sudden whole-frame brightness spike = light switch → suppress
                is_light_change = False
                if self._prev_gray is not None and self._proc_count > WARMUP_FRAMES:
                    if abs(float(np.mean(gray)) - float(np.mean(self._prev_gray))) > GLOBAL_LIGHT_THR:
                        is_light_change = True

                # ── SHAKE DETECTION ───────────────────────────────
                # >45% of pixels changed frame-to-frame = camera moved → suppress
                is_shake = False
                if self._prev_prep is not None and self._proc_count > WARMUP_FRAMES:
                    fd = cv2.absdiff(self._prev_prep, cur_prep)
                    _, fth = cv2.threshold(fd, 15, 255, cv2.THRESH_BINARY)
                    if np.count_nonzero(fth) / (PROC_W * PROC_H) > SHAKE_THRESHOLD:
                        is_shake = True

                self._prev_gray = gray
                self._prev_prep = cur_prep

                # ── VARIANCE-BASED DIFF AGAINST TRAINED MODEL ────
                # model.mean/std are in the same _prep space (blur+equalize).
                # k*std gives each pixel its own personal tolerance width.
                th = self.model.diff_mask(cur_prep, k)

                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
                th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel)
                th = cv2.dilate(th, None, iterations=2)

                cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
                big = []
                for c in cnts:
                    if cv2.contourArea(c) < area_tv: continue
                    x, y, w, h = cv2.boundingRect(c)
                    if w < MIN_BOX_W or h < MIN_BOX_H: continue
                    if w > h * 7 or h > w * 9: continue
                    big.append(c)

                if self._proc_count <= WARMUP_FRAMES or is_shake or is_light_change:
                    big = []

                pct = min(100.0,
                          sum(cv2.contourArea(c) for c in big) / (PROC_W * PROC_H) * 1000)

                if big: self._motion_streak += 1
                else:   self._motion_streak = 0

                if self._motion_streak >= CONFIRM_FRAMES:
                    sx = frame.shape[1] / PROC_W
                    sy = frame.shape[0] / PROC_H
                    for c in big:
                        x, y, w, h = cv2.boundingRect(c)
                        boxes.append((int(x*sx), int(y*sy), int(w*sx), int(h*sy)))
                    alert = True

            if boxes:
                for (x,y,w,h) in boxes:
                    cv2.rectangle(frame,(x,y),(x+w,y+h),(0,255,80),2)
                    cv2.putText(frame,"DETECTED",(x,max(y-8,14)),
                                cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,255,80),2)

            now = time.time()
            if alert:
                if self.sound_enabled and now-self._last_alert > ALERT_COOLDOWN:
                    self._last_alert = now
                    play_sound(self.sound_preset)
                if self.vd_enabled and now-self._last_vd > self.vd_cooldown:
                    self._last_vd = now
                    threading.Thread(target=_switch_desktop,
                                     args=(self.vd_direction,),daemon=True).start()

            if now - self._last_gui >= gui_interval:
                self._last_gui = now
                rgb = cv2.cvtColor(cv2.resize(frame,(DISP_W,DISP_H)),cv2.COLOR_BGR2RGB)
                self.on_frame(rgb, alert, pct)

        cap.release()


# ──────────────────────────────────────────────────────────────
# GUI
# ──────────────────────────────────────────────────────────────
class ArjunSusApp(tk.Tk):
    # ── colour palette ──────────────────────────────────────
    BG   = "#07080d"   # deep space black
    BG2  = "#0d0e16"   # panel bg
    BG3  = "#13141f"   # button bg
    BG4  = "#1a1b2e"   # highlight bg
    GRN  = "#00ffa3"   # cyber green
    RED  = "#ff2d55"   # alert red
    BLU  = "#2979ff"   # electric blue
    CYN  = "#00e5ff"   # cyan accent
    YLW  = "#ffd60a"   # caution yellow
    PRP  = "#bf5af2"   # purple accent
    DIM  = "#2a2b40"   # dim text/borders
    TXT  = "#8b8fa8"   # body text
    TXT2 = "#c8cbe8"   # bright body text

    def __init__(self):
        super().__init__()
        self.title("Arjun's Third Eye — v1.17.2")
        self.configure(bg=self.BG)
        self.minsize(MIN_W, MIN_H)
        self.resizable(True, True)

        self.detector = MotionDetector(self._on_frame, self._on_cam_error,
                                       self._on_train_progress)

        self._cameras     = list_cameras()
        self._cam_labels  = [l for _,l in self._cameras]
        self._cam_indices = [i for i,_ in self._cameras]

        self.cam_var      = tk.StringVar(value=self._cam_labels[0])
        self.sensitivity  = tk.StringVar(value="Medium")
        self.sound_var    = tk.StringVar(value="Custom MP3")
        self.sound_on_var = tk.BooleanVar(value=True)
        self.vd_on_var    = tk.BooleanVar(value=False)
        self.vd_dir_var   = tk.StringVar(value="next")
        self.vd_delay_var = tk.IntVar(value=5)
        self.bg_path_var  = tk.StringVar(value="No model loaded")

        self._live_imgtk   = None
        self._bg_imgtk     = None
        self._last_frame   = None
        self._bg_source    = None
        self._resize_job   = None
        self._vd_on        = False
        self._temp_bg_path = None
        self._snap_anim_job = None
        self._training_cap  = None   # cap held during training

        self._build_ui()
        self.bind("<Configure>", self._on_resize)

        # auto-load last saved profile if exists
        self._try_autoload_profile()

        self.update_idletasks()
        sw,sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = max(self.winfo_reqwidth(), MIN_W)
        h = max(self.winfo_reqheight(), MIN_H)
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── BUILD UI ──────────────────────────────────────────────
    def _build_ui(self):
        BG,BG2,BG3,BG4 = self.BG,self.BG2,self.BG3,self.BG4
        GRN,RED,BLU,CYN,YLW,PRP = self.GRN,self.RED,self.BLU,self.CYN,self.YLW,self.PRP
        DIM,TXT,TXT2 = self.DIM,self.TXT,self.TXT2
        P = 12

        # ── HEADER ─────────────────────────────────────────
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=P, pady=(P, 4))

        title_f = tk.Frame(hdr, bg=BG)
        title_f.pack(side="left")
        tk.Label(title_f, text="ARJUN'S", font=("Courier New",22,"bold"),
                 fg=GRN, bg=BG).pack(side="left")
        tk.Label(title_f, text=" THIRD EYE", font=("Courier New",22,"bold"),
                 fg=YLW, bg=BG).pack(side="left", padx=(4,0))
        # version + backend tag on right
        right_f = tk.Frame(hdr, bg=BG)
        right_f.pack(side="right")
        tk.Label(right_f, text="v1.17.2", font=("Courier New",8),
                 fg=DIM, bg=BG).pack(side="right", padx=(4,0))
        self.backend_lbl = tk.Label(right_f, text="", font=("Courier New",8),
                                    fg=DIM, bg=BG)
        self.backend_lbl.pack(side="right")
        # scan line decoration
        tk.Frame(hdr, bg=DIM, height=1).pack(side="bottom", fill="x")

        # ── STATUS BAR ─────────────────────────────────────
        self.status_bar = tk.Label(self,
            text="  ◈  STANDBY  ─────  Load background then press START",
            font=("Courier New",10,"bold"),
            fg=DIM, bg=BG2, anchor="w", padx=12, pady=7)
        self.status_bar.pack(fill="x", padx=P, pady=(4,6))

        # ── VIDEO PANELS ───────────────────────────────────
        vf = tk.Frame(self, bg=BG)
        vf.pack(fill="both", expand=True, padx=P)
        vf.columnconfigure(0, weight=3)
        vf.columnconfigure(1, weight=1)
        vf.rowconfigure(1, weight=1)

        # column headers with bracket style
        tk.Label(vf, text="[ LIVE FEED ]", font=("Courier New",8),
                 fg=CYN, bg=BG).grid(row=0, column=0, sticky="w", pady=(0,2))
        tk.Label(vf, text="[ REF BG ]", font=("Courier New",8),
                 fg=PRP, bg=BG).grid(row=0, column=1, sticky="w", pady=(0,2), padx=(8,0))

        self.live_canvas = tk.Canvas(vf, bg="#04040a",
                                     highlightthickness=1,
                                     highlightbackground=CYN)
        self.live_canvas.grid(row=1, column=0, sticky="nsew")

        self.bg_canvas = tk.Canvas(vf, bg="#04040a",
                                   highlightthickness=1,
                                   highlightbackground=PRP)
        self.bg_canvas.grid(row=1, column=1, sticky="nsew", padx=(8,0))

        for canvas in (self.live_canvas, self.bg_canvas):
            for seq in ("<ButtonPress>","<B1-Motion>","<B2-Motion>","<B3-Motion>",
                        "<ButtonRelease>","<MouseWheel>","<Double-Button>"):
                canvas.bind(seq, lambda e: "break")

        self.after(120, self._draw_placeholders)

        # ── MOTION METER ───────────────────────────────────
        mf = tk.Frame(self, bg=BG)
        mf.pack(fill="x", padx=P, pady=(8,2))
        tk.Label(mf, text="MOTION:", font=("Courier New",8),
                 fg=TXT, bg=BG, width=9, anchor="w").pack(side="left")
        sty = ttk.Style(); sty.theme_use("default")
        sty.configure("G.Horizontal.TProgressbar",
                      troughcolor="#0d0e16", background=GRN, thickness=12)
        self.meter = ttk.Progressbar(mf, mode="determinate", maximum=100,
                                     style="G.Horizontal.TProgressbar")
        self.meter.pack(side="left", padx=6, fill="x", expand=True)
        self.meter_lbl = tk.Label(mf, text="  0%", width=6,
                                  font=("Courier New",10,"bold"), fg=GRN, bg=BG)
        self.meter_lbl.pack(side="left")

        # ── CONTROL PANEL ──────────────────────────────────
        cp = tk.Frame(self, bg=BG2, pady=8)
        cp.pack(fill="x", padx=P, pady=(4,P))

        # thin top border on panel
        tk.Frame(cp, bg=DIM, height=1).pack(fill="x")

        # ── ROW 1 ─ camera + bg buttons ────────────────────
        r1 = tk.Frame(cp, bg=BG2)
        r1.pack(fill="x", padx=10, pady=(8,4))

        tk.Label(r1, text="CAM:", font=("Courier New",9),
                 fg=TXT, bg=BG2).pack(side="left")
        self.cam_combo = ttk.Combobox(r1, textvariable=self.cam_var,
                                       values=self._cam_labels,
                                       state="readonly", width=14,
                                       font=("Courier New",9))
        self.cam_combo.pack(side="left", padx=(4,2))
        self._tbtn(r1, "⟳", self._refresh_cameras, fg=TXT, tip="Refresh cameras"
                   ).pack(side="left", padx=(0,10))

        self._tbtn(r1, "◧  FILE BG", self._load_bg, fg=BLU,
                   tip="Load background from image file").pack(side="left", padx=(0,4))
        self.snap_btn = self._snap_button(r1)
        self.snap_btn.pack(side="left", padx=(0,4))

        # ── TRAIN ROOM BUTTON ──────────────────────────────
        self.train_btn = tk.Button(r1,
            text="🧠  TRAIN ROOM",
            command=self._train_room,
            font=("Courier New",9,"bold"),
            bg="#0e0818", fg=PRP,
            activebackground="#180d28", activeforeground=PRP,
            relief="flat", padx=10, pady=3,
            cursor="hand2", bd=0)
        self.train_btn.pack(side="left", padx=(0,4))

        self._tbtn(r1, "💾 SAVE", self._save_profile, fg=TXT).pack(side="left", padx=(0,2))
        self._tbtn(r1, "📂 LOAD", self._load_profile, fg=TXT).pack(side="left", padx=(0,8))

        self.bg_status_lbl = tk.Label(r1, textvariable=self.bg_path_var,
                 font=("Courier New",8), fg="#383850", bg=BG2,
                 wraplength=180, justify="left")
        self.bg_status_lbl.pack(side="left", padx=4)

        # training progress bar (hidden until training starts)
        self._train_bar_frame = tk.Frame(cp, bg=BG2)
        self._train_bar_frame.pack(fill="x", padx=10, pady=(0,2))
        sty.configure("T.Horizontal.TProgressbar",
                      troughcolor="#0d0e16", background=PRP, thickness=8)
        self._train_bar = ttk.Progressbar(self._train_bar_frame,
                                           mode="determinate", maximum=TRAIN_FRAMES,
                                           style="T.Horizontal.TProgressbar")
        self._train_lbl = tk.Label(self._train_bar_frame, text="",
                                   font=("Courier New",8), fg=PRP, bg=BG2)
        self._train_bar_frame.pack_forget()   # hidden initially

        # ── ROW 2 ─ sensitivity + sound ────────────────────
        r2 = tk.Frame(cp, bg=BG2)
        r2.pack(fill="x", padx=10, pady=4)
        tk.Label(r2, text="SENS:", font=("Courier New",9),
                 fg=TXT, bg=BG2).pack(side="left")
        for lbl, col in (("Low", TXT), ("Medium", CYN), ("High", YLW)):
            tk.Radiobutton(r2, text=lbl, variable=self.sensitivity, value=lbl,
                           command=self._sync, bg=BG2, fg=col,
                           selectcolor=BG4, activebackground=BG2,
                           font=("Courier New",9)).pack(side="left", padx=3)

        tk.Label(r2, text="   ◈  SOUND:", font=("Courier New",9),
                 fg=TXT, bg=BG2).pack(side="left", padx=(12,0))
        self.sound_combo = ttk.Combobox(r2, textvariable=self.sound_var,
                                         values=list(SOUND_PRESETS.keys()),
                                         state="readonly", width=13,
                                         font=("Courier New",9))
        self.sound_combo.pack(side="left", padx=(4,3))
        self.sound_combo.bind("<<ComboboxSelected>>", lambda e: self._sync())
        self._tbtn(r2, "▶", self._test_sound, fg=YLW).pack(side="left", padx=(0,8))
        tk.Checkbutton(r2, text="ON", variable=self.sound_on_var, command=self._sync,
                       bg=BG2, fg=TXT, selectcolor=BG4, activebackground=BG2,
                       font=("Courier New",8)).pack(side="left")

        # ── ROW 3 ─ desktop switch ──────────────────────────
        r3 = tk.Frame(cp, bg=BG2)
        r3.pack(fill="x", padx=10, pady=4)
        tk.Label(r3, text="DESKTOP:", font=("Courier New",9,"bold"),
                 fg=TXT, bg=BG2, width=9, anchor="w").pack(side="left")
        self.vd_btn = tk.Button(r3, text=" ■ OFF ",
                                font=("Courier New",9,"bold"),
                                bg="#1a0510", fg=RED,
                                activebackground="#250818", activeforeground=RED,
                                relief="flat", padx=12, pady=4,
                                cursor="hand2", bd=0,
                                command=self._toggle_vd)
        self.vd_btn.pack(side="left", padx=(0,10))

        tk.Label(r3, text="DIR:", font=("Courier New",8), fg=TXT, bg=BG2).pack(side="left")
        for val, txt in (("next","NEXT →"),("prev","← PREV")):
            tk.Radiobutton(r3, text=txt, variable=self.vd_dir_var, value=val,
                           bg=BG2, fg=TXT, selectcolor=BG4, activebackground=BG2,
                           font=("Courier New",8)).pack(side="left", padx=3)
        tk.Label(r3, text="  DELAY:", font=("Courier New",8),
                 fg=TXT, bg=BG2).pack(side="left")
        tk.Spinbox(r3, from_=2, to=60, textvariable=self.vd_delay_var,
                   width=3, font=("Courier New",8),
                   bg=BG4, fg=CYN, buttonbackground=DIM,
                   relief="flat", command=self._sync).pack(side="left", padx=3)
        tk.Label(r3, text="s", font=("Courier New",8), fg=DIM, bg=BG2).pack(side="left")
        self.vd_lbl = tk.Label(r3, text="", font=("Courier New",8), fg=BLU, bg=BG2)
        self.vd_lbl.pack(side="left", padx=10)

        # ── ROW 4 ─ start / stop + quick start ─────────────
        tk.Frame(cp, bg=DIM, height=1).pack(fill="x", pady=(6,0))
        r4 = tk.Frame(cp, bg=BG2)
        r4.pack(fill="x", padx=10, pady=(8,4))

        self.start_btn = self._bigbtn(r4, "▶  START", self._start, GRN)
        self.start_btn.pack(side="left", padx=(0,6))
        self.stop_btn  = self._bigbtn(r4, "■  STOP", self._stop, RED)
        self.stop_btn.pack(side="left", padx=(0,16))
        self.stop_btn.config(state="disabled")

        # QUICK START: opens camera + auto-snaps BG after 3s, no pre-loading needed
        self.qs_btn = tk.Button(r4,
            text="⚡  QUICK START  (auto-snap BG)",
            command=self._quick_start,
            font=("Courier New",9,"bold"),
            bg="#0e1020", fg=CYN,
            activebackground="#16192e", activeforeground=CYN,
            relief="flat", padx=14, pady=7,
            cursor="hand2", bd=0)
        self.qs_btn.pack(side="left")

    # ── BUTTON HELPERS ────────────────────────────────────────
    def _tbtn(self, parent, text, cmd, fg="#8b8fa8", tip=""):
        """Small techy flat button."""
        b = tk.Button(parent, text=text, command=cmd,
                      font=("Courier New",8,"bold"),
                      bg=self.BG4, fg=fg,
                      activebackground="#21223a", activeforeground=fg,
                      relief="flat", padx=8, pady=3,
                      cursor="hand2", bd=0)
        return b

    def _bigbtn(self, parent, text, cmd, fg):
        """Large primary action button with bracket border feel."""
        return tk.Button(parent, text=text, command=cmd,
                         font=("Courier New",10,"bold"),
                         bg=self.BG3, fg=fg,
                         activebackground=self.BG4, activeforeground=fg,
                         relief="flat", padx=18, pady=7,
                         cursor="hand2", bd=0)

    def _snap_button(self, parent):
        """The special snap-from-live-feed button — styled distinctly."""
        b = tk.Button(parent,
                      text="◉  SNAP BG",
                      command=self._snap_bg,
                      font=("Courier New",9,"bold"),
                      bg="#0d1a10", fg=self.GRN,
                      activebackground="#152a1a", activeforeground=self.GRN,
                      relief="flat", padx=12, pady=3,
                      cursor="hand2", bd=0)
        return b

    # ── PLACEHOLDERS ─────────────────────────────────────────
    def _draw_placeholders(self):
        items = [
            (self.live_canvas, "[ NO SIGNAL ]\n\nstart camera first", self.CYN),
            (self.bg_canvas,   "[ NO REF ]\n\nsnap or load bg",       self.PRP),
        ]
        for canvas, msg, col in items:
            canvas.update_idletasks()
            w = canvas.winfo_width()  or 200
            h = canvas.winfo_height() or 140
            canvas.delete("all")
            # draw corner brackets
            s = 14
            for x,y in [(0,0),(w-1,0),(0,h-1),(w-1,h-1)]:
                dx = s if x==0 else -s
                dy = s if y==0 else -s
                canvas.create_line(x,y, x+dx,y, fill=col, width=1)
                canvas.create_line(x,y, x,y+dy, fill=col, width=1)
            canvas.create_text(w//2, h//2, text=msg, fill=col,
                               font=("Courier New",9), justify="center")

    # ── QUICK START ───────────────────────────────────────────
    def _quick_start(self):
        """Open camera, wait 3s for it to stabilise, auto-snap BG, then monitor."""
        sel = self.cam_var.get()
        try:   idx = self._cam_indices[self._cam_labels.index(sel)]
        except: idx = 0
        self.detector.camera_index = idx
        self._sync()

        # Start camera loop first (without BG — it just streams until we snap)
        self.detector.start()
        self.start_btn.config(state="disabled")
        self.qs_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        # Count down 3s, then snap
        self._qs_countdown(3)

    def _qs_countdown(self, n):
        if n > 0:
            self.status_bar.config(
                text=f"  ⚡  QUICK START  —  Clear the area! Auto-snap in {n}s...",
                fg=self.YLW, bg="#120f00")
            self.after(1000, self._qs_countdown, n-1)
        else:
            self.status_bar.config(
                text="  ◉  SNAPPING background from live feed...",
                fg=self.CYN, bg="#060e12")
            self.after(100, self._qs_do_snap)

    def _qs_do_snap(self):
        """Auto-snap version — called from quick start, no button animation needed."""
        if self._last_frame is None:
            # frame not arrived yet — wait a bit more
            self.after(200, self._qs_do_snap)
            return
        self._capture_frame_as_bg()
        self.qs_btn.config(state="normal")

    # ── SNAP BG FROM LIVE FEED ───────────────────────────────
    def _snap_bg(self):
        if self._last_frame is None:
            messagebox.showinfo("Snap BG",
                "Start the camera first, then press SNAP BG.\n\n"
                "Tip: use  ⚡ QUICK START  to do everything automatically.")
            return
        self.snap_btn.config(state="disabled")
        self._snap_countdown(3)

    def _snap_countdown(self, n):
        if n > 0:
            self.snap_btn.config(text=f"◉  SNAP  {n}", fg=self.YLW, bg="#1a1500")
            self._snap_anim_job = self.after(700, self._snap_countdown, n-1)
        else:
            self.snap_btn.config(text="◉  CAPTURING...", fg=self.GRN, bg="#001a0a")
            self.after(80, self._do_snap)

    def _do_snap(self):
        try:
            self._capture_frame_as_bg()
        except Exception as e:
            messagebox.showerror("Snap Error", str(e))
        finally:
            self.snap_btn.config(text="◉  SNAP BG", fg=self.GRN,
                                 bg="#0d1a10", state="normal")

    def _capture_frame_as_bg(self):
        """Core logic: take _last_frame and set it as the background."""
        import tempfile
        if self._last_frame is None:
            raise RuntimeError("No live frame available.")

        bgr = cv2.cvtColor(self._last_frame, cv2.COLOR_RGB2BGR)

        # write to temp file so load_background can also accept arrays
        tmp = tempfile.NamedTemporaryFile(suffix=".png", prefix="arjunsus_bg_",
                                          delete=False)
        tmp_path = tmp.name; tmp.close()
        cv2.imwrite(tmp_path, bgr)

        if self._temp_bg_path and os.path.exists(self._temp_bg_path):
            try: os.remove(self._temp_bg_path)
            except: pass
        self._temp_bg_path = tmp_path

        # pass the array directly — no re-read needed
        img = self.detector.load_background(bgr)
        self.bg_path_var.set("⚡ LIVE SNAP  (session only)")
        self._bg_source = img
        self._blit_bg(img)

        # reset warmup
        self.detector._proc_count    = 0
        self.detector._motion_streak = 0
        self.detector._prev_gray     = None
        self.detector._prev_prep     = None

        self.status_bar.config(
            text="  ◈  BG SNAPPED  —  Monitoring active",
            fg=self.GRN, bg="#001a0a")
        self.bg_canvas.config(highlightbackground=self.GRN)
        self.after(800, lambda: self.bg_canvas.config(highlightbackground=self.PRP))

    # ── TRAIN ROOM ────────────────────────────────────────────
    def _train_room(self):
        """Open camera, collect TRAIN_FRAMES frames, build variance model."""
        if self.detector._running:
            messagebox.showinfo("Training",
                "Stop monitoring first, then click Train Room.")
            return

        sel = self.cam_var.get()
        try:   idx = self._cam_indices[self._cam_labels.index(sel)]
        except: idx = 0

        self.train_btn.config(state="disabled", text="🧠  OPENING CAM...")
        self.status_bar.config(
            text="  🧠  TRAINING  —  Clear the room, move away from camera!",
            fg=self.PRP, bg="#0e0818")

        # show training progress bar
        self._train_bar_frame.pack(fill="x", padx=10, pady=(0,4))
        self._train_bar.pack(side="left", fill="x", expand=True, padx=(0,6))
        self._train_lbl.pack(side="left")
        self._train_bar["value"] = 0

        def _open_and_train():
            try:
                cap, backend = open_camera(idx)
                self.after(0, lambda: self.train_btn.config(
                    text=f"🧠  RECORDING... [{backend}]"))
                # 2s warmup before collecting
                for _ in range(30): cap.grab(); time.sleep(0.05)
                self._training_cap = cap
                self.detector.start_training(cap)
                # poll until training done
                self._poll_training(cap)
            except Exception as e:
                err = str(e)
                self.after(0, lambda: (
                    messagebox.showerror("Training Error", err),
                    self._finish_training(None)
                ))

        threading.Thread(target=_open_and_train, daemon=True).start()

    def _poll_training(self, cap):
        if self.detector._training:
            self.after(200, self._poll_training, cap)
        else:
            self.after(0, self._finish_training, cap)

    def _finish_training(self, cap):
        if cap:
            try: cap.release()
            except: pass
        self._training_cap = None

        if self.detector.model.ready:
            # show the clean mean image in BG panel (for display only)
            # NEVER store heatmap or coloured preview in _bg_source —
            # that would corrupt detection comparisons
            preview = self.detector.model.preview_bgr()
            if preview is not None:
                self._bg_source = preview   # plain gray mean, safe to display
                self._blit_bg(preview)

            self.bg_path_var.set(f"🧠 TRAINED  ({TRAIN_FRAMES} frames)")
            self.status_bar.config(
                text="  🧠  TRAINING COMPLETE  —  Room model ready. Press START.",
                fg=self.PRP, bg="#0e0818")
        else:
            self.status_bar.config(
                text="  ✗  TRAINING FAILED  —  try again",
                fg=self.RED, bg="#1a0008")

        self._train_bar_frame.pack_forget()
        self.train_btn.config(state="normal", text="🧠  TRAIN ROOM")

    def _on_train_progress(self, n, total):
        """Called from training thread — schedule on main thread."""
        self.after(0, self._update_train_bar, n, total)

    def _update_train_bar(self, n, total):
        self._train_bar["value"] = n
        pct = int(n/total*100)
        bar = "█" * (pct//10) + "░" * (10 - pct//10)
        self._train_lbl.config(text=f" [{bar}] {pct}%  ({n}/{total})")

    # ── PROFILE SAVE / LOAD ───────────────────────────────────
    def _save_profile(self):
        if not self.detector.model.ready:
            messagebox.showinfo("Save Profile", "No model to save yet.\nTrain your room first.")
            return
        os.makedirs(_PROFILE_DIR, exist_ok=True)
        path = filedialog.asksaveasfilename(
            title="Save Room Profile",
            initialdir=_PROFILE_DIR,
            defaultextension=".npz",
            filetypes=[("Room Profile","*.npz"),("All","*.*")])
        if not path: return
        self.detector.model.save(path)
        self.bg_path_var.set(f"💾 {os.path.basename(path)}")
        self.status_bar.config(
            text=f"  💾  PROFILE SAVED  —  {os.path.basename(path)}",
            fg=self.GRN, bg="#001a0a")

    def _load_profile(self):
        path = filedialog.askopenfilename(
            title="Load Room Profile",
            initialdir=_PROFILE_DIR if os.path.isdir(_PROFILE_DIR) else ".",
            filetypes=[("Room Profile","*.npz"),("All","*.*")])
        if not path: return
        try:
            self.detector.model.load(path)
            # show clean mean preview — display only, does NOT affect detection
            preview = self.detector.model.preview_bgr()
            if preview is not None:
                self._bg_source = preview
                self._blit_bg(preview)
            self.bg_path_var.set(f"📂 {os.path.basename(path)}")
            self.status_bar.config(
                text=f"  📂  PROFILE LOADED  —  Press START to monitor",
                fg=self.BLU, bg="#080b18")
        except Exception as e:
            messagebox.showerror("Load Error", str(e))

    def _try_autoload_profile(self):
        """Silently load 'default.npz' from profiles dir if it exists."""
        default = os.path.join(_PROFILE_DIR, "default.npz")
        if os.path.exists(default):
            try:
                self.detector.model.load(default)
                preview = self.detector.model.preview_bgr()
                if preview is not None:
                    self._bg_source = preview
                self.bg_path_var.set("📂 default.npz  (auto-loaded)")
            except Exception:
                pass

    # ── TOGGLE DESKTOP ────────────────────────────────────────
    def _toggle_vd(self):
        self._vd_on = not self._vd_on
        if self._vd_on:
            self.vd_btn.config(text=" ◆ ON  ",fg=self.GRN,
                               bg="#091a0e",activebackground="#0e2614",
                               activeforeground=self.GRN)
        else:
            self.vd_btn.config(text=" ■ OFF ",fg=self.RED,
                               bg="#1a0510",activebackground="#250818",
                               activeforeground=self.RED)
            self.vd_lbl.config(text="")
        self.vd_on_var.set(self._vd_on)
        self._sync()

    # ── CAMERA REFRESH ────────────────────────────────────────
    def _refresh_cameras(self):
        self._cameras     = list_cameras()
        self._cam_labels  = [l for _,l in self._cameras]
        self._cam_indices = [i for i,_ in self._cameras]
        self.cam_combo["values"] = self._cam_labels
        self.cam_var.set(self._cam_labels[0])

    def _test_sound(self):
        play_sound(self.sound_var.get())

    # ── RESIZE ────────────────────────────────────────────────
    def _on_resize(self, event=None):
        if self._resize_job: self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._redraw_all)

    def _redraw_all(self):
        if self._last_frame is not None:
            self._blit_live(self._last_frame)
        elif self._bg_source is None:
            self._draw_placeholders()
        if self._bg_source is not None:
            self._blit_bg(self._bg_source)

    def _blit_live(self, frame_rgb):
        self.live_canvas.update_idletasks()
        cw = self.live_canvas.winfo_width()
        ch = self.live_canvas.winfo_height()
        if cw < 4 or ch < 4: return
        imgtk = ImageTk.PhotoImage(
            Image.fromarray(cv2.resize(frame_rgb, (cw, ch))))
        self._live_imgtk = imgtk
        self.live_canvas.delete("all")
        self.live_canvas.create_image(0, 0, anchor="nw", image=imgtk)

    def _blit_bg(self, img_bgr):
        self.bg_canvas.update_idletasks()
        cw = self.bg_canvas.winfo_width()  or 160
        ch = self.bg_canvas.winfo_height() or 120
        rgb   = cv2.cvtColor(cv2.resize(img_bgr, (cw, ch)), cv2.COLOR_BGR2RGB)
        imgtk = ImageTk.PhotoImage(Image.fromarray(rgb))
        self._bg_imgtk = imgtk
        self.bg_canvas.delete("all")
        self.bg_canvas.create_image(0, 0, anchor="nw", image=imgtk)

    # ── ACTIONS ───────────────────────────────────────────────
    def _load_bg(self):
        path = filedialog.askopenfilename(
            title="Select Reference Background Image",
            filetypes=[("Images","*.jpg *.jpeg *.png *.bmp *.tiff *.webp"),
                       ("All files","*.*")])
        if not path: return
        try:
            img = self.detector.load_background(path)
            self.bg_path_var.set(os.path.basename(path))
            self._bg_source = img
            self._blit_bg(img)
            self.status_bar.config(
                text="  ◈  BG LOADED  —  Press START MONITORING",
                fg=self.BLU, bg="#080b18")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _start(self):
        if not self.detector.model.ready:
            messagebox.showwarning("No Background",
                "No background loaded yet.\n\n"
                "Options:\n"
                "► Click  ⚡ QUICK START  — opens camera and auto-snaps BG in 3s\n"
                "► Click  ◉ SNAP BG  after starting camera manually\n"
                "► Click  ◧ FILE BG  to load a saved image")
            return
        sel = self.cam_var.get()
        try:   idx = self._cam_indices[self._cam_labels.index(sel)]
        except: idx = 0
        self.detector.camera_index = idx
        self._sync()
        self.detector.start()
        self.start_btn.config(state="disabled")
        self.qs_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_bar.config(
            text=f"  ◈  INITIALISING  —  Opening {sel}...",
            fg=self.TXT, bg=self.BG2)

    def _stop(self):
        self.detector.stop()
        self.start_btn.config(state="normal")
        self.qs_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_bar.config(
            text="  ■  STOPPED", fg=self.TXT, bg=self.BG2)
        self._last_frame = None
        self.live_canvas.delete("all")
        cw = self.live_canvas.winfo_width()  or 200
        ch = self.live_canvas.winfo_height() or 140
        self.live_canvas.config(highlightbackground=self.CYN)
        self.live_canvas.create_text(cw//2, ch//2,
            text="[ SIGNAL LOST ]", fill=self.DIM,
            font=("Courier New",10))

    def _sync(self):
        self.detector.sensitivity   = self.sensitivity.get()
        self.detector.sound_enabled = self.sound_on_var.get()
        self.detector.sound_preset  = self.sound_var.get()
        self.detector.vd_enabled    = self.vd_on_var.get()
        self.detector.vd_direction  = self.vd_dir_var.get()
        self.detector.vd_cooldown   = self.vd_delay_var.get()

    # ── FRAME / ERROR CALLBACKS ───────────────────────────────
    def _on_cam_error(self, msg):
        self.after(0, lambda: (messagebox.showerror("Camera Error", msg),
                               self._stop()))

    def _on_frame(self, frame_rgb, alert, pct, info=None):
        self.after(0, self._update_gui, frame_rgb, alert, pct, info)

    def _update_gui(self, frame_rgb, alert, pct, info):
        if info: self.backend_lbl.config(text=info)
        if frame_rgb is not None:
            self._last_frame = frame_rgb
            self._blit_live(frame_rgb)
        self.meter["value"] = min(pct, 100)
        self.meter_lbl.config(text=f"{int(pct):3d}%")

        wf = self.detector._proc_count
        if wf <= WARMUP_FRAMES and self.detector._running:
            pct_done = int(wf / WARMUP_FRAMES * 100)
            bar = "█" * (pct_done // 10) + "░" * (10 - pct_done // 10)
            self.status_bar.config(
                text=f"  ◌  CALIBRATING  [{bar}]  {pct_done}%",
                fg=self.YLW, bg="#120f00")
            return

        if alert:
            self.status_bar.config(
                text="  ⚠  INTRUDER DETECTED  ——  Someone is behind you, Arjun!",
                fg=self.RED, bg="#1a0008")
            self.live_canvas.config(highlightbackground=self.RED)
            if self.vd_on_var.get():
                self.vd_lbl.config(
                    text=f"↪ {time.strftime('%H:%M:%S')}")
        else:
            if frame_rgb is not None:
                self.status_bar.config(
                    text="  ◈  MONITORING  ──  All clear, Arjun",
                    fg=self.GRN, bg="#001208")
                self.live_canvas.config(highlightbackground=self.CYN)

    def _on_close(self):
        self.detector.stop()
        # delete temp snapshot file if it exists
        if self._temp_bg_path and os.path.exists(self._temp_bg_path):
            try:
                os.remove(self._temp_bg_path)
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    app = ArjunSusApp()
    app.mainloop()
