import pytest

from engine.audio import SynthTrack, TrackAnalyzer


def test_synth_track_has_beats():
    track = SynthTrack(duration=6.0, bpm=120)
    assert track.bpm == 120
    assert len(track.beats) >= 10
    assert track.duration == pytest.approx(6.0)


def test_synth_track_frame_arrays():
    track = SynthTrack(duration=6.0, bpm=120)
    arrays = track.frame_arrays(fps=30, n_frames=90)
    for key in ("t", "energy", "bass", "pulse", "flash"):
        assert arrays[key].shape == (90,)
    assert arrays["pulse"].min() >= 0.0
    assert arrays["pulse"].max() <= 1.0
    assert arrays["spectrum"].shape == (90, 32)


def test_analyzer_detects_bpm(beat_wav):
    path, expected_bpm = beat_wav
    analyzer = TrackAnalyzer(path)
    # synthetic 120 BPM clicks must be found within tolerance
    assert 90 <= analyzer.bpm <= 150
    assert analyzer.duration == pytest.approx(5.0, abs=0.2)
    assert len(analyzer.beats) >= 6


def test_analyzer_frame_arrays(beat_wav):
    path, _ = beat_wav
    analyzer = TrackAnalyzer(path)
    fps = 30
    n_frames = 75
    arrays = analyzer.frame_arrays(fps, n_frames)
    for key in ("t", "energy", "bass", "pulse", "flash"):
        assert arrays[key].shape == (n_frames,)
    assert arrays["spectrum"].shape == (n_frames, 32)
    assert arrays["pulse"].max() <= 1.01


@pytest.mark.parametrize("sensitivity", [0.0, 0.5, 1.0])
def test_analyzer_sensitivity_is_legal(beat_wav, sensitivity):
    path, _ = beat_wav
    analyzer = TrackAnalyzer(path, sensitivity=sensitivity)
    assert analyzer.bpm >= 0
