<?php
// GET /api/captcha/v1/challenge  (per .htaccess-Rewrite)
require __DIR__ . '/_lib.php';
send_json(make_challenge());
