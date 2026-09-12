#!/usr/bin/env python3
"""What the session publish tick has to publish, and the bookkeeping for it (single writer of docs/architecture/artifacts.json).

  publish-plan.py                 print, one line per style that (a) is permitted by /automation, (b) has a model.html or a narrative newer
                                  than its last publish, in the form:  <style> <url|PENDING> <out-path> <build-command>
  publish-plan.py --mark <style> [--url URL]   record the publish (touch the marker; store the URL the first publish of a PENDING style created)
  publish-plan.py --status        every style with its inputs' mtimes, last publish, and whether it is due

The model layer (scripts/model-read.sh, headless Sonnet) writes data/live/prelim/<style>.<SYM>.model.html and
data/live/narrative/<style>.json; the scanner writes data/live/prelim/<style>.facts.json. A style is due when the newest of those is
newer than data/live/.published-<style>. The session tick then runs the build command (scripts/build-artifact.py, numbers from
code) and the Artifact read + publish — the only step that must happen inside a Claude session.
"""
import argparse, glob, json, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "docs", "architecture", "artifacts.json")


def load():
    return json.load(open(REG, encoding="utf-8"))


def allowed(style):
    return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "automation.py"), "allows", "local_read", style], capture_output=True).returncode == 0


def inputs_mtime(style):
    paths = glob.glob(f"{ROOT}/data/live/prelim/{style}.*.model.html") + [f"{ROOT}/data/live/narrative/{style}.json", f"{ROOT}/data/live/prelim/{style}.facts.json"]
    ts = [os.path.getmtime(p) for p in paths if os.path.exists(p)]
    return max(ts) if ts else None


def marker(style):
    return os.path.join(ROOT, "data", "live", f".published-{style}")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--mark"); ap.add_argument("--url"); ap.add_argument("--status", action="store_true")
    a = ap.parse_args(); reg = load()
    if a.mark:
        st = reg["styles"].get(a.mark)
        if st is None:
            sys.exit(f"unknown style {a.mark}")
        if a.url:
            st["url"] = a.url
            json.dump(reg, open(REG, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        open(marker(a.mark), "w").write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n")
        print(f"marked {a.mark} published" + (f" at {a.url}" if a.url else "")); return
    for style, st in reg["styles"].items():
        im = inputs_mtime(style); pm = os.path.getmtime(marker(style)) if os.path.exists(marker(style)) else None
        due = im is not None and (pm is None or im > pm)
        ok = allowed(style)
        if a.status:
            print(f"{style:<11} allowed={ok} inputs={time.strftime('%H:%M:%SZ', time.gmtime(im)) if im else '-'} published={time.strftime('%H:%M:%SZ', time.gmtime(pm)) if pm else '-'} due={due and ok} url={st['url'][-12:]}")
        elif due and ok:
            print(f"{style} {st['url']} {st['out']} python3 scripts/build-artifact.py {style} --out {st['out']}")


if __name__ == "__main__":
    main()
