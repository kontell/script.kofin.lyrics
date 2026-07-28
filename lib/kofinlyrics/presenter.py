"""Deciding where lyrics get drawn, and keeping them on the beat.

Two ways to show the same lines:

* A skin that draws lyrics itself declares the list control it wants driven
  (``kofin.lyric.control``). We fill nothing and only move the highlight,
  because the skin's control belongs to the window that is already active --
  it takes no input and blocks nothing.
* Any other skin gets this addon's own window, the way CU LRC Lyrics works.
  That window *is* the active window while it is up, so it is opened only over
  the visualisation screen, where there is nothing else to navigate.

Following stands down the moment the viewer scrolls for themselves, and the
next song takes it back.
"""

from typing import List, Optional

import xbmc
import xbmcaddon

from kofinlyrics import lyrics as source
from kofinlyrics.window import XML_FILENAME, LyricsWindow

ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo("path")

# The visualisation window. The addon's own window is only ever shown here.
WINDOW_VISUALISATION = 12006


def log(message: str) -> None:
    xbmc.log("[kofin-lyrics] %s" % message, xbmc.LOGINFO)


def _skin_list_position(control: int) -> int:
    """Which line a skin's list is on, or -1 if it cannot be read.

    CurrentItem, not Position: on a fixedlist Position is the pinned cursor
    row and never moves. And it counts from one.
    """
    try:
        return int(xbmc.getInfoLabel("Container(%d).CurrentItem" % control)) - 1
    except (TypeError, ValueError):
        return -1


class Presenter:
    """Owns whichever surface is showing the current song's lyrics."""

    def __init__(self) -> None:
        self._lines: List[source.LyricLine] = []
        self._window: Optional[LyricsWindow] = None
        self._sent: Optional[int] = None
        self._following = False
        self._confirmed = False

    # -- lifecycle ----------------------------------------------------------

    def start_song(self) -> None:
        """Take up whatever kofin has published for the song now playing."""
        self.stop_song()
        lines = source.published_lines()
        if not lines:
            return
        self._lines = lines
        self._following = source.is_timed(lines)
        self._sent = None
        self._confirmed = False
        log("%d lines%s" % (len(lines), "" if self._following else " (untimed)"))

    def stop_song(self) -> None:
        self._close_window()
        self._lines = []
        self._sent = None
        self._following = False
        self._confirmed = False

    def summon(self) -> None:
        """Bring the lyrics to the front, and hand them to the viewer.

        Deliberately stops following: the only reason to ask for the lyrics
        that are already on screen is to scroll them yourself.
        """
        control = source.skin_control_id()
        if control:
            self._following = False
            xbmc.executebuiltin("SetFocus(%d)" % control)
            log("handed the skin's list to the viewer")
            return
        if self._window is None or self._window.closed:
            self._window = None
            self.start_song()
        elif self._window is not None:
            self._window.scrolled = True

    def close(self) -> None:
        self.stop_song()

    # -- the tick -----------------------------------------------------------

    def tick(self, position: Optional[float]) -> None:
        """Called on the service's cadence while a song plays."""
        if not self._lines:
            return

        visualisation = xbmc.getCondVisibility(
            "Window.IsVisible(%d)" % WINDOW_VISUALISATION
        )
        control = source.skin_control_id()

        if control:
            # The skin draws. Our own window must not also be up -- that is the
            # double-render that makes two lyrics addons unusable together.
            self._close_window()
            if visualisation:
                self._drive_skin(control, position)
            return

        if not visualisation:
            # Nowhere safe to put a window of our own.
            self._close_window()
            return
        self._drive_window(position)

    # -- driving a skin's list ----------------------------------------------

    def _drive_skin(self, control: int, position: Optional[float]) -> None:
        if not self._following:
            return
        where = _skin_list_position(control)
        if where < 0:
            # Not readable from here. Container(...) resolves against whatever
            # window is active, so anything over the visualisation screen --
            # the OSD, a dialog -- hides the list from us. Unreadable is not
            # the same as moved: treating it as a manual scroll stood us down
            # for the rest of the song every time the OSD was opened.
            return

        # Until the list has agreed with us once, a mismatch means our command
        # went nowhere -- the directory loads asynchronously, so the opening
        # move usually lands in an empty list. Re-issue rather than read that
        # as the viewer scrolling, which would stand us down for the whole
        # song before the first line ever lit.
        if not self._confirmed:
            if self._sent is not None and where == self._sent:
                self._confirmed = True
        elif self._sent is not None and where != self._sent:
            self._following = False
            log("yielding to manual scroll")
            return

        active = self._active(position)
        if active is None or (active == self._sent and self._confirmed):
            return
        self._sent = active
        # absolute: without it the position is taken relative to the visible
        # page, which lands on a different line every time the list scrolls.
        xbmc.executebuiltin("Control.SetFocus(%d,%d,absolute)" % (control, active))

    # -- driving our own window ---------------------------------------------

    def _drive_window(self, position: Optional[float]) -> None:
        if self._window is None:
            self._open_window()
        if self._window is None:
            return
        if self._window.closed:
            # Dismissed by the viewer; leave it shut for this song.
            self._lines = []
            self._window = None
            return
        if not self._following or self._window.scrolled:
            return
        active = self._active(position)
        if active is None or active == self._sent:
            return
        self._sent = active
        self._window.highlight(active)

    def _open_window(self) -> None:
        try:
            window = LyricsWindow(
                XML_FILENAME,
                ADDON_PATH,
                "default",
                "1080i",
                lines=[text for _, text in self._lines],
            )
            window.show()
            self._window = window
            self._sent = None
        except Exception as error:  # pragma: no cover - defensive
            log("could not open the lyrics window: %s" % error)
            self._window = None

    def _close_window(self) -> None:
        if self._window is not None:
            self._window.close()
            self._window = None

    # -- shared -------------------------------------------------------------

    def _active(self, position: Optional[float]) -> Optional[int]:
        if position is None:
            return None
        return source.active_index(self._lines, position)
