#!/bin/sh
# A test on the server: a replay of an earlier sitting, sent to the same
# address as the live stream (SEJMOMAT_RTMP in /etc/sejmomat-live.env). As root:
#   sh /opt/sejmomat/tools/vps/test-stream.sh                         # 10 minutes of 22 October 2026 from 17:40 (votes)
#   sh /opt/sejmomat/tools/vps/test-stream.sh "2026-10-22 12:10" 15   # from that moment, for 15 minutes
# It goes out like a live stream: set the stream to Unlisted or Private in
# YouTube Studio first. Ctrl+C stops it. Not while the service is streaming a
# sitting (one address takes one stream).
set -eu
AT=${1:-2026-10-22 17:40}
MINUTES=${2:-10}
if pgrep -u sejmomat -x ffmpeg >/dev/null; then
    echo "The service is streaming a sitting now; try again later." >&2
    exit 1
fi
set -a; . /etc/sejmomat-live.env; set +a
[ -n "${SEJMOMAT_RTMP:-}" ] || { echo "Put the stream key in /etc/sejmomat-live.env first." >&2; exit 1; }
cd /opt/sejmomat
exec runuser -u sejmomat --preserve-environment -- .venv/bin/python tools/livestream.py --at "$AT" --seconds $((MINUTES * 60)) --out rtmp
