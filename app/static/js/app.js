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
  // File pickers that upload as soon as a file is chosen (e.g. "+ Add picture")
  document.querySelectorAll('input[type=file][data-autosubmit]').forEach(function (inp) {
    inp.addEventListener('change', function () { if (inp.files.length) inp.form.submit(); });
    var btn = inp.form.querySelector('.js-hide');
    if (btn) btn.hidden = true;
  });
  // Copy-to-clipboard buttons for templates/reminders
  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var el = document.getElementById(btn.getAttribute('data-copy'));
      if (!el || !navigator.clipboard) return;
      navigator.clipboard.writeText(el.value !== undefined && el.tagName === 'INPUT' ? el.value : el.innerText).then(function () {
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
  // Time clock: "I'm on the field" shows the reason box and makes it required.
  document.querySelectorAll('[data-field-toggle]').forEach(function (cb) {
    var box = cb.closest('.field').querySelector('[data-field-box]');
    if (!box) return;
    var input = box.querySelector('input');
    function sync() { box.hidden = !cb.checked; if (input) input.required = cb.checked; }
    cb.addEventListener('change', sync); sync();
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

/* Action menus (⋯) inside scrolling tables: make room below so the open menu isn't cut off. Also re-measures when a
   section inside the menu (e.g. "Edit …") opens. */
(function () {
  document.addEventListener('toggle', function (e) {
    var k = e.target.closest && e.target.closest('details.kebab');
    if (!k) return;
    var wrap = k.closest('.table-wrap');
    if (!wrap) return;
    wrap.style.paddingBottom = '';
    if (!k.open) return;
    var menu = k.querySelector('.kebab-menu');
    if (!menu) return;
    var need = menu.getBoundingClientRect().bottom - wrap.getBoundingClientRect().bottom + 16;
    if (need > 0) wrap.style.paddingBottom = need + 'px';
    if (menu.getBoundingClientRect().bottom > window.innerHeight) menu.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, true);
})();

/* Price list pickers: <select data-price-pick data-desc="#input" data-price="#input"> fills the description and price. */
(function () {
  // delegated, so pickers added later (e.g. another case on a new work) work too.
  // data-price="block" fills the price box of the same case block.
  document.addEventListener('change', function (e) {
    var sel = e.target;
    if (!sel.matches || !sel.matches('select[data-price-pick]')) return;
    var opt = sel.options[sel.selectedIndex];
    if (!opt || !opt.getAttribute('data-price')) return;
    var dsel = sel.getAttribute('data-desc'), psel = sel.getAttribute('data-price');
    var row = sel.closest('.extra-row');
    var d = dsel === 'row' ? row.querySelector('[name="x_desc"]') : (dsel && document.querySelector(dsel));
    var p = psel === 'row' ? row.querySelector('[name="x_price"]') :
      (psel === 'block' ? sel.closest('.case-block').querySelector('[name="price"]') : (psel && document.querySelector(psel)));
    if (d && opt.getAttribute('data-name')) d.value = opt.getAttribute('data-name');
    if (p) p.value = opt.getAttribute('data-price');
  });
})();

/* Signature pads: <canvas data-sigpad> + hidden [data-sig-out] + [data-sig-clear], inside a form. */
(function () {
  document.querySelectorAll('canvas[data-sigpad]').forEach(function (canvas) {
    // Each pad uses the hidden field and Clear button of its own fieldset, so a form can hold several pads.
    var form = canvas.closest('form'), box = canvas.closest('fieldset') || form, out = box.querySelector('[data-sig-out]');
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
    var clear = box.querySelector('[data-sig-clear]');
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
      var qty = parseInt(qtyIn.value, 10) || (row.dataset.percount === '0' ? 1 : Math.max(1, teeth(row.querySelector('[data-pn-tooth]').value)));
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
      if (opt) {
        row.dataset.percount = opt.dataset.percount || '1';
        var qq = row.querySelector('[data-pn-qty]');
        if (opt.dataset.percount === '0' && !qq.dataset.touched) qq.value = '';
      }
    }
    if (row && e.target.matches('[data-pn-tooth]')) {
      var q = row.querySelector('[data-pn-qty]');
      if (!q.dataset.touched && row.dataset.percount !== '0') q.value = teeth(e.target.value) > 1 ? teeth(e.target.value) : '';
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

/* Evaluation form: "answered X of Y" and jump to the first unanswered question. */
(function () {
  var form = document.querySelector('form[data-evalform]');
  if (!form) return;
  var qs = form.querySelectorAll('.eval-q'), out = form.querySelector('[data-eval-progress]');
  function update() {
    var done = 0;
    qs.forEach(function (q) { if (q.querySelector('input:checked')) { done++; q.classList.remove('unanswered'); } });
    out.textContent = done + ' of ' + qs.length + ' answered';
  }
  form.addEventListener('change', update);
  // picking the staff member also picks their branch
  var subj = form.querySelector('[data-eval-subject]'), br = form.querySelector('[data-eval-branch]');
  if (subj && br) subj.addEventListener('change', function () {
    var o = subj.options[subj.selectedIndex], b = o && o.dataset.branch;
    if (b && br.querySelector('option[value="' + b + '"]')) br.value = b;
  });
  form.addEventListener('submit', function (e) {
    var first = null;
    qs.forEach(function (q) { if (!q.querySelector('input:checked')) { q.classList.add('unanswered'); if (!first) first = q; } });
    if (first) { e.preventDefault(); first.scrollIntoView({ behavior: 'smooth', block: 'center' }); first.querySelector('input').focus({ preventScroll: true }); }
  });
  update();
})();

/* Print buttons: <button data-print> */
(function () {
  document.querySelectorAll('[data-print]').forEach(function (b) { b.addEventListener('click', function () { window.print(); }); });
})();

/* Bill line: pick from the fee schedule to fill the description and unit price. */
(function () {
  document.querySelectorAll('input[data-fee-pick]').forEach(function (inp) {
    var form = inp.closest('form'), list = document.getElementById(inp.getAttribute('list'));
    inp.addEventListener('change', function () {
      var opt = null;
      list.querySelectorAll('option').forEach(function (o) { if (o.value === inp.value) opt = o; });
      if (!opt) return;
      form.querySelector('[name=description]').value = inp.value;
      form.querySelector('[name=unit_price]').value = opt.dataset.price;
    });
  });
})();

/* Quotation (simple editor): picking a procedure from the list fills in its price. */
(function () {
  document.querySelectorAll('input[data-q-proc]').forEach(function (inp) {
    var form = inp.closest('form'), list = document.getElementById(inp.getAttribute('list')), price = form.querySelector('[data-q-price]');
    inp.addEventListener('change', function () {
      var opt = null;
      list.querySelectorAll('option').forEach(function (o) { if (o.value === inp.value) opt = o; });
      if (opt && price && (!price.value || price.dataset.auto)) { price.value = opt.dataset.price; price.dataset.auto = '1'; }
    });
    if (price) price.addEventListener('input', function () { price.dataset.auto = ''; });
  });
})();

/* Expenses: total = qty x unit price (until the total is typed by hand). */
(function () {
  document.querySelectorAll('form[data-expform]').forEach(function (f) {
    var q = f.querySelector('[data-exp-qty]'), u = f.querySelector('[data-exp-unit]'), t = f.querySelector('[data-exp-total]');
    function calc() {
      if (t.dataset.typed) return;
      var qq = parseFloat(q.value), uu = parseFloat(String(u.value).replace(/[^0-9.]/g, ''));
      t.value = (qq > 0 && uu >= 0) ? (Math.round(qq * uu * 100) / 100).toFixed(2) : '';
    }
    q.addEventListener('input', calc); u.addEventListener('input', calc);
    t.addEventListener('input', function () { t.dataset.typed = t.value ? '1' : ''; });
  });
})();

/* Radio buttons that submit their form when changed (report type). */
(function () {
  document.querySelectorAll('input[data-autosubmit-radio]').forEach(function (r) {
    r.addEventListener('change', function () { r.form.submit(); });
  });
})();

/* Quotation: picking from the fee schedule fills description, price and unit. */
(function () {
  document.querySelectorAll('[data-q-fee]').forEach(function (inp) {
    var form = inp.closest('form'), list = document.getElementById('q-fees');
    inp.addEventListener('change', function () {
      var opt = null;
      list.querySelectorAll('option').forEach(function (o) { if (o.value === inp.value) opt = o; });
      if (!opt) return;
      var d = form.querySelector('[data-q-desc]'), p = form.querySelector('[data-q-price]'), u = form.querySelector('[data-q-unit]');
      if (!d.value) d.value = inp.value.replace(/\s*\(.*\)$/, '').toLowerCase().replace(/(^|[\s\-\/(])([a-z])/g, function (m, a, b) { return a + b.toUpperCase(); });
      p.value = opt.dataset.price;
      var unit = (opt.dataset.unit || '').toLowerCase(), words = ['canal', 'unit', 'tooth', 'arch', 'surface', 'bracket', 'scan', 'cc', 'quadrant', 'case', 'cycle'];
      for (var i = 0; i < words.length; i++) { if (unit.indexOf(words[i]) >= 0) { u.value = words[i]; break; } }
    });
  });
})();

/* Quotation: choosing from the clinic's item list fills the line (description, price, unit, type, section, note). */
(function () {
  document.querySelectorAll('[data-q-preset]').forEach(function (sel) {
    var form = sel.closest('form');
    sel.addEventListener('change', function () {
      var o = sel.options[sel.selectedIndex];
      if (!o || !o.value) return;
      form.querySelector('[data-q-desc]').value = o.dataset.name;
      form.querySelector('[data-q-price]').value = o.dataset.price;
      form.querySelector('[data-q-unit]').value = o.dataset.unit;
      form.querySelector('[name=kind]').value = o.dataset.kind;
      var sec = form.querySelector('[name=section]'); if (!sec.value && o.dataset.section) sec.value = o.dataset.section;
      var note = form.querySelector('[data-q-note]'); if (!note.value && o.dataset.note) note.value = o.dataset.note;
    });
  });
})();

/* Quotation: add several procedures at once (rows; choosing a procedure fills its price and type). */
(function () {
  document.querySelectorAll('form[data-q-many]').forEach(function (form) {
    var body = form.querySelector('[data-q-rows]'), list = document.getElementById('q-procs');
    function wire(row) {
      var proc = row.querySelector('[data-q-proc]');
      proc.addEventListener('change', function () {
        var opt = null;
        list.querySelectorAll('option').forEach(function (o) { if (o.value === proc.value && !opt) opt = o; });
        if (!opt) return;
        row.querySelector('[data-q-mprice]').value = opt.dataset.price;
        row.querySelector('[data-q-mkind]').value = opt.dataset.kind || 'item';
      });
      row.querySelector('[data-q-del]').addEventListener('click', function () {
        if (body.querySelectorAll('[data-q-row]').length > 1) { row.remove(); }
        else { row.querySelectorAll('input').forEach(function (i) { i.value = i.name === 'm_qty' ? '1' : ''; }); }
      });
    }
    body.querySelectorAll('[data-q-row]').forEach(wire);
    form.querySelector('[data-q-addrow]').addEventListener('click', function () {
      var rows = body.querySelectorAll('[data-q-row]'), clone = rows[rows.length - 1].cloneNode(true);
      clone.querySelectorAll('input').forEach(function (i) { i.value = i.name === 'm_qty' ? '1' : ''; });
      clone.querySelector('[data-q-mkind]').value = 'item';
      body.appendChild(clone); wire(clone);
      clone.querySelector('[data-q-proc]').focus();
    });
  });
})();

/* Lists with checkboxes: "select all on this page", a live count, and confirm on dangerous buttons. */
(function () {
  document.querySelectorAll('form[data-bulk]').forEach(function (form) {
    var all = form.querySelector('[data-check-all]'), count = form.querySelector('[data-check-count]');
    var boxes = function () { return form.querySelectorAll('[data-check]'); };
    function update() {
      var n = 0; boxes().forEach(function (b) { if (b.checked) n++; });
      if (count) count.textContent = n + ' selected';
      if (all) { all.checked = n > 0 && n === boxes().length; all.indeterminate = n > 0 && n < boxes().length; }
    }
    if (all) all.addEventListener('change', function () { boxes().forEach(function (b) { b.checked = all.checked; }); update(); });
    boxes().forEach(function (b) { b.addEventListener('change', update); });
    form.querySelectorAll('button[data-confirm]').forEach(function (btn) {
      btn.addEventListener('click', function (e) { if (!window.confirm(btn.getAttribute('data-confirm'))) e.preventDefault(); });
    });
    update();
  });
})();

/* Confirm on single buttons marked data-confirm (outside the bulk-action lists, which handle their own). */
(function () {
  document.querySelectorAll('button[data-confirm]').forEach(function (btn) {
    if (btn.closest('form[data-bulk]')) return;
    btn.addEventListener('click', function (e) { if (!window.confirm(btn.getAttribute('data-confirm'))) e.preventDefault(); });
  });
})();

/* Group chat: send without reloading, and show new messages every few seconds while the page is open. */
(function () {
  var chat = document.getElementById('chat');
  if (!chat || chat.getAttribute('data-after') === '') return;
  var form = document.getElementById('chat-form');
  var box = document.getElementById('chat-body');
  var err = document.getElementById('chat-err');
  var token = form ? form.querySelector('[name=csrf_token]').value : '';
  var after = parseInt(chat.getAttribute('data-after') || '0', 10);
  var first = parseInt(chat.getAttribute('data-first') || '0', 10);
  var removeUrl = chat.getAttribute('data-remove-url');
  var pinUrl = chat.getAttribute('data-pin-url');
  var pinsBox = document.getElementById('pins');
  var pinList = document.getElementById('pin-list');
  var busy = false;
  var ePanel = document.getElementById('emoji-panel'), eBtn = document.getElementById('emoji-btn');

  function nearBottom() { return window.innerHeight + window.scrollY >= document.body.scrollHeight - 160; }
  function toBottom() { var b = document.getElementById('bottom'); if (b) b.scrollIntoView({ block: 'end' }); }
  function lastDay() { var d = chat.querySelectorAll('.chat-day'); return d.length ? d[d.length - 1].getAttribute('data-day') : ''; }
  function fmtDay(iso) {
    var p = iso.split('-'); var m = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return m[parseInt(p[1], 10) - 1] + ' ' + p[2] + ', ' + p[0];
  }
  function markRemoved(el) {
    el.classList.add('removed');
    var t = el.querySelector('.text'); if (t) t.textContent = 'Message removed';
    el.querySelectorAll('form, a[data-reply], .reply-quote').forEach(function (f) { f.remove(); });
    setPinned(el, false);
  }
  function pinForm(id, pinned) {
    var f = document.createElement('form');
    f.method = 'post'; f.action = pinUrl.replace(/\/0\/pin$/, '/' + id + '/pin');
    var h = document.createElement('input'); h.type = 'hidden'; h.name = 'csrf_token'; h.value = token; f.appendChild(h);
    var b = document.createElement('button'); b.className = 'rm'; b.setAttribute('data-pin', id); b.textContent = pinned ? 'Unpin' : 'Pin'; f.appendChild(b);
    return f;
  }
  function setPinned(el, on) {
    el.classList.toggle('is-pinned', on);
    var tag = el.querySelector('.pin-tag');
    if (on && !tag) { tag = document.createElement('span'); tag.className = 'pin-tag'; tag.textContent = '📌'; el.querySelector('.who').insertBefore(tag, el.querySelector('.who').firstChild); }
    if (!on && tag) tag.remove();
    var b = el.querySelector('button[data-pin]'); if (b) b.textContent = on ? 'Unpin' : 'Pin';
  }
  function renderPins(pins) {
    if (!pinList) return;
    pinList.textContent = '';
    pins.forEach(function (m) {
      var row = document.createElement('div'); row.className = 'pin-item'; row.setAttribute('data-id', m.id);
      var left = document.createElement('div');
      var a = document.createElement('a'); a.href = '#m' + m.id;
      var t = document.createElement('span'); t.className = 'text'; t.textContent = m.body; a.appendChild(t); left.appendChild(a);
      left.appendChild(document.createElement('br'));
      var sm = document.createElement('small'); sm.textContent = (m.mine ? 'You' : m.name) + ' · ' + m.when; left.appendChild(sm);
      row.appendChild(left);
      if (m.can_pin) row.appendChild(pinForm(m.id, true));
      pinList.appendChild(row);
    });
    pinsBox.hidden = !pins.length;
  }
  function removeForm(id) {
    var f = document.createElement('form');
    f.method = 'post'; f.action = removeUrl.replace(/\/0\/remove$/, '/' + id + '/remove');
    var h = document.createElement('input'); h.type = 'hidden'; h.name = 'csrf_token'; h.value = token; f.appendChild(h);
    var b = document.createElement('button'); b.className = 'rm'; b.textContent = 'Remove'; f.appendChild(b);
    f.addEventListener('submit', function (e) { if (!window.confirm('Remove this message?')) e.preventDefault(); });
    return f;
  }
  function avatarEl(id, name, url, initials, color, size) {
    var a;
    if (url) { a = document.createElement('img'); a.src = url; a.alt = ''; a.width = size; a.height = size; a.loading = 'lazy'; }
    else { a = document.createElement('span'); a.textContent = initials || '?'; a.className = 'avatar-initials'; a.style.background = color; a.style.fontSize = Math.round(size * 0.4) + 'px'; a.setAttribute('aria-hidden', 'true'); }
    a.className = 'avatar' + (url ? '' : ' avatar-initials');
    a.style.width = size + 'px'; a.style.height = size + 'px';
    return a;
  }
  function add(m) {
    if (chat.querySelector('.msg[data-id="' + m.id + '"]')) return;
    var empty = document.getElementById('chat-empty'); if (empty) empty.remove();
    if (m.day !== lastDay()) {
      var d = document.createElement('div'); d.className = 'chat-day'; d.setAttribute('data-day', m.day); d.textContent = fmtDay(m.day);
      chat.appendChild(d);
    }
    var el = document.createElement('div');
    el.className = 'msg' + (m.mine ? ' mine' : '') + (m.removed ? ' removed' : '') + (m.mentions_me ? ' mentioned' : '');
    el.setAttribute('data-id', m.id);
    var who = document.createElement('div'); who.className = 'who';
    var n = document.createElement('strong'); n.textContent = m.mine ? 'You' : m.name; who.appendChild(n);
    if (m.role && !m.mine) { var r = document.createElement('span'); r.textContent = m.role; who.appendChild(r); }
    var w = document.createElement('span'); w.textContent = m.when; who.appendChild(w);
    if (!m.removed) {
      var rp = document.createElement('a'); rp.className = 'rm'; rp.href = '?reply=' + m.id + '#chat-form';
      rp.setAttribute('data-reply', m.id); rp.setAttribute('data-reply-name', m.mine ? 'You' : m.name); rp.textContent = 'Reply';
      who.appendChild(rp);
    }
    if (m.can_pin) who.appendChild(pinForm(m.id, m.pinned));
    if (m.can_remove) who.appendChild(removeForm(m.id));
    var t = document.createElement('div'); t.className = 'text';
    if (m.removed) t.textContent = 'Message removed';
    else (m.parts || [{ t: m.body }]).forEach(function (p) {
      if (p.m) { var sp = document.createElement('span'); sp.className = 'mention' + (p.me ? ' me' : ''); sp.textContent = p.t; t.appendChild(sp); }
      else t.appendChild(document.createTextNode(p.t));
    });
    el.id = 'm' + m.id;
    el.appendChild(who);
    if (m.reply && !m.removed) {
      var q = document.createElement(m.reply.id ? 'a' : 'span');
      q.className = 'reply-quote' + (m.reply.removed ? ' gone' : '');
      if (m.reply.id) { q.href = '#m' + m.reply.id; q.setAttribute('data-jump', m.reply.id); }
      var qn = document.createElement('strong'); qn.textContent = m.reply.name ? (m.reply.mine ? 'You' : m.reply.name) : 'Reply';
      q.appendChild(qn); q.appendChild(document.createTextNode(m.reply.text)); el.appendChild(q);
    }
    el.appendChild(t);
    var row = document.createElement('div'); row.className = 'msg-row' + (m.mine ? ' mine' : '');
    if (!m.mine) row.appendChild(avatarEl(m.uid, m.name, m.avatar, m.initials, m.color, 30));
    row.appendChild(el); chat.appendChild(row);
    if (m.pinned) setPinned(el, true);
    if (!first) first = m.id;
  }
  function poll() {
    if (busy || document.hidden) return;
    busy = true;
    var url = chat.getAttribute('data-since-url') + '?after=' + after + '&first=' + first;
    fetch(url, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        var stick = nearBottom();
        data.messages.forEach(function (m) { add(m); if (m.id > after) after = m.id; });
        data.removed.forEach(function (id) { var el = chat.querySelector('.msg[data-id="' + id + '"]'); if (el && !el.classList.contains('removed')) markRemoved(el); });
        if (data.pinned_ids) chat.querySelectorAll('.msg').forEach(function (el) {
          var on = data.pinned_ids.indexOf(parseInt(el.getAttribute('data-id'), 10)) !== -1;
          if (on !== el.classList.contains('is-pinned')) setPinned(el, on);
        });
        if (data.pins) renderPins(data.pins);
        if (data.messages.length && stick) toBottom();
      })
      .catch(function () {})
      .then(function () { busy = false; });
  }
  if (form) {
    form.addEventListener('submit', function (e) {
      if (e.target !== form) return;
      e.preventDefault();
      var text = box.value.trim(); if (!text) return;
      var fd = new FormData(form);
      err.textContent = '';
      form.querySelector('button.btn').disabled = true;
      if (ePanel) { ePanel.classList.remove('open'); eBtn.setAttribute('aria-expanded', 'false'); }
      fetch(form.action, { method: 'POST', body: fd, headers: { 'Accept': 'application/json', 'X-CSRF-Token': token }, credentials: 'same-origin' })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          if (!res.ok) { err.textContent = res.j.error || 'Not sent. Try again.'; return; }
          box.value = ''; clearReply(); if (typeof caret !== 'undefined') caret = [0, 0]; busy = false; poll(); setTimeout(toBottom, 300);
        })
        .catch(function () { err.textContent = 'Not sent. Check your connection and try again.'; })
        .then(function () { form.querySelector('button.btn').disabled = false; box.focus(); });
    });
    box.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey && !(mBox && !mBox.hidden) && window.matchMedia('(min-width: 800px)').matches) { e.preventDefault(); form.requestSubmit(); }
    });
  }
  /* pin / unpin without reloading */
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (!/\/pin$/.test(f.getAttribute('action') || '')) return;
    e.preventDefault();
    fetch(f.action, { method: 'POST', body: new FormData(f), headers: { 'Accept': 'application/json', 'X-CSRF-Token': token }, credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (res) {
        if (!res) return;
        var id = f.action.match(/\/(\d+)\/pin$/)[1];
        chat.querySelectorAll('.msg').forEach(function (el) {
          var on = res.pins.some(function (p) { return String(p.id) === el.getAttribute('data-id'); });
          if (on !== el.classList.contains('is-pinned')) setPinned(el, on);
        });
        renderPins(res.pins);
        if (res.pinned) window.scrollTo({ top: 0, behavior: 'smooth' });
      });
  });
  /* replies */
  var replyBar = document.getElementById('reply-bar'), replyTo = document.getElementById('reply-to');
  function clearReply() { if (replyBar) { replyBar.hidden = true; replyTo.value = ''; } }
  function flash(el) { el.scrollIntoView({ block: 'center', behavior: 'smooth' }); el.classList.add('flash-hl'); setTimeout(function () { el.classList.remove('flash-hl'); }, 1600); }
  chat.addEventListener('click', function (e) {
    var r = e.target.closest('a[data-reply]');
    if (r && replyBar) {
      e.preventDefault();
      var msg = r.closest('.msg'), txt = (msg.querySelector('.text').textContent || '').replace(/\s+/g, ' ').trim();
      replyTo.value = r.getAttribute('data-reply');
      document.getElementById('reply-name').textContent = r.getAttribute('data-reply-name');
      document.getElementById('reply-text').textContent = txt.length > 90 ? txt.slice(0, 89) + '…' : txt;
      replyBar.hidden = false; box.focus();
      return;
    }
    var j = e.target.closest('[data-jump]');
    if (j) {
      e.preventDefault();
      var target = document.getElementById('m' + j.getAttribute('data-jump'));
      if (target) flash(target);
    }
  });
  var cancel = document.getElementById('reply-cancel');
  if (cancel) cancel.addEventListener('click', function (e) { e.preventDefault(); clearReply(); box.focus(); });
  /* jump to a pinned message: briefly highlight it */
  if (pinList) pinList.addEventListener('click', function (e) {
    var a = e.target.closest('a'); if (!a) return;
    var el = document.getElementById(a.getAttribute('href').slice(1));
    if (!el) { e.preventDefault(); return; }
    el.classList.add('flash-hl'); setTimeout(function () { el.classList.remove('flash-hl'); }, 1600);
  });
  /* emoticons */
  if (eBtn && ePanel && box) {
    eBtn.addEventListener('click', function () {
      var open = ePanel.classList.toggle('open'); eBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    ePanel.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-emoji]'); if (!b) return;
      var em = b.getAttribute('data-emoji');
      var s0 = Math.min(caret[0], box.value.length), s1 = Math.min(caret[1], box.value.length);
      box.value = box.value.slice(0, s0) + em + box.value.slice(s1);
      var pos = s0 + em.length; caret = [pos, pos]; box.setSelectionRange(pos, pos);
    });
    /* remember where the cursor was, since tapping an emoticon takes focus away from the message box */
    var caret = [box.value.length, box.value.length];
    ['input', 'keyup', 'click', 'select', 'focus'].forEach(function (ev) {
      box.addEventListener(ev, function () { caret = [box.selectionStart, box.selectionEnd]; });
    });
    box.addEventListener('blur', function () { caret = [box.selectionStart, box.selectionEnd]; });
  }
  /* @mentions: suggest names while typing "@..." */
  var mBox = document.getElementById('mention-box');
  if (mBox && box) {
    var folks = [];
    try { folks = JSON.parse(mBox.getAttribute('data-people') || '[]'); } catch (err) { folks = []; }
    var mStart = -1, mItems = [], mActive = 0;
    function hideM() { mBox.hidden = true; mStart = -1; mItems = []; }
    function pick(p) {
      var pos = box.selectionStart, before = box.value.slice(0, mStart), after = box.value.slice(pos);
      var ins = '@' + p.name + ' ';
      box.value = before + ins + after.replace(/^\s+/, '');
      var c = before.length + ins.length; box.setSelectionRange(c, c);
      if (typeof caret !== 'undefined') caret = [c, c];
      hideM(); box.focus();
    }
    function showM(list) {
      mBox.textContent = ''; mItems = list; mActive = 0;
      list.forEach(function (p, i) {
        var b = document.createElement('button'); b.type = 'button'; b.setAttribute('role', 'option');
        if (i === 0) b.className = 'active';
        b.appendChild(avatarEl(p.id, p.name, p.avatar, p.initials, p.color, 26));
        var n = document.createElement('span'); n.textContent = p.name; b.appendChild(n);
        b.addEventListener('mousedown', function (e) { e.preventDefault(); pick(p); });
        mBox.appendChild(b);
      });
      mBox.hidden = !list.length;
    }
    function check() {
      var pos = box.selectionStart, upto = box.value.slice(0, pos);
      var m = upto.match(/(^|\s)@([^@\n]{0,30})$/);
      if (!m) { hideM(); return; }
      var q = m[2].toLowerCase();
      var list = folks.filter(function (p) {
        var n = p.name.toLowerCase();
        return !q || n.indexOf(q) === 0 || n.split(/\s+/).some(function (w) { return w.indexOf(q) === 0; }) || (q.length > 2 && n.indexOf(q) !== -1);
      }).slice(0, 6);
      if (!list.length && /\s/.test(q)) { hideM(); return; }
      mStart = pos - m[2].length - 1;
      showM(list);
    }
    box.addEventListener('input', check);
    box.addEventListener('click', check);
    box.addEventListener('blur', function () { setTimeout(hideM, 150); });
    box.addEventListener('keydown', function (e) {
      if (mBox.hidden || !mItems.length) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        mActive = (mActive + (e.key === 'ArrowDown' ? 1 : mItems.length - 1)) % mItems.length;
        Array.prototype.forEach.call(mBox.children, function (b, i) { b.className = i === mActive ? 'active' : ''; });
      } else if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault(); e.stopImmediatePropagation(); pick(mItems[mActive]);
      } else if (e.key === 'Escape') { hideM(); }
    });
  }
  toBottom();
  setInterval(poll, 6000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); });
})();

/* Account menu: close when clicking elsewhere or pressing Escape. */
(function () {
  var m = document.getElementById('me-menu');
  if (!m) return;
  document.addEventListener('click', function (e) { if (m.open && !m.contains(e.target)) m.open = false; });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && m.open) { m.open = false; m.querySelector('summary').focus(); } });
})();


/* New outside work: several cases in one go (+ Add another case / Remove). */
(function () {
  var wrap = document.getElementById('case-blocks');
  var add = document.getElementById('add-case');
  if (!wrap || !add) return;
  function renumber() {
    var blocks = wrap.querySelectorAll('.case-block');
    blocks.forEach(function (b, i) {
      var t = b.querySelector('.case-n'); if (t) t.textContent = (wrap.getAttribute('data-label') || 'Case') + ' ' + (i + 1);
      var r = b.querySelector('.case-remove'); if (r) r.hidden = blocks.length < 2;
      b.querySelectorAll('[data-id]').forEach(function (el) { el.id = el.getAttribute('data-id') + i; });
      b.querySelectorAll('label[data-for]').forEach(function (l) { l.htmlFor = l.getAttribute('data-for') + i; });
      b.querySelectorAll('input[name="x_case"]').forEach(function (h) { h.value = i; });   // which case each charge belongs to
    });
  }
  add.addEventListener('click', function () {
    var blocks = wrap.querySelectorAll('.case-block');
    var last = blocks[blocks.length - 1];
    var b = last.cloneNode(true);
    b.querySelectorAll('input, textarea').forEach(function (el) { el.value = el.name === 'units' ? '1' : ''; });
    b.querySelectorAll('select').forEach(function (el) { if (el.name !== 'case_type') el.selectedIndex = 0; });
    b.querySelectorAll('.field-error').forEach(function (el) { el.remove(); });
    b.querySelectorAll('.field.error').forEach(function (el) { el.classList.remove('error'); });
    b.querySelectorAll('.extra-row').forEach(function (el) { el.remove(); });
    b.querySelectorAll('.mat-new').forEach(function (el) { el.hidden = true; el.value = ''; });
    b.querySelectorAll('select[name="material"]').forEach(function (el) { el.selectedIndex = 0; });

    wrap.appendChild(b); renumber();
    var f = b.querySelector('select[name="case_type"]'); if (f) f.focus();
  });
  var tpl = document.getElementById('extra-row-tpl');
  document.addEventListener('click', function (e) {
    var a = e.target.closest('.add-extra');
    if (a && tpl) {
      var rows = a.closest('.extras').querySelector('.extra-rows');
      rows.appendChild(tpl.content.cloneNode(true));
      var last = rows.lastElementChild; var inp = last && last.querySelector('[name="x_desc"]'); if (inp) inp.focus();
      return;
    }
    var x = e.target.closest('.extra-remove');
    if (x) { x.closest('.extra-row').remove(); }
  });
  wrap.addEventListener('click', function (e) {
    var r = e.target.closest('.case-remove'); if (!r) return;
    if (wrap.querySelectorAll('.case-block').length < 2) return;
    r.closest('.case-block').remove(); renumber();
  });
  renumber();
})();



/* Material: “+ New material…” shows a box to type it. */
document.addEventListener('change', function (e) {
  var sel = e.target;
  if (!sel.matches || !sel.matches('select[name="material"]')) return;
  var box = sel.parentNode.querySelector('.mat-new');
  if (!box) return;
  box.hidden = sel.value !== '__new__';
  if (!box.hidden) box.focus(); else box.value = '';
});

/* Patient search: suggest names while typing (sent by POST, so names stay out of web addresses) */
(function () {
  var input = document.querySelector('input[data-suggest]');
  if (!input) return;
  var box = document.getElementById(input.getAttribute('aria-controls'));
  var form = input.form;
  var token = form && form.querySelector('[name=csrf_token]') ? form.querySelector('[name=csrf_token]').value : '';
  var timer = null, seq = 0, links = [], active = -1;
  function hide() { box.hidden = true; input.setAttribute('aria-expanded', 'false'); active = -1; }
  function mark(i) {
    links.forEach(function (a, j) { a.className = j === i ? 'active' : ''; a.setAttribute('aria-selected', j === i ? 'true' : 'false'); });
    active = i;
  }
  function show(results, q) {
    box.textContent = ''; links = []; active = -1;
    if (!results.length) {
      var d = document.createElement('div'); d.className = 'none'; d.textContent = 'No patient found for “' + q + '”. Try fewer letters or another part of the name.';
      box.appendChild(d);
    }
    results.forEach(function (r) {
      var a = document.createElement('a'); a.href = r.url; a.setAttribute('role', 'option');
      var n = document.createElement('span'); n.textContent = r.name; a.appendChild(n);
      var m = document.createElement('small'); m.textContent = [r.chart_no, r.branch].filter(Boolean).join(' · '); a.appendChild(m);
      box.appendChild(a); links.push(a);
    });
    box.hidden = false; input.setAttribute('aria-expanded', 'true');
  }
  function ask() {
    var q = input.value.trim();
    if (q.length < 2) { hide(); return; }
    var mine = ++seq, fd = new FormData(); fd.append('q', q);
    fetch(input.getAttribute('data-suggest'), { method: 'POST', body: fd, credentials: 'same-origin',
      headers: { 'Accept': 'application/json', 'X-CSRF-Token': token } })
      .then(function (r) { return r.ok ? r.json() : { results: [] }; })
      .then(function (d) { if (mine === seq && document.activeElement === input) show(d.results || [], q); })
      .catch(function () {});
  }
  input.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(ask, 200); });
  input.addEventListener('focus', function () { if (input.value.trim().length >= 2) ask(); });
  input.addEventListener('keydown', function (e) {
    if (box.hidden) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); if (links.length) mark((active + 1) % links.length); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); if (links.length) mark((active - 1 + links.length) % links.length); }
    else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); window.location = links[active].href; }
    else if (e.key === 'Escape') { hide(); }
  });
  input.addEventListener('blur', function () { setTimeout(hide, 150); });
})();
