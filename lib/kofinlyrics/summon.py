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
    # Always through the service, never straight to SetFocus from here. A
    # skin's lyrics button closes its OSD in the same click, and the builtins
    # do not wait for each other -- focusing from this process targets the OSD
    # that is still up, so the focus never reaches the list. By the next
    # service tick the OSD has gone.
    #
    # Timestamped so a second press is a distinct event rather than a no-op
    # against a flag that is already raised.
    xbmcgui.Window(source.HOME_WINDOW).setProperty(PROP_SUMMON, str(time.time()))
