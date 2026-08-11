import wave

import numpy as np
import pytest


@pytest.fixture
def beat_wav(tmp_path):
    """Write a short WAV containing a clean 120 BPM click track."""
    sr = 22050
    bpm = 120.0
    beat_dur = 60.0 / bpm
    duration = 5.0
    n = int(sr * duration)
    sig = np.zeros(n)

    beat_times = np.arange(0.5, duration - 0.2, beat_dur)
    kick_n = int(0.15 * sr)
    k = np.arange(kick_n)
    env = np.exp(-k / (0.030 * sr))
    click = np.sin(2 * np.pi * 60.0 * k / sr) * env
    for bt in beat_times:
        onset = int(bt * sr)
        end = min(n, onset + kick_n)
        sig[onset:end] += click[:end - onset]

    sig = np.clip(sig * 0.6, -1.0, 1.0)
    pcm = (sig * 32767).astype(np.int16)

    path = tmp_path / "beat.wav"
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return str(path), bpm
