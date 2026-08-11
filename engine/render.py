"""Render frames through ffmpeg at high quality and mux the original audio."""

import os
import subprocess
import threading

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import templates as T
from .templates import clip_u8, pack_u8

# learned once for PIL text
FONT_CACHE = {}


def _font(size):
    key = size
    if key not in FONT_CACHE:
        try:
            FONT_CACHE[key] = ImageFont.load_default(size=size)
        except Exception:
            FONT_CACHE[key] = ImageFont.load_default()
    return FONT_CACHE[key]


def _text_overlay(text, font_size, color, align="center"):
    """Pre-render a text overlay; returns (alpha 2-D, bbox width, bbox height)."""
    o = Image.new("RGBA", (2048, font_size * 3), (0, 0, 0, 0))
    d = ImageDraw.Draw(o)
    f = _font(font_size)
    bbox = d.textbbox((0, 0), text, font=f)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    if align == "center":
        x = (o.width - tw) // 2 - bbox[0]
    else:
        x = -bbox[0]
    yy = (o.height - th) // 2 - bbox[1]
    d.text((x, yy), text, font=f, fill=color)
    a = np.asarray(o.getchannel("A"), np.float64) / 255.0
    nzr = np.where(a.max(axis=1) > 0.001)[0]
    if len(nzr):
        a = a[nzr[0]:nzr[-1] + 1]
    nzc = np.where(a.max(axis=0) > 0.001)[0]
    if len(nzc):
        a = a[:, nzc[0]:nzc[-1] + 1]
    tw_r, th_r = a.shape[1], a.shape[0]
    return a, tw_r, th_r


# ----------------------------------------------------------------------------
#  post-processing overlays (applied to every frame of every template)
# ----------------------------------------------------------------------------

class Overlays:
    def __init__(self, w, h, ctx, enable_vignette=True, enable_scanlines=True,
                 enable_flash=True, watermark="", title=""):
        self.w = w
        self.h = h
        self.ctx = ctx

        # precomputed masks
        self.vig = None
        if enable_vignette:
            d = T.radial_distance(w, h) ** 2
            self.vig = (0.35 + 0.65 * np.exp(-d * 1.8))[:, :, None]
        self.scan = None
        if enable_scanlines:
            self.scan = (0.92 + 0.08 * np.sin(np.linspace(0, np.pi * 2, h))[:, None, None])
        self.enable_flash = enable_flash

        self.wm_alpha = None
        if watermark:
            a, tw, th = _text_overlay(watermark, max(16, w // 46), (80, 220, 255, 255), "left")
            self.wm_alpha = a
            self.wm_w = tw
            self.wm_h = th
            self.wm_x = w - tw - 24
            self.wm_y = h - th - 18

        self.title_alpha = None
        if title:
            ts = max(34, w // 14)
            a, tw, th = _text_overlay(title, ts, (255, 255, 255, 255), "center")
            self.title_alpha = a
            self.title_w = min(tw, w)
            self.title_h = th

        self._matrix = None
        if ctx.overlay_matrix:
            self._matrix = T.MatrixTemplate(ctx)

    def apply(self, idx, img):
        ctx = self.ctx
        out = img.astype(np.float64) / 255.0

        if self._matrix is not None:
            m = self._matrix.frame(idx).astype(np.float64) / 255.0
            gtint = m * (np.array([0.3, 1.0, 0.4]) * 0.7) + m * 0.5
            out = out * (1.0 - gtint * 0.45) + gtint * 0.45
        if self.vig is not None:
            out = out * self.vig
        if self.scan is not None:
            out = out * self.scan
        if self.enable_flash:
            fl = ctx.flash[idx]
            if fl > 0.05:
                out = clip_u8(out + fl * 0.10 * np.array([1.0, 0.97, 0.9]))

        if self.title_alpha is not None:
            th, tw = self.title_alpha.shape
            m = min(th, self.h)
            alpha = self.title_alpha[:m] * (0.35 + 0.55 * ctx.pulse[idx])
            alpha = alpha[:, :, None] * 0.95
            x0 = (self.w - tw) // 2
            seg = out[:m, x0:x0 + tw]
            seg = seg * (1.0 - alpha) + alpha * np.array([1.0, 1.0, 1.0])
            out[:m, x0:x0 + tw] = seg

        if self.wm_alpha is not None:
            a = self.wm_alpha
            ah, aw = a.shape
            seg = out[self.wm_y:self.wm_y + ah, self.wm_x:self.wm_x + aw]
            alpha = (a * (0.55 + 0.45 * ctx.pulse[idx]))[:, :, None]
            seg = seg * (1.0 - alpha) + alpha * np.array([0.35, 0.9, 1.0])
            out[self.wm_y:self.wm_y + ah, self.wm_x:self.wm_x + aw] = seg

        return pack_u8(clip_u8(out))


# ----------------------------------------------------------------------------
#  encoder presets
# ----------------------------------------------------------------------------

ENCODERS = {
    "YouTube (H.264, max compat)": {
        "vcodec": "libx264", "crf": 18, "preset": "slow",
        "extra": ["-profile:v", "high", "-movflags", "+faststart"],
    },
    "Max Quality (H.265/HEVC)": {
        "vcodec": "libx265", "crf": 20, "preset": "slow",
        "extra": ["-movflags", "+faststart"],
    },
    "GPU Fast (NVIDIA NVENC)": {
        "vcodec": "h264_nvenc", "crf": 19, "preset": "p7",
        "extra": ["-rc:v", "vbr", "-cq", "19", "-b:v", "20M", "-maxrate:v", "30M"],
    },
}

AUDIO_BITRATE = "320k"


def build_ffmpeg_command(audio_path, out_path, rw, rh, w, h, fps, duration, encoder_key):
    enc = ENCODERS[encoder_key]
    extra = list(enc["extra"])
    if (rw, rh) != (w, h):
        extra = ["-vf", f"scale={w}:{h}:flags=lanczos", *extra]
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", audio_path,
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{rw}x{rh}", "-r", str(fps),
        "-i", "pipe:0",
        "-map", "1:v:0", "-map", "0:a:0",
        "-c:v", enc["vcodec"], "-crf", str(enc["crf"]), "-preset", enc["preset"],
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", AUDIO_BITRATE,
        "-t", f"{duration:.3f}",
        *extra,
        out_path,
    ]
    return cmd


def render_video(analyzer, template_cls, out_path, audio_path, fps, w, h,
                 primary, accent, bg_image, title, watermark,
                 encoder_key="YouTube (H.264, max compat)",
                 enable_vignette=True, enable_scanlines=True, enable_flash=True,
                 overlay_matrix=False, render_scale=0.5,
                 on_progress=None, cancel_event=None):
    """Render the whole video. Runs inside the calling thread (background worker).

    render_scale: internal rendering resolution multiplier. Effects are rendered
    at `render_scale` size and ffmpeg upscales to the target (w x h) with Lanczos.
    0.5 is the recommended sweet spot of quality vs speed.
    """
    rw = max(2, int(round(w * render_scale)))
    rh = max(2, int(round(h * render_scale)))
    n_frames = max(1, int(round(analyzer.duration * fps)))
    arrays = analyzer.frame_arrays(fps, n_frames)
    arrays["t"] = arrays["t"]  # already float32

    ctx = T.TemplateContext(rw, rh, fps, arrays, primary=primary, accent=accent,
                            bg_image=bg_image, title=title,
                            overlay_matrix=overlay_matrix)
    ctx._analyzer = analyzer
    ctx.beats = analyzer.beats

    template = template_cls(ctx)

    cmd = build_ffmpeg_command(audio_path, out_path, rw, rh, w, h, fps,
                               analyzer.duration, encoder_key)
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except Exception as exc:
        raise RuntimeError(f"Could not start ffmpeg: {exc}")

    err_log = []

    def _drain_stderr():
        try:
            for line in proc.stderr:
                err_log.append(line.decode(errors="replace").rstrip())
        except Exception:
            pass

    threading.Thread(target=_drain_stderr, daemon=True).start()

    overlays = Overlays(rw, rh, ctx, enable_vignette, enable_scanlines,
                        enable_flash, watermark, title)

    start = _now()
    cancelled = False
    pipe_lost = False
    try:
        for i in range(n_frames):
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break
            img = template.frame(i)
            img = overlays.apply(i, img)
            try:
                proc.stdin.write(img.tobytes())
            except (BrokenPipeError, OSError):
                pipe_lost = True
                break

            if on_progress is not None:
                now = _now()
                if i % 8 == 0 or i == n_frames - 1:
                    eta = (now - start) / (i + 1) * (n_frames - i - 1)
                    on_progress(i + 1, n_frames, eta)
    except Exception:
        raise
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=900)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise RuntimeError(
                "ffmpeg did not finish in time. The video file may be too large or "
                "the encoder too slow - try a faster encoder preset or lower resolution.")

    if cancelled:
        try:
            os.remove(out_path)
        except OSError:
            pass
        raise RuntimeError("cancelled")

    if proc.returncode != 0 or pipe_lost:
        tail = "\n".join(err_log[-10:])
        raise RuntimeError(
            f"ffmpeg encoding failed (return code {proc.returncode}).\n{tail}\n"
            "Try another encoder preset.")
    return out_path


def _now():
    import time
    return time.perf_counter()
