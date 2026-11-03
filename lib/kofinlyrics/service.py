"""The service loop: follow playback and feed the presenter.

It waits in waitForAbort, which is also what delivers the lyrics window's
callbacks.
"""

from typing import Optional

import xbmc
import xbmcgui

from kofinlyrics import lyrics as source
from kofinlyrics import settings
from kofinlyrics.presenter import Presenter, log
from kofinlyrics.summon import PROP_SUMMON

TICK_SECONDS = 0.25

# Kofin clears its lyrics between songs, so a few empty ticks are expected.
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
    # The published path carries the song id, so it changes with every song.
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
                # A new song. When it is not shown automatically, the last
                # song's lyrics still have to go.
                if settings.show_automatically():
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
    presenter = Presenter(monitor)
    log("service started")
    try:
        _loop(monitor, presenter)
    except Exception as error:  # pragma: no cover - defensive
        log("service loop failed: %s" % error)
    finally:
        # The window has to go: one left open pins Kodi's UI to it.
        try:
            presenter.close()
        except Exception:
            pass
    log("service stopped")
