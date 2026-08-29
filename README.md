# NovaVideo Downloader and PSP Converter

A small Flask web app for:

- downloading videos from YouTube using `yt-dlp`
- choosing 720p, 1080p, or audio-only M4A output
- converting local video files to a PSP-compatible MP4 using the project preset file

## Features

- Download YouTube videos directly from the dashboard
- Save downloaded files in the `downloads` folder
- Convert uploaded video files into PSP-style MP4 output using the preset from `psp-preset.json`
- Browse recent downloads and converted files from the UI

## Requirements

Before running the app, install:

- Python 3.10+
- FFmpeg, or the bundled `imageio-ffmpeg` fallback installed from `requirements.txt`
- Git

## Clone the project

```bash
git clone <your-repository-url>
cd "Vid downlaoder and ffmpeging"
```

## Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## FFmpeg setup

The app looks for FFmpeg in this order:

1. The executable specified by the `FFMPEG_PATH` environment variable
2. An `ffmpeg` executable on your system `PATH`
3. The platform-specific binary supplied by `imageio-ffmpeg`

The third option allows the app to work without a separate FFmpeg installation on Windows, macOS, and Linux. For production or redistribution, installing FFmpeg system-wide or shipping a legally licensed binary yourself is usually more predictable.

To use a custom executable:

```bash
export FFMPEG_PATH=/path/to/ffmpeg
```

PowerShell:

```powershell
$env:FFMPEG_PATH = "C:\\path\\to\\ffmpeg.exe"
```

To verify a system installation:

Verify it works:

```bash
ffmpeg -version
```

If FFmpeg is not installed, install it using your OS package manager.

## Run the app

```bash
python run.py
```

Then open:

```text
http://127.0.0.1:5000
```

## Project structure

```text
.
├── app.py
├── dashboard.html
├── psp-preset.json
├── downloads/
├── converted/
├── uploads/
├── README.md
└── .venv/
```

## Notes

- The app stores downloaded videos in the `downloads` directory.
- Converted PSP-ready MP4 files are saved to `converted/`.
- Uploaded local files are temporarily stored in `uploads/` before conversion.
- The conversion preset follows the values defined in `psp-preset.json`.

## Troubleshooting

### `yt-dlp` cannot find a format

This usually means the selected video is unavailable, restricted, or does not expose the requested resolution. Try another URL or switch to a different quality option.

### `ffmpeg` is not found

Install FFmpeg and confirm it is in your PATH.

```bash
which ffmpeg
```

or on Windows:

```powershell
where ffmpeg
```
