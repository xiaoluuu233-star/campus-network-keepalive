from __future__ import annotations
import ctypes, os, sys, threading
from pathlib import Path
import tkinter as tk
from campus_keepalive import AppConfig, run_forever
from portal_client import PortalClient
APP_NAME = "Campus Network Keepalive"
def _console(show: bool):
    if os.name == "nt":
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd: ctypes.windll.user32.ShowWindow(hwnd, 5 if show else 0)
def _startup_command(config_path: Path) -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe": return f'"{sys.executable}" "{Path(__file__).resolve()}" --config "{config_path}" --background'
    return f'"{exe}" --config "{config_path}" --background'
def set_startup(enabled: bool, config_path: Path):
    if os.name != "nt": return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as key:
        if enabled: winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _startup_command(config_path))
        else:
            try: winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError: pass
class TrayApplication:
    def __init__(self, config: AppConfig, config_path: Path, background=False):
        self.config, self.config_path = config, config_path.resolve(); self.stop_event = threading.Event(); self._quitting = False
        self.root = tk.Tk(); self.root.title("校园网防掉线"); self.root.geometry("520x300"); self.root.protocol("WM_DELETE_WINDOW", self.hide_console)
        self.root.bind("<Unmap>", self._on_unmap)
        self.root.withdraw()
        self.status = tk.StringVar(value="运行中"); tk.Label(self.root, textvariable=self.status, anchor="w").pack(fill="x", padx=8, pady=8)
        if background: _console(False)
        self.worker = threading.Thread(target=lambda: run_forever(self.config, PortalClient(self.config), self.stop_event), daemon=True)
    def _on_unmap(self, _event=None):
        # 点击最小化时从任务栏移除，但不退出后台线程或托盘图标。
        if self.root.state() == "iconic":
            self.root.after_idle(self.root.withdraw)

    def show_console(self): _console(True); self.root.deiconify(); self.root.lift(); self.root.focus_force()
    def hide_console(self): self.root.withdraw(); _console(False)
    def quit(self):
        self.stop_event.set()
        if hasattr(self, "icon"): self.icon.stop()
        self.root.destroy()
    def run(self):
        set_startup(True, self.config_path); self.worker.start()
        import pystray
        from PIL import Image, ImageDraw
        image = Image.new("RGB", (64,64), "#1976d2"); ImageDraw.Draw(image).text((18,17), "网", fill="white")
        menu = pystray.Menu(pystray.MenuItem("打开控制台", lambda *_: self.root.after(0,self.show_console)), pystray.MenuItem("隐藏控制台", lambda *_: self.root.after(0,self.hide_console)), pystray.MenuItem("退出", lambda *_: self.root.after(0,self.quit)))
        self.icon = pystray.Icon(APP_NAME, image, APP_NAME, menu); threading.Thread(target=self.icon.run, daemon=True).start(); self.root.mainloop()




