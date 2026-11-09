"""Windows driver built directly on user32 via ctypes.

Deliberately dependency-free: no pyautogui, no pywin32. ``SendInput`` with
scancodes is what games, terminals and Electron apps actually listen to, and
DirectInput-style consumers ignore the ``keybd_event`` path that the common
libraries still use.
"""

from __future__ import annotations

import ctypes
import subprocess
import time
from ctypes import wintypes
from typing import Optional, Sequence

from .base import Driver, WindowInfo

try:  # pragma: no cover - import guard, exercised only off-Windows
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _WINDOWS = True
except (AttributeError, OSError):  # pragma: no cover
    user32 = kernel32 = None  # type: ignore[assignment]
    _WINDOWS = False


# --- virtual key codes -------------------------------------------------
VK = {
    "backspace": 0x08, "tab": 0x09, "clear": 0x0C, "enter": 0x0D, "return": 0x0D,
    "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12, "menu": 0x12,
    "pause": 0x13, "capslock": 0x14, "escape": 0x1B, "esc": 0x1B, "space": 0x20,
    "pageup": 0x21, "pgup": 0x21, "pagedown": 0x22, "pgdn": 0x22,
    "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "select": 0x29, "print": 0x2A, "printscreen": 0x2C, "insert": 0x2D,
    "delete": 0x2E, "del": 0x2E, "help": 0x2F,
    "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C, "apps": 0x5D, "menukey": 0x5D,
    "numlock": 0x90, "scrolllock": 0x91,
    "add": 0x6B, "subtract": 0x6D, "multiply": 0x6A, "divide": 0x6F, "decimal": 0x6E,
    "volumemute": 0xAD, "volumedown": 0xAE, "volumeup": 0xAF,
    "medianext": 0xB0, "mediaprev": 0xB1, "mediastop": 0xB2, "mediaplay": 0xB3,
    ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF,
    "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
}
VK.update({str(d): 0x30 + d for d in range(10)})
VK.update({chr(c): c for c in range(ord("A"), ord("Z") + 1)})
VK.update({chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)})
VK.update({f"f{n}": 0x6F + n for n in range(1, 25)})       # F1..F24 -> 0x70..
VK.update({f"num{d}": 0x60 + d for d in range(10)})        # numpad

MODIFIERS = {"ctrl", "control", "alt", "shift", "win", "lwin", "rwin"}

#: Keys on the extended-key half of the keyboard need KEYEVENTF_EXTENDEDKEY,
#: or apps read the numpad twin instead (arrow keys are the usual casualty).
EXTENDED = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E,
    0x5B, 0x5C, 0x5D, 0x90, 0x6F,
}

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x0001, 0x0002
KEYEVENTF_UNICODE, KEYEVENTF_SCANCODE = 0x0004, 0x0008

MOUSEEVENTF = {
    "move": 0x0001, "absolute": 0x8000,
    "leftdown": 0x0002, "leftup": 0x0004,
    "rightdown": 0x0008, "rightup": 0x0010,
    "middledown": 0x0020, "middleup": 0x0040,
    "wheel": 0x0800, "hwheel": 0x1000,
}
WHEEL_DELTA = 120

SW_MINIMIZE, SW_MAXIMIZE, SW_RESTORE, SW_SHOW = 6, 3, 9, 5
WM_CLOSE = 0x0010


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _declare() -> None:
    """Pin argtypes/restypes. ctypes defaults returns to ``c_int``, which
    silently truncates 64-bit HWNDs and HANDLEs."""
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.BringWindowToTop.argtypes = (wintypes.HWND,)
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.IsIconic.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.PostMessageW.argtypes = (
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    )
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
    user32.MapVirtualKeyW.restype = wintypes.UINT
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    )


if _WINDOWS:  # pragma: no cover - Windows only
    _declare()


def _send(*inputs: INPUT) -> None:
    array = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise OSError(f"SendInput sent {sent}/{len(inputs)}: {ctypes.get_last_error()}")


def _key_input(vk: int, up: bool) -> INPUT:
    scan = user32.MapVirtualKeyW(vk, 0)
    flags = KEYEVENTF_SCANCODE
    if vk in EXTENDED:
        flags |= KEYEVENTF_EXTENDEDKEY
    if up:
        flags |= KEYEVENTF_KEYUP
    # Some VKs have no scancode (media keys); fall back to the VK path.
    if scan == 0:
        flags &= ~KEYEVENTF_SCANCODE
    return INPUT(type=INPUT_KEYBOARD,
                 ki=KEYBDINPUT(wVk=0 if flags & KEYEVENTF_SCANCODE else vk,
                               wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None))


def _unicode_input(char: str, up: bool) -> INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    return INPUT(type=INPUT_KEYBOARD,
                 ki=KEYBDINPUT(wVk=0, wScan=ord(char), dwFlags=flags,
                               time=0, dwExtraInfo=None))


def _mouse_input(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> INPUT:
    return INPUT(type=INPUT_MOUSE,
                 mi=MOUSEINPUT(dx=dx, dy=dy, mouseData=data, dwFlags=flags,
                               time=0, dwExtraInfo=None))


def parse_chord(chord: str) -> tuple[list[int], int]:
    """``"ctrl+shift+p"`` -> ``([VK_CONTROL, VK_SHIFT], VK_P)``."""
    parts = [p.strip().lower() for p in chord.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"empty chord: {chord!r}")
    *mods, key = parts
    unknown = [m for m in mods if m not in MODIFIERS]
    if unknown:
        raise ValueError(f"not a modifier: {unknown} in {chord!r}")
    if key not in VK:
        raise ValueError(f"unknown key {key!r} in chord {chord!r}")
    return [VK[m] for m in mods], VK[key]


class WindowsDriver(Driver):
    name = "windows"
    available = _WINDOWS

    def __init__(self, key_delay: float = 0.012, dpi_aware: bool = True):
        if not _WINDOWS:
            raise RuntimeError("WindowsDriver requires Windows (user32.dll)")
        self.key_delay = key_delay
        if dpi_aware:
            self._make_dpi_aware()

    @staticmethod
    def _make_dpi_aware() -> None:
        # Without this, screen coords are reported in scaled units and every
        # absolute mouse move lands in the wrong place on a HiDPI display.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass

    # --- keyboard -------------------------------------------------------
    def send_keys(self, chord: str, repeat: int = 1) -> None:
        for step in chord.split():
            mods, key = parse_chord(step)
            for _ in range(max(1, int(repeat))):
                _send(*[_key_input(m, up=False) for m in mods], _key_input(key, up=False))
                _send(_key_input(key, up=True), *[_key_input(m, up=True) for m in reversed(mods)])
                if self.key_delay:
                    time.sleep(self.key_delay)

    def type_text(self, text: str) -> None:
        for char in text:
            if char == "\n":
                self.send_keys("enter")
                continue
            _send(_unicode_input(char, up=False), _unicode_input(char, up=True))
            if self.key_delay:
                time.sleep(self.key_delay / 2)

    # --- mouse ----------------------------------------------------------
    def scroll(self, amount: int, horizontal: bool = False) -> None:
        flag = MOUSEEVENTF["hwheel" if horizontal else "wheel"]
        # mouseData is a signed value packed into an unsigned DWORD field.
        data = ctypes.c_long(int(amount) * WHEEL_DELTA).value & 0xFFFFFFFF
        _send(_mouse_input(flag, data=data))

    def click(self, button: str = "left", count: int = 1) -> None:
        button = button.lower()
        if button not in ("left", "right", "middle"):
            raise ValueError(f"unknown mouse button {button!r}")
        down, up = MOUSEEVENTF[f"{button}down"], MOUSEEVENTF[f"{button}up"]
        for index in range(max(1, int(count))):
            _send(_mouse_input(down), _mouse_input(up))
            if index + 1 < count:
                time.sleep(0.05)  # inside the double-click threshold

    def move_to(self, x: int, y: int) -> None:
        width, height = self.screen_size()
        # SendInput absolute coords are 0..65535 across the primary screen.
        nx = int(x * 65535 / max(1, width - 1))
        ny = int(y * 65535 / max(1, height - 1))
        _send(_mouse_input(MOUSEEVENTF["move"] | MOUSEEVENTF["absolute"], nx, ny))

    def move_by(self, dx: int, dy: int) -> None:
        _send(_mouse_input(MOUSEEVENTF["move"], int(dx), int(dy)))

    def cursor_position(self) -> tuple[int, int]:
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        return (point.x, point.y)

    def screen_size(self) -> tuple[int, int]:
        return (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))

    # --- windows --------------------------------------------------------
    def list_windows(self) -> Sequence[WindowInfo]:
        results: list[WindowInfo] = []
        enum_proc = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        def callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()
            if title:
                results.append(WindowInfo(hwnd, title, _process_name(hwnd)))
            return True

        user32.EnumWindows(enum_proc(callback), 0)
        return results

    def activate(self, window: WindowInfo) -> bool:
        hwnd = window.handle
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        if user32.SetForegroundWindow(hwnd):
            return True
        # Windows refuses SetForegroundWindow from a process that does not own
        # the foreground. Borrowing the foreground thread's input queue is the
        # standard way around it.
        return self._force_foreground(hwnd)

    def _force_foreground(self, hwnd: int) -> bool:
        foreground = user32.GetForegroundWindow()
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        current_thread = kernel32.GetCurrentThreadId()
        foreground_thread = user32.GetWindowThreadProcessId(foreground, None)
        attached = []
        for thread in {target_thread, foreground_thread} - {current_thread, 0}:
            if user32.AttachThreadInput(current_thread, thread, True):
                attached.append(thread)
        try:
            user32.BringWindowToTop(hwnd)
            user32.ShowWindow(hwnd, SW_SHOW)
            ok = bool(user32.SetForegroundWindow(hwnd))
        finally:
            for thread in attached:
                user32.AttachThreadInput(current_thread, thread, False)
        return ok

    def window_action(self, action: str, window: Optional[WindowInfo] = None) -> bool:
        hwnd = window.handle if window else user32.GetForegroundWindow()
        if not hwnd:
            return False
        mapping = {"minimize": SW_MINIMIZE, "maximize": SW_MAXIMIZE, "restore": SW_RESTORE}
        if action == "close":
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            return True
        if action not in mapping:
            raise ValueError(f"unknown window action {action!r}")
        user32.ShowWindow(hwnd, mapping[action])
        return True

    def foreground_window(self) -> Optional[WindowInfo]:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        buffer = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buffer, 512)
        return WindowInfo(hwnd, buffer.value, _process_name(hwnd))

    def launch(self, command: str) -> None:
        subprocess.Popen(command, shell=True, close_fds=True)

    def beep(self, frequency: int = 880, duration_ms: int = 90) -> None:
        try:
            kernel32.Beep(int(frequency), int(duration_ms))
        except Exception:
            pass


def _process_name(hwnd: int) -> str:
    """Best-effort executable name for a window; "" if it cannot be read."""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(260)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value.rsplit("\\", 1)[-1]
    finally:
        kernel32.CloseHandle(handle)
    return ""
