# ⬡ SENTINEL — Motion Guard

A Windows 10 desktop application that uses your webcam + a reference background photo
to detect intruders or unexpected movement and trigger audio/visual alerts.

---

## How It Works

1. You provide a **still photo of your empty background** (your room, doorway, etc.)
2. SENTINEL continuously compares the **live camera feed** against that reference
3. When pixels differ significantly (a person walks in), it:
   - Draws **red bounding boxes** around the moving area
   - Flashes a **red ALERT banner**
   - Plays **beeping warning sounds**
   - Shows a **motion intensity meter**

---

## Quick Start

### Requirements
- Windows 10
- Python 3.8+ (https://python.org) — tick "Add to PATH" during install
- A webcam

### Steps
1. Double-click **`RUN_SENTINEL.bat`** — it auto-installs deps and launches the app
2. Click **"Load Background Image"** and select your reference photo
3. Optionally change **Sensitivity** and **Camera #**
4. Click **"▶ Start Monitoring"**

---

## Tips for Best Results

| Tip | Why |
|-----|-----|
| Take the background photo with the **same camera** | Ensures color/lighting match |
| Keep **lighting consistent** (no sunlight shifting) | Reduces false positives |
| Use **Medium sensitivity** to start | Low = misses subtle movement, High = many false alarms |
| Camera should be **mounted still** | Any camera shake = false alert |
| Background photo should be **640×480 or similar** | App auto-resizes, but native res is best |

---

## Controls

| Control | Description |
|---------|-------------|
| Load Background Image | Pick your reference empty-room photo |
| Sensitivity Low/Medium/High | How different pixels must be to count as motion |
| Cam # | If you have multiple cameras, pick the right index (0, 1, 2…) |
| 🔔 Sound | Toggle the beep alert on/off |
| ▶ Start / ■ Stop | Start or stop monitoring |

---

## Files

```
sentinel/
├── sentinel.py        ← main application
├── requirements.txt   ← Python dependencies
├── RUN_SENTINEL.bat   ← double-click to run on Windows
└── README.md          ← this file
```

---

## Dependencies

- `opencv-python` — camera capture + image comparison
- `Pillow` — displaying frames in the GUI
- `numpy` — pixel math
- `tkinter` — GUI (built into Python)
- `winsound` — alert beeps (built into Windows Python, no install needed)

## preview

<img width="854" height="663" alt="image" src="https://github.com/user-attachments/assets/7a79b3e1-5111-4cec-926d-24b00acb679b" />
