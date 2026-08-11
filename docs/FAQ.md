# FAQ

### Does MusicVidForge upload my music or videos anywhere?

No. Analysis and rendering happen entirely on your machine. There are no network
calls in the codebase.

### Do I need an NVIDIA GPU?

No. All templates work on CPU. NVENC is an optional accelerator for faster
encoding if you have a supported NVIDIA card.

### Why do I need ffmpeg installed separately?

ffmpeg is the industry-standard encoder and is best installed at the system
level (it gets regular updates and SIMD optimisations). MusicVidForge talks to it
as a subprocess rather than bundling a copy.

### Which platforms are supported?

Officially Windows. The code is portable Python + Tkinter, so macOS/Linux may
work, but Windows is the tested target.

### Can I use my own images?

Yes — the **Photo Zoom** template renders your image with a Ken Burns pan/zoom,
and a custom background image is supported by **Matrix Rain**.

### Can I render vertical (9:16) or square (1:1) videos?

Yes. Choose **9:16** for Shorts/TikTok/Reels or **1:1** for feed posts.

### What resolution should I use?

`1080p 60fps H.264` is a great default for YouTube. Use 4K + H.265 for maximum
quality and NVENC if you have an NVIDIA GPU and want speed.

### How accurate is the beat detection?

It uses spectral flux (FFT-based onset detection) — very reliable for drums and
EDM. Very sparse/acoustic music may detect fewer, softer beats; the **beat
sensitivity** slider lets you tune it.

### Is it free?

Yes. MIT-licensed open source, no accounts, no paywalls.
