import ctypes
import ctypes.wintypes
import platform
import random
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk


WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
WM_QUIT = 0x0012


SPECIAL_KEYS = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "escape": 0x1B,
    "esc": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "ins": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
}


class AreaSelector(tk.Toplevel):
    def __init__(self, master, on_selected):
        super().__init__(master)
        self.on_selected = on_selected
        self.start_x = 0
        self.start_y = 0
        self.rect_id = None

        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.25)
        self.configure(bg="black")

        width = self.winfo_screenwidth()
        height = self.winfo_screenheight()
        self.geometry(f"{width}x{height}+0+0")

        self.canvas = tk.Canvas(self, bg="#4a90e2", highlightthickness=0, cursor="cross")
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Escape>", lambda _event: self.destroy())

        self.deiconify()
        self.focus_force()

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x,
            self.start_y,
            self.start_x,
            self.start_y,
            outline="red",
            width=2,
            fill="white",
            stipple="gray25",
        )

    def on_drag(self, event):
        if self.rect_id:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)

        if x2 - x1 < 2 or y2 - y1 < 2:
            messagebox.showwarning("Selection too small", "Please drag a larger area.")
            return

        self.on_selected((x1, y1, x2, y2))
        self.destroy()


class WindowsAutoClicker:
    def __init__(self):
        self.user32 = ctypes.windll.user32 if platform.system() == "Windows" else None

    def is_supported(self):
        return self.user32 is not None

    def move_and_click(self, x, y):
        self.user32.SetCursorPos(x, y)
        self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


class HotkeyManager:
    def __init__(self, on_trigger):
        self.on_trigger = on_trigger
        self.running = False
        self.thread = None
        self.thread_id = None
        self.hotkey_id = 1
        self.key_code = None
        self.modifiers = 0
        self.last_error = None
        self.user32 = ctypes.windll.user32 if platform.system() == "Windows" else None
        self.kernel32 = ctypes.windll.kernel32 if platform.system() == "Windows" else None

    def is_supported(self):
        return self.user32 is not None

    def parse_hotkey(self, value):
        raw = value.strip().lower().replace(" ", "")
        if not raw:
            raise ValueError("Please enter a hotkey.")

        parts = raw.split("+")
        modifiers = 0
        key_part = None

        modifier_map = {
            "ctrl": MOD_CONTROL,
            "control": MOD_CONTROL,
            "alt": MOD_ALT,
            "shift": MOD_SHIFT,
            "win": MOD_WIN,
            "windows": MOD_WIN,
        }

        for part in parts:
            if part in modifier_map:
                modifiers |= modifier_map[part]
                continue
            if key_part is not None:
                raise ValueError("Use one main key plus optional modifiers.")
            key_part = part

        if key_part is None:
            raise ValueError("Hotkey must include a main key.")

        key_code = self.virtual_key_code(key_part)
        return modifiers, key_code, raw

    def virtual_key_code(self, key_name):
        if len(key_name) == 1 and key_name.isalpha():
            return ord(key_name.upper())
        if len(key_name) == 1 and key_name.isdigit():
            return ord(key_name)
        if key_name.startswith("f") and key_name[1:].isdigit():
            number = int(key_name[1:])
            if 1 <= number <= 24:
                return 0x70 + number - 1
        if key_name in SPECIAL_KEYS:
            return SPECIAL_KEYS[key_name]
        raise ValueError("Unsupported hotkey. Try examples like f6, ctrl+f6, alt+x, or space.")

    def register(self, hotkey_text):
        if not self.is_supported():
            raise RuntimeError("Global hotkeys are only supported on Windows.")

        self.stop()
        self.modifiers, self.key_code, normalized = self.parse_hotkey(hotkey_text)
        self.last_error = None
        self.running = True
        self.thread = threading.Thread(target=self.message_loop, daemon=True)
        self.thread.start()
        return normalized

    def message_loop(self):
        self.thread_id = self.kernel32.GetCurrentThreadId()

        if not self.user32.RegisterHotKey(None, self.hotkey_id, self.modifiers, self.key_code):
            self.last_error = ctypes.GetLastError()
            self.running = False
            return

        msg = ctypes.wintypes.MSG()
        while self.running:
            result = self.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result <= 0:
                break
            if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:
                self.on_trigger()
            self.user32.TranslateMessage(ctypes.byref(msg))
            self.user32.DispatchMessageW(ctypes.byref(msg))

        self.user32.UnregisterHotKey(None, self.hotkey_id)

    def stop(self):
        if not self.running or not self.user32:
            return
        self.running = False
        if self.thread_id is not None:
            self.user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
        self.thread = None
        self.thread_id = None


class AutoClickerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Auto Clicker")
        self.root.resizable(False, False)

        self.clicker = WindowsAutoClicker()
        self.hotkeys = HotkeyManager(self.handle_hotkey)
        self.area = None
        self.running = False
        self.worker_thread = None

        self.status_var = tk.StringVar(value="Idle")
        self.area_var = tk.StringVar(value="No area selected")
        self.delay_var = tk.StringVar(value="0.50")
        self.hotkey_var = tk.StringVar(value="f6")

        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if self.clicker.is_supported() and self.hotkeys.is_supported():
            self.apply_hotkey()
        else:
            self.status_var.set("Windows only")
            messagebox.showwarning(
                "Unsupported platform",
                "This version uses only the Python standard library and currently supports Windows only.",
            )

    def build_ui(self):
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text="Click delay (seconds):").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.delay_var, width=14).grid(row=0, column=1, sticky="ew", padx=(8, 0))

        ttk.Label(frame, text="Toggle hotkey:").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(frame, textvariable=self.hotkey_var, width=14).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(10, 0))

        ttk.Button(frame, text="Apply hotkey", command=self.apply_hotkey).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0)
        )
        ttk.Button(frame, text="Select click area", command=self.open_area_selector).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0)
        )
        ttk.Button(frame, text="Start / Stop", command=self.toggle_clicking).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0)
        )

        ttk.Label(frame, text="Selected area:").grid(row=5, column=0, sticky="nw", pady=(12, 0))
        ttk.Label(frame, textvariable=self.area_var, wraplength=320, justify="left").grid(
            row=5, column=1, sticky="w", padx=(8, 0), pady=(12, 0)
        )

        ttk.Label(frame, text="Status:").grid(row=6, column=0, sticky="w", pady=(8, 0))
        ttk.Label(frame, textvariable=self.status_var).grid(row=6, column=1, sticky="w", padx=(8, 0), pady=(8, 0))

        ttk.Label(
            frame,
            text="Examples: f6, ctrl+f6, alt+x, shift+space",
            foreground="#555555",
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def get_delay(self):
        try:
            delay = float(self.delay_var.get())
        except ValueError:
            raise ValueError("Delay must be a number.")
        if delay <= 0:
            raise ValueError("Delay must be greater than 0.")
        return delay

    def apply_hotkey(self):
        if not self.hotkeys.is_supported():
            messagebox.showerror("Unsupported platform", "Global hotkeys are only supported on Windows.")
            return

        try:
            normalized = self.hotkeys.register(self.hotkey_var.get())
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("Hotkey error", str(exc))
            return

        self.hotkey_var.set(normalized)
        self.status_var.set(f"Idle (toggle key: {normalized})")
        self.root.after(250, self.check_hotkey_registration)

    def check_hotkey_registration(self):
        if self.hotkeys.last_error is None:
            return
        messagebox.showerror(
            "Hotkey error",
            "Windows could not register that hotkey. It may already be in use by another app.",
        )
        self.status_var.set("Hotkey registration failed")

    def open_area_selector(self):
        self.root.withdraw()

        def finish_selection(area):
            self.area = area
            x1, y1, x2, y2 = area
            self.area_var.set(f"({x1}, {y1}) to ({x2}, {y2})")
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()

        selector = AreaSelector(self.root, finish_selection)

        def handle_destroy(_event):
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()

        selector.bind("<Destroy>", handle_destroy)

    def handle_hotkey(self):
        self.root.after(0, self.toggle_clicking)

    def toggle_clicking(self):
        if not self.clicker.is_supported():
            messagebox.showerror("Unsupported platform", "Mouse automation is only supported on Windows.")
            return

        if self.running:
            self.running = False
            self.status_var.set("Stopping...")
            return

        if not self.area:
            messagebox.showerror("No area selected", "Select a click area first.")
            return

        try:
            delay = self.get_delay()
        except ValueError as exc:
            messagebox.showerror("Invalid delay", str(exc))
            return

        self.running = True
        self.status_var.set(f"Running every {delay:.2f}s")
        self.worker_thread = threading.Thread(target=self.click_loop, daemon=True)
        self.worker_thread.start()

    def click_loop(self):
        while self.running:
            x1, y1, x2, y2 = self.area
            x = random.randint(x1, x2)
            y = random.randint(y1, y2)
            self.clicker.move_and_click(x, y)

            try:
                delay = max(0.01, float(self.delay_var.get() or 0.01))
            except ValueError:
                delay = 0.01

            end_time = time.time() + delay
            while self.running and time.time() < end_time:
                time.sleep(0.01)

        self.root.after(0, lambda: self.status_var.set("Idle"))

    def on_close(self):
        self.running = False
        self.hotkeys.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = AutoClickerApp(root)
    root.mainloop()
