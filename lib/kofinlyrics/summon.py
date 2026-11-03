"""What a skin's lyrics button runs.

It runs in its own interpreter, so it only raises a property for the service
to act on.
"""

import time

import xbmc
import xbmcgui

from kofinlyrics import lyrics as source

PROP_SUMMON = "kofin.lyric.summon"


def summon() -> None:
    if not source.has_lyrics():
        xbmc.log("[kofin-lyrics] summoned with no lyrics to show", xbmc.LOGDEBUG)
        return
    # Left to the service's next tick: the button also closes the OSD, which
    # is still up for anything done from here. Timestamped so a second press
    # still counts.
    xbmcgui.Window(source.HOME_WINDOW).setProperty(PROP_SUMMON, str(time.time()))
