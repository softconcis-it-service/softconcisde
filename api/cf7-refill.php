<?php
// GET /api/forms/v1/contact-forms/<id>/refill (per Rewrite)
// CF7 ruft das nach erfolgreichem Versand auf und zeigt die Erfolgsmeldung
// erst nach dieser Antwort an (der Server liefert für unsere Formulare "[]").
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
echo '[]';
