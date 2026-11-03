"""Script entry point: what a skin's lyrics button runs."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from kofinlyrics.summon import summon  # noqa: E402

summon()
