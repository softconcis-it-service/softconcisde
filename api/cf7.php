<?php
// POST /api/forms/v1/contact-forms/<id>/feedback  (per .htaccess-Rewrite)
// Validiert das ALTCHA-Captcha, speichert die Nachricht als JSON unter _nachrichten/
// und leitet sie per E-Mail weiter. Newsletter-Formulare laufen über Double-Opt-In:
// erst nach Klick auf den Bestätigungslink (api/newsletter-confirm.php) geht die
// Nachricht an den Admin.
require __DIR__ . '/_lib.php';

const MESSAGES = [
    'de' => [
        'sent' => 'Vielen Dank für Ihre Nachricht. Sie wurde versandt.',
        'doi' => 'Fast geschafft! Wir haben Ihnen eine E-Mail geschickt — bitte bestätigen Sie Ihre Anmeldung über den Link darin.',
        'spam' => 'Die Anti-Spam-Prüfung ist fehlgeschlagen. Bitte bestätigen Sie „Ich bin kein Roboter“ und versuchen Sie es erneut.',
        'rate' => 'Zu viele Anfragen. Bitte versuchen Sie es später erneut.',
    ],
    'en' => [
        'sent' => 'Thank you for your message. It has been sent.',
        'doi' => 'Almost done! We have sent you an email — please confirm your subscription via the link inside.',
        'spam' => 'The anti-spam check failed. Please confirm “I am not a robot” and try again.',
        'rate' => 'Too many requests. Please try again later.',
    ],
];

// Formular-ID → Name (für den Betreff), Sprache, Double-Opt-In
const FORMS = [
    669  => ['name' => 'Kontakt',       'lang' => 'de'],
    2510 => ['name' => 'Kontakt',       'lang' => 'en'],
    1297 => ['name' => 'Demo anfragen', 'lang' => 'de'],
    2512 => ['name' => 'Demo anfragen', 'lang' => 'en'],
    419  => ['name' => 'Karriere',      'lang' => 'de'],
    2490 => ['name' => 'Karriere',      'lang' => 'en'],
    1428 => ['name' => 'Newsletter',    'lang' => 'de', 'doi' => true],
    2520 => ['name' => 'Newsletter',    'lang' => 'en', 'doi' => true],
];

const UPLOAD_MAX_BYTES = 8 * 1024 * 1024;  // Anhänge bis 8 MB mitschicken

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    send_json(['code' => 'rest_no_route', 'message' => 'Not found'], 404);
}

$form_id = (int)preg_replace('/\D/', '', $_GET['form'] ?? '');
if ($form_id === 0) {
    send_json(['code' => 'rest_no_route', 'message' => 'Not found'], 404);
}
$form = FORMS[$form_id] ?? ['name' => "Formular $form_id", 'lang' => null];

$fields = $_POST; // PHP parst multipart/form-data und urlencoded selbst

$locale = $fields['_scf7_locale'] ?? 'de_DE';
$lang = $form['lang'] ?? (str_starts_with($locale, 'en') ? 'en' : 'de');
$unit_tag = $fields['_scf7_unit_tag'] ?? '';
$base = [
    'contact_form_id' => $form_id,
    'into' => $unit_tag !== '' ? '#' . $unit_tag : '',
    'posted_data_hash' => '',
    'invalid_fields' => [],
];

$ip = $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
if (rate_limited($ip)) {
    send_json($base + ['status' => 'spam', 'message' => MESSAGES[$lang]['rate']]);
}

$payload = $fields['altcha'] ?? $fields['_altcha'] ?? '';
[$ok, $reason] = $payload !== '' ? verify_altcha($payload) : [false, 'missing'];
if (!$ok) {
    error_log("ALTCHA abgelehnt ($reason) von $ip");
    send_json($base + ['status' => 'spam', 'message' => MESSAGES[$lang]['spam']]);
}

// Nachricht speichern (Verzeichnis ist per .htaccess gegen Abruf gesperrt)
$msg_dir = messages_dir();
$stamp = date('Y-m-d_His');
$record = [
    'eingegangen' => date('Y-m-d H:i:s'),
    'formular' => $form['name'],
    'formular_id' => $form_id,
    'sprache' => $lang,
    'seite' => $_SERVER['HTTP_REFERER'] ?? '',
    'felder' => array_filter(
        $fields,
        fn($v, $k) => !str_starts_with($k, '_') && $k !== 'altcha',
        ARRAY_FILTER_USE_BOTH
    ),
];

// Datei-Upload (Karriere-Formular): mit abspeichern und später anhängen
$attachment = null;
foreach ($_FILES as $fkey => $file) {
    if (($file['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK) {
        continue;
    }
    $orig = basename((string)$file['name']);
    $safe = preg_replace('/[^A-Za-z0-9._-]/', '_', $orig) ?: 'anhang';
    $dest = $msg_dir . '/' . $stamp . "_form{$form_id}_" . $safe;
    if (move_uploaded_file($file['tmp_name'], $dest)) {
        $record['anhang'] = basename($dest);
        if (filesize($dest) <= UPLOAD_MAX_BYTES) {
            $attachment = ['path' => $dest, 'name' => $orig];
        }
    }
}

if (!empty($form['doi'])) {
    // ---- Newsletter: Double-Opt-In ----
    $token_id = bin2hex(random_bytes(16));
    $record['status'] = 'unbestaetigt';
    write_message($msg_dir . "/newsletter-pending_$token_id.json", $record);

    $email = trim((string)($record['felder']['email-322'] ?? ''));
    if ($email === '' || !filter_var($email, FILTER_VALIDATE_EMAIL)) {
        send_json($base + ['status' => 'validation_failed', 'invalid_fields' => [
            ['field' => 'email-322', 'message' => $lang === 'en' ? 'Please enter a valid email address.' : 'Bitte geben Sie eine gültige E-Mail-Adresse an.', 'idref' => null, 'error_id' => ''],
        ], 'message' => $lang === 'en' ? 'One or more fields have an error.' : 'Ein oder mehrere Felder haben einen Fehler.']);
    }

    $expires = time() + 7 * 86400;
    $sig = hash_hmac('sha256', "newsletter|$token_id|$expires", get_secret());
    $confirm_url = site_base_url() . "/newsletter-bestaetigung?t=$token_id&e=$expires&s=$sig";

    if ($lang === 'en') {
        $subject = 'Please confirm your newsletter subscription';
        $body = "Hello,\n\nthank you for your interest in the SoftconCIS newsletter.\n\n"
            . "Please confirm your subscription by clicking this link (valid for 7 days):\n\n$confirm_url\n\n"
            . "If you did not request this subscription, simply ignore this email — nothing will be stored or sent.\n\n"
            . "Best regards\nSoftconCIS GmbH";
    } else {
        $subject = 'Bitte bestätigen Sie Ihre Newsletter-Anmeldung';
        $body = "Guten Tag,\n\nvielen Dank für Ihr Interesse am SoftconCIS-Newsletter.\n\n"
            . "Bitte bestätigen Sie Ihre Anmeldung über diesen Link (7 Tage gültig):\n\n$confirm_url\n\n"
            . "Falls Sie sich nicht angemeldet haben, ignorieren Sie diese E-Mail einfach — es wird nichts gespeichert oder versandt.\n\n"
            . "Freundliche Grüße\nSoftconCIS GmbH";
    }
    send_json_then($base + ['status' => 'mail_sent', 'message' => MESSAGES[$lang]['doi']],
        fn() => send_mail($email, $subject, $body));
}

// ---- Übrige Formulare: speichern + direkt an den Admin ----
write_message($msg_dir . "/{$stamp}_form$form_id.json", $record);

send_json_then($base + ['status' => 'mail_sent', 'message' => MESSAGES[$lang]['sent']], function () use ($form, $record, $attachment) {
    if (MAIL_TO !== '') {
        // Reply-To = Absender des Formulars, damit "Antworten" direkt an ihn geht
        $sender = trim((string)($record['felder']['email-322'] ?? ''));
        send_mail(MAIL_TO, 'Neue Nachricht über das Formular "' . $form['name'] . '"',
            format_fields($record['felder'], $record['anhang'] ?? null), $attachment,
            filter_var($sender, FILTER_VALIDATE_EMAIL) ? $sender : null);
    }
});
