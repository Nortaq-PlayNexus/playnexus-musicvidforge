"""MusicVidForge - upload a song, pick a beat-synced visual template, render a
YouTube / social-media ready music video at the highest quality."""

import os
import queue
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from engine import TEMPLATES
from engine.audio import SynthTrack, TrackAnalyzer
from engine.render import ENCODERS, render_video
from engine.templates import TemplateContext, get_template, hex_to_rgb

APP_NAME = "MusicVidForge"


def _now():
    import time
    return time.time()


def _fmt(n):
    return f"{int(n):,}"


def _fmt_eta(s):
    if not s or s != s or s <= 0 or s > 1e8:
        return "…"
    s = int(s)
    h, m = divmod(s // 60, 60)
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m {s % 60:02d}s"
RESOLUTIONS = {
    "4K Ultra HD  3840x2160  16:9": (3840, 2160),
    "1440p QHD    2560x1440  16:9": (2560, 1440),
    "1080p FullHD 1920x1080  16:9 (YouTube)": (1920, 1080),
    "1080p Vertical  1080x1920  9:16 (Shorts/TikTok)": (1080, 1920),
    "720p  1280x720  16:9 (fast preview)": (1280, 720),
    "Square 1080x1080  1:1 (Instagram)": (1080, 1080),
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("980x760")
        self.minsize(860, 640)
        self.configure(bg="#0e0e14")

        self.audio_path = None
        self.analyzer = None
        self.bg_pil = None
        self.primary_hex = "#00ff5a"
        self.accent_hex = "#ff28a8"

        self.events = queue.Queue()
        self.cancel_event = threading.Event()

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", background="#0e0e14", foreground="#e6e6e6",
                        fieldbackground="#16161f", bordercolor="#22223a")
        style.configure("TFrame", background="#0e0e14")
        style.configure("TLabel", background="#0e0e14", foreground="#e6e6e6")
        style.configure("Card.TFrame", background="#14141d",
                        relief="flat", borderwidth=1)
        style.configure("TButton", background="#23233a", foreground="#e6e6e6",
                        borderwidth=0, focusthickness=0)
        style.map("TButton",
                  background=[("active", "#2e2e4a"), ("disabled", "#1a1a26")])
        style.configure("Accent.TButton", background="#1b6b3a",
                        foreground="#ffffff", font=("Segoe UI", 10, "bold"))
        style.configure("TCombobox", fieldbackground="#16161f", background="#23233a",
                        foreground="#e6e6e6", arrowcolor="#e6e6e6")
        style.configure("TCheckbutton", background="#14141d", foreground="#d8d8e6")
        style.configure("Horizontal.TProgressbar", background="#00ff5a",
                        troughcolor="#16161f")

        self._build_ui()
        self.after(120, self._poll_events)

    # ------------------------------------------------------------------ UI
    def _card(self, parent, label):
        f = ttk.Frame(parent, style="Card.TFrame", padding=12)
        f.pack(fill="x", padx=14, pady=(14, 0))
        ttk.Label(f, text=label, font=("Segoe UI", 10, "bold"),
                  foreground="#7fe8a8").pack(anchor="w")
        return f

    def _build_ui(self):
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=4, pady=4)

        # header
        head = ttk.Frame(wrap)
        head.pack(fill="x", padx=14, pady=(10, 0))
        ttk.Label(head, text="♪  " + APP_NAME,
                  font=("Segoe UI", 17, "bold"), foreground="#7fe8a8").pack(side="left")
        ttk.Label(head, text="song in  ->  beat-synced video out",
                  foreground="#8a8aa0").pack(side="left", padx=12)

        # ---------------- source card
        c = self._card(wrap, "1 · SONG")
        self.song_label = ttk.Label(c, text="No song loaded", foreground="#8a8aa0")
        self.song_label.pack(side="left", fill="x", expand=True)
        ttk.Button(c, text="Choose song…", command=self.choose_song).pack(side="right")
        self.bpm_label = ttk.Label(c, text="", foreground="#7fe8a8")
        self.bpm_label.pack(side="right", padx=10)

        # ---------------- template card
        c = self._card(wrap, "2 · TEMPLATE")
        row = ttk.Frame(c)
        row.pack(fill="x")
        self.template_cb = ttk.Combobox(row, state="readonly", width=34,
                                        values=[t.name for t in TEMPLATES])
        self.template_cb.current(0)
        self.template_cb.pack(side="left")
        self.template_cb.bind("<<ComboboxSelected>>", lambda e: self._template_desc())
        ttk.Button(row, text="Preview frame", command=self.preview_frame).pack(side="left", padx=8)
        self.desc_label = ttk.Label(c, text=TEMPLATES[0].description,
                                    foreground="#9a9ab0", wraplength=820, justify="left")
        self.desc_label.pack(fill="x", pady=(8, 0))

        # ---------------- style card
        c = self._card(wrap, "3 · BACKGROUND & COLORS")
        row = ttk.Frame(c)
        row.pack(fill="x")
        ttk.Label(row, text="Background image (optional):").pack(side="left")
        self.bg_label = ttk.Label(row, text="none", foreground="#8a8aa0")
        self.bg_label.pack(side="left", padx=8)
        ttk.Button(row, text="Choose image…", command=self.choose_bg).pack(side="left")
        ttk.Button(row, text="Clear", command=self.clear_bg).pack(side="left", padx=6)

        row2 = ttk.Frame(c)
        row2.pack(fill="x", pady=(8, 0))
        self.primary_btn = tk.Button(row2, text="Primary color", command=self.pick_primary,
                                     bg=self.primary_hex, fg="black", relief="flat",
                                     padx=10, cursor="hand2")
        self.primary_btn.pack(side="left")
        self.accent_btn = tk.Button(row2, text="Accent color", command=self.pick_accent,
                                    bg=self.accent_hex, fg="white", relief="flat",
                                    padx=10, cursor="hand2")
        self.accent_btn.pack(side="left", padx=10)
        ttk.Label(row2, text="Beat sensitivity").pack(side="left", padx=(20, 6))
        self.sens = ttk.Scale(row2, from_=0, to=1, value=0.5)
        self.sens.pack(side="left")

        # ---------------- output card
        c = self._card(wrap, "4 · OUTPUT")
        row = ttk.Frame(c)
        row.pack(fill="x")
        ttk.Label(row, text="Resolution:").pack(side="left")
        self.res_cb = ttk.Combobox(row, state="readonly", width=40,
                                   values=list(RESOLUTIONS.keys()))
        self.res_cb.current(2)
        self.res_cb.pack(side="left", padx=8)
        ttk.Label(row, text="FPS:").pack(side="left")
        self.fps_cb = ttk.Combobox(row, state="readonly", width=4, values=["60", "30", "24"])
        self.fps_cb.current(0)
        self.fps_cb.pack(side="left", padx=8)
        ttk.Label(row, text="Encoder:").pack(side="left")
        self.enc_cb = ttk.Combobox(row, state="readonly", width=32,
                                   values=list(ENCODERS.keys()))
        self.enc_cb.current(0)
        self.enc_cb.pack(side="left", padx=8)
        ttk.Label(row, text="Speed/Quality:").pack(side="left")
        self.scale_cb = ttk.Combobox(row, state="readonly", width=20,
                                     values=["0.5x fast (recommended)",
                                             "0.25x fastest",
                                             "1.0x max quality"])
        self.scale_cb.current(0)
        self.scale_cb.pack(side="left", padx=8)

        row2 = ttk.Frame(c)
        row2.pack(fill="x", pady=(8, 0))
        ttk.Label(row2, text="Title overlay:").pack(side="left")
        self.title_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.title_var, width=34).pack(side="left", padx=6)
        ttk.Label(row2, text="Save as:").pack(side="left", padx=(12, 4))
        self.out_var = tk.StringVar()
        self.out_entry = ttk.Entry(row2, textvariable=self.out_var, width=26)
        self.out_entry.pack(side="left")

        row3 = ttk.Frame(c)
        row3.pack(fill="x", pady=(8, 0))
        self.vig_var = tk.BooleanVar(value=True)
        self.scan_var = tk.BooleanVar(value=False)
        self.flash_var = tk.BooleanVar(value=True)
        self.matrix_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row3, text="Vignette", variable=self.vig_var).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(row3, text="Scanlines", variable=self.scan_var).pack(side="left", padx=8)
        ttk.Checkbutton(row3, text="Beat flash", variable=self.flash_var).pack(side="left", padx=8)
        ttk.Checkbutton(row3, text="Matrix overlay", variable=self.matrix_var).pack(side="left", padx=8)

        # ---------------- render
        foot = ttk.Frame(wrap, padding=(14, 12, 14, 14))
        foot.pack(fill="x")
        self.render_btn = ttk.Button(foot, text="RENDER MUSIC VIDEO",
                                     style="Accent.TButton", command=self.start_render)
        self.render_btn.pack(side="left")
        self.cancel_btn = ttk.Button(foot, text="Cancel", command=self.cancel_render,
                                     state="disabled")
        self.cancel_btn.pack(side="left", padx=8)
        self.progress = ttk.Progressbar(foot, maximum=100)
        self.progress.pack(side="left", fill="x", expand=True, padx=14)
        self.status = ttk.Label(wrap, text="Ready.", foreground="#9a9ab0")
        self.status.pack(anchor="w", padx=18, pady=(0, 12))

        self._template_desc()

    # ----------------------------------------------------------------- funcs
    def _template_desc(self):
        idx = self.template_cb.current()
        t = TEMPLATES[max(0, idx)]
        self.desc_label.config(text=t.description)

    def choose_song(self):
        path = filedialog.askopenfilename(
            title="Choose your song",
            filetypes=[("Audio", "*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus *.wma"),
                       ("All files", "*.*")])
        if not path:
            return
        self.audio_path = path
        self.song_label.config(text=os.path.basename(path))
        stem = os.path.splitext(os.path.basename(path))[0]
        if not self.title_var.get():
            self.title_var.set(stem)
        if not self.out_var.get():
            self.out_var.set(stem + "_music_video.mp4")
        self.status.config(text="Analysing beats…")
        self.update_idletasks()

        def work():
            try:
                an = TrackAnalyzer(path, sensitivity=self.sens.get())
                self.events.put(("analysed", an))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def choose_bg(self):
        path = filedialog.askopenfilename(
            title="Choose background image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.webp"), ("All files", "*.*")])
        if not path:
            return
        from PIL import Image
        try:
            self.bg_pil = Image.open(path)
            self.bg_pil.load()
            self.bg_label.config(text=f"{os.path.basename(path)}  ({self.bg_pil.size[0]}x{self.bg_pil.size[1]})")
        except Exception as exc:
            messagebox.showerror(APP_NAME, "Could not open image:\n" + str(exc))

    def clear_bg(self):
        self.bg_pil = None
        self.bg_label.config(text="none")

    def pick_primary(self):
        c = colorchooser.askcolor(color=self.primary_hex)[1]
        if c:
            self.primary_hex = c
            self.primary_btn.config(bg=c, fg="#000000" if int(c[1:3], 16) > 150 else "#ffffff")
        # self.focus_force()

    def pick_accent(self):
        c = colorchooser.askcolor(color=self.accent_hex)[1]
        if c:
            self.accent_hex = c
            self.accent_btn.config(bg=c, fg="#000000" if int(c[1:3], 16) > 150 else "#ffffff")

    def _dims(self):
        return RESOLUTIONS[self.res_cb.get()]

    def _current_analyzer(self):
        if self.analyzer is not None:
            return self.analyzer
        return SynthTrack(6.0)

    def preview_frame(self):
        try:
            from PIL import Image as PILImage

            from engine.templates import pack_u8
            w, h = self._dims()
            analyzer = self._current_analyzer()
            n = int(round(analyzer.duration * 30))
            arrays = analyzer.frame_arrays(30, n)
            tcls = get_template(TEMPLATES[self.template_cb.current()].key)
            ctx = TemplateContext(w, h, 30, arrays,
                                  primary=hex_to_rgb(self.primary_hex),
                                  accent=hex_to_rgb(self.accent_hex),
                                  bg_image=self.bg_pil,
                                  title=self.title_var.get(),
                                  overlay_matrix=self.matrix_var.get())
            ctx._analyzer = analyzer
            ctx.beats = analyzer.beats
            templ = tcls(ctx)
            idx = min(int(n * 0.35), n - 1)
            frame = pack_u8(templ.frame(idx))
            img = PILImage.fromarray(frame)
            img.thumbnail((420, 420))
            img.show()
        except Exception as exc:
            messagebox.showerror(APP_NAME, "Preview failed:\n" + str(exc))

    # ----------------------------------------------------------------- render
    def start_render(self):
        if self.audio_path is None or self.analyzer is None:
            messagebox.showwarning(APP_NAME, "Choose a song first and wait for beat analysis.")
            return
        out = self.out_var.get().strip()
        if not out:
            out = "music_video.mp4"
        if not out.lower().endswith(".mp4"):
            out += ".mp4"
        out = os.path.join(os.path.dirname(self.audio_path), out)
        if os.path.exists(out):
            if not messagebox.askyesno(APP_NAME, f'"{os.path.basename(out)}" exists.\nOverwrite?'):
                return

        w, h = self._dims()
        fps = int(self.fps_cb.get())
        self.cancel_event.clear()
        self.render_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.progress.config(value=0)
        self.status.config(text="Rendering… starting (building beat arrays)")
        self._render_start = _now()
        self._last_prog = _now()
        self._rendering = True

        args = dict(
            analyzer=self.analyzer,
            template_cls=get_template(TEMPLATES[self.template_cb.current()].key),
            out_path=out,
            audio_path=self.audio_path,
            fps=fps, w=w, h=h,
            primary=hex_to_rgb(self.primary_hex),
            accent=hex_to_rgb(self.accent_hex),
            bg_image=self.bg_pil,
            title=self.title_var.get(),
            watermark="MusicVidForge",
            encoder_key=self.enc_cb.get(),
            enable_vignette=self.vig_var.get(),
            enable_scanlines=self.scan_var.get(),
            enable_flash=self.flash_var.get(),
            overlay_matrix=self.matrix_var.get(),
            render_scale=float(self.scale_cb.get().split("x")[0]),
            on_progress=lambda done, total, eta: self.events.put(("progress", done, total, eta)),
            cancel_event=self.cancel_event,
        )

        def worker():
            try:
                result = render_video(**args)
                self.events.put(("done", result))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def cancel_render(self):
        self.cancel_event.set()
        self.status.config(text="Cancelling…")

    # ----------------------------------------------------------------- events
    def _poll_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "analysed":
                    self.analyzer = ev[1]
                    bpm = self.analyzer.bpm or 0
                    dur = self.analyzer.duration
                    self.bpm_label.config(text=f"~{bpm:.0f} BPM · {dur:.0f}s")
                    self.status.config(text=f"Ready. {dur:.1f}s of audio, ~{bpm:.0f} BPM.")
                elif ev[0] == "progress":
                    done, total, eta = ev[1], ev[2], ev[3]
                    pct = int(done / total * 100)
                    self.progress.config(value=pct)
                    self._last_prog = _now()
                    if done > 1 and total:
                        fps = done / max(0.001, self._last_prog - self._render_start)
                        self.status.config(
                            text=(f"Rendering… {pct}% · frame {_fmt(done)}/{_fmt(total)}"
                                  f" · {fps:.1f} fps · ETA {_fmt_eta(eta)}"))
                    else:
                        self.status.config(text="Rendering… starting")
                elif ev[0] == "done":
                    self._rendering = False
                    self.progress.config(value=100)
                    self.status.config(text="Done!")
                    self.render_btn.config(state="normal")
                    self.cancel_btn.config(state="disabled")
                    result = ev[1]
                    self._open_video(result)
                elif ev[0] == "error":
                    self._rendering = False
                    self.render_btn.config(state="normal")
                    self.cancel_btn.config(state="disabled")
                    if str(ev[1]) == "cancelled":
                        self.status.config(text="Cancelled.")
                    else:
                        self.status.config(text="Error.")
                        messagebox.showerror(APP_NAME, str(ev[1]))
        except queue.Empty:
            pass
        if getattr(self, "_rendering", False) and _now() - self._last_prog > 8:
            self.status.config(text="Still rendering… this can take a while for long songs")
            self._last_prog = _now()
        try:
            if self.winfo_exists():
                self._poll_job = self.after(120, self._poll_events)
        except tk.TclError:
            pass

    def destroy(self):
        job = getattr(self, "_poll_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        super().destroy()

    def _open_video(self, path):
        if messagebox.askyesno(APP_NAME, "Video finished!\n\nOpen it now?"):
            os.startfile(path)  # noqa


# ----------------------------------------------------------------------------

def main():
    import sys
    try:
        app = App()
        app.mainloop()
    except Exception as exc:
        sys.stderr.write(f"MusicVidForge could not open its window: {exc}\n")
        raise


if __name__ == "__main__":
    main()
