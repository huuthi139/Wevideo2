#!/usr/bin/env python3
"""Turn a narration MP3 into candidate subtitle windows.

Runs ffmpeg silencedetect, inverts the silences into *speech* segments, and
prints each segment already shifted onto the VIDEO timeline (i.e. + lead_in),
so you can read them straight into cue start/end values. Merge or split the
segments to match how you want to chunk the caption text.

Usage:  python3 detect_silence.py voice.mp3 [lead_in] [noise_db] [min_gap]
        defaults: lead_in=1.2  noise_db=-32  min_gap=0.30
"""
import re
import subprocess
import sys

voice = sys.argv[1]
lead = float(sys.argv[2]) if len(sys.argv) > 2 else 1.2
noise = sys.argv[3] if len(sys.argv) > 3 else "-32"
gap = sys.argv[4] if len(sys.argv) > 4 else "0.30"

dur = float(subprocess.check_output([
    "ffprobe", "-v", "error", "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1", voice]).strip())

out = subprocess.run(
    ["ffmpeg", "-hide_banner", "-i", voice, "-af",
     f"silencedetect=noise={noise}dB:d={gap}", "-f", "null", "-"],
    capture_output=True, text=True).stderr

starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]

# Build speech segments = time NOT inside a silence.
sil = list(zip(starts, ends)) if len(starts) == len(ends) else list(zip(starts, ends + [dur]))
segs = []
cur = 0.0
for s, e in sil:
    if s > cur + 0.05:
        segs.append((cur, s))
    cur = e
if cur < dur - 0.05:
    segs.append((cur, dur))

print(f"# voice duration: {dur:.2f}s   lead_in: {lead}s   (video time = voice time + lead_in)")
print(f"# {len(segs)} speech segments (start_video  end_video  length):")
for s, e in segs:
    print(f"  {s + lead:6.2f}  {e + lead:6.2f}   ({e - s:.2f}s)")
print("\n# Draft cues (merge short ones, split long ones, then add the text lines):")
print('  "cues": [')
for s, e in segs:
    print(f'    {{"start": {s + lead:.2f}, "end": {e + lead:.2f}, "lines": ["..."]}},')
print("  ]")
