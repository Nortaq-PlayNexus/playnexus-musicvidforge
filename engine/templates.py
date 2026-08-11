"""Beat-synced visual templates. Pure numpy rendering (PIL for text/glyphs only).

Every template reacts to ctx.pulse / ctx.flash / ctx.energy arrays which are
derived from the analysed beats, so "everything hits the beat".
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ----------------------------------------------------------------------------
#  small colour / image helpers
# ----------------------------------------------------------------------------

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def to_01(c):
    return (c[0] / 255.0, c[1] / 255.0, c[2] / 255.0)


def clip_u8(img):
    return np.clip(img, 0.0, 1.0)


def pack_u8(img):
    return np.clip(img * 255.0, 0.0, 255.0).astype(np.uint8)


def box_filter_axis(img, axis, k):
    """1-D box average along one axis using cumsum (fast, numpy only)."""
    k = int(max(1, k))
    width = k
    n = img.shape[axis]
    padw = [(width, width) if a == axis else (0, 0) for a in range(img.ndim)]
    p = np.pad(img, padw, mode="edge")
    c = np.cumsum(p, axis=axis)
    slo = [slice(None)] * img.ndim
    sup = [slice(None)] * img.ndim
    slo[axis] = slice(0, n)
    sup[axis] = slice(width, width + n)
    return (c[tuple(sup)] - c[tuple(slo)]) / width


def blur(img, k):
    return box_filter_axis(box_filter_axis(img, 0, k), 1, k)


def upscale(a, factor, w, h, blur_k=3):
    """Nearest-upscale a low-res plane to exactly (h, w) with a light smooth.

    The plane is repeated by `factor` and then padded + cropped so the result is
    always exactly (h, w) even when the source dimensions don't divide evenly.
    """
    a = np.repeat(np.repeat(a, factor, axis=0), factor, axis=1)
    if a.shape[0] < h or a.shape[1] < w:
        pad_h = max(0, h - a.shape[0])
        pad_w = max(0, w - a.shape[1])
        pad = [(0, pad_h), (0, pad_w)] + [(0, 0)] * (a.ndim - 2)
        a = np.pad(a, pad, mode="edge")
    a = a[:h, :w]
    if blur_k > 1:
        a = blur(a, blur_k)
    return a


def vertical_gradient(top_rgb, bottom_rgb, w, h):
    t = np.linspace(0.0, 1.0, h, dtype=np.float64)[:, None, None]
    g = (np.array(bottom_rgb, np.float64)[None, None, :] * t +
         np.array(top_rgb, np.float64)[None, None, :] * (1.0 - t))
    return np.broadcast_to(g, (h, w, 3)).copy()


def radial_distance(w, h, cx=0.5, cy=0.5):
    xs = np.linspace(0, 1, w, dtype=np.float64)[None, :]
    ys = np.linspace(0, 1, h, dtype=np.float64)[:, None]
    return np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)


def meshgrid(w, h):
    xs = np.broadcast_to(np.arange(w, dtype=np.float64)[None, :], (h, w))
    ys = np.broadcast_to(np.arange(h, dtype=np.float64)[:, None], (h, w))
    return xs, ys


def hsv_to_rgb(h, s, v):
    """Vectorised HSV -> RGB, all in [0,1]. Shapes broadcast."""
    i = np.floor(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i = i.astype(int) % 6
    r = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5],
                  [v, q, p, p, t, v])
    g = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5],
                  [t, v, v, q, p, p])
    b = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5],
                  [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1)


# ----------------------------------------------------------------------------
#  glyph atlas for the matrix template
# ----------------------------------------------------------------------------

MATRIX_GLYPHS = list("アイウエオカキクケコサシスセソタチツテトナニヌネノ0123456789$%#&@*+=;:.,~")


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def build_glyph_atlas(cell_w, cell_h):
    """Render every glyph as a (cell_h, cell_w) float alpha array."""
    glyphs = []
    for ch in MATRIX_GLYPHS:
        img = Image.new("L", (cell_w * 2, cell_h * 2), 0)
        d = ImageDraw.Draw(img)
        font = _font(int(cell_h * 0.8))
        d.text((cell_w, cell_h), ch, fill=255, font=font, anchor="mm")
        g = np.asarray(img, np.float64) / 255.0
        glyphs.append(g)
    return glyphs


# ----------------------------------------------------------------------------
#  template base
# ----------------------------------------------------------------------------

class Template:
    key = ""
    name = ""
    description = ""
    needs_image = False

    def __init__(self, ctx):
        self.ctx = ctx
        self.w = ctx.w
        self.h = ctx.h
        self.fps = ctx.fps

    def frame(self, i):
        raise NotImplementedError


class TemplateContext:
    """Shared context handed to every template."""

    def __init__(self, w, h, fps, arrays, primary=(0, 255, 90),
                 accent=(255, 40, 160), bg_image=None, title="",
                 overlay_matrix=False):
        self.w = w
        self.h = h
        self.fps = fps
        self.arrays = arrays
        self.t = arrays["t"]
        self.pulse = arrays["pulse"]
        self.flash = arrays["flash"]
        self.energy = arrays["energy"]
        self.bass = arrays["bass"]
        self.spectrum = arrays["spectrum"]
        self.beats = None
        self.primary = primary
        self.accent = accent
        self.title = title
        self.overlay_matrix = overlay_matrix
        self.rng = np.random.default_rng(20260718)
        self.bg_image = None
        if bg_image is not None:
            self.bg_image = self._prepare_image(bg_image)

    @staticmethod
    def _prepare_image(img):
        """Normalise a PIL image to float RGB, max 2560px on the long edge."""
        if img.mode != "RGB":
            img = img.convert("RGB")
        long_edge = max(img.size)
        if long_edge > 2560:
            scale = 2560 / long_edge
            img = img.resize((int(img.size[0] * scale), int(img.size[1] * scale)),
                             Image.LANCZOS)
        return np.asarray(img, np.float64) / 255.0


# ============================================================================
#  Template implementations
# ============================================================================

# ------------------------------------------------------------- Matrix Rain
class MatrixTemplate(Template):
    key = "matrix"
    name = "Matrix Rain"
    description = ("Classic falling-matrix glyphs. Green phosphor storm that "
                   "accelerates and flashes brighter on every beat.")
    bg = "black"

    def __init__(self, ctx):
        super().__init__(ctx)
        scale = 0.5
        self.cw, self.ch = int(round(12 * scale)) or 1, int(round(18 * scale)) or 1
        self.cols = max(1, self.w // self.cw)
        self.rows = max(1, self.h // self.ch)
        self.glyphs = build_glyph_atlas(self.cw, self.ch)
        self.ng = len(self.glyphs)
        rng = ctx.rng
        self.heads = rng.uniform(-self.h * 1.5, self.h * 0.1, self.cols).astype(np.float64)
        self.speeds = rng.uniform(60, 260, self.cols).astype(np.float64)
        self.lens = rng.integers(6, max(7, self.rows // 2), self.cols)
        self.chars = rng.integers(0, self.ng, (self.rows, self.cols))
        # pre-make glyph rgb slices: each glyph is (ch,cw) alpha
        self._grgb = [g[..., None] for g in self.glyphs]
        self._buf = None

    def frame(self, i):
        ctx = self.ctx
        h, w = self.h, self.w
        p = ctx.pulse[i]
        f = ctx.flash[i]
        dt = 1.0 / self.fps

        rng = ctx.rng
        # advance heads; beats accelerate
        boost = 1.0 + p * 2.5
        self.heads += self.speeds * dt * boost
        reset = self.heads > (h + self.ch * 2)
        if reset.any():
            n = int(reset.sum())
            self.heads[reset] = rng.uniform(-self.h, -self.ch, n)
            self.speeds[reset] = rng.uniform(60, 320, n)
            self.lens[reset] = rng.integers(6, max(7, self.rows // 2), n)
        # occasional early respawn on beats (new streaks burst in)
        if p > 0.35:
            burst = rng.random(self.cols) < (p * 0.5)
            self.heads[burst] = rng.uniform(-self.h * 0.5, 0.0, int(burst.sum()))

        # mutate characters: some change every frame, more on beats
        prob = 0.04 + p * 0.25
        morph = rng.random((self.rows, self.cols)) < prob
        self.chars[morph] = rng.integers(0, self.ng, int(morph.sum()))

        if self._buf is None or self._buf.shape != (h, w, 3):
            self._buf = np.empty((h, w, 3), np.float64)
        base = self._buf
        base[:] = 0.012
        base[:, :, 1] = 0.016
        for c in range(self.cols):
            head = self.heads[c]
            if head < 0:
                continue
            start = int(head // self.ch)
            length = int(self.lens[c])
            for r in range(start, min(start + length, self.rows)):
                if r < 0:
                    continue
                depth = r - start
                bright = np.exp(-depth / max(2.0, length * 0.55))
                if bright < 0.05:
                    break
                gi = self.chars[r, c]
                glyph = self._grgb[gi]
                y0 = r * self.ch
                x0 = c * self.cw
                region = base[y0:y0 + self.ch, x0:x0 + self.cw, :]
                if region.shape[:2] != glyph.shape[:2]:
                    continue
                g = region
                color = np.array([0.55, 1.0, 0.42], np.float64)
                if depth == 0:
                    color = np.array([1.0, 1.0, 0.95], np.float64)
                elif depth == 1:
                    color = np.array([0.75, 1.0, 0.55], np.float64)
                a = bright * (0.55 + 0.45 * f)
                np.maximum(g, glyph * color[None, None, :] * a, out=g)

        # green fog
        fog = base[..., 1] * 0.6
        base[..., 1] = np.maximum(base[..., 1], fog * 0.35)
        # beat flash lift
        lift = 1.0 + p * 0.9 + f * 0.6
        base *= lift
        if f > 0.4:
            flashv = (f - 0.4) / 0.6
            base = base + 0.35 * flashv * np.array([0.4, 1.0, 0.4])
        return pack_u8(clip_u8(base))


# ------------------------------------------------------------- Beat Pulse
class PulseTemplate(Template):
    key = "pulse"
    name = "Beat Pulse"
    description = ("Breathing colour-field background with expanding beat rings. "
                   "The background brightness and opacity pulse with the kick.")
    needs_image = False

    def __init__(self, ctx):
        super().__init__(ctx)
        w, h = self.w, self.h
        self.dist_low = radial_distance(max(1, w // 4), max(1, h // 4))
        pr = to_01(ctx.primary)
        ac = to_01(ctx.accent)
        self.p = np.array(pr, np.float64)
        self.a = np.array(ac, np.float64)
        self.hue0 = 0.0
        self.max_r = 1.15

    def frame(self, i):
        ctx = self.ctx
        w, h = self.w, self.h
        p = ctx.pulse[i]
        e = ctx.energy[i]
        t = ctx.t[i]

        # low-res computing canvas (4x down)
        lw, lh = max(1, w // 4), max(1, h // 4)

        hue = (0.02 * t + self.hue0) % 1.0
        rows = np.linspace(0.0, 0.22, lh, dtype=np.float64)[:, None]
        sat = 0.55 + 0.25 * np.sin(2 * np.pi * 0.11 * t)
        val = np.clip(0.35 + 0.30 * e + 0.25 * np.sin(2 * np.pi * 0.13 * t)
                      + 0.08 * ctx.bass[i], 0, 1)
        img = hsv_to_rgb(hue + rows, np.full((lh, lw), sat, np.float64),
                         np.full((lh, lw), val, np.float64))

        dist_l = self.dist_low
        ring_sum = np.zeros((lh, lw), np.float64)
        if ctx.beats is not None:
            recent = ctx.beats[(ctx.beats > t - 2.4) & (ctx.beats <= t)]
            for b in recent[-6:]:
                r = (t - b) * self.max_r
                ring_sum += np.exp(-((dist_l - r) ** 2) / (2 * (0.035) ** 2))
        else:
            rr = p * self.max_r
            ring_sum = np.exp(-((dist_l - rr) ** 2) / (2 * (0.035) ** 2))
        ring = np.clip(ring_sum, 0, 1)[..., None]
        ring_col = np.array([1.0, 1.0, 1.0]) * 0.9 + self.a * 0.1
        img = img + ring * ring_col * 0.85

        img = img * (0.85 + 0.5 * p)
        glow = np.exp(-dist_l * 3.0)[..., None]
        img = img + glow * self.a * (0.15 + 0.5 * p)

        img = upscale(img, 4, w, h, blur_k=4)
        return pack_u8(clip_u8(img))


# ------------------------------------------------------------- Spectrum Bars
class SpectrumTemplate(Template):
    key = "spectrum"
    name = "Spectrum Bars"
    description = ("Real-time frequency analyser bars (32 bands) mirrored top and "
                   "bottom, scaled and re-energised on every beat.")
    needs_image = False

    def __init__(self, ctx):
        super().__init__(ctx)
        w, h = self.w, self.h
        self.nbars = 64
        self.barw = w / self.nbars
        self.centery = h / 2
        self.maxh = h * 0.42
        pr = to_01(ctx.primary)
        self.prim = np.array(pr, np.float64)
        ac = to_01(ctx.accent)
        self.acc = np.array(ac, np.float64)

    def frame(self, i):
        ctx = self.ctx
        w, h = self.w, self.h
        p = ctx.pulse[i]
        spec = ctx.spectrum[i]                     # (N_BANDS,)
        v = spec - spec.mean()
        v = np.maximum(v, 0)
        v = np.clip(v / (np.max(v) + 1e-6), 0, 1) ** 1.4

        # map 32 bands onto 64 bars with slight smoothing
        bars = np.interp(np.linspace(0, 1, self.nbars) * (len(v) - 1),
                         np.arange(len(v)), v)
        bars = np.clip(bars * (0.7 + 0.6 * p) + 0.02 * p, 0, 1)

        xs = np.arange(w, dtype=np.float64)
        col = np.clip((xs / self.barw).astype(int), 0, self.nbars - 1)
        ht = self.maxh * bars[col]                 # per-column height
        _, ys = meshgrid(w, h)
        up = ys >= (self.centery - ht)
        dn = ys <= (self.centery + ht)
        mask = (up & dn).astype(np.float64)

        hue = (0.62 + 0.02 * ctx.t[i]) % 1.0
        colfrac = (col / self.nbars)
        colors = hsv_to_rgb(np.clip(hue + colfrac * 0.25, 0, 1),
                            np.full_like(colfrac, 0.9, np.float64),
                            np.full_like(colfrac, 1.0, np.float64))
        img = colors[None, :, :] * mask[..., None]

        # glow (blurred mask) + base dark gradient
        glow = blur(mask, 9)[..., None]
        base = vertical_gradient((0.03, 0.02, 0.05), (0.10, 0.06, 0.15), w, h)
        img = base + img * 0.9 + glow * self.acc * 0.35 * (0.6 + 0.6 * p)
        # mirror reflection fade
        fade = np.ones_like(ys)
        fade *= 0.55
        img *= fade[..., None]
        # beat flash
        img = img * (1.0 + p * 0.25)
        return pack_u8(clip_u8(img))


# ------------------------------------------------------------- Waveform
class WaveformTemplate(Template):
    key = "waveform"
    name = "Audiogram Wave"
    description = ("Scrolling full-track audio waveform with a glowing playhead, "
                   "beat rings and mirror symmetry. Classic YouTube audiogram.")
    needs_image = False

    def __init__(self, ctx):
        super().__init__(ctx)
        w, h = self.w, self.h
        self.centery = h / 2
        self.scale = h * 0.42
        self.sec_view = 3.5
        # per-frame peak array (short-time RMS blocks)
        analyzer = getattr(ctx, "_analyzer", None)
        if analyzer is not None and analyzer.duration:
            block = int(round(analyzer.sr / (self.w / self.sec_view)))
            x = analyzer.x
            n = len(x)
            m = max(1, block)
            nblocks = n // m
            rms = np.sqrt(np.add.reduceat(x[:nblocks * m] ** 2, np.arange(0, nblocks * m, m)) / m)
            self.wave = rms
            self.wave_s = m / analyzer.sr
            self._have_wave = True
        else:
            self.wave = np.zeros(512)
            self.wave_s = 0.01
            self._have_wave = False
        pr = to_01(ctx.primary)
        self.prim = np.array(pr, np.float64)
        ac = to_01(ctx.accent)
        self.acc = np.array(ac, np.float64)
        self.f = 2  # low-res render factor
        lw, lh = max(1, w // self.f), max(1, h // self.f)
        self._dist_low = radial_distance(lw, lh)

    def frame(self, i):
        ctx = self.ctx
        w, h = self.w, self.h
        f = self.f
        lw, lh = w // f, h // f
        p = ctx.pulse[i]
        t = ctx.t[i]

        wave = self.wave
        tw = self.wave_s
        t0 = max(0.0, t - self.sec_view)
        i0 = int(t0 / tw)
        span = max(1, int(self.sec_view / tw))
        seg = np.zeros(span)
        take = wave[i0:i0 + span]
        seg[:len(take)] = take
        seg = seg / (seg.max() + 1e-9)

        xs, ys = meshgrid(lw, lh)
        pix = np.linspace(0, len(seg) - 1, lw)
        amp = np.take(seg, pix.astype(int))
        amp = amp * (1.0 + p * 0.5)
        thick = (2 + 3 * p) / f + 0.4
        y_hi = self.centery - self.scale * amp - thick
        y_lo = self.centery + self.scale * amp + thick
        mask = ((ys >= y_hi[None, :]) & (ys <= y_lo[None, :])).astype(np.float64)

        colfrac = np.arange(lw, dtype=np.float64) / max(1, lw)
        hue = (0.58 + 0.015 * t) % 1.0
        colors = hsv_to_rgb(np.clip(hue + 0.15 * np.sin(2 * np.pi * colfrac), 0, 1),
                            np.full_like(colfrac, 0.85), np.full_like(colfrac, 1.0))
        img = colors[None, :, :] * mask[..., None]
        glow = (blur(mask, 3))[..., None]

        base = np.full((lh, lw, 3), 0.02, np.float64)
        img = base + img + glow * self.acc * (0.4 + 0.5 * p)

        # centre line
        img = img + (np.abs(ys - self.centery) < 1.0)[..., None] * np.array([0.4, 0.7, 1.0]) * 0.6
        # playhead
        phx = int(np.clip(((t - t0) / self.sec_view) * lw, 0, lw - 1))
        img = img + (np.abs(xs - phx) < 1.2)[..., None] * (self.acc * 0.9 + 0.5) * (0.6 + 0.4 * p)

        # beat rings behind
        ring = np.exp(-((self._dist_low - p * 1.1) ** 2) / (2 * 0.03 ** 2))[..., None]
        img = img + ring * self.acc * 0.5 * p

        img = upscale(img, f, w, h, blur_k=2)
        return pack_u8(clip_u8(img))


# ------------------------------------------------------------- Glitch
class GlitchTemplate(Template):
    key = "glitch"
    name = "Digital Glitch"
    description = ("RGB-split chromatic glitching, sliced scan bands and static "
                   "noise that detonates on every beat.")
    needs_image = False

    def __init__(self, ctx):
        super().__init__(ctx)
        w, h = self.w, self.h
        self._glitch = 0.0
        self.rng = np.random.default_rng(9)
        self.dist = radial_distance(w, h)
        pr = to_01(ctx.primary)
        self.prim = np.array(pr, np.float64)
        ac = to_01(ctx.accent)
        self.acc = np.array(ac, np.float64)
        self.static = self.rng.random((h, w, 1), dtype=np.float32)

    def frame(self, i):
        ctx = self.ctx
        w, h = self.w, self.h
        p = ctx.pulse[i]
        f = ctx.flash[i]
        t = ctx.t[i]

        hue = (0.80 + 0.03 * t) % 1.0
        base = hsv_to_rgb(np.full((h, w), hue), np.full((h, w), 0.5),
                          np.full((h, w), 0.16 + 0.10 * ctx.energy[i]))
        img = base * (1.0 + self.dist[..., None] * 0.4)

        self._glitch = max(self._glitch, p) * 0.8
        g = self._glitch

        # RGB split
        dx = int(g * 14 * (self.rng.random() - 0.5) * 2)
        r = np.roll(img[..., 0], dx, axis=1)
        gch = np.roll(img[..., 1], -dx, axis=1)
        b = np.roll(img[..., 2], int(dx * 0.6), axis=1)
        img = np.stack([r, gch, b], axis=-1)

        # horizontal slice displacement
        if g > 0.05:
            for _ in range(int(1 + g * 4)):
                y = self.rng.integers(0, h)
                hgt = self.rng.integers(4, 40)
                dxb = int(g * self.rng.integers(-60, 60))
                img[y:y + hgt] = np.roll(img[y:y + hgt], dxb, axis=1)

        # static noise
        if g > 0.02:
            s = self.static
            img = img + (s * 0.35 * g)
            img = img - (s * 0.35 * g * 0.5)

        # beat white flash
        if f > 0.15:
            img = img + (f - 0.15) * 1.4

        # chromatic fringe bars
        img[::9] *= 1.25
        return pack_u8(clip_u8(img))


# ------------------------------------------------------------- Particles
class ParticlesTemplate(Template):
    key = "particles"
    name = "Beat Fireworks"
    description = ("Particle bursts detonate from the stage glow on every beat; "
                   "each burst uses its own colour from your palette.")
    needs_image = False

    def __init__(self, ctx):
        super().__init__(ctx)
        w, h = self.w, self.h
        self.N = 1400
        rng = ctx.rng
        self.pos = np.zeros((self.N, 2), np.float64)
        self.vel = np.zeros((self.N, 2), np.float64)
        self.life = np.zeros(self.N)
        self.hue = rng.random(self.N)
        self.grav = 90.0
        self._burst = 0
        self.dist = radial_distance(w, h)
        pr = to_01(ctx.primary)
        self.prim = np.array(pr, np.float64)
        ac = to_01(ctx.accent)
        self.acc = np.array(ac, np.float64)
        self.glow = np.zeros((h // 8, w // 8), np.float64)

    def _spawn(self, count, t):
        rng = self.ctx.rng
        w, h = self.w, self.h
        dead = np.where(self.life <= 0)[0]
        k = min(int(count), len(dead))
        if k <= 0:
            return
        idx = dead[:k]
        pos = self.pos[idx]
        vel = self.vel[idx]
        life = self.life[idx]
        cx = w / 2 + rng.normal(0, w * 0.10, k)
        cy = h * 0.82 + rng.normal(0, h * 0.03, k)
        pos[:, 0] = cx
        pos[:, 1] = cy
        ang = rng.uniform(-np.pi, 0, k)
        spd = rng.uniform(60, 260, k)
        vel[:, 0] = np.cos(ang) * spd
        vel[:, 1] = np.sin(ang) * spd
        life[:] = rng.uniform(0.8, 2.2)
        self.hue[idx] = rng.uniform(0, 1, k)

    def frame(self, i):
        ctx = self.ctx
        w, h = self.w, self.h
        p = ctx.pulse[i]
        t = ctx.t[i]
        dt = 1.0 / self.fps

        if ctx.beats is not None:
            if t in ctx.beats or p > 0.6:
                self._spawn(260 + 300 * p, t)
        else:
            self._burst -= dt
            if self._burst <= 0:
                self._spawn(300, t)
                self._burst = 0.9

        alive = self.life > 0
        if alive.any():
            self.pos[alive] += self.vel[alive] * dt
            self.vel[alive, 1] += self.grav * dt
            self.life[alive] -= dt
            off = (self.pos[:, 0] < -20) | (self.pos[:, 0] > w + 20) | (self.pos[:, 1] > h + 20)
            self.life[off] = 0.0

        base = vertical_gradient((0.01, 0.005, 0.02), (0.09, 0.02, 0.12), w, h)
        stage = np.exp(-np.abs(np.arange(h, dtype=np.float64) - h * 0.9) / (h * 0.15))[:, None, None]
        img = base + stage * (self.acc * 0.5 + self.prim * 0.3) * (0.4 + 0.8 * p)

        # accumulate particle glow on a small buffer, then upscale+blur
        sw, sh = int(np.ceil(w / 8)), int(np.ceil(h / 8))
        buf = np.zeros((sh, sw), np.float64)
        alive = self.life > 0
        if alive.any():
            gx = np.clip((self.pos[alive, 0] / w * sw).astype(int), 0, sw - 1)
            gy = np.clip((self.pos[alive, 1] / h * sh).astype(int), 0, sh - 1)
            a = np.clip(self.life[alive] / 2.0, 0, 1)
            np.add.at(buf, (gy, gx), a)
        buf = blur(buf, 3)
        big = np.repeat(np.repeat(buf, 8, axis=0), 8, axis=1)
        big = big[:h, :w, None]

        # colour each pixel by radial hue mix
        colfrac = np.clip(np.sqrt(self.dist), 0, 1)
        hue = np.clip(0.02 * t + colfrac * 0.6, 0, 1)
        col = hsv_to_rgb(hue, np.full_like(hue, 0.85), np.full_like(hue, 1.0))
        img = img + big * col * 1.1 * (0.7 + 0.6 * p)

        # twinkle floor
        img = img + 0.02 * ctx.energy[i]
        return pack_u8(clip_u8(img))


# ------------------------------------------------------------- Image Zoom
class ImageZoomTemplate(Template):
    key = "image"
    name = "Photo Zoom (Ken Burns)"
    description = ("Your custom background image slowly zooms and pans to the "
                   "music, flashing and colour-pulsing on every beat.")
    needs_image = True

    def __init__(self, ctx):
        super().__init__(ctx)
        w, h = self.w, self.h
        self.ar = w / h
        self.zoom0 = 1.02
        self.zoom1 = 1.28
        self._slow = 0.0
        pr = to_01(ctx.primary)
        self.prim = np.array(pr, np.float64)
        ac = to_01(ctx.accent)
        self.acc = np.array(ac, np.float64)
        self.dist = radial_distance(w, h)

    def frame(self, i):
        ctx = self.ctx
        w, h = self.w, self.h
        t = ctx.t[i]
        p = ctx.pulse[i]
        f = ctx.flash[i]
        n = len(ctx.t)
        u = (t / (n / self.fps)) if n else 0.0

        if ctx.bg_image is None:
            img = vertical_gradient((0.05, 0.05, 0.15), (0.3, 0.1, 0.3), w, h)
        else:
            src = ctx.bg_image
            sh, sw = src.shape[:2]
            zoom = self.zoom0 + (self.zoom1 - self.zoom0) * u
            if p > 0.4:
                self._slow = 0.02
            else:
                self._slow = max(0.0, self._slow - 0.003)
            zoom += self._slow
            # fit-cover target region
            base_w = w / zoom
            base_h = base_w / self.ar
            if base_h < h / zoom:
                base_h = h / zoom
                base_w = base_h * self.ar
            panx = 0.5 + 0.15 * np.sin(t * 0.05)
            pany = 0.5 + 0.12 * np.cos(t * 0.037)
            cxm = panx * sw
            cym = pany * sh
            x0 = int(np.clip(cxm - base_w / 2, 0, max(0, sw - base_w)))
            y0 = int(np.clip(cym - base_h / 2, 0, max(0, sh - base_h)))
            crop = src[y0:int(min(y0 + base_h, sh)), x0:int(min(x0 + base_w, sw))]
            if crop.size == 0:
                return pack_u8(clip_u8(np.full((h, w, 3), 0.02)))
            img = np.asarray(Image.fromarray(pack_u8(crop)).resize((w, h), Image.LANCZOS),
                             np.float64) / 255.0

        # beat reaction: flash + color wash + vignette pulse
        wash = self.acc * (0.12 + 0.30 * p) + self.prim * 0.10 * p
        img = img * (1.0 - 0.30 * p) + wash * 0.30 * p
        img = img + f * 0.22 * np.array([1.0, 0.95, 0.9])
        vign = np.exp(-(self.dist ** 2) * 1.6)[..., None]
        img = img * (0.55 + 0.45 * vign)
        img = img + (1.0 - vign) * 0.05 * p
        return pack_u8(clip_u8(img))


# ------------------------------------------------------------- Synthwave
class SynthwaveTemplate(Template):
    key = "synthwave"
    name = "Synthwave Grid"
    description = ("Retro sunset, neon sun with scanlines and a perspective grid "
                   "that surges toward you on every beat.")
    needs_image = False

    def __init__(self, ctx):
        super().__init__(ctx)
        w, h = self.w, self.h
        self.horizon = int(h * 0.56)
        self.vpx, self.vpy = w / 2, self.horizon
        self._t_adv = 0.0
        self.gf = 4  # grid render factor (low res)

        # ---- sky rows (per-row colour, cheap to fill) ----
        hs = np.arange(self.horizon, dtype=np.float64) / max(1, self.horizon)
        self.skyrows = (np.array([0.06, 0.02, 0.18]) * (1 - hs)[:, None] +
                        np.array([0.46, 0.10, 0.42]) * hs[:, None])
        self.hglow_row = np.exp(-np.abs((np.arange(h, dtype=np.float64) - self.horizon) / h) / 0.02)
        self.hglow_col = np.array([1.0, 0.45, 0.25]) * 0.5
        self.base_col = np.array([0.02, 0.01, 0.06])

        # ---- sun (full-res, static) ----
        xs, ys = meshgrid(w, h)
        rr = np.sqrt((xs - w / 2) ** 2 + (ys - (self.horizon + h * 0.14)) ** 2) / (h * 0.30)
        sun = np.clip(1.0 - rr * rr, 0, 1) ** 2
        self.sun_rgb = sun[..., None] * np.array([1.0, 0.55, 0.25])
        scan = ((ys % 6) < 3).astype(np.float64)
        self.sun_scan = sun[:, :, None] * scan[:, :, None] * 0.12 * np.array([1.0, 0.3, 0.1])

        # ---- stars (sparse full-res field, vectorised flicker) ----
        rng = np.random.default_rng(42)
        star_y = rng.integers(2, self.horizon - 2, 260)
        star_x = rng.integers(0, w, 260)
        star_a = rng.uniform(0.3, 1.0, 260)
        star_ph = rng.uniform(0, 6, 260)
        self.starfield = np.zeros((self.horizon, w), np.float32)
        self.starfield[star_y, star_x] = star_a
        self.star_phase = np.zeros_like(self.starfield)
        self.star_phase[star_y, star_x] = star_ph

        # ---- vertical perspective grid lines (static, low-res) ----
        gw, gh = max(1, int(np.ceil(w / self.gf))), max(1, int(np.ceil(h / self.gf)))
        self.gw, self.gh = gw, gh
        gxs, gys = meshgrid(gw, gh)
        vmask = np.zeros((gh, gw), np.float64)
        vpxg, vpyg = self.vpx / self.gf, self.vpy / self.gf
        for k in range(-12, 13):
            xbg = self.vpx / self.gf + k * (gw / 13.0)
            xr = (gxs - vpxg) / (xbg - vpxg + 1e-9)
            yr = (gys - vpyg) / (gh - vpyg + 1e-9)
            m = (np.abs(xr - yr) < 0.03) & (gys >= self.vpy / self.gf)
            vmask += m.astype(np.float64)
        self.vmask = np.clip(vmask, 0, 1)
        self.neon = np.array([1.0, 0.2, 0.75])
        self.glow_c = np.array([0.42, 0.05, 0.45])

    def frame(self, i):
        ctx = self.ctx
        w, h = self.w, self.h
        p = ctx.pulse[i]
        t = ctx.t[i]
        gf = self.gf
        gw, gh = self.gw, self.gh

        # ---- sky ----
        sky = np.zeros((h, w, 3), np.float64)
        sky[:self.horizon] = self.skyrows[:, None, :]
        sky = sky + self.hglow_row[:, None, None] * self.hglow_col
        sky += self.sun_rgb * (0.65 + 0.4 * p) + self.sun_scan
        flick = self.starfield * (0.5 + 0.5 * np.sin(t * 3.0 + self.star_phase))
        sky[:self.horizon] += flick[..., None] * (0.5 + 0.5 * ctx.energy[i]) * np.array([1.0, 0.9, 0.8])
        sky[self.horizon:] = self.base_col

        # ---- grid (computed at low res) ----
        if p > 0.15:
            self._t_adv += p * 0.9
        self._t_adv += 0.012
        tz = self._t_adv

        grid = np.zeros((gh, gw, 3), np.float64)
        f = self.horizon + (h - self.horizon) * 0.06
        hb = h - self.horizon
        for k in range(1, 22):
            z = k * 0.45 - tz * 0.5
            if z < 0:
                z = z % 4.4
            zy = (self.horizon + hb * (f / (f + z * 1000))) / gf
            m = (np.abs(np.arange(gh, dtype=np.float64) - zy) < 1.2)
            grid += m[:, None, None] * self.neon * (0.55 + 0.55 * p)
        v = np.clip(self.vmask, 0, 1)[..., None]
        grid = grid + v * self.neon * (0.5 + 0.5 * p)

        glow_low = blur(np.max(grid, axis=-1), 3)  # (gh, gw)
        grid_f = upscale(np.clip(grid, 0, 1), gf, w, h, blur_k=5)
        glow = upscale(glow_low, gf, w, h, blur_k=7)[..., None]

        sky = sky + glow * self.glow_c * (1.6 + 1.4 * p)
        sky[self.horizon:] = sky[self.horizon:] + grid_f[self.horizon:]
        sky[self.horizon:] += glow[self.horizon:] * self.glow_c * 2.2

        sky = sky * (1.0 + 0.12 * p)
        return pack_u8(clip_u8(sky))


# ----------------------------------------------------------------------------
#  registry
# ----------------------------------------------------------------------------

TEMPLATES = [
    MatrixTemplate,
    PulseTemplate,
    SpectrumTemplate,
    WaveformTemplate,
    GlitchTemplate,
    ParticlesTemplate,
    ImageZoomTemplate,
    SynthwaveTemplate,
]


def register_templates():
    return [t.key for t in TEMPLATES]


def get_template(key):
    for t in TEMPLATES:
        if t.key == key:
            return t
    raise KeyError(key)
