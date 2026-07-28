"""Script entry point -- what a skin's lyrics button runs.

The service already shows lyrics on its own, so this exists to bring them to
the front on demand: it focuses the skin's list when a skin is drawing, and
otherwise asks the service to (re)open this addon's window.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from kofinlyrics.summon import summon  # noqa: E402

summon()
