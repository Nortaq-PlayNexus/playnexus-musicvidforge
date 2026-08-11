# Installation

MusicVidForge runs on **Windows** (macOS/Linux should work but are not yet
officially supported).

## 1. Install Python

Download **Python 3.10 or newer** from [python.org](https://www.python.org/downloads/).
During install, tick **"Add Python to PATH"**.

Verify:

```powershell
python --version
```

## 2. Install ffmpeg

MusicVidForge uses `ffmpeg` to encode the final video. The simplest way on
Windows is the gyan.dev build:

1. Download from https://www.gyan.dev/ffmpeg/builds/ (**ffmpeg-release-full**).
2. Unzip to a permanent location, e.g. `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to your **PATH** (System Properties → Environment Variables).

Verify:

```powershell
ffmpeg -version
```

## 3. Get the code

```bash
git clone https://github.com/Nortaq-PlayNexus/playnexus-musicvidforge.git
cd playnexus-musicvidforge
```

Or download and extract the ZIP from the GitHub page.

## 4. Create a virtual environment and install dependencies

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 5. Run

```powershell
python app.py
```

A window titled **MusicVidForge** should open.

## Running without a console

To launch without a console window:

```powershell
.venv\Scripts\pythonw.exe app.py
```

## First render

Pick any song, choose a template, set a low resolution like **720p** to start,
and hit **RENDER MUSIC VIDEO**. The finished file opens automatically.
