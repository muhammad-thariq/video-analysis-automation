import os
import re
import sys
import shutil
import subprocess
import threading
from pathlib import Path
from flask import Flask, render_template, request, send_from_directory, jsonify
from flask_socketio import SocketIO, emit

# -------------------------------------------------------
# CONFIG
# -------------------------------------------------------
SCRIPTS_DIR = Path(__file__).parent.resolve()   # server/
PCC_DIR = SCRIPTS_DIR.parent                    # repo root (holds v_raw, v_fin, v_uploaded)
TEMP_DIR = PCC_DIR / "temp"                     # runtime working dir

UPLOAD_VIDEO_NAME = "video1.mp4"
UPLOAD_TEXT_NAME = "input.txt"

# this is the python that runs THIS app (your venv python)
VENV_PYTHON = sys.executable
# venv Scripts dir (Windows)
VENV_SCRIPTS = Path(VENV_PYTHON).parent  # ...\.venv\Scripts

app = Flask(
    __name__,
    template_folder=str(PCC_DIR / "interface" / "templates"),
    static_folder=str(PCC_DIR / "interface" / "static"),
)
app.secret_key = "super-secret-thariq"
socketio = SocketIO(app, cors_allowed_origins="*")

# -------------------------------------------------------
# HUMAN-IN-THE-LOOP GATES
# -------------------------------------------------------
# Gate for analysis review (after step 1, before script generation)
analysis_review_gate = threading.Event()
analysis_review_action = {"action": "approve", "text": ""}

# Gate for script review (after step 2)
script_review_gate = threading.Event()
script_review_action = {"action": "approve", "text": ""}

# -------------------------------------------------------
# PIPELINE CANCELLATION
# -------------------------------------------------------
pipeline_cancel = threading.Event()      # Set to request cancellation
current_subprocess = None                # Track the running subprocess
current_subprocess_lock = threading.Lock()

# -------------------------------------------------------
# PIPELINE STEPS CONFIGURATION
# -------------------------------------------------------
PIPELINE_STEPS = [
    {
        "id": 1,
        "name": "Video Analysis",
        "description": "Analyzing video content with AI",
        "progress_start": 0,
        "progress_end": 10,
    },
    {
        "id": 2,
        "name": "Analysis Approval",
        "description": "Review and approve analysis",
        "progress_start": 10,
        "progress_end": 12,
    },
    {
        "id": 3,
        "name": "AI Script Generation",
        "description": "Generating script with Ollama LLM",
        "progress_start": 12,
        "progress_end": 25,
    },
    {
        "id": 4,
        "name": "TTS Generation",
        "description": "Generating text-to-speech audio",
        "progress_start": 25,
        "progress_end": 35,
    },
    {
        "id": 5,
        "name": "Subtitle Generation",
        "description": "Creating subtitles with Whisper",
        "progress_start": 35,
        "progress_end": 55,
    },
    {
        "id": 6,
        "name": "Color Replacement",
        "description": "Adjusting subtitle colors",
        "progress_start": 55,
        "progress_end": 67,
    },
    {
        "id": 7,
        "name": "Video Reformatting",
        "description": "Converting to 9:16 format",
        "progress_start": 67,
        "progress_end": 80,
    },
    {
        "id": 8,
        "name": "Subtitle Burning",
        "description": "Burning subtitles into video",
        "progress_start": 80,
        "progress_end": 100,
    },
]

# -------------------------------------------------------
# HELPERS
# -------------------------------------------------------
def emit_progress(percentage, message=""):
    """Emit progress update to connected clients."""
    socketio.emit("progress_update", {"percentage": percentage, "message": message})


def emit_step_status(step_id, status, message=""):
    """Emit step status update. Status: queued, running, completed, failed."""
    socketio.emit(
        "step_update", {"step_id": step_id, "status": status, "message": message}
    )


def emit_log(message):
    """Emit log message to connected clients."""
    socketio.emit("log_message", {"message": message})


def check_cancelled():
    """Return True if the pipeline has been cancelled."""
    return pipeline_cancel.is_set()


def run_cmd(cmd, cwd: Path, step_info):
    """
    Run a command and emit progress/logs in real-time.
    Returns (ok, text_log).

    NOTE: All commands run in the venv environment:
    - Python scripts use VENV_PYTHON directly
    - CLI tools like 'stable-ts' use venv version via prepended PATH (VENV_SCRIPTS)
    """
    global current_subprocess

    if check_cancelled():
        return False, "[CANCELLED]"

    env = os.environ.copy()
    # CRITICAL: Prepend venv Scripts so CLI tools (stable-ts, etc.) use venv versions
    env["PATH"] = str(VENV_SCRIPTS) + os.pathsep + env.get("PATH", "")

    step_id = step_info["id"]
    emit_step_status(step_id, "running", step_info["description"])
    emit_log(f"▶ Running: {' '.join(cmd)}")

    try:
        # Use communicate() to avoid blocking on full buffers
        # This is critical for commands that produce lots of output (like ffmpeg)
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Merge stderr into stdout
            text=True,
            encoding='utf-8',  # Explicit UTF-8 to avoid cp1252 errors on Windows
            errors='replace',  # Replace undecodable bytes instead of crashing
            shell=True,  # Use shell for better Windows compatibility
            env=env,
        )

        # Track subprocess so it can be killed on cancel
        with current_subprocess_lock:
            current_subprocess = proc

        # Read output in real-time to prevent blocking
        output_lines = []
        while True:
            # Check cancellation each iteration
            if check_cancelled():
                proc.kill()
                proc.wait()
                emit_step_status(step_id, "failed", f"{step_info['name']} cancelled")
                emit_log(f"🛑 {step_info['name']} cancelled")
                return False, "[CANCELLED]"

            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                line = line.rstrip()
                output_lines.append(line)
                # Only emit non-empty lines to reduce spam
                if line.strip():
                    emit_log(line)

        # Clear subprocess tracker
        with current_subprocess_lock:
            current_subprocess = None

        # Get return code
        returncode = proc.wait()
        full_output = "\n".join(output_lines)

        if returncode == 0:
            emit_step_status(step_id, "completed", f"{step_info['name']} completed ✓")
            emit_progress(step_info["progress_end"])
            emit_log(f"✓ {step_info['name']} completed successfully")
            return True, full_output
        else:
            emit_step_status(step_id, "failed", f"{step_info['name']} failed ✗")
            emit_log(f"✗ {step_info['name']} failed with return code {returncode}")
            return False, full_output

    except Exception as e:
        with current_subprocess_lock:
            current_subprocess = None
        emit_step_status(step_id, "failed", f"{step_info['name']} error: {str(e)}")
        emit_log(f"✗ ERROR: {str(e)}")
        return False, f"$ {' '.join(cmd)}\n[ERROR] {e}\n"


def final_video_name_from_input_txt() -> str | None:
    """Get the final video filename based on generated_title.txt or input.txt first line."""
    import re
    generated_path = TEMP_DIR / "generated_title.txt"
    if generated_path.exists():
        try:
            raw_title = generated_path.read_text(encoding="utf-8", errors="ignore").strip()
            raw_title = " ".join(raw_title.split())
            safe = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", raw_title).strip().rstrip(".")
            if safe:
                return f"{safe}.mp4"
        except Exception:
            pass

    input_path = TEMP_DIR / UPLOAD_TEXT_NAME
    if not input_path.exists():
        return None
    try:
        first_line = input_path.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip()
    except Exception:
        return None
    if not first_line:
        return None

    words = first_line.split()
    selected_words = []
    for i, word in enumerate(words):
        if i >= 15: break
        selected_words.append(word)
        if '.' in word and i >= 4: break
    raw_title = " ".join(selected_words)

    safe = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", raw_title).strip().rstrip(".")
    if not safe:
        return None
    return f"{safe}.mp4"


def process_pipeline():
    """Main pipeline processing function (runs in background thread)."""
    try:
        # Clear any previous cancellation
        pipeline_cancel.clear()

        emit_log("=" * 60)
        emit_log("🚀 Starting Video Processing Pipeline")
        emit_log(f"🐍 Using Python: {VENV_PYTHON}")
        emit_log(f"📁 Scripts PATH: {VENV_SCRIPTS}")
        emit_log(f"📂 Scripts DIR: {SCRIPTS_DIR}")
        emit_log(f"📂 Working DIR: {TEMP_DIR}")
        emit_log("=" * 60)

        # Initialize all steps as queued
        for step in PIPELINE_STEPS:
            emit_step_status(step["id"], "queued", "Waiting...")

        skip_analysis = (TEMP_DIR / "skip_analysis.txt").exists()

        if skip_analysis:
            emit_log("⏭️ Skipping video analysis and analysis approval...")
            step1 = PIPELINE_STEPS[0]
            emit_step_status(step1["id"], "completed", f"{step1['name']} skipped")
            emit_progress(step1["progress_end"])

            step2 = PIPELINE_STEPS[1]
            emit_step_status(step2["id"], "completed", f"{step2['name']} skipped")
            emit_progress(step2["progress_end"])

            output_txt = TEMP_DIR / "output.txt"
            if output_txt.exists():
                output_txt.unlink()
                emit_log("🗑️ Removed existing output.txt (Analysis Skipped)")
        else:
            # Step 1: analyze_cat_video.py
            step = PIPELINE_STEPS[0]
            # Delete existing output.txt to avoid any prompts
            output_txt = TEMP_DIR / "output.txt"
            if output_txt.exists():
                output_txt.unlink()
                emit_log("🗑️ Removed existing output.txt")

            ok, log = run_cmd(
                [
                    VENV_PYTHON,
                    str(SCRIPTS_DIR / "analyze_cat_video.py"),
                    "--video",
                    UPLOAD_VIDEO_NAME,
                    "--out",
                    "output.txt",
                    "--fps",
                    "1.0",
                ],
                TEMP_DIR,
                step,
            )
            if not ok:
                emit_log("❌ Pipeline failed at step 1")
                socketio.emit("processing_error", {"message": "Video analysis failed"})
                return

            # ── HUMAN-IN-THE-LOOP: pause for analysis review ──
            step = PIPELINE_STEPS[1]  # Analysis Approval step
            emit_step_status(step["id"], "running", step["description"])
            output_txt = TEMP_DIR / "output.txt"
            analysis_text = output_txt.read_text(encoding="utf-8", errors="ignore") if output_txt.exists() else ""

            emit_log("✏️ Waiting for analysis review...")
            socketio.emit("analysis_review", {"text": analysis_text})

            # Block until user approves
            analysis_review_gate.clear()
            analysis_review_gate.wait()

            approved_text = analysis_review_action["text"]
            if approved_text.strip():
                output_txt.write_text(approved_text, encoding="utf-8")
                emit_log("✅ Analysis approved (with edits) — continuing pipeline")
            else:
                emit_log("✅ Analysis approved — continuing pipeline")

            emit_step_status(step["id"], "completed", f"{step['name']} completed ✓")
            emit_progress(step["progress_end"])

        # Step 3: ollama_generate_script.py
        step = PIPELINE_STEPS[2]
        ollama_cmd = [VENV_PYTHON, str(SCRIPTS_DIR / "ollama_generate_script.py")]

        # Use contextual prompt if analysis was skipped
        if skip_analysis:
            ollama_cmd += ["--sys-prompt", str(SCRIPTS_DIR / "system_prompt_context.txt")]

        topic_file = TEMP_DIR / "video_topic.txt"
        if topic_file.exists():
            ollama_cmd += ["--topic", str(topic_file)]
        target_chars_file = TEMP_DIR / "target_chars.txt"
        if target_chars_file.exists():
            tc = target_chars_file.read_text(encoding="utf-8").strip()
            if tc and int(tc) > 0:
                ollama_cmd += ["--target-chars", tc]
        ok, log = run_cmd(
            ollama_cmd,
            TEMP_DIR,
            step,
        )
        if not ok:
            emit_log("❌ Pipeline failed at step 2 (Ollama script generation)")
            socketio.emit("processing_error", {"message": "AI script generation failed"})
            return

        # ── HUMAN-IN-THE-LOOP: pause for script review ──
        audio_generated_during_review = False
        while True:
            input_txt_path = TEMP_DIR / UPLOAD_TEXT_NAME
            script_text = input_txt_path.read_text(encoding="utf-8", errors="ignore") if input_txt_path.exists() else ""

            emit_log("✏️ Waiting for script review...")
            socketio.emit("script_review", {"script": script_text})

            # Block until user responds
            script_review_gate.clear()
            script_review_gate.wait()

            action = script_review_action["action"]
            new_text = script_review_action["text"]

            if action == "generate_audio":
                # Save the current script text
                if new_text.strip():
                    input_txt_path.write_text(new_text, encoding="utf-8")
                emit_log("🔉 Generating TTS audio...")

                # Delete existing audio
                heart_wav = TEMP_DIR / "heart_all.wav"
                if heart_wav.exists():
                    heart_wav.unlink()

                # Run kokoro_heart.py for TTS
                tts_step = PIPELINE_STEPS[2]  # TTS step info for logging
                ok, log = run_cmd(
                    [VENV_PYTHON, str(SCRIPTS_DIR / "kokoro_heart.py")],
                    TEMP_DIR,
                    tts_step,
                )
                if not ok:
                    emit_log("❌ Audio generation failed")
                    socketio.emit("processing_error", {"message": "Audio generation failed"})
                    return

                audio_generated_during_review = True
                # Emit audio ready event with file URL
                socketio.emit("audio_ready", {"url": "/files/heart_all.wav"})
                emit_log("🔊 Audio ready for preview")

                # Wait for user's next action (approve or modify script)
                script_review_gate.clear()
                script_review_gate.wait()

                # Process the next action from the second wait
                action = script_review_action["action"]
                new_text = script_review_action["text"]

                if action == "approve":
                    if new_text.strip():
                        input_txt_path.write_text(new_text, encoding="utf-8")
                    emit_log("✅ Script approved — continuing pipeline")
                    break
                # If they chose anything else, fall through to the handlers below

            if action == "extend":
                # Delete audio if it exists (script changed)
                heart_wav = TEMP_DIR / "heart_all.wav"
                if heart_wav.exists():
                    heart_wav.unlink()
                    emit_log("🗑️ Audio deleted (script changed)")
                audio_generated_during_review = False

                # Save the current script text so the extend prompt can read it
                input_txt_path.write_text(new_text, encoding="utf-8")
                emit_log("➕ Extending script by ~50% (re-running Ollama)...")
                extend_cmd = [VENV_PYTHON, str(SCRIPTS_DIR / "ollama_generate_script.py"), "--extend"]

                if skip_analysis:
                    extend_cmd += ["--sys-prompt", str(SCRIPTS_DIR / "system_prompt_context.txt")]

                if topic_file.exists():
                    extend_cmd += ["--topic", str(topic_file)]
                target_chars = script_review_action.get("target_chars", 0)
                if target_chars and int(target_chars) > 0:
                    extend_cmd += ["--target-chars", str(target_chars)]
                ok, log = run_cmd(
                    extend_cmd,
                    TEMP_DIR,
                    step,
                )
                if not ok:
                    emit_log("❌ Script extension failed")
                    socketio.emit("processing_error", {"message": "Script extension failed"})
                    return
                # Loop back to show the extended script for review
                continue

            if action == "reduce":
                # Delete audio if it exists (script changed)
                heart_wav = TEMP_DIR / "heart_all.wav"
                if heart_wav.exists():
                    heart_wav.unlink()
                    emit_log("🗑️ Audio deleted (script changed)")
                audio_generated_during_review = False

                # Save the current script text so the reduce prompt can read it
                input_txt_path.write_text(new_text, encoding="utf-8")
                emit_log("➖ Reducing script by ~50% (re-running Ollama)...")
                reduce_cmd = [VENV_PYTHON, str(SCRIPTS_DIR / "ollama_generate_script.py"), "--reduce"]

                if skip_analysis:
                    reduce_cmd += ["--sys-prompt", str(SCRIPTS_DIR / "system_prompt_context.txt")]

                if topic_file.exists():
                    reduce_cmd += ["--topic", str(topic_file)]
                target_chars = script_review_action.get("target_chars", 0)
                if target_chars and int(target_chars) > 0:
                    reduce_cmd += ["--target-chars", str(target_chars)]
                ok, log = run_cmd(
                    reduce_cmd,
                    TEMP_DIR,
                    step,
                )
                if not ok:
                    emit_log("❌ Script reduction failed")
                    socketio.emit("processing_error", {"message": "Script reduction failed"})
                    return
                # Loop back to show the reduced script for review
                continue

            if action == "regenerate":
                # Delete audio if it exists (script changed)
                heart_wav = TEMP_DIR / "heart_all.wav"
                if heart_wav.exists():
                    heart_wav.unlink()
                    emit_log("🗑️ Audio deleted (script changed)")
                audio_generated_during_review = False

                emit_log("🔄 Regenerating script (re-running Ollama)...")
                regen_cmd = [VENV_PYTHON, str(SCRIPTS_DIR / "ollama_generate_script.py")]

                if skip_analysis:
                    regen_cmd += ["--sys-prompt", str(SCRIPTS_DIR / "system_prompt_context.txt")]

                if topic_file.exists():
                    regen_cmd += ["--topic", str(topic_file)]
                target_chars = script_review_action.get("target_chars", 0)
                if target_chars and int(target_chars) > 0:
                    regen_cmd += ["--target-chars", str(target_chars)]
                ok, log = run_cmd(
                    regen_cmd,
                    TEMP_DIR,
                    step,
                )
                if not ok:
                    emit_log("❌ Regeneration failed")
                    socketio.emit("processing_error", {"message": "Script regeneration failed"})
                    return
                # Loop back to show the new script for review
                continue

            if action == "edit":
                input_txt_path.write_text(new_text, encoding="utf-8")
                emit_log("✅ Script updated with your edits")

            # action == "approve" or "edit" -> continue pipeline
            # Save any edits from approve (since Save button was removed)
            if action == "approve" and new_text.strip():
                input_txt_path.write_text(new_text, encoding="utf-8")
            emit_log("✅ Script approved — continuing pipeline")
            break

        # ── TITLE GENERATION (runs after any approve path exits the loop) ──
        title_txt_path = TEMP_DIR / "generated_title.txt"
        if title_txt_path.exists():
            title_txt_path.unlink()
        emit_log("🧠 Generating title with AI...")
        try:
            subprocess.run(
                [VENV_PYTHON, str(SCRIPTS_DIR / "ollama_generate_title.py")],
                cwd=str(TEMP_DIR), check=True, capture_output=True, text=True
            )
            if title_txt_path.exists():
                generated_title = title_txt_path.read_text(encoding="utf-8").strip()
                socketio.emit("title_generated", {"title": generated_title})
                emit_log(f"🏷️ Generated Title: {generated_title}")
        except Exception as e:
            emit_log(f"⚠ Title generation failed: {e}")

        # Step 4: kokoro_heart.py (skip if audio was already generated during review)
        step = PIPELINE_STEPS[3]
        if audio_generated_during_review:
            emit_log("⏭️ Skipping TTS — audio was already generated during review")
            emit_step_status(step["id"], "completed", f"{step['name']} completed ✓ (pre-generated)")
            emit_progress(step["progress_end"])
        else:
            # Delete existing heart_all.wav to avoid any prompts
            heart_wav = TEMP_DIR / "heart_all.wav"
            if heart_wav.exists():
                heart_wav.unlink()
                emit_log("🗑️ Removed existing heart_all.wav")

            ok, log = run_cmd(
                [VENV_PYTHON, str(SCRIPTS_DIR / "kokoro_heart.py")],
                TEMP_DIR,
                step,
            )
            if not ok:
                emit_log("❌ Pipeline failed at step 3")
                socketio.emit("processing_error", {"message": "TTS generation failed"})
                return

        # Step 5: stable-ts
        step = PIPELINE_STEPS[4]
        # CRITICAL: Delete existing heart_all.srt to prevent user input prompt (y/n)
        heart_srt = TEMP_DIR / "heart_all.srt"
        if heart_srt.exists():
            heart_srt.unlink()
            emit_log("🗑️ Removed existing heart_all.srt to prevent overwrite prompt")

        # stable-ts uses venv version via PATH (prepended in run_cmd with VENV_SCRIPTS)
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
            TEMP_DIR,
            step,
        )
        if not ok:
            emit_log("❌ Pipeline failed at step 4")
            socketio.emit("processing_error", {"message": "Subtitle generation failed"})
            return

        # Step 6: Color replacement (inline Python — no PowerShell needed)
        step = PIPELINE_STEPS[5]
        emit_step_status(step["id"], "running", step["description"])
        emit_log(f"▶ Running: Inline color replacement (#00ff00 → #ff00ffff)")
        try:
            srt_path = TEMP_DIR / "heart_all.srt"
            text = srt_path.read_text(encoding="utf-8")
            text = text.replace("#00ff00", "#ff00ffff")
            srt_path.write_text(text, encoding="utf-8")
            emit_step_status(step["id"], "completed", f"{step['name']} completed ✓")
            emit_progress(step["progress_end"])
            emit_log(f"✓ {step['name']} completed successfully")
        except Exception as e:
            emit_log(f"⚠ Color replacement had issues: {e} (non-critical)")
            emit_step_status(step["id"], "completed", "Color replacement done")
            emit_progress(step["progress_end"])

        # Step 7: rearrange_9x16.py
        step = PIPELINE_STEPS[6]
        # Delete existing output video to avoid any prompts
        output_video = TEMP_DIR / "output_9x16_letterbox.mp4"
        if output_video.exists():
            output_video.unlink()
            emit_log("🗑️ Removed existing output_9x16_letterbox.mp4")

        ok, log = run_cmd(
            [
                VENV_PYTHON,
                str(SCRIPTS_DIR / "rearrange_9x16.py"),
                "--input",
                "video1.mp4",
                "--output",
                "output_9x16_letterbox.mp4",
                "--last",
                "3",
                "--letterbox",
            ],
            TEMP_DIR,
            step,
        )
        if not ok:
            emit_log("❌ Pipeline failed at step 6")
            socketio.emit("processing_error", {"message": "Video reformatting failed"})
            return

        # Step 8: burn_hardsub_fit_ass.py
        step = PIPELINE_STEPS[7]
        burn_cmd = [
            VENV_PYTHON,
            str(SCRIPTS_DIR / "burn_hardsub_fit_ass.py"),
            "--keep_font_color",
            "--ass_color_order",
            "rgb",
            "--margin_v_ratio",
            "0.24",
            "--base_scale",
            "0.056",
        ]

        add_music_file = TEMP_DIR / "add_music.txt"
        if add_music_file.exists() and add_music_file.read_text(encoding="utf-8").strip() == "true":
            burn_cmd.append("--add-music")

        ok, log = run_cmd(
            burn_cmd,
            TEMP_DIR,
            step,
        )
        if not ok:
            emit_log("❌ Pipeline failed at step 8")
            socketio.emit("processing_error", {"message": "Subtitle burning failed"})
            return

        # Collect produced files
        produced_files = []
        for fname in [
            "output.txt",
            "heart_all.wav",
            "heart_all.srt",
            "output_9x16_letterbox.mp4",
        ]:
            if (TEMP_DIR / fname).exists():
                produced_files.append(fname)

        maybe_final = final_video_name_from_input_txt()
        if maybe_final and (TEMP_DIR / maybe_final).exists():
            produced_files.append(maybe_final)

        emit_log("=" * 60)
        emit_log("✅ Pipeline completed successfully!")
        emit_log("=" * 60)
        emit_progress(100)
        socketio.emit("processing_complete", {"files": produced_files})

    except Exception as e:
        if check_cancelled():
            emit_log("🛑 Pipeline cancelled by user")
            socketio.emit("processing_cancelled", {"message": "Pipeline cancelled"})
        else:
            emit_log(f"❌ Unexpected error: {str(e)}")
            socketio.emit("processing_error", {"message": str(e)})


# -------------------------------------------------------
# ROUTES
# -------------------------------------------------------
@app.route("/")
def index():
    """Main page."""
    return render_template("index.html")


@app.route("/start_processing", methods=["POST"])
def start_processing():
    """Start the video processing pipeline."""
    try:
        # Ensure temp dir exists
        TEMP_DIR.mkdir(parents=True, exist_ok=True)

        # Handle video file upload (drag-drop OR auto-select from v_raw)
        auto_select_file = request.form.get("auto_select_file", "").strip()
        if auto_select_file:
            # Auto-select mode: copy from v_raw to video1.mp4
            src = PCC_DIR / "v_raw" / auto_select_file
            if src.exists():
                dst = TEMP_DIR / UPLOAD_VIDEO_NAME
                shutil.copy2(str(src), str(dst))
                emit_log(f"📂 Auto-selected from v_raw: {auto_select_file}")
            else:
                return jsonify({"status": "error", "message": f"File not found in v_raw: {auto_select_file}"}), 400
        elif "video_file" in request.files:
            video_file = request.files["video_file"]
            if video_file and video_file.filename:
                video_path = TEMP_DIR / UPLOAD_VIDEO_NAME
                video_file.save(str(video_path))
                emit_log(f"📹 Video uploaded: {video_file.filename}")
            else:
                emit_log("⚠ No video uploaded, using existing video1.mp4")
        else:
            emit_log("⚠ No video file in request")

        # Handle video topic (optional weighted context)
        video_topic = request.form.get("video_topic", "").strip()
        topic_path = TEMP_DIR / "video_topic.txt"
        if video_topic:
            topic_path.write_text(video_topic, encoding="utf-8")
            emit_log(f"📝 Video topic set: {video_topic}")
        elif topic_path.exists():
            topic_path.unlink()  # Remove stale topic file

        # Handle target char count (optional)
        target_chars = request.form.get("target_chars", "").strip()
        tc_path = TEMP_DIR / "target_chars.txt"
        if target_chars and int(target_chars) > 0:
            tc_path.write_text(target_chars, encoding="utf-8")
            emit_log(f"🔒 Target char count: {target_chars}")
        elif tc_path.exists():
            tc_path.unlink()

        # Script will be automatically generated by Ollama after video analysis
        emit_log("🤖 Script will be auto-generated by AI from video analysis")

        # Handle mute raw audio option
        mute_raw = request.form.get("mute_raw_audio", "").strip()
        if mute_raw == "true":
            video_path = TEMP_DIR / UPLOAD_VIDEO_NAME
            if video_path.exists():
                muted_path = TEMP_DIR / "_video1_muted.mp4"
                try:
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", str(video_path), "-an", "-c:v", "copy", str(muted_path)],
                        check=True, capture_output=True, text=True,
                    )
                    muted_path.replace(video_path)
                    emit_log("🔇 Raw video audio stripped")
                except Exception as e:
                    emit_log(f"⚠ Failed to mute raw audio: {e}")

        # Handle add music option
        add_music = request.form.get("add_music", "").strip()
        am_path = TEMP_DIR / "add_music.txt"
        if add_music == "true":
            am_path.write_text("true", encoding="utf-8")
            emit_log("🎵 Add background music enabled")
        elif am_path.exists():
            am_path.unlink()

        # Handle skip analysis option
        skip_analysis = request.form.get("skip_analysis", "").strip()
        skip_path = TEMP_DIR / "skip_analysis.txt"
        if skip_analysis == "true":
            skip_path.write_text("true", encoding="utf-8")
            emit_log("⏭️ Skip video analysis enabled")
        elif skip_path.exists():
            skip_path.unlink()

        # Start processing in background thread
        thread = threading.Thread(target=process_pipeline)
        thread.daemon = True
        thread.start()

        return jsonify({"status": "started", "message": "Processing started"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/files/<path:filename>")
def files(filename):
    """Serve output files for download."""
    return send_from_directory(str(TEMP_DIR), filename, as_attachment=False)


@app.route("/existing_files")
def existing_files():
    """Get list of existing output files."""
    existing = []
    for fname in [
        "output.txt",
        "heart_all.wav",
        "heart_all.srt",
        "output_9x16_letterbox.mp4",
    ]:
        if (TEMP_DIR / fname).exists():
            existing.append(fname)

    maybe_final = final_video_name_from_input_txt()
    if maybe_final and (TEMP_DIR / maybe_final).exists():
        existing.append(maybe_final)

    return jsonify({"files": existing})


@app.route("/api/v_raw_oldest")
def v_raw_oldest():
    """Return the oldest video file in v_raw/ by modification time."""
    v_raw_dir = PCC_DIR / "v_raw"
    if not v_raw_dir.exists():
        return jsonify({"found": False})
    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
    files = [f for f in v_raw_dir.iterdir() if f.is_file() and f.suffix.lower() in video_exts]
    if not files:
        return jsonify({"found": False})
    oldest = min(files, key=lambda f: f.stat().st_mtime)
    return jsonify({
        "found": True,
        "filename": oldest.name,
        "size": oldest.stat().st_size,
    })


@app.route("/api/move_to_v_fin", methods=["POST"])
def move_to_v_fin():
    """Move the final processed video to v_fin/ and delete the original from v_raw/."""
    data = request.get_json(force=True)
    raw_filename = data.get("raw_filename", "").strip()
    final_filename = data.get("final_filename", "").strip()

    if not raw_filename or not final_filename:
        return jsonify({"status": "error", "message": "Missing filenames"}), 400

    src_raw = PCC_DIR / "v_raw" / raw_filename
    src_final = TEMP_DIR / final_filename

    if not src_raw.exists():
        return jsonify({"status": "error", "message": "Original file not found in v_raw"}), 404
    if not src_final.exists():
        return jsonify({"status": "error", "message": "Final generated video not found"}), 404

    dst_dir = PCC_DIR / "v_fin"
    dst_dir.mkdir(parents=True, exist_ok=True)

    # Store the final video in v_fin, using the generated name (which includes the title)
    try:
        shutil.copy2(str(src_final), str(dst_dir / final_filename))
        # Delete the original from v_raw
        src_raw.unlink()
        emit_log(f"📦 Saved {final_filename} to v_fin and removed {raw_filename} from v_raw")
        return jsonify({"status": "ok", "message": f"Saved to v_fin and cleaned up v_raw"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/cancel_processing", methods=["POST"])
def cancel_processing():
    """Cancel the running pipeline and kill any active subprocess."""
    global current_subprocess
    pipeline_cancel.set()

    # Unblock any waiting gates so the pipeline thread can exit
    analysis_review_gate.set()
    script_review_gate.set()

    # Kill running subprocess if any
    with current_subprocess_lock:
        if current_subprocess and current_subprocess.poll() is None:
            try:
                current_subprocess.kill()
                current_subprocess.wait(timeout=5)
                emit_log("🛑 Killed running subprocess")
            except Exception:
                pass
            current_subprocess = None

    emit_log("🛑 Pipeline cancellation requested")
    socketio.emit("processing_cancelled", {"message": "Pipeline cancelled"})
    return jsonify({"status": "ok", "message": "Cancellation requested"})


# -------------------------------------------------------
# WEBSOCKET EVENTS
# -------------------------------------------------------
@socketio.on("connect")
def handle_connect():
    """Handle client connection."""
    emit_log("🔌 Client connected")


@socketio.on("disconnect")
def handle_disconnect():
    """Handle client disconnection."""
    print("Client disconnected")


@socketio.on("script_review_response")
def handle_script_review(data):
    """Handle user's script review decision: approve, extend, reduce, or regenerate."""
    global script_review_action
    script_review_action = {
        "action": data.get("action", "approve"),
        "text": data.get("text", ""),
        "target_chars": data.get("target_chars", 0),
    }
    script_review_gate.set()


@socketio.on("analysis_review_response")
def handle_analysis_review(data):
    """Handle user's analysis review decision: approve with optional edits."""
    global analysis_review_action
    analysis_review_action = {
        "action": data.get("action", "approve"),
        "text": data.get("text", ""),
    }
    analysis_review_gate.set()


@socketio.on("update_title")
def handle_update_title(data):
    """Handle manually edited title from the frontend."""
    new_title = data.get("title", "").strip()
    if new_title:
        (TEMP_DIR / "generated_title.txt").write_text(new_title, encoding="utf-8")


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, allow_unsafe_werkzeug=True)
