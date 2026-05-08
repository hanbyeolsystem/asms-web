#!/usr/bin/env python3
"""원본사이트에서 '임대제품교체' / '임대제품회수' 검색 결과 중 DB 에 없는 건만 fetch + insert.

기존 DB 레코드는 절대 건드리지 않음 (중복 시 PostgREST 가 409 반환 → skip).

환경변수:
  $env:SUPABASE_URL          = "https://xxx.supabase.co"
  $env:SUPABASE_SERVICE_KEY  = "eyJ..."
"""
import os, sys, json, re, time, argparse
import urllib.request, urllib.parse, urllib.error, http.cookiejar

BASE_ORIG = "http://wolf-fox.dreamtec.co.kr/pacai2/admin/as"
LOGIN     = f"{BASE_ORIG}/admin_login.php"
LIST      = f"{BASE_ORIG}/as_list.php"
DETAIL    = f"{BASE_ORIG}/as_uform.php"

KEYWORDS = ["임대제품교체", "임대제품회수"]

# ---------- 원본사이트 세션 ----------
def make_orig_session():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", "Mozilla/5.0")]
    op.open(LOGIN, urllib.parse.urlencode({"ID":"wolffox","password":"1129"}).encode(), timeout=30).read()
    return op

def fetch_orig(op, url):
    with op.open(url, timeout=30) as r:
        return r.read().decode("euc-kr", errors="replace")

# ---------- 원본 검색 페이지네이션 ----------
def collect_seq_nos(op, keyword):
    """검색 결과 모든 페이지를 돌며 seq_no 와 게시물 총 수 반환."""
    PAGE = 15
    params = {"f_name":"mo_engname","f_value":keyword,"start":"0"}
    url = f"{LIST}?{urllib.parse.urlencode(params, encoding='euc-kr')}"
    html = fetch_orig(op, url)
    m = re.search(r"게시물.*?([0-9,]+)", html)
    total = int(m.group(1).replace(",","")) if m else 0
    seqs = set(re.findall(r"seq_no=(\d+)", html))
    pages = (total + PAGE - 1) // PAGE
    for p in range(1, pages):
        params["start"] = str(p * PAGE)
        url = f"{LIST}?{urllib.parse.urlencode(params, encoding='euc-kr')}"
        html = fetch_orig(op, url)
        seqs.update(re.findall(r"seq_no=(\d+)", html))
    return total, sorted(int(s) for s in seqs)

# ---------- 원본 detail 파싱 (기존 harvest_order_details.py 와 동일 로직) ----------
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

# v2 display-cell 패턴 (re_content 옛 페이지)
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

# ---------- DB 작업 ----------
def supabase_get_existing_seqs(base_url, headers, seqs):
    """대상 seqs 중 DB 에 이미 있는 것만 반환."""
    if not seqs: return set()
    url = f"{base_url}/rest/v1/orders?select=seq_no&seq_no=in.({','.join(map(str, seqs))})"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return {int(x["seq_no"]) for x in data}

def supabase_insert(base_url, headers, row):
    """단건 insert. 중복 시 409 (skip)."""
    url = f"{base_url}/rest/v1/orders"
    h = {**headers, "Content-Type":"application/json", "Prefer":"return=minimal"}
    body = json.dumps(row, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")

# orders 테이블에 맞춰 필드 매핑 (snapshot → DB 형식)
def to_db_row(rec):
    """snapshot 레코드를 DB 컬럼에 맞춰 변환. 추가 보정/계산 컬럼 포함."""
    # process_date / order_no / status 등은 원본에 없을 수 있음 — 기본값 채움
    status = rec.get("re_now") or "접수"
    # process_date: 원본 detail 페이지엔 보통 없음. 그냥 비움.
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제 INSERT (없으면 dry-run)")
    args = ap.parse_args()

    sb_url = os.environ.get("SUPABASE_URL")
    sb_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not sb_url or not sb_key:
        print("환경변수 SUPABASE_URL / SUPABASE_SERVICE_KEY 필요", file=sys.stderr); sys.exit(1)
    base_url = sb_url.rstrip("/")
    headers = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}

    print("[orig] 로그인")
    op = make_orig_session()

    all_orig_seqs = set()
    for kw in KEYWORDS:
        print(f"[orig] '{kw}' 검색 중 ...")
        total, seqs = collect_seq_nos(op, kw)
        print(f"  → 원본사이트 {total}건 / 수집 {len(seqs)}개")
        all_orig_seqs.update(seqs)
    print(f"[orig] 합계 unique seq_no: {len(all_orig_seqs)}")

    existing = supabase_get_existing_seqs(base_url, headers, sorted(all_orig_seqs))
    missing = sorted(all_orig_seqs - existing)
    print(f"[db] 이미 있음: {len(existing)}")
    print(f"[db] 누락:      {len(missing)}")
    if not missing:
        print("누락된 게 없습니다. 종료."); return

    print(f"\n[plan]")
    print(f"  대상 seq_no 앞 10개: {missing[:10]}")
    print(f"  대상 seq_no 뒤 10개: {missing[-10:]}")

    if not args.apply:
        print("\n[dry-run] --apply 없이 실행됨. 실제 INSERT 안함."); return

    print(f"\n[fetch+insert] {len(missing)}건 처리 시작 ...")
    t0 = time.time()
    ok = err = skipped = 0
    for i, seq in enumerate(missing, 1):
        try:
            html = fetch_orig(op, f"{DETAIL}?seq_no={seq}")
            rec = extract_full(html, seq)
            row = to_db_row(rec)
            status, body = supabase_insert(base_url, headers, row)
            if status == 201 or status == 200:
                ok += 1
            elif status == 409:  # 중복
                skipped += 1
            else:
                err += 1
                print(f"  seq={seq} HTTP {status}: {body[:200]}", file=sys.stderr)
        except Exception as e:
            err += 1
            print(f"  seq={seq} 예외: {e}", file=sys.stderr)
        if i % 10 == 0:
            elapsed = time.time() - t0
            print(f"  {i}/{len(missing)} ok={ok} skip={skipped} err={err} ({elapsed:.0f}s)")

    print(f"\n[done] ok={ok} skip={skipped} err={err}  ({time.time()-t0:.0f}s)")

if __name__ == "__main__":
    main()
