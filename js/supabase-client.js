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

async function dbFetchAll(table, orderCol, ascending = false) {
  const PAGE = 1000;
  const all = [];
  let from = 0;
  while (true) {
    const { data, error } = await sb()
      .from(table).select("*").order(orderCol, { ascending }).range(from, from + PAGE - 1);
    if (error) { console.error(error); return all; }
    all.push(...data);
    if (data.length < PAGE) break;
    from += PAGE;
  }
  return all;
}

async function dbOrdersAll() {
  if (!window.SB_CONFIGURED) return null;
  return await dbFetchAll("orders", "seq_no", false);
}

// 서버 측 페이지네이션 + 필터 (대용량 테이블용)
async function dbOrdersPage({ page = 1, pageSize = 15, status = "", searchField = "", searchValue = "" } = {}) {
  if (!window.SB_CONFIGURED) return null;
  const from = (page - 1) * pageSize;
  const to   = from + pageSize - 1;
  let q = sb().from("orders").select("*", { count: "exact" });
  if (status) q = q.eq("status", status);
  if (searchValue) {
    const v = String(searchValue).replace(/%/g, "");
    if (searchField === "phone") {
      q = q.or(`cu_tel.ilike.%${v}%,cu_mobile.ilike.%${v}%`);
    } else if (searchField) {
      q = q.ilike(searchField, `%${v}%`);
    }
  }
  q = q.order("seq_no", { ascending: false }).range(from, to);
  const { data, count, error } = await q;
  if (error) { console.error(error); return { rows: [], total: 0 }; }
  return { rows: data || [], total: count || 0 };
}
window.dbOrdersPage = dbOrdersPage;

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
  return await dbFetchAll("products", "seq_no", false);
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
  return await dbFetchAll("customers", "cu_name", true);
}

async function dbEngineersAll() {
  if (!window.SB_CONFIGURED) return null;
  const { data, error } = await sb()
    .from("engineers").select("*").order("created_at", { ascending: false });
  if (error) { console.error(error); return []; }
  return data;
}

async function fnCreateEngineer(payload) {
  if (!window.SB_CONFIGURED) return { error: "Supabase 미설정" };
  const { data, error } = await sb().functions.invoke("admin-engineers", {
    method: "POST",
    body: payload,
  });
  if (error) return { error: error.message };
  if (data?.error) return { error: data.error };
  return { data };
}

async function fnDeleteEngineer(en_id) {
  if (!window.SB_CONFIGURED) return { error: "Supabase 미설정" };
  const { data, error } = await sb().functions.invoke("admin-engineers", {
    method: "DELETE",
    body: { en_id },
  });
  if (error) return { error: error.message };
  if (data?.error) return { error: data.error };
  return { data };
}

window.dbOrdersAll      = dbOrdersAll;
window.dbOrderBySeq     = dbOrderBySeq;
window.dbOrderUpsert    = dbOrderUpsert;
window.dbOrderDelete    = dbOrderDelete;
window.dbProductsAll    = dbProductsAll;
window.dbProductBySeq   = dbProductBySeq;
window.dbCustomersAll   = dbCustomersAll;
window.dbEngineersAll   = dbEngineersAll;
window.fnCreateEngineer = fnCreateEngineer;
window.fnDeleteEngineer = fnDeleteEngineer;

// ---------- 현재 사용자 이름 (헤더용) ----------
async function currentUserName() {
  if (!window.SB_CONFIGURED) return localStorage.getItem("current_user") || "데모";
  const { data: { user } } = await window.sb.auth.getUser();
  if (!user) return null;
  return user.user_metadata?.name || user.email?.split("@")[0] || user.email || "사용자";
}
window.currentUserName = currentUserName;
