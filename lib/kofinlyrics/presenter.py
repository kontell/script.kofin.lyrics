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

from typing import Callable, List, Optional

import xbmc
import xbmcaddon
import xbmcgui

from kofinlyrics import lyrics as source
from kofinlyrics import settings
from kofinlyrics.window import (
    FULL_HEIGHT,
    FULL_WIDTH,
    XML_FILENAME,
    LyricsWindow,
    estimate_px,
    width_for,
)

ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo("path")

# The visualisation window. The addon's own window is only ever shown here.
WINDOW_VISUALISATION = 12006

# The skin overlay's vertical framing, part of the driving contract a skin
# opts into by publishing kofin.lyric.panel: 60px rows with 20px of combined
# inset above and below the list. The height itself is the user's setting,
# shared with this addon's own window.
SKIN_ROW_HEIGHT = 60
SKIN_VERTICAL_INSET = 20

# Where the size buckets split, as fractions of the addon window's full
# width. Published for skins that draw their own overlay: skin geometry
# cannot bind a property (verified -- an $INFO width renders zero-wide), so
# a skin gets a coarse class to switch authored variants on rather than a
# pixel value it could not use.
NARROW_BELOW = FULL_WIDTH * 45 // 100
WIDE_ABOVE = FULL_WIDTH * 75 // 100


def log(message: str) -> None:
    """Chatty at INFO only when asked; otherwise it stays in the debug log.

    This runs once per song and once per hand-over, which is more than a
    normal log wants from an addon that is working.
    """
    try:
        level = xbmc.LOGINFO if settings.debug() else xbmc.LOGDEBUG
    except Exception:  # never let logging be the thing that fails
        level = xbmc.LOGDEBUG
    xbmc.log("[kofin-lyrics] %s" % message, level)


def _skin_list_position(control: int) -> int:
    """Which line a skin's list is on, or -1 if it cannot be read.

    CurrentItem, not Position: on a fixedlist Position is the pinned cursor
    row and never moves. And it counts from one.
    """
    try:
        return int(xbmc.getInfoLabel("Container(%d).CurrentItem" % control)) - 1
    except (TypeError, ValueError):
        return -1


def _size_bucket(lines: List[source.LyricLine]) -> str:
    """The coarse width class of a song, for skins to switch variants on."""
    widest = max((estimate_px(text) for _, text in lines if text.strip()), default=0)
    width = width_for(widest)
    if width <= NARROW_BELOW:
        return "narrow"
    if width >= WIDE_ABOVE:
        return "wide"
    return "medium"


def _skin_rows(height: int) -> int:
    return max(3, (height - SKIN_VERTICAL_INSET) // SKIN_ROW_HEIGHT)


class Presenter:
    """Owns whichever surface is showing the current song's lyrics."""

    def __init__(self) -> None:
        self._lines: List[source.LyricLine] = []
        self._window: Optional[LyricsWindow] = None
        self._sent: Optional[int] = None
        self._following = False
        # Our own window has taken over from a skin's overlay for scrolling.
        self._interactive = False
        # The skin overlay needs its geometry (re)applied: at each new song,
        # and whenever its window reloaded -- a reload rebuilds the controls
        # at their authored size, which silently discards anything set.
        self._skin_stale = True

    # -- lifecycle ----------------------------------------------------------

    def start_song(self) -> None:
        """Take up whatever kofin has published for the song now playing.

        An open window is refilled rather than closed and reopened: it is the
        same panel showing the next track, and tearing it down between songs
        made it flash out and back on every change.
        """
        lines = source.published_lines()
        if not lines:
            self.stop_song()
            return
        timed = source.is_timed(lines)
        if not timed and not settings.show_untimed():
            log("%d lines, but untimed lyrics are turned off" % len(lines))
            self.stop_song()
            return
        self._lines = lines
        self._following = timed
        self._sent = None
        self._skin_stale = True
        source.set_size(_size_bucket(lines))
        if self._window is not None and not self._window.closed:
            self._window.set_target_height(settings.window_height())
            self._window.set_lines([text for _, text in lines])
        source.set_show(True)
        log("%d lines%s" % (len(lines), "" if timed else " (untimed)"))

    def stop_song(self) -> None:
        source.set_show(False)
        source.set_size(None)
        self._leave_interactive()
        self._close_window()
        self._lines = []
        self._sent = None
        self._following = False

    def summon(self) -> None:
        """Hand the lyrics to the viewer to scroll.

        A skin's overlay cannot take the arrow keys however it is focused:
        Kodi's keymap binds them to StepBack/SkipNext for the whole
        visualisation window, so they never reach a control. Only a window of
        our own gets ordinary navigation -- so that is what scrolling means
        here, with the skin's overlay standing aside while it is up.
        """
        if not self._lines:
            # Nothing taken up yet -- showAutomatically is off, or the viewer
            # dismissed the window earlier in this song. Take them up now and
            # carry straight on into the hand-over: one press, lyrics you can
            # scroll.
            self.start_song()
            if not self._lines:
                return
        if source.skin_control_id() and not self._interactive:
            self._interactive = True
            source.set_interactive(True)
            self._sent = None
            log("handing over to our own window for scrolling")
            return
        if self._window is None or self._window.closed:
            self._window = None
            self._sent = None
            self._lines = source.published_lines()

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
        control = 0 if self._interactive else source.skin_control_id()

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
        """Keep a skin's list on the line being sung.

        Nothing here watches for the viewer scrolling, because in a skin's
        list they cannot: Kodi's keymap spends the arrow keys on
        StepBack/SkipNext for the whole visualisation window, so they never
        reach the control. Scrolling by hand is what the interactive window is
        for.

        That makes any divergence ours to correct rather than theirs to keep,
        so this re-asserts instead of standing down. Three separate bugs came
        from the older reading -- the OSD, a hidden overlay and an unloaded
        list each moved the position somewhere we had not put it, and each
        looked exactly like a manual scroll.
        """
        where = _skin_list_position(control)
        if where < 0:
            # Not addressable. Container(...) resolves against the active
            # window, so while the OSD is up the list cannot be read -- and
            # must not be written either: Control.SetFocus acts on the active
            # window too, so driving here fires it into the OSD every tick and
            # takes the focus off whatever the viewer is using.
            #
            # It also cannot be *seen*: whatever geometry we pushed may be
            # gone by the time it is back, so it is pushed again then.
            self._skin_stale = True
            return
        if self._skin_stale and self._apply_skin_geometry(control):
            self._skin_stale = False
        if not self._following:
            return
        active = self._active(position)
        if active is None:
            return
        if active == self._sent and where == active:
            return
        self._sent = active
        rows = _skin_rows(settings.window_height())
        self._position_list(
            lambda index: xbmc.executebuiltin(
                # absolute: without it the position is taken relative to the
                # visible page, which lands on a different line every time the
                # list scrolls.
                "Control.SetFocus(%d,%d,absolute)"
                % (control, index)
            ),
            active,
            max(1, (rows - 1) // 2),
        )

    def _apply_skin_geometry(self, control: int) -> bool:
        """Push the user's height onto the skin's overlay, if it opted in.

        Skin XML cannot read geometry from a property, so exact pixel heights
        have to be written onto the skin's controls from here. A skin opts in
        by publishing its backdrop ids as kofin.lyric.panel; without them
        nothing is touched, and at the full height there is nothing to say.

        One Window wrapper per application, not per tick: constructing
        wrappers on a live window at polling rate has crashed Kodi.
        """
        height = settings.window_height()
        panel_ids = source.skin_panel_ids()
        if not panel_ids or height >= FULL_HEIGHT:
            return True
        try:
            visualisation = xbmcgui.Window(WINDOW_VISUALISATION)
            for panel_id in panel_ids:
                visualisation.getControl(panel_id).setHeight(height)
            visualisation.getControl(control).setHeight(
                _skin_rows(height) * SKIN_ROW_HEIGHT
            )
            log("skin overlay height set to %d" % height)
            return True
        except Exception:
            # Mid-reload; stays stale and is pushed again next tick.
            return False

    # -- driving our own window ---------------------------------------------

    def _drive_window(self, position: Optional[float]) -> None:
        if self._window is None:
            self._open_window()
        if self._window is None:
            return
        if self._window.closed:
            window = self._window
            self._window = None
            if not window.dismissed:
                # Kodi closed it out from under us -- observed live, closer
                # unidentified. Not the viewer's doing, so reopen with the
                # same song rather than standing down.
                self._sent = None
                log("window closed out from under us; reopening")
            elif self._interactive:
                # Handed back: the skin's overlay draws again, following the
                # music once more.
                self._leave_interactive()
                self._following = source.is_timed(self._lines)
                self._sent = None
            else:
                self._lines = []  # dismissed; leave it shut for this song
            return
        # Fitting the panel to the measured lines happens out here rather
        # than in the window's own onInit: measuring pumps callbacks, and a
        # callback is no place to pump from. A no-op once it has landed.
        self._window.refit()
        if not self._following or self._window.scrolled:
            return
        active = self._active(position)
        if active is None or active == self._sent:
            return
        self._sent = active
        window = self._window
        self._position_list(window.highlight, active, window.lead_rows())

    def _open_window(self) -> None:
        try:
            window = LyricsWindow(
                XML_FILENAME,
                ADDON_PATH,
                "default",
                "1080i",
                lines=[text for _, text in self._lines],
                height=settings.window_height(),
            )
            window.show()
            self._window = window
            self._sent = None
        except Exception as error:  # pragma: no cover - defensive
            log("could not open the lyrics window: %s" % error)
            self._window = None

    def _leave_interactive(self) -> None:
        if self._interactive:
            self._interactive = False
            source.set_interactive(False)

    def _close_window(self) -> None:
        if self._window is not None:
            self._window.close()
            self._window = None

    # -- shared -------------------------------------------------------------

    @staticmethod
    def _position_list(select: Callable[[int], None], active: int, lead: int) -> None:
        """Put ``active`` on the list, sitting mid-panel once it gets there.

        A list only scrolls when the cursor reaches the edge of the view, so
        selecting the sung line alone walks the cursor from the top down to
        the *bottom* row and scrolls from there -- the line ends up at the
        foot of the panel rather than the middle.

        Selecting a line ``lead`` further on first drags the view down so that
        line sits at the bottom, which leaves the sung line ``lead`` rows above
        it; putting the cursor back on it then moves no view, because it is
        already showing. Early in a track neither selection scrolls anything,
        so the cursor simply walks down from the top, which is what we want
        there.
        """
        select(active + lead)
        select(active)

    def _active(self, position: Optional[float]) -> Optional[int]:
        """Which line to sit on, or None when there is nothing to follow.

        Before the first stamped line there is no line playing, but leaving
        the list unselected shows a panel with nothing picked out at all. The
        first line is the one about to be sung, so it waits there.
        """
        if position is None:
            return None
        active = source.active_index(self._lines, position - settings.offset())
        if active is None and self._following:
            return 0
        return active
