"""
Ollama Title Generator
Reads input.txt and system_prompt_title.txt and generates a video title to generated_title.txt
"""
import sys
import requests
import re
from pathlib import Path

# Fix Windows console encoding for emoji support
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL_NAME = "llama3.1:latest"
SCRIPTS_DIR = Path(__file__).parent.resolve()
SYSTEM_PROMPT_FILE = SCRIPTS_DIR / "system_prompt_title.txt"
INPUT_FILE = "input.txt"
OUTPUT_FILE = "generated_title.txt"

def main():
    try:
        if not SYSTEM_PROMPT_FILE.exists():
            raise FileNotFoundError(f"Missing system prompt: {SYSTEM_PROMPT_FILE}")
        system_prompt = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
        
        input_path = Path(INPUT_FILE)
        if not input_path.exists():
            raise FileNotFoundError(f"Missing script file: {INPUT_FILE}")
        script_text = input_path.read_text(encoding="utf-8", errors="ignore")
        
        user_message = f"SCRIPT:\n{script_text}\n"
        
        payload = {
            "model": MODEL_NAME,
            "prompt": user_message,
            "system": system_prompt,
            "stream": False
        }
        
        print("[AI] Generating title via Ollama...")
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
        
        title = resp.json().get("response", "").strip()
        # Remove any <think> reasoning blocks that newer models might produce
        title = re.sub(r'<think>.*?</think>', '', title, flags=re.DOTALL | re.IGNORECASE).strip()
        
        # Flatten into a single line to ensure it generates valid filenames
        title = ' '.join(title.split())
        
        Path(OUTPUT_FILE).write_text(title, encoding="utf-8")
        print(f"[OK] Title generated: {title}")
        
    except Exception as e:
        print(f"[ERROR] Title generation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
