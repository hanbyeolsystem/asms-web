#!/usr/bin/env python3
"""orders/order_details/customers/products JSON → Supabase 일괄 import.

전제:
  pip install supabase

실행 전 환경변수 설정 (PowerShell):
  $env:SUPABASE_URL = "https://xxxxxxxxxxxx.supabase.co"
  $env:SUPABASE_SERVICE_KEY = "eyJ..."  # service_role key (RLS 우회)

데이터 파일 위치 (기본): ../web/data/ 에 있는 4개 JSON
  --src 옵션으로 다른 경로 지정 가능
"""
import os, sys, json, time, argparse
try:
    from supabase import create_client, Client
except ImportError:
    print("supabase 패키지 필요: pip install supabase", file=sys.stderr)
    sys.exit(1)

def chunks(arr, n):
    for i in range(0, len(arr), n):
        yield arr[i:i+n]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None, help="JSON 데이터 폴더 경로 (기본: 자동 탐색)")
    ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--only", choices=["products","customers","orders"], help="특정 테이블만")
    args = ap.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("환경변수 SUPABASE_URL / SUPABASE_SERVICE_KEY 설정 필요", file=sys.stderr)
        sys.exit(1)

    # 데이터 폴더 자동 탐색
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        args.src,
        os.path.join(here, "..", "data"),                     # asms-web/data/
        os.path.join(here, "..", "..", "new-project-management", "web", "data"),  # 원본
    ]
    src = None
    for c in candidates:
        if c and os.path.isdir(c) and os.path.exists(os.path.join(c, "orders.json")):
            src = c
            break
    if not src:
        print("데이터 폴더를 찾을 수 없습니다. --src 로 지정하세요.", file=sys.stderr)
        sys.exit(1)
    print(f"[src] {os.path.abspath(src)}")

    sb: Client = create_client(url, key)

    # 1) products
    if not args.only or args.only == "products":
        path = os.path.join(src, "products.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f: products = json.load(f)
            print(f"[products] {len(products)}건 upsert")
            t0 = time.time()
            for batch in chunks(products, args.batch):
                sb.table("products").upsert(batch).execute()
            print(f"  완료 ({time.time()-t0:.1f}s)")

    # 2) customers
    if not args.only or args.only == "customers":
        path = os.path.join(src, "customers.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f: customers = json.load(f)
            print(f"[customers] {len(customers)}건 upsert")
            t0 = time.time()
            for i, batch in enumerate(chunks(customers, args.batch), 1):
                sb.table("customers").upsert(batch).execute()
                if i % 5 == 0:
                    print(f"  {i*args.batch}/{len(customers)}")
            print(f"  완료 ({time.time()-t0:.1f}s)")

    # 3) orders + order_details 합쳐서 orders 테이블에 upsert
    if not args.only or args.only == "orders":
        with open(os.path.join(src, "orders.json"), encoding="utf-8") as f: orders = json.load(f)
        with open(os.path.join(src, "order_details.json"), encoding="utf-8") as f: details = json.load(f)
        print(f"[orders] {len(orders)}건 합치는 중 (details {len(details)})")
        merged = []
        for o in orders:
            d = details.get(str(o["seq_no"]), {})
            row = {**d, **o}
            row.pop("created_at", None)
            row.pop("updated_at", None)
            merged.append(row)
        print(f"[orders] {len(merged)}건 upsert (batch={args.batch})")
        t0 = time.time()
        total = len(merged)
        for i, batch in enumerate(chunks(merged, args.batch), 1):
            try:
                sb.table("orders").upsert(batch).execute()
            except Exception as e:
                print(f"  batch {i} 오류: {e}", file=sys.stderr)
            done = min(i * args.batch, total)
            print(f"  {done}/{total} ({time.time()-t0:.1f}s)")
        print(f"[done] orders 완료 ({time.time()-t0:.1f}s)")

if __name__ == "__main__":
    main()
