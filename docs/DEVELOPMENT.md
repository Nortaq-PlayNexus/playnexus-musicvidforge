# Development

Guide for running, testing and extending MusicVidForge.

## Running from source

```powershell
.venv\Scripts\activate
python app.py
```

## Project layout

```
app.py                  # Tkinter GUI — all UI logic lives here
engine/
├── __init__.py
├── audio.py            # audio loading, BPM + beat detection (NumPy)
├── templates.py        # 8 visual templates; each returns a frame given (frame_no, state)
└── render.py           # frame loop, PIL compositing, ffmpeg encode & mux
tests/                  # pytest suite (no GUI, engine-level only)
```

## Running the tests

```powershell
pip install -r requirements.txt pytest
pytest -v
```

The tests exercise the engine (audio + rendering) without opening the GUI.

## How templates work

Each template in `engine/templates.py` is a function that, given the current
frame index and a render state, returns a `PIL.Image`. The render loop
(`engine/render.py`) handles:

- resizing & compositing overlays (vignette, scanlines, flash, matrix overlay)
- writing frames to ffmpeg's stdin pipe
- muxing the original audio back in

To add a new template:

1. Add a `*_frame(...)` function in `engine/templates.py` that returns a `PIL.Image`.
2. Register it in the template registry used by the GUI (`app.py`).
3. Add an entry to the README template table.
4. (Optional) add a smoke test in `tests/` that renders a few frames.

## Style guide

- Python 3.10+ typing, keep functions small and single-purpose.
- No comments that restate code; use docstrings for public helpers.
- No new dependencies unless they add clear value — NumPy + Pillow cover most needs.
- Match the existing naming conventions (`snake_case` for functions/variables).

## Rendering at a glance

```
app.py  →  engine/audio.py (analyze → beats)
        →  engine/render.py:
             for each frame:
               frame = templates.<template>_frame(i, state)
               apply overlays
               pipe raw RGB to ffmpeg stdin
             ffmpeg muxes audio + encodes → .mp4
```
