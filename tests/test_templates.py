import numpy as np
import pytest
from PIL import Image

from engine.audio import SynthTrack
from engine.templates import (
    TEMPLATES,
    TemplateContext,
    get_template,
    hex_to_rgb,
    register_templates,
)


def make_ctx(w=160, h=90, fps=30, duration=3.0, bg=None,
             primary=(0, 255, 90), accent=(255, 40, 160)):
    track = SynthTrack(duration=duration, bpm=120)
    arrays = track.frame_arrays(fps, int(duration * fps))
    ctx = TemplateContext(w, h, fps, arrays, primary=primary, accent=accent, bg_image=bg)
    ctx.beats = track.beats
    return ctx


@pytest.mark.parametrize("cls", TEMPLATES, ids=[t.key for t in TEMPLATES])
def test_every_template_renders_a_frame(cls):
    ctx = make_ctx()
    templ = cls(ctx)
    frame = templ.frame(0)
    assert frame.shape == (ctx.h, ctx.w, 3)
    assert frame.dtype == np.uint8
    assert frame.min() >= 0 and frame.max() <= 255


@pytest.mark.parametrize("cls", TEMPLATES, ids=[t.key for t in TEMPLATES])
def test_every_template_renders_30_frames(cls):
    ctx = make_ctx()
    templ = cls(ctx)
    for i in range(30):
        assert templ.frame(i).shape == (90, 160, 3)


def test_image_zoom_with_background():
    bg = Image.new("RGB", (64, 64), (30, 30, 200))
    ctx = make_ctx(bg=bg)
    templ = get_template("image")(ctx)
    frame = templ.frame(15)
    assert frame.shape == (90, 160, 3)
    assert frame.dtype == np.uint8


def test_image_zoom_without_background_falls_back():
    ctx = make_ctx()
    templ = get_template("image")(ctx)
    frame = templ.frame(5)
    assert frame.shape == (90, 160, 3)


def test_registry():
    keys = register_templates()
    assert len(keys) == 8
    for t in TEMPLATES:
        assert t.key in keys


def test_get_template():
    assert get_template("synthwave").key == "synthwave"
    with pytest.raises(KeyError):
        get_template("does-not-exist")


def test_hex_to_rgb():
    assert hex_to_rgb("#00ff5a") == (0, 255, 90)
    assert hex_to_rgb("ff28a8") == (255, 40, 168)


def test_template_metadata():
    for t in TEMPLATES:
        assert t.name
        assert t.description
        assert t.key
