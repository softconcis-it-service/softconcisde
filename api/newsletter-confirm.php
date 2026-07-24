<?php
// GET /newsletter-bestaetigung?t=<id>&e=<expires>&s=<hmac>  (per .htaccess-Rewrite)
// Double-Opt-In-Bestätigung: prüft den signierten Link, markiert die Anmeldung
// als bestätigt und schickt erst dann die Admin-Benachrichtigung.
require __DIR__ . '/_lib.php';

$t = preg_replace('/[^a-f0-9]/', '', $_GET['t'] ?? '');
$e = (int)($_GET['e'] ?? 0);
$s = (string)($_GET['s'] ?? '');

$pending = messages_dir() . "/newsletter-pending_$t.json";
$confirmed = messages_dir() . "/newsletter-bestaetigt_$t.json";

$valid = $t !== '' && $e > 0
    && hash_equals(hash_hmac('sha256', "newsletter|$t|$e", get_secret()), $s);

// Sprache: aus dem Datensatz, sonst Browser
$lang = 'de';
foreach ([$pending, $confirmed] as $f) {
    if (is_file($f)) {
        $rec = json_decode(file_get_contents($f), true) ?: [];
        $lang = $rec['sprache'] ?? 'de';
        break;
    }
}
if (!isset($rec) && str_starts_with($_SERVER['HTTP_ACCEPT_LANGUAGE'] ?? '', 'en')) {
    $lang = 'en';
}

$texts = [
    'de' => [
        'ok_title' => 'Anmeldung bestätigt',
        'ok_body' => 'Vielen Dank! Ihre Newsletter-Anmeldung ist damit abgeschlossen.',
        'again_title' => 'Bereits bestätigt',
        'again_body' => 'Diese Anmeldung wurde bereits bestätigt — es ist nichts weiter zu tun.',
        'err_title' => 'Link ungültig oder abgelaufen',
        'err_body' => 'Dieser Bestätigungslink ist ungültig oder abgelaufen. Bitte melden Sie sich einfach erneut über das Formular an.',
        'back' => 'Zur Startseite',
        'newsletter' => 'Zur Newsletter-Anmeldung',
    ],
    'en' => [
        'ok_title' => 'Subscription confirmed',
        'ok_body' => 'Thank you! Your newsletter subscription is now complete.',
        'again_title' => 'Already confirmed',
        'again_body' => 'This subscription has already been confirmed — nothing more to do.',
        'err_title' => 'Link invalid or expired',
        'err_body' => 'This confirmation link is invalid or has expired. Please simply sign up again using the form.',
        'back' => 'Back to homepage',
        'newsletter' => 'To the newsletter form',
    ],
][$lang];

$base = site_base_url();
$nl_path = $lang === 'en' ? '/en/newsletter/' : '/newsletter/';

if (!$valid || $e < time()) {
    render_page($texts['err_title'], $texts['err_body'], $base . $nl_path, $texts['newsletter'], 410);
}
if (is_file($confirmed)) {
    render_page($texts['again_title'], $texts['again_body'], $base . '/', $texts['back']);
}
if (!is_file($pending)) {
    render_page($texts['err_title'], $texts['err_body'], $base . $nl_path, $texts['newsletter'], 410);
}

$rec = json_decode(file_get_contents($pending), true) ?: [];
$rec['status'] = 'bestaetigt';
$rec['bestaetigt_am'] = date('Y-m-d H:i:s');  // DSGVO-Nachweis des Double-Opt-In
$rec['bestaetigt_ip'] = $_SERVER['REMOTE_ADDR'] ?? '';
write_message($confirmed, $rec);
unlink($pending);

// Admin-Benachrichtigung für Newsletter vorerst AUS (Testphase) — bestätigte
// Anmeldungen liegen als JSON unter _nachrichten/newsletter-bestaetigt_*.json.
// Zum Aktivieren: NEWSLETTER_NOTIFY auf true setzen.
const NEWSLETTER_NOTIFY = false;
if (NEWSLETTER_NOTIFY && MAIL_TO !== '') {
    $body = format_fields($rec['felder'] ?? [])
        . "\nAngemeldet: {$rec['eingegangen']}\nBestätigt (Double-Opt-In): {$rec['bestaetigt_am']}\n";
    send_mail(MAIL_TO, 'Neue Nachricht über das Formular "Newsletter"', $body);
}

render_page($texts['ok_title'], $texts['ok_body'], $base . '/', $texts['back']);

function render_page(string $title, string $body, string $link, string $link_text, int $code = 200): never {
    http_response_code($code);
    header('Content-Type: text/html; charset=utf-8');
    $t = htmlspecialchars($title);
    $b = htmlspecialchars($body);
    $l = htmlspecialchars($link);
    $lt = htmlspecialchars($link_text);
    echo <<<HTML
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>$t – SoftconCIS</title>
<style>
  body { font-family: system-ui, -apple-system, sans-serif; background: #f5f5f5; margin: 0;
         display: flex; min-height: 100vh; align-items: center; justify-content: center; }
  .card { background: #fff; border-top: 4px solid #86bc25; border-radius: 6px; padding: 40px 44px;
          max-width: 520px; margin: 20px; box-shadow: 0 2px 12px rgba(0,0,0,.08); }
  h1 { font-size: 24px; margin: 0 0 12px; color: #222; }
  p { color: #444; line-height: 1.5; }
  a { display: inline-block; margin-top: 18px; color: #fff; background: #86bc25; text-decoration: none;
      padding: 10px 22px; border-radius: 4px; font-weight: 600; }
  a:hover { background: #76a621; }
</style>
</head>
<body><div class="card"><h1>$t</h1><p>$b</p><a href="$l">$lt</a></div></body>
</html>
HTML;
    exit;
}
