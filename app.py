import os
import sys
import subprocess
from pathlib import Path
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    send_from_directory,
    flash,
)

# -------------------------------------------------------
# CONFIG
# -------------------------------------------------------
PCC_DIR = Path(r"C:\Users\Thariq\Documents\ITS\PROJECT\PCC-v2").resolve()
UPLOAD_VIDEO_NAME = "video1.mp4"
UPLOAD_TEXT_NAME = "input.txt"

# this is the python that runs THIS app (your venv python)
VENV_PYTHON = sys.executable
# venv Scripts dir (Windows)
VENV_SCRIPTS = Path(VENV_PYTHON).parent  # ...\.venv\Scripts

app = Flask(__name__)
app.secret_key = "super-secret-thariq"  # ganti kalau mau

# -------------------------------------------------------
# HELPERS
# -------------------------------------------------------
def run_cmd(cmd, cwd: Path):
    """
    Jalankan satu perintah dan kembalikan (ok, text_log).
    Pastikan venv Scripts ada di depan PATH.
    """
    env = os.environ.copy()
    # prepend venv Scripts so `stable-ts` from venv is used
    env["PATH"] = str(VENV_SCRIPTS) + os.pathsep + env.get("PATH", "")

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            shell=False,
            env=env,
        )
        out = proc.stdout or ""
        err = proc.stderr or ""
        full = f"$ {' '.join(cmd)}\n{out}\n{err}\n"
        return proc.returncode == 0, full
    except Exception as e:
        return False, f"$ {' '.join(cmd)}\n[ERROR] {e}\n"


def final_video_name_from_input_txt() -> str | None:
    input_path = PCC_DIR / UPLOAD_TEXT_NAME
    if not input_path.exists():
        return None
    try:
        first_line = input_path.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip()
    except Exception:
        return None
    if not first_line:
        return None
    safe = "".join(ch for ch in first_line if ch not in '<>:"/\\|?*').rstrip(".").strip()
    if not safe:
        return None
    return f"{safe}.mp4"


# -------------------------------------------------------
# ROUTES
# -------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    logs = ""
    produced_files = []

    if request.method == "POST":
        video_file = request.files.get("video_file")
        text_file = request.files.get("text_file")

        PCC_DIR.mkdir(parents=True, exist_ok=True)

        if video_file and video_file.filename:
            video_path = PCC_DIR / UPLOAD_VIDEO_NAME
            video_file.save(str(video_path))
        else:
            logs += "[WARN] No video uploaded, using existing video1.mp4 if present.\n"

        if text_file and text_file.filename:
            text_path = PCC_DIR / UPLOAD_TEXT_NAME
            text_file.save(str(text_path))
        else:
            logs += "[WARN] No input.txt uploaded, using existing input.txt if present.\n"

        # 2.1 analyze_cat_video.py  (use venv python)
        ok, log = run_cmd(
            [
                VENV_PYTHON,
                "analyze_cat_video.py",
                "--video",
                UPLOAD_VIDEO_NAME,
                "--out",
                "output.txt",
                "--fps",
                "1.0",
            ],
            PCC_DIR,
        )
        logs += log
        if not ok:
            flash("analyze_cat_video.py gagal. Lihat log di bawah.")
            return render_template("index.html", logs=logs, produced_files=produced_files)

        # 2.2 kokoro_heart.py (pakai PCC_DIR biar 1 folder)
        ok, log = run_cmd(
            [
                VENV_PYTHON,
                str(PCC_DIR / "kokoro_heart.py"),
            ],
            PCC_DIR,
        )
        logs += log
        if not ok:
            flash("kokoro_heart.py gagal.")
            return render_template("index.html", logs=logs, produced_files=produced_files)

        # 2.3 stable-ts ... (will be found in venv Scripts because we prepended PATH)
        ok, log = run_cmd(
            [
                "stable-ts",
                "heart_all.wav",
                "--output",
                "heart_all.srt",
                "--output_format",
                "srt",
                "--device",
                "cuda",
                "--language",
                "en",
                "--word_timestamps",
                "True",
                "--max_chars",
                "42",
                "--max_words",
                "3",
            ],
            PCC_DIR,
        )
        logs += log
        if not ok:
            flash("stable-ts gagal.")
            return render_template("index.html", logs=logs, produced_files=produced_files)

        # 2.4 powershell replace warna
        # ps_cmd = (
        #     r'(Get-Content .\heart_all.srt) -replace ''#00ff00'',''#ff00ffff'' | '
        #     r'Set-Content .\heart_all.srt -Encoding utf8'
        # )
        # ok, log = run_cmd(
        #     ["powershell", "-NoProfile", "-Command", ps_cmd],
        #     PCC_DIR,
        # )
        # logs += log
        # if not ok:
        #     flash("PowerShell replace warna gagal.")
        #     return render_template("index.html", logs=logs, produced_files=produced_files)

        # 2.5 rearrange_9x16.py (use venv python)
        ok, log = run_cmd(
            [
                VENV_PYTHON,
                "rearrange_9x16.py",
                "--input",
                "video1.mp4",
                "--output",
                "output_9x16_letterbox.mp4",
                "--last",
                "3",
                "--letterbox",
            ],
            PCC_DIR,
        )
        logs += log
        if not ok:
            flash("rearrange_9x16.py gagal.")
            return render_template("index.html", logs=logs, produced_files=produced_files)

        # 2.6 burn_hardsub_fit_ass.py (use venv python)
        ok, log = run_cmd(
            [
                VENV_PYTHON,
                "burn_hardsub_fit_ass.py",
                "--keep_font_color",
                "--ass_color_order",
                "rgb",
                "--margin_v_ratio",
                "0.24",
                "--base_scale",
                "0.056",
            ],
            PCC_DIR,
        )
        logs += log
        if not ok:
            flash("burn_hardsub_fit_ass.py gagal.")
            return render_template("index.html", logs=logs, produced_files=produced_files)

        # kumpulkan file hasil
        for fname in [
            "output.txt",
            "heart_all.wav",
            "heart_all.srt",
            "output_9x16_letterbox.mp4",
        ]:
            if (PCC_DIR / fname).exists():
                produced_files.append(fname)

        maybe_final = final_video_name_from_input_txt()
        if maybe_final and (PCC_DIR / maybe_final).exists():
            produced_files.append(maybe_final)

        flash("Pipeline selesai ✅")

    # GET
    existing = []
    for fname in [
        "output.txt",
        "heart_all.wav",
        "heart_all.srt",
        "output_9x16_letterbox.mp4",
    ]:
        if (PCC_DIR / fname).exists():
            existing.append(fname)
    maybe_final = final_video_name_from_input_txt()
    if maybe_final and (PCC_DIR / maybe_final).exists():
        existing.append(maybe_final)

    if not produced_files:
        produced_files = existing

    return render_template("index.html", logs=logs, produced_files=produced_files)


@app.route("/files/<path:filename>")
def files(filename):
    return send_from_directory(str(PCC_DIR), filename, as_attachment=False)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
