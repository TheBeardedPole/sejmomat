#!/bin/sh
# A test on the server: a replay of an earlier sitting, sent to the same
# address as the live stream (SEJMOMAT_RTMP in /etc/sejmomat-live.env). As root:
#   sh /opt/sejmomat/tools/vps/test-stream.sh                         # 10 minutes of a debate (22 October 2026 from 12:12:
#                                                                     # speakers recognised, cards, club Top 5s)
#   sh /opt/sejmomat/tools/vps/test-stream.sh "2026-10-22 17:40" 10   # votes, with the amendment panels
#   TEST_RTMP=rtmp://… sh …/test-stream.sh "2026-10-22 18:00" 5 chat   # to a test broadcast's own key
#                      (python tools/live_chat.py broadcast "Test" prints it), with vote links in its chat
# It goes out like a live stream: set the stream to Unlisted or Private in
# YouTube Studio first. Ctrl+C stops it. Not while the service is streaming a
# sitting (one address takes one stream).
set -eu
AT=${1:-2026-10-22 12:12}
MINUTES=${2:-10}
if pgrep -u sejmomat -x ffmpeg >/dev/null; then
    echo "The service is streaming a sitting now; try again later." >&2
    exit 1
fi
KEEP_RTMP=${TEST_RTMP:-}
set -a; . /etc/sejmomat-live.env; set +a
[ -n "$KEEP_RTMP" ] && SEJMOMAT_RTMP=$KEEP_RTMP   # a test broadcast's key over the channel's own
[ -n "${SEJMOMAT_RTMP:-}" ] || { echo "Put the stream key in /etc/sejmomat-live.env first." >&2; exit 1; }
cd /opt/sejmomat
# further arguments: "announce" (the site shows the test as Sejmomat's live stream too),
# "chat" (vote links in the broadcast's chat)
EXTRA=""
shift 2 2>/dev/null || shift $#
for a in "$@"; do
    case "$a" in
        announce) EXTRA="$EXTRA --announce" ;;
        chat) EXTRA="$EXTRA --chat" ;;
    esac
done
exec runuser -u sejmomat --preserve-environment -- env HOME=/var/lib/sejmomat .venv/bin/python tools/livestream.py --at "$AT" --seconds $((MINUTES * 60)) --out rtmp $EXTRA
