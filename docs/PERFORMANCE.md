# Performance

Render time is dominated by **resolution × frame count × encoder speed**. Here is
how to get the fastest results without sacrificing quality.

## The trade-off ladder

| Setting | Use when | Notes |
|---|---|---|
| `720p / 30fps / H.264` | Testing, quick drafts | Fastest preview |
| `1080p / 60fps / H.264` | Default for YouTube | Great quality/speed balance (CRF 18) |
| `4K / H.265` | Max quality | Slowest encode, best compression |
| `NVENC` | NVIDIA GPU available | ~2-5× faster encodes than CPU |

## Rules of thumb

- **Lower resolution first.** A 4K render of a long song can take a very long
  time. Verify your template with 720p, then scale up.
- **FPS matters as much as resolution.** 60fps = double the frames of 30fps.
- **NVENC is a free win if you have a modern NVIDIA card.** H.264 NVENC is a
  solid default for sharing to social platforms.
- **H.265 (HEVC)** compresses ~50% better at equal quality but encodes slower —
  use it for archival / max quality, not drafts.

## What each template costs

- **Spectrum Bars / Audiogram Wave** — cheap; light per-frame FFT work.
- **Matrix Rain / Beat Fireworks** — moderate; particle state per pixel.
- **Photo Zoom** — expensive at high resolutions; large image rescale each frame
  (internally cached where possible).

## Practical tips

- Render short clips (30-60s) to preview a template before doing the full song.
- Close other heavy apps during 4K renders.
- If you render often, keep ffmpeg up to date — newer builds have faster SIMD
  codecs.
- The progress bar reflects frames written; a pause late in the render is
  usually the final audio mux finishing.
