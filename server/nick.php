<?php
// Nicknames for the leaderboards (speedrun.php, fantasy.php): 2 to 20 letters, digits,
// spaces and . _ -, and none of the obvious insults (also spelt with digits for letters).
// Only defines a function; requesting this file directly does nothing.

declare(strict_types=1);

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
