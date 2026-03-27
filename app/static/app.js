/* tiny helper: non-redirecting submits + spinners */
window.addEventListener('DOMContentLoaded', () => {
  const toast = document.getElementById('toast');

  function flash(msg, ms = 2500) {
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.add('on');
    setTimeout(() => toast.classList.remove('on'), ms);
  }

  document.querySelectorAll('form[data-async]').forEach((form) => {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const action = form.getAttribute('action');
      const method = (form.getAttribute('method') || 'POST').toUpperCase();
      const statusEl = form.querySelector('.status');
      if (statusEl) statusEl.textContent = '…';
      try {
        const body = new URLSearchParams(new FormData(form));
        const resp = await fetch(action, {
          method,
          body,
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
        });
        const data = await resp.json();
        if (statusEl) statusEl.textContent = data.message || resp.statusText;
        flash(data.ok === false ? data.message : 'saved');
      } catch (err) {
        if (statusEl) statusEl.textContent = 'error';
        flash(String(err));
      }
    });
  });

  document.querySelectorAll('[data-test]').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const url = btn.getAttribute('data-test');
      const statusEl = btn.closest('.test-action-row')?.querySelector('.status');
      if (statusEl) statusEl.textContent = '…';
      try {
        const resp = await fetch(url, { method: 'POST' });
        const data = await resp.json();
        if (statusEl) statusEl.textContent = data.ok ? 'ok' : (data.message || 'failed');
        flash(data.ok ? 'ok' : (data.message || 'failed'), 3000);
      } catch (err) {
        if (statusEl) statusEl.textContent = 'error';
        flash(String(err));
      }
    });
  });

  document.querySelectorAll('form[data-scan]').forEach((form) => {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = form.querySelector('button[type=submit]');
      if (btn) {
        btn.disabled = true;
        btn.classList.add('spin');
      }
      try {
        const resp = await fetch('/api/scan', { method: 'POST' });
        if (resp.ok) location.reload();
        else flash('scan failed ' + resp.status);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.classList.remove('spin');
        }
      }
    });
  });

  document.querySelectorAll('section.panel[data-accord]').forEach((sec) => {
    const toggle = sec.querySelector('.accord-toggle');
    const body = sec.querySelector('.accord-body');
    if (!toggle || !body) return;
    const saved = localStorage.getItem(sec.id);
    body.style.display = saved ?? 'block';
    toggle.addEventListener('click', () => {
      const open = body.style.display !== 'none';
      body.style.display = open ? 'none' : 'block';
      toggle.classList.toggle('closed', open);
      localStorage.setItem(sec.id, body.style.display);
    });
  });

  document.querySelectorAll('.fmt-time').forEach((el) => {
    const raw = (el.textContent || '').trim();
    if (!raw || raw === '-') return;
    const d = new Date(raw);
    if (Number.isNaN(d.getTime())) return;
    el.textContent = d.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  });
});
