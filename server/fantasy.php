<?php
// Sejmowa liga: the fantasy game's server (the page is liga.html, static/league.js; the
// data it reads, prices and points, is made by the build, sejmomat/fantasy.py, in
// api/v1/fantasy/). The build copies this file to /srv/fantasy.php.
//
// Accounts: sign-in with Google, asking for the "openid" scope only, so Google tells us
// an ID and nothing else (no name, no email, no photo). We keep a keyed hash of that ID,
// a nickname the player chooses, and their squads. An email address is kept only if the
// player gives one for the newsletter or the reminder, confirmed by a link (double opt-in),
// and every mail carries a link that removes it. A session is a random token in an
// HttpOnly cookie (an essential cookie: no consent needed).
//
// The game: a squad of ten in six positions, within a budget, at most two from a club;
// it locks at 00:00 Warsaw time on a sitting's first day. Transfers as in FPL: one free a
// kolejka (unused ones saved, up to two), each extra costs 4 points; the first squad is
// free. A player sells at the current price when it fell, and keeps half of a rise.
//
//   GET  ?a=me                      -> {user|null, game, squad, history, email}
//   GET  ?a=login                   -> to Google; it comes back here with ?code&state
//   POST ?a=logout
//   POST ?a=nick     {nick}
//   POST ?a=squad    {slots: [{mp, pos}] x 10, captain}
//   GET  ?a=board                   -> {rows: [{rank, nick, total, last}], me}
//   POST ?a=email    {email, newsletter, reminders}  (sends the confirmation link)
//   GET  ?a=confirm&t=TOKEN         -> back to liga.html
//   GET  ?a=unsub&u=UID&s=SIG       -> removes the address
//   POST ?a=delete                  -> the account, its squads and address, gone
//   GET  ?a=remind&key=CRON_KEY     -> the reminder mail (from a cron job)
//   POST ?a=newsletter {key, subject, text}  -> a newsletter to those who asked for it
//
// Data: JSON files with locking and the configuration (Google client, mailbox, cron key)
// outside the web folder when the host allows it, else in ./data/fantasy, closed to the web.

declare(strict_types=1);

require_once __DIR__ . '/nick.php';   // clean_nick()

const SESSION_DAYS = 90;
const BOARD_SHOWN = 100;
const MAILS_PER_DAY = 3;              // confirmation mails a player can ask for in a day
const REMIND_BEFORE = 14 * 3600;      // the reminder goes out this long before the lock (10:00 the day before)
const COOKIE = 'sl_s';
const LOGIN_COOKIE = 'sl_l';

// ---- basics

function fail(int $code, string $message): void {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['error' => $message], JSON_UNESCAPED_UNICODE);
    exit;
}

function out(array $data): void {
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_UNICODE);
    exit;
}

function data_dir(): string {
    static $dir = null;
    if ($dir !== null) return $dir;
    foreach ([dirname(__DIR__, 2) . '/fantasy-data', __DIR__ . '/data/fantasy'] as $candidate) {
        if ((is_dir($candidate) || @mkdir($candidate, 0700, true)) && is_writable($candidate)) {
            $dir = $candidate;
            break;
        }
    }
    if ($dir === null) fail(500, 'storage unavailable');
    if (str_starts_with($dir, __DIR__)) {
        $closed = dirname($dir) . '/.htaccess';   // srv/data: closed to the web (and kept by the upload)
        if (!file_exists($closed)) file_put_contents($closed, "Require all denied\nDeny from all\n");
    }
    return $dir;
}

function config(): array {
    static $c = null;
    if ($c === null) {
        $path = data_dir() . '/config.php';
        $c = file_exists($path) ? (array)(require $path) : [];
        $c += ['base' => 'https://sejmomat.pl/', 'smtp_host' => 'smtp.hostinger.com', 'smtp_port' => 465];
    }
    return $c;
}

function secret(): string {
    $path = data_dir() . '/secret.key';
    if (!file_exists($path)) {
        file_put_contents($path, bin2hex(random_bytes(32)), LOCK_EX);
        @chmod($path, 0600);
    }
    return hex2bin(trim((string)file_get_contents($path)));
}

function now(): int { return time(); }

function read_json(string $name): array {
    $path = data_dir() . "/$name.json";
    return file_exists($path) ? (json_decode((string)file_get_contents($path), true) ?: []) : [];
}

function locked_update(string $name, callable $change): mixed {
    $fh = fopen(data_dir() . "/$name.json", 'c+');
    if (!$fh) fail(500, 'storage unavailable');
    flock($fh, LOCK_EX);
    $data = json_decode((string)stream_get_contents($fh), true) ?: [];
    [$data, $result] = $change($data);
    ftruncate($fh, 0);
    rewind($fh);
    fwrite($fh, json_encode($data, JSON_UNESCAPED_UNICODE));
    fflush($fh);
    flock($fh, LOCK_UN);
    fclose($fh);
    return $result;
}

function body(): array {
    // JSON only: a form on another site cannot send it without the browser asking first (CORS)
    if (!str_starts_with($_SERVER['CONTENT_TYPE'] ?? '', 'application/json')) fail(415, 'JSON expected');
    $origin = $_SERVER['HTTP_ORIGIN'] ?? '';
    if ($origin !== '') {
        $port = parse_url($origin, PHP_URL_PORT);
        if (parse_url($origin, PHP_URL_HOST) . ($port ? ":$port" : '') !== ($_SERVER['HTTP_HOST'] ?? '')) fail(403, 'wrong origin');
    }
    $json = json_decode((string)file_get_contents('php://input'), true);
    return is_array($json) ? $json : [];
}

function b64url(string $s): string { return rtrim(strtr(base64_encode($s), '+/', '-_'), '='); }
function unb64url(string $s): string|false { return base64_decode(strtr($s, '-_', '+/'), true); }

function seal(array $payload): string {
    $iv = random_bytes(12);
    $tag = '';
    $box = openssl_encrypt(json_encode($payload), 'aes-256-gcm', secret(), OPENSSL_RAW_DATA, $iv, $tag);
    return b64url($iv . $tag . $box);
}

function unseal(string $token): ?array {
    $raw = unb64url($token);
    if ($raw === false || strlen($raw) < 29) return null;
    $json = openssl_decrypt(substr($raw, 28), 'aes-256-gcm', secret(), OPENSSL_RAW_DATA, substr($raw, 0, 12), substr($raw, 12, 16));
    $p = $json === false ? null : json_decode($json, true);
    return is_array($p) ? $p : null;
}

function set_cookie(string $name, string $value, int $expires): void {
    setcookie($name, $value, ['expires' => $expires, 'path' => '/srv/', 'secure' => empty(config()['dev_login']), 'httponly' => true, 'samesite' => 'Lax']);
}

// ---- the game's data, from the build (api/v1/fantasy)

function game(): array {
    static $g = null;
    if ($g === null) {
        $g = json_decode((string)@file_get_contents(dirname(__DIR__) . '/api/v1/fantasy/game.json'), true);
        if (!is_array($g)) fail(503, 'Gra nie jest jeszcze gotowa.');
    }
    return $g;
}

function points_of(string $kid): ?array {
    static $cache = [];
    if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $kid)) return null;
    if (!array_key_exists($kid, $cache)) {
        $cache[$kid] = json_decode((string)@file_get_contents(dirname(__DIR__) . "/api/v1/fantasy/points/$kid.json"), true) ?: null;
    }
    return $cache[$kid];
}

function lock_ts(array $k): int { return (new DateTime($k['lock'] ?? ($k['id'] . 'T00:00:00'), new DateTimeZone('Europe/Warsaw')))->getTimestamp(); }

// every kolejka whose lock has passed: the ones played, and the live one
function locked_kolejki(): array {
    $out = [];
    foreach (game()['played'] ?? [] as $k) {
        $k['lock'] = $k['id'] . 'T00:00:00';
        $out[] = $k;
    }
    return $out;
}

function open_kolejka(): ?array {
    $g = game();
    if (($g['state'] ?? '') !== 'open' || empty($g['kolejka'])) return null;
    return lock_ts($g['kolejka']) > now() ? $g['kolejka'] : null;
}

// prices in tenths (integers, so no rounding errors): [mp][position index]
function price(int $mp, int $pos): ?int {
    $p = game()['prices'][(string)$mp][$pos] ?? null;
    return $p === null ? null : (int)round($p * 10);
}

function sell_price(array $slot): int {
    $now = price((int)$slot['mp'], (int)$slot['pos']) ?? (int)$slot['buy'];
    $buy = (int)$slot['buy'];
    return $now <= $buy ? $now : $buy + intdiv($now - $buy, 2);
}

// ---- users and sessions

function uid_for(string $sub): string { return substr(hash_hmac('sha256', "google|$sub", secret()), 0, 24); }

// a player's id for others (the ranking's links to their squads): not their account's own id
function pub_id(string $uid): string { return substr(hash_hmac('sha256', "pub|$uid", secret()), 0, 12); }

// the ranking: [['uid', 'nick', 'total', 'last', 'rank']] best first, players with a squad scored
function ranking(): array {
    $rows = [];
    foreach (read_json('users') as $id => $u) {
        if (empty($u['history']) || empty($u['nick'])) continue;
        [$total, $last] = season_total($u);
        $rows[] = ['uid' => $id, 'nick' => $u['nick'], 'total' => $total, 'last' => $last];
    }
    usort($rows, fn($a, $b) => $b['total'] <=> $a['total'] ?: strcmp($a['nick'], $b['nick']));
    $rank = 0;
    $prev = null;
    foreach ($rows as $i => &$r) {
        if ($r['total'] !== $prev) $rank = $i + 1;   // equal totals, equal rank
        $prev = $r['total'];
        $r['rank'] = $rank;
    }
    unset($r);
    return $rows;
}

function current_uid(): ?string {
    $token = $_COOKIE[COOKIE] ?? '';
    if ($token === '' || strlen($token) > 100) return null;
    $s = read_json('sessions')[hash('sha256', $token)] ?? null;
    return $s && $s['exp'] > now() ? $s['uid'] : null;
}

function need_uid(): string {
    $uid = current_uid();
    if ($uid === null) fail(401, 'Zaloguj się.');
    return $uid;
}

function start_session(string $uid): void {
    $token = b64url(random_bytes(32));
    $exp = now() + SESSION_DAYS * 86400;
    locked_update('sessions', function ($s) use ($token, $uid, $exp) {
        $s = array_filter($s, fn($x) => $x['exp'] > now());   // forget the expired ones
        $s[hash('sha256', $token)] = ['uid' => $uid, 'exp' => $exp];
        return [$s, null];
    });
    set_cookie(COOKIE, $token, $exp);
}

// Squads locked: before a squad can change or be scored, every kolejka whose lock has
// passed keeps the squad each player had at its lock (and the transfers made for it).
function freeze_all(): void {
    $locked = locked_kolejki();
    if (!$locked) return;
    locked_update('users', function ($users) use ($locked) {
        $hit = game()['transfers']['hit'] ?? 4;
        $max = game()['transfers']['bank_max'] ?? 2;
        foreach ($users as $uid => &$u) {
            foreach ($locked as $k) {
                $kid = $k['id'];
                if (isset($u['history'][$kid]) || empty($u['squad']['slots'])) continue;
                if (($u['squad']['saved'] ?? PHP_INT_MAX) >= lock_ts($k)) continue;   // made for a later kolejka
                $made = transfers_made($u);
                $free = $u['free'] ?? 1;
                $first = empty($u['base']);
                $u['history'][$kid] = ['slots' => $u['squad']['slots'], 'captain' => $u['squad']['captain'],
                                       'transfers' => $first ? 0 : $made, 'hit' => $first ? 0 : max(0, $made - $free) * $hit];
                $u['base'] = array_map(fn($s) => [$s['mp'], $s['pos']], $u['squad']['slots']);
                $u['free'] = $first ? 1 : min($max, max(0, $free - $made) + 1);
            }
        }
        return [$users, null];
    });
}

// how many places in the squad changed since the last lock
function transfers_made(array $u): int {
    $base = array_map(fn($b) => $b[0] . ':' . $b[1], $u['base'] ?? []);
    $now = array_map(fn($s) => $s['mp'] . ':' . $s['pos'], $u['squad']['slots'] ?? []);
    return count(array_diff($now, $base));
}

function kolejka_points(array $h, string $kid): array {
    $pts = points_of($kid);
    $rows = [];
    $sum = 0;
    foreach ($h['slots'] as $i => $s) {
        $p = $pts['mps'][(string)$s['mp']]['p'][$s['pos']] ?? 0;
        $x = $i === $h['captain'] ? 2 * $p : $p;
        $rows[] = ['mp' => $s['mp'], 'pos' => $s['pos'], 'points' => $x, 'captain' => $i === $h['captain'],
                   'facts' => $pts['mps'][(string)$s['mp']]['f'] ?? new stdClass()];
        $sum += $x;
    }
    return ['total' => $sum - $h['hit'], 'hit' => $h['hit'], 'transfers' => $h['transfers'], 'rows' => $rows,
            'final' => (bool)($pts['final'] ?? false), 'number' => $pts['number'] ?? null];
}

function season_total(array $u): array {
    $total = 0;
    $last = null;
    foreach ($u['history'] ?? [] as $kid => $h) {
        $k = kolejka_points($h, $kid);
        $total += $k['total'];
        $last = $k['total'];
    }
    return [$total, $last];
}

// ---- mail (SMTP over TLS, the hosting's mailbox)

function smtp_send(string $to, string $subject, string $text, ?string $unsub = null): bool {
    $c = config();
    if (empty($c['smtp_user']) || empty($c['smtp_pass'])) return false;
    $fp = @stream_socket_client("ssl://{$c['smtp_host']}:{$c['smtp_port']}", $errno, $err, 20);
    if (!$fp) return false;
    $read = function () use ($fp) {
        $all = '';
        while (($line = fgets($fp, 1024)) !== false) {
            $all .= $line;
            if (strlen($line) < 4 || $line[3] === ' ') break;
        }
        return $all;
    };
    $say = function (string $cmd, string $want) use ($fp, $read) {
        fwrite($fp, $cmd . "\r\n");
        return str_starts_with($read(), $want);
    };
    $from = $c['from'] ?? $c['smtp_user'];
    $ok = str_starts_with($read(), '220')
        && $say('EHLO ' . (parse_url($c['base'], PHP_URL_HOST) ?: 'localhost'), '250')
        && $say('AUTH LOGIN', '334') && $say(base64_encode($c['smtp_user']), '334') && $say(base64_encode($c['smtp_pass']), '235')
        && $say("MAIL FROM:<$from>", '250') && $say("RCPT TO:<$to>", '250') && $say('DATA', '354');
    if ($ok) {
        $headers = [
            'From: =?UTF-8?B?' . base64_encode('Sejmowa liga · Sejmomat') . "?= <$from>",
            "To: <$to>",
            'Subject: =?UTF-8?B?' . base64_encode($subject) . '?=',
            'Date: ' . date('r'),
            'Message-ID: <' . bin2hex(random_bytes(12)) . '@' . (parse_url($c['base'], PHP_URL_HOST) ?: 'sejmomat.pl') . '>',
            'MIME-Version: 1.0',
            'Content-Type: text/plain; charset=UTF-8',
            'Content-Transfer-Encoding: base64',
        ];
        if ($unsub) {
            $headers[] = "List-Unsubscribe: <$unsub>";
            $headers[] = 'List-Unsubscribe-Post: List-Unsubscribe=One-Click';
        }
        fwrite($fp, implode("\r\n", $headers) . "\r\n\r\n" . chunk_split(base64_encode($text)) . ".\r\n");
        $ok = str_starts_with($read(), '250');
    }
    fwrite($fp, "QUIT\r\n");
    fclose($fp);
    return $ok;
}

function unsub_link(string $uid): string {
    return config()['base'] . 'srv/fantasy.php?a=unsub&u=' . $uid . '&s=' . substr(hash_hmac('sha256', "unsub|$uid", secret()), 0, 32);
}

function league_link(): string { return config()['base'] . 'liga.html'; }

// ---- actions

header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: no-referrer');
$action = $_GET['a'] ?? '';

// Google sends the player back here with ?code&state (the redirect address registered in
// Google Cloud Console is exactly https://sejmomat.pl/srv/fantasy.php)
if ($action === '' && (isset($_GET['code']) || isset($_GET['error']))) $action = 'callback';

switch ($action) {
case 'login': {
    $c = config();
    // on a test machine (config "dev_login", Google client "dev"): straight in as a test player,
    // ?sub=name for another one
    if (!empty($c['dev_login']) && ($c['google_id'] ?? '') === 'dev' && in_array($_SERVER['REMOTE_ADDR'] ?? '', ['127.0.0.1', '::1'], true)) {
        $uid = uid_for('dev|' . preg_replace('/[^a-z0-9]/', '', (string)($_GET['sub'] ?? 'tester')));
        locked_update('users', function ($users) use ($uid) {
            $users[$uid] ??= ['created' => now(), 'nick' => null, 'free' => 1, 'history' => new stdClass()];
            return [$users, null];
        });
        start_session($uid);
        header('Location: ' . league_link(), true, 302);
        exit;
    }
    if (empty($c['google_id'])) fail(503, 'Logowanie nie jest jeszcze skonfigurowane.');
    $state = b64url(random_bytes(16));
    $verifier = b64url(random_bytes(32));
    set_cookie(LOGIN_COOKIE, seal(['state' => $state, 'v' => $verifier, 'exp' => now() + 600]), now() + 600);
    $q = http_build_query([
        'client_id' => $c['google_id'], 'redirect_uri' => $c['base'] . 'srv/fantasy.php', 'response_type' => 'code',
        'scope' => 'openid', 'state' => $state, 'code_challenge' => b64url(hash('sha256', $verifier, true)),
        'code_challenge_method' => 'S256', 'prompt' => 'select_account',
    ]);
    header('Location: https://accounts.google.com/o/oauth2/v2/auth?' . $q, true, 302);
    exit;
}

case 'callback': {
    $c = config();
    $back = league_link();
    $login = unseal($_COOKIE[LOGIN_COOKIE] ?? '');
    set_cookie(LOGIN_COOKIE, '', 1);
    if (isset($_GET['error']) || !$login || $login['exp'] < now() || !hash_equals($login['state'], (string)($_GET['state'] ?? ''))) {
        header("Location: $back?login=failed", true, 302);
        exit;
    }
    // the code for a token, straight from Google over TLS: the ID token it answers with
    // needs no signature check of our own (OpenID Connect Core 3.1.3.7)
    $ch = curl_init('https://oauth2.googleapis.com/token');
    curl_setopt_array($ch, [CURLOPT_POST => true, CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 15,
        CURLOPT_POSTFIELDS => http_build_query(['code' => (string)$_GET['code'], 'client_id' => $c['google_id'],
            'client_secret' => $c['google_secret'] ?? '', 'redirect_uri' => $c['base'] . 'srv/fantasy.php',
            'grant_type' => 'authorization_code', 'code_verifier' => $login['v']])]);
    $res = json_decode((string)curl_exec($ch), true);
    curl_close($ch);
    $parts = explode('.', (string)($res['id_token'] ?? ''));
    $claims = count($parts) === 3 ? json_decode((string)unb64url($parts[1]), true) : null;
    if (!is_array($claims) || ($claims['aud'] ?? '') !== $c['google_id'] || ($claims['exp'] ?? 0) < now()
        || !in_array($claims['iss'] ?? '', ['accounts.google.com', 'https://accounts.google.com'], true) || empty($claims['sub'])) {
        header("Location: $back?login=failed", true, 302);
        exit;
    }
    $uid = uid_for((string)$claims['sub']);
    locked_update('users', function ($users) use ($uid) {
        $users[$uid] ??= ['created' => now(), 'nick' => null, 'free' => 1, 'history' => new stdClass()];
        return [$users, null];
    });
    start_session($uid);
    header("Location: $back", true, 302);
    exit;
}

// for testing on this machine only: config "dev_login" => true, and a request from localhost
case 'devlogin': {
    if (empty(config()['dev_login']) || !in_array($_SERVER['REMOTE_ADDR'] ?? '', ['127.0.0.1', '::1'], true)) fail(404, 'unknown action');
    $uid = uid_for('dev|' . preg_replace('/[^a-z0-9]/', '', (string)($_GET['sub'] ?? 'tester')));
    locked_update('users', function ($users) use ($uid) {
        $users[$uid] ??= ['created' => now(), 'nick' => null, 'free' => 1, 'history' => new stdClass()];
        return [$users, null];
    });
    start_session($uid);
    out(['uid' => $uid]);
}

case 'logout': {
    body();
    $token = $_COOKIE[COOKIE] ?? '';
    if ($token !== '') {
        locked_update('sessions', function ($s) use ($token) {
            unset($s[hash('sha256', $token)]);
            return [$s, null];
        });
    }
    set_cookie(COOKIE, '', 1);
    out(['ok' => true]);
}

case 'me': {
    $uid = current_uid();
    $g = game();
    $open = open_kolejka();
    $base = ['game' => ['state' => $g['state'], 'kolejka' => $g['kolejka'], 'live' => $g['live'], 'open' => (bool)$open,
                        'configured' => !empty(config()['google_id'])]];
    if ($uid === null) out($base + ['user' => null]);
    freeze_all();
    $u = read_json('users')[$uid] ?? null;
    if ($u === null) {
        set_cookie(COOKIE, '', 1);
        out($base + ['user' => null]);
    }
    $history = [];
    foreach ($u['history'] ?? [] as $kid => $h) $history[$kid] = kolejka_points($h, $kid);
    [$total] = season_total($u);
    $squad = $u['squad'] ?? null;
    if ($squad) {
        $squad['value'] = array_sum(array_map('sell_price', $squad['slots'])) + $squad['bank'];
        $squad['sell'] = array_map('sell_price', $squad['slots']);
    }
    $e = read_json('emails')[$uid] ?? null;
    out($base + [
        'user' => ['nick' => $u['nick'], 'total' => $total],
        'squad' => $squad,
        // base: the squad at the last lock, which transfers are counted from
        'transfers' => ['free' => $u['free'] ?? 1, 'made' => empty($u['base']) ? 0 : transfers_made($u), 'first' => empty($u['base']),
                        'base' => array_map(fn($b) => $b[0] . ':' . $b[1], $u['base'] ?? [])],
        'history' => $history ?: new stdClass(),
        'email' => $e ? ['address' => $e['email'], 'confirmed' => (bool)$e['confirmed'], 'newsletter' => (bool)$e['newsletter'],
                         'reminders' => (bool)$e['reminders']] : null,
    ]);
}

case 'nick': {
    $uid = need_uid();
    $nick = clean_nick((string)(body()['nick'] ?? ''));
    $taken = locked_update('users', function ($users) use ($uid, $nick) {
        foreach ($users as $other => $u) {
            if ($other !== $uid && mb_strtolower((string)($u['nick'] ?? '')) === mb_strtolower($nick)) return [$users, true];
        }
        $users[$uid]['nick'] = $nick;
        return [$users, false];
    });
    if ($taken) fail(409, 'Ten nick jest już zajęty.');
    out(['nick' => $nick]);
}

case 'squad': {
    $uid = need_uid();
    $in = body();
    $k = open_kolejka();
    if (!$k) fail(409, 'Składy są zamknięte do końca tej kolejki.');
    freeze_all();
    $g = game();
    $positions = $g['positions'];
    $need = $g['squad'];
    $slots = [];
    $count = array_fill_keys($positions, 0);
    $clubs = [];
    $seen = [];
    foreach ((array)($in['slots'] ?? []) as $s) {
        $mp = (int)($s['mp'] ?? 0);
        $pos = array_search((string)($s['pos'] ?? ''), $positions, true);
        if ($pos === false || price($mp, $pos) === null) fail(400, 'Nieznany poseł albo pozycja.');
        if (isset($seen[$mp])) fail(400, 'Każdy poseł może być w składzie raz.');
        $seen[$mp] = true;
        $count[$positions[$pos]]++;
        $club = $g['mps'][(string)$mp][1] ?? 'niez.';
        $clubs[$club] = ($clubs[$club] ?? 0) + 1;
        if ($club !== 'niez.' && $clubs[$club] > $g['clubCap']) fail(400, "Najwyżej {$g['clubCap']} posłów z jednego klubu.");
        $slots[] = ['mp' => $mp, 'pos' => $pos];
    }
    foreach ($need as $pos => $n) {
        if ($count[$pos] !== $n) fail(400, 'Skład: 2 mówców, 2 buntowników, 2 lojalistów, 2 klikaczy, zwycięzca i opozycjonista.');
    }
    $captain = (int)($in['captain'] ?? -1);
    if ($captain < 0 || $captain >= count($slots)) fail(400, 'Wybierz kapitana.');
    $result = locked_update('users', function ($users) use ($uid, $slots, $captain, $g) {
        $u = $users[$uid] ?? null;
        if (!$u) return [$users, ['error' => 'Nie ma takiego konta.']];
        $old = $u['squad']['slots'] ?? [];
        $bank = $u['squad']['bank'] ?? (int)round($g['budget'] * 10);
        // places kept keep their purchase price; the others are sold and bought now
        $keep = [];
        foreach ($old as $o) $keep[$o['mp'] . ':' . $o['pos']] = $o;
        $new = [];
        foreach ($slots as $s) {
            $key = $s['mp'] . ':' . $s['pos'];
            if (isset($keep[$key])) {
                $new[] = $keep[$key];
                unset($keep[$key]);
            } else {
                $buy = price($s['mp'], $s['pos']);
                $bank -= $buy;
                $new[] = ['mp' => $s['mp'], 'pos' => $s['pos'], 'buy' => $buy];
            }
        }
        foreach ($keep as $sold) $bank += sell_price($sold);
        if ($bank < 0) return [$users, ['error' => sprintf('Brakuje %.1f mln w budżecie.', -$bank / 10)]];
        $u['squad'] = ['slots' => $new, 'captain' => $captain, 'bank' => $bank, 'saved' => now()];
        $users[$uid] = $u;
        return [$users, ['bank' => $bank, 'made' => empty($u['base']) ? 0 : transfers_made($u), 'free' => $u['free'] ?? 1]];
    });
    if (isset($result['error'])) fail(400, $result['error']);
    out($result);
}

case 'board': {
    freeze_all();
    $uid = current_uid();
    $rows = ranking();
    $me = null;
    foreach ($rows as $r) {
        if ($r['uid'] === $uid) $me = ['rank' => $r['rank'], 'total' => $r['total'], 'of' => count($rows)];
    }
    out(['rows' => array_map(fn($r) => ['rank' => $r['rank'], 'nick' => $r['nick'], 'total' => $r['total'], 'last' => $r['last'],
                                        'me' => $r['uid'] === $uid, 'id' => pub_id($r['uid'])],
                             array_slice($rows, 0, BOARD_SHOWN)), 'players' => count($rows), 'me' => $me]);
}

// another player's squads, as anyone may see them: only kolejki already locked (the squad being
// made for the next one stays theirs until it locks)
case 'player': {
    freeze_all();
    $want = preg_replace('/[^0-9a-f]/', '', (string)($_GET['id'] ?? ''));
    foreach (ranking() as $r) {
        if (pub_id($r['uid']) !== $want) continue;
        $u = read_json('users')[$r['uid']];
        $history = [];
        foreach ($u['history'] ?? [] as $kid => $h) $history[$kid] = kolejka_points($h, $kid);
        out(['nick' => $r['nick'], 'rank' => $r['rank'], 'total' => $r['total'], 'history' => $history ?: new stdClass()]);
    }
    fail(404, 'Nie ma takiego gracza.');
}

// for the stream (tools/livestream.py): the leaders, and the leader's latest locked squad
case 'leaders': {
    freeze_all();
    $rows = ranking();
    $lead = null;
    if ($rows) {
        $u = read_json('users')[$rows[0]['uid']];
        $kids = array_keys($u['history'] ?? []);
        sort($kids);
        $kid = end($kids);
        if ($kid) $lead = ['nick' => $rows[0]['nick'], 'total' => $rows[0]['total'], 'kolejka' => $kid] + kolejka_points($u['history'][$kid], $kid);
    }
    out(['top' => array_map(fn($r) => ['rank' => $r['rank'], 'nick' => $r['nick'], 'total' => $r['total'], 'last' => $r['last']],
                            array_slice($rows, 0, 5)), 'players' => count($rows), 'leader' => $lead]);
}

case 'email': {
    $uid = need_uid();
    $in = body();
    $email = trim((string)($in['email'] ?? ''));
    $newsletter = (bool)($in['newsletter'] ?? false);
    $reminders = (bool)($in['reminders'] ?? false);
    if (!$newsletter && !$reminders) {
        locked_update('emails', function ($e) use ($uid) {
            unset($e[$uid]);
            return [$e, null];
        });
        out(['email' => null]);
    }
    if (!filter_var($email, FILTER_VALIDATE_EMAIL) || strlen($email) > 200) fail(400, 'Podaj poprawny adres e-mail.');
    $token = b64url(random_bytes(18));
    $send = locked_update('emails', function ($e) use ($uid, $email, $newsletter, $reminders, $token) {
        $was = $e[$uid] ?? null;
        $same = $was && strcasecmp($was['email'], $email) === 0 && $was['confirmed'];
        $day = date('Y-m-d');
        $sent = ($was['day'] ?? '') === $day ? ($was['sent'] ?? 0) : 0;
        if (!$same && $sent >= MAILS_PER_DAY) return [$e, 'limit'];
        $e[$uid] = ['email' => $email, 'newsletter' => $newsletter, 'reminders' => $reminders, 'confirmed' => $same,
                    'token' => $same ? null : hash('sha256', $token), 'day' => $day, 'sent' => $sent + ($same ? 0 : 1)];
        return [$e, $same ? 'kept' : 'send'];
    });
    if ($send === 'limit') fail(429, 'Spróbuj jutro: dziś wysłaliśmy już kilka linków.');
    if ($send === 'send') {
        $link = config()['base'] . 'srv/fantasy.php?a=confirm&t=' . $token;
        $ok = smtp_send($email, 'Potwierdź adres w Sejmowej lidze',
            "Dzień dobry,\n\nktoś (mamy nadzieję, że Ty) podał ten adres w Sejmowej lidze na sejmomat.pl.\n" .
            "Potwierdź go tym linkiem:\n$link\n\nJeśli to nie Ty, zignoruj tę wiadomość: bez potwierdzenia adres nie będzie używany.\n");
        if (!$ok) fail(502, 'Nie udało się wysłać wiadomości. Spróbuj później.');
    }
    out(['email' => $email, 'confirmed' => $send === 'kept']);
}

case 'confirm': {
    $hash = hash('sha256', (string)($_GET['t'] ?? ''));
    $ok = locked_update('emails', function ($e) use ($hash) {
        foreach ($e as $uid => &$x) {
            if (!$x['confirmed'] && $x['token'] !== null && hash_equals($x['token'], $hash)) {
                $x['confirmed'] = true;
                $x['token'] = null;
                return [$e, true];
            }
        }
        return [$e, false];
    });
    header('Location: ' . league_link() . '?email=' . ($ok ? 'ok' : 'failed'), true, 302);
    exit;
}

case 'unsub': {
    $uid = (string)($_GET['u'] ?? '');
    $sig = (string)($_GET['s'] ?? '');
    $ok = $uid !== '' && hash_equals(substr(hash_hmac('sha256', "unsub|$uid", secret()), 0, 32), $sig);
    if ($ok) {
        locked_update('emails', function ($e) use ($uid) {
            unset($e[$uid]);
            return [$e, null];
        });
    }
    if ($_SERVER['REQUEST_METHOD'] === 'POST') out(['ok' => $ok]);   // one-click unsubscribe from the mail program
    header('Location: ' . league_link() . '?email=' . ($ok ? 'removed' : 'failed'), true, 302);
    exit;
}

case 'delete': {
    $uid = need_uid();
    body();
    foreach (['users', 'emails'] as $file) {
        locked_update($file, function ($x) use ($uid) {
            unset($x[$uid]);
            return [$x, null];
        });
    }
    locked_update('sessions', function ($s) use ($uid) {
        return [array_filter($s, fn($x) => $x['uid'] !== $uid), null];
    });
    set_cookie(COOKIE, '', 1);
    out(['ok' => true]);
}

case 'remind': {
    $key = config()['cron_key'] ?? '';
    if ($key === '' || !hash_equals($key, (string)($_GET['key'] ?? ''))) fail(403, 'no');
    $k = open_kolejka();
    if (!$k) out(['sent' => 0, 'why' => 'no kolejka open']);
    $lock = lock_ts($k);
    if (now() < $lock - REMIND_BEFORE) out(['sent' => 0, 'why' => 'too early']);
    $first = locked_update('reminders', function ($r) use ($k) {
        if (isset($r[$k['id']])) return [$r, false];
        $r[$k['id']] = now();
        return [$r, true];
    });
    if (!$first) out(['sent' => 0, 'why' => 'already sent']);
    $when = (new DateTime('@' . $lock))->setTimezone(new DateTimeZone('Europe/Warsaw'))->modify('-1 minute')->format('d.m');
    $name = $k['number'] ? "{$k['number']}. posiedzenie" : 'następne posiedzenie';
    $sent = 0;
    foreach (read_json('emails') as $uid => $e) {
        if (!$e['confirmed'] || !$e['reminders']) continue;
        $unsub = unsub_link($uid);
        if (smtp_send($e['email'], "Sejmowa liga: skład zamyka się dziś o północy",
            "Dzień dobry,\n\nskłady na $name zamykają się dziś ($when) o 23:59. Ceny posłów zmieniły się po ostatniej kolejce;\n" .
            "to dobry moment na transfery i wybór kapitana:\n" . league_link() . "\n\n" .
            "Nie chcesz przypomnień? Wypisz się jednym kliknięciem:\n$unsub\n", $unsub)) $sent++;
    }
    out(['sent' => $sent]);
}

case 'newsletter': {
    $in = body();
    $key = config()['cron_key'] ?? '';
    if ($key === '' || !hash_equals($key, (string)($in['key'] ?? ''))) fail(403, 'no');
    $subject = trim((string)($in['subject'] ?? ''));
    $text = trim((string)($in['text'] ?? ''));
    if ($subject === '' || $text === '') fail(400, 'subject and text needed');
    $sent = 0;
    foreach (read_json('emails') as $uid => $e) {
        if (!$e['confirmed'] || !$e['newsletter']) continue;
        $unsub = unsub_link($uid);
        if (smtp_send($e['email'], $subject, "$text\n\n--\nNewsletter Sejmowej ligi (sejmomat.pl). Wypisz się:\n$unsub\n", $unsub)) $sent++;
    }
    out(['sent' => $sent]);
}

default:
    fail(404, 'unknown action');
}
