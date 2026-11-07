#!/usr/bin/env python3
"""
TV Caster - find Chromecast / Google Cast TVs on your Wi-Fi network,
cast a video or audio URL (or a file on this computer) and control playback.

Requires:  pip install pychromecast
"""
import http.server
import mimetypes
import os
import socket
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pychromecast

MEDIA_PORT = 8765  # port used to serve local files to the TV


def local_ip():
    """LAN address of this computer (used so the TV can reach local files)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class FileServer:
    """Serves exactly one chosen file over HTTP so the TV can stream it."""

    def __init__(self):
        self.httpd = None
        self.path = None

    def serve(self, path):
        self.path = path
        if self.httpd is None:
            self.httpd = http.server.ThreadingHTTPServer(("0.0.0.0", MEDIA_PORT), _OneFileHandler)
            threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.httpd.chosen_path = path
        return f"http://{local_ip()}:{MEDIA_PORT}/media"


class _OneFileHandler(http.server.BaseHTTPRequestHandler):
    """Serves the file chosen in the app at /media; everything else is 404."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        self._send(head=False)

    def do_HEAD(self):
        self._send(head=True)

    def _send(self, head):
        path = getattr(self.server, "chosen_path", None)
        if self.path.split("?")[0] != "/media" or not path or not os.path.isfile(path):
            self.send_error(404)
            return
        size = os.path.getsize(path)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Accept-Ranges", "none")
        self.end_headers()
        if not head:
            with open(path, "rb") as f:
                while chunk := f.read(1 << 20):
                    try:
                        self.wfile.write(chunk)
                    except OSError:
                        break



class CastController:
    """Wraps one connected Chromecast device."""

    def __init__(self):
        self.cast = None

    def connect(self, cast):
        if self.cast is not None:
            self.disconnect()
        cast.wait(timeout=15)
        self.cast = cast

    def disconnect(self):
        if self.cast is not None:
            try:
                self.cast.disconnect()
            except Exception:
                pass
            self.cast = None

    @property
    def mc(self):
        if self.cast is None:
            raise RuntimeError("Not connected to a TV.")
        return self.cast.media_controller

    def play_url(self, url, title):
        ctype = mimetypes.guess_type(url.split("?")[0])[0] or "video/mp4"
        self.mc.play_media(url, ctype, title=title)
        self.mc.block_until_active(timeout=20)

    def play(self):
        self.mc.play()

    def pause(self):
        self.mc.pause()

    def stop(self):
        self.mc.stop()

    def seek(self, seconds):
        self.mc.seek(seconds)

    def volume_change(self, delta):
        self.cast.volume_up(delta) if delta > 0 else self.cast.volume_down(-delta)

    def set_volume(self, level):
        self.cast.socket_client.receiver_controller.set_volume(max(0.0, min(1.0, level)))

    def set_muted(self, muted):
        self.cast.socket_client.receiver_controller.set_volume_muted(muted)

    def status(self):
        """Return (state, position, duration) for the current media."""
        self.mc.update_status()
        s = self.mc.status
        return s.player_state, s.current_time, s.duration

    def quit_app(self):
        self.cast.quit_app()


def discover(timeout=6):
    """Return a sorted list of (name, host, port, uuid) for Cast devices."""
    chromecasts, browser = pychromecast.get_chromecasts(timeout=timeout)
    pychromecast.discovery.stop_discovery(browser)
    found = [(c.name, c.cast_info.host, c.cast_info.port, c) for c in chromecasts]
    return sorted(found, key=lambda d: d[0].lower())


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TV Caster")
        self.geometry("520x560")
        self.devices = []  # (name, host, port, chromecast)
        self.ctrl = CastController()
        self.files = FileServer()
        self.busy = False

        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="TV:").pack(side="left")
        self.device_var = tk.StringVar(value="(no TVs found)")
        self.device_menu = ttk.Combobox(top, textvariable=self.device_var, state="readonly", width=34)
        self.device_menu.pack(side="left", padx=6)
        self.device_menu.bind("<<ComboboxSelected>>", lambda e: self.on_select())
        self.scan_btn = ttk.Button(top, text="Scan", command=self.scan)
        self.scan_btn.pack(side="left")

        src = ttk.LabelFrame(self, text="Media", padding=10)
        src.pack(fill="x", padx=10)
        self.url_var = tk.StringVar()
        ttk.Entry(src, textvariable=self.url_var, width=48).grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Button(src, text="Cast URL", command=self.cast_url).grid(row=1, column=0, sticky="ew", pady=4)
        ttk.Button(src, text="Cast File...", command=self.cast_file).grid(row=1, column=1, sticky="ew", pady=4)
        src.columnconfigure(0, weight=1)
        src.columnconfigure(1, weight=1)

        ctl = ttk.LabelFrame(self, text="Controls", padding=10)
        ctl.pack(fill="x", padx=10, pady=8)
        buttons = [
            ("Play", self.ctrl.play), ("Pause", self.ctrl.pause), ("Stop", self.ctrl.stop),
            ("-30s", lambda: self.seek_by(-30)), ("+30s", lambda: self.seek_by(30)),
            ("Vol -", lambda: self.vol(-0.05)), ("Vol +", lambda: self.vol(0.05)),
            ("Mute", lambda: self.mute(True)), ("Unmute", lambda: self.mute(False)),
        ]
        for i, (label, fn) in enumerate(buttons):
            ttk.Button(ctl, text=label, command=lambda f=fn: self.run_action(f)).grid(
                row=i // 3, column=i % 3, sticky="ew", padx=3, pady=3)
        for c in range(3):
            ctl.columnconfigure(c, weight=1)

        self.status_var = tk.StringVar(value="Click Scan to find TVs on your Wi-Fi.")
        ttk.Label(self, textvariable=self.status_var, wraplength=490).pack(fill="x", padx=10, pady=(4, 10))

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(300, self.scan)

    # -- helpers
    def set_status(self, text):
        self.after(0, lambda: self.status_var.set(text))

    def in_background(self, fn, done=None):
        def worker():
            try:
                result = fn()
                if done:
                    self.after(0, lambda: done(result))
            except Exception as e:  # shown to the user
                self.after(0, lambda: messagebox.showerror("TV Caster", str(e)))
                self.set_status(f"Error: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def require_tv(self):
        if self.ctrl.cast is None:
            raise RuntimeError("Pick a TV first (click Scan).")

    def run_action(self, fn):
        def go():
            self.require_tv()
            fn()
        self.in_background(go)

    # -- discovery
    def scan(self):
        self.scan_btn.config(state="disabled")
        self.set_status("Scanning the network for TVs...")

        def done(found):
            self.scan_btn.config(state="normal")
            self.devices = found
            names = [d[0] for d in found]
            self.device_menu["values"] = names
            if names:
                self.device_var.set(names[0])
                self.set_status(f"Found {len(names)} device(s). Choose one.")
                self.connect_to(0)
            else:
                self.device_var.set("(no TVs found)")
                self.set_status("No TVs found. Make sure this computer and the TV are on the same Wi-Fi.")

        self.in_background(discover, done)

    def on_select(self):
        names = [d[0] for d in self.devices]
        if self.device_var.get() in names:
            self.connect_to(names.index(self.device_var.get()))

    def connect_to(self, index):
        cast = self.devices[index][3]

        def done(_):
            self.set_status(f"Connected to {cast.name}.")

        self.in_background(lambda: self.ctrl.connect(cast), done)

    # -- casting
    def cast_url(self):
        url = self.url_var.get().strip()
        if not url.startswith(("http://", "https://")):
            messagebox.showwarning("TV Caster", "Enter a full http:// or https:// link.")
            return

        def go():
            self.require_tv()
            self.ctrl.play_url(url, title=url)

        self.in_background(go, lambda _: self.set_status("Casting URL."))

    def cast_file(self):
        path = filedialog.askopenfilename(title="Choose a video or audio file")
        if not path:
            return

        def go():
            self.require_tv()
            url = self.files.serve(path)
            self.ctrl.play_url(url, title=os.path.basename(path))

        self.in_background(go, lambda _: self.set_status(f"Casting {os.path.basename(path)}."))

    # -- controls
    def seek_by(self, seconds):
        _, pos, _ = self.ctrl.status()
        self.ctrl.seek(max(0, (pos or 0) + seconds))

    def vol(self, delta):
        self.ctrl.volume_change(delta)

    def mute(self, muted):
        self.ctrl.set_muted(muted)

    def on_close(self):
        self.ctrl.disconnect()
        self.destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
