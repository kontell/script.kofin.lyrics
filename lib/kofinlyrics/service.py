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
from kofinlyrics import settings
from kofinlyrics.presenter import Presenter, log
from kofinlyrics.summon import PROP_SUMMON

TICK_SECONDS = 0.25

# Kofin clears the published lyrics before it publishes the next song's, so
# there is always a moment mid-track-change with nothing there. Tearing down on
# the first empty tick closed the window between every pair of songs. Wait a
# few ticks before believing it: a song genuinely without lyrics only costs
# this long showing the previous one's.
EMPTY_TICKS_BEFORE_STOP = 12


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


def _loop(monitor: xbmc.Monitor, presenter: Presenter) -> None:
    # The published path carries the song id, so it is what tells one song's
    # lyrics from the next. A flag would not: kofin clears and republishes
    # within a single tick on a track change, so "has lyrics" never goes false
    # in between and stale lines would sit there for the whole next song.
    showing = ""
    empty_ticks = 0

    while not monitor.abortRequested():
        try:
            audio = xbmc.Player().isPlayingAudio()
            published = source.directory_path() if source.has_lyrics() else ""

            if not audio:
                if showing:
                    presenter.stop_song()
                    showing = ""
                empty_ticks = 0
            elif not published:
                empty_ticks += 1
                if showing and empty_ticks >= EMPTY_TICKS_BEFORE_STOP:
                    presenter.stop_song()
                    showing = ""
            elif published != showing:
                empty_ticks = 0
                # A song we have not taken up yet, or a new one. With
                # showAutomatically off nothing is taken up until the lyrics
                # button asks for it -- but the song still has to be noticed,
                # or the previous one's lines would linger.
                if settings.show_automatically():
                    # start_song refills an open window rather than closing
                    # it, so the panel carries across the track change instead
                    # of flashing out and back.
                    presenter.start_song()
                else:
                    presenter.stop_song()
                showing = published
            else:
                empty_ticks = 0
                if _take_summons():
                    presenter.summon()
                presenter.tick(_position())
        except Exception as error:  # never let a tick kill the service
            log("tick failed: %s" % error)

        if monitor.waitForAbort(TICK_SECONDS):
            break


def run() -> None:
    monitor = xbmc.Monitor()
    presenter = Presenter()
    log("service started")
    try:
        _loop(monitor, presenter)
    except Exception as error:  # pragma: no cover - defensive
        log("service loop failed: %s" % error)
    finally:
        # Whatever happened above, the window has to go. One left registered
        # pins the whole UI to it until Kodi is restarted -- which is what
        # made a settings read throwing during teardown so expensive.
        try:
            presenter.close()
        except Exception:
            pass
    log("service stopped")
