"""
Ollama Script Generator
Sends output.txt to Ollama LLM with system_prompt.txt and writes result to input.txt
"""
import re
import sys
import requests
import json
from pathlib import Path

# Fix Windows console encoding for emoji support
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Configuration
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL_NAME = "llama3.1:latest"
SYSTEM_PROMPT_FILE = "system_prompt.txt"
INPUT_FILE = "output.txt"
OUTPUT_FILE = "input.txt"


def read_file(filepath: str) -> str:
    """Read text file content."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    return path.read_text(encoding="utf-8", errors="ignore")


def remove_think_tags(text: str) -> str:
    """Remove <think>...</think> tags from the response."""
    # Remove <think> tags and their content
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Clean up extra whitespace
    cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)
    return cleaned.strip()


def call_ollama(system_prompt: str, user_message: str) -> str:
    """Call Ollama API and get response."""
    print(f"[AI] Calling Ollama API at {OLLAMA_URL}")
    print(f"[*] Model: {MODEL_NAME}")
    
    payload = {
        "model": MODEL_NAME,
        "prompt": user_message,
        "system": system_prompt,
        "stream": False
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        
        result = response.json()
        generated_text = result.get("response", "")
        
        if not generated_text:
            raise ValueError("Empty response from Ollama")
        
        print(f"[OK] Received response ({len(generated_text)} characters)")
        return generated_text
        
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            f"Cannot connect to Ollama at {OLLAMA_URL}. "
            "Make sure Ollama is running with: ollama serve"
        )
    except requests.exceptions.Timeout:
        raise TimeoutError("Ollama request timed out after 120 seconds")
    except Exception as e:
        raise RuntimeError(f"Ollama API error: {str(e)}")


def main():
    """Main execution."""
    try:
        print("=" * 60)
        print("[*] Starting Ollama Script Generation")
        print("=" * 60)
        
        # Read system prompt
        print(f"[*] Reading system prompt from {SYSTEM_PROMPT_FILE}...")
        system_prompt = read_file(SYSTEM_PROMPT_FILE)
        print(f"[OK] System prompt loaded ({len(system_prompt)} characters)")
        
        # Read video analysis output
        print(f"[*] Reading video analysis from {INPUT_FILE}...")
        video_analysis = read_file(INPUT_FILE)
        print(f"[OK] Video analysis loaded ({len(video_analysis)} characters)")
        
        # Call Ollama
        raw_response = call_ollama(system_prompt, video_analysis)
        
        # Remove <think> tags
        print("[*] Cleaning response (removing <think> tags)...")
        cleaned_response = remove_think_tags(raw_response)
        print(f"[OK] Response cleaned ({len(cleaned_response)} characters)")
        
        # Write to input.txt
        print(f"[*] Writing to {OUTPUT_FILE}...")
        output_path = Path(OUTPUT_FILE)
        output_path.write_text(cleaned_response, encoding="utf-8")
        print(f"[OK] Script saved to {OUTPUT_FILE}")
        
        print("=" * 60)
        print("[SUCCESS] Script generation completed successfully!")
        print("=" * 60)
        print("\nGenerated Script Preview:")
        print("-" * 60)
        print(cleaned_response[:200] + "..." if len(cleaned_response) > 200 else cleaned_response)
        print("-" * 60)
        
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        raise


if __name__ == "__main__":
    main()
