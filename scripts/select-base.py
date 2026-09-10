#!/usr/bin/env python3
"""Pick the base HTML for a publish tick deterministically (single-publisher rule, numbers-from-code discipline).
Usage: select-base.py <style> <artifact_saved_html> <out_html>
If data/live/narrative/<style>.full.html exists AND is newer than data/live/narrative/<style>.applied (or the marker is
missing), copy it to <out_html> and touch the marker (the full analysis goes live); otherwise copy <artifact_saved_html>.
Prints which base was used. Never decides anything else."""
import os, shutil, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
style, saved, out = sys.argv[1:4]
full = f"{ROOT}/data/live/narrative/{style}.full.html"; marker = f"{ROOT}/data/live/narrative/{style}.applied"
use_full = os.path.exists(full) and (not os.path.exists(marker) or os.path.getmtime(full) > os.path.getmtime(marker))
src = full if use_full else saved
shutil.copy(src, out)
if use_full:
    open(marker, "a").close(); os.utime(marker, None)
print(f"BASE: {'full analysis (hand-off applied)' if use_full else 'live artifact'} -> {os.path.relpath(out, ROOT)}")
