/* ============================================================
   DataPlatform Analytics Console — shared.js
   Live ticker + active nav + Superset embed helpers
   ============================================================ */

// ── Active sidebar nav highlighting ─────────────────────────
(function () {
  const path = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.sb-item[href]').forEach(el => {
    if (el.getAttribute('href') === path) el.classList.add('active');
    else el.classList.remove('active');
  });
})();

// ── Live company value ticker ────────────────────────────────
// TODO: replace mock with real API call:
// fetch('/api/company-value').then(r => r.json()).then(d => { el.textContent = fmt(d.value); });
(function () {
  const el = document.getElementById('ticker-value');
  if (!el) return;

  let base = 4_821_039;
  let offset = 0;

  function fmt(n) {
    return '$' + Math.round(n).toLocaleString('en-US');
  }

  function refresh() {
    offset += (Math.random() - 0.47) * 1400;
    el.textContent = fmt(base + offset);
  }

  refresh();
  setInterval(refresh, 5000);
})();

// ── Superset dashboard UUID registry ────────────────────────
// After creating each dashboard in Superset, copy its UUID from
// the URL (superset/dashboard/YOUR-UUID-HERE/) and paste it below.
const DASHBOARDS = {
  kpiStrip:   '813326be-8203-4dce-9908-25e28d9f0e6e',
  mainTx:     '4f55a708-c316-406e-8480-1aa3d071631f',
  company:    '0b663ea7-b0d8-4611-9ca4-a8761e17d875',
  industry:   '75c09c9f-faf0-448b-9215-bda18bbf87f7',   // TODO: paste UUID after creating dashboard
  quarantine: '',   // TODO: paste UUID after creating dashboard
  dataHealth: '',   // TODO: paste UUID after creating dashboard
  pipeline:   '',   // TODO: paste UUID after creating dashboard
  fxRates:    '',   // TODO: paste UUID after creating dashboard
  fxFees:     '',   // TODO: paste UUID after creating dashboard
};

// ── Guest token fetch from Bouncer ──────────────────────────
async function fetchGuestToken(dashboardId) {
  try {
    const response = await fetch(`/api/get-token?dashboard_id=${dashboardId}`, { credentials: "include" });
    if (!response.ok) throw new Error(`Bouncer returned ${response.status}`);
    const data = await response.json();
    return data.token;
  } catch (err) {
    console.error('Token fetch failed:', err);
    return null;
  }
}

// ── Embed a Superset dashboard into a mount div ──────────────
function embedDashboard(uuid, mountId, uiConfig = {}) {
  if (!uuid) {
    console.warn(`embedDashboard: no UUID provided for mount #${mountId}`);
    return;
  }
  const mountPoint = document.getElementById(mountId);
  if (!mountPoint) {
    console.warn(`embedDashboard: mount element #${mountId} not found`);
    return;
  }
  supersetEmbeddedSdk.embedDashboard({
    id: uuid,
    supersetDomain: 'https://superset.samrodgers.site',
    mountPoint,
    fetchGuestToken: () => fetchGuestToken(uuid),
    dashboardUiConfig: { hideTitle: true, hideTab: true, ...uiConfig },
  });
}

// ── Force iframe dimensions after SDK injection ──────────────
function resizeMount(mountId, width, height) {
  const mount = document.getElementById(mountId);
  if (!mount) return;
  const observer = new MutationObserver(() => {
    const iframe = mount.querySelector('iframe');
    if (iframe) {
      iframe.style.width = width;
      iframe.style.height = height;
      iframe.style.minWidth = width;
      iframe.style.minHeight = height;
      observer.disconnect();
    }
  });
  observer.observe(mount, { childList: true, subtree: true });
}