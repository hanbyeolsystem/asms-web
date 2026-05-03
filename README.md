# ASMS Web (PACAI)

A/S 접수 관리 웹페이지 (정적 HTML/CSS/JS 프로토타입, 반응형).

🌐 **Live Demo**: https://hanbyeolsystem.github.io/asms-web/

## 구성

```
asms-web/
├── index.html              # 진입 화면
├── orders.html             # 접수내역 목록
├── order-new.html          # 신규 접수
├── order-detail.html       # 접수 상세/수정
├── products.html           # 부품/상품 관리
├── product-detail.html
├── customers.html
├── engineers.html
├── sms.html
├── login.html
├── css/
├── images/
├── data/                   # 정적 JSON 데이터 (개인정보 데이터는 .gitignore 됨)
│   └── products.json
└── tools/                  # 원본 사이트에서 자료 수집하는 파이썬 스크립트 (선택)
    └── config.py.example   # tools/config.py 로 복사 후 사용
```

## 로컬 실행

```bash
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

- Supabase 미설정 시: localStorage 에 변경분 저장 + JSON 파일 fetch 로 동작
- Supabase 설정 시: 모든 페이지가 DB 와 직접 통신 + 인증 가드

## Supabase 연동 (옵션)

고객 데이터 등을 Supabase DB 에 두고 인증된 사용자만 접근하게 하려면:

### 1) 프로젝트 생성
- https://supabase.com → New Project (Region: Northeast Asia (Seoul))

### 2) 스키마 실행
- 대시보드 → SQL Editor → New Query
- `sql/01_schema.sql` 내용 붙여넣기 → Run

### 3) 데이터 마이그레이션
PowerShell:
```powershell
cd asms-web
pip install supabase
$env:SUPABASE_URL = "https://xxx.supabase.co"
$env:SUPABASE_SERVICE_KEY = "eyJ..." # service_role key (절대 공개 X)
python tools/migrate_to_supabase.py --src "..\new-project-management\web\data"
```

### 4) RLS 활성화
- SQL Editor 에서 `sql/02_rls.sql` 실행

### 5) 클라이언트 설정
`js/supabase-config.js` 의 두 줄을 본인 키로 교체 후 commit + push:
```js
window.SUPABASE_URL  = "https://xxx.supabase.co";
window.SUPABASE_ANON = "eyJ..."; // anon public key (RLS 적용되어 안전)
```

### 6) 첫 사용자 가입
- 사이트 접속 → 로그인 화면 → "신규 가입" → 이메일/비번 입력
- Supabase 가 인증 메일 발송 → 메일 확인 후 로그인

이후 추가 가입을 막으려면: Supabase 대시보드 → Authentication → Providers → Email → "Enable Sign ups" OFF
