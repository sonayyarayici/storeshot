"""Command line interface for storeshot."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import presets
from .render import RenderError, Style, compose, save

STARTER_CONFIG = """\
# storeshot configuration
# Docs: https://github.com/sonayyarayici/storeshot

input: raw          # folder holding your raw device screenshots
output: out         # where store-ready images are written
format: png         # png or jpg

targets:
  - ios-6.9         # required by the App Store for iPhone
  - ipad-13         # required by the App Store for iPad
  - play-phone      # Google Play phone
  # - play-feature  # Google Play feature graphic (1024x500 banner)

style:
  background: ["#0B1020", "#1E2A5A"]   # one color = solid, two or more = gradient
  caption_color: "#FFFFFF"
  padding: 0.08         # side padding, fraction of width
  caption_area: 0.20    # top band reserved for the caption
  corner_radius: 0.035  # device corner rounding, fraction of width
  shadow: true
  # font: /path/to/YourFont.ttf

screens:
  - file: 01-home.png
    caption: "Everything in one place"
  - file: 02-search.png
    caption: "Find it instantly"

# Text shown on the Play Store feature graphic, if you enable that target.
feature_caption: "Your tagline here"
"""


def _slug(filename: str) -> str:
    """Stem without a leading order number, so we do not write '01-01-home'."""
    stem = Path(filename).stem
    return re.sub(r"^\d+[-_\s]*", "", stem) or stem


def load_config(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"no config at {path}. Run 'storeshot init' to create a starter file."
        )
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml
    except ImportError:
        raise SystemExit(
            "PyYAML is needed to read .yaml configs. Install it with "
            "'pip install pyyaml', or use a .json config instead."
        )
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise SystemExit(f"{path} does not contain a configuration mapping")
    return data


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.config)
    if path.exists() and not args.force:
        print(f"{path} already exists. Use --force to overwrite.", file=sys.stderr)
        return 1
    path.write_text(STARTER_CONFIG, encoding="utf-8")
    print(f"wrote {path}")
    print("Next: put your raw screenshots in ./raw, then run 'storeshot build'.")
    return 0


def cmd_presets(args: argparse.Namespace) -> int:
    width = max(len(name) for name in presets.PRESETS)
    for name, (w, h) in presets.PRESETS.items():
        note = "  (banner)" if presets.is_banner(name) else ""
        print(f"{name.ljust(width)}  {w} x {h}{note}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    config = load_config(Path(args.config))

    in_dir = Path(config.get("input", "raw"))
    out_dir = Path(config.get("output", "out"))
    fmt = str(config.get("format", "png")).lower().lstrip(".")
    if fmt not in {"png", "jpg", "jpeg"}:
        raise SystemExit(f"format must be png or jpg, got {fmt!r}")

    custom = config.get("custom_targets") or {}
    targets = config.get("targets") or list(presets.DEFAULT_TARGETS)
    screens = config.get("screens") or []

    try:
        style = Style.from_dict(config.get("style") or {})
    except RenderError as exc:
        raise SystemExit(f"config error: {exc}")

    if not screens and not any(presets.is_banner(t) for t in targets):
        raise SystemExit("no screens listed in the config, nothing to build")

    missing = [
        s["file"]
        for s in screens
        if isinstance(s, dict) and s.get("file") and not (in_dir / s["file"]).exists()
    ]
    if missing:
        raise SystemExit(
            f"these files are missing from {in_dir}/: " + ", ".join(missing)
        )

    written = 0
    for target in targets:
        try:
            size = presets.resolve(target, custom)
        except (KeyError, ValueError) as exc:
            raise SystemExit(str(exc).strip("\"'"))

        target_dir = out_dir / target

        if presets.is_banner(target):
            caption = config.get("feature_caption") or ""
            out_path = target_dir / f"feature.{fmt}"
            try:
                save(compose(None, size, style, caption), out_path)
            except RenderError as exc:
                raise SystemExit(f"{target}: {exc}")
            written += 1
            if args.verbose:
                print(f"  {out_path}  ({size[0]}x{size[1]})")
            continue

        for index, screen in enumerate(screens, start=1):
            if not isinstance(screen, dict) or not screen.get("file"):
                raise SystemExit(f"screen #{index} needs a 'file' entry")
            src = in_dir / screen["file"]
            out_path = target_dir / f"{index:02d}-{_slug(screen['file'])}.{fmt}"
            try:
                image = compose(src, size, style, screen.get("caption"))
                save(image, out_path)
            except RenderError as exc:
                raise SystemExit(f"{target} / {screen['file']}: {exc}")
            written += 1
            if args.verbose:
                print(f"  {out_path}  ({size[0]}x{size[1]})")

    print(f"wrote {written} image(s) to {out_dir}/")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="storeshot",
        description="Turn raw device screenshots into store-ready App Store "
        "and Google Play images.",
    )
    parser.add_argument(
        "-c", "--config", default="storeshot.yaml", help="config file (default: %(default)s)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="write a starter config")
    p_init.add_argument("--force", action="store_true", help="overwrite an existing config")
    p_init.set_defaults(func=cmd_init)

    p_presets = sub.add_parser("presets", help="list built-in size presets")
    p_presets.set_defaults(func=cmd_presets)

    p_build = sub.add_parser("build", help="render store images")
    p_build.add_argument("-v", "--verbose", action="store_true", help="list every file written")
    p_build.set_defaults(func=cmd_build)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
