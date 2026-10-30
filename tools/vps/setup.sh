#!/bin/sh
# Sets up the stream on a fresh Debian or Ubuntu server. As root:
#   curl -fsSL https://raw.githubusercontent.com/TheBeardedPole/sejmomat/main/tools/vps/setup.sh | sh
# then put the stream key in /etc/sejmomat-live.env and start the service
# (the script says how at the end). Running it again updates the setup.
set -eu

apt-get update -q
apt-get install -y -q git ffmpeg tesseract-ocr tesseract-ocr-pol fonts-noto-core fontconfig python3-venv

id sejmomat >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/sejmomat --shell /usr/sbin/nologin sejmomat
if [ ! -d /opt/sejmomat/.git ]; then
    git clone -q --depth 1 https://github.com/TheBeardedPole/sejmomat.git /opt/sejmomat
fi
chown -R sejmomat: /opt/sejmomat
runuser -u sejmomat -- git -C /opt/sejmomat pull --ff-only -q
runuser -u sejmomat -- python3 -m venv /opt/sejmomat/.venv
runuser -u sejmomat -- /opt/sejmomat/.venv/bin/pip install -q -r /opt/sejmomat/requirements.txt

if [ ! -f /etc/sejmomat-live.env ]; then
    printf '%s\n' '# the platform address with the stream key, e.g.' \
        '# SEJMOMAT_RTMP=rtmp://a.rtmp.youtube.com/live2/xxxx-xxxx-xxxx-xxxx-xxxx' \
        'SEJMOMAT_RTMP=' \
        '# outside Poland the video CDN does not answer: a proxy in Poland (tools/vps/proxy-setup.sh), e.g.' \
        '# SEJMOMAT_VIDEO_PROXY=http://203.0.113.5:8888' \
        '# the key the stream tells the site it is on air with (its SHA-256 in server/youtube-live.php):' \
        '# SEJMOMAT_LIVE_KEY=' \
        '# x264 speed if the server cannot keep up ("behind real time" growing in the log): ultrafast' \
        '# SEJMOMAT_PRESET=superfast' \
        '# vote links in the stream'"'"'s chat: the lines `python tools/live_chat.py auth` prints' \
        '# SEJMOMAT_YT_CLIENT_ID=' \
        '# SEJMOMAT_YT_CLIENT_SECRET=' \
        '# SEJMOMAT_YT_REFRESH_TOKEN=' \
        '# seconds a vote message waits beyond the picture (YouTube shows the video later than chat):' \
        '# SEJMOMAT_CHAT_LAG=12' \
        '# a sitting'"'"'s broadcast title once live ({n}: the sitting):' \
        '# SEJMOMAT_YT_TITLE={n}. Posiedzenie Sejmu | Lepsza Transmisja' > /etc/sejmomat-live.env
fi
chown root:sejmomat /etc/sejmomat-live.env
chmod 640 /etc/sejmomat-live.env

cp /opt/sejmomat/tools/vps/sejmomat-live.service /opt/sejmomat/tools/vps/sejmomat-pull.service \
   /opt/sejmomat/tools/vps/sejmomat-pull.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sejmomat-pull.timer

echo
echo "Done. Next:"
echo "  1. nano /etc/sejmomat-live.env      (the stream key after SEJMOMAT_RTMP=)"
echo "  2. systemctl enable --now sejmomat-live"
echo "  3. journalctl -u sejmomat-live -f   (what it is doing)"
