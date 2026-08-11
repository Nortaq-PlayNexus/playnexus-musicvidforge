# Troubleshooting

Common issues and fixes.

## `ffmpeg` not found / "No such file or directory" when rendering

ffmpeg is not on your PATH.

1. Download the gyan.dev build: https://www.gyan.dev/ffmpeg/builds/.
2. Unzip it, e.g. to `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to PATH (Start → "Edit environment variables").
4. Restart your terminal and verify with `ffmpeg -version`.

## App opens but a song never shows BPM

Beat detection needs a decodable audio file. Check:

- The file is a standard format (MP3, WAV, M4A, FLAC, OGG).
- The file isn't zero-length or DRM-protected (iTunes purchases are usually DRM-locked).
- Your Python is 3.10+ and `numpy` is installed (`pip show numpy`).

## Render finishes but the video is silent

The mux step needs the original audio. Try re-rendering; if it persists, reinstall
ffmpeg (older builds occasionally drop AAC mux). Check the file plays in a media
player that supports AAC (VLC, MPC-HC).

## Render is stuck at 1%

A 4K render of a long song produces a lot of frames — the progress bar updates per
**frame batch**. For a very long track, the first percent can take a while.
Verify with a 10-second clip at 720p to confirm the pipeline works, then scale up.

## NVENC not available even though I have an NVIDIA GPU

- Your GPU must support NVENC (most GTX 10-series+ cards do).
- The ffmpeg build must include NVENC (the gyan.dev "full" build does; the
  "essentials" build may not). Re-download the **ffmpeg-release-full** build.
- Driver must be reasonably current.

## Window looks blurry / tiny on a 4K display

The Tkinter GUI does not auto-scale on HiDPI in all setups. Set a Windows display
scaling you are comfortable with; the *rendered output* is unaffected and is
always crisp at the resolution you choose.

## Video opens but is upside down / stretched

This happens only if an unusual source was used. Re-render with the built-in
templates — they output native 16:9, 9:16 or 1:1 geometry as selected.

## Still stuck?

Open an issue at https://github.com/Nortaq-PlayNexus/playnexus-musicvidforge/issues
and include: your OS, Python version, ffmpeg version, template used, resolution/FPS,
and the exact error text.
