#!/usr/bin/env python3
"""원본사이트의 '현황' 셀에서 정확한 status 가져와 DB UPDATE.

대상: DB.status = '접수' AND seq_no < 50000 (옛 레코드, INSERT 단계에서 fallback 됐을 것).
4/30 이후 신규 입력 행은 영향 없음 (seq_no 가 5만대 후반).
"""
import os, sys, json, re, time, threading, argparse, urllib.parse
import urllib.request, urllib.error, http.cookiejar
from concurrent.futures import ThreadPoolExecutor

BASE_ORIG = "http://wolf-fox.dreamtec.co.kr/pacai2/admin/as"
LOGIN     = f"{BASE_ORIG}/admin_login.php"
DETAIL    = f"{BASE_ORIG}/as_uform.php"

WORKERS = 8

_local = threading.local()
def session():
    if not hasattr(_local, "op"):
        cj = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        op.addheaders = [("User-Agent","Mozilla/5.0")]
        op.open(LOGIN, urllib.parse.urlencode({"ID":"wolffox","password":"1129"}).encode(), timeout=30).read()
        _local.op = op
    return _local.op

# 현황 셀: "<td>현황</td><td>[ status ]</td>"
P_STATUS_1 = re.compile(r'<td[^>]*>\s*(?:&nbsp;|\s)*현황\s*</td>\s*<td[^>]*>\s*(?:&nbsp;|\s)*([가-힣]{2,4})', re.IGNORECASE)
# 폴백: 라디오 checked
P_STATUS_2 = re.compile(r'name=["\']?re_now["\']?[^>]*value=["\']([^"\']+)["\'][^>]*\bchecked', re.IGNORECASE)

VALID = {"접수","진행","센터","견적","택배","완료","출고"}

def fetch_status(seq):
    op = session()
    url = f"{DETAIL}?seq_no={seq}"
    for i in range(3):
        try:
            with op.open(url, timeout=30) as r:
                html = r.read().decode("euc-kr", errors="replace")
            break
        except Exception:
            if i == 2: raise
            time.sleep(0.5)
    m = P_STATUS_1.search(html)
    if m and m.group(1) in VALID:
        return m.group(1)
    m = P_STATUS_2.search(html)
    if m and m.group(1) in VALID:
        return m.group(1)
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    sb_url = os.environ.get("SUPABASE_URL")
    sb_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not sb_url or not sb_key: sys.exit("환경변수 필요")
    base_url = sb_url.rstrip("/")
    H = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}

    # 대상 seq 조회
    print("[1/2] 대상 seq 조회 ...", flush=True)
    targets = []
    offset = 0
    PAGE = 1000
    while True:
        params = {
            "select": "seq_no",
            "status": "eq.접수",
            "seq_no": "lt.50000",
            "order":  "seq_no.asc",
            "limit":  str(PAGE),
            "offset": str(offset),
        }
        url = f"{base_url}/rest/v1/orders?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=H)
        with urllib.request.urlopen(req, timeout=30) as r:
            chunk = json.loads(r.read())
        if not chunk: break
        targets.extend(int(r["seq_no"]) for r in chunk)
        offset += len(chunk)
        if len(chunk) < PAGE: break
    print(f"  → {len(targets)} 건", flush=True)

    if args.limit and len(targets) > args.limit:
        targets = targets[:args.limit]
        print(f"  --limit {args.limit}", flush=True)

    if not args.apply:
        print(f"\n[dry-run] {len(targets)}건 대상. --apply 없이 종료.")
        return

    print(f"\n[2/2] 원본 fetch + UPDATE 시작 ...", flush=True)
    counter = [0]
    ok = err = unchanged = unknown = 0
    by_status = {}
    lock = threading.Lock()
    t0 = time.time()

    def worker(seq):
        nonlocal ok, err, unchanged, unknown
        try:
            st = fetch_status(seq)
        except Exception as e:
            with lock:
                err += 1
                counter[0] += 1
            return
        if not st:
            with lock:
                unknown += 1
                counter[0] += 1
                if counter[0] % 100 == 0:
                    elapsed = time.time() - t0
                    print(f"  {counter[0]}/{len(targets)} ok={ok} unchanged={unchanged} unknown={unknown} err={err} ({elapsed:.0f}s)", flush=True)
            return
        if st == "접수":
            with lock:
                unchanged += 1
                counter[0] += 1
            return
        # UPDATE
        url = f"{base_url}/rest/v1/orders?seq_no=eq.{seq}"
        h = {**H, "Content-Type":"application/json", "Prefer":"return=minimal"}
        body = json.dumps({"status": st, "re_now": st}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=h, method="PATCH")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                pass
            with lock:
                ok += 1
                by_status[st] = by_status.get(st, 0) + 1
                counter[0] += 1
                if counter[0] % 100 == 0:
                    elapsed = time.time() - t0
                    rate = counter[0] / elapsed if elapsed else 0
                    eta = (len(targets) - counter[0]) / rate if rate else 0
                    print(f"  {counter[0]}/{len(targets)} ok={ok} unchanged={unchanged} unknown={unknown} err={err} {elapsed:.0f}s rate={rate:.1f}/s eta={eta:.0f}s", flush=True)
        except Exception as e:
            with lock:
                err += 1
                counter[0] += 1

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(worker, targets))

    print(f"\n[done] ok={ok} unchanged={unchanged} unknown={unknown} err={err}  ({time.time()-t0:.0f}s)")
    print(f"  status 분포 (변경된 것): {by_status}")

if __name__ == "__main__":
    main()
