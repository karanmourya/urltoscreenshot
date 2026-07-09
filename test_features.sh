#!/usr/bin/env bash
# Pixforge full feature test suite — run from project root.
set -u
B="http://127.0.0.1:10000"
K="Authorization: Bearer localkey"
pass=0; fail=0
log(){ echo "$1"; }
check(){ # desc expected_code actual_code extra
  local d="$1" ec="$2" ac="$3" extra="${4:-}"
  if [ "$ec" = "$ac" ]; then echo "PASS | $d (http $ac) ${extra}"; pass=$((pass+1));
  else echo "FAIL | $d (expected $ec, got $ac) ${extra}"; fail=$((fail+1)); fi
}

echo "=== AUTH ==="
check "no auth -> 401" 401 "$(curl -s -o /dev/null -w '%{http_code}' "$B/v1/devices")"
check "RapidAPI header path" 200 "$(curl -s -o /dev/null -w '%{http_code}' -H 'X-RapidAPI-Key: rk' "$B/v1/devices")"
check "Bearer admin path" 200 "$(curl -s -o /dev/null -w '%{http_code}' -H "$K" "$B/v1/devices")"

echo "=== DEVICES ==="
DC=$(curl -s -H "$K" "$B/v1/devices" | uv run python -c "import sys,json;print(json.load(sys.stdin)['count'])")
check "devices list returns >=100" 133 "$DC" ""

echo "=== SYNC IMAGE (jpeg) ==="
curl -s -H "$K" "$B/v1/screenshots/image?url=https://example.com&width=800&type=jpeg&quality=70" -o /tmp/t_img.jpg
SZ=$(wc -c < /tmp/t_img.jpg)
FT=$(file -b /tmp/t_img.jpg | cut -d, -f1)
check "image jpeg -> 200 + file>1KB" 200 "$([ "$SZ" -gt 1000 ] && echo 200 || echo 0)" "bytes=$SZ type=$FT"

echo "=== SYNC IMAGE (png) ==="
curl -s -H "$K" "$B/v1/screenshots/image?url=https://example.com&type=png" -o /tmp/t_img.png
check "image png -> 200 + file>1KB" 200 "$([ $(wc -c < /tmp/t_img.png) -gt 1000 ] && echo 200 || echo 0)" "bytes=$(wc -c < /tmp/t_img.png)"

echo "=== SYNC JSON ==="
JB=$(curl -s -H "$K" "$B/v1/screenshots/json?url=https://example.com&dark_mode=true&full_page=false" | uv run python -c "import sys,json,base64;d=json.load(sys.stdin);print(len(base64.b64decode(d['image'])))")
check "json -> 200 + image bytes" 200 "$([ "${JB:-0}" -gt 1000 ] && echo 200 || echo 0)" "bytes=$JB"

echo "=== PARAM: emulate_device (iPhone 14) ==="
curl -s -H "$K" "$B/v1/screenshots/image?url=https://example.com&emulate_device=iPhone%2014" -o /tmp/t_dev.jpg
check "emulate_device iPhone14 -> 200" 200 "$([ $(wc -c < /tmp/t_dev.jpg) -gt 1000 ] && echo 200 || echo 0)"

echo "=== PARAM: full_page + dark (png) ==="
curl -s -H "$K" "$B/v1/screenshots/image?url=https://example.com&full_page=true&dark_mode=true&type=png" -o /tmp/t_fd.png
check "full_page+dark png -> 200" 200 "$([ $(wc -c < /tmp/t_fd.png) -gt 1000 ] && echo 200 || echo 0)"

echo "=== PARAM: mobile ==="
curl -s -H "$K" "$B/v1/screenshots/image?url=https://example.com&mobile=true&width=390&height=844" -o /tmp/t_m.jpg
check "mobile viewport -> 200" 200 "$([ $(wc -c < /tmp/t_m.jpg) -gt 1000 ] && echo 200 || echo 0)"

echo "=== PARAM: delay + scale ==="
curl -s -H "$K" "$B/v1/screenshots/image?url=https://example.com&delay=200&scale=2" -o /tmp/t_ds.jpg
check "delay+scale -> 200" 200 "$([ $(wc -c < /tmp/t_ds.jpg) -gt 1000 ] && echo 200 || echo 0)"

echo "=== PDF ==="
curl -s -H "$K" "$B/v1/pdf?url=https://example.com&format=Letter&landscape=true" -o /tmp/t.pdf
PDSZ=$(wc -c < /tmp/t.pdf); PDFT=$(file -b /tmp/t.pdf | cut -d, -f1)
check "pdf -> 200 + valid" 200 "$([ "$PDFT" = "PDF document" ] && echo 200 || echo 0)" "bytes=$PDSZ type=$PDFT"

echo "=== BATCH (2 urls) ==="
BR=$(curl -s -H "$K" -H "Content-Type: application/json" -X POST "$B/v1/batch" -d '{"requests":[{"url":"https://example.com"},{"url":"https://example.org"}]}')
BOUT=$(echo "$BR" | uv run python -c "import sys,json;d=json.load(sys.stdin);print(d['total'],d['successful'],d['failed'])")
check "batch 2 -> total2 ok2 fail0" 200 "$(echo $BOUT | grep -q '2 2 0' && echo 200 || echo 0)" "$BOUT"

echo "=== BATCH limit (11 -> 422) ==="
BIG='{"requests":['; for i in $(seq 1 11); do BIG="$BIG{\"url\":\"https://example.com\"}"; [ $i -lt 11 ] && BIG="$BIG,"; done; BIG="$BIG]}"
check "batch >10 -> 422" 422 "$(curl -s -o /dev/null -w '%{http_code}' -H "$K" -H "Content-Type: application/json" -X POST "$B/v1/batch" -d "$BIG")"

echo "=== ERROR: bad url (ftp) -> 400 ==="
check "bad url -> 400" 400 "$(curl -s -o /dev/null -w '%{http_code}' -H "$K" "$B/v1/screenshots/json?url=ftp://x.com")"

echo "=== ERROR: unknown device -> 400 ==="
check "unknown device -> 400" 400 "$(curl -s -o /dev/null -w '%{http_code}' -H "$K" "$B/v1/screenshots/image?url=https://example.com&emulate_device=Nope")"

echo "=== ERROR: bad quality -> 400 ==="
check "quality=200 -> 400" 400 "$(curl -s -o /dev/null -w '%{http_code}' -H "$K" "$B/v1/screenshots/json?url=https://example.com&quality=200")"

echo "=== ASYNC job ==="
J=$(curl -s -H "$K" -H "Content-Type: application/json" -X POST "$B/v1/async/screenshots/image" -d '{"url":"https://example.com","options":{"width":600}}')
T=$(echo "$J" | uv run python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
JID=$(echo "$J" | uv run python -c "import sys,json;print(json.load(sys.stdin)['job_id'])")
check "async submit -> 202" 202 "$(echo "$J" | grep -q job_id && echo 202 || echo 0)"
# poll
ST="pending"
for i in $(seq 1 15); do
  R=$(curl -s -H "Authorization: Bearer $T" "$B/v1/jobs/$JID")
  ST=$(echo "$R" | uv run python -c "import sys,json;print(json.load(sys.stdin).get('status'))" 2>/dev/null)
  [ "$ST" = "completed" ] && break; sleep 1
done
check "async job completes" "completed" "$ST"
FR=$(curl -s -H "Authorization: Bearer $T" "$B/v1/jobs/$JID" | uv run python -c "import sys,json;d=json.load(sys.stdin);print('done' if d['status']=='completed' and d['result'] else 'fail')")
check "async result has image" "done" "$FR"

echo "=== ASYNC wrong token -> 403 ==="
check "wrong job token -> 403" 403 "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer badtok" "$B/v1/jobs/$JID")"

echo "=== ASYNC unknown job -> 404 ==="
check "unknown job -> 404" 404 "$(curl -s -o /dev/null -w '%{http_code}' -H "$K" "$B/v1/jobs/doesnotexist")"

echo "=== RATE LIMIT (10/min) ==="
N=0; for i in $(seq 1 13); do C=$(curl -s -o /dev/null -w '%{http_code}' -H "$K" "$B/v1/devices"); [ "$C" = "429" ] && N=$((N+1)); done
check "rate limit blocks after 10" 3 "$N" "429s=$N (expect>=1)"
HL=$(curl -s -D - -o /dev/null -H "$K" "$B/v1/devices" | tr -d '\r' | grep -ci x-ratelimit)
check "X-RateLimit headers present" 3 "$HL" "headers=$HL"

echo ""
echo "==================== SUMMARY ===================="
echo "PASS=$pass  FAIL=$fail"
