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
"""

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
# The inset of the list and the title inside the panel, on both sides.
LIST_LEFT = 20
# Air between the widest line and the panel edges, shared between both sides.
PADDING = 80

# How long the renderer gets to show a measure line before it is read. Not a
# poll: reading is what spends the label, so there is exactly one read.
SETTLE_MS = 400
# Measurement rounds that come back empty before a track keeps the estimate.
PROBE_ATTEMPTS = 3

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


def _estimate(line: str) -> int:
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


class LyricsWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Taken here rather than through a setter after show(): onInit runs on
        # Kodi's thread some time after show() returns, so anything written to
        # the controls before then lands on a window that does not exist yet.
        self._lines: List[str] = list(kwargs.pop("lines", []))
        super().__init__(*args)
        self.closed = False
        self.scrolled = False
        self._list: Optional[xbmcgui.ControlList] = None
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
        for line in self._lines:
            # A blank line still occupies a row: lines are addressed by index,
            # so dropping empties would shift every line after one.
            self._list.addItem(xbmcgui.ListItem(line or " ", offscreen=True))
        # The estimate only: measuring waits on the renderer, and waiting is
        # exactly what a callback must not do. The service loop's next
        # refit() replaces it.
        self.fit_to(self._lines)

    def set_lines(self, lines: List[str]) -> None:
        """Replace the lines in an already-open window, for the next track."""
        self._lines = list(lines)
        if self._list is None:
            return
        self._list.reset()
        for line in self._lines:
            self._list.addItem(xbmcgui.ListItem(line or " ", offscreen=True))
        self.scrolled = False
        self._measured = False
        self._probe_attempts = 0
        self.fit_to(self._lines)
        # Called from the service thread, so the measurement can happen right
        # here rather than waiting a tick.
        self.refit()

    def fit_to(self, lines: List[str]) -> None:
        """Fit the panel to the estimated widest line, immediately.

        Safe from onInit -- pure arithmetic and control writes, nothing that
        waits. The estimate errs by glyph mix, so this is only the width
        shown until refit() measures the truth.
        """
        if self._list is None:
            return
        widest = max((_estimate(line) for line in lines if line.strip()), default=0)
        self._apply_width(widest)

    def refit(self) -> None:
        """Measure the widest line on the live skin font and fit to it.

        The service loop calls this every tick; it is a no-op once measured.
        The measure labels in script-kofin-lyrics.xml have <width>auto</width>,
        so the renderer sizes them to whatever text PROP_MEASURE holds -- the
        one true answer for whichever font the active skin resolves, where
        any estimate from character counts is wrong per skin, per font and
        per glyph.
        """
        if self._list is None or self.closed or self._measured:
            return
        self._probe_attempts += 1
        measured = self._measure_longest(self._lines)
        if measured is None:
            if self._probe_attempts >= PROBE_ATTEMPTS:
                self._measured = True  # the estimate stands for this track
            return
        self._measured = True
        self._apply_width(measured)

    def _apply_width(self, longest_px: int) -> None:
        """Size the panel to a widest-line width, never past the authored one.

        Only the panel and the two controls move: the list keeps its authored
        width because an <itemlayout> cannot be resized at runtime, so the text
        would stop being centred if it did. Instead the list is shifted so its
        centre stays on the panel's centre. No text escapes the panel: below
        the clamp the widest line is PADDING narrower than the panel, and at
        the clamp anything wider than the item layout's 1200 is clipped (and
        scrolled) by the label, which sits inside the full-width panel.

        Written unconditionally, including at the full width, because the
        window is refilled across track changes rather than reopened. Returning
        early once the lines no longer need shrinking left the *previous*
        track's narrow panel in place: the list is re-centred on the panel, so
        the next track's longer lines drew centred on a panel 500 too far left
        and ran off the right of the screen, clipped and unbacked. At the full
        width the arithmetic below reproduces the authored geometry exactly.
        """
        width = min(FULL_WIDTH, max(MIN_WIDTH, longest_px + PADDING))
        left = FULL_WIDTH - width  # right edge stays where it was authored
        try:
            panel = self.getControl(PANEL_ID)
            panel.setWidth(width)
            panel.setPosition(left, 0)
            title = self.getControl(TITLE_ID)
            title.setWidth(width - 2 * LIST_LEFT)
            title.setPosition(left + LIST_LEFT, 10)
            # Half the shrink: the list's text centres on its own authored
            # width, so moving it half way keeps that centre on the panel's.
            if self._list is not None:
                self._list.setPosition(LIST_LEFT + left // 2, 60)
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
            # Torn down under us mid-probe; the estimate is already up.
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
            {line for line in lines if line.strip()}, key=_estimate, reverse=True
        )
        if not unique:
            return []
        floor = _estimate(unique[0]) * 85 // 100
        return [line for line in unique[:3] if _estimate(line) >= floor]

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
        if self._list is None or self.scrolled:
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
            self.close()
        elif action_id in SCROLL_ACTIONS:
            self.scrolled = True
