"""JS-Keypad Profile - switches the keypad's key profile automatically when a game is in the foreground.

Profiles live on the keypad (firmware 1.4+), so this app and the web mapper edit the same set:
    PLIST / PGET / PSET / PDEL / PUSE   (see firmware/js_keypad/js_keypad.ino)
The serial port is only opened for a moment per command, so the web mapper can connect at any time.
The window ("Profile und Tasten bearbeiten") is the web mapper bundled with the app, served offline from localhost and
shown in an Edge app window. While it is connected it holds the serial port; then the page does the switching itself
and asks this app which program is in front (/api/foreground).
Start: opens the window (with --tray only the tray icon, used for the Windows autostart). A second start brings the
running copy's window to the front.
Profile 0 is the standard mapping (GET/SET); switching (PUSE) is RAM only, after unplugging the keypad
starts with the standard mapping and this app sets the right profile again.
"""
import ctypes
import glob
import json
import re
import os
import sys
import threading
import time
import functools
import http.server
import shutil
import subprocess
import urllib.parse
import urllib.request
import webbrowser
import winreg
from ctypes import wintypes
from pathlib import Path

import psutil
import pystray
import serial
from PIL import Image
from serial.tools import list_ports

APP_NAME = "JS-Keypad Profile"
USB_VID, USB_PID = 0x1209, 0x0003
NUM_SLOTS = 18  # 0..11 finger keys, 12 thumb key, 13..17 stick up/down/left/right/click
MAX_PROFILES = 8
POLL_SECONDS = 0.7
SETTINGS_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
MAPPER_PORT = 47811
PORT_FILE = SETTINGS_DIR / "port"          # HTTP port of the running copy, a second start talks to it
WINDOW_TITLE = "JS-Keypad"                   # <title> of the mapper page = title of its Edge app window
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]


def window_title(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def window_exe(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        return psutil.Process(pid.value).name()
    except (psutil.Error, ValueError):
        return ""


def is_mapper_window(hwnd):
    return window_title(hwnd) == WINDOW_TITLE and window_exe(hwnd).lower() in ("msedge.exe", "chrome.exe")


def foreground_exe():
    """Process name of the window in front; None while that is our own mapper window (keep the profile)."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    if is_mapper_window(hwnd):
        return None
    return window_exe(hwnd)


class ForegroundWatch(threading.Thread):
    """Notices a change of the program in front within 0.1 s; the switcher and the mapper page (long poll) wait on it."""

    def __init__(self):
        super().__init__(daemon=True)
        self.cond = threading.Condition()
        self.seq = 0
        self.exe = foreground_exe()

    def run(self):
        last = None
        while True:
            hwnd = user32.GetForegroundWindow()
            if hwnd != last:
                last = hwnd
                exe = foreground_exe()
                if exe != self.exe:
                    self.changed(exe)
            time.sleep(0.1)

    def changed(self, exe=None, keep_exe=False):
        with self.cond:
            if not keep_exe:
                self.exe = exe
            self.seq += 1
            self.cond.notify_all()

    def wait(self, seq, timeout):
        """Waits until something changed after `seq` (or the timeout), returns (seq, exe)."""
        with self.cond:
            self.cond.wait_for(lambda: self.seq != seq, timeout)
            return self.seq, self.exe


def find_mapper_window():
    found = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def check(hwnd, _):
        if user32.IsWindowVisible(hwnd) and is_mapper_window(hwnd):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(enum_proc(check), 0)
    return found[0] if found else None


def bring_to_front(hwnd):
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)                  # SW_RESTORE
    # Windows only lets the foreground process take the focus: a short Alt press lifts that lock
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)


def running_window_programs():
    """Process names of programs that currently have a window (for the program picker)."""
    names = set()
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def collect(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                names.add(psutil.Process(pid.value).name())
            except (psutil.Error, ValueError):
                pass
        return True

    user32.EnumWindows(enum_proc(collect), 0)
    names.discard(Path(sys.executable).name)
    return sorted(names, key=str.lower)


# ---------------------------------------------------------------------------------------------------------------
# Program icons for the profile list: from the exe file (running process, or found in the Epic/Steam game folders -
# anti-cheat games like Fortnite hide their process path), else from the program's window. Cached as PNG.
# ---------------------------------------------------------------------------------------------------------------
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
ICON_DIR = SETTINGS_DIR / "icons"
ICON_SIZE = 64


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
                ("hbmMask", wintypes.HBITMAP), ("hbmColor", wintypes.HBITMAP)]


class BITMAP(ctypes.Structure):
    _fields_ = [("bmType", wintypes.LONG), ("bmWidth", wintypes.LONG), ("bmHeight", wintypes.LONG),
                ("bmWidthBytes", wintypes.LONG), ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                ("bmBits", ctypes.c_void_p)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


user32.PrivateExtractIconsW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.UINT), wintypes.UINT,
                                        wintypes.UINT]
user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(ICONINFO)]
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.UINT,
                                       wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
user32.GetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetClassLongPtrW.restype = ctypes.c_size_t
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                            ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT]
gdi32.GetObjectW.argtypes = [wintypes.HGDIOBJ, ctypes.c_int, ctypes.c_void_p]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]


def _bitmap_rgba(hdc, hbm):
    bm = BITMAP()
    if not gdi32.GetObjectW(hbm, ctypes.sizeof(bm), ctypes.byref(bm)) or bm.bmWidth <= 0:
        return None
    w, h = bm.bmWidth, bm.bmHeight
    bih = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    if not gdi32.GetDIBits(hdc, hbm, 0, h, buf, ctypes.byref(bih), 0):
        return None
    return Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1).copy()


def icon_image(hicon):
    """HICON -> RGBA image (keeps the alpha channel; old icons without one get it from their mask)."""
    info = ICONINFO()
    if not user32.GetIconInfo(hicon, ctypes.byref(info)):
        return None
    hdc = user32.GetDC(None)
    try:
        if not info.hbmColor:
            return None
        img = _bitmap_rgba(hdc, info.hbmColor)
        if img and img.getchannel("A").getextrema()[1] == 0 and info.hbmMask:
            mask = _bitmap_rgba(hdc, info.hbmMask)
            if mask and mask.size == img.size:
                img.putalpha(mask.convert("L").point(lambda v: 0 if v else 255))
        return img
    finally:
        user32.ReleaseDC(None, hdc)
        for hbm in (info.hbmColor, info.hbmMask):
            if hbm:
                gdi32.DeleteObject(hbm)


def file_icon(path):
    hicon = wintypes.HICON()
    if user32.PrivateExtractIconsW(str(path), 0, ICON_SIZE, ICON_SIZE, ctypes.byref(hicon), None, 1, 0) != 1 or not hicon:
        return None
    try:
        return icon_image(hicon)
    finally:
        user32.DestroyIcon(hicon)


def window_icon(exe):
    """Icon of a visible window of that program (works for protected game processes too)."""
    found = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def check(hwnd, _):
        if user32.IsWindowVisible(hwnd) and window_exe(hwnd).lower() == exe:
            found.append(hwnd)
        return True

    user32.EnumWindows(enum_proc(check), 0)
    for hwnd in found:
        result = ctypes.c_size_t(0)
        user32.SendMessageTimeoutW(hwnd, 0x7F, 1, 0, 0x2, 300, ctypes.byref(result))   # WM_GETICON, ICON_BIG
        hicon = result.value or user32.GetClassLongPtrW(hwnd, -14)                    # GCLP_HICON
        if hicon:
            img = icon_image(hicon)                                                    # owned by the window
            if img:
                return img
    return None


def game_folders():
    """Install folders of Epic and Steam games."""
    folders = []
    for item in glob.glob(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests\*.item"):
        try:
            folders.append(json.loads(Path(item).read_text(encoding="utf-8"))["InstallLocation"])
        except (OSError, ValueError, KeyError):
            pass
    vdf = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam" / "steamapps" / "libraryfolders.vdf"
    try:
        for lib in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="replace")):
            common = Path(lib.replace("\\\\", "\\")) / "steamapps" / "common"
            if common.is_dir():
                folders += [str(d) for d in common.iterdir() if d.is_dir()]
    except OSError:
        pass
    return folders


def search_game_exe(exe):
    skip = {"content", "paks", "movies", "data", "localization", "shadercache", "logs", "saved"}
    for root in game_folders():
        base = len(Path(root).parts)
        for folder, dirs, files in os.walk(root):
            if any(f.lower() == exe for f in files):
                return Path(folder) / next(f for f in files if f.lower() == exe)
            depth = len(Path(folder).parts) - base
            dirs[:] = [] if depth >= 5 else [d for d in dirs if d.lower() not in skip]
    return None


_icon_lock = threading.Lock()
_icon_missing = {}      # exe -> time of the last failed try (the program may be started later)


def program_icon_png(exe):
    """PNG bytes of the program's icon, or None. exe: process name like FortniteClient-Win64-Shipping.exe"""
    exe = exe.strip().lower()
    if not re.fullmatch(r"[\w .()+-]{1,60}\.exe", exe):
        return None
    cached = ICON_DIR / (exe[:-4] + ".png")
    if cached.exists():
        return cached.read_bytes()
    if time.time() - _icon_missing.get(exe, 0) < 30:
        return None
    with _icon_lock:
        img = None
        for p in psutil.process_iter(["name", "exe"]):
            if (p.info["name"] or "").lower() == exe and p.info["exe"]:
                img = file_icon(p.info["exe"])
                break
        if img is None:
            path = search_game_exe(exe)
            img = file_icon(path) if path else None
        if img is None:
            img = window_icon(exe)
        if img is None or img.getchannel("A").getextrema()[1] == 0:
            _icon_missing[exe] = time.time()
            return None
        if img.size != (ICON_SIZE, ICON_SIZE):
            img = img.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
        ICON_DIR.mkdir(parents=True, exist_ok=True)
        img.save(cached)
        return cached.read_bytes()


# ---------------------------------------------------------------------------------------------------------------
# Keypad (serial, one short connection per call)
# ---------------------------------------------------------------------------------------------------------------
class KeypadBusy(Exception):
    """Port exists but cannot be opened (web mapper or another program is connected)."""


class Keypad:
    def __init__(self):
        self.lock = threading.Lock()

    @staticmethod
    def find_port():
        for p in list_ports.comports():
            if p.vid == USB_VID and p.pid == USB_PID:
                return p.device
        return None

    def talk(self, commands, until=None):
        """Sends each command, returns the reply line per command (or all lines up to `until` for the last)."""
        port = self.find_port()
        if not port:
            return None
        with self.lock:
            try:
                ser = serial.Serial(port, 115200, timeout=1.5, write_timeout=1.5)
            except (serial.SerialException, OSError) as e:
                raise KeypadBusy(str(e))
            try:
                ser.dtr = True
                ser.reset_input_buffer()
                replies = []
                for n, cmd in enumerate(commands):
                    ser.write((cmd + "\n").encode("ascii", "replace"))
                    if until and n == len(commands) - 1:
                        lines = []
                        deadline = time.time() + 3
                        while time.time() < deadline:
                            line = ser.readline().decode("utf-8", "replace").strip()
                            if line:
                                lines.append(line)
                            if line == until or line == "ERR":
                                break
                        replies.append(lines)
                    else:
                        replies.append(ser.readline().decode("utf-8", "replace").strip())
                return replies
            finally:
                ser.close()

    def version(self):
        r = self.talk(["VER"])
        return r[0][4:].strip() if r and r[0].startswith("VER ") else None

    def load_all(self):
        """(standard keys, threshold, active index, [profile dict]) or None without keypad."""
        cmds = ["GET", "PUSE"] + [f"PGET {i}" for i in range(1, MAX_PROFILES + 1)]
        r = self.talk(cmds)
        if not r:
            return None
        cfg = r[0].split()
        if cfg[0] != "CFG" or len(cfg) < NUM_SLOTS + 2:
            raise RuntimeError("Unerwartete Antwort vom Keypad: " + r[0])
        std = [int(v) for v in cfg[1:NUM_SLOTS + 1]]
        thr = int(cfg[NUM_SLOTS + 1])
        if not r[1].startswith("PUSE "):
            raise RuntimeError("Firmware zu alt - bitte im Web-Mapper auf 1.4 oder neuer aktualisieren.")
        active = int(r[1][5:])
        profiles = []
        for line in r[2:]:
            if not line.startswith("PDAT "):
                continue
            parts = line[5:].split("|")
            nums = [int(v) for v in parts[3].split()]
            profiles.append({"i": int(parts[0]), "name": parts[1], "exe": parts[2],
                             "keys": nums[:NUM_SLOTS], "threshold": nums[NUM_SLOTS]})
        return std, thr, active, profiles

    def ok(self, cmd):  # noqa: D102
        r = self.talk([cmd])
        return bool(r) and r[0] == "OK"


# ---------------------------------------------------------------------------------------------------------------
# Settings, autostart
# ---------------------------------------------------------------------------------------------------------------
def load_settings():
    try:
        return {"auto": True, "notify": True, **json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return {"auto": True, "notify": True}


def save_settings(settings):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def autostart_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw}" "{Path(__file__).resolve()}" --tray'


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(on):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except OSError:
                pass


def resource_dir():
    return Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


@functools.lru_cache(maxsize=None)
def tray_image(active=False):
    """The JS-Keypad logo (tools/make_logo.py); a green dot while a game profile is active."""
    return Image.open(resource_dir() / ("tray-active.png" if active else "tray.png")).convert("RGBA")


# ---------------------------------------------------------------------------------------------------------------
# Background switcher
# ---------------------------------------------------------------------------------------------------------------
class Switcher(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.app = app
        self.profiles = []          # cached [{i, name, exe}]
        self.applied = None         # profile index last set on the keypad, None = unknown
        self.port = None
        self.status = "Suche Keypad…"
        self.reload_needed = True
        self.next_reload = 0
        self.seen = 0

    def run(self):
        while not self.app.quitting:
            try:
                self.tick()
            except KeypadBusy:
                # The mapper window holds the port: the page switches the profiles itself (/api/foreground)
                self.set_status("Fenster ist verbunden – es schaltet die Profile um")
                self.applied = None
            except Exception as e:  # noqa: BLE001 - keep the tray app alive
                self.set_status(f"Fehler: {e}")
                self.applied = None
            self.seen = self.app.fg.wait(self.seen, POLL_SECONDS)[0]   # wakes at once when the window changes

    def set_status(self, text):
        if text != self.status:
            self.status = text
            self.app.update_tray()

    def tick(self):
        port = Keypad.find_port()
        if port != self.port:            # plugged in / out: the keypad starts with the standard map
            self.port, self.applied, self.reload_needed = port, None, True
        if not port:
            self.set_status("Kein Keypad gefunden")
            return
        if self.reload_needed or time.time() > self.next_reload:
            data = self.app.keypad.load_all()
            if data is None:
                return
            self.profiles = data[3]
            self.applied = data[2]          # what the keypad really has (the mapper may have switched)
            self.reload_needed = False
            self.next_reload = time.time() + 5
        want = self.wanted_profile()
        if want != self.applied:
            if self.app.keypad.ok(f"PUSE {want}"):
                self.applied = want
                self.app.notify_switch(self.profile_name(want))
        self.set_status(f"Aktiv: {self.profile_name(self.applied)}")

    def wanted_profile(self):
        if not self.app.settings.get("auto", True):
            return self.applied            # switching off: leave the keypad as it is
        exe = foreground_exe()
        if exe is None:                    # our own window is in front: keep what is active
            return self.applied
        exe = exe.lower()
        for p in self.profiles:
            if p["exe"] and p["exe"].lower() == exe:
                return p["i"]
        return 0

    def profile_name(self, index):
        if not index:
            return "Standardbelegung"
        for p in self.profiles:
            if p["i"] == index:
                return p["name"]
        return f"Profil {index}"


# ---------------------------------------------------------------------------------------------------------------
# Local web mapper: the same page as on GitHub Pages, bundled with the app and served offline, opened in an Edge
# app window. Web Serial works there (localhost is a secure context).
# ---------------------------------------------------------------------------------------------------------------
def mapper_dir():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "docs"
    return Path(__file__).resolve().parent.parent / "docs"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    app = None  # set by App

    def log_message(self, *args):
        pass

    def send_json(self, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # /api/* only exists in the local copy, the online mapper gets 404 and does without
        path, _, query = self.path.partition("?")
        app = QuietHandler.app
        if path == "/api/programs":
            return self.send_json(running_window_programs())
        if path == "/api/foreground":                 # ?seq=N: long poll, answers when it changed (or after 20 s)
            seq = urllib.parse.parse_qs(query).get("seq", [""])[0]
            current, exe = app.fg.wait(int(seq), 20) if seq.lstrip("-").isdigit() else (app.fg.seq, app.fg.exe)
            return self.send_json({"seq": current, "exe": exe, "auto": app.settings.get("auto", True)})
        if path == "/api/switched":
            name = urllib.parse.parse_qs(query).get("name", ["?"])[0][:40]
            app.notify_switch(name)
            return self.send_json(True)
        if path == "/api/icon":
            png = program_icon_png(urllib.parse.parse_qs(query).get("exe", [""])[0])
            if not png:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(png)))
            self.end_headers()
            self.wfile.write(png)
            return
        if path == "/api/settings":                   # ?auto=0|1&notify=0|1&autostart=0|1 changes, then reports
            for key, value in urllib.parse.parse_qs(query).items():
                on = value[0] == "1"
                if key == "autostart":
                    set_autostart(on)
                elif key in ("auto", "notify"):
                    app.settings[key] = on
                    save_settings(app.settings)
                    if key == "auto":
                        app.fg.changed(keep_exe=True)
            app.update_tray()
            return self.send_json({"auto": app.settings.get("auto", True), "notify": app.settings.get("notify", True),
                                   "autostart": autostart_enabled()})
        if path == "/api/show":                       # a second start of the app
            app.open_mapper()
            return self.send_json(True)
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def start_mapper_server():
    handler = functools.partial(QuietHandler, directory=str(mapper_dir()))
    # Fixed port: Edge remembers the serial permission per origin, so the window can reconnect by itself
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", MAPPER_PORT), handler)
    except OSError:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


def find_edge():
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            exe = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if exe.exists():
                return str(exe)
    return shutil.which("msedge") or shutil.which("chrome")


# ---------------------------------------------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------------------------------------------
class App:
    def __init__(self):
        self.quitting = False
        self.settings = load_settings()
        self.keypad = Keypad()
        self.fg = ForegroundWatch()
        self.fg.start()
        self.mapper_port = start_mapper_server()
        self.switcher = Switcher(self)
        QuietHandler.app = self
        try:
            SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
            PORT_FILE.write_text(str(self.mapper_port), encoding="ascii")
        except OSError:
            pass
        self.icon = pystray.Icon(APP_NAME, tray_image(), APP_NAME, menu=pystray.Menu(
            pystray.MenuItem(lambda item: self.switcher.status, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Profile und Tasten bearbeiten …", self.open_mapper, default=True),
            pystray.MenuItem("Automatisch umschalten", self.toggle_auto,
                             checked=lambda item: self.settings.get("auto", True)),
            pystray.MenuItem("Meldung beim Umschalten", self.toggle_notify,
                             checked=lambda item: self.settings.get("notify", True)),
            pystray.MenuItem("Mit Windows starten", self.toggle_autostart, checked=lambda item: autostart_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Beenden", self.quit),
        ))

    def open_mapper(self, icon=None, item=None):
        hwnd = find_mapper_window()
        if hwnd:                                    # only one window: bring the open one to the front
            bring_to_front(hwnd)
            return
        url = f"http://127.0.0.1:{self.mapper_port}/index.html"
        edge = find_edge()
        if edge:
            subprocess.Popen([edge, f"--app={url}", "--window-size=1280,860", "--disable-background-timer-throttling",
                              "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding"])
        else:
            webbrowser.open(url)

    def update_tray(self):
        try:
            self.icon.title = f"{APP_NAME} – {self.switcher.status}"[:127]
            self.icon.icon = tray_image(active=bool(self.switcher.applied))
            self.icon.update_menu()
        except Exception:  # noqa: BLE001 - tray not ready yet
            pass

    def notify_switch(self, name):
        if self.settings.get("notify", True):
            try:
                self.icon.notify(f"Profil: {name}", APP_NAME)
            except Exception:  # noqa: BLE001
                pass

    def toggle_auto(self, icon, item):
        self.settings["auto"] = not self.settings.get("auto", True)
        save_settings(self.settings)
        self.fg.changed(keep_exe=True)              # the page re-reads "auto" right away

    def toggle_notify(self, icon, item):
        self.settings["notify"] = not self.settings.get("notify", True)
        save_settings(self.settings)

    def toggle_autostart(self, icon, item):
        set_autostart(not autostart_enabled())

    def quit(self, icon=None, item=None):
        self.quitting = True
        self.icon.stop()

    def run(self):
        self.switcher.start()
        if "--tray" not in sys.argv:                 # Windows autostart: only the tray icon
            threading.Timer(0.3, self.open_mapper).start()
        self.icon.run()


def single_instance():
    """Only one copy may run (two would fight over the serial port)."""
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "JS-Keypad-Profile-Mutex")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        if "--tray" not in sys.argv:              # show the running copy's window instead of a second program
            try:
                port = int(PORT_FILE.read_text(encoding="ascii"))
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/show", timeout=3).read()
            except (OSError, ValueError):
                ctypes.windll.user32.MessageBoxW(None, f"{APP_NAME} läuft bereits – Symbol unten rechts neben der Uhr.",
                                                 APP_NAME, 0x40)
        sys.exit(0)
    return mutex


if __name__ == "__main__":
    _mutex = single_instance()
    App().run()
