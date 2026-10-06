/* DemandRadar shared front-end helpers */
window.DR = (function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  function toast(message, type = 'success') {
    let stack = $('.toast-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'toast-stack';
      stack.setAttribute('role', 'status');
      stack.setAttribute('aria-live', 'polite');
      document.body.appendChild(stack);
    }
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    const icon = document.createElement('i');
    icon.className = type === 'error' ? 'fas fa-circle-exclamation' : 'fas fa-circle-check';
    const text = document.createElement('span');
    text.textContent = message;
    el.append(icon, text);
    stack.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; setTimeout(() => el.remove(), 300); }, 4500);
  }

  async function request(url, options = {}) {
    try {
      const res = await fetch(url, options);
      let data = {};
      try { data = await res.json(); } catch (_) { /* non-json */ }
      if (!res.ok && data.success === undefined) data = { success: false, message: 'Request failed (' + res.status + ')' };
      return { ok: res.ok && data.success !== false, data };
    } catch (err) {
      return { ok: false, data: { success: false, message: 'Network error. Please check your connection and try again.' } };
    }
  }
  const postJSON = (url, body) => request(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
  });

  function setLoading(btn, loading, label) {
    btn.disabled = loading;
    btn.classList.toggle('loading', loading);
    if (label !== undefined) {
      const t = btn.querySelector('.btn-label');
      if (t) t.textContent = label;
    }
  }

  function clearErrors(form) {
    $$('.is-invalid', form).forEach(e => e.classList.remove('is-invalid'));
    $$('.field-error', form).forEach(e => e.remove());
  }
  function showErrors(form, errors) {
    let first = null;
    Object.entries(errors || {}).forEach(([name, msg]) => {
      const input = form.elements[name];
      if (!input) return;
      input.classList.add('is-invalid');
      const p = document.createElement('p');
      p.className = 'field-error';
      p.textContent = msg;
      (input.closest('.form-group') || input.parentElement).appendChild(p);
      first = first || input;
    });
    if (first && first.focus) first.focus();
  }

  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* Leaflet heat/circle map. Falls back to a message when Leaflet cannot load (offline). */
  function drawMap(el, clusters) {
    const wrap = el.closest('.map-wrap');
    if (typeof L === 'undefined') {
      if (wrap) { wrap.classList.add('empty'); $('.map-empty', wrap).textContent = 'Map could not be loaded. Check your internet connection.'; }
      return null;
    }
    if (!el._map) {
      el._map = L.map(el, { scrollWheelZoom: false }).setView([20.59, 78.96], 4);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors', maxZoom: 18
      }).addTo(el._map);
      el._layer = L.layerGroup().addTo(el._map);
    }
    el._layer.clearLayers();
    if (wrap) wrap.classList.toggle('empty', !clusters.length);
    if (!clusters.length) return el._map;
    const bounds = [];
    clusters.forEach(c => {
      const color = c.count >= 20 ? '#d93025' : c.count >= 10 ? '#f59e0b' : '#00875a';
      L.circleMarker([c.lat, c.lng], {
        radius: Math.min(30, 10 + Math.sqrt(c.count) * 3), color, fillColor: color, fillOpacity: .45, weight: 2
      }).bindPopup('<strong>' + esc(c.top_service) + '</strong><br>' + c.count + ' request' + (c.count > 1 ? 's' : '') +
        (c.location ? '<br>' + esc(c.location) : '')).addTo(el._layer);
      bounds.push([c.lat, c.lng]);
    });
    el._map.fitBounds(bounds, { padding: [40, 40], maxZoom: 12 });
    setTimeout(() => el._map.invalidateSize(), 100);
    return el._map;
  }

  function initNav() {
    const nav = $('.navbar'), toggle = $('.nav-toggle'), links = $('.nav-links');
    if (toggle) toggle.addEventListener('click', () => {
      const open = links.classList.toggle('open');
      toggle.setAttribute('aria-expanded', open);
    });
    $$('.nav-links a').forEach(a => a.addEventListener('click', () => links.classList.remove('open')));
    window.addEventListener('scroll', () => nav.classList.toggle('scrolled', window.scrollY > 10), { passive: true });
  }

  function initReveal() {
    const items = $$('.reveal');
    if (!('IntersectionObserver' in window)) { items.forEach(i => i.classList.add('visible')); return; }
    const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('visible'); io.unobserve(e.target); } }), { threshold: .1 });
    items.forEach(i => io.observe(i));
  }

  function initFeedback() {
    const widget = $('#feedbackWidget'), launcher = $('#feedbackLauncher');
    if (!widget) return;
    const form = $('#feedbackForm'), stars = $$('.stars button', widget), ratingInput = $('#rating');
    const toggle = open => { widget.classList.toggle('open', open); launcher.setAttribute('aria-expanded', open); };
    launcher.addEventListener('click', () => toggle(!widget.classList.contains('open')));
    $('.close-btn', widget).addEventListener('click', () => toggle(false));
    document.addEventListener('keydown', e => { if (e.key === 'Escape') toggle(false); });
    const paint = n => stars.forEach((s, i) => s.classList.toggle('active', i < n));
    stars.forEach((s, i) => s.addEventListener('click', () => { ratingInput.value = i + 1; paint(i + 1); }));
    form.addEventListener('submit', async e => {
      e.preventDefault();
      clearErrors(form);
      const btn = $('button[type=submit]', form);
      const rating = parseInt(ratingInput.value, 10);
      if (!rating) return toast('Please choose a star rating.', 'error');
      setLoading(btn, true);
      const { ok, data } = await postJSON('/submit-feedback', {
        rating, feedback: form.elements['feedback'].value, name: form.elements['name'].value
      });
      setLoading(btn, false);
      if (ok) {
        toast('Thank you for your feedback!');
        form.reset(); ratingInput.value = 0; paint(0); toggle(false);
        if (location.pathname === '/') setTimeout(() => location.reload(), 900);
      } else toast(data.message || 'Something went wrong.', 'error');
    });
  }

  document.addEventListener('DOMContentLoaded', () => { initNav(); initReveal(); initFeedback(); });
  return { $, $$, toast, request, postJSON, setLoading, clearErrors, showErrors, esc, drawMap };
})();
