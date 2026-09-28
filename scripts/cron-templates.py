#!/usr/bin/env python3
"""Session-cron templates for the Claude-side chart layers (layer 2 local read, layer 3 daily full analysis, and the
scalping publish tick). These crons live only inside a Claude session (CronCreate is in-memory, 7-day expiry), so
`/automation on|demo|real` re-creates them from the templates in integrations/crons/*.md and `/automation off`
deletes them. The launchd scanner and the pilot are NOT here -- they are outside Claude and survive on their own.

Usage:
  cron-templates.py list                                   every template, with the gate that enables it
  cron-templates.py render-all --scratchpad DIR [--json]   the templates ENABLED by docs/architecture/automation-config.json,
                                                           each rendered with {{SCRATCHPAD}} -> DIR and prefixed with
                                                           "[trading-cron:<name>] " so a CronList can identify them
  cron-templates.py render <name> --scratchpad DIR         one template, gates ignored

Template format (integrations/crons/<name>.md): a YAML-like front matter block with name, cron, model, market,
timeframe, layer, artifact, note -- then the prompt body. Gate = master switch on AND layers.<layer> on AND
markets.<market>.enabled AND markets.<market>.timeframes.<timeframe>. Nothing here schedules anything itself.
"""
import json, os, sys, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys as _sys; _sys.path.insert(0, os.path.join(ROOT, "scripts"))  # importable when loaded by path from anywhere
from repo_paths import repo_rel
TPL_DIR = os.path.join(ROOT, "integrations", "crons")
CONFIG = os.path.join(ROOT, "docs", "architecture", "automation-config.json")
TAG = "[trading-cron:{name}] "


def parse(path):
    txt = open(path, encoding="utf-8").read()
    if not txt.startswith("---\n"):
        raise ValueError(f"{path}: missing front matter")
    head, _, body = txt[4:].partition("\n---\n")
    meta = {}
    for line in head.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip('"')
    meta.setdefault("name", os.path.basename(path)[:-3])
    meta["path"] = repo_rel(path, ROOT)
    return meta, body.strip("\n")


def is_template(path):
    """A template starts with a front matter block; README.md and notes do not."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read(4) == "---\n"
    except OSError:
        return False


def templates():
    return [parse(p) for p in sorted(glob.glob(os.path.join(TPL_DIR, "*.md"))) if is_template(p)]


def config():
    try:
        return json.load(open(CONFIG, encoding="utf-8"))
    except Exception:
        return None


def enabled(meta, cfg):
    """(ok, reason). Unconfigured (no file) = enabled, matching every other gate in this repo."""
    if cfg is None:
        return True, "unconfigured (no automation-config.json) -- treated as enabled"
    if not cfg.get("enabled", True):
        return False, "automation master switch is OFF"
    layer = meta.get("layer", "local_read")
    if layer != "none" and not cfg.get("layers", {}).get(layer, True):
        return False, f"layers.{layer} is off"
    m = meta.get("market")
    mk = cfg.get("markets", {}).get(m, {}) if m else {}
    if m and not mk.get("enabled", True):
        return False, f"market {m} is off"
    tf = meta.get("timeframe")
    if m and tf and not mk.get("timeframes", {}).get(tf, True):
        return False, f"timeframe {tf} is off for market {m}"
    return True, "enabled"


def render(meta, body, scratchpad):
    """A cron session receives ONLY this rendered string -- the front matter never reaches it. So anything the
    body refers to must be substituted in here. `{{ARTIFACT}}` carries the template's own `artifact:` value:
    without it, method-switch.md asked a session to call the Artifact tool with "this template's own artifact
    URL" that appeared nowhere in its prompt (found 2026-09-13 while debugging the panel's
    "bộ áp dụng không phản hồi" banner)."""
    prompt = (body.replace("{{SCRATCHPAD}}", scratchpad)
                  .replace("{{ROOT}}", ROOT)
                  .replace("{{ARTIFACT}}", str(meta.get("artifact", "PENDING_CREATE_ON_FIRST_RUN"))))
    return TAG.format(name=meta["name"]) + prompt


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("list", "render-all", "render"):
        print(__doc__); return 1
    scratchpad = None
    if "--scratchpad" in args:
        scratchpad = args[args.index("--scratchpad") + 1]
    as_json = "--json" in args
    cfg = config()
    if args[0] == "list":
        for meta, body in templates():
            ok, why = enabled(meta, cfg)
            print(f"{'ON ' if ok else 'off'}  {meta['name']:<22} cron={meta.get('cron','?'):<24} model={meta.get('model','?'):<7} "
                  f"gate={meta.get('market','-')}/{meta.get('timeframe','-')}/{meta.get('layer','-')}  ({why})")
        return 0
    if not scratchpad:
        print("--scratchpad DIR is required for render", file=sys.stderr); return 1
    os.makedirs(scratchpad, exist_ok=True)
    out = []
    if args[0] == "render":
        name = args[1]
        for meta, body in templates():
            if meta["name"] == name:
                out.append({"name": name, "cron": meta.get("cron"), "model": meta.get("model"),
                            "prompt": render(meta, body, scratchpad)})
        if not out:
            print(f"no template named {name}", file=sys.stderr); return 1
    else:
        for meta, body in templates():
            ok, why = enabled(meta, cfg)
            if ok:
                out.append({"name": meta["name"], "cron": meta.get("cron"), "model": meta.get("model"),
                            "prompt": render(meta, body, scratchpad)})
            else:
                print(f"# skipped {meta['name']}: {why}", file=sys.stderr)
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        for o in out:
            print(f"=== {o['name']}  cron: {o['cron']}  model: {o['model']}\n{o['prompt']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
