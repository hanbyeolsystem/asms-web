// Supabase 클라이언트 + 인증/데이터 래퍼.
// supabase-config.js 가 먼저 로드되어 있어야 함.
// supabase-js v2 UMD 가 window.supabase 로 노출됨.

(function () {
  const URL  = window.SUPABASE_URL;
  const ANON = window.SUPABASE_ANON;

  function isConfigured() {
    return URL && ANON
        && URL  !== "https://YOUR_PROJECT.supabase.co"
        && ANON !== "YOUR_ANON_KEY";
  }
  window.SB_CONFIGURED = isConfigured();

  if (!isConfigured()) {
    console.warn("[supabase] 설정 미완료 — 데모 폴백 모드로 동작 (js/supabase-config.js 참고)");
    window.sb = null;
    return;
  }

  if (!window.supabase || !window.supabase.createClient) {
    console.error("[supabase] supabase-js UMD 로드 실패 — <script src='https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2'></script> 가 먼저 있어야 합니다");
    window.sb = null;
    return;
  }

  window.sb = window.supabase.createClient(URL, ANON, {
    auth: { persistSession: true, autoRefreshToken: true },
  });
})();

// ---------- 인증 가드: 로그인 안 됐으면 login.html 로 ----------
async function requireLogin() {
  if (!window.SB_CONFIGURED) return null;       // 데모 모드는 게이트 안 함
  const { data: { session } } = await window.sb.auth.getSession();
  const here = location.pathname.split("/").pop();
  if (!session && here !== "login.html") {
    location.href = "login.html?next=" + encodeURIComponent(here || "orders.html");
    return null;
  }
  return session;
}
window.requireLogin = requireLogin;

async function logout() {
  if (window.sb) await window.sb.auth.signOut();
  location.href = "login.html";
}
window.logout = logout;

// ---------- 데이터 래퍼 ----------
const sb = () => window.sb;

async function dbOrdersAll() {
  if (!window.SB_CONFIGURED) return null;
  const { data, error } = await sb()
    .from("orders").select("*").order("seq_no", { ascending: false });
  if (error) { console.error(error); return []; }
  return data;
}

async function dbOrderBySeq(seq) {
  if (!window.SB_CONFIGURED) return null;
  const { data, error } = await sb()
    .from("orders").select("*").eq("seq_no", Number(seq)).maybeSingle();
  if (error) { console.error(error); return null; }
  return data;
}

async function dbOrderUpsert(row) {
  if (!window.SB_CONFIGURED) return null;
  const { data, error } = await sb()
    .from("orders").upsert(row, { onConflict: "seq_no" }).select().maybeSingle();
  if (error) { console.error(error); return null; }
  return data;
}

async function dbOrderDelete(seq) {
  if (!window.SB_CONFIGURED) return false;
  const { error } = await sb().from("orders").delete().eq("seq_no", Number(seq));
  if (error) { console.error(error); return false; }
  return true;
}

async function dbProductsAll() {
  if (!window.SB_CONFIGURED) return null;
  const { data, error } = await sb()
    .from("products").select("*").order("seq_no", { ascending: false });
  if (error) { console.error(error); return []; }
  return data;
}

async function dbProductBySeq(seq) {
  if (!window.SB_CONFIGURED) return null;
  const { data, error } = await sb()
    .from("products").select("*").eq("seq_no", Number(seq)).maybeSingle();
  if (error) { console.error(error); return null; }
  return data;
}

async function dbCustomersAll() {
  if (!window.SB_CONFIGURED) return null;
  const { data, error } = await sb()
    .from("customers").select("*").order("cu_name");
  if (error) { console.error(error); return []; }
  return data;
}

window.dbOrdersAll      = dbOrdersAll;
window.dbOrderBySeq     = dbOrderBySeq;
window.dbOrderUpsert    = dbOrderUpsert;
window.dbOrderDelete    = dbOrderDelete;
window.dbProductsAll    = dbProductsAll;
window.dbProductBySeq   = dbProductBySeq;
window.dbCustomersAll   = dbCustomersAll;

// ---------- 현재 사용자 이름 (헤더용) ----------
async function currentUserName() {
  if (!window.SB_CONFIGURED) return localStorage.getItem("current_user") || "데모";
  const { data: { user } } = await window.sb.auth.getUser();
  if (!user) return null;
  return user.user_metadata?.name || user.email?.split("@")[0] || user.email || "사용자";
}
window.currentUserName = currentUserName;
