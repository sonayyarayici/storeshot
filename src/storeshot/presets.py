"""Store screenshot size presets.

Sources of truth (check these if a store changes its requirements):
  Apple  https://developer.apple.com/help/app-store-connect/reference/screenshot-specifications/
  Google https://support.google.com/googleplay/android-developer/answer/9866151

Stores change these from time to time. Rather than waiting for a release,
you can define your own sizes in storeshot.yaml:

    custom_targets:
      my-size: [1290, 2796]
"""

from __future__ import annotations

# name -> (width, height) in pixels, portrait
PRESETS: dict[str, tuple[int, int]] = {
    # --- Apple App Store -------------------------------------------------
    # 6.9" is the size Apple requires for iPhone apps. Apple also accepts
    # 1290x2796 for this class of device.
    "ios-6.9": (1320, 2868),
    "ios-6.9-alt": (1290, 2796),
    "ios-6.5": (1284, 2778),
    "ios-6.3": (1179, 2556),
    "ios-6.1": (1170, 2532),
    "ios-5.5": (1242, 2208),
    # 13" is the size Apple requires for iPad apps.
    "ipad-13": (2064, 2752),
    "ipad-12.9": (2048, 2732),
    "ipad-11": (1668, 2388),
    # --- Google Play -----------------------------------------------------
    # Play accepts a range rather than exact sizes. These are the safe
    # 9:16 defaults that satisfy the "at least 1080px" recommendation.
    "play-phone": (1080, 1920),
    "play-tablet-7": (1200, 1920),
    "play-tablet-10": (1600, 2560),
    # The feature graphic is landscape and has no screenshot inside it;
    # storeshot renders it as a caption on your background.
    "play-feature": (1024, 500),
}

# Targets that are a banner rather than a device screenshot.
BANNER_TARGETS = frozenset({"play-feature"})

# Sensible defaults if the user does not name any targets.
DEFAULT_TARGETS = ("ios-6.9", "ipad-13", "play-phone")


def resolve(name: str, custom: dict[str, list[int]] | None = None) -> tuple[int, int]:
    """Return (width, height) for a target name.

    Custom targets defined in the config win over built-in presets, so a
    user can override a preset that has gone stale without editing code.
    """
    if custom and name in custom:
        size = custom[name]
        if len(size) != 2:
            raise ValueError(f"custom target {name!r} must be [width, height]")
        return int(size[0]), int(size[1])
    if name in PRESETS:
        return PRESETS[name]
    raise KeyError(
        f"unknown target {name!r}. Run 'storeshot presets' to list built-in "
        f"targets, or add it under custom_targets in your config."
    )


def is_banner(name: str) -> bool:
    return name in BANNER_TARGETS
