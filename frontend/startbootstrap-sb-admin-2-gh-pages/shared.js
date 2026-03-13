/* shared.js — live ticker + active nav highlighting */

// Mark active sidebar link based on current page
(function () {
  const path = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.sb-item[href]').forEach(el => {
    if (el.getAttribute('href') === path) el.classList.add('active');
    else el.classList.remove('active');
  });
})();

// Live company value ticker — replace fetch() target with your FastAPI EC2 endpoint
// e.g. fetch('https://your-ec2-host/api/company-value')
(function () {
  const el = document.getElementById('ticker-value');
  if (!el) return;

  let base = 4_821_039;
  let offset = 0;

  function fmt(n) {
    return '$' + Math.round(n).toLocaleString('en-US');
  }

  function refresh() {
    // TODO: replace mock with real API call:
    // fetch('/api/company-value')
    //   .then(r => r.json())
    //   .then(d => { el.textContent = fmt(d.value); });
    offset += (Math.random() - 0.47) * 1400;
    el.textContent = fmt(base + offset);
  }

  refresh();
  setInterval(refresh, 5000);
})();
