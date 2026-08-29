import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yt_dlp
from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
CONVERTED_DIR = BASE_DIR / "converted"
UPLOAD_DIR = BASE_DIR / "uploads"

for folder in (DOWNLOAD_DIR, CONVERTED_DIR, UPLOAD_DIR):
    folder.mkdir(exist_ok=True)

app = Flask(__name__, template_folder=str(BASE_DIR))
job_executor = ThreadPoolExecutor(max_workers=2)
jobs = {}
jobs_lock = threading.Lock()

with open(BASE_DIR / "psp-preset.json", "r", encoding="utf-8") as preset_file:
    PSP_PRESET = json.load(preset_file)


def update_job(job_id: str, **changes):
    with jobs_lock:
        jobs[job_id].update(changes)


def create_job(job_type: str):
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {
            "type": job_type,
            "status": "queued",
            "percent": 0,
            "message": "Waiting to start...",
        }
    return job_id


def run_job(job_id: str, worker):
    update_job(job_id, status="running", message="Starting...")
    try:
        result = worker()
        update_job(job_id, status="completed", percent=100, message="Finished.", result=result)
    except Exception as exc:  # pragma: no cover - runtime failure path
        update_job(job_id, status="failed", message=str(exc), error=str(exc))


def resolve_ffmpeg():
    configured_path = os.environ.get("FFMPEG_PATH")
    if configured_path:
        configured_executable = Path(configured_path).expanduser()
        if configured_executable.is_file():
            return str(configured_executable)
        raise FileNotFoundError(f"FFMPEG_PATH does not point to a file: {configured_executable}")

    system_executable = shutil.which("ffmpeg")
    if system_executable:
        return system_executable

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise FileNotFoundError(
            "FFmpeg was not found. Install it, set FFMPEG_PATH, or install imageio-ffmpeg."
        ) from exc


def get_video_duration(ffmpeg_executable: str, input_file: Path):
    probe = subprocess.run(
        [ffmpeg_executable, "-hide_banner", "-i", str(input_file)],
        capture_output=True,
        text=True,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", probe.stderr)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


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


def download_from_youtube(url: str, quality: str, progress_callback=None):
    safe_name = url.rsplit("/", 1)[-1] or "video"
    output_template = str(DOWNLOAD_DIR / "%(title)s.%(ext)s")

    def download_progress(progress):
        if not progress_callback:
            return
        if progress.get("status") == "downloading":
            downloaded = progress.get("downloaded_bytes", 0)
            total = progress.get("total_bytes") or progress.get("total_bytes_estimate")
            percent = round(downloaded * 100 / total, 1) if total else 0
            eta = progress.get("eta")
            message = f"Downloading... {percent:.1f}%"
            if eta is not None:
                message += f" (about {eta}s remaining)"
            progress_callback(percent, message)
        elif progress.get("status") == "finished":
            progress_callback(100, "Download complete. Processing file...")

    ydl_opts = {
        "format": resolve_download_quality(quality),
        "outtmpl": output_template,
        "noplaylist": True,
        "ffmpeg_location": resolve_ffmpeg(),
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "paths": {"home": str(DOWNLOAD_DIR)},
        "progress_hooks": [download_progress],
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


def convert_to_psp_mp4(input_path: str, output_dir: Path, progress_callback=None, output_stem=None):
    settings = psp_preset_settings()
    input_file = Path(input_path).resolve()
    if not input_file.is_file():
        raise FileNotFoundError(f"Uploaded video was not saved: {input_file}")

    ffmpeg_executable = resolve_ffmpeg()

    output_name_stem = output_stem or input_file.stem
    output_file = output_dir / f"{output_name_stem}_to_psp.mp4"

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

    try:
        duration = get_video_duration(ffmpeg_executable, input_file)
    except OSError:
        duration = None

    ffmpeg_cmd[1:1] = ["-progress", "pipe:1", "-nostats"]
    process = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    stderr_output = []
    for line in process.stdout:
        stderr_output.append(line)
        if line.startswith("out_time_ms=") and progress_callback and duration:
            elapsed = int(line.split("=", 1)[1]) / 1_000_000
            progress_callback(min(round(elapsed * 100 / duration, 1), 99.9), "Converting video...")

    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError("\n".join(stderr_output).strip() or "FFmpeg conversion failed.")

    return output_file.name


@app.route("/")
def index():
    return render_template("dashboard.html", downloads=list_recent_files(DOWNLOAD_DIR), converted=list_recent_files(CONVERTED_DIR))


@app.route("/download", methods=["POST"])
def download_video():
    url = (request.form.get("url") or "").strip()
    quality = request.form.get("quality") or "1080p"

    if not url:
        return jsonify(error="Please add a valid video URL before downloading."), 400

    job_id = create_job("download")
    job_executor.submit(
        run_job,
        job_id,
        lambda: download_from_youtube(
            url,
            quality,
            lambda percent, message: update_job(job_id, percent=percent, message=message),
        ),
    )
    return jsonify(job_id=job_id)


@app.route("/convert", methods=["POST"])
def convert_video():
    uploaded_file = request.files.get("video_file")
    if not uploaded_file or not uploaded_file.filename:
        return jsonify(error="Please select a video file to convert."), 400

    safe_name = secure_filename(uploaded_file.filename)
    if not safe_name:
        return jsonify(error="The selected video has an invalid filename."), 400

    source_path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{safe_name}"
    uploaded_file.save(source_path)

    job_id = create_job("convert")
    job_executor.submit(
        run_job,
        job_id,
        lambda: convert_to_psp_mp4(
            str(source_path),
            CONVERTED_DIR,
            lambda percent, message: update_job(job_id, percent=percent, message=message),
            Path(safe_name).stem,
        ),
    )
    return jsonify(job_id=job_id)


@app.route("/progress/<job_id>")
def job_progress(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            abort(404)
        return jsonify(job)


@app.route("/files/<folder>/<filename>")
def serve_file(folder: str, filename: str):
    folder_map = {"downloads": DOWNLOAD_DIR, "converted": CONVERTED_DIR}
    target_folder = folder_map.get(folder)
    if target_folder is None:
        abort(404)
    return send_from_directory(target_folder, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
