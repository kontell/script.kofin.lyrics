"""The service loop: follow playback and keep the presenter fed.

Kofin publishes a song's lyrics at playback start -- it holds the Jellyfin
session and gets there before anything else can. This addon waits for that
publication and decides where to draw it.

The cadence is Kodi-aware (``waitForAbort``, not ``Event.wait``): while this
addon's own window is up, the loop has to yield to Kodi between ticks or the
window's callbacks are never delivered.
"""

from typing import Optional

import xbmc
import xbmcgui

from kofinlyrics import lyrics as source
from kofinlyrics.presenter import Presenter, log
from kofinlyrics.summon import PROP_SUMMON

TICK_SECONDS = 0.25



def _position() -> Optional[float]:
    try:
        return float(xbmc.Player().getTime())
    except (RuntimeError, ValueError):
        return None  # not playing, or playback ended under us


def _take_summons() -> bool:
    """Whether the script entry point asked for the lyrics to be brought up."""
    window = xbmcgui.Window(source.HOME_WINDOW)
    if not window.getProperty(PROP_SUMMON):
        return False
    window.clearProperty(PROP_SUMMON)
    return True


def run() -> None:
    monitor = xbmc.Monitor()
    presenter = Presenter()
    # The published path carries the song id, so it is what tells one song's
    # lyrics from the next. A flag would not: kofin clears and republishes
    # within a single tick on a track change, so "has lyrics" never goes false
    # in between and stale lines would sit there for the whole next song.
    showing = ""
    log("service started")

    while not monitor.abortRequested():
        try:
            audio = xbmc.Player().isPlayingAudio()

            published = source.directory_path() if source.has_lyrics() else ""

            if not audio or not published:
                if showing:
                    presenter.stop_song()
                    showing = ""
            elif published != showing:
                # A song we have not taken up yet, or a new one.
                presenter.start_song()
                showing = published
            else:
                if _take_summons():
                    # The viewer asked for the lyrics back after closing them;
                    # re-adopt so the window reopens.
                    presenter.start_song()
                presenter.tick(_position())
        except Exception as error:  # never let a tick kill the service
            log("tick failed: %s" % error)

        if monitor.waitForAbort(TICK_SECONDS):
            break

    presenter.close()
    log("service stopped")
