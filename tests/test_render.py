import json
import os
import shutil
import subprocess

import pytest

from engine.audio import TrackAnalyzer
from engine.render import ENCODERS, build_ffmpeg_command, render_video
from engine.templates import get_template


def test_encoders_defined():
    assert set(ENCODERS) == {"YouTube (H.264, max compat)",
                             "Max Quality (H.265/HEVC)",
                             "GPU Fast (NVIDIA NVENC)"}


def test_build_ffmpeg_command():
    cmd = build_ffmpeg_command("in.mp3", "out.mp4", 160, 90, 320, 180, 30, 2.0,
                               "YouTube (H.264, max compat)")
    assert cmd[0] == "ffmpeg"
    assert "-c:v" in cmd
    assert "-c:a" in cmd
    assert "out.mp4" in cmd


def test_render_scale_changes_vf():
    cmd = build_ffmpeg_command("in.mp3", "out.mp4", 160, 90, 320, 180, 30, 2.0,
                               "YouTube (H.264, max compat)")
    assert "-vf" in cmd  # render res differs from target res -> lanczos scale


def test_render_small_clip(beat_wav, tmp_path):
    path, _ = beat_wav
    analyzer = TrackAnalyzer(path)
    out = str(tmp_path / "clip.mp4")
    render_video(
        analyzer,
        get_template("synthwave"),
        out, path,
        fps=24, w=320, h=180,
        primary=(0, 255, 90), accent=(255, 40, 160),
        bg_image=None, title="TEST", watermark="",
        render_scale=1.0,
    )
    assert os.path.getsize(out) > 1000

    if shutil.which("ffprobe"):
        duration = _probe_duration(out)
        assert duration == pytest.approx(5.0, abs=0.5)


def _probe_duration(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(p.stdout)["format"]["duration"])
