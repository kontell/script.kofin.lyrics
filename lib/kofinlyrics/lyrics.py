"""Reading the lyrics plugin.video.kofin publishes, and following the clock.

Pure logic, no Kodi imports beyond the window property read, so the line
search is testable on its own. Kofin publishes
``[[start_seconds_or_null, text], ...]`` -- the timings ride along because
deciding which line is current is this addon's job, not kofin's.
"""

import json
from typing import List, Optional, Tuple

import xbmcgui

LyricLine = Tuple[Optional[float], str]

HOME_WINDOW = 10000

# Written by plugin.video.kofin.
PROP_HAS = "kofin.lyric.has"
PROP_JSON = "kofin.lyric.json"
PROP_PATH = "kofin.lyric.path"
# Written by a skin that intends to draw the lyrics itself, naming the list
# control to drive. Its presence is what makes this addon keep its own window
# shut -- see service.py.
PROP_CONTROL = "kofin.lyric.control"
# Written by us, read by the skin: raised while our own window has taken over
# for manual scrolling, so the skin's passive overlay stands aside rather than
# drawing the same lyrics twice.
PROP_INTERACTIVE = "kofin.lyric.interactive"


def _window() -> xbmcgui.Window:
    return xbmcgui.Window(HOME_WINDOW)


def has_lyrics() -> bool:
    return _window().getProperty(PROP_HAS) == "true"


def directory_path() -> str:
    """The plugin path a skin's list is filled from. Carries the song id, so
    it changes per song and Kodi re-reads it."""
    return _window().getProperty(PROP_PATH)


def skin_control_id() -> int:
    """The list control a skin has asked us to drive, or 0 if none has."""
    try:
        return int(_window().getProperty(PROP_CONTROL))
    except (TypeError, ValueError):
        return 0


def set_interactive(active: bool) -> None:
    if active:
        _window().setProperty(PROP_INTERACTIVE, "true")
    else:
        _window().clearProperty(PROP_INTERACTIVE)


def published_lines() -> List[LyricLine]:
    """What kofin published for the playing song."""
    raw = _window().getProperty(PROP_JSON)
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(payload, list):
        return []

    lines: List[LyricLine] = []
    for entry in payload:
        if not isinstance(entry, list) or len(entry) != 2:
            continue
        start, text = entry
        lines.append((float(start) if start is not None else None, str(text)))
    return lines


def is_timed(lines: List[LyricLine]) -> bool:
    """Whether the lyrics carry timings, and so can follow the music."""
    return bool(lines) and lines[0][0] is not None


def active_index(lines: List[LyricLine], position: float) -> Optional[int]:
    """Index of the line playing at ``position`` seconds.

    None when the lyrics carry no timings, or playback has not reached the
    first stamped line -- both mean "nothing to highlight" rather than
    "highlight line zero".

    Searched from the end so repeated stamps resolve to the last line sharing
    the time, which is how a stacked ``[00:12.00]`` pair reads.
    """
    for index in range(len(lines) - 1, -1, -1):
        start = lines[index][0]
        if start is not None and start <= position:
            return index
    return None
