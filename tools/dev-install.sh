#!/bin/bash
# Install the working tree into the local Kodi and (re)load it.
# Usage: tools/dev-install.sh
# Installs what tools/build.py packs, so a new file needs a `git add` first.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/.kodi/addons/script.kofin.lyrics"
KODI_RPC="http://localhost:8080/jsonrpc"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
python3 "$SRC/tools/build.py" "$WORK" > /dev/null
rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
unzip -q "$WORK"/script.kofin.lyrics-*.zip -d "$(dirname "$DEST")"

if ! curl -s -m 2 -u kodi:kodi -o /dev/null "$KODI_RPC" \
        -X POST -H 'Content-Type: application/json' \
        -d '{"jsonrpc":"2.0","id":1,"method":"JSONRPC.Ping"}'; then
    echo "installed to $DEST (Kodi not reachable — skipped reload/enable)"
    exit 0
fi

"$HOME/bin/kodi-builtin" 'UpdateLocalAddons()'
sleep 2
# Disable, then enable: enabling alone does not restart the service.
for state in false true; do
    curl -s -u kodi:kodi -X POST -H 'Content-Type: application/json' \
        -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"Addons.SetAddonEnabled\",\"params\":{\"addonid\":\"script.kofin.lyrics\",\"enabled\":$state}}" \
        "$KODI_RPC" > /dev/null
    sleep 2
done
# Kodi caches strings.po and the window XML until it restarts.
echo "installed and enabled script.kofin.lyrics"
