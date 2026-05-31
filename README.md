<div align="center">
    <h1>Video Analysis Automation</h1>
    <p>Automated vertical short-form video generation from raw footage via vision analysis, AI scripting, neural TTS, and styled subtitles, all behind a real-time web UI.</p>

https://github.com/user-attachments/assets/31bfbcb7-30d6-4e1b-a849-686c7b6bef26

</div>

<div align="center">
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-gray?style=flat&labelColor=blue" alt="License"></a>
    <br>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-gray?style=flat&logo=python&logoColor=white&labelColor=3776AB" alt="Python"></a>
    <a href="https://flask.palletsprojects.com/"><img src="https://img.shields.io/badge/Flask-3.0+-gray?style=flat&logo=flask&logoColor=white&labelColor=000000" alt="Flask"></a>
    <a href="https://opencv.org/"><img src="https://img.shields.io/badge/OpenCV-4.9+-gray?style=flat&logo=opencv&logoColor=white&labelColor=5C3EE8" alt="OpenCV"></a>
    <a href="https://numpy.org/"><img src="https://img.shields.io/badge/NumPy-1.24+-gray?style=flat&logo=numpy&logoColor=white&labelColor=013243" alt="NumPy"></a>
    <a href="https://pytorch.org/"><img src="https://img.shields.io/badge/PyTorch-2.3+-gray?style=flat&logo=pytorch&logoColor=white&labelColor=EE4C2C" alt="PyTorch"></a>
    <a href="https://huggingface.co/docs/transformers/index"><img src="https://img.shields.io/badge/Transformers-4.45+-gray?style=flat&logo=huggingface&logoColor=FFD21E&labelColor=454545" alt="Transformers"></a>
    <a href="https://github.com/openai/whisper"><img src="https://img.shields.io/badge/OpenAI%20Whisper-v20231117-gray?style=flat&logo=openai&logoColor=white&labelColor=412991" alt="OpenAI Whisper"></a>
    <a href="https://ffmpeg.org/"><img src="https://img.shields.io/badge/FFmpeg-6.0+-gray?style=flat&logo=ffmpeg&logoColor=white&labelColor=007808" alt="FFmpeg"></a>
    <a href="https://ollama.com/"><img src="https://img.shields.io/badge/Ollama-LLaMA_3.1-gray?style=flat&logo=meta&logoColor=white&labelColor=0467DF" alt="Ollama"></a>
</div>

---

## Table of Contents

- [Overview](#-overview)
- [Key Concepts](#key-concepts)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Scenarios](#scenarios)
- [Setup](#setup)
- [Configuration](#configuration)
- [Execution](#execution)
- [Troubleshooting](#troubleshooting)
- [Model Licenses & Acknowledgments](#model-licenses--acknowledgments)
- [License](#license)

---

## Overview

<img width="1400" height="1926" alt="Web dashboard screenshot" src="https://github.com/user-attachments/assets/b02cc74d-560e-4d2d-864e-e856043b2c08" />

**Video Analysis Automation** is a web-based tool that automates the creation of vertical short-form content from raw video footage. It provides a **Flask-powered web UI** with real-time progress tracking via Socket.IO, and leverages AI models for vision analysis, script generation, speech synthesis, and subtitle styling.

### Core Features
*   **🌐 Web Interface**: Real-time dashboard with drag-and-drop upload, live pipeline progress, script editor, and audio preview.
*   **📂 Auto-Select from `v_raw`**: Automatically pick the oldest unprocessed video from the `v_raw` directory. Processed files are moved to `v_fin` after download.
*   **👁️ Computer Vision Analysis**: Uses Salesforce/BLIP to convert visual frames into textual descriptions, enabling content-aware script generation.
*   **🤖 AI Script Generation**: Uses **Ollama (LLaMA 3.1)** to analyze video content and generate engaging narration scripts, with regenerate, extend, and reduce controls.
*   **🏷️ AI Title Generation**: Automatically generates a video title from the approved script using a second Ollama prompt.
*   **🔊 TTS Audio Preview**: Generates speech via **Kokoro-82M** TTS with in-browser audio preview before approval.
*   **🎵 Background Music**: Optionally mixes a background music track into the final video at configurable volume.
*   **🔇 Mute Raw Audio**: Strip the original video's audio before processing.
*   **📝 Human-in-the-Loop**: Review, edit, regenerate, extend, or reduce the AI script before approving — all from the web UI.
*   **🎬 Vertical Adaptation**: Automatically crops or letterboxes footage into 9:16 vertical format.
*   **✨ Precise Subtitling**: Uses **OpenAI Whisper** (`stable-ts`) for word-level timestamps with custom ASS-styled subtitles.

---

## Key Concepts

| Concept | Description |
| :--- | :--- |
| **Vision-Language Understanding** | Uses **Salesforce/BLIP** to convert visual frames into textual descriptions, enabling content-aware script generation. |
| **LLM Script & Title Generation** | Uses **Ollama** with LLaMA 3.1 to generate scripts and titles from video analysis, with system prompts for style control. |
| **Neural TTS** | Implements **Kokoro**, a lightweight yet high-quality text-to-speech model, for generating voiceovers that sound human and engaging. |
| **Automated Editing** | Programmatically manipulates video using **MoviePy** and **FFmpeg** to handle resizing, audio mixing, and subtitle burning. |
| **Hardsub Processing** | Converts standard SRT subtitles into advanced **ASS format** to ensure perfect fit, readability, and color styling on vertical video screens. |

---

## Architecture

The project runs as a **Flask + Socket.IO web application** that orchestrates a sequential pipeline in a background thread.

### Pipeline Steps

| No | Step | Script | Output |
| :-- | :--- | :--- | :--- |
| 1 | Video Analysis — samples frames at 1 FPS | `analyze_cat_video.py` | `output.txt` |
| 2 | Script Generation — narration from analysis | `ollama_generate_script.py` | `input.txt` |
| 3 | Script Review — human-in-the-loop (edit / regenerate / extend / reduce / approve) | — | — |
| 4 | Title Generation — title from approved script | `ollama_generate_title.py` | `generated_title.txt` |
| 5 | TTS Synthesis — speech audio | `kokoro_heart.py` | `heart_all.wav` |
| 6 | Subtitle Alignment — word-level subtitles | `stable-ts` | `heart_all.srt` |
| 7 | Vertical Reformat — crop / letterbox to 9:16 | `rearrange_9x16.py` | `output_9x16_letterbox.mp4` |
| 8 | Subtitle Burn + Music — burn ASS subtitles, optionally mix music | `burn_hardsub_fit_ass.py` | final titled `.mp4` |

### API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Serve the web dashboard |
| `POST` | `/start_processing` | Upload video & start the full pipeline |
| `POST` | `/script_review_response` | Submit script review action (approve / regenerate / extend / reduce / edit) |
| `GET` | `/api/v_raw_oldest` | Get the oldest unprocessed video from `v_raw/` |
| `POST` | `/api/move_to_v_fin` | Save final video to `v_fin/` and clean up `v_raw/` |
| `GET` | `/files/<path>` | Serve generated files (videos, audio, etc.) |

### Socket.IO Events

| Event | Direction | Description |
| :--- | :--- | :--- |
| `log` | Server → Client | Real-time pipeline log messages |
| `progress` | Server → Client | Overall progress percentage updates |
| `step_status` | Server → Client | Individual pipeline step status changes |
| `script_review` | Server → Client | Script ready for human review |
| `audio_ready` | Server → Client | TTS audio available for preview |
| `title_generated` | Server → Client | AI-generated title for the video |
| `processing_complete` | Server → Client | Pipeline finished with output file list |
| `processing_error` | Server → Client | Pipeline error with message |

### Project Structure

```
video-analysis-automation/
├── app.py                      # Flask + Socket.IO backend server
├── analyze_cat_video.py        # BLIP vision analysis (Step 1)
├── ollama_generate_script.py   # AI script generation via Ollama (Step 2)
├── ollama_generate_title.py    # AI title generation via Ollama (Step 4)
├── kokoro_heart.py             # Kokoro-82M TTS synthesis (Step 5)
├── rearrange_9x16.py           # 9:16 vertical reformat (Step 7)
├── burn_hardsub_fit_ass.py     # ASS subtitle burn + music mixing (Step 8)
├── system_prompt.txt           # System prompt for script generation
├── system_prompt_title.txt     # System prompt for title generation
├── templates/
│   └── index.html              # Web UI dashboard
├── static/
│   ├── app.js                  # Frontend logic (Socket.IO, upload, review)
│   └── style.css               # UI styling
├── music/
│   └── videoplayback.m4a       # Background music track
├── v_raw/                      # Unprocessed input videos (Auto-Select source)
├── v_fin/                      # Finished output videos (Auto-Select destination)
├── requirements.txt            # Python dependencies
└── README.md                   # Project documentation
```

---

## Tech Stack

| Category | Technologies |
| :--- | :--- |
| **Backend** | Python, Flask, Flask-SocketIO, FFmpeg, MoviePy |
| **Frontend** | HTML5, Vanilla JS, CSS3, Socket.IO Client |
| **AI / Vision** | Salesforce/BLIP (image captioning), PyTorch, Transformers |
| **AI / LLM** | Ollama (LLaMA 3.1) for script & title generation |
| **AI / Speech** | Kokoro-82M (TTS), OpenAI Whisper via `stable-ts` (STT) |
| **Video Processing** | FFmpeg, OpenCV, NumPy |
| **Real-time Comms** | Socket.IO (bidirectional events) |

---

## Scenarios

| Scenario | Objective |
| :--- | :--- |
| **Full Web UI Run** | Upload or auto-select a video, let AI generate a script, preview audio, approve, and download the final titled vertical short. |
| **Batch Processing** | Place videos in `v_raw/`, use Auto-Select to process them one at a time; finished files land in `v_fin/`. |
| **Script Iteration** | Use regenerate/extend/reduce buttons to refine the AI-generated script before committing to TTS. |
| **Subtitle Styling** | Use the burn tool standalone to apply high-readability, colored subtitles to any existing vertical video. |

---

## Setup

### Prerequisites
*   **Python 3.10+**
*   **FFmpeg** installed and added to your system `PATH` (verify with `ffmpeg -version`).
*   **Ollama** installed and running locally with the `llama3.1:latest` model pulled.
*   **NVIDIA GPU (recommended)** with CUDA 12.1+. The pipeline loads BLIP, Kokoro-82M, Whisper, and an 8B LLM; **~8 GB VRAM** is a comfortable floor for quantized LLaMA 3.1. CPU-only works but is significantly slower.

### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/muhammad-thariq/video-analysis-automation.git
    cd video-analysis-automation
    ```

2.  Create and activate a virtual environment (recommended):
    ```bash
    python -m venv .venv

    # Windows
    .\.venv\Scripts\activate

    # Linux / macOS
    source .venv/bin/activate
    ```

3.  Install dependencies (PyTorch with CUDA 12.1 is recommended):
    ```bash
    # Install PyTorch with CUDA support first
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

    # Install remaining requirements
    pip install -r requirements.txt
    ```

4.  Ensure Ollama is running and the model is available:
    ```bash
    ollama pull llama3.1:latest
    ollama serve
    ```

---

## Configuration

Common settings you may want to adjust:

| Setting | Where | Notes |
| :--- | :--- | :--- |
| **LLM model** | `ollama_generate_script.py`, `ollama_generate_title.py` | Swap `llama3.1:latest` for any model you've pulled in Ollama. |
| **Script style** | `system_prompt.txt`, `system_prompt_title.txt` | Edit the system prompts to control tone, length, and titling style. |
| **Input / output folders** | `v_raw/`, `v_fin/` | Auto-Select reads from `v_raw/`; finished videos are saved to `v_fin/`. |
| **Background music** | `music/videoplayback.m4a` | Replace this file or pass a different track to the burn step. |
| **Server port** | `app.py` | Defaults to `5000`. |

> If you maintain any secrets or machine-specific paths, keep them out of version control via a `.env` file or local config rather than hard-coding them.

---

## Execution

### Web UI (recommended)
Start the Flask development server:
```bash
python app.py
```
Then open **http://localhost:5000** in your browser.

**Workflow:**
1.  **Upload** a video via drag-and-drop, or use **Auto-Select** to pick the oldest video from `v_raw/`.
2.  Optionally set a **Video Topic** for context-aware script generation.
3.  Configure toggles: **Mute Audio**, **Add Music**, **Target Script Length**.
4.  Click **Start Processing** — the pipeline runs with live progress updates.
5.  **Review the AI-generated script** — regenerate, extend, reduce, or edit before approving.
6.  **Preview the generated audio** before final approval.
7.  Once approved, the AI generates a **title** and the pipeline completes.
8.  Click **Download Video** to get the final output. If Auto-Select was used, the finished video is also saved to `v_fin/`.

### CLI (manual pipeline)
You can also run individual steps from the command line. Step numbers below match the [Pipeline Steps](#pipeline-steps) table:

```bash
# Step 1 — Analyze video
python analyze_cat_video.py --video video1.mp4 --out output.txt --fps 1.0

# Step 2 — Generate script via Ollama
python ollama_generate_script.py

# Step 4 — Generate title via Ollama
python ollama_generate_title.py

# Step 5 — Generate TTS audio
python kokoro_heart.py

# Step 6 — Generate subtitles
stable-ts heart_all.wav --output heart_all.srt --output_format srt \
  --device cuda --language en --word_timestamps True --max_chars 42 --max_words 3

# Step 7 — Reformat to 9:16
python rearrange_9x16.py --input video1.mp4 --output output_9x16_letterbox.mp4 --last 3 --letterbox

# Step 8 — Burn subtitles (with optional background music)
python burn_hardsub_fit_ass.py --keep_font_color --ass_color_order rgb \
  --margin_v_ratio 0.24 --base_scale 0.056 --add-music
```

---

## Troubleshooting

| Symptom | Likely cause & fix |
| :--- | :--- |
| `ffmpeg: command not found` | FFmpeg isn't on your `PATH`. Reinstall or add it, then verify with `ffmpeg -version`. |
| Connection refused to Ollama / script generation hangs | Ollama isn't running. Start it with `ollama serve` and confirm the model is pulled (`ollama list`). |
| `CUDA out of memory` | Close other GPU processes, use a smaller/quantized LLM, or run on CPU (slower). |
| `torch` installs CPU-only build | Reinstall using the CUDA index URL shown in [Installation](#installation) **before** other requirements. |
| First run is very slow | Model weights (BLIP, Kokoro, Whisper) download on first use and are cached afterward. |
| Subtitles misaligned or off-screen | Tune `--margin_v_ratio` and `--base_scale` in the burn step for your footage. |

---

## Model Licenses & Acknowledgments

This project builds on excellent open models — please review and comply with each upstream license before commercial use:

- **[Salesforce/BLIP](https://huggingface.co/Salesforce/blip-image-captioning-base)** — image captioning.
- **[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)** — neural TTS.
- **[OpenAI Whisper](https://github.com/openai/whisper)** (via [`stable-ts`](https://github.com/jianfch/stable-ts)) — word-level transcription.
- **[Meta LLaMA 3.1](https://ai.meta.com/llama/)** (via [Ollama](https://ollama.com/)) — subject to the LLaMA 3.1 Community License.

---

## License

This project is released under the **MIT License**. See [`LICENSE`](LICENSE) for details. *(Replace if you choose a different license.)*

---

<div align="center">

*[Back to Top](#video-analysis-automation)*

</div>
