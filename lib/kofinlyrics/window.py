"""This addon's own lyrics window, for skins that draw none themselves.

Owning the window means the list can be driven directly with selectItem
rather than through the Control.SetFocus builtin a skin's list needs.

Everything here runs on the service thread. Window callbacks are not the
exception but the proof: Kodi delivers onInit and onAction *inside* the
owning thread's xbmc.sleep and waitForAbort calls -- makePendingCalls pumps
them -- so a callback is this same thread, re-entered. That is why callbacks
must stay trivial: onInit doing the measurement below re-entered the GUI from
a window still being activated and crashed Kodi outright (SIGSEGV, 21.3).
Measuring therefore happens in refit(), called from the service loop once
the window is up, never from a callback.

One more rule with a crash behind it: every control write checks _alive()
first. Kodi can close this dialog from its own side -- observed in the wild,
closer unidentified -- and a closed WindowXML frees the control tree while
the Python wrappers keep their pointers. A write through one is a
use-after-free that no except can catch (SIGSEGV in Control::setWidth,
21.3).
"""

import math
import time
from typing import Any, List, Optional, cast

import xbmc
import xbmcgui

LIST_ID = 100
PANEL_ID = 101
TITLE_ID = 102
# The pool of hidden auto-width labels the panel is measured with; see
# refit. A pool because each is readable once, ever -- a control wrapper
# copies its geometry out of the live control at the first getControl() made
# for its id and returns that snapshot forever. (A fresh
# xbmcgui.Window(dialog_id) wrapper per read does defeat that cache, but
# constructing wrappers on a live window at polling rate crashed Kodi --
# twice, same site, both threads -- so ids are spent instead.)
MEASURE_ID_FIRST = 3901
MEASURE_ID_LAST = 3940
# A hidden label that exists only to prove a dialog id is ours: fetching it
# through a wrapper on some other dialog raises. Never read for geometry, so
# the one-read-per-id cache does not matter here.
SENTINEL_ID = 3999
XML_FILENAME = "script-kofin-lyrics.xml"

HOME_WINDOW = 10000
# Written by us, read by the measure labels' $INFO binding. On Home rather
# than on this window because a label can only bind a property it can name,
# and this window's id is only known at runtime.
PROP_MEASURE = "kofin.lyric.measure"

# The panel as authored, and how narrow it may shrink to. The authored width
# is the ceiling the measurement can grow the panel to, so it is set for the
# longest lines real songs carry -- a 74-character line renders ~1120px at
# font14, and an 800 ceiling kept every such song clamped with its lines
# truncated. The right edge stays anchored; only the left edge moves.
FULL_WIDTH = 1240
MIN_WIDTH = 300
# The panel as authored vertically, and how short the height setting may
# take it. Top-anchored: the height grows and shrinks at the bottom edge.
FULL_HEIGHT = 800
MIN_HEIGHT = 260
# The inset of the list and the title inside the panel, on both sides.
LIST_LEFT = 20
# Air between the widest line and the panel edges, shared between both sides.
PADDING = 80
# Vertical framing: the title strip above the list, breathing room below,
# and the row height every layout in the XML uses.
TITLE_STRIP = 60
BOTTOM_PAD = 20
ROW_HEIGHT = 60

# How long the renderer gets to show a measure line before it is read. Not a
# poll: reading is what spends the label, so there is exactly one read.
SETTLE_MS = 400
# Measurement rounds that come back empty before a track keeps the estimate.
PROBE_ATTEMPTS = 3

# The resize glide: how the panel moves between songs. Stepped from the
# service thread because it is the only smooth mechanism there is -- skin
# animations cannot be triggered from Python (setVisible ignores
# VisibleChange and setAnimations alike, verified on 21.3), and skin
# geometry cannot bind a property. Positions come from the clock, not a
# step counter: xbmc.sleep pumps pending callbacks, so a step can overrun
# during exactly the busy moments a track change brings, and a counted
# tween fell behind the curve and read as jerky. Differences below the
# snap threshold are applied directly: a glide nobody can see is just
# latency.
TWEEN_MS = 300
TWEEN_STEP_MS = 16
TWEEN_SNAP_PX = 12

# The width put up before the measurement lands, and the fallback if it never
# does: per-glyph-class advances for the stock NotoSans at font14's 33px,
# calibrated against the font file (within ~4% on real lines). Ranking probe
# candidates uses the same numbers, where only the order matters. A single
# chars-times-constant figure cannot do either job -- it was wrong by -40% on
# ordinary lines and +10% on wide-glyph ones at the same time.
_NARROW = set("iljI!.,'|:;()[]\" ")
_WIDE = set("MWmw@%&")
_NARROW_PX = 9
_WIDE_PX = 31
_UPPER_PX = 22
_OTHER_PX = 17

ACTION_PARENT_DIR = 9
ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
CLOSE_ACTIONS = (ACTION_PARENT_DIR, ACTION_PREVIOUS_MENU, ACTION_NAV_BACK)

# Actions that mean the viewer took the list over. Following stands down until
# the next song rather than fighting them for the scroll position.
SCROLL_ACTIONS = (3, 4, 5, 6, 104, 105, 111, 112)


def estimate_px(line: str) -> int:
    """Rendered-width estimate in pixels, for ranking and for fallback."""
    total = 0
    for ch in line:
        if ch in _NARROW:
            total += _NARROW_PX
        elif ch in _WIDE or ord(ch) >= 0x2E80:
            # CJK and everything beyond it is full-width or close to it.
            total += _WIDE_PX
        elif ch.isupper():
            total += _UPPER_PX
        else:
            total += _OTHER_PX
    return total


def width_for(longest_px: int) -> int:
    """Panel width for a widest line, clamped to the authored bounds."""
    return min(FULL_WIDTH, max(MIN_WIDTH, longest_px + PADDING))


def rows_for(height: int) -> int:
    """Whole rows that fit a panel of ``height`` alongside the title strip."""
    return max(3, (height - TITLE_STRIP - BOTTOM_PAD) // ROW_HEIGHT)


# A list resized at runtime keeps the page it was authored with: scrolling
# still treats the view as this many rows, so a selected line rides at the
# bottom of the *authored* page however short the visible list is. Verified
# live -- at 11 visible rows of a 13-row page the sung line sat two rows
# below centre, and shorter than that it left the window entirely. Lead
# arithmetic therefore works in page rows, not visible rows.
PAGE_ROWS = rows_for(FULL_HEIGHT)


class LyricsWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Taken here rather than through a setter after show(): onInit runs on
        # Kodi's thread some time after show() returns, so anything written to
        # the controls before then lands on a window that does not exist yet.
        self._lines: List[str] = list(kwargs.pop("lines", []))
        self._target_height: int = self._clamp_height(
            int(kwargs.pop("height", FULL_HEIGHT))
        )
        super().__init__(*args)
        self.closed = False
        # Distinguishes the viewer closing the window (stay shut for the
        # song) from Kodi closing it out from under us (reopen).
        self.dismissed = False
        self.scrolled = False
        self._list: Optional[xbmcgui.ControlList] = None
        self._window_id: Optional[int] = None
        self._width = 0
        self._height = 0
        self._next_probe = MEASURE_ID_FIRST
        self._measured = False
        self._probe_attempts = 0

    def onInit(self) -> None:
        try:
            # getControl is declared to return the Control base class; LIST_ID
            # addresses the <control type="list"> in script-kofin-lyrics.xml, and
            # addItem/reset/selectItem below already depend on that. The cast
            # states the invariant rather than widening the attribute, so a
            # future LIST_ID pointing at a non-list fails type-checking here
            # instead of at the first addItem on a live window.
            self._list = cast(xbmcgui.ControlList, self.getControl(LIST_ID))
        except Exception:  # pragma: no cover - window torn down mid-init
            self._list = None
            return
        self._fill()
        # The estimate only, applied instantly so it is the width the open
        # fade plays at: measuring waits on the renderer, and waiting is
        # exactly what a callback must not do. The service loop's next
        # refit() glides the few pixels to the measured truth.
        self._fit(self._estimate_width(self._lines))

    def set_lines(self, lines: List[str]) -> None:
        """Replace the lines in an already-open window, for the next track.

        Measured before anything visible moves: the probe labels are
        window-level and know nothing of the list, so the outgoing track
        keeps its panel while the new one is sized. The swap and the resize
        then land together -- one visible change, glided -- where fitting
        the estimate first moved the panel twice per track.
        """
        self._lines = list(lines)
        if self._list is None or not self._alive():
            return
        self.scrolled = False
        self._measured = False
        self._probe_attempts = 0
        measured = self._measure_longest(self._lines)
        if measured is None:
            self._probe_attempts = 1
            width = self._estimate_width(self._lines)
        else:
            self._measured = True
            width = width_for(measured)
        if not self._alive():  # measurement took ~a second; re-check
            return
        self._fill()
        self._tween_to(width)

    def set_target_height(self, height: int) -> None:
        """The user's panel height; applied with the next fit."""
        self._target_height = self._clamp_height(height)

    def refit(self) -> None:
        """Measure the widest line on the live skin font and glide to it.

        The service loop calls this every tick; it is a no-op once measured.
        The measure labels in script-kofin-lyrics.xml have <width>auto</width>,
        so the renderer sizes them to whatever text PROP_MEASURE holds -- the
        one true answer for whichever font the active skin resolves, where
        any estimate from character counts is wrong per skin, per font and
        per glyph.
        """
        if self._list is None or self._measured or not self._alive():
            return
        self._probe_attempts += 1
        measured = self._measure_longest(self._lines)
        if measured is None:
            if self._probe_attempts >= PROBE_ATTEMPTS:
                self._measured = True  # the estimate stands for this track
            return
        self._measured = True
        self._tween_to(width_for(measured))

    def lead_rows(self) -> int:
        """How far below the sung line to drag the view; see the presenter.

        Selecting ``lead`` ahead leaves the sung line that far above the
        *authored* page's bottom row -- the page a runtime-resized list
        still scrolls by -- which lands it mid-way down the rows actually
        visible at the current height.
        """
        visible = rows_for(self._target_height)
        return max(1, (PAGE_ROWS - 1) - (visible - 1) // 2)

    def _fill(self) -> None:
        """Put the current lines on the list, plus a blank tail.

        A blank line still occupies a row: lines are addressed by index, so
        dropping empties would shift every line after one. The lead_rows()
        blanks after the last line let the final sung lines be dragged up to
        the visible middle -- the view scrolls no further than its last row,
        so without them the song's tail could only sit at the bottom of the
        page, which a shortened window clips off entirely.
        """
        if self._list is None:
            return
        self._list.reset()
        for line in self._lines:
            self._list.addItem(xbmcgui.ListItem(line or " ", offscreen=True))
        for _ in range(self.lead_rows()):
            self._list.addItem(xbmcgui.ListItem(" ", offscreen=True))

    # -- liveness ------------------------------------------------------------

    def _alive(self) -> bool:
        """Whether the dialog Kodi holds for us still exists.

        Kodi can close this dialog without close() ever running -- observed
        live, closer unidentified -- and a closed WindowXML frees its control
        tree while our wrappers keep their pointers. The next write through
        one segfaulted Kodi (Control::setWidth, 21.3), so nothing here
        touches a control before asking.

        The id is taken from getCurrentWindowDialogId once, validated by
        fetching the sentinel label through it -- a foreign dialog raises.
        While something else is on top the id cannot be learned; the window
        was shown moments ago, so that counts as alive and discovery retries
        on the next call. Once known, Window.IsVisible answers from Kodi's
        side, repeatably, with no wrapper involved.
        """
        if self.closed:
            return False
        if self._window_id is None:
            dialog_id = xbmcgui.getCurrentWindowDialogId()
            try:
                xbmcgui.Window(dialog_id).getControl(SENTINEL_ID)
            except Exception:
                return True
            self._window_id = dialog_id
            return True
        if xbmc.getCondVisibility("Window.IsVisible(%d)" % self._window_id):
            return True
        self.closed = True
        return False

    # -- fitting -------------------------------------------------------------

    def _estimate_width(self, lines: List[str]) -> int:
        widest = max((estimate_px(line) for line in lines if line.strip()), default=0)
        return width_for(widest)

    @staticmethod
    def _clamp_height(height: int) -> int:
        return min(FULL_HEIGHT, max(MIN_HEIGHT, height))

    def _tween_to(self, width: int) -> None:
        """Glide the panel's left edge to ``width`` over ~300ms.

        Stepped writes from this thread render as real motion (verified at
        full frame rate on 21.3); there is no GUI-side alternative, because
        Python cannot trigger skin animations and skin geometry cannot bind
        a property. The position for each write comes from the elapsed
        clock, so a sleep stretched by the callback pump lands the next
        write further along the curve instead of behind it -- late, not
        wrong. Each step re-checks _alive() so a window closed mid-glide is
        abandoned, not written to.
        """
        if self._width == 0 or abs(width - self._width) <= TWEEN_SNAP_PX:
            self._fit(width)
            return
        start = self._width
        began = time.monotonic()
        while True:
            if not self._alive():
                return
            part = (time.monotonic() - began) * 1000 / TWEEN_MS
            if part >= 1:
                break
            eased = (1 - math.cos(math.pi * part)) / 2
            self._fit(round(start + (width - start) * eased))
            xbmc.sleep(TWEEN_STEP_MS)
        self._fit(width)

    def _fit(self, width: int) -> None:
        """Put the panel at ``width`` and the target height, right-anchored.

        Only the panel and the two controls move: the list keeps its authored
        width because an <itemlayout> cannot be resized at runtime, so the text
        would stop being centred if it did. Instead the list is shifted so its
        centre stays on the panel's centre. No text escapes the panel: below
        the clamp the widest line is PADDING narrower than the panel, and at
        the clamp anything wider than the item layout's 1200 is clipped (and
        scrolled) by the label, which sits inside the full-width panel.

        Written unconditionally, including at the full width, because the
        window is refilled across track changes rather than reopened. At the
        full size the arithmetic reproduces the authored geometry exactly.
        The height is top-anchored -- the panel's bottom edge is what moves --
        and the list shows whole rows only, so the panel keeps the exact
        pixel height the setting asks for while the rows snap underneath.
        """
        height = self._target_height
        left = FULL_WIDTH - width  # right edge stays where it was authored
        self._width = width
        try:
            panel = self.getControl(PANEL_ID)
            panel.setWidth(width)
            panel.setPosition(left, 0)
            title = self.getControl(TITLE_ID)
            title.setWidth(width - 2 * LIST_LEFT)
            title.setPosition(left + LIST_LEFT, 10)
            if self._list is not None:
                # Half the shrink: the list's text centres on its own authored
                # width, so moving it half way keeps that centre on the panel's.
                self._list.setPosition(LIST_LEFT + left // 2, TITLE_STRIP)
            if height != self._height:
                panel.setHeight(height)
                if self._list is not None:
                    self._list.setHeight(rows_for(height) * ROW_HEIGHT)
                self._height = height
        except Exception:  # pragma: no cover - window torn down under us
            pass

    # -- measuring ----------------------------------------------------------

    def _measure_longest(self, lines: List[str]) -> Optional[int]:
        """Rendered width of the widest line, or None if unmeasurable now."""
        candidates = self._candidates(lines)
        if not candidates:
            return 0
        home = xbmcgui.Window(HOME_WINDOW)
        measured = 0
        try:
            for line in candidates:
                width = self._probe(home, line)
                if width is None:
                    return None
                measured = max(measured, width)
                if measured >= FULL_WIDTH - PADDING:
                    # Clamped regardless; a wider runner-up changes nothing.
                    break
        except Exception:
            # Torn down under us mid-probe; the caller falls back.
            return None
        finally:
            try:
                # Collapses every unread label to width 1, which is what
                # makes a premature read detectable -- see _probe.
                home.clearProperty(PROP_MEASURE)
            except Exception:  # pragma: no cover - teardown race
                pass
        return measured

    @staticmethod
    def _candidates(lines: List[str]) -> List[str]:
        """The lines that could plausibly render widest, widest-first.

        The estimate can only mis-rank lines whose real widths are close, so
        probing everything within 15% of the top estimate covers the ranking
        error, and three probes is plenty.
        """
        unique = sorted(
            {line for line in lines if line.strip()}, key=estimate_px, reverse=True
        )
        if not unique:
            return []
        floor = estimate_px(unique[0]) * 85 // 100
        return [line for line in unique[:3] if estimate_px(line) >= floor]

    def _probe(self, home: xbmcgui.Window, line: str) -> Optional[int]:
        """One measurement through the next virgin label, or None.

        Exactly one read: reading is what spends the label, so there is no
        polling -- the renderer gets SETTLE_MS and then the answer is taken.
        Outside a measurement the property is empty and every unspent label
        sits at width 1, so a read of 1 means the renderer had not shown
        this line yet; the id is spent, but the caller retries the round.
        """
        if self._next_probe > MEASURE_ID_LAST:
            return None  # pool exhausted; the estimate stands
        home.setProperty(PROP_MEASURE, line)
        xbmc.sleep(SETTLE_MS)
        cid = self._next_probe
        self._next_probe += 1
        width = self.getControl(cid).getWidth()
        home.setProperty(PROP_MEASURE, "")
        if width <= 1:
            return None
        return width

    # -- driving ------------------------------------------------------------

    def highlight(self, index: int) -> None:
        if self._list is None or self.scrolled or not self._alive():
            return
        try:
            self._list.selectItem(index)
        except Exception:  # pragma: no cover - list emptied under us
            pass

    def close(self) -> None:
        self.closed = True
        try:
            super().close()
        except Exception:  # window already torn down with the player
            pass

    def onAction(self, action: xbmcgui.Action) -> None:
        action_id = action.getId()
        if action_id in CLOSE_ACTIONS:
            self.dismissed = True
            self.close()
        elif action_id in SCROLL_ACTIONS:
            self.scrolled = True
