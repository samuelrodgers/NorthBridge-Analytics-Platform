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

// ── Account modal ────────────────────────────────────────────
(function () {
  // Inject modal HTML
  const overlay = document.createElement('div');
  overlay.className = 'acct-overlay';
  overlay.id = 'acct-overlay';
  overlay.innerHTML = `
    <div class="acct-modal">
      <div class="acct-modal-hdr">
        <span class="acct-modal-title">Account</span>
        <button class="acct-close-btn" id="acct-close">&#x2715;</button>
      </div>
      <div class="acct-user-block">
        <div class="acct-avatar" id="acct-avatar">—</div>
        <div>
          <div class="acct-user-name" id="acct-name">—</div>
          <div class="acct-user-email" id="acct-email">—</div>
          <div class="acct-user-role-badge" id="acct-role">—</div>
        </div>
      </div>
      <div>
        <div class="acct-section-label">Change password</div>
        <div class="acct-form">
          <input class="acct-input" type="password" id="acct-current-pw" placeholder="Current password" autocomplete="current-password">
          <input class="acct-input" type="password" id="acct-new-pw"     placeholder="New password (min 8 chars)" autocomplete="new-password">
          <input class="acct-input" type="password" id="acct-confirm-pw" placeholder="Confirm new password" autocomplete="new-password">
          <div class="acct-feedback" id="acct-feedback"></div>
          <button class="acct-btn acct-btn-primary" id="acct-save-pw">Update password</button>
        </div>
      </div>
      <button class="acct-btn acct-btn-danger" id="acct-logout-btn">Sign out</button>
    </div>
  `;
  document.body.appendChild(overlay);

  // Apply role-based visibility on page load
  document.addEventListener('DOMContentLoaded', function () {
    fetch('/api/auth/me', { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then(u => {
        if (u && u.role === 'admin') {
          document.querySelectorAll('.admin-only').forEach(el => el.style.display = '');
        }
      })
      .catch(() => {});
  });

  // Live quarantine badge — update sidebar "Data quality" badge on every page
  document.addEventListener('DOMContentLoaded', function () {
    fetch('/api/quarantine/summary', { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        const badge = document.querySelector('.sb-badge');
        if (!badge) return;
        const total = data ? data.summary.reduce((s, r) => s + r.count, 0) : 0;
        if (total === 0) {
          badge.textContent = '●';
          badge.classList.add('sb-badge-ok');
        } else {
          badge.textContent = '!';
          badge.classList.remove('sb-badge-ok');
        }
      })
      .catch(() => {});
  });

  // Enhance sidebar footer — replace raw arrow button with labelled icon buttons
  document.addEventListener('DOMContentLoaded', function () {
    const logoutBtn = document.getElementById('logout-btn');
    if (!logoutBtn) return;

    // Wrap avatar + user-info siblings into a .sb-footer-user row
    const footer = logoutBtn.closest('.sb-footer');
    if (footer) {
      const avatar   = footer.querySelector('.sb-avatar');
      const userInfo = footer.querySelector('.sb-user-info');
      if (avatar && userInfo) {
        const userRow = document.createElement('div');
        userRow.className = 'sb-footer-user';
        avatar.before(userRow);
        userRow.appendChild(avatar);
        userRow.appendChild(userInfo);
      }
    }

    // Replace logout button with stacked labelled buttons
    const actions = document.createElement('div');
    actions.className = 'sb-footer-actions';
    actions.innerHTML = `
      <button class="sb-icon-btn" id="acct-open-btn" title="Account settings">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
        </svg>
        Account
      </button>
      <button class="sb-icon-btn" id="sidebar-logout-btn" title="Sign out">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
        </svg>
        Sign out
      </button>
    `;
    logoutBtn.replaceWith(actions);

    // Wire open/close
    document.getElementById('acct-open-btn').addEventListener('click', openModal);
    document.getElementById('acct-close').addEventListener('click', closeModal);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) closeModal(); });

    // Wire sign out buttons
    const doLogout = () => import('./auth.js').then(m => m.logout());
    document.getElementById('sidebar-logout-btn').addEventListener('click', doLogout);
    document.getElementById('acct-logout-btn').addEventListener('click', doLogout);

    // Wire change password
    document.getElementById('acct-save-pw').addEventListener('click', changePassword);
  });

  function openModal() {
    // Populate user info from existing DOM elements
    const name  = document.getElementById('nav-user-name')?.textContent || '—';
    const initials = name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);
    document.getElementById('acct-name').textContent   = name;
    document.getElementById('acct-avatar').textContent = initials;
    // Fetch email fresh
    fetch('/api/auth/me', { credentials: 'include' })
      .then(r => r.json())
      .then(u => {
        document.getElementById('acct-email').textContent = u.email || '—';
        const roleEl = document.getElementById('acct-role');
        roleEl.textContent = u.role || '—';
        roleEl.className = 'acct-user-role-badge' + (u.role === 'admin' ? ' admin' : '');
      })
      .catch(() => {});
    clearForm();
    overlay.classList.add('open');
  }

  function closeModal() {
    overlay.classList.remove('open');
    clearForm();
  }

  function clearForm() {
    ['acct-current-pw', 'acct-new-pw', 'acct-confirm-pw'].forEach(id => {
      document.getElementById(id).value = '';
    });
    setFeedback('', '');
  }

  function setFeedback(msg, type) {
    const el = document.getElementById('acct-feedback');
    el.textContent = msg;
    el.className = 'acct-feedback' + (type ? ' ' + type : '');
  }

  async function changePassword() {
    const current  = document.getElementById('acct-current-pw').value;
    const next     = document.getElementById('acct-new-pw').value;
    const confirm  = document.getElementById('acct-confirm-pw').value;

    if (!current || !next || !confirm) { setFeedback('All fields are required.', 'error'); return; }
    if (next !== confirm)              { setFeedback('New passwords do not match.', 'error'); return; }
    if (next.length < 8)              { setFeedback('Password must be at least 8 characters.', 'error'); return; }

    try {
      const res = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      const data = await res.json();
      if (!res.ok) { setFeedback(data.detail || 'Update failed.', 'error'); return; }
      setFeedback('Password updated successfully.', 'success');
      ['acct-current-pw', 'acct-new-pw', 'acct-confirm-pw'].forEach(id => {
        document.getElementById(id).value = '';
      });
    } catch (_) {
      setFeedback('Network error — please try again.', 'error');
    }
  }
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