#!/usr/bin/env bash
# The stream on your own computer (Linux with systemd), as on the server (setup.sh), but as a
# user service, no root needed: a copy of the repository of its own in ~/sejmomat-live (the
# service pulls main before each start, so it must not be your working copy), the settings
# in ~/.config/sejmomat-live.env, the service sejmomat-live waiting for each day's sitting.
# Can be run again: it keeps what is there and only fills in what is missing.
#
#   bash tools/vps/pc-setup.sh
#
# Afterwards:  journalctl --user -u sejmomat-live -f      (what it is doing)
#              systemctl --user stop sejmomat-live          (stop it, e.g. when the server streams)
set -euo pipefail

REPO=https://github.com/TheBeardedPole/sejmomat.git
DIR="$HOME/sejmomat-live"
ENV="$HOME/.config/sejmomat-live.env"
UNIT="$HOME/.config/systemd/user/sejmomat-live.service"

say() { printf '\n== %s\n' "$*"; }

say "Programy"
missing=()
for c in git python3 ffmpeg systemctl; do command -v "$c" >/dev/null || missing+=("$c"); done
if ((${#missing[@]})); then
    echo "Brakuje: ${missing[*]}. Na Fedorze/Nobarze: sudo dnf install ${missing[*]}" >&2
    exit 1
fi
if ! command -v tesseract >/dev/null || ! tesseract --list-langs 2>/dev/null | grep -qx pol; then
    echo "Uwaga: bez tesseract z językiem polskim nie będzie nazwisk mówców (sudo dnf install tesseract tesseract-langpack-pol)."
fi
echo "ok"

say "Kopia repozytorium w $DIR"
if [ -d "$DIR/.git" ]; then
    git -C "$DIR" pull --ff-only -q && echo "zaktualizowana"
else
    git clone -q "$REPO" "$DIR" && echo "pobrana"
fi

say "Środowisko Pythona"
[ -x "$DIR/.venv/bin/python" ] || python3 -m venv "$DIR/.venv"
# morfeusz2 is only needed to build the site: if it will not install, the stream's own packages
if ! "$DIR/.venv/bin/pip" install -q -r "$DIR/requirements.txt"; then
    echo "pełna lista się nie zainstalowała; instaluję tylko to, czego potrzebuje transmisja"
    "$DIR/.venv/bin/pip" install -q pillow requests
fi
echo "ok"

say "Ustawienia w $ENV"
mkdir -p "$(dirname "$ENV")"
touch "$ENV"
chmod 600 "$ENV"
if ! grep -q '^SEJMOMAT_RTMP=.\+' "$ENV"; then
    echo "Klucz strumienia: YouTube Studio > Utwórz > Transmisja na żywo > Stream (domyślny klucz)."
    read -rsp "Wklej klucz strumienia (nie będzie widoczny): " key
    echo
    key=${key##*/}   # a whole address pasted: just the key
    [ -n "$key" ] || { echo "Bez klucza nie da się nadawać." >&2; exit 1; }
    sed -i '/^SEJMOMAT_RTMP=/d' "$ENV"
    echo "SEJMOMAT_RTMP=rtmp://a.rtmp.youtube.com/live2/$key" >> "$ENV"
    echo "zapisany"
else
    echo "klucz już jest"
fi
# a computer has more CPU to spare than the server: a better picture for the same bitrate
grep -q '^SEJMOMAT_PRESET=' "$ENV" || echo "SEJMOMAT_PRESET=veryfast" >> "$ENV"
grep -q '^SEJMOMAT_YT_' "$ENV" || echo "(Linki w czacie i tytuł: dopisz trzy linie SEJMOMAT_YT_* z /etc/sejmomat-live.env na serwerze.)"

say "Usługa sejmomat-live"
mkdir -p "$(dirname "$UNIT")"
cat > "$UNIT" <<'EOF'
# Made by tools/vps/pc-setup.sh: the stream on this computer, waiting for each day's sitting.
[Unit]
Description=Sejmomat: the Sejm's stream with captions (this computer)
Wants=network-online.target
After=network-online.target

[Service]
WorkingDirectory=%h/sejmomat-live
EnvironmentFile=%h/.config/sejmomat-live.env
ExecStartPre=-/usr/bin/git -C %h/sejmomat-live pull --ff-only -q
# the computer does not go to sleep while it streams
ExecStart=/usr/bin/systemd-inhibit --what=sleep:idle --who=Sejmomat --why="Transmisja Sejmu" %h/sejmomat-live/.venv/bin/python tools/livestream.py --wait --out rtmp
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable -q sejmomat-live
# running when you are logged out too, and from boot
loginctl enable-linger "$USER" 2>/dev/null || echo "(Nie udało się włączyć 'linger': usługa ruszy dopiero po zalogowaniu.)"
echo "ok"

say "Start"
echo "Jeśli serwer (VPS) też nadaje, zatrzymaj go najpierw: oba używają tego samego klucza."
read -rp "Uruchomić transmisję teraz? [t/N] " go
if [[ "$go" =~ ^[tTyY] ]]; then
    systemctl --user restart sejmomat-live
    echo "Uruchomiona. Podgląd: journalctl --user -u sejmomat-live -f"
else
    echo "Nie uruchomiona. Później: systemctl --user start sejmomat-live"
fi
