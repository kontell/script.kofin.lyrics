"""Addon settings, read fresh each time.

A new Addon() per read rather than one held at import: Kodi caches settings
per instance, so a long-lived service would go on using whatever was set when
it started.

Nothing here raises. During addon teardown xbmcaddon.Addon() throws
"Unknown addon id", and these are read from the service loop -- including from
its own exception handler, by way of log(). A throw there killed the loop
before it could close its window, which left the window registered and pinned
the whole UI to it, recoverable only by restarting Kodi. A settings read is
never worth that, so a failed one is just the default.
"""

from typing import Any

import xbmcaddon

DEFAULTS = {
    "showAutomatically": True,
    "showUntimed": True,
    "offset": 0.0,
    "debug": False,
}


def _get(setting_id: str, reader: str) -> Any:
    try:
        return getattr(xbmcaddon.Addon(), reader)(setting_id)
    except Exception:
        return DEFAULTS[setting_id]


def show_automatically() -> bool:
    """Whether lyrics come up on their own, or wait to be asked for."""
    return bool(_get("showAutomatically", "getSettingBool"))


def show_untimed() -> bool:
    """Whether lyrics with no timings are worth showing.

    They cannot follow the music, so they sit there as a block that never
    moves -- which some would rather not have on screen at all.
    """
    return bool(_get("showUntimed", "getSettingBool"))


def offset() -> float:
    """Seconds to shift the timings by; positive means the lines come later.

    Server-side .lrc files are routinely a beat out from the recording they
    were matched to.
    """
    try:
        return float(_get("offset", "getSettingNumber"))
    except (TypeError, ValueError):
        return 0.0


def debug() -> bool:
    return bool(_get("debug", "getSettingBool"))
