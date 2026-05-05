#!/usr/bin/env python3
"""orders.re_content 의 스탬프 사이 누락된 <br> 보정.

문제
----
일괄 출고 기능 초기 버전에서 prev re_content 끝이 <br> 이 아닐 때
새 스탬프를 그냥 이어 붙여서 한 줄로 합쳐진 데이터가 발생.

  예) "...완료05월 05일 18시 06분  김상환 기사의 의견 : 출고<br>입금확인<br>"
       ↑ 사이 <br> 누락

스캔 대상 패턴 (한 스탬프의 시작):
  MM월 DD일 HH시 MM분  AUTHOR 기사 접수
  MM월 DD일 HH시 MM분  AUTHOR 기사의 의견 : <STATUS>

위 패턴이 등장하는 위치 바로 앞 글자가 '>' (즉 <br> 직후) 가 아니라면
그 앞에 <br> 을 끼워넣음.

기본 dry-run, --apply 로 실제 UPDATE.

환경변수
  $env:SUPABASE_URL          = "https://xxx.supabase.co"
  $env:SUPABASE_SERVICE_KEY  = "eyJ..."
"""
import os, re, sys, json, time, argparse
import urllib.request, urllib.parse, urllib.error

PAGE = 1000

# 스탬프 시작 패턴 (한 줄)
STAMP_RE = re.compile(
    r'\d{1,2}월\s\d{1,2}일\s\d{1,2}시\s\d{1,2}분\s{1,2}\S+?\s기사(?:\s접수|의\s의견\s:\s\S+)'
)

def has_br_before(s, pos):
    """pos 직전이 (공백 무시하고) <br> 류 태그로 끝나는지 판단."""
    i = pos - 1
    while i >= 0 and s[i] in ' \t\r\n':
        i -= 1
    if i < 0:
        return True  # 시작 바로 앞 → separator 불필요
    return s[i] == '>'

def fix_text(s):
    """스탬프 앞에 <br> 을 보강한 문자열 반환."""
    if not s:
        return s, 0
    out = []
    last = 0
    inserted = 0
    for m in STAMP_RE.finditer(s):
        start = m.start()
        out.append(s[last:start])
        if not has_br_before(s, start):
            out.append('<br>')
            inserted += 1
        out.append(m.group(0))
        last = m.end()
    out.append(s[last:])
    return ''.join(out), inserted

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

def fetch_all(base_url, headers):
    rows = []
    offset = 0
    while True:
        params = {
            "select": "seq_no,re_content",
            "or":     "(re_content.not.is.null,re_content.neq.)",
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
        if len(chunk) < PAGE: break
        if offset % 5000 == 0:
            print(f"  fetched {offset} ...")
    return rows

def patch_one(base_url, headers, seq_no, re_content):
    params = {"seq_no": f"eq.{seq_no}"}
    url = f"{base_url}/rest/v1/orders?{urllib.parse.urlencode(params)}"
    h = dict(headers)
    h["Content-Type"] = "application/json"
    h["Prefer"]       = "return=minimal"
    return http_request(url, h, method="PATCH", body={"re_content": re_content})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제 UPDATE 실행")
    ap.add_argument("--limit", type=int, default=0, help="처리 최대 건수 (0=전체)")
    ap.add_argument("--samples", type=int, default=5, help="dry-run 시 보여줄 샘플 수")
    args = ap.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("환경변수 SUPABASE_URL / SUPABASE_SERVICE_KEY 필요", file=sys.stderr)
        sys.exit(1)
    base_url = url.rstrip("/")
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}

    print("[fetch] re_content 있는 행 전부 조회 ...")
    rows = fetch_all(base_url, headers)
    print(f"[fetch] {len(rows)}건")

    targets = []
    total_inserted = 0
    for r in rows:
        seq = r["seq_no"]
        rc = r.get("re_content") or ""
        new, n = fix_text(rc)
        if n > 0 and new != rc:
            targets.append((seq, rc, new, n))
            total_inserted += n
            if args.limit and len(targets) >= args.limit: break

    print(f"\n[plan]")
    print(f"  손상 행          : {len(targets)} / {len(rows)}")
    print(f"  삽입될 <br> 개수 : {total_inserted}")

    if not targets:
        print("\n복구할 행이 없습니다.")
        return

    print(f"\n--- 샘플 (앞 {args.samples}건) ---")
    for seq, before, after, n in targets[: args.samples]:
        b = before.replace("<br>", " | ")[:200]
        a = after.replace("<br>", " | ")[:200]
        print(f"\nseq={seq}  inserts={n}")
        print(f"  before: {b}")
        print(f"  after : {a}")

    if not args.apply:
        print("\n[dry-run] --apply 없이 실행됨. 실제 UPDATE 는 수행되지 않았습니다.")
        return

    print(f"\n[apply] {len(targets)}건 UPDATE 시작 ...")
    t0 = time.time()
    ok = err = 0
    for i, (seq, _b, new, _n) in enumerate(targets, 1):
        status, body = patch_one(base_url, headers, seq, new)
        if 200 <= status < 300:
            ok += 1
        else:
            err += 1
            print(f"  seq={seq} HTTP {status}: {body[:200]}", file=sys.stderr)
        if i % 50 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed else 0
            print(f"  {i}/{len(targets)}  ok={ok} err={err}  {elapsed:.1f}s  ({rate:.1f}/s)")
    print(f"\n[done] ok={ok} err={err}  ({time.time()-t0:.1f}s)")

if __name__ == "__main__":
    main()
