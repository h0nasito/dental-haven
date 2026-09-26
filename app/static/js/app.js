// Progressive enhancement only; every page works without JavaScript.
document.addEventListener('DOMContentLoaded', function () {
  // Confirm destructive actions
  document.querySelectorAll('form[data-confirm]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (!window.confirm(form.getAttribute('data-confirm'))) e.preventDefault();
    });
  });
  // Auto-submit selects (branch switcher, filters)
  document.querySelectorAll('select[data-autosubmit]').forEach(function (sel) {
    sel.addEventListener('change', function () { sel.form.submit(); });
    var btn = sel.form.querySelector('.js-hide');
    if (btn) btn.hidden = true;
  });
  // Copy-to-clipboard buttons for templates/reminders
  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var el = document.getElementById(btn.getAttribute('data-copy'));
      if (!el || !navigator.clipboard) return;
      navigator.clipboard.writeText(el.innerText).then(function () {
        var old = btn.textContent; btn.textContent = 'Copied'; setTimeout(function () { btn.textContent = old; }, 1500);
      });
    });
  });
  // Public booking: refresh available times when branch/service/dentist/date change
  var bookForm = document.getElementById('booking-form');
  if (bookForm) {
    var slotBox = document.getElementById('slot-box');
    var refresh = function () {
      var fd = new FormData(bookForm);
      var params = new URLSearchParams();
      ['branch_id', 'service_id', 'dentist_id', 'date'].forEach(function (k) { if (fd.get(k)) params.set(k, fd.get(k)); });
      if (!params.get('branch_id') || !params.get('service_id') || !params.get('date')) return;
      slotBox.setAttribute('aria-busy', 'true');
      fetch(bookForm.getAttribute('data-slots-url') + '?' + params.toString(), { headers: { 'Accept': 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          slotBox.innerHTML = '';
          if (!data.slots.length) {
            slotBox.innerHTML = '<p class="muted">No open times on this date. Please try another day or branch.</p>';
          } else {
            var grid = document.createElement('div'); grid.className = 'slot-grid'; grid.setAttribute('role', 'radiogroup');
            data.slots.forEach(function (s, i) {
              var lab = document.createElement('label');
              var inp = document.createElement('input'); inp.type = 'radio'; inp.name = 'time'; inp.value = s; inp.required = true;
              var sp = document.createElement('span'); sp.textContent = data.labels[i];
              lab.appendChild(inp); lab.appendChild(sp); grid.appendChild(lab);
            });
            slotBox.appendChild(grid);
          }
          slotBox.removeAttribute('aria-busy');
        })
        .catch(function () { slotBox.removeAttribute('aria-busy'); });
    };
    ['branch_id', 'service_id', 'dentist_id', 'date'].forEach(function (k) {
      var el = bookForm.elements[k]; if (el) el.addEventListener('change', refresh);
    });
    var noJs = document.getElementById('slot-nojs'); if (noJs) noJs.hidden = true;
  }

  // ---------------- Landing page (home) ----------------
  if (document.body.classList.contains('landing')) {
    // Reveal sections as they scroll into view
    var reveals = document.querySelectorAll('.reveal');
    if ('IntersectionObserver' in window && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      document.documentElement.classList.add('js-reveal');
      document.body.classList.add('js-reveal');
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target); } });
      }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
      reveals.forEach(function (el) { io.observe(el); });
    }
    // Portfolio filters
    var filterBtns = document.querySelectorAll('.lp-filters button');
    filterBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var f = btn.getAttribute('data-filter');
        filterBtns.forEach(function (b) { var on = b === btn; b.classList.toggle('is-active', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); });
        document.querySelectorAll('.lp-gallery .lp-case').forEach(function (c) {
          c.classList.toggle('is-hidden', f !== 'all' && c.getAttribute('data-cat') !== f);
          c.classList.add('is-in');
        });
      });
    });
    // Before / after sliders
    document.querySelectorAll('.ba').forEach(function (ba) {
      var r = ba.querySelector('.ba-range');
      if (!r) return;
      var set = function () { ba.style.setProperty('--pos', r.value + '%'); };
      r.addEventListener('input', set); set();
    });
    // Lightbox
    var lb = document.getElementById('lightbox');
    if (lb && typeof lb.showModal === 'function') {
      document.querySelectorAll('.lp-case-open').forEach(function (btn) {
        btn.addEventListener('click', function () {
          lb.querySelector('img').src = btn.getAttribute('data-full');
          lb.querySelector('img').alt = btn.getAttribute('data-title') || '';
          var cap = btn.getAttribute('data-title') || '';
          if (btn.getAttribute('data-caption')) cap += ' · ' + btn.getAttribute('data-caption');
          lb.querySelector('p').textContent = cap;
          lb.showModal();
        });
      });
      lb.addEventListener('click', function (e) { if (e.target === lb) lb.close(); });
    }
    // One-page navigation: highlight the menu link for the section in view
    var navLinks = {};
    document.querySelectorAll('.site-nav a[href*="#"]').forEach(function (a) {
      var id = a.getAttribute('href').split('#')[1];
      if (id) navLinks[id] = a;
    });
    var spySections = Object.keys(navLinks).map(function (id) { return document.getElementById(id); }).filter(Boolean);
    if ('IntersectionObserver' in window && spySections.length) {
      var spy = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (!e.isIntersecting) return;
          Object.keys(navLinks).forEach(function (id) { navLinks[id].classList.toggle('is-active', id === e.target.id); });
        });
      }, { rootMargin: '-45% 0px -50% 0px' });
      spySections.forEach(function (sec) { spy.observe(sec); });
    }
    // Back-to-top button
    var topBtn = document.querySelector('.lp-top');
    if (topBtn) {
      var onScroll = function () { topBtn.classList.toggle('is-shown', window.scrollY > 700); };
      window.addEventListener('scroll', onScroll, { passive: true }); onScroll();
    }
    // Close the mobile menu after tapping a section link
    document.querySelectorAll('.site-nav a[href*="#"]').forEach(function (a) {
      a.addEventListener('click', function () { var t = document.getElementById('nav-toggle'); if (t) t.checked = false; });
    });
  }
});

/* Quotations: picking a treatment from the price list fills in its description and starting price. */
(function () {
  document.querySelectorAll("select[data-quote-price]").forEach(function (sel) {
    var form = sel.closest("form");
    sel.addEventListener("change", function () {
      var opt = sel.options[sel.selectedIndex];
      var price = form.querySelector("[name=unit_price]"), desc = form.querySelector("[name=description]");
      if (opt && opt.dataset.price) { price.value = opt.dataset.price; desc.value = opt.dataset.name || ""; }
      else { price.value = ""; desc.value = ""; desc.focus(); }
    });
  });
})();
