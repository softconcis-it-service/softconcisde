<?php
/**
 * ALTCHA-Backend (PHP-Portierung von server.py für Webspace-Hosting).
 * Proof-of-Work-Captcha: DSGVO-konform, selbst gehostet, keine Cookies.
 */

const CHALLENGE_TTL = 600;   // Sekunden Gültigkeit einer Challenge
const MAX_NUMBER = 60000;    // Proof-of-Work-Schwierigkeit
const RATE_LIMIT = 10;       // max. Formular-Posts ...
const RATE_WINDOW = 600;     // ... pro IP in diesem Zeitfenster (Sek.)

define('DATA_DIR', __DIR__ . '/data');

// Empfänger der Admin-Benachrichtigungen ('' = aus) und Absender ausgehender Mails
// Live: Formularnachrichten gehen an den Kunden (wie im CF7-Plugin konfiguriert)
const MAIL_TO = 'info@softconcis.de';
// ACHTUNG: IONOS verwirft mail() mit Absenderdomains, die nicht zum Vertrag
// gehören (info@softconcis.de -> false). Daher Server-Domain als Absender.
const MAIL_FROM = 'noreply@softconcis.de';
const MAIL_REPLY_TO = 'info@softconcis.de';

function data_dir(string $sub = ''): string {
    $dir = DATA_DIR . ($sub ? '/' . $sub : '');
    if (!is_dir($dir)) {
        mkdir($dir, 0700, true);
    }
    return $dir;
}

function get_secret(): string {
    $file = data_dir() . '/secret.bin';
    if (is_file($file)) {
        return file_get_contents($file);
    }
    $s = random_bytes(32);
    file_put_contents($file, $s, LOCK_EX);
    chmod($file, 0600);
    return $s;
}

function make_challenge(): array {
    $salt = bin2hex(random_bytes(12)) . '?expires=' . (time() + CHALLENGE_TTL);
    $number = random_int(0, MAX_NUMBER - 1);
    $challenge = hash('sha256', $salt . $number);
    $signature = hash_hmac('sha256', $challenge, get_secret());
    return [
        'algorithm' => 'SHA-256',
        'challenge' => $challenge,
        'maxnumber' => MAX_NUMBER,
        'salt' => $salt,
        'signature' => $signature,
    ];
}

/** Serverseitige Verifikation des ALTCHA-Payloads (PoW + HMAC + Ablauf + Replay). */
function verify_altcha(string $payload_b64): array {
    $data = json_decode(base64_decode($payload_b64, true) ?: '', true);
    if (!is_array($data) || !isset($data['salt'], $data['number'], $data['challenge'], $data['signature'])) {
        return [false, 'malformed'];
    }
    $salt = (string)$data['salt'];
    $number = (string)(int)$data['number'];
    $challenge = (string)$data['challenge'];
    $signature = (string)$data['signature'];

    if (!preg_match('/[?&]expires=(\d+)/', $salt, $m) || (int)$m[1] < time()) {
        return [false, 'expired'];
    }
    // Replay-Schutz: jede Challenge nur einmal einlösbar
    $used = data_dir('used') . '/' . hash('sha256', $challenge);
    if (is_file($used)) {
        return [false, 'replay'];
    }
    if (hash('sha256', $salt . $number) !== $challenge) {
        return [false, 'pow'];
    }
    $expected = hash_hmac('sha256', $challenge, get_secret());
    if (!hash_equals($expected, $signature)) {
        return [false, 'signature'];
    }
    file_put_contents($used, '1');
    cleanup_dir(data_dir('used'), CHALLENGE_TTL);
    return [true, 'ok'];
}

function rate_limited(string $ip): bool {
    $file = data_dir('rate') . '/' . hash('sha256', $ip) . '.json';
    $now = time();
    $hits = [];
    if (is_file($file)) {
        $hits = json_decode(file_get_contents($file), true) ?: [];
        $hits = array_values(array_filter($hits, fn($t) => $now - $t < RATE_WINDOW));
    }
    $hits[] = $now;
    file_put_contents($file, json_encode($hits), LOCK_EX);
    cleanup_dir(data_dir('rate'), RATE_WINDOW);
    return count($hits) > RATE_LIMIT;
}

/** Entfernt gelegentlich veraltete Hilfsdateien (kein Cron nötig). */
function cleanup_dir(string $dir, int $max_age): void {
    if (random_int(0, 20) !== 0) {
        return;
    }
    foreach (glob($dir . '/*') ?: [] as $f) {
        if (is_file($f) && time() - filemtime($f) > $max_age * 2) {
            unlink($f);
        }
    }
}

function messages_dir(): string {
    $dir = dirname(__DIR__) . '/_nachrichten';
    if (!is_dir($dir)) {
        mkdir($dir, 0700, true);
    }
    return $dir;
}

function write_message(string $path, array $record): void {
    file_put_contents($path, json_encode($record, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE), LOCK_EX);
}

/** Basis-URL der Site inkl. Unterverzeichnis, z. B. http://host/softconcis */
function site_base_url(): string {
    $scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
    $prefix = rtrim(dirname(dirname($_SERVER['SCRIPT_NAME'] ?? '/api/x.php')), '/');
    return $scheme . '://' . ($_SERVER['HTTP_HOST'] ?? 'localhost') . $prefix;
}

/** Felder als "Beschriftung: Wert"-Zeilen für die Admin-Mail. */
function format_fields(array $fields, ?string $stored_attachment = null): string {
    $labels = [
        'text-name' => 'Name',
        'text-strassenr' => 'Straße, Nr.',
        'text-plzort' => 'PLZ, Ort',
        'email-322' => 'E-Mail',
        'tel-538' => 'Telefon',
        'tel-84' => 'Telefon',
        'text-firma' => 'Unternehmen',
        'text-unternehmen' => 'Unternehmen',
        'text-position' => 'Position',
        'text-bewerbungfuer' => 'Bewerbung für',
        'text-anmeldung' => 'Anmeldung zu Seminar/Veranstaltung',
        'text-register' => 'Anmeldung zu Seminar/Veranstaltung',
        'your-message' => 'Nachricht',
        'acceptance-953' => 'Datenschutz akzeptiert',
    ];
    $lines = [];
    $message = null;
    foreach ($labels as $key => $label) {
        if (!array_key_exists($key, $fields)) {
            continue;
        }
        $v = $fields[$key];
        $v = is_array($v) ? implode(', ', $v) : (string)$v;
        if ($key === 'your-message') {
            $message = $v;
            continue;
        }
        if ($key === 'acceptance-953') {
            $v = $v !== '' ? 'Ja' : 'Nein';
        }
        $lines[] = "$label: $v";
    }
    foreach ($fields as $key => $v) {  // unbekannte Felder nicht verlieren
        if (!array_key_exists($key, $labels)) {
            $lines[] = "$key: " . (is_array($v) ? implode(', ', $v) : (string)$v);
        }
    }
    if ($stored_attachment !== null) {
        $lines[] = "Anhang: $stored_attachment (auf dem Server unter _nachrichten/ gespeichert)";
    }
    $out = implode("\n", $lines);
    if ($message !== null && $message !== '') {
        $out .= "\n\n------------------------------\nNachricht:\n" . $message;
    }
    return $out . "\n";
}

/** UTF-8-Mail, optional mit Datei-Anhang und eigenem Reply-To (z. B. Absender des Formulars). */
function send_mail(string $to, string $subject, string $body, ?array $attachment = null, ?string $reply_to = null): bool {
    $from = MAIL_FROM;
    $reply = $reply_to ?: MAIL_REPLY_TO;
    $envelope = '-f' . MAIL_FROM;
    $enc_subject = function_exists('mb_encode_mimeheader')
        ? mb_encode_mimeheader($subject, 'UTF-8', 'B')
        : '=?UTF-8?B?' . base64_encode($subject) . '?=';
    $headers = "From: SoftconCIS Website <$from>\r\nReply-To: $reply\r\n";
    if ($attachment === null) {
        $headers .= "Content-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: 8bit";
        return @mail($to, $enc_subject, $body, $headers, $envelope);
    }
    $boundary = 'b' . bin2hex(random_bytes(12));
    $headers .= "MIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary=\"$boundary\"";
    $file_b64 = chunk_split(base64_encode(file_get_contents($attachment['path'])));
    $fname = preg_replace('/[^\x20-\x7E]/', '_', $attachment['name']);
    $mime = "--$boundary\r\n"
        . "Content-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: 8bit\r\n\r\n"
        . $body . "\r\n"
        . "--$boundary\r\n"
        . "Content-Type: application/octet-stream; name=\"$fname\"\r\n"
        . "Content-Transfer-Encoding: base64\r\n"
        . "Content-Disposition: attachment; filename=\"$fname\"\r\n\r\n"
        . $file_b64 . "\r\n--$boundary--";
    return @mail($to, $enc_subject, $mime, $headers, $envelope);
}

function send_json(array $obj, int $code = 200): never {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($obj, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

/** Antwort sofort ausliefern, $after (z. B. langsamer Mailversand) danach ausführen. */
function send_json_then(array $obj, callable $after): never {
    $body = json_encode($obj, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    http_response_code(200);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    if (function_exists('fastcgi_finish_request')) {
        echo $body;
        fastcgi_finish_request();
    } else {
        ignore_user_abort(true);
        header('Connection: close');
        header('Content-Length: ' . strlen($body));
        echo $body;
        flush();
    }
    $after();
    exit;
}
