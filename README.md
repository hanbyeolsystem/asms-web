# ASMS Web (PACAI)

A/S 접수 관리 웹페이지 (Next.js 마이그레이션 전 정적 프로토타입).

## 구성

```
asms-web/
├── web/                # 정적 사이트 (HTML/CSS/JS)
│   ├── index.html
│   ├── orders.html         # 접수내역 목록
│   ├── order-new.html      # 신규 접수
│   ├── order-detail.html   # 접수 상세/수정
│   ├── products.html       # 부품/상품 관리
│   ├── product-detail.html
│   ├── customers.html
│   ├── engineers.html
│   ├── manual.html
│   ├── sms.html
│   ├── login.html
│   ├── css/
│   ├── images/
│   └── data/               # 정적 JSON 데이터 (개인정보 데이터는 .gitignore 됨)
│       └── products.json
└── tools/              # 원본 사이트에서 자료 수집하는 파이썬 스크립트
    └── config.py.example   # tools/config.py 로 복사 후 사용
```

## 로컬 실행

```bash
cd web
python -m http.server 8765
# 브라우저: http://localhost:8765
```

## 데이터 수집 (관리자만)

원본 사이트에서 데이터를 끌어오는 스크립트는 `tools/` 에 있습니다.
**고객 개인정보가 포함되므로 결과 JSON 파일은 git 에 커밋하지 마세요** (`.gitignore` 처리됨).

```bash
cp tools/config.py.example tools/config.py
# config.py 의 ID/PASSWORD 채우기
python tools/harvest_orders.py        # 접수 목록
python tools/harvest_order_details.py # 접수 상세
python tools/harvest_recent.py        # 최근 변경분만 incremental
```

## 주요 기능

- 접수내역 목록: 상태별 필터, 고객명/제품명/전화번호/시리얼번호 검색, 페이지네이션
- 접수 상세/수정: 원본 사이트와 동일한 폼, 처리 의견 누적, 상태 변경 → 목록 자동 반영
- 부품/상품 관리: 동적 렌더링, 상세 화면
- 반응형 레이아웃 (PC/태블릿/모바일)

## 참고

- 데이터는 클라이언트의 `localStorage` 에 변경분이 저장되며, 원본 JSON 은 변경되지 않습니다.
- 원본 PHP 사이트와 라우트 매핑은 `02_사이트맵.md` 참고.
