"""
Ollama Script Generator
Sends output.txt to Ollama LLM with system_prompt.txt and writes result to input.txt
"""
import re
import sys
import argparse
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
    parser = argparse.ArgumentParser(description="Ollama Script Generator")
    parser.add_argument("--topic", type=str, default=None,
                        help="Path to a text file containing the video topic/context")
    parser.add_argument("--extend", action="store_true",
                        help="Extend the existing script in input.txt by ~50%%")
    parser.add_argument("--reduce", action="store_true",
                        help="Reduce the existing script in input.txt by ~50%%")
    parser.add_argument("--target-chars", type=int, default=0,
                        help="Target character count for the generated script")
    args = parser.parse_args()

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
        
        # Build user message with optional weighted topic context
        if args.extend:
            # EXTEND MODE: Read existing script and ask LLM to extend it by ~50%
            print(f"[*] EXTEND MODE: Reading existing script from {OUTPUT_FILE}...")
            existing_script = read_file(OUTPUT_FILE)
            word_count = len(existing_script.split())
            target_extra = max(int(word_count * 0.5), 20)  # At least 20 extra words
            print(f"[*] Current script: {word_count} words, targeting ~{target_extra} additional words")

            # Read topic context if provided
            topic_context = ""
            if args.topic:
                topic_path = Path(args.topic)
                if topic_path.exists():
                    topic_text = topic_path.read_text(encoding="utf-8").strip()
                    if topic_text:
                        topic_context = f'\nVideo topic/context: "{topic_text}"\n'

            user_message = (
                "=== TASK: EXTEND THIS SCRIPT ===\n"
                "You must take the following existing script and EXTEND it by adding "
                f"approximately {target_extra} more words of NEW content.\n\n"
                "RULES:\n"
                "1. Keep ALL of the original script EXACTLY as-is (word for word).\n"
                "2. The script MUST start with \"This cat\" (already in the original).\n"
                "3. The script MUST end with \"...And did you know that?\"\n"
                "4. Insert your NEW content BEFORE the ending phrase \"...And did you know that?\"\n"
                "5. The new content should flow naturally from the existing script.\n"
                "6. Maintain the same comedic tone, energy, and style.\n"
                "7. Output ONLY the full extended script (original + new content), nothing else.\n"
                f"{topic_context}\n"
                "=== ORIGINAL SCRIPT (extend this) ===\n"
                f"{existing_script}\n"
                "=== END ORIGINAL SCRIPT ===\n"
            )

            # Also load image analysis as secondary context
            if Path(INPUT_FILE).exists():
                analysis = read_file(INPUT_FILE)
                # Only add if it's actual analysis (not the script itself)
                if not analysis.strip().startswith("This cat"):
                    user_message += (
                        "\n=== SUPPORTING VISUAL ANALYSIS (for inspiration) ===\n"
                        f"{analysis}\n"
                        "=== END VISUAL ANALYSIS ===\n"
                    )
        elif args.reduce:
            # REDUCE MODE: Read existing script and ask LLM to halve it
            print(f"[*] REDUCE MODE: Reading existing script from {OUTPUT_FILE}...")
            existing_script = read_file(OUTPUT_FILE)
            word_count = len(existing_script.split())
            char_count = len(existing_script)
            target_words = max(int(word_count * 0.5), 10)
            target_char_count = max(int(char_count * 0.5), 50)
            print(f"[*] Current script: {word_count} words / {char_count} chars, targeting ~{target_words} words / ~{target_char_count} chars")

            # Read topic context if provided
            topic_context = ""
            if args.topic:
                topic_path = Path(args.topic)
                if topic_path.exists():
                    topic_text = topic_path.read_text(encoding="utf-8").strip()
                    if topic_text:
                        topic_context = f'\nVideo topic/context: "{topic_text}"\n'

            user_message = (
                "=== TASK: REDUCE THIS SCRIPT ===\n"
                "You must take the following existing script and REDUCE it to approximately "
                f"{target_words} words (~{target_char_count} characters). That is roughly HALF the current length.\n\n"
                "RULES:\n"
                "1. The script MUST start with \"This cat\" (keep the opening).\n"
                "2. The script MUST end with \"...And did you know that?\"\n"
                "3. Keep the BEST and FUNNIEST parts of the original script.\n"
                "4. Remove filler, repetitive jokes, and weaker lines.\n"
                "5. Maintain the same comedic tone, energy, and punchiness.\n"
                "6. The reduced script should feel complete and natural, not abruptly cut.\n"
                "7. Output ONLY the reduced script, nothing else.\n"
                f"{topic_context}\n"
                "=== ORIGINAL SCRIPT (reduce this) ===\n"
                f"{existing_script}\n"
                "=== END ORIGINAL SCRIPT ===\n"
            )
        elif args.topic:
            topic_path = Path(args.topic)
            if topic_path.exists():
                topic_text = topic_path.read_text(encoding="utf-8").strip()
                if topic_text:
                    print(f"[*] Video topic provided: {topic_text}")
                    # Prepend topic as PRIMARY CONTEXT with higher weight than image analysis
                    user_message = (
                        "=== PRIMARY CONTEXT (USE THIS AS THE MAIN THEME) ===\n"
                        f"The creator has specified the following topic/context for this video:\n"
                        f"\"{topic_text}\"\n"
                        "\n"
                        "IMPORTANT: The above topic is the MAIN DIRECTION for the script. "
                        "Use the image analysis below as supporting visual details, but the "
                        "topic above should be the PRIMARY driver of the script's theme, "
                        "jokes, and narrative direction.\n"
                        "=== END PRIMARY CONTEXT ===\n\n"
                        "=== SUPPORTING VISUAL ANALYSIS (secondary reference) ===\n"
                        f"{video_analysis}\n"
                        "=== END VISUAL ANALYSIS ===\n"
                    )
                else:
                    user_message = video_analysis
            else:
                print(f"[WARN] Topic file not found: {args.topic}")
                user_message = video_analysis
        else:
            user_message = video_analysis
        
        # Append target character count instruction if specified
        if args.target_chars and args.target_chars > 0 and not args.extend and not args.reduce:
            target_words_approx = max(int(args.target_chars / 5), 10)  # Rough chars-to-words
            print(f"[*] Target char count: {args.target_chars} (~{target_words_approx} words)")
            user_message += (
                f"\n\n=== LENGTH CONSTRAINT ===\n"
                f"IMPORTANT: The output script MUST be approximately {args.target_chars} characters long "
                f"(roughly {target_words_approx} words). This is a hard constraint — "
                f"aim to be within 10%% of this target length.\n"
                f"=== END LENGTH CONSTRAINT ===\n"
            )
        
        # Call Ollama
        raw_response = call_ollama(system_prompt, user_message)
        
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
