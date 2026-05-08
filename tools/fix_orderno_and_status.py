#!/usr/bin/env python3
"""원본사이트에서 order_no / status / process_date 가져와 DB UPDATE.

대상: order_no IS NULL 인 행 (= INSERT 단계에서 누락된 것 + 옛 마이그레이션 잔존).
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

VALID_STATUS = {"접수","진행","센터","견적","택배","완료","출고"}

P_ORDER_NO   = re.compile(r"접수번호\s*</td>\s*<td[^>]*>\s*(?:&nbsp;|\s)*(\d{6}-\d{1,4})")
P_STATUS_1   = re.compile(r'<td[^>]*>\s*(?:&nbsp;|\s)*현황\s*</td>\s*<td[^>]*>\s*(?:&nbsp;|\s)*([가-힣]{2,4})')
P_STATUS_2   = re.compile(r'name=["\']?re_now["\']?[^>]*value=["\']([^"\']+)["\'][^>]*\bchecked', re.IGNORECASE)
P_PROC_DATE  = re.compile(r"변경/처리\s*일자\s*</td>\s*<td[^>]*>\s*(?:&nbsp;|\s)*(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)")

def parse_proc_date(s):
    """'2017년 10월 31일' → '2017/10/31'."""
    if not s: return None
    m = re.match(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", s)
    if not m: return None
    y, mo, d = m.groups()
    return f"{y}/{int(mo):02d}/{int(d):02d}"

def fetch_orig_meta(seq):
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
    out = {}
    m = P_ORDER_NO.search(html)
    if m: out["order_no"] = m.group(1)
    m = P_STATUS_1.search(html)
    if not m or m.group(1) not in VALID_STATUS:
        m = P_STATUS_2.search(html)
    if m and m.group(1) in VALID_STATUS:
        out["status"] = m.group(1)
    m = P_PROC_DATE.search(html)
    if m:
        d = parse_proc_date(m.group(1))
        if d: out["process_date"] = d
    return out

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

    print("[1/2] 대상 seq 조회 (order_no IS NULL) ...", flush=True)
    targets = []
    offset = 0
    PAGE = 1000
    while True:
        params = {
            "select": "seq_no,status",
            "order_no": "is.null",
            "order":  "seq_no.asc",
            "limit":  str(PAGE),
            "offset": str(offset),
        }
        url = f"{base_url}/rest/v1/orders?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=H)
        with urllib.request.urlopen(req, timeout=30) as r:
            chunk = json.loads(r.read())
        if not chunk: break
        targets.extend(chunk)
        offset += len(chunk)
        if len(chunk) < PAGE: break
    print(f"  → {len(targets)} 건", flush=True)

    if args.limit and len(targets) > args.limit:
        targets = targets[:args.limit]
        print(f"  --limit {args.limit}", flush=True)

    if not args.apply:
        print(f"\n[dry-run] {len(targets)}건 대상. --apply 없이 종료.")
        return

    print(f"\n[2/2] fetch + UPDATE ...", flush=True)
    counter = [0]
    ok = err = no_change = no_data = 0
    by_status = {}
    lock = threading.Lock()
    t0 = time.time()

    def worker(rec):
        nonlocal ok, err, no_change, no_data
        seq = rec["seq_no"]
        cur_status = rec.get("status")
        try:
            meta = fetch_orig_meta(seq)
        except Exception:
            with lock:
                err += 1
                counter[0] += 1
            return
        if not meta:
            with lock:
                no_data += 1
                counter[0] += 1
            return
        # 변경할 필드만 추려서 PATCH
        patch = {}
        if "order_no" in meta:
            patch["order_no"] = meta["order_no"]
        if "status" in meta and meta["status"] != cur_status:
            patch["status"] = meta["status"]
            patch["re_now"] = meta["status"]
        if "process_date" in meta:
            patch["process_date"] = meta["process_date"]
        if not patch:
            with lock:
                no_change += 1
                counter[0] += 1
            return
        url = f"{base_url}/rest/v1/orders?seq_no=eq.{seq}"
        h = {**H, "Content-Type":"application/json", "Prefer":"return=minimal"}
        body = json.dumps(patch, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=h, method="PATCH")
        try:
            with urllib.request.urlopen(req, timeout=30) as r: pass
            with lock:
                ok += 1
                if "status" in patch:
                    by_status[patch["status"]] = by_status.get(patch["status"], 0) + 1
                counter[0] += 1
                if counter[0] % 100 == 0:
                    elapsed = time.time() - t0
                    rate = counter[0] / elapsed if elapsed else 0
                    eta = (len(targets) - counter[0]) / rate if rate else 0
                    print(f"  {counter[0]}/{len(targets)} ok={ok} no_data={no_data} no_change={no_change} err={err} {elapsed:.0f}s rate={rate:.1f}/s eta={eta:.0f}s", flush=True)
        except Exception:
            with lock:
                err += 1
                counter[0] += 1

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(worker, targets))

    print(f"\n[done] ok={ok} no_change={no_change} no_data={no_data} err={err}  ({time.time()-t0:.0f}s)")
    print(f"  status 변경 분포: {by_status}")

if __name__ == "__main__":
    main()
