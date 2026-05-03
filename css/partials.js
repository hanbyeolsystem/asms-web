// 정적 HTML에서 헤더/푸터 공통 마크업을 주입하는 헬퍼.
// 각 페이지가 <div id="app-header"></div> 와 <div id="app-footer"></div> 를 포함하면
// 자동으로 마크업이 채워집니다.

(function () {
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");
  const dayNames = ["일요일","월요일","화요일","수요일","목요일","금요일","토요일"];

  const headerHtml = `
    <div class="top-bar">
      <div class="top-bar-row1">
        <div class="brand">
          <a href="orders.html"><span class="brand-logo">한별시스템</span></a>
          <span class="branch-tag">[관리자]</span>
        </div>
        <div class="top-menu-wrap">
          <a href="orders.html"><b>A/S Management System</b></a> &nbsp;&nbsp;&nbsp;
          <a href="order-new.html">신규접수</a> <span class="sep">|</span>
          <a href="orders.html">접수내역</a> <span class="sep">|</span>
          <a href="customers.html">고객관리</a> <span class="sep">|</span>
          <a href="products.html">부품/상품관리</a> <span class="sep">|</span>
          <a href="engineers.html">엔지니어</a> <span class="sep">|</span>
          <a href="manual.html">매뉴얼</a> <span class="sep">|</span>
          <a href="sms.html">SMS관리</a> <span class="sep">|</span>
          <a href="#" id="logoutLink">로그아웃</a>
        </div>
      </div>
      <div class="top-bar-divider1"></div>
      <div class="top-bar-divider2"></div>
      <div class="top-bar-row2">
        <b>${yyyy}년 ${mm}월 ${dd}일</b>&nbsp;
        <b>${dayNames[today.getDay()]}</b>
        <span id="clock" style="margin-left:8px;"></span>
        <span class="gap"></span>
        <span class="quick">
          <a href="orders.html">전체</a> |
          <a href="orders.html?status=접수">접수</a> |
          <a href="orders.html?status=진행">진행</a> |
          <a href="orders.html?status=센터">센터</a> |
          <a href="orders.html?status=견적">견적</a> |
          <a href="orders.html?status=택배">택배</a> |
          <a href="orders.html?status=완료">완료</a> |
          <a href="orders.html?status=출고">출고</a>
        </span>
        <span class="gap"></span>
        <span id="userBadge">…님</span> ※ 오늘 완료 건수는
      </div>
    </div>
  `;

  const footerHtml = `
    <div class="foot-line"></div>
    <div class="foot-bar">A/S Management System.</div>
  `;

  function tick() {
    const n = new Date();
    let h = n.getHours();
    const ampm = h < 12 ? "오전" : "오후";
    if (h > 12) h -= 12;
    if (h === 0) h = 12;
    const m = String(n.getMinutes()).padStart(2, "0");
    const s = String(n.getSeconds()).padStart(2, "0");
    const el = document.getElementById("clock");
    if (el) el.innerHTML = `<b>${ampm} ${h}:${m}:${s}</b>`;
  }

  document.addEventListener("DOMContentLoaded", async function () {
    const h = document.getElementById("app-header");
    const f = document.getElementById("app-footer");
    if (h) h.innerHTML = headerHtml;
    if (f) f.innerHTML = footerHtml;
    tick();
    setInterval(tick, 1000);

    // 현재 메뉴 강조
    const path = location.pathname.split("/").pop();
    document.querySelectorAll(".top-menu-wrap a").forEach(a => {
      if (a.getAttribute("href") === path) a.style.color = "#0000ff";
    });

    // 로그아웃 링크 → supabase signOut
    const out = document.getElementById("logoutLink");
    if (out) out.addEventListener("click", e => {
      e.preventDefault();
      if (typeof window.logout === "function") window.logout();
      else location.href = "login.html";
    });

    // 인증 가드 (login.html / index.html 제외) — 미로그인 시 login.html 로
    const noGuard = ["login.html", "index.html", ""];
    if (!noGuard.includes(path) && typeof window.requireLogin === "function") {
      await window.requireLogin();
    }

    // 사용자 이름 표시
    const badge = document.getElementById("userBadge");
    if (badge && typeof window.currentUserName === "function") {
      const n = await window.currentUserName();
      badge.textContent = (n || "사용자") + "님";
      try { localStorage.setItem("current_user", n || ""); } catch (e) {}
    }
  });
})();
