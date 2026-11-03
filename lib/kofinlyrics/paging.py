"""How far ahead of the sung line to drag a list, so it settles mid-view.

Presenter._position_list selects a line ``lead`` rows past the sung one,
which scrolls that line onto the bottom row of the list's page, then selects
the sung line back -- landing it ``lead`` rows above the page's bottom
without moving the view again. The lead therefore has to be counted against
the page the list really scrolls by, and Kodi changed what that is for a list
resized at runtime, as both lists here are, to the height setting:

* Up to 22.0 beta 2 a resized list keeps the page it was authored with. Cut
  to 6 visible rows, it still scrolls as though all 12 were there, and the
  rows past the sixth are clipped (verified live on 21.3).
* From 22.0 RC1 the page is recalculated from the new height (xbmc
  0de2f89359, "Refresh page size after transformed layout"), so it is exactly
  the rows on screen.

Counting against the authored page on RC1 overshoots the shorter real one.
The sung line then falls before the page, and Kodi's rule for that puts it on
the top row -- every line change scrolling four rows on and three back, which
Kodi's scroll correction renders as a two-row jump and a backward glide
(verified on 22.0 RC1).
"""

import functools
from typing import Optional, Tuple

import xbmc

# The first build whose resized lists recalculate their page: 22.0 RC1. Master
# nightlies from the five days between that version bump and the change
# landing report it without having it; nothing current does.
PAGE_FOLLOWS_HEIGHT_FROM = (21, 90, 901)


def _version_code(text: str) -> Optional[Tuple[int, int, int]]:
    """System.BuildVersionCode ("21.90.901") as a tuple, or None."""
    parts = text.strip().split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return int(parts[0]), int(parts[1]), int(parts[2])


@functools.lru_cache(maxsize=None)
def page_follows_height() -> bool:
    """Whether a list resized at runtime scrolls by its new height.

    Unreadable counts as yes: every build from here on behaves that way.
    """
    code = _version_code(xbmc.getInfoLabel("System.BuildVersionCode"))
    return code is None or code >= PAGE_FOLLOWS_HEIGHT_FROM


def middle_row(visible: int) -> int:
    """The row the sung line settles on: mid-way down ``visible`` rows,
    the upper of the two when there is no single middle."""
    return (visible - 1) // 2


def lead_rows(visible: int, authored: int) -> int:
    """The lead that settles the sung line mid-way down ``visible`` rows.

    ``authored`` is the page the list was written with: what it scrolls by
    when Kodi keeps that page, and equal to ``visible`` anyway when the list
    is at its authored height.
    """
    page = visible if page_follows_height() else authored
    return max(1, (page - 1) - middle_row(visible))
