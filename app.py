import json
import os
import shutil
import subprocess
from pathlib import Path

import yt_dlp
from flask import Flask, abort, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
CONVERTED_DIR = BASE_DIR / "converted"
UPLOAD_DIR = BASE_DIR / "uploads"

for folder in (DOWNLOAD_DIR, CONVERTED_DIR, UPLOAD_DIR):
    folder.mkdir(exist_ok=True)

app = Flask(__name__, template_folder=str(BASE_DIR))

with open(BASE_DIR / "psp-preset.json", "r", encoding="utf-8") as preset_file:
    PSP_PRESET = json.load(preset_file)


def list_recent_files(folder: Path):
    if not folder.exists():
        return []
    files = sorted(folder.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in files if p.is_file()]


def resolve_download_quality(quality: str):
    quality_map = {
        "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
        "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
        "audio_m4a": "bestaudio[ext=m4a]/bestaudio/best",
    }
    return quality_map.get(quality, quality_map["1080p"])


def download_from_youtube(url: str, quality: str):
    safe_name = url.rsplit("/", 1)[-1] or "video"
    output_template = str(DOWNLOAD_DIR / "%(title)s.%(ext)s")

    ydl_opts = {
        "format": resolve_download_quality(quality),
        "outtmpl": output_template,
        "noplaylist": True,
        "ffmpeg_location": "/usr/bin/ffmpeg",
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "paths": {"home": str(DOWNLOAD_DIR)},
    }

    if quality == "audio_m4a":
        ydl_opts.update(
            {
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "m4a",
                        "preferredquality": "0",
                    }
                ]
            }
        )

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get("title") or safe_name
        suggested_name = title.replace("/", "_")

    if quality == "audio_m4a":
        for candidate in DOWNLOAD_DIR.glob(f"{suggested_name}.*"):
            if candidate.suffix.lower() in {".m4a", ".mp3", ".webm", ".aac"}:
                return candidate.name
        return f"{suggested_name}.m4a"

    for candidate in DOWNLOAD_DIR.glob(f"{suggested_name}.*"):
        if candidate.suffix.lower() in {".mp4", ".webm", ".mkv"}:
            return candidate.name

    return f"{suggested_name}.mp4"


def psp_preset_settings():
    preset = PSP_PRESET.get("PresetList", [{}])[0]
    audio = preset.get("AudioList", [{}])[0]
    return {
        "width": int(preset.get("PictureWidth", 480)),
        "height": int(preset.get("PictureHeight", 272)),
        "fps": int(float(preset.get("VideoFramerate", 30))),
        "video_preset": preset.get("VideoPreset", "medium"),
        "video_profile": preset.get("VideoProfile", "baseline"),
        "video_level": preset.get("VideoLevel", "1.3"),
        "audio_bitrate": int(audio.get("AudioBitrate", 160)),
        "audio_samplerate": 48000,
    }


def convert_to_psp_mp4(input_path: str, output_dir: Path):
    settings = psp_preset_settings()
    input_file = Path(input_path).resolve()
    if not input_file.is_file():
        raise FileNotFoundError(f"Uploaded video was not saved: {input_file}")

    ffmpeg_executable = shutil.which("ffmpeg")
    if not ffmpeg_executable:
        raise FileNotFoundError("FFmpeg was not found in PATH. Install FFmpeg and restart the app.")

    output_file = output_dir / f"{input_file.stem}_psp.mp4"

    ffmpeg_cmd = [
        ffmpeg_executable,
        "-y",
        "-i",
        str(input_file),
        "-vf",
        (
            f"scale={settings['width']}:{settings['height']}:force_original_aspect_ratio=decrease,"
            f"pad={settings['width']}:{settings['height']}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"fps={settings['fps']}"
        ),
        "-c:v",
        "libx264",
        "-preset",
        settings["video_preset"],
        "-profile:v",
        settings["video_profile"],
        "-level",
        settings["video_level"],
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(settings["fps"]),
        "-c:a",
        "aac",
        "-b:a",
        f"{settings['audio_bitrate']}k",
        "-ac",
        "2",
        "-ar",
        str(settings["audio_samplerate"]),
        "-movflags",
        "+faststart",
        str(output_file),
    ]

    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "FFmpeg conversion failed.")

    return output_file.name


@app.route("/")
def index():
    return render_template("dashboard.html", downloads=list_recent_files(DOWNLOAD_DIR), converted=list_recent_files(CONVERTED_DIR))


@app.route("/download", methods=["POST"])
def download_video():
    url = (request.form.get("url") or "").strip()
    quality = request.form.get("quality") or "1080p"

    if not url:
        return render_template(
            "dashboard.html",
            error="Please add a valid video URL before downloading.",
            downloads=list_recent_files(DOWNLOAD_DIR),
            converted=list_recent_files(CONVERTED_DIR),
        )

    try:
        filename = download_from_youtube(url, quality)
        success_message = f"Downloaded successfully: {filename}"
        return render_template(
            "dashboard.html",
            success=success_message,
            downloads=list_recent_files(DOWNLOAD_DIR),
            converted=list_recent_files(CONVERTED_DIR),
        )
    except Exception as exc:  # pragma: no cover - runtime failure path
        return render_template(
            "dashboard.html",
            error=f"Download failed: {exc}",
            downloads=list_recent_files(DOWNLOAD_DIR),
            converted=list_recent_files(CONVERTED_DIR),
        )


@app.route("/convert", methods=["POST"])
def convert_video():
    uploaded_file = request.files.get("video_file")
    if not uploaded_file or not uploaded_file.filename:
        return render_template(
            "dashboard.html",
            error="Please select a video file to convert.",
            downloads=list_recent_files(DOWNLOAD_DIR),
            converted=list_recent_files(CONVERTED_DIR),
        )

    safe_name = secure_filename(uploaded_file.filename)
    if not safe_name:
        return render_template(
            "dashboard.html",
            error="The selected video has an invalid filename.",
            downloads=list_recent_files(DOWNLOAD_DIR),
            converted=list_recent_files(CONVERTED_DIR),
        )

    source_path = UPLOAD_DIR / safe_name
    uploaded_file.save(source_path)

    try:
        output_name = convert_to_psp_mp4(str(source_path), CONVERTED_DIR)
        return render_template(
            "dashboard.html",
            success=f"Converted to PSP-ready MP4: {output_name}",
            downloads=list_recent_files(DOWNLOAD_DIR),
            converted=list_recent_files(CONVERTED_DIR),
        )
    except Exception as exc:
        return render_template(
            "dashboard.html",
            error=f"Conversion failed: {exc}",
            downloads=list_recent_files(DOWNLOAD_DIR),
            converted=list_recent_files(CONVERTED_DIR),
        )


@app.route("/files/<folder>/<filename>")
def serve_file(folder: str, filename: str):
    folder_map = {"downloads": DOWNLOAD_DIR, "converted": CONVERTED_DIR}
    target_folder = folder_map.get(folder)
    if target_folder is None:
        abort(404)
    return send_from_directory(target_folder, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
