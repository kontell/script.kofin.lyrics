"""This addon's own lyrics window, for skins that draw none themselves.

Owning the window means the list can be driven directly with selectItem
rather than through the Control.SetFocus builtin a skin's list needs.
"""

from typing import Any, List, Optional

import xbmcgui

LIST_ID = 100
XML_FILENAME = "script-kofin-lyrics.xml"

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
