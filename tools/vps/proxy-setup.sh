#!/bin/sh
# The Sejm's video CDN answers only Polish addresses. If the stream's server is
# elsewhere, a small server in Poland runs this proxy and the stream fetches the
# video through it (SEJMOMAT_VIDEO_PROXY). Only the incoming video (about 3 Mbit/s)
# passes through; the work and the upload to YouTube stay on the stream's server.
#
# On the Polish server (Debian or Ubuntu), as root:
#   curl -fsSL https://raw.githubusercontent.com/TheBeardedPole/sejmomat/main/tools/vps/proxy-setup.sh | sh -s <stream server IP> [port]
#
# It answers only the stream server's address, and only for the CDN (*.blueonline.tv).
set -eu
CLIENT=${1:?usage: proxy-setup.sh <stream server IP> [port]}
PORT=${2:-8888}

apt-get update -q
apt-get install -y -q tinyproxy curl

cat > /etc/tinyproxy/tinyproxy.conf <<CONF
User tinyproxy
Group tinyproxy
Port $PORT
Timeout 600
MaxClients 20
# only the stream server
Allow 127.0.0.1
Allow $CLIENT
# only the video CDN, only HTTPS
FilterDefaultDeny Yes
Filter "/etc/tinyproxy/filter"
FilterType ere
ConnectPort 443
DisableViaHeader Yes
LogLevel Warning
CONF
printf '%s\n' '(^|\.)blueonline\.tv$' > /etc/tinyproxy/filter

systemctl enable -q tinyproxy
systemctl restart tinyproxy

# does the CDN answer this server?
code=$(curl -4 -s -o /dev/null -w '%{http_code}' --max-time 15 -x "http://127.0.0.1:$PORT" \
    https://tvo-1-1.e.blueonline.tv/nb-s2/sejm_abr/ENC01/playlist_dvr_range-1761128400-now.m3u8 || true)
echo
if [ "$code" = 200 ]; then
    echo "The video CDN answers this server. On the stream server, add to /etc/sejmomat-live.env:"
    echo "  SEJMOMAT_VIDEO_PROXY=http://<this server's IP>:$PORT"
    echo "then: systemctl restart sejmomat-live"
else
    echo "The video CDN does not answer this server either (got '$code'): this server will not help." >&2
    exit 1
fi
