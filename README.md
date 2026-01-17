<div align="center">
    <h1>Multimodal AI Content Pipeline</h1>

https://github.com/user-attachments/assets/31bfbcb7-30d6-4e1b-a849-686c7b6bef26

</div>

<div align="center">
<a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-gray?style=flat&logo=python&logoColor=white&labelColor=3776AB" alt="Python"></a>
<a href="https://opencv.org/"><img src="https://img.shields.io/badge/OpenCV-4.9+-gray?style=flat&logo=opencv&logoColor=white&labelColor=5C3EE8" alt="OpenCV"></a>
<a href="https://numpy.org/"><img src="https://img.shields.io/badge/NumPy-1.24+-gray?style=flat&logo=numpy&logoColor=white&labelColor=013243" alt="NumPy"></a>
<a href="https://pytorch.org/"><img src="https://img.shields.io/badge/PyTorch-2.3+-gray?style=flat&logo=pytorch&logoColor=white&labelColor=EE4C2C" alt="PyTorch"></a>
<a href="https://huggingface.co/docs/transformers/index"><img src="https://img.shields.io/badge/Transformers-4.45+-gray?style=flat&logo=huggingface&logoColor=FFD21E&labelColor=454545" alt="Transformers"></a>
<a href="https://github.com/openai/whisper"><img src="https://img.shields.io/badge/OpenAI%20Whisper-v20231117-gray?style=flat&logo=openai&logoColor=white&labelColor=412991" alt="OpenAI Whisper"></a>
<a href="https://ffmpeg.org/"><img src="https://img.shields.io/badge/FFmpeg-6.0+-gray?style=flat&logo=ffmpeg&logoColor=white&labelColor=007808" alt="FFmpeg"></a>
</div>

---

## 📋 Overview
**Multimodal AI Content Pipeline** is a tool designed to automate the creation of vertical short-form content from raw video footage. It leverages AI models for vision, speech, and audio processing to analyze content, generate narration, and produce polished videos with hardcoded subtitles.

### Core Focus Points
*   **Intelligent Analysis**: Automatically generates per-second descriptions of video content using the BLIP image captioning model.
*   **High-Quality Narration**: Synthesizes natural-sounding speech using the **Kokoro-82M** TTS model.
*   **Precise Subtitling**: Uses **OpenAI Whisper** (via `stable-ts`) for word-level timestamp accuracy and burns custom-styled subtitles.
*   **Vertical Adaptation**: automatically crops or letterboxes horizontal footage into 9:16 vertical formats suitable for mobile viewing.

---

## Key Concepts

| Concept | Description |
| :--- | :--- |
| **Vision-Language Understanding** | Uses **Salesforce/BLIP** to convert visual frames into textual descriptions, enabling content-aware script generation. |
| **Neural TTS** | Implements **Kokoro**, a lightweight yet high-quality text-to-speech model, for generating voiceovers that sound human and engaging. |
| **Automated Editing** | Programmatically manipulates video using **MoviePy** and **FFmpeg** to handle resizing, audio mixing, and subtitle burning without manual editor intervention. |
| **Hardsub Processing** | Converts standard SRT subtitles into advanced **ASS format** to ensure perfect fit, readability, and color styling on vertical video screens. |

---

## Architecture

The project operates as a sequential pipeline optimized for local execution on consumer GPUs (e.g., NVIDIA RTX series).

### Typical Topology
1.  **Input**: Raw MP4 video file.
2.  **Analysis Node**: `analyze_cat_video.py` samples frames at 1 FPS -> `output.txt`.
3.  **Creative Node** (User/LLM): User refines analysis into a script -> `input.txt`.
4.  **Synthesis Node**: `kokoro_heart.py` generates speech audio -> `heart_all.wav`.
5.  **Alignment Node**: `stable-ts` generates subtitles -> `heart_all.srt`.
6.  **Compositing Node**: `rearrange_9x16.py` & `burn_hardsub_fit_ass.py` render the final vertical video.

---

## Scenarios

| Scenario | Objective |
| :--- | :--- |
| **Full Automation Run** | Go from a raw landscape video of a cat (or any subject) to a fully narrated, subtitled vertical Short. |
| **Metadata Generation** | Use the analysis tool strictly to log activities in a video collection for searchability or archiving. |
| **Subtitle Styling** | Use the burn tool to apply high-readability, karaoke-style or static colored subtitles to any existing vertical video. |

---

## ⚙️ Setup

### Prerequisites
*   **Python 3.10+**
*   **FFmpeg** installed and added to system PATH.
*   **NVIDIA GPU** (Recommended) with CUDA 12.1+ for fast inference.

### Installation
1.  Clone the repository:
    ```bash
    git clone https://github.com/muhammad-thariq/HM-Tools-YTAutomation.git
    cd HM-Tools-YTAutomation
    ```

2.  Create and activate a virtual environment (Recommended):
    ```bash
    # Create virtual environment
    python -m venv .venv

    # Activate on Windows
    .\venv\Scripts\activate

    # Activate on Linux/macOS
    source venv/bin/activate
    ```

3.  Install dependencies (PyTorch with CUDA 12.1 is recommended):
    ```bash
    # Install PyTorch with CUDA support first
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    
    # Install remaining requirements
    pip install -r requirements.txt
    ```

---

## Execution

Follow this workflow to generate a video:

### 1. Analyze Core Footage
Extracts a play-by-play description of the video.
```bash
python analyze_cat_video.py --video video1.mp4 --out output.txt --fps 1.0
```
> **Output**: `output.txt` containing timestamps and descriptions.

### 2. Prepare Script
*   Open `output.txt`.
*   Use an LLM (ChatGPT/Claude) to turn the descriptions into a short, engaging script.
*   Save the script into **`input.txt`**.

### 3. Generate Audio (TTS)
Synthesizes the voiceover from your script.
```bash
python kokoro_heart.py
```
> **Output**: `heart_all.wav`

### 4. Create and Style Subtitles
Generates word-level subtitles and applies color formatting.
```powershell
# Generate SRT
stable-ts heart_all.wav --output heart_all.srt --output_format srt --device cuda --language en --word_timestamps True --max_chars 42 --max_words 3

# Apply Custom Colors (PowerShell)
(Get-Content .\heart_all.srt) -replace '#00ff00','#ff00ffff' | Set-Content .\heart_all.srt -Encoding utf8
```

### 5. Render Vertical Video
Crops/Letterboxes the video to 9:16 and mixes input audio.
```bash
python rearrange_9x16.py --input video1.mp4 --output output_9x16_letterbox.mp4 --last 3 --letterbox
```

### 6. Burn Hardsubs
Finalizes the video with high-contrast subtitles.
```bash
python burn_hardsub_fit_ass.py --keep_font_color --ass_color_order rgb --margin_v_ratio 0.24 --base_scale 0.056
```
> **Final Output**: `heart_all_visual_hardsub.mp4`

---

<div align="center">

*[Back to Top](#hm-tools-automatedshorts)*

</div>
