"""Service entry point: watch playback, keep the lyrics on the beat."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from kofinlyrics.service import run  # noqa: E402

run()
