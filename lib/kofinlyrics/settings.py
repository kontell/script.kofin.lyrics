"""Addon settings, read fresh each time.

A new Addon() per read rather than one held at import: Kodi caches settings
per instance, so a long-lived service would go on using whatever was set when
it started.
"""

import xbmcaddon


def _addon() -> xbmcaddon.Addon:
    return xbmcaddon.Addon()


def show_automatically() -> bool:
    """Whether lyrics come up on their own, or wait to be asked for."""
    return _addon().getSettingBool("showAutomatically")


def show_untimed() -> bool:
    """Whether lyrics with no timings are worth showing.

    They cannot follow the music, so they sit there as a block that never
    moves -- which some would rather not have on screen at all.
    """
    return _addon().getSettingBool("showUntimed")


def offset() -> float:
    """Seconds to shift the timings by; positive means the lines come later.

    Server-side .lrc files are routinely a beat out from the recording they
    were matched to.
    """
    try:
        return float(_addon().getSettingNumber("offset"))
    except (TypeError, ValueError):
        return 0.0


def debug() -> bool:
    return _addon().getSettingBool("debug")
