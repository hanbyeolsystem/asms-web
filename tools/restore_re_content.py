#!/usr/bin/env python3
"""orders.re_content 복원 — 원본 사이트 수집 스냅샷(order_details.json)에서.

표준 라이브러리만 사용 (urllib + json). 추가 패키지 설치 불필요.

복원 정책 (보수적):
  1) 원본(order_details.json)에 존재하는 seq_no 만 대상
     (= 2026-04-30 시점 스냅샷이므로 그 이후 신규 접수는 자동 제외)
  2) DB.re_content 가 비어 있을(NULL/빈문자열) 때만 채움
     (= 사용자 최근 편집분은 절대 덮어쓰지 않음)
  3) 원본의 re_content 가 비어있으면 스킵

기본은 dry-run (변경 없이 카운트만). 실제 UPDATE 는 --apply 플래그로.

환경변수:
  $env:SUPABASE_URL          = "https://xxx.supabase.co"
  $env:SUPABASE_SERVICE_KEY  = "eyJ..."   # service_role (RLS 우회)

실행:
  python restore_re_content.py            # dry-run
  python restore_re_content.py --apply    # 실제 적용
"""
import os, sys, json, time, argparse
import urllib.request, urllib.parse, urllib.error

PAGE = 1000

def is_empty(s):
    if s is None: return True
    if not isinstance(s, str): return False
    return s.strip() == ""

def http_request(url, headers, method="GET", body=None, timeout=60):
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, raw.decode("utf-8") if raw else ""
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body

def fetch_empty_recontent_rows(base_url, headers):
    """orders 중 re_content 가 NULL 또는 빈문자열인 행의 seq_no 만 페이지네이션으로 모두 가져옴."""
    rows = []
    offset = 0
    while True:
        # PostgREST: or=(re_content.is.null,re_content.eq.)
        params = {
            "select": "seq_no",
            "or":     "(re_content.is.null,re_content.eq.)",
            "order":  "seq_no.asc",
            "limit":  str(PAGE),
            "offset": str(offset),
        }
        url = f"{base_url}/rest/v1/orders?{urllib.parse.urlencode(params)}"
        status, body = http_request(url, headers)
        if status != 200:
            print(f"[err] HTTP {status}: {body[:300]}", file=sys.stderr)
            sys.exit(2)
        chunk = json.loads(body)
        if not chunk: break
        rows.extend(chunk)
        offset += len(chunk)
        print(f"  fetched {offset} ...")
        if len(chunk) < PAGE: break
    return [r["seq_no"] for r in rows]

def update_recontent(base_url, headers, seq_no, re_content):
    params = {"seq_no": f"eq.{seq_no}"}
    url = f"{base_url}/rest/v1/orders?{urllib.parse.urlencode(params)}"
    h = dict(headers)
    h["Content-Type"]   = "application/json"
    h["Prefer"]         = "return=minimal"
    status, body = http_request(url, h, method="PATCH", body={"re_content": re_content})
    return status, body

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None, help="order_details.json 경로 (기본 자동탐색)")
    ap.add_argument("--apply", action="store_true", help="실제 UPDATE 실행 (없으면 dry-run)")
    ap.add_argument("--limit", type=int, default=0, help="처리할 최대 건수 (테스트용, 0=전체)")
    args = ap.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("환경변수 SUPABASE_URL / SUPABASE_SERVICE_KEY 설정 필요", file=sys.stderr)
        sys.exit(1)
    base_url = url.rstrip("/")
    headers = {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
    }

    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        args.src,
        os.path.join(here, "..", "..", "new-project-management", "web", "data", "order_details.json"),
        os.path.join(here, "..", "data", "order_details.json"),
    ]
    src = next((c for c in candidates if c and os.path.exists(c)), None)
    if not src:
        print("order_details.json 을 찾지 못했습니다. --src 로 지정하세요.", file=sys.stderr)
        sys.exit(1)
    print(f"[src] {os.path.abspath(src)}")

    with open(src, encoding="utf-8") as f:
        details = json.load(f)
    print(f"[src] {len(details)}건 로드")

    print(f"[db] re_content 비어있는 행 조회 중...")
    empty_seqs = fetch_empty_recontent_rows(base_url, headers)
    print(f"[db] re_content 비어있는 행 {len(empty_seqs)}건")

    targets = []
    skipped_no_orig = 0
    skipped_orig_empty = 0
    for seq in empty_seqs:
        seq_str = str(seq)
        d = details.get(seq_str)
        if d is None:
            skipped_no_orig += 1
            continue
        rc = d.get("re_content")
        if is_empty(rc):
            skipped_orig_empty += 1
            continue
        targets.append((seq, rc))
        if args.limit and len(targets) >= args.limit: break

    print(f"\n[plan]")
    print(f"  복원 대상           : {len(targets)}건")
    print(f"  원본 스냅샷 미존재   : {skipped_no_orig}건  (4/30 이후 신규 접수 추정)")
    print(f"  원본도 비어있어 스킵 : {skipped_orig_empty}건")

    if not targets:
        print("\n복원할 행이 없습니다."); return

    print("\n--- 샘플 (앞 5건) ---")
    for seq, rc in targets[:5]:
        head = rc.replace("<br>", " | ").replace("\n", " ")[:120]
        print(f"  seq={seq}  re_content[:120]= {head}")

    if not args.apply:
        print("\n[dry-run] --apply 없이 실행됨. 실제 UPDATE 는 수행되지 않았습니다.")
        return

    print(f"\n[apply] {len(targets)}건 UPDATE 시작 ...")
    t0 = time.time()
    ok = err = 0
    for i, (seq, rc) in enumerate(targets, 1):
        status, body = update_recontent(base_url, headers, seq, rc)
        if 200 <= status < 300:
            ok += 1
        else:
            err += 1
            print(f"  seq={seq} HTTP {status}: {body[:200]}", file=sys.stderr)
        if i % 100 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            print(f"  {i}/{len(targets)}  ok={ok} err={err}  {elapsed:.1f}s  ({rate:.1f}/s)")
    print(f"\n[done] ok={ok} err={err}  ({time.time()-t0:.1f}s)")

if __name__ == "__main__":
    main()
