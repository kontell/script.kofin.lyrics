"""Split the English source into what gets translated and what is copied.

PASSTHROUGH is the do-not-translate allowlist: ids that are nothing but a
technical token or a product name, where a translation is the defect rather
than the feature. The generator supplies msgstr == msgid for these, so they
never appear in a tr/<locale>.json and a translator is never asked about them.

Run this to get the worklist:

    python3 tools/i18n/classify.py            # counts to stderr, worklist to stdout
"""

import sys
from typing import Set

from po_lib import parse_entries

# Empty: every string this add-on has is words.
PASSTHROUGH: Set[str] = set()


def main():
    entries = parse_entries()
    ctxs = {e["ctx"] for e in entries}
    dangling = sorted(c for c in PASSTHROUGH if c not in ctxs)
    if dangling:
        raise SystemExit(
            "PASSTHROUGH ids no longer in the source (renumbered or removed): %s"
            % ", ".join(dangling)
        )
    work = [e for e in entries if e["ctx"] not in PASSTHROUGH]
    print(
        "# translatable: %d   passthrough: %d   total: %d"
        % (len(work), len(PASSTHROUGH), len(entries)),
        file=sys.stderr,
    )
    for e in work:
        print("%s\t%s" % (e["ctx"], e["msgid"]))


if __name__ == "__main__":
    main()
