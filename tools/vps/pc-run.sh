#!/usr/bin/env bash
# The stream from your own computer as a stand-in for the server (when it is off): runs in this
# terminal until Ctrl+C, no service installed. Uses a copy of the repository of its own,
# ~/sejmomat-live (brought up to main first; your working copy is left alone), and the key in
# ~/.config/sejmomat-live.env (asked for and kept on the first run). Waits for the day's sitting
# if it has not begun; after a dropped connection it starts again by itself.
#
#   bash tools/vps/pc-run.sh
set -uo pipefail

REPO=https://github.com/TheBeardedPole/sejmomat.git
DIR="$HOME/sejmomat-live"
ENV="$HOME/.config/sejmomat-live.env"

for c in git python3 ffmpeg; do
    command -v "$c" >/dev/null || { echo "Brakuje programu: $c" >&2; exit 1; }
done
# the service (pc-setup.sh) or the server must not stream at the same time: one key, one stream
if systemctl --user is-active -q sejmomat-live 2>/dev/null; then
    echo "Usługa sejmomat-live już nadaje z tego komputera (systemctl --user stop sejmomat-live, by ją zatrzymać)." >&2
    exit 1
fi
echo "Upewnij się, że serwer (VPS) nie nadaje: oba używają tego samego klucza."

# the copy, up to date
if [ -d "$DIR/.git" ]; then
    git -C "$DIR" pull --ff-only -q || echo "(Nie udało się pobrać zmian; nadaję z tego, co jest.)"
else
    git clone -q "$REPO" "$DIR" || exit 1
fi
if [ ! -x "$DIR/.venv/bin/python" ]; then
    echo "Pierwsze uruchomienie: przygotowuję Pythona…"
    python3 -m venv "$DIR/.venv" && "$DIR/.venv/bin/pip" install -q pillow requests || exit 1
fi

# the key, asked for once
mkdir -p "$(dirname "$ENV")"
touch "$ENV" && chmod 600 "$ENV"
if ! grep -q '^SEJMOMAT_RTMP=.\+' "$ENV"; then
    echo "Klucz strumienia: YouTube Studio > Utwórz > Transmisja na żywo > Stream (domyślny klucz)."
    read -rsp "Wklej klucz strumienia (nie będzie widoczny): " key
    echo
    key=${key##*/}
    [ -n "$key" ] || { echo "Bez klucza nie da się nadawać." >&2; exit 1; }
    echo "SEJMOMAT_RTMP=rtmp://a.rtmp.youtube.com/live2/$key" >> "$ENV"
fi
set -a
# shellcheck disable=SC1090
. "$ENV"
set +a
export SEJMOMAT_PRESET="${SEJMOMAT_PRESET:-veryfast}"   # more CPU here than on the server

# Ctrl+C: stop now, not start again
stop=0
trap 'stop=1' INT TERM
cd "$DIR" || exit 1
echo "Nadaję. Ctrl+C kończy."
while :; do
    # the computer does not go to sleep while it streams
    systemd-inhibit --what=sleep:idle --who=Sejmomat --why="Transmisja Sejmu" \
        .venv/bin/python tools/livestream.py --wait --out rtmp
    ((stop)) && break
    echo "Transmisja przerwana; ponownie za 30 s (Ctrl+C kończy)."
    sleep 30 || true
    ((stop)) && break
done
echo "Zakończono."
