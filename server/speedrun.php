<?php
// "Twarze w minutę" (Sejmdle): name as many MPs from their photos as you can
// in a minute (+1 right, −1 wrong, skipping is free), with a daily and an
// all-time leaderboard. No accounts: a player leaves a nickname after a run.
// The build copies this file to /srv/speedrun.php.
//
// The run is dealt, checked and timed here, so the leaderboard cannot simply
// be written to: the server picks the MPs and keeps who they are in an
// encrypted token (photos come through ?a=photo, so their addresses do not
// give the answers away), starts the clock at ?a=go, checks and timestamps
// every answer at ?a=answer (an answer is only revealed once given), ignores
// answers after the minute, and finishes each run once. A nickname is
// attached afterwards (?a=name), so typing it does not count.
//
//   GET  ?a=start                 -> {token, rounds: [{options: [4 names]}]}
//   GET  ?a=photo&t=TOKEN&i=N     -> the N-th photo
//   POST ?a=go      t=TOKEN       -> {seconds} (the clock starts)
//   POST ?a=answer  t, i, choice  -> {ok, answer} (choice -1 = skip)
//   POST ?a=finish  t=TOKEN       -> {score, correct, wrong, claim, counted}
//   POST ?a=name    claim, nick   -> {rank, rankAll, today, all}
//   GET  ?a=board                 -> {today: [...], all: [...]}
//
// Data (JSON files, a secret key, cached photos) lives outside the web
// folder when the host allows it, otherwise in ./data, closed to the web.

declare(strict_types=1);

const ROUNDS = 120;           // faces dealt per run: more than anyone names in a minute
const OPTIONS = 4;
const DURATION = 60.0;        // seconds
const GRACE = 3.0;            // for answers sent just before the end and still on their way
const CLAIM_MINUTES = 15;     // time to type a nickname after a run
const BOARD_SIZE = 100;       // entries kept per board
const SHOWN = 20;             // entries shown
const RUNS_PER_DAY = 40;      // results saved per player (by hashed address) per day
const TERM = 10;

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

function fail(int $code, string $message): void {
    http_response_code($code);
    echo json_encode(['error' => $message], JSON_UNESCAPED_UNICODE);
    exit;
}

function data_dir(): string {
    static $dir = null;
    if ($dir !== null) return $dir;
    foreach ([dirname(__DIR__, 2) . '/speedrun-data', __DIR__ . '/data'] as $candidate) {
        if ((is_dir($candidate) || @mkdir($candidate, 0700, true)) && is_writable($candidate)) {
            $dir = $candidate;
            break;
        }
    }
    if ($dir === null) fail(500, 'storage unavailable');
    if (str_starts_with($dir, __DIR__) && !file_exists("$dir/.htaccess")) {
        file_put_contents("$dir/.htaccess", "Require all denied\nDeny from all\n");
    }
    foreach (['photos', 'pending', 'runs'] as $sub) @mkdir("$dir/$sub", 0700);
    return $dir;
}

function secret(): string {
    $path = data_dir() . '/secret.key';
    if (!file_exists($path)) {
        file_put_contents($path, bin2hex(random_bytes(32)), LOCK_EX);
        @chmod($path, 0600);
    }
    return hex2bin(trim((string)file_get_contents($path)));
}

function today(): string {
    return (new DateTime('now', new DateTimeZone('Europe/Warsaw')))->format('Y-m-d');
}

// --- tokens: the run's MPs, answers and times, encrypted and signed

function seal(array $payload): string {
    $iv = random_bytes(12);
    $tag = '';
    $box = openssl_encrypt(json_encode($payload), 'aes-256-gcm', secret(), OPENSSL_RAW_DATA, $iv, $tag);
    return rtrim(strtr(base64_encode($iv . $tag . $box), '+/', '-_'), '=');
}

function unseal(string $token): array {
    $raw = base64_decode(strtr($token, '-_', '+/'), true);
    if ($raw === false || strlen($raw) < 29) fail(400, 'bad token');
    $json = openssl_decrypt(substr($raw, 28), 'aes-256-gcm', secret(), OPENSSL_RAW_DATA, substr($raw, 0, 12), substr($raw, 12, 16));
    $payload = $json === false ? null : json_decode($json, true);
    if (!is_array($payload)) fail(400, 'bad token');
    return $payload;
}

// --- MPs: the site's own game data

function mps(): array {
    $games = json_decode((string)@file_get_contents(dirname(__DIR__) . '/api/v1/games.json'), true);
    if (!is_array($games) || empty($games['mps'])) fail(500, 'no data');
    return array_values(array_map(fn($m) => ['id' => (int)$m['id'], 'name' => (string)$m['name']], $games['mps']));
}

function female(string $name): bool {
    // a first name ending in "a" (Polish, with the usual exceptions) — options of one sex are harder
    $first = mb_strtolower(explode(' ', $name)[0]);
    return str_ends_with($first, 'a') && !in_array($first, ['kuba', 'barnaba', 'bonawentura'], true);
}

function deal(): array {
    $all = mps();
    shuffle($all);
    $picked = array_slice($all, 0, ROUNDS);
    $rounds = [];
    foreach ($picked as $mp) {
        $same = array_values(array_filter($all, fn($m) => $m['id'] !== $mp['id'] && female($m['name']) === female($mp['name'])));
        shuffle($same);
        $options = array_merge([$mp], array_slice($same, 0, OPTIONS - 1));
        shuffle($options);
        $rounds[] = ['id' => $mp['id'], 'names' => array_column($options, 'name'),
                     'answer' => array_search($mp['id'], array_column($options, 'id'), true)];
    }
    return $rounds;
}

// --- files

function locked_update(string $path, callable $change): mixed {
    $fh = fopen($path, 'c+');
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

function board(string $name): array {
    $path = data_dir() . "/minute-$name.json";   // "minute-": the one-minute game (earlier boards were by time)
    return file_exists($path) ? (json_decode((string)file_get_contents($path), true) ?: []) : [];
}

function shown(array $board): array {
    return array_map(fn($e) => ['nick' => $e['nick'], 'score' => $e['score'], 'correct' => $e['correct'], 'wrong' => $e['wrong'],
                                'day' => $e['day']], array_slice($board, 0, SHOWN));
}

function run_path(array $run): string {
    return data_dir() . '/runs/' . preg_replace('/[^a-f0-9]/', '', (string)$run['n']) . '.json';
}

function client_key(): string {
    return hash_hmac('sha256', ($_SERVER['REMOTE_ADDR'] ?? '') . '|' . today(), secret());
}

function clean_nick(string $nick): string {
    $nick = trim(preg_replace('/\s+/u', ' ', $nick));
    if (mb_strlen($nick) < 2 || mb_strlen($nick) > 20) fail(400, 'Nick musi mieć od 2 do 20 znaków.');
    if (!preg_match('/^[\p{L}\p{N} ._\-]+$/u', $nick)) fail(400, 'Nick może zawierać litery, cyfry, spację, kropkę, myślnik i podkreślnik.');
    $folded = strtr(mb_strtolower($nick), ['ą' => 'a', 'ć' => 'c', 'ę' => 'e', 'ł' => 'l', 'ń' => 'n', 'ó' => 'o', 'ś' => 's', 'ź' => 'z', 'ż' => 'z',
                                           '0' => 'o', '1' => 'i', '3' => 'e', '4' => 'a', '5' => 's', '@' => 'a', '$' => 's']);
    $folded = preg_replace('/[^a-z]/', '', $folded);
    foreach (['kurw', 'chuj', 'huj', 'pizd', 'jeb', 'pierdol', 'cipa', 'kutas', 'dziwk', 'szmat', 'pedal', 'ciot', 'hitler', 'heil',
              'nazi', 'fuck', 'cunt', 'nigg', 'whore'] as $bad) {
        if (str_contains($folded, $bad)) fail(400, 'Wybierz inny nick.');
    }
    return $nick;
}

function body(): array {
    $json = json_decode((string)file_get_contents('php://input'), true);
    return is_array($json) ? $json : $_POST;
}

// --- actions

$action = $_GET['a'] ?? '';

if ($action === 'start') {
    $rounds = deal();
    echo json_encode([
        // the token keeps only each face's MP and right answer, so it stays short (it goes in photo addresses)
        'token' => seal(['r' => array_map(fn($r) => [$r['id'], $r['answer']], $rounds), 'n' => bin2hex(random_bytes(8))]),
        'rounds' => array_map(fn($r) => ['options' => $r['names']], $rounds),
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

if ($action === 'photo') {
    $run = unseal((string)($_GET['t'] ?? ''));
    $i = (int)($_GET['i'] ?? -1);
    if (!isset($run['r'][$i])) fail(404, 'no such photo');
    $id = (int)$run['r'][$i][0];
    $path = data_dir() . "/photos/$id.jpg";
    if (!file_exists($path)) {
        $url = 'https://api.sejm.gov.pl/sejm/term' . TERM . "/MP/$id/photo";
        $ctx = stream_context_create(['http' => ['timeout' => 20, 'header' => "User-Agent: sejmomat\r\n"]]);
        $img = @file_get_contents($url, false, $ctx);
        if ($img === false && function_exists('curl_init')) {
            $c = curl_init($url);
            curl_setopt_array($c, [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 20, CURLOPT_USERAGENT => 'sejmomat']);
            $img = curl_exec($c);
            curl_close($c);
        }
        if (!$img) fail(502, 'photo unavailable');
        file_put_contents($path, $img, LOCK_EX);
    }
    header('Content-Type: image/jpeg');
    header('Cache-Control: private, max-age=600');
    readfile($path);
    exit;
}

if ($action === 'go') {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') fail(405, 'POST only');
    $run = unseal((string)(body()['t'] ?? ''));
    $path = run_path($run);
    $fh = @fopen($path, 'x');   // only the first "go" for a run starts it
    if (!$fh) fail(400, 'already started');
    fwrite($fh, json_encode(['go' => microtime(true), 'answers' => new stdClass(), 'done' => false]));
    fclose($fh);
    echo json_encode(['seconds' => DURATION]);
    exit;
}

if ($action === 'answer') {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') fail(405, 'POST only');
    $in = body();
    $run = unseal((string)($in['t'] ?? ''));
    $i = (int)($in['i'] ?? -1);
    $choice = (int)($in['choice'] ?? -1);
    if (!isset($run['r'][$i])) fail(400, 'no such face');
    if (!file_exists(run_path($run))) fail(400, 'not started');
    $answer = (int)$run['r'][$i][1];
    // each face is answered once; answers may arrive out of order, but not after the minute
    $result = locked_update(run_path($run), function ($state) use ($i, $choice, $answer) {
        $now = microtime(true);
        if ($state['done'] || $now > $state['go'] + DURATION + GRACE) return [$state, 'late'];
        if (isset($state['answers'][(string)$i])) return [$state, 'twice'];
        $state['answers'][(string)$i] = [$choice, $choice === -1 ? null : $choice === $answer, $now];
        return [$state, 'ok'];
    });
    if ($result !== 'ok') fail(409, $result);
    echo json_encode(['ok' => $choice === -1 ? null : $choice === $answer, 'answer' => $answer]);
    exit;
}

if ($action === 'finish') {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') fail(405, 'POST only');
    $run = unseal((string)(body()['t'] ?? ''));
    if (!file_exists(run_path($run))) fail(400, 'not started');
    $state = locked_update(run_path($run), function ($state) {
        $was = $state['done'];
        $state['done'] = true;
        return [$state, $was ? null : $state];
    });
    if ($state === null) fail(409, 'run already finished');
    $answers = (array)$state['answers'];
    $correct = count(array_filter($answers, fn($a) => $a[1] === true));
    $wrong = count(array_filter($answers, fn($a) => $a[1] === false));
    $score = max(0, $correct - $wrong);
    $counted = $score > 0;   // a run without points stays off the boards
    $claim = '';
    if ($counted) {
        $claim = bin2hex(random_bytes(12));
        file_put_contents(data_dir() . "/pending/$claim.json",
            json_encode(['score' => $score, 'correct' => $correct, 'wrong' => $wrong, 'day' => today(), 'at' => time()]));
    }
    echo json_encode(['score' => $score, 'correct' => $correct, 'wrong' => $wrong, 'claim' => $claim, 'counted' => $counted]);
    // tidy up now and then: unclaimed results and runs after an hour, and the per-day
    // address hashes after three days (as the privacy page says)
    if (random_int(1, 20) === 1) {
        foreach (array_merge(glob(data_dir() . '/pending/*.json') ?: [], glob(data_dir() . '/runs/*.json') ?: []) as $f) {
            if (filemtime($f) < time() - 3600) @unlink($f);
        }
        foreach (glob(data_dir() . '/rate-*.json') ?: [] as $f) if (filemtime($f) < time() - 3 * 86400) @unlink($f);
    }
    exit;
}

if ($action === 'name') {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') fail(405, 'POST only');
    $in = body();
    $claim = preg_replace('/[^a-f0-9]/', '', (string)($in['claim'] ?? ''));
    $path = data_dir() . "/pending/$claim.json";
    if ($claim === '' || !file_exists($path)) fail(404, 'Ten wynik wygasł albo został już zapisany.');
    $result = json_decode((string)file_get_contents($path), true);
    if (time() - (int)$result['at'] > CLAIM_MINUTES * 60) { @unlink($path); fail(410, 'Ten wynik wygasł.'); }
    $nick = clean_nick((string)($in['nick'] ?? ''));
    $key = client_key();
    $count = locked_update(data_dir() . '/rate-' . today() . '.json', function ($rates) use ($key) {
        $rates[$key] = ($rates[$key] ?? 0) + 1;
        return [$rates, $rates[$key]];
    });
    if ($count > RUNS_PER_DAY) fail(429, 'Na dziś to już wszystkie zapisy z tego urządzenia.');
    @unlink($path);
    $entry = ['nick' => $nick, 'score' => $result['score'], 'correct' => $result['correct'], 'wrong' => $result['wrong'],
              'day' => $result['day'], 'at' => time()];
    // higher score first, then fewer mistakes, then whoever got there first
    $insert = function ($board) use ($entry) {
        $board[] = $entry;
        usort($board, fn($a, $b) => [-$a['score'], $a['wrong'], $a['at']] <=> [-$b['score'], $b['wrong'], $b['at']]);
        $rank = array_search($entry, $board, true) + 1;
        return [array_slice($board, 0, BOARD_SIZE), $rank <= BOARD_SIZE ? $rank : null];
    };
    $rank = locked_update(data_dir() . '/minute-' . $result['day'] . '.json', $insert);
    $rankAll = locked_update(data_dir() . '/minute-all.json', $insert);
    echo json_encode(['rank' => $rank, 'rankAll' => $rankAll, 'today' => shown(board(today())), 'all' => shown(board('all'))],
                     JSON_UNESCAPED_UNICODE);
    exit;
}

if ($action === 'board') {
    echo json_encode(['today' => shown(board(today())), 'all' => shown(board('all')), 'day' => today()], JSON_UNESCAPED_UNICODE);
    exit;
}

fail(404, 'unknown action');
