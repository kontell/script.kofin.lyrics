"""This addon's own lyrics window, for skins that draw none themselves.

Owning the window means the list can be driven directly with selectItem
rather than through the Control.SetFocus builtin a skin's list needs.
"""

from typing import Any, List, Optional

import xbmcgui

LIST_ID = 100
PANEL_ID = 101
TITLE_ID = 102
XML_FILENAME = "script-kofin-lyrics.xml"

# The panel as authored, and how narrow it may shrink to.
FULL_WIDTH = 800
MIN_WIDTH = 300
# The list is authored 600 wide inside a 640 panel, its text centred.
LIST_WIDTH = 760
LIST_LEFT = 20

# Nothing in Kodi measures rendered text, so line length is estimated from
# character count. Deliberately generous: over-estimating only costs a panel
# wider than it needed to be, and the width is clamped anyway, while
# under-estimating cuts the words off.
CHAR_WIDTH = 20
PADDING = 80

ACTION_PARENT_DIR = 9
ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
CLOSE_ACTIONS = (ACTION_PARENT_DIR, ACTION_PREVIOUS_MENU, ACTION_NAV_BACK)

# Actions that mean the viewer took the list over. Following stands down until
# the next song rather than fighting them for the scroll position.
SCROLL_ACTIONS = (3, 4, 5, 6, 104, 105, 111, 112)


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

    def onInit(self) -> None:
        try:
            self._list = self.getControl(LIST_ID)
        except Exception:  # pragma: no cover - window torn down mid-init
            self._list = None
            return
        for line in self._lines:
            # A blank line still occupies a row: lines are addressed by index,
            # so dropping empties would shift every line after one.
            self._list.addItem(xbmcgui.ListItem(line or " ", offscreen=True))
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
        self.fit_to(self._lines)

    def fit_to(self, lines: List[str]) -> None:
        """Shrink the panel to the longest line, never past the authored width.

        Only the panel and the two controls move: the list keeps its authored
        width because an <itemlayout> cannot be resized at runtime, so the text
        would stop being centred if it did. Instead the list is shifted so its
        centre stays on the panel's centre, and its overhang is harmless --
        the lines are shorter than the panel by construction.
        """
        if self._list is None:
            return
        longest = max((len(line) for line in lines), default=0)
        width = min(FULL_WIDTH, max(MIN_WIDTH, longest * CHAR_WIDTH + PADDING))
        if width >= FULL_WIDTH:
            return
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
            self._list.setPosition(LIST_LEFT + left // 2, 60)
        except Exception:  # pragma: no cover - window torn down under us
            pass

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
