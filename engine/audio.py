"""Audio analysis: decode an audio file through ffmpeg and build beat/spectrum data.

Only numpy is required. Everything is driven by ffmpeg subprocesses.
"""

import shutil
import subprocess

import numpy as np

SR = 22050          # analysis sample rate
NFFT = 2048         # fft size for the spectrogram
HOP = 512           # hop size (samples) -> ~43 analysis frames per second
N_BANDS = 32        # log-spaced frequency bands kept for the visualisers


def _moving_average(x, w):
    """Centered moving average with reflected edges (numpy only)."""
    w = int(w)
    if w <= 1:
        return x.astype(np.float64).copy()
    n = len(x)
    pad = np.full(w, x[0], dtype=np.float64)
    pad_end = np.full(w, x[-1], dtype=np.float64)
    y = np.concatenate([pad, x.astype(np.float64), pad_end])
    c = np.cumsum(y)
    out = (c[2 * w:2 * w + n] - c[:n]) / (2 * w)
    return out


class TrackAnalyzer:
    """Decodes a song and exposes per-video-frame arrays for the templates."""

    def __init__(self, path, sensitivity=0.5):
        self.path = path
        self.sensitivity = float(sensitivity)
        self.sr = SR
        self.hop = HOP
        self.x = self._decode(path)
        self._build()

    # ------------------------------------------------------------------ decode
    @staticmethod
    def _ffmpeg():
        exe = shutil.which("ffmpeg")
        if not exe:
            raise RuntimeError(
                "ffmpeg was not found on PATH. Download it from https://ffmpeg.org "
                "and make sure ffmpeg.exe is reachable from the command line."
            )
        return exe

    def _decode(self, path):
        cmd = [self._ffmpeg(), "-v", "error", "-i", path,
               "-vn", "-ac", "1", "-ar", str(self.sr), "-f", "f32le", "pipe:1"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        raw = p.stdout.read()
        err = p.stderr.read().decode(errors="ignore")
        p.wait()
        if not raw:
            raise RuntimeError("ffmpeg could not decode the audio file.\n" + err)
        return np.frombuffer(raw, dtype=np.float32).copy()

    # -------------------------------------------------------------- analysis
    def _build(self):
        x = self.x
        n = len(x)
        nf = max(0, (n - NFFT) // HOP)
        if nf < 10:
            raise RuntimeError("The audio file is too short to analyse.")
        self.duration = n / self.sr

        window = np.hanning(NFFT).astype(np.float32)
        spec = np.empty((nf, NFFT // 2 + 1), dtype=np.float32)
        for i in range(nf):
            seg = x[i * HOP:i * HOP + NFFT] * window
            spec[i] = np.abs(np.fft.rfft(seg))

        self.spec = spec
        freqs = np.fft.rfftfreq(NFFT, 1.0 / self.sr)

        # log-spaced bands
        edges = np.geomspace(30.0, 12000.0, N_BANDS + 1)
        bands = np.zeros((nf, N_BANDS), dtype=np.float32)
        for b in range(N_BANDS):
            m = (freqs >= edges[b]) & (freqs < edges[b + 1])
            if m.any():
                bands[:, b] = spec[:, m].mean(axis=1)
        self.band_log = np.log(np.maximum(bands, 0.0) + 1e-8).astype(np.float32)

        diff = np.maximum(np.diff(self.band_log, axis=0, prepend=self.band_log[:1]), 0.0)
        flux = 0.5 * diff.mean(axis=1) + 0.5 * diff.max(axis=1)

        bass = bands[:, :6].mean(axis=1)

        def norm01(v):
            hi = float(np.percentile(v, 98))
            if hi <= 1e-6 or not np.isfinite(hi):
                return np.zeros_like(v, dtype=np.float64)
            return np.clip(v / hi, 0.0, 1.0)

        flux_n = norm01(flux)
        bass_n = norm01(bass)
        onset = flux_n * 0.7 + bass_n * 0.3
        self._onset = onset
        self._bass_n = bass_n

        # detect beats from the smoothed onset envelope
        hop_s = HOP / SR
        smooth_w = int(round(0.40 / hop_s))
        env = _moving_average(onset, smooth_w)
        hi = float(np.percentile(env, 98))
        if hi <= 1e-6:
            hi = 1.0
        env_n = np.clip(env / hi, 0.0, 1.0)
        self._env_n = env_n

        k = 1.30 - float(self.sensitivity) * 0.70   # stronger slider -> easier beats
        base = _moving_average(env, max(2, int(round(0.5 / hop_s))))
        thresh = base * k

        # ---- tempo estimate via autocorrelation of the onset envelope ----
        n_ac = len(env)
        envc = env - env.mean()
        max_lag = int(round(min(0.9, n_ac * hop_s) / hop_s))
        min_lag = int(round(0.28 / hop_s))
        ac = np.correlate(envc, envc, "full")[n_ac - 1:n_ac + max_lag]
        if len(ac) > min_lag:
            lag = int(np.argmax(ac[min_lag:]) + min_lag)
            period_s = lag * hop_s
            bpm = 60.0 / period_s
            while bpm > 165:
                bpm /= 2.0
            while bpm < 75:
                bpm *= 2.0
            self.bpm = round(bpm, 1)
            min_gap = int(round(0.42 * period_s / hop_s))
        else:
            self.bpm = 0.0
            min_gap = int(round(0.27 / hop_s))

        peaks = []
        i = 1
        m = len(env)
        while i < m - 1:
            if env[i] >= env[i - 1] and env[i] > env[i + 1] and env[i] > thresh[i]:
                peaks.append(i)
                i += min_gap
            else:
                i += 1
        if not peaks:
            peaks = [0]
        self._peaks = np.array(peaks)
        self.beats = self._peaks * hop_s
        self.beat_strength = env[self._peaks]

    # ----------------------------------------------------- per-frame helpers
    def frame_arrays(self, fps, n_frames):
        t = np.arange(n_frames, dtype=np.float64) / fps
        hop_s = HOP / SR
        a_t = (np.arange(len(self._env_n)) + 0.5) * hop_s

        energy = np.interp(t, a_t, self._env_n, left=0.0, right=0.0)
        bass = np.interp(t, a_t, self._bass_n, left=0.0, right=0.0)

        beats = self.beats
        idx = np.searchsorted(beats, t, side="right") - 1
        prev = np.where(idx >= 0, beats[np.clip(idx, 0, None)], -1e9)
        dt = t - prev
        pulse = np.exp(-dt * 6.0)
        flash = np.exp(-dt * 16.0)

        spec_v = np.empty((n_frames, N_BANDS), dtype=np.float32)
        a = self.band_log
        for col in range(N_BANDS):
            spec_v[:, col] = np.interp(t, a_t, a[:, col], left=a[0, col], right=a[-1, col])

        return {
            "t": t.astype(np.float32),
            "energy": energy.astype(np.float32),
            "bass": bass.astype(np.float32),
            "pulse": pulse.astype(np.float32),
            "flash": flash.astype(np.float32),
            "spectrum": spec_v,
        }


class SynthTrack:
    """Synthetic beat track used for previews before a real song is loaded."""

    def __init__(self, duration=6.0, bpm=120):
        self.duration = duration
        self.bpm = bpm
        self.beats = np.arange(0.2, duration - 0.3, 60.0 / bpm)
        self._env_n = None

    def frame_arrays(self, fps, n_frames):
        t = np.arange(n_frames, dtype=np.float64) / fps
        idx = np.searchsorted(self.beats, t, side="right") - 1
        prev = np.where(idx >= 0, self.beats[np.clip(idx, 0, None)], -1e9)
        dt = t - prev
        pulse = np.exp(-dt * 6.0)
        flash = np.exp(-dt * 16.0)
        energy = 0.25 + 0.75 * pulse
        bass = pulse
        spec_v = np.empty((n_frames, N_BANDS), dtype=np.float32)
        spec_v[:] = np.logspace(-2, 0.0, N_BANDS)[None, :]
        spec_v *= (0.6 + 0.4 * pulse[:, None])
        return {
            "t": t.astype(np.float32),
            "energy": energy.astype(np.float32),
            "bass": bass.astype(np.float32),
            "pulse": pulse.astype(np.float32),
            "flash": flash.astype(np.float32),
            "spectrum": spec_v + np.random.default_rng(0).normal(0, 0.05, spec_v.shape).astype(np.float32),
        }
