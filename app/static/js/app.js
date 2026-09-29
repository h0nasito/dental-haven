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

/* Time clock: location for time in/out, and "Use my current location" on the setup page. */
(function () {
  // Time clock: fill in the phone's location before timing in/out
  document.querySelectorAll('form[data-geo]').forEach(function (form) {
    var status = form.querySelector('[data-geo-status]');
    var say = function (t) { if (status) status.textContent = t; };
    if (!navigator.geolocation) { say('Location isn\u2019t available on this device; your manager will review your time.'); return; }
    navigator.geolocation.getCurrentPosition(function (pos) {
      form.elements.lat.value = pos.coords.latitude.toFixed(6);
      form.elements.lng.value = pos.coords.longitude.toFixed(6);
      form.elements.acc.value = Math.round(pos.coords.accuracy);
      say('Location found (within about ' + Math.round(pos.coords.accuracy) + ' m).');
    }, function () {
      say('Location is off or was not allowed. You can still time in, but your manager will review it. To fix: allow location for this site in your browser settings.');
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
  });
  // Time clock setup: "Use my current location"
  document.querySelectorAll('form[data-geo-set]').forEach(function (form) {
    var btn = form.querySelector('[data-geo-fill]');
    var status = form.querySelector('[data-geo-status]');
    if (!btn) return;
    btn.addEventListener('click', function () {
      if (!navigator.geolocation) { status.textContent = 'Location isn\u2019t available on this device.'; return; }
      status.textContent = 'Getting your location…';
      navigator.geolocation.getCurrentPosition(function (pos) {
        form.querySelector('[data-geo-lat]').value = pos.coords.latitude.toFixed(6);
        form.querySelector('[data-geo-lng]').value = pos.coords.longitude.toFixed(6);
        status.textContent = 'Got it (within about ' + Math.round(pos.coords.accuracy) + ' m). Tap Save.';
      }, function () { status.textContent = 'Location was not allowed. Allow location for this site and try again.'; },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
    });
  });
})();

/* Sidebar accordion: opening one group closes the others. */
(function () {
  var groups = document.querySelectorAll('details.nav-acc');
  groups.forEach(function (d) {
    d.addEventListener('toggle', function () {
      if (!d.open) return;
      groups.forEach(function (o) { if (o !== d) o.open = false; });
    });
  });
})();

/* Add payment: several payment lines, live summary, and the patient's signature pad. */
(function () {
  function peso(c) { return '₱' + (c / 100).toLocaleString('en-PH', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function cents(v) { var n = parseFloat(String(v || '').replace(/[^0-9.]/g, '')); return isNaN(n) ? 0 : Math.round(n * 100); }
  document.querySelectorAll('form[data-payform]').forEach(function (form) {
    var total = parseInt(form.dataset.total, 10) || 0, paid = parseInt(form.dataset.paid, 10) || 0;
    var list = form.querySelector('[data-pay-lines]');
    function update() {
      var now = 0;
      form.querySelectorAll('[data-pay-amt]').forEach(function (i) { now += cents(i.value); });
      form.querySelector('[data-pay-now]').textContent = peso(now);
      form.querySelector('[data-pay-left]').textContent = peso(Math.max(0, total - paid - now));
      comm(now);
    }
    // Dentist commission on this payment: pre-filled with the dentist's usual %, after the bill's lab fee share.
    var box = form.querySelector('[data-comm]');
    function comm(now) {
      if (!box) return;
      var sel = box.querySelector('[data-comm-dentist]'), mode = box.querySelector('[data-comm-mode]').value;
      var out = box.querySelector('[data-comm-calc]');
      box.querySelector('[data-comm-pctbox]').hidden = mode !== 'percent';
      box.querySelector('[data-comm-amtbox]').hidden = mode !== 'amount';
      if (!sel.value) { out.textContent = 'No commission on this payment.'; return; }
      var lab = parseInt(box.dataset.lab, 10) || 0;
      var share = (lab && total) ? Math.min(now, Math.round(now * lab / total)) : 0;
      var base = now - share;
      if (mode === 'amount') { out.textContent = 'Commission: ' + peso(cents(box.querySelector('[data-comm-amt]').value)); return; }
      var pct = parseFloat(box.querySelector('[data-comm-pct]').value);
      if (isNaN(pct)) { out.textContent = 'Enter the commission %.'; return; }
      out.textContent = 'Commission: ' + peso(Math.round(base * pct / 100)) + '  (' + pct + '% of ' + peso(base) +
        (share ? ', after lab fee share ' + peso(share) : '') + ')';
    }
    if (box) {
      var dsel = box.querySelector('[data-comm-dentist]'), pctIn = box.querySelector('[data-comm-pct]');
      function fillRate() { var o = dsel.options[dsel.selectedIndex]; if (o && o.dataset.rate) pctIn.value = o.dataset.rate; }
      dsel.addEventListener('change', fillRate);
      if (!pctIn.value) fillRate();
    }
    form.addEventListener('input', update);
    form.addEventListener('change', update);
    form.querySelector('[data-pay-add]').addEventListener('click', function () {
      var first = list.querySelector('[data-pay-line]');
      var line = first.cloneNode(true);
      line.querySelector('[data-pay-amt]').value = '';
      list.appendChild(line);
      line.querySelector('select').focus();
      update();
    });
    list.addEventListener('click', function (e) {
      var del = e.target.closest('[data-pay-del]');
      if (!del) return;
      var lines = list.querySelectorAll('[data-pay-line]');
      if (lines.length > 1) del.closest('[data-pay-line]').remove(); else lines[0].querySelector('[data-pay-amt]').value = '';
      update();
    });
    form.addEventListener('submit', function (e) {
      var canvas = form.querySelector('[data-sigpad]');
      var reason = form.querySelector('[name=not_signed_reason]');
      if (!(canvas && canvas.dataset.drawn === '1') && !(reason && reason.value.trim())) {
        e.preventDefault();
        alert('Please ask the patient to sign, or open "Patient can\u2019t sign" and give the reason.');
      }
    });
    update();
  });
})();

/* Dialogs opened by a button: <button data-open="dialog-id">. Row "⋯" menus close when you click elsewhere. */
(function () {
  document.addEventListener('click', function (e) {
    var opener = e.target.closest('[data-open]');
    if (opener) {
      var d = document.getElementById(opener.getAttribute('data-open'));
      if (d && d.showModal) { e.preventDefault(); d.showModal(); }
    }
    var closer = e.target.closest('[data-close]');
    if (closer) { var dlg = closer.closest('dialog'); if (dlg) dlg.close(); }
    document.querySelectorAll('details.kebab[open]').forEach(function (k) { if (!k.contains(e.target)) k.open = false; });
  });
})();

/* Signature pads: <canvas data-sigpad> + hidden [data-sig-out] + [data-sig-clear], inside a form. */
(function () {
  document.querySelectorAll('canvas[data-sigpad]').forEach(function (canvas) {
    var form = canvas.closest('form'), out = form.querySelector('[data-sig-out]');
    var ctx = canvas.getContext('2d'), drawing = false, last = null;
    ctx.lineWidth = 2.5; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = '#111';
    function pos(e) {
      var r = canvas.getBoundingClientRect();
      return { x: (e.clientX - r.left) * canvas.width / r.width, y: (e.clientY - r.top) * canvas.height / r.height };
    }
    canvas.addEventListener('pointerdown', function (e) { drawing = true; last = pos(e); canvas.setPointerCapture(e.pointerId); e.preventDefault(); });
    canvas.addEventListener('pointermove', function (e) {
      if (!drawing) return;
      var p = pos(e);
      ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(p.x, p.y); ctx.stroke();
      last = p; canvas.dataset.drawn = '1'; e.preventDefault();
    });
    ['pointerup', 'pointercancel', 'pointerleave'].forEach(function (ev) { canvas.addEventListener(ev, function () { drawing = false; }); });
    var clear = form.querySelector('[data-sig-clear]');
    if (clear) clear.addEventListener('click', function () { ctx.clearRect(0, 0, canvas.width, canvas.height); canvas.dataset.drawn = ''; out.value = ''; });
    // capture phase: fill the hidden field before other submit handlers look at it
    form.addEventListener('submit', function (e) {
      var draft = e.submitter && e.submitter.value === 'draft';
      out.value = (canvas.dataset.drawn === '1' && !draft) ? canvas.toDataURL('image/png') : '';
    }, true);
  });
})();

/* New progress note: service search fills the price, teeth set the quantity, live totals. */
(function () {
  var form = document.querySelector('form[data-pnform]');
  if (!form) return;
  var tbody = form.querySelector('[data-pn-lines]');
  function cents(v) { var n = parseFloat(String(v || '').replace(/[^0-9.]/g, '')); return isNaN(n) ? 0 : Math.round(n * 100); }
  function money(c) { return (c / 100).toLocaleString('en-PH', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function teeth(t) { return String(t || '').split(/[,\s;\/]+/).filter(Boolean).length; }
  function recalc() {
    var total = 0;
    tbody.querySelectorAll('[data-pn-line]').forEach(function (row) {
      var qtyIn = row.querySelector('[data-pn-qty]');
      var qty = parseInt(qtyIn.value, 10) || Math.max(1, teeth(row.querySelector('[data-pn-tooth]').value));
      var sub = qty * cents(row.querySelector('[data-pn-price]').value);
      var pct = Math.min(100, parseFloat(row.querySelector('[data-pn-disc]').value) || 0);
      var net = sub - Math.round(sub * pct / 100);
      row.querySelector('[data-pn-sub]').textContent = money(sub);
      row.querySelector('[data-pn-net]').textContent = money(net);
      total += net;
    });
    var billPct = Math.min(100, parseFloat(form.querySelector('[data-pn-billdisc]').value) || 0);
    form.querySelector('[data-pn-subtotal]').textContent = '\u20B1' + money(total);
    form.querySelector('[data-pn-total]').textContent = '\u20B1' + money(total - Math.round(total * billPct / 100));
  }
  form.addEventListener('input', function (e) {
    var row = e.target.closest('[data-pn-line]');
    if (row && e.target.matches('[data-pn-desc]')) {
      var opt = null;
      document.querySelectorAll('#pn-services option').forEach(function (o) { if (o.value === e.target.value) opt = o; });
      row.querySelector('[data-pn-sid]').value = opt ? opt.dataset.sid : '';
      if (opt && opt.dataset.price) row.querySelector('[data-pn-price]').value = opt.dataset.price;
    }
    if (row && e.target.matches('[data-pn-tooth]')) {
      var q = row.querySelector('[data-pn-qty]');
      if (!q.dataset.touched) q.value = teeth(e.target.value) > 1 ? teeth(e.target.value) : '';
    }
    if (e.target.matches('[data-pn-qty]')) e.target.dataset.touched = '1';
    recalc();
  });
  form.querySelector('[data-pn-add]').addEventListener('click', function () {
    var row = tbody.querySelector('[data-pn-line]').cloneNode(true);
    row.querySelectorAll('input').forEach(function (i) { i.value = ''; delete i.dataset.touched; });
    tbody.appendChild(row);
    row.querySelector('[data-pn-desc]').focus();
    recalc();
  });
  tbody.addEventListener('click', function (e) {
    var del = e.target.closest('[data-pn-del]');
    if (!del) return;
    var rows = tbody.querySelectorAll('[data-pn-line]');
    if (rows.length > 1) del.closest('[data-pn-line]').remove();
    else rows[0].querySelectorAll('input').forEach(function (i) { i.value = ''; });
    recalc();
  });
  var files = form.querySelector('[data-pn-files]'), list = form.querySelector('[data-pn-filelist]');
  if (files) {
    var zone = files.closest('.dropzone');
    ['dragover', 'dragenter'].forEach(function (ev) { zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.add('over'); }); });
    ['dragleave', 'drop'].forEach(function (ev) { zone.addEventListener(ev, function () { zone.classList.remove('over'); }); });
    zone.addEventListener('drop', function (e) { e.preventDefault(); files.files = e.dataTransfer.files; files.dispatchEvent(new Event('change')); });
    files.addEventListener('change', function () {
      list.innerHTML = '';
      Array.prototype.forEach.call(files.files, function (f) { var li = document.createElement('li'); li.textContent = '📎 ' + f.name; list.appendChild(li); });
    });
  }
  recalc();
  var dlg = document.querySelector('dialog[data-autoopen]');
  if (dlg && dlg.showModal) dlg.showModal();
})();
