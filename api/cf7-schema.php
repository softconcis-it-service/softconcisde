<?php
// GET /api/forms/v1/contact-forms/<id>/feedback/schema (per Rewrite)
// Liefert das swv-Validierungsschema (1:1 vom Original übernommen).
// Ohne diese Antwort bricht die CF7-Submit-Pipeline ab (Formular hängt in "submitting").
$form_id = preg_replace('/\D/', '', $_GET['form'] ?? '');
$file = __DIR__ . "/schema/$form_id.json";
header('Cache-Control: no-store');
if ($form_id === '' || !is_file($file)) {
    http_response_code(404);
    header('Content-Type: application/json; charset=utf-8');
    echo '{"code":"rest_no_route","message":"Not found"}';
    exit;
}
header('Content-Type: application/json; charset=utf-8');
readfile($file);
