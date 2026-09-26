/* Dental Haven website chat: a built-in assistant that answers from the site's own content.
   No outside service, no tracking. The conversation is not stored or sent anywhere; only the
   "send to our team" form is saved, as an inquiry (like the inquiry form). */
(function () {
  "use strict";
  var root = document.getElementById("dh-chat");
  if (!root) return;
  var launch = root.querySelector(".dh-chat-launch"), panel = root.querySelector(".dh-chat-panel");
  var log = root.querySelector(".dh-chat-log"), chips = root.querySelector(".dh-chat-chips");
  var form = root.querySelector(".dh-chat-input"), input = root.querySelector("#dh-chat-text");
  var info = null, lastQuestion = "", started = false, lang = null, ctxBranch = null, ctxService = null;
  try { lang = localStorage.getItem("dh-chat-lang"); } catch (e) { lang = null; }
  if (lang !== "en" && lang !== "tl") lang = null;

  var T = {
    en: {
      hi: "Hi! 👋 Welcome to Dental Haven, where we make you the happiest your teeth will ever be.",
      help: "Aesthetic dentistry is our specialty: smile makeovers, veneers, crowns and implants, plus complete care for the whole family. How can I help you today?",
      c_book: "Book a visit", c_services: "Our services", c_branches: "Branches & hours", c_prices: "Prices", c_team: "Have our team call me",
      c_why: "Why Dental Haven?", c_book_here: function (n) { return "Book at " + n; }, c_book_this: "Book this treatment",
      why_t: "Why patients choose Dental Haven:",
      why: ["Aesthetic dentistry is our specialty: natural-looking smile makeovers, veneers, crowns and implants",
            "Our own Digital Solutions Dental Laboratory crafts your crowns, bridges and dentures, for a precise fit and a faster turnaround",
            "3D CBCT and panoramic X-rays in-house, so your dentist sees the full picture",
            "Gentle care for kids and patients with special needs",
            "4 branches: Malolos, Guiguinto, Bocaue and San Jose del Monte"],
      why_end: "The best first step is a consultation: your dentist checks your teeth and walks you through your options. Shall I help you book one?",
      prefilled: function (what) { return "I've already filled in " + what + " for you. Just choose a date and time."; },
      at: " at ", svc_pitch: "Our dentists plan every treatment around you and your goals, and our own lab crafts restorations for a natural-looking fit.",
      svc_special: "✨ This is our specialty.",
      br_pitch: function (n) { return "Want me to set up your visit at our " + n + " branch?"; },
      price3: "Your consultation is where you get a clear treatment plan and the exact cost, so there are no surprises.",
      done_more: "While you wait, you can also pick a time yourself:",
      unsure_nudge: "",
      c_consult: "Book a consultation", c_send: "Send my question", c_call: "Call a branch", c_never: "Never mind",
      book1: "Great choice! 😊 Taking you to our booking page now. Just pick a date and time, and our team will call or message you to confirm.",
      go_now: "If the page doesn't open, tap here:",
      all_branches: "🕘 All our branches:", hours_book: "Book ahead so we can reserve your time with the dentist.",
      read: "📖 Read: ", guide_intro: "We have a short guide on that:", guide_end: "Have more questions? Your dentist will explain everything at your consultation.",
      book_cta: "Book your visit →", consult_cta: "Book a consultation →", learn: "Learn more about ",
      svc_menu: "Here's what we offer. Tap one to learn more:", svc_yes: "Yes, we can help with that.",
      br_menu: function (n) { return "We have " + n + " branches. Which one would you like?"; },
      no_hours: "Please call the branch for hours.", map: "📍 Map",
      contacts: "You can call or text any of our branches:", see_fb: "see our Facebook page",
      price1: "Every smile is different, so our dentist confirms the exact cost after checking your teeth. It depends on the treatment and materials that suit you.",
      price2: "Would you like to book a consultation, or send your question to a branch?",
      pain1: "I'm sorry you're in pain. I can't give medical advice here, so please call your nearest branch so a dentist can advise you and fit you in.",
      pain2: "If you have severe swelling of the face or neck, trouble breathing or swallowing, a high fever, or bleeding that won't stop, go to the nearest hospital emergency room right away.",
      pay: "For payment options such as HMO, cards, e-wallets or installment plans, the branch will give you the details.",
      lab1: "Our in-house Digital Solutions Dental Laboratory crafts crowns, bridges, dentures and 3D-printed appliances for our patients, for a precise fit and a faster turnaround.",
      lab2: "We also have intraoral scanners and CBCT & panoramic X-rays.",
      unsure: "I'm not sure I can answer that one, but our team can. Want me to pass your question to a branch?",
      hello: "Hello! How can I help you today?", thanks: "You're welcome! 😊 We hope to see you soon.",
      nevermind: "No problem! Anything else I can help with?",
      f_title: "Send a message to our team", f_name: "Your name", f_phone: "Mobile number", f_email: "or email", f_branch: "Branch",
      f_any: "Any branch", f_q: "Your question", f_priv1: "I agree to the ", f_priv2: "privacy notice", f_priv3: " so Dental Haven can reply.",
      f_contact: "You may also send me reminders and updates.", f_send: "Send", f_sending: "Sending…",
      f_done: "Thank you! ✅ Your message was sent. Our team will reply by phone, text or email during clinic hours.",
      f_check: "Please check the form.", f_fail: "Something went wrong. Please try again or call the branch.",
      f_offline: "No connection. Please try again or call the branch.",
      load_fail: "Sorry, the chat couldn't load. Please call any branch or use the inquiry form.",
      placeholder: "Type your question…", svc_note: "",
      switched: "Okay, I'll reply in English."
    },
    tl: {
      hi: "Hello po! 👋 Welcome sa Dental Haven, kung saan ang inyong ngipin ay magiging pinakamasaya.",
      help: "Aesthetic dentistry po ang aming specialty: smile makeover, veneers, crowns at implants, kasama ang kumpletong dental care para sa buong pamilya. Paano ko po kayo matutulungan?",
      c_book: "Mag-book", c_services: "Mga serbisyo", c_branches: "Branches at oras", c_prices: "Presyo", c_team: "Patawagan ako sa staff",
      c_why: "Bakit Dental Haven?", c_book_here: function (n) { return "Mag-book sa " + n; }, c_book_this: "I-book ang treatment na ito",
      why_t: "Bakit pinipili ng mga pasyente ang Dental Haven:",
      why: ["Aesthetic dentistry ang aming specialty: natural-looking na smile makeover, veneers, crowns at implants",
            "Sariling Digital Solutions Dental Laboratory ang gumagawa ng inyong crowns, bridges at pustiso, para sa eksaktong sukat at mas mabilis na paggawa",
            "May 3D CBCT at panoramic X-ray sa clinic, para kita ng dentista ang buong larawan",
            "Maingat at magiliw na pag-aalaga sa mga bata at pasyenteng may special needs",
            "4 na branches: Malolos, Guiguinto, Bocaue at San Jose del Monte"],
      why_end: "Ang pinakamagandang unang hakbang ay konsulta: titingnan ng dentista ang inyong ngipin at ipapaliwanag ang mga opsyon. Tutulungan ko po ba kayong mag-book?",
      prefilled: function (what) { return "Nailagay ko na po ang " + what + " para sa inyo. Pumili na lang ng petsa at oras."; },
      at: " sa ", svc_pitch: "Pinaplano ng aming mga dentista ang bawat treatment ayon sa inyong pangangailangan, at ang sarili naming lab ang gumagawa ng restorations para natural ang itsura.",
      svc_special: "✨ Ito po ang aming specialty.",
      br_pitch: function (n) { return "Gusto n'yo po bang i-set ang inyong visit sa aming " + n + " branch?"; },
      price3: "Sa konsulta po ninyo malalaman ang malinaw na treatment plan at eksaktong halaga, kaya walang sorpresa.",
      done_more: "Habang naghihintay, puwede na rin kayong pumili ng oras:",
      unsure_nudge: "",
      c_consult: "Mag-book ng konsulta", c_send: "Ipadala ang tanong ko", c_call: "Tawagan ang branch", c_never: "Huwag na lang",
      book1: "Magandang desisyon po! 😊 Dadalhin ko na po kayo sa booking page. Pumili lang ng petsa at oras, at tatawagan o ite-text kayo ng aming team para kumpirmahin.",
      go_now: "Kung hindi bumukas ang page, i-tap dito:",
      all_branches: "🕘 Lahat po ng aming branch:", hours_book: "Mag-book po nang maaga para ma-reserve ang oras ninyo sa dentista.",
      read: "📖 Basahin: ", guide_intro: "May maikling guide po kami tungkol diyan (nasa English):", guide_end: "May iba pa po kayong tanong? Ipapaliwanag ng dentista ang lahat sa inyong konsulta.",
      book_cta: "Mag-book na →", consult_cta: "Mag-book ng konsulta →", learn: "Alamin pa ang tungkol sa ",
      svc_menu: "Ito po ang aming mga serbisyo. Pumili para sa detalye:", svc_yes: "Opo, matutulungan namin kayo diyan.",
      br_menu: function (n) { return "Mayroon po kaming " + n + " branches. Alin po ang gusto ninyo?"; },
      no_hours: "Pakitawagan po ang branch para sa oras.", map: "📍 Mapa",
      contacts: "Puwede po kayong tumawag o mag-text sa alinmang branch:", see_fb: "tingnan ang aming Facebook page",
      price1: "Iba-iba po ang bawat ngiti, kaya ang dentista ang magkukumpirma ng eksaktong halaga pagkatapos ma-check ang inyong ngipin. Depende ito sa treatment at materyales na bagay sa inyo.",
      price2: "Gusto n'yo po bang mag-book ng konsulta, o ipadala ang tanong ninyo sa isang branch?",
      pain1: "Pasensya na po at masakit ang inyong ngipin. Hindi po ako makapagbibigay ng medical advice dito, kaya pakitawagan ang pinakamalapit na branch para ma-assist kayo ng dentista at maisingit sa schedule.",
      pain2: "Kung may matinding pamamaga sa mukha o leeg, hirap sa paghinga o paglunok, mataas na lagnat, o pagdurugong hindi tumitigil, pumunta agad sa emergency room ng pinakamalapit na ospital.",
      pay: "Para sa mga paraan ng pagbabayad gaya ng HMO, card, e-wallet o hulugan, ang branch po ang magbibigay ng detalye.",
      lab1: "Ang aming sariling Digital Solutions Dental Laboratory ang gumagawa ng crowns, bridges, pustiso at 3D-printed appliances para sa aming mga pasyente, para sa mas eksaktong sukat at mas mabilis na paggawa.",
      lab2: "Mayroon din kaming intraoral scanners at CBCT at panoramic X-ray.",
      unsure: "Hindi po ako sigurado sa sagot diyan, pero matutulungan kayo ng aming team. Ipapasa ko po ba ang tanong ninyo sa isang branch?",
      hello: "Hello po! Paano ko kayo matutulungan ngayon?", thanks: "Walang anuman po! 😊 Sana makita namin kayo sa clinic.",
      nevermind: "Sige po! May iba pa po ba akong maitutulong?",
      f_title: "Magpadala ng mensahe sa aming team", f_name: "Pangalan", f_phone: "Mobile number", f_email: "o email", f_branch: "Branch",
      f_any: "Kahit anong branch", f_q: "Tanong ninyo", f_priv1: "Sumasang-ayon ako sa ", f_priv2: "privacy notice", f_priv3: " para makasagot ang Dental Haven.",
      f_contact: "Puwede rin akong padalhan ng reminders at updates.", f_send: "Ipadala", f_sending: "Ipinapadala…",
      f_done: "Salamat po! ✅ Naipadala na ang inyong mensahe. Sasagot ang aming team sa tawag, text o email sa oras ng clinic.",
      f_check: "Pakisuri po ang form.", f_fail: "May nangyaring mali. Pakisubukang muli o tawagan ang branch.",
      f_offline: "Walang koneksyon. Pakisubukang muli o tawagan ang branch.",
      load_fail: "Pasensya na po, hindi ma-load ang chat. Pakitawagan ang alinmang branch o gamitin ang inquiry form.",
      placeholder: "I-type ang inyong tanong…", svc_note: "(Nasa English ang paglalarawan ng serbisyo.)",
      switched: "Sige po, sa Tagalog na ako sasagot."
    }
  };
  function t(k) { return T[lang || "en"][k]; }

  // ------------------------------------------------------------ helpers
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function link(href, text, ext) { var a = el("a", null, text); a.href = href; if (ext) { a.target = "_blank"; a.rel = "noopener"; } return a; }
  function scroll() { log.scrollTop = log.scrollHeight; }
  function say(parts, who) {
    var b = el("div", "dh-msg " + (who || "bot"));
    (Array.isArray(parts) ? parts : [parts]).forEach(function (p) {
      if (p == null) return;
      if (typeof p === "string") b.appendChild(el("p", null, p)); else b.appendChild(p);
    });
    log.appendChild(b); scroll(); return b;
  }
  function typing(then) {
    var t = el("div", "dh-msg bot dh-typing"); t.innerHTML = "<span></span><span></span><span></span>";
    log.appendChild(t); scroll();
    setTimeout(function () { t.remove(); then(); }, 450);
  }
  function setChips(list) {
    chips.innerHTML = "";
    list.forEach(function (c) {
      var b = el("button", "dh-chip", c[0]); b.type = "button";
      b.addEventListener("click", function () { say(c[0], "me"); typing(c[1]); });
      chips.appendChild(b);
    });
    scroll();
  }
  var MAIN = function () {
    return [[t("c_book"), book], [t("c_why"), why], [t("c_services"), servicesMenu], [t("c_branches"), branchesMenu],
            [t("c_prices"), price], [t("c_team"), handoff]];
  };
  function after(list) { setChips((list || []).concat(MAIN().filter(function (m) { return !(list || []).some(function (l) { return l[0] === m[0]; }); })).slice(0, 6)); }
  function bookUrl() {
    var q = [];
    if (ctxBranch) q.push("branch=" + ctxBranch.id);
    if (ctxService) q.push("service=" + ctxService.id);
    return info.book + (q.length ? "?" + q.join("&") : "");
  }
  function list(items) { var ul = el("ul"); items.forEach(function (i) { var li = el("li"); if (typeof i === "string") li.textContent = i; else li.appendChild(i); ul.appendChild(li); }); return ul; }
  function norm(t) { return (" " + (t || "").toLowerCase().replace(/[^a-z0-9ñ\s-]/g, " ").replace(/\s+/g, " ") + " "); }
  function has(t, words) { return words.some(function (w) { return t.indexOf(w) !== -1; }); }

  function hoursText(h) { return h; }  // day and hour labels stay in English in both languages

  var langBtns = root.querySelectorAll(".dh-lang button");
  function setLang(l, announce) {
    lang = l;
    try { localStorage.setItem("dh-chat-lang", l); } catch (e) { /* private mode: remember for this visit only */ }
    input.placeholder = t("placeholder");
    Array.prototype.forEach.call(langBtns, function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-lang") === l ? "true" : "false"); });
    if (announce) { say(t("switched")); setChips(MAIN()); }
  }
  function chooseLanguage() {
    say(["Which language would you like me to use?", "Anong wika ang gusto ninyong gamitin ko?"]);
    setChips([["English", function () { setLang("en"); greet(); }], ["Tagalog", function () { setLang("tl"); greet(); }]]);
  }
  Array.prototype.forEach.call(langBtns, function (b) {
    b.addEventListener("click", function () {
      var l = b.getAttribute("data-lang");
      if (!info) { setLang(l); return; }
      if (l !== lang) { setLang(l, true); }
    });
  });

  // ------------------------------------------------------------ answers
  function greet() {
    say([t("hi"), t("help")]);
    setChips(MAIN());
  }
  function book() {
    var a = link(bookUrl(), t("book_cta")); a.className = "dh-cta";
    var what = [ctxService && ctxService.name, ctxBranch && ctxBranch.name].filter(Boolean).join(t("at"));
    say([t("book1"), what ? t("prefilled")(what) : null, t("go_now"), a]);
    setChips([]);
    var dest = bookUrl();
    setTimeout(function () { window.location.href = dest; }, 1800);
  }
  function servicesMenu() {
    say(t("svc_menu"));
    setChips(info.services.map(function (s) { return [s.name, function () { service(s.slug); }]; }).slice(0, 6));
  }
  function service(slug, lead) {
    var s = info.services.filter(function (x) { return x.slug === slug; })[0];
    if (!s) return fallback();
    ctxService = s;
    var special = ["aesthetic-dentistry", "prosthodontics", "dental-implants"].indexOf(s.slug) !== -1;
    var more = link(s.url, t("learn") + s.name + " →");
    var bk = link(bookUrl(), t("consult_cta")); bk.className = "dh-cta";
    var reads = (info.guides || []).filter(function (g) { return g.service === s.slug; }).map(function (g) {
      var p = el("p"); p.appendChild(link(g.url, t("read") + g.title)); return p;
    });
    say([lead || null, el("p", "dh-strong", s.name), special ? el("p", "dh-special", t("svc_special")) : null, s.summary || null,
         t("svc_note") || null, t("svc_pitch")].concat(reads).concat([more, bk]));
    after([[t("c_book_this"), book], [t("c_prices"), price], [t("c_team"), handoff]]);
  }
  function branchCard(b) {
    var parts = [el("p", "dh-strong", "Dental Haven " + b.name)];
    if (b.address) parts.push(b.address);
    var row = el("p", "dh-links");
    b.phones.forEach(function (p, i) { row.appendChild(link(b.tel[i], "📞 " + p)); });
    if (b.map) row.appendChild(link(b.map, t("map"), true));
    if (b.facebook) row.appendChild(link(b.facebook, "Facebook", true));
    parts.push(row);
    return parts;
  }
  function branchesMenu() {
    say(t("br_menu")(info.branches.length));
    setChips(info.branches.map(function (b) { return [b.name, function () { branch(b); }]; }));
  }
  function branch(b) {
    ctxBranch = b;
    say(branchCard(b).concat([el("p", "dh-strong", t("br_pitch")(b.name))]));
    setChips([[t("c_book_here")(b.name), book], [t("c_team"), handoff], [t("c_services"), servicesMenu], [t("c_branches"), branchesMenu]]);
  }
  function why() {
    say([el("p", "dh-strong", t("why_t")), list(t("why").map(function (x) { return "✔ " + x; })), t("why_end")]);
    setChips([[t("c_consult"), book], [t("c_team"), handoff], [t("c_services"), servicesMenu]]);
  }
  function allHours() {
    var h = info.branches.length ? info.branches[0].hours.map(hoursText).join(" · ") : "";
    say(h ? [t("all_branches") + " " + h + ".", t("hours_book")] : t("no_hours"));
    after([[t("c_book"), book], [t("c_branches"), branchesMenu]]);
  }
  function contacts() {
    var items = info.branches.map(function (b) {
      var li = el("span"); li.append(b.name + ": ");
      b.phones.forEach(function (p, i) { if (i) li.append(" / "); li.appendChild(link(b.tel[i], p)); });
      if (!b.phones.length) li.append(t("see_fb"));
      return li;
    });
    say([t("contacts"), list(items)]); after([[t("c_team"), handoff]]);
  }
  function price() {
    say([t("price1"), t("price3"), t("price2")]);
    setChips([[t("c_consult"), book], [t("c_team"), handoff], [t("c_why"), why]]);
  }
  function guide(slug) {
    var g = (info.guides || []).filter(function (x) { return x.slug === slug; })[0];
    if (!g) return fallback();
    if (g.service) ctxService = info.services.filter(function (x) { return x.slug === g.service; })[0] || ctxService;
    var a = link(g.url, t("read") + g.title); a.className = "dh-strong";
    var bk = link(bookUrl(), t("consult_cta")); bk.className = "dh-cta";
    say([t("guide_intro"), a, t("guide_end"), bk]);
    after([[t("c_consult"), book], [t("c_team"), handoff]]);
  }
  function pain() {
    say([t("pain1"), el("p", "dh-warn", t("pain2"))]);
    after([[t("c_call"), contacts], [t("c_book"), book]]);
  }
  function payment() {
    say(t("pay"));
    setChips([[t("c_send"), handoff], [t("c_call"), contacts]]);
  }
  function lab() {
    say([t("lab1"), t("lab2")]);
    after([[t("c_services"), servicesMenu], [t("c_book"), book]]);
  }
  function fallback() {
    say(t("unsure"));
    setChips([[t("c_team"), handoff], [t("c_book"), book], [t("c_why"), why], [t("c_services"), servicesMenu]]);
  }

  // ------------------------------------------------------------ hand-off form (saved as an inquiry)
  function handoff() {
    var f = el("form", "dh-form"); f.noValidate = true;
    var q = lastQuestion && lastQuestion.length > 2 ? lastQuestion : "";
    f.innerHTML =
      '<p class="dh-strong" data-t="f_title"></p>' +
      '<label><span data-t="f_name"></span><input name="full_name" maxlength="120" required autocomplete="name"></label>' +
      '<label><span data-t="f_phone"></span><input name="phone" maxlength="25" inputmode="tel" autocomplete="tel" placeholder="09XX XXX XXXX"></label>' +
      '<label><span data-t="f_email"></span><input name="email" type="email" maxlength="200" autocomplete="email"></label>' +
      '<label><span data-t="f_branch"></span><select name="branch_id"><option value="" data-t="f_any"></option></select></label>' +
      '<label><span data-t="f_q"></span><textarea name="message" rows="3" maxlength="1500" required></textarea></label>' +
      '<label class="dh-check"><input type="checkbox" name="consent_privacy" value="1"> <span><span data-t="f_priv1"></span><a target="_blank" rel="noopener" data-t="f_priv2"></a><span data-t="f_priv3"></span></span></label>' +
      '<label class="dh-check"><input type="checkbox" name="consent_contact" value="1"> <span data-t="f_contact"></span></label>' +
      '<input name="website" tabindex="-1" autocomplete="off" class="dh-hp" aria-hidden="true">' +
      '<p class="dh-err" role="alert"></p><button type="submit" class="dh-cta" data-t="f_send"></button>';
    Array.prototype.forEach.call(f.querySelectorAll("[data-t]"), function (n) { n.textContent = t(n.getAttribute("data-t")); });
    f.querySelector("a").href = info.privacy;
    f.message.value = q;
    var sel = f.branch_id;
    info.branches.forEach(function (b) { var o = el("option", null, b.name); o.value = b.id; if (ctxBranch && ctxBranch.id === b.id) o.selected = true; sel.appendChild(o); });
    f.addEventListener("submit", function (e) {
      e.preventDefault();
      var btn = f.querySelector("button"), err = f.querySelector(".dh-err");
      err.textContent = ""; btn.disabled = true; btn.textContent = t("f_sending");
      var body = new URLSearchParams(new FormData(f));
      fetch(root.dataset.send, { method: "POST", body: body, credentials: "same-origin",
                                 headers: { "X-CSRF-Token": root.dataset.csrf } })
        .then(function (r) { return r.json().catch(function () { return { ok: false, errors: { _form: t("f_fail") } }; }); })
        .then(function (d) {
          if (d.ok) {
            (f.closest(".dh-msg") || f).remove();
            var a = link(bookUrl(), t("book_cta")); a.className = "dh-cta";
            say([t("f_done"), t("done_more"), a]);
            after([[t("c_why"), why]]);
          } else {
            var msgs = []; for (var k in (d.errors || {})) msgs.push(d.errors[k]);
            err.textContent = msgs.join(" ") || t("f_check");
            btn.disabled = false; btn.textContent = t("f_send");
          }
        })
        .catch(function () { err.textContent = t("f_offline"); btn.disabled = false; btn.textContent = t("f_send"); });
    });
    var b = say([f]); b.classList.add("dh-msg-form");
    setChips([[t("c_never"), function () { (f.closest(".dh-msg") || f).remove(); say(t("nevermind")); setChips(MAIN()); }]]);
  }

  // ------------------------------------------------------------ understanding free text (English + Tagalog)
  var SERVICE_WORDS = [
    ["aesthetic-dentistry", ["veneer", "whiten", "bleach", "makeover", "cosmetic", "aesthetic", "smile design", "composite", "bonding", "pasta", "filling", "restor"]],
    ["prosthodontics", ["denture", "pustiso", "crown", "bridge", "zirconia", "jacket", "flexite", "prostho"]],
    ["dental-implants", ["implant", "extract", "bunot", "wisdom", "surgery", "opera", "impacted"]],
    ["orthodontics", ["brace", "bracket", "aligner", "invisalign", "retainer", "ortho", "tmj", "jaw", "panga", "sungki", "crooked"]],
    ["pediatric-dentistry", ["kid", "child", "bata", "anak", "baby", "pedia", "sedation", "special need", "toddler"]],
    ["general-dentistry", ["clean", "linis", "prophy", "check-up", "checkup", "check up", "root canal", "x-ray", "xray", "gum", "gilagid", "fluoride", "sealant"]]
  ];
  function answer(text) {
    var q = norm(text);
    // remember a treatment they mention (e.g. "how much are veneers?") so the booking form is pre-filled
    for (var k = 0; k < SERVICE_WORDS.length; k++) {
      if (has(q, SERVICE_WORDS[k][1])) { ctxService = info.services.filter(function (x) { return x.slug === SERVICE_WORDS[k][0]; })[0] || ctxService; break; }
    }
    if (has(q, [" masakit", " sakit", "pain", "ache", " hurt", "swell", "namamaga", "maga ", "bleed", "dugo", "emergency", "urgent", "infect", "nana "])) return pain();
    if (has(q, ["magkano", "presyo", "price", "cost", "how much", "rate", "fee", "bayad", "budget", "promo", "discount"])) return price();
    if (has(q, [" hmo", "insurance", "maxicare", "intellicare", "gcash", "maya", "credit card", "card ", "installment", "hulugan", "hulog", "payment", "cash"])) return payment();
    if (has(q, ["human", "staff", "person", "agent", "receptionist", "talk to", "kausap", "message the", "reply", "contact me", "call me", "tawagan"])) return handoff();
    var GUIDE_WORDS = [
      ["veneers-vs-crowns", function () { return has(q, ["veneer"]) && has(q, ["crown", "jacket"]) || has(q, ["difference", "pagkakaiba", " vs "]) && has(q, ["veneer", "crown"]); }],
      ["silver-diamine-fluoride", function () { return has(q, [" sdf", "silver diamine", "diamine", "silver fluoride"]); }],
      ["childs-first-dental-visit", function () { return has(q, ["first visit", "first dental", "first check", "unang", "first time"]) && has(q, ["kid", "child", "bata", "anak", "baby", "son", "daughter", "toddler", "visit"]); }],
      ["preventive-dentistry-for-kids", function () { return has(q, ["sealant", "fluoride", "prevent", "iwas"]); }],
      ["white-spots-and-fluorosis", function () { return has(q, ["white spot", "fluorosis", "chalky", "mantsa", "puting", "spots on"]); }],
      ["about-dental-fillings", function () { return has(q, ["what is a filling", "about filling", "does filling hurt", "masakit ba ang pasta"]); }],
      ["caring-for-dentures", function () { return has(q, ["denture care", "clean my denture", "linisin ang pustiso", "new denture"]); }],
      ["braces-or-clear-aligners", function () { return has(q, ["brace", "aligner"]) && has(q, [" or ", " vs ", "difference", "better", "alin"]); }]
    ];
    for (var gi = 0; gi < GUIDE_WORDS.length; gi++) { if (GUIDE_WORDS[gi][1]()) return guide(GUIDE_WORDS[gi][0]); }
    for (var i = 0; i < info.branches.length; i++) {
      var b = info.branches[i];
      if (q.indexOf(" " + b.name.toLowerCase().split(" ")[0]) !== -1 || (b.slug === "sjdm" && has(q, ["san jose", "sjdm"]))) return branch(b);
    }
    if (has(q, ["why", "bakit", "legit", "trusted", "reliable", "maganda ba", "okay ba", "ok ba", "magaling", "experience", "recommend", "sulit", "worth"])) return why();
    if (has(q, ["hour", "open", "close", "oras", "bukas", "sarado", "sunday", "linggo", "saturday", "sabado", "holiday", "what time", "anong oras"])) return allHours();
    if (has(q, ["book", "appoint", "schedule", "sched", "reserve", "slot", "magpa", "pa-appoint", "available"])) return book();
    if (has(q, ["where", "saan", "location", "address", "direction", "map", "branch", "near", "malapit", "located"])) return branchesMenu();
    if (has(q, ["phone", "number", "contact", "call", "tawag", "text ", "viber", "cellphone", "mobile", "landline"])) return contacts();
    if (has(q, [" lab", "laborator", "cbct", "scanner", "3d", "milling", "digital"])) return lab();
    for (var j = 0; j < SERVICE_WORDS.length; j++) {
      if (has(q, SERVICE_WORDS[j][1])) return service(SERVICE_WORDS[j][0], t("svc_yes"));
    }
    if (has(q, ["service", "offer", "treatment", "procedure", "ginagawa"])) return servicesMenu();
    if (has(q, [" hi ", "hello", " hey", "good morning", "good afternoon", "good evening", "magandang", "kumusta", " po "]) && q.length < 30) {
      say(t("hello")); return setChips(MAIN());
    }
    if (has(q, ["thank", "salamat", "ty "])) { say(t("thanks")); return setChips(MAIN()); }
    return fallback();
  }

  // ------------------------------------------------------------ wiring
  function open() {
    panel.hidden = false; root.classList.add("is-open"); launch.setAttribute("aria-expanded", "true");
    if (!started) {
      started = true;
      fetch(root.dataset.info, { credentials: "same-origin" }).then(function (r) { return r.json(); })
        .then(function (d) { info = d; if (lang) { setLang(lang); greet(); } else { chooseLanguage(); } })
        .catch(function () { say(t("load_fail")); });
    }
    setTimeout(function () { input.focus(); }, 50);
  }
  function close() { panel.hidden = true; root.classList.remove("is-open"); launch.setAttribute("aria-expanded", "false"); launch.focus(); }
  launch.addEventListener("click", function () { panel.hidden ? open() : close(); });
  root.querySelector(".dh-chat-close").addEventListener("click", close);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !panel.hidden) close(); });
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text || !info) return;
    input.value = ""; lastQuestion = text;
    if (!lang) setLang(/\b(po|ba|ano|magkano|saan|paano|ako|kayo|ninyo|gusto|pwede|puwede|sana|salamat)\b/i.test(text) ? "tl" : "en");
    say(text, "me"); typing(function () { answer(text); });
  });
})();
