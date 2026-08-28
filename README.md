# NovaVideo Downloader and PSP Converter

A small Flask web app for:

- downloading videos from YouTube using `yt-dlp`
- choosing 720p, 1080p, or audio-only M4A output
- converting local `.webm` and `.mkv` files to a PSP-compatible MP4 using the project preset file

## Features

- Download YouTube videos directly from the dashboard
- Save downloaded files in the `downloads` folder
- Convert uploaded WebM/MKV files into PSP-style MP4 output using the preset from `psp-preset.json`
- Browse recent downloads and converted files from the UI

## Requirements

Before running the app, install:

- Python 3.10+
- FFmpeg
- Git

## Clone the project

```bash
git clone https://github.com/samyboi16/VidDownPSPConvert.git
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
pip install Flask yt-dlp
```

## Make sure FFmpeg is available

Verify it works:

```bash
ffmpeg -version
```

If FFmpeg is not installed, install it using your OS package manager.

## Run the app

```bash
python app.py
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
