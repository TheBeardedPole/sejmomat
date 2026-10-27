<?php
// Is Sejmomat's YouTube channel live? Asked by the site's pages (static/yt.js), which
// cannot find out themselves: YouTube's pages allow no cross-site reads, and its Data
// API would need a key in the page. The channel's /live page is read at most once a
// minute, the answer cached in the data folder (as server/speedrun.php keeps its own):
//   {"live": true, "id": "<video id>", "title": "...", "checked": <unix time>}
//   {"live": false, "checked": ...}   (or "error": true when YouTube did not answer)
// Nothing about the visitor is sent to YouTube: the request is the server's own.

const CHANNEL_LIVE = 'https://www.youtube.com/@Sejmomat/live';
const TTL = 60;   // seconds a check is reused

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: public, max-age=30');
header('X-Content-Type-Options: nosniff');

function data_dir(): ?string {
    foreach ([dirname(__DIR__, 2) . '/speedrun-data', __DIR__ . '/data'] as $candidate) {
        if ((is_dir($candidate) || @mkdir($candidate, 0700, true)) && is_writable($candidate)) {
            if (str_starts_with($candidate, __DIR__) && !file_exists("$candidate/.htaccess")) {
                file_put_contents("$candidate/.htaccess", "Require all denied\nDeny from all\n");
            }
            return $candidate;
        }
    }
    return null;
}

// The channel's live page: when a stream is on, it is that video's page (its canonical
// address is watch?v=..., and it says "isLiveNow":true); otherwise the channel's own.
function check(): array {
    $context = stream_context_create(['http' => [
        'timeout' => 6,
        'header' => "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36\r\n"
                  . "Accept-Language: pl,en;q=0.8\r\n"
                  // past the EU consent page, which would stand in for the channel
                  . "Cookie: SOCS=CAI; CONSENT=YES+\r\n",
    ]]);
    $html = @file_get_contents(CHANNEL_LIVE, false, $context);
    if ($html === false || $html === '') return ['live' => false, 'error' => true, 'checked' => time()];
    $live = (bool) preg_match('/"isLiveNow"\s*:\s*true/', $html);
    $id = preg_match('#<link rel="canonical" href="https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})"#', $html, $m) ? $m[1] : null;
    if (!$live || !$id) return ['live' => false, 'checked' => time()];
    $title = preg_match('#<meta name="title" content="([^"]*)"#', $html, $t)
        ? mb_substr(html_entity_decode($t[1], ENT_QUOTES | ENT_HTML5, 'UTF-8'), 0, 200) : '';
    return ['live' => true, 'id' => $id, 'title' => $title, 'checked' => time()];
}

$dir = data_dir();
$cache = $dir ? "$dir/youtube-live.json" : null;
if ($cache && is_file($cache) && time() - filemtime($cache) < TTL) {
    readfile($cache);
    exit;
}
// one check at a time; the others meanwhile get the last answer
$lock = $cache ? @fopen("$cache.lock", 'c') : false;
if ($lock && !flock($lock, LOCK_EX | LOCK_NB)) {
    if (is_file($cache)) readfile($cache);
    else echo json_encode(['live' => false, 'checked' => time()]);
    exit;
}
$answer = check();
// YouTube did not answer: the last good answer (if fresh enough) rather than "not live"
if (!empty($answer['error']) && $cache && is_file($cache) && time() - filemtime($cache) < 10 * TTL) {
    readfile($cache);
    exit;
}
$json = json_encode($answer, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
if ($cache) file_put_contents($cache, $json, LOCK_EX);
echo $json;
