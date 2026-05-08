#!/usr/bin/env python3
"""원본사이트의 모든 접수 seq_no 수집 → DB 와 차이 → 누락분 fetch + insert.

기존 DB 행은 절대 안 건드림 (INSERT only).
"""
import os, sys, json, re, time, threading, argparse, urllib.parse
import urllib.request, urllib.error, http.cookiejar
from concurrent.futures import ThreadPoolExecutor

BASE_ORIG = "http://wolf-fox.dreamtec.co.kr/pacai2/admin/as"
LOGIN     = f"{BASE_ORIG}/admin_login.php"
LIST      = f"{BASE_ORIG}/as_list.php"
DETAIL    = f"{BASE_ORIG}/as_uform.php"

WORKERS_LIST = 8
WORKERS_FETCH = 6

_local = threading.local()
def session():
    if not hasattr(_local, "op"):
        cj = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        op.addheaders = [("User-Agent","Mozilla/5.0")]
        op.open(LOGIN, urllib.parse.urlencode({"ID":"wolffox","password":"1129"}).encode(), timeout=30).read()
        _local.op = op
    return _local.op

def fetch_orig(url, retries=3):
    for i in range(retries):
        try:
            with session().open(url, timeout=30) as r:
                return r.read().decode("euc-kr", errors="replace")
        except Exception:
            if i == retries-1: raise
            time.sleep(0.5*(i+1))

# ---------- 원본 페이지에서 seq_no 추출 ----------
def collect_page(start):
    url = f"{LIST}?start={start}"
    html = fetch_orig(url)
    return set(re.findall(r"seq_no=(\d+)", html))

def collect_all_orig_seqs():
    # 첫 페이지로 총 건수
    html = fetch_orig(f"{LIST}?start=0")
    m = re.search(r"게시물.*?([0-9,]+)", html)
    total = int(m.group(1).replace(",","")) if m else 0
    PAGE = 15
    pages = (total + PAGE - 1) // PAGE
    print(f"  원본 총 게시물: {total}, 페이지: {pages}")
    all_seqs = set()
    starts = [p * PAGE for p in range(pages)]
    done = [0]
    lock = threading.Lock()
    def worker(s):
        try:
            seqs = collect_page(s)
            with lock:
                all_seqs.update(seqs)
                done[0] += 1
                # 50 페이지마다 진행 출력 + 파일에 상태 저장
                if done[0] % 50 == 0:
                    print(f"    {done[0]}/{pages} pages, {len(all_seqs)} seqs", flush=True)
                    try:
                        with open(os.path.join(os.path.dirname(__file__), "..", "..", "new-project-management", "web", "data", "all_missing_progress.txt"), "w", encoding="utf-8") as fp:
                            fp.write(f"pages: {done[0]}/{pages}, seqs: {len(all_seqs)}\n")
                    except Exception: pass
        except Exception as e:
            print(f"    page start={s} err: {e}", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=WORKERS_LIST) as ex:
        list(ex.map(worker, starts))
    return total, sorted(int(s) for s in all_seqs)

# ---------- 파싱 (이전 스크립트와 동일) ----------
def get_value(html, field):
    m = re.search(r'<input[^>]*\bname=["\']' + re.escape(field) + r'["\'][^>]*\bvalue=["\']([^"\']*)["\']', html, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'<input[^>]*\bvalue=["\']([^"\']*)["\'][^>]*\bname=["\']' + re.escape(field) + r'["\']', html, re.IGNORECASE)
    return m.group(1) if m else ""

def get_checked_radio(html, name):
    for p in [
        r'<input[^>]*\btype=["\']?radio["\']?[^>]*\bname=["\']?' + re.escape(name) + r'["\']?[^>]*\bvalue=["\']([^"\']+)["\'][^>]*\bchecked',
        r'<input[^>]*\bname=["\']?' + re.escape(name) + r'["\']?[^>]*\bvalue=["\']([^"\']+)["\'][^>]*\bchecked',
        r'<input[^>]*\bchecked[^>]*\bname=["\']?' + re.escape(name) + r'["\']?[^>]*\bvalue=["\']([^"\']+)["\']',
    ]:
        m = re.search(p, html, re.IGNORECASE)
        if m: return m.group(1)
    return ""

def get_textarea(html, name):
    m = re.search(r'<textarea[^>]*\bname=["\']?' + re.escape(name) + r'["\']?[^>]*>(.*?)</textarea>', html, re.DOTALL | re.IGNORECASE)
    if not m: return ""
    text = re.sub(r'<[^>]+>', '', m.group(1))
    return text.replace('&nbsp;',' ').replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&quot;','"').strip()

P_DISPLAY = re.compile(r'<td\s+colspan=3\s+bgcolor="#ffffff"\s+style="padding:0 0 0 20px">(.*?)</textarea>\s*</td>', re.IGNORECASE | re.DOTALL)
P_HIDDEN  = re.compile(r'<input[^>]*\btype=["\']?hidden["\']?[^>]*\bname=["\']?re_content["\']?[^>]*\bvalue=["\']([^"\']*)["\']', re.IGNORECASE)
def extract_re_content(html):
    m = P_HIDDEN.search(html)
    if m and m.group(1).strip():
        return m.group(1).replace('&nbsp;',' ').replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&quot;','"').strip()
    m = P_DISPLAY.search(html)
    if m: return m.group(1).replace('&nbsp;',' ').replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&quot;','"').strip()
    return ""

PHONE_FIELDS = [
    ("cu_tel",    ["cu_tel1","cu_tel2","cu_tel3"]),
    ("cu_mobile", ["cu_mobile1","cu_mobile2","cu_mobile3"]),
    ("co_tel",    ["co_tel1","co_tel2","co_tel3"]),
    ("co_fax",    ["co_fax1","co_fax2","co_fax3"]),
]

def extract_full(html, seq_no):
    rec = {
        "seq_no":       seq_no,
        "en_gubun":     get_value(html, "en_gubun"),
        "cu_number":    get_value(html, "cu_number_old") or get_value(html, "cu_number"),
        "cu_kind":      get_value(html, "cu_kind"),
        "or_kind1":     get_value(html, "or_kind1"),
        "or_kind2":     get_checked_radio(html, "or_kind2") or get_value(html, "or_kind2"),
        "or_kind3":     get_checked_radio(html, "or_kind3") or get_value(html, "or_kind3"),
        "cu_name":      get_value(html, "cu_name"),
        "co_name":      get_value(html, "co_name"),
        "cu_mail":      get_value(html, "cu_mail"),
        "zipcode1":     get_value(html, "zipcode1"),
        "address1":     get_value(html, "address1"),
        "address2":     get_value(html, "address2"),
        "mo_number":    get_value(html, "mo_number"),
        "mo_engname":   get_value(html, "mo_engname"),
        "mo_serial":    get_value(html, "mo_serial"),
        "mo_srfr":      get_value(html, "mo_srfr"),
        "mo_number2":   get_value(html, "mo_number2"),
        "mo_engname2":  get_value(html, "mo_engname2"),
        "mo_money2":    get_value(html, "mo_money2"),
        "trip_money":   get_value(html, "trip_money"),
        "gongim_money": get_value(html, "gongim_money"),
        "work_name":    get_value(html, "work_name"),
        "re_now":       get_checked_radio(html, "re_now"),
        "cu_want":      get_textarea(html, "cu_want"),
        "re_content":   extract_re_content(html),
    }
    for combined, parts in PHONE_FIELDS:
        vals = [get_value(html, p) for p in parts]
        rec[combined] = "-".join(v for v in vals if v) if any(vals) else ""
    return rec

def to_db_row(rec):
    status = rec.get("re_now") or "접수"
    return {
        "seq_no":       rec["seq_no"],
        "branch":       rec.get("en_gubun") or "대구",
        "cu_number":    rec.get("cu_number") or None,
        "cu_kind":      rec.get("cu_kind") or "",
        "or_kind1":     rec.get("or_kind1") or "",
        "or_kind2":     rec.get("or_kind2") or "",
        "or_kind3":     rec.get("or_kind3") or "",
        "kind2":        rec.get("or_kind3") or "출장",
        "cu_name":      rec.get("cu_name") or "",
        "co_name":      rec.get("co_name") or "",
        "cu_mail":      rec.get("cu_mail") or "",
        "zipcode1":     rec.get("zipcode1") or "",
        "address1":     rec.get("address1") or "",
        "address2":     rec.get("address2") or "",
        "cu_tel":       rec.get("cu_tel") or "",
        "cu_mobile":    rec.get("cu_mobile") or "",
        "co_tel":       rec.get("co_tel") or "",
        "co_fax":       rec.get("co_fax") or "",
        "mo_number":    rec.get("mo_number") or "",
        "mo_engname":   rec.get("mo_engname") or "",
        "product":      rec.get("mo_engname") or "",
        "mo_serial":    rec.get("mo_serial") or "",
        "serial":       rec.get("mo_serial") or "",
        "mo_srfr":      rec.get("mo_srfr") or "",
        "mo_number2":   rec.get("mo_number2") or "",
        "mo_engname2":  rec.get("mo_engname2") or "",
        "mo_money2":    rec.get("mo_money2") or "",
        "trip_money":   rec.get("trip_money") or "",
        "gongim_money": rec.get("gongim_money") or "",
        "work_name":    rec.get("work_name") or "",
        "receiver":     rec.get("work_name") or "",
        "re_now":       status,
        "status":       status,
        "cu_want":      rec.get("cu_want") or "",
        "re_content":   rec.get("re_content") or "",
    }

# ---------- DB ----------
def db_get_all_seqs(base_url, headers):
    rows = []
    offset = 0
    while True:
        params = {"select":"seq_no","limit":"1000","offset":str(offset),"order":"seq_no.asc"}
        url = f"{base_url}/rest/v1/orders?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            chunk = json.loads(r.read())
        if not chunk: break
        rows.extend(chunk)
        offset += len(chunk)
        if len(chunk) < 1000: break
    return {int(r["seq_no"]) for r in rows}

def db_insert(base_url, headers, row):
    url = f"{base_url}/rest/v1/orders"
    h = {**headers, "Content-Type":"application/json", "Prefer":"return=minimal"}
    body = json.dumps(row, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")

# ---------- 메인 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="처리 상한 (0=전체)")
    args = ap.parse_args()

    sb_url = os.environ.get("SUPABASE_URL")
    sb_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not sb_url or not sb_key:
        print("환경변수 필요", file=sys.stderr); sys.exit(1)
    base_url = sb_url.rstrip("/")
    headers = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}

    print("[1/3] 원본사이트의 모든 seq_no 수집 ...")
    t0 = time.time()
    total_orig, orig_seqs = collect_all_orig_seqs()
    print(f"  → {len(orig_seqs)} 개 (총 보고된 {total_orig}건) {time.time()-t0:.0f}s")

    print("[2/3] DB 의 모든 seq_no 조회 ...")
    db_seqs = db_get_all_seqs(base_url, headers)
    print(f"  → DB {len(db_seqs)} 개")

    missing = sorted(set(orig_seqs) - db_seqs)
    print(f"\n누락: {len(missing)}건")
    if missing:
        print(f"  앞 5: {missing[:5]}")
        print(f"  뒤 5: {missing[-5:]}")

    if args.limit and len(missing) > args.limit:
        missing = missing[:args.limit]
        print(f"  --limit {args.limit} 적용")

    if not args.apply:
        print("\n[dry-run] --apply 없이 실행됨. INSERT 안 함.")
        return

    print(f"\n[3/3] {len(missing)}건 fetch+insert ...")
    ok = err = skipped = 0
    lock = threading.Lock()
    counter = [0]
    t1 = time.time()

    def worker(seq):
        nonlocal ok, err, skipped
        try:
            html = fetch_orig(f"{DETAIL}?seq_no={seq}")
            rec = extract_full(html, seq)
            row = to_db_row(rec)
            status, body = db_insert(base_url, headers, row)
            with lock:
                counter[0] += 1
                if status in (200, 201): ok += 1
                elif status == 409:      skipped += 1
                else:
                    err += 1
                    if err <= 5:
                        print(f"  seq={seq} HTTP {status}: {body[:200]}", file=sys.stderr)
                if counter[0] % 100 == 0:
                    elapsed = time.time() - t1
                    rate = counter[0] / elapsed if elapsed else 0
                    eta = (len(missing) - counter[0]) / rate if rate else 0
                    print(f"  {counter[0]}/{len(missing)} ok={ok} skip={skipped} err={err} {elapsed:.0f}s rate={rate:.1f}/s eta={eta:.0f}s")
        except Exception as e:
            with lock:
                counter[0] += 1
                err += 1

    with ThreadPoolExecutor(max_workers=WORKERS_FETCH) as ex:
        list(ex.map(worker, missing))

    elapsed = time.time() - t1
    print(f"\n[done] ok={ok} skip={skipped} err={err}  ({elapsed:.0f}s)")

if __name__ == "__main__":
    main()
