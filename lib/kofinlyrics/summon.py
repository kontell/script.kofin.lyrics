"""What a skin's lyrics button runs.

The script runs in its own Python instance, so it cannot reach into the
service's window directly. It raises a flag the service picks up on its next
tick -- which is also what makes the button work identically whether a skin is
drawing the lyrics or this addon is.
"""

import time

import xbmc
import xbmcgui

from kofinlyrics import lyrics as source

PROP_SUMMON = "kofin.lyric.summon"


def summon() -> None:
    if not source.has_lyrics():
        xbmc.log("[kofin-lyrics] summoned with no lyrics to show", xbmc.LOGINFO)
        return
    control = source.skin_control_id()
    if control:
        # A skin is drawing: hand it the focus so the viewer can scroll. No
        # round trip through the service needed for that.
        xbmc.executebuiltin("SetFocus(%d)" % control)
        return
    # Timestamped so a second press is a distinct event rather than a no-op
    # against a flag that is already raised.
    xbmcgui.Window(source.HOME_WINDOW).setProperty(PROP_SUMMON, str(time.time()))
