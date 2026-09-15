from pathlib import Path

import pytest
from PIL import Image

from storeshot import presets
from storeshot.cli import _slug, main
from storeshot.render import RenderError, Style, compose, make_background, save


# --- presets ---------------------------------------------------------------


def test_builtin_preset_resolves():
    assert presets.resolve("play-feature") == (1024, 500)


def test_custom_target_overrides_builtin():
    assert presets.resolve("ios-6.9", {"ios-6.9": [100, 200]}) == (100, 200)


def test_unknown_target_raises():
    with pytest.raises(KeyError):
        presets.resolve("nope")


def test_custom_target_must_be_a_pair():
    with pytest.raises(ValueError):
        presets.resolve("x", {"x": [100]})


def test_required_store_sizes_are_present():
    # These are the two Apple requires; a typo here ships broken output.
    assert presets.PRESETS["ios-6.9"] == (1320, 2868)
    assert presets.PRESETS["ipad-13"] == (2064, 2752)


# --- helpers ---------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [("01-home.png", "home"), ("home.png", "home"), ("2_search.jpg", "search"), ("07.png", "07")],
)
def test_slug_strips_order_prefix(name, expected):
    assert _slug(name) == expected


def test_style_rejects_unknown_option():
    with pytest.raises(RenderError):
        Style.from_dict({"backgroundd": "#fff"})


def test_style_accepts_single_color_string():
    assert Style.from_dict({"background": "#ffffff"}).background == ["#ffffff"]


def test_bad_color_is_reported():
    with pytest.raises(RenderError):
        make_background((4, 4), ["nonsense"])


def test_solid_and_gradient_backgrounds():
    solid = make_background((8, 8), ["#ff0000"])
    assert solid.getpixel((0, 0)) == solid.getpixel((7, 7)) == (255, 0, 0)

    grad = make_background((8, 64), ["#000000", "#ffffff"])
    assert grad.getpixel((0, 0))[0] < grad.getpixel((0, 63))[0]


# --- composition -----------------------------------------------------------


@pytest.fixture
def shot(tmp_path: Path) -> Path:
    path = tmp_path / "raw.png"
    Image.new("RGB", (1179, 2556), (200, 40, 40)).save(path)
    return path


def test_compose_hits_the_exact_target_size(shot):
    out = compose(shot, (1320, 2868), Style(), "Hello")
    assert out.size == (1320, 2868)
    assert out.mode == "RGB"


def test_banner_needs_no_screenshot():
    out = compose(None, (1024, 500), Style(), "Tagline")
    assert out.size == (1024, 500)


def test_impossible_layout_is_reported(shot):
    with pytest.raises(RenderError):
        compose(shot, (1320, 2868), Style(padding=0.6), "Hello")


def test_missing_source_is_reported(tmp_path):
    with pytest.raises(RenderError):
        compose(tmp_path / "absent.png", (600, 800), Style())


def test_saved_output_has_no_alpha(tmp_path, shot):
    out = tmp_path / "out.png"
    save(compose(shot, (600, 1200), Style(), "x"), out)
    # Stores reject alpha channels outright.
    assert Image.open(out).mode == "RGB"


# --- end to end ------------------------------------------------------------


def test_build_writes_every_target(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "raw").mkdir()
    for name in ("01-home.png", "02-search.png"):
        Image.new("RGB", (1179, 2556), (30, 30, 30)).save(tmp_path / "raw" / name)

    (tmp_path / "storeshot.yaml").write_text(
        "input: raw\n"
        "output: out\n"
        "targets: [ios-6.9, play-phone, play-feature]\n"
        "feature_caption: Tagline\n"
        "screens:\n"
        "  - file: 01-home.png\n"
        "    caption: One\n"
        "  - file: 02-search.png\n"
        "    caption: Two\n",
        encoding="utf-8",
    )

    assert main(["build"]) == 0
    assert Image.open(tmp_path / "out/ios-6.9/01-home.png").size == (1320, 2868)
    assert Image.open(tmp_path / "out/play-phone/02-search.png").size == (1080, 1920)
    assert Image.open(tmp_path / "out/play-feature/feature.png").size == (1024, 500)


def test_build_names_missing_files(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "raw").mkdir()
    (tmp_path / "storeshot.yaml").write_text(
        "targets: [play-phone]\nscreens:\n  - file: gone.png\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit) as exc:
        main(["build"])
    assert "gone.png" in str(exc.value)


def test_init_refuses_to_clobber(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert main(["init"]) == 1
    assert main(["init", "--force"]) == 0
