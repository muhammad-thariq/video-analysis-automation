#!/usr/bin/env python3
"""
rearrange_9x16.py  —  Pure-FFmpeg video reformatter (no moviepy).

Builds a single FFmpeg complex filtergraph for:
  1. Timeline rolling  (move last N seconds to the front)
  2. Looping / trimming (match target audio duration)
  3. Scaling            (to exact --size)
  4. Audio mixing       (original @25% + BGM track)

All done in one ffmpeg subprocess call — no frame-by-frame piping.
"""

import argparse
import json
import math
import subprocess
import sys


# ─── ffprobe helpers ────────────────────────────────────────────────

def ffprobe_json(filepath: str, entries: str, select: str = None) -> dict:
    """Run ffprobe and return parsed JSON."""
    cmd = ["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json"]
    if select:
        cmd += ["-select_streams", select]
    cmd.append(filepath)
    r = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def get_duration(filepath: str) -> float:
    info = ffprobe_json(filepath, "format=duration")
    return float(info["format"]["duration"])


def get_video_info(filepath: str) -> dict:
    """Return fps, has_audio, and audio sample_rate for the input file."""
    info = ffprobe_json(filepath, "stream=codec_type,r_frame_rate,sample_rate")

    fps = 30.0
    has_audio = False
    sample_rate = 44100

    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            num, den = s.get("r_frame_rate", "30/1").split("/")
            fps = round(float(num) / float(den), 3)
        elif s.get("codec_type") == "audio":
            has_audio = True
            sample_rate = int(s.get("sample_rate", 44100))

    return {"fps": fps, "has_audio": has_audio, "sample_rate": sample_rate}


# ─── filtergraph builder ────────────────────────────────────────────

def build_filtergraph(
    video_dur: float,
    target_dur: float,
    fps: float,
    out_w: int,
    out_h: int,
    last: float,
    has_audio: bool,
    sample_rate: int,
) -> str:
    """Build the -filter_complex string for ffmpeg."""
    parts = []

    # ── VIDEO ────────────────────────────────────────────────────────
    # 1) Roll: move last `last` seconds to the front
    if last > 0:
        split_t = video_dur - last
        parts.append("[0:v]split[_v1][_v2]")
        parts.append(f"[_v1]trim=start={split_t},setpts=PTS-STARTPTS[_vtail]")
        parts.append(f"[_v2]trim=end={split_t},setpts=PTS-STARTPTS[_vhead]")
        parts.append("[_vtail][_vhead]concat=n=2:v=1:a=0[_vrolled]")
        v = "_vrolled"
    else:
        v = "0:v"

    # 2) Loop (if needed) + trim + scale
    rolled_dur = video_dur  # rolling preserves duration
    if rolled_dur < target_dur - 0.01:
        extra_loops = math.ceil(target_dur / rolled_dur) - 1
        frame_count = int(round(rolled_dur * fps))
        parts.append(
            f"[{v}]loop=loop={extra_loops}:size={frame_count}:start=0,"
            f"trim=duration={target_dur},setpts=PTS-STARTPTS,"
            f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p[vout]"
        )
    else:
        parts.append(
            f"[{v}]trim=duration={target_dur},setpts=PTS-STARTPTS,"
            f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p[vout]"
        )

    # ── AUDIO ────────────────────────────────────────────────────────
    if has_audio:
        # Roll the original audio the same way
        if last > 0:
            split_t = video_dur - last
            parts.append("[0:a]asplit[_a1][_a2]")
            parts.append(f"[_a1]atrim=start={split_t},asetpts=PTS-STARTPTS[_atail]")
            parts.append(f"[_a2]atrim=end={split_t},asetpts=PTS-STARTPTS[_ahead]")
            parts.append("[_atail][_ahead]concat=n=2:v=0:a=1[_arolled]")
            a = "_arolled"
        else:
            a = "0:a"

        # Loop / trim + lower to 25 %
        if rolled_dur < target_dur - 0.01:
            extra_loops = math.ceil(target_dur / rolled_dur) - 1
            sample_count = int(round(rolled_dur * sample_rate))
            parts.append(
                f"[{a}]aloop=loop={extra_loops}:size={sample_count}:start=0,"
                f"atrim=duration={target_dur},asetpts=PTS-STARTPTS,"
                f"volume=0.25[_orig_lo]"
            )
        else:
            parts.append(
                f"[{a}]atrim=duration={target_dur},asetpts=PTS-STARTPTS,"
                f"volume=0.25[_orig_lo]"
            )

        # BGM: just trim to target_dur (it defines the target anyway)
        parts.append(
            f"[1:a]atrim=duration={target_dur},asetpts=PTS-STARTPTS[_bgm]"
        )

        # Mix BGM + lowered original  (normalize=0 keeps volumes as-is)
        parts.append("[_bgm][_orig_lo]amix=inputs=2:duration=first:normalize=0[aout]")
    else:
        # No original audio — BGM only
        parts.append(
            f"[1:a]atrim=duration={target_dur},asetpts=PTS-STARTPTS[aout]"
        )

    return ";\n".join(parts)


# ─── main ───────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Reformat video: roll timeline, loop/trim to audio, scale, mix audio.  Pure FFmpeg."
    )
    ap.add_argument("--input",   "-i", default="video1.mp4",   help="Input video")
    ap.add_argument("--output",  "-o", default="output_9x16.mp4", help="Output video")
    ap.add_argument("--audio",   "-a", default="heart_all.wav", help="BGM / voiceover track")
    ap.add_argument("--size",          default="1080x1920",     help="Output WxH (e.g. 1080x1920)")
    ap.add_argument("--last",    type=float, default=3.0,       help="Seconds to roll from end → start")
    ap.add_argument("--preset",        default="medium",        help="x264 preset")
    ap.add_argument("--crf",     type=int, default=18,          help="x264 CRF (lower = better)")
    # kept for backward-compat with app.py (ignored)
    ap.add_argument("--letterbox", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--fill",     action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--ratio",    default=None,        help=argparse.SUPPRESS)
    args = ap.parse_args()

    # Parse output size
    if "x" not in args.size.lower():
        sys.exit("--size must be WxH, e.g. 1080x1920")
    w_str, h_str = args.size.lower().split("x")
    out_w, out_h = int(w_str), int(h_str)

    # Probe inputs
    video_dur = get_duration(args.input)
    target_dur = get_duration(args.audio)
    info = get_video_info(args.input)
    fps = info["fps"]
    has_audio = info["has_audio"]
    sr = info["sample_rate"]

    last = args.last
    if last <= 0 or last >= video_dur:
        last = 0.0

    print(f"[rearrange] Input : {args.input}  ({video_dur:.2f}s, {fps}fps, audio={'yes' if has_audio else 'no'})")
    print(f"[rearrange] Audio : {args.audio}  ({target_dur:.2f}s)")
    print(f"[rearrange] Roll  : last {last:.1f}s -> front")
    print(f"[rearrange] Output: {args.output}  ({out_w}x{out_h})")

    fg = build_filtergraph(
        video_dur=video_dur,
        target_dur=target_dur,
        fps=fps,
        out_w=out_w,
        out_h=out_h,
        last=last,
        has_audio=has_audio,
        sample_rate=sr,
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", args.input,
        "-i", args.audio,
        "-filter_complex", fg,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-threads", "0",
        args.output,
    ]

    subprocess.run(cmd, check=True)
    print(f"[rearrange] Done -> {args.output}")


if __name__ == "__main__":
    main()
