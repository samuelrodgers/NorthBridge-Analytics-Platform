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

// ── Query-ref toggle buttons ─────────────────────────────────
// Injects an "ⓘ schema" button into each .section-hdr that precedes
// a .query-ref block. Clicking toggles the block open/closed.
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.query-ref').forEach(function (ref) {
    const hdr = ref.previousElementSibling;
    if (!hdr || !hdr.classList.contains('section-hdr')) return;
    const btn = document.createElement('button');
    btn.className = 'query-ref-toggle';
    btn.innerHTML = 'ⓘ schema';
    btn.addEventListener('click', function () {
      const open = ref.classList.toggle('open');
      btn.innerHTML = open ? '✕ schema' : 'ⓘ schema';
    });
    hdr.appendChild(btn);
  });
});

// ── Live EUR→USD platform value ticker ──────────────────────
// Fetches total EUR-denominated revenue converted at the current live
// EUR/USD rate. Refreshes every 5 seconds — the value fluctuates because
// the exchange rate moves, not because new transactions arrived.
(function () {
  const el = document.getElementById('ticker-value');
  if (!el) return;

  function fmt(n) {
    return '$' + Math.round(n).toLocaleString('en-US');
  }

  async function refresh() {
    try {
      const res = await fetch('/api/value', { credentials: 'include' });
      if (!res.ok) return;
      const { value } = await res.json();
      el.textContent = fmt(value);
    } catch (_) {}
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
  industry:   '75c09c9f-faf0-448b-9215-bda18bbf87f7', 
  analytics:  '3bc8f17c-3e49-4611-98df-545a061c65ed',
  quarantine: '8a6dfe5e-3f6e-49b8-8b83-757895c58d25',
  pipeline:   '9a9fdd7c-27fc-4c4b-8d54-af074a2f8f52',
  fx:         'ea995c11-ac00-48ed-a92e-8529978b19fb',
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
      iframe.style.minWidth = '0';
      iframe.style.minHeight = height;
      observer.disconnect();
    }
  });
  observer.observe(mount, { childList: true, subtree: true });
}