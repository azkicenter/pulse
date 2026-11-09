/*!
 * کلید خاموش/روشن (حالت تعمیر) برنامه‌های ازکی سنتر
 * استفاده — یک خط توی <head> هر برنامه:
 *   <script src="https://azkicenter.github.io/status/gate.js" data-app="sanhab" defer></script>
 * از صفحه‌ی وضعیت (azkicenter.github.io/status) روشن/خاموش می‌شه.
 * - اگه Supabase جواب نده، برنامه عادی باز می‌شه (این اسکریپت هیچ‌وقت خودش باعث قطعی نمی‌شه).
 * - برای دیدن برنامه حین تعمیر (تست): آخر آدرس ?bypass=1 بذار.
 */
(function () {
  "use strict";
  var me = document.currentScript;
  var APP = me && me.getAttribute("data-app");
  if (!APP) return;

  var URL_ = "https://paokcjakxxjqtulibegi.supabase.co/rest/v1/rpc/maintenance_get";
  var KEY = "sb_publishable_Us07X7VRGQ4q3jSIPzeT0g_8-qkLTeO";
  var RECHECK_MS = 10 * 60 * 1000;   // صفحه‌های باز هر ۱۰ دقیقه یه بار دوباره چک می‌کنن (فقط وقتی جلوی چشمه)
  var BYPASS_KEY = "azki-maint-bypass";

  // ?bypass=1 → برای همین تب، حالت تعمیر نادیده گرفته می‌شه (برای تست خودت)
  try {
    if (/[?&]bypass=1\b/.test(location.search)) sessionStorage.setItem(BYPASS_KEY, "1");
    if (sessionStorage.getItem(BYPASS_KEY) === "1") return;
  } catch (e) {}

  var overlay = null;

  function show() {
    if (overlay) return;
    overlay = document.createElement("div");
    overlay.setAttribute("role", "alertdialog");
    overlay.setAttribute("aria-live", "assertive");
    overlay.style.cssText =
      "position:fixed;inset:0;z-index:2147483647;display:flex;align-items:center;justify-content:center;" +
      "padding:24px;background:#0F1B33;color:#EAF0FB;font-family:Vazirmatn,Tahoma,system-ui,sans-serif;" +
      "direction:rtl;text-align:center;";
    overlay.innerHTML =
      '<div style="max-width:420px">' +
      '<div style="font-size:56px;line-height:1;margin-bottom:18px">🛠️</div>' +
      '<div style="font-size:22px;font-weight:800;margin-bottom:10px">در حال به‌روزرسانی</div>' +
      '<div style="font-size:15px;line-height:1.9;opacity:.85">این بخش موقتاً برای تعمیر و به‌روزرسانی در دسترس نیست.<br>به‌زودی برمی‌گرده؛ چند دقیقه‌ی دیگه دوباره سر بزن.</div>' +
      '<div style="font-size:12px;opacity:.5;margin-top:22px;direction:ltr">UNDER MAINTENANCE</div>' +
      "</div>";
    (document.body || document.documentElement).appendChild(overlay);
    document.documentElement.style.overflow = "hidden";
  }

  function hide() {
    if (!overlay) return;
    overlay.remove();
    overlay = null;
    document.documentElement.style.overflow = "";
  }

  function check() {
    var ctrl = typeof AbortController === "function" ? new AbortController() : null;
    var t = setTimeout(function () { if (ctrl) ctrl.abort(); }, 6000);
    fetch(URL_, {
      method: "POST",
      cache: "no-store",
      headers: { apikey: KEY, "Content-Type": "application/json" },
      body: "{}",
      signal: ctrl ? ctrl.signal : undefined,
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (m) {
        if (!m) return;                       // خطا → دست به چیزی نمی‌زنیم
        if (m[APP] === true) show(); else hide();
      })
      .catch(function () {})
      .then(function () { clearTimeout(t); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", check);
  else check();

  var last = Date.now();
  setInterval(function () {
    if (!document.hidden) { last = Date.now(); check(); }
  }, RECHECK_MS);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && Date.now() - last > RECHECK_MS) { last = Date.now(); check(); }
  });
})();
