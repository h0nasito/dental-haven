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
      help: "We're a complete family dental clinic: check-ups and cleanings, fillings, kids' dentistry, braces, veneers and crowns, dentures, and implants. How can I help you today?",
      c_book: "Book a visit", c_services: "Our services", c_branches: "Branches & hours", c_prices: "Prices", c_team: "Have our team call me",
      c_why: "Why Dental Haven?", c_book_here: function (n) { return "Book at " + n; }, c_book_this: "Book this treatment",
      why_t: "Why patients choose Dental Haven:",
      why: ["Complete care in one clinic: check-ups, cleanings and fillings, kids' dentistry, braces, veneers and crowns, dentures, and implants",
            "Our own Digital Solutions Dental Laboratory crafts your crowns, bridges and dentures, for a precise fit and a faster turnaround",
            "3D CBCT and panoramic X-rays in-house, so your dentist sees the full picture",
            "Gentle care for kids and patients with special needs",
            "4 branches: Malolos, Guiguinto, Bocaue and San Jose del Monte"],
      why_end: "The best first step is a consultation: your dentist checks your teeth and walks you through your options. Shall I help you book one?",
      prefilled: function (what) { return "I've already filled in " + what + " for you. Just choose a date and time."; },
      at: " at ", svc_pitch: "Our dentists plan every treatment around you and your goals, and our own lab crafts restorations for a natural-looking fit.",
      br_pitch: function (n) { return "Want me to set up your visit at our " + n + " branch?"; },
      price3: "Your consultation is where you get a clear treatment plan and the exact cost, so there are no surprises.",
      done_more: "While you wait, you can also pick a time yourself:",
      unsure_nudge: "",
      c_consult: "Book a consultation", c_send: "Send my question", c_call: "Call a branch", c_never: "Never mind",
      book1: "Great choice! 😊 Taking you to our booking page now. Just pick a date and time, and our team will call or message you to confirm.",
      go_now: "If the page doesn't open, tap here:",
      all_branches: "🕘 All our branches:", hours_book: "Book ahead so we can reserve your time with the dentist.",
      from: "from ", sample_note: "Sample prices for testing only (demo site). These are not Dental Haven's actual prices yet.",
      price_list: "Here are some of our starting prices:", price_ask: "Ask me about a specific treatment, for example \"How much are braces?\"",
      price_final: "The final cost depends on your teeth and treatment plan. Your dentist confirms it at your consultation, before any work begins.",
      again: "I think I've already answered that. Would you like our team to explain it in more detail?",
      unsure2: "Sorry, I still didn't catch that. You can type a short question like \"How much is cleaning?\", \"Do you do braces?\" or \"Where is your Bocaue branch?\", or I can have our team call you.",
      more_read: "Read the full guide →",
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
      help: "Kumpletong dental clinic po kami para sa buong pamilya: check-up at cleaning, pasta, dentistry para sa bata, braces, veneers at crowns, pustiso, at implants. Paano ko po kayo matutulungan?",
      c_book: "Mag-book", c_services: "Mga serbisyo", c_branches: "Branches at oras", c_prices: "Presyo", c_team: "Patawagan ako sa staff",
      c_why: "Bakit Dental Haven?", c_book_here: function (n) { return "Mag-book sa " + n; }, c_book_this: "I-book ang treatment na ito",
      why_t: "Bakit pinipili ng mga pasyente ang Dental Haven:",
      why: ["Kumpletong serbisyo sa iisang clinic: check-up, cleaning at pasta, dentistry para sa bata, braces, veneers at crowns, pustiso, at implants",
            "Sariling Digital Solutions Dental Laboratory ang gumagawa ng inyong crowns, bridges at pustiso, para sa eksaktong sukat at mas mabilis na paggawa",
            "May 3D CBCT at panoramic X-ray sa clinic, para kita ng dentista ang buong larawan",
            "Maingat at magiliw na pag-aalaga sa mga bata at pasyenteng may special needs",
            "4 na branches: Malolos, Guiguinto, Bocaue at San Jose del Monte"],
      why_end: "Ang pinakamagandang unang hakbang ay konsulta: titingnan ng dentista ang inyong ngipin at ipapaliwanag ang mga opsyon. Tutulungan ko po ba kayong mag-book?",
      prefilled: function (what) { return "Nailagay ko na po ang " + what + " para sa inyo. Pumili na lang ng petsa at oras."; },
      at: " sa ", svc_pitch: "Pinaplano ng aming mga dentista ang bawat treatment ayon sa inyong pangangailangan, at ang sarili naming lab ang gumagawa ng restorations para natural ang itsura.",
      br_pitch: function (n) { return "Gusto n'yo po bang i-set ang inyong visit sa aming " + n + " branch?"; },
      price3: "Sa konsulta po ninyo malalaman ang malinaw na treatment plan at eksaktong halaga, kaya walang sorpresa.",
      done_more: "Habang naghihintay, puwede na rin kayong pumili ng oras:",
      unsure_nudge: "",
      c_consult: "Mag-book ng konsulta", c_send: "Ipadala ang tanong ko", c_call: "Tawagan ang branch", c_never: "Huwag na lang",
      book1: "Magandang desisyon po! 😊 Dadalhin ko na po kayo sa booking page. Pumili lang ng petsa at oras, at tatawagan o ite-text kayo ng aming team para kumpirmahin.",
      go_now: "Kung hindi bumukas ang page, i-tap dito:",
      all_branches: "🕘 Lahat po ng aming branch:", hours_book: "Mag-book po nang maaga para ma-reserve ang oras ninyo sa dentista.",
      from: "mula ", sample_note: "Sample na presyo lang po ito para sa testing (demo site). Hindi pa ito ang aktuwal na presyo ng Dental Haven.",
      price_list: "Narito po ang ilan sa aming starting prices:", price_ask: "Magtanong po tungkol sa partikular na treatment, halimbawa \"Magkano ang braces?\"",
      price_final: "Ang huling halaga ay depende sa inyong ngipin at treatment plan. Kukumpirmahin ito ng dentista sa konsulta, bago simulan ang anumang treatment.",
      again: "Parang nasagot ko na po iyan. Gusto n'yo po bang ipaliwanag pa ito nang mas detalyado ng aming team?",
      unsure2: "Pasensya na po, hindi ko pa rin nakuha. Subukan ang maikling tanong gaya ng \"Magkano ang cleaning?\", \"May braces ba kayo?\" o \"Saan ang Bocaue branch?\", o ipapatawag ko kayo sa aming team.",
      more_read: "Basahin ang buong guide →",
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
            [t("c_prices"), function () { priceAnswer(" "); }], [t("c_team"), handoff]];
  };
  function after(list) {
    list = (list || []).slice(0, 3);
    if (!list.some(function (l) { return l[1] === book; })) list.push([t("c_book"), book]);
    setChips(list.slice(0, 4));
  }
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
    var more = link(s.url, t("learn") + s.name + " →");
    var bk = link(bookUrl(), t("consult_cta")); bk.className = "dh-cta";
    var reads = (info.guides || []).filter(function (g) { return g.service === s.slug; }).map(function (g) {
      var p = el("p"); p.appendChild(link(g.url, t("read") + g.title)); return p;
    });
    say([lead || null, el("p", "dh-strong", s.name), s.summary || null,
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
    if ((info.prices || []).length) return priceAnswer(" ");
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
  var misses = 0;
  function fallback() {
    misses += 1;
    if (misses > 1) {
      say(t("unsure2"));
      return setChips([[t("c_team"), handoff], [t("c_prices"), price], [t("c_services"), servicesMenu], [t("c_book"), book]]);
    }
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
    ["aesthetic-dentistry", ["veneer", "whiten", "bleach", "makeover", "cosmetic", "aesthetic", "smile design", "bonding", "crown", "jacket", "bridge", "zirconia"]],
    ["prosthodontics", ["denture", "pustiso", "flexite", "prostho", "full mouth"]],
    ["dental-implants", ["implant", "extract", "bunot", "wisdom", "surgery", "opera", "impacted"]],
    ["orthodontics", ["brace", "bracket", "aligner", "invisalign", "retainer", "ortho", "tmj", "jaw", "panga", "sungki", "crooked"]],
    ["pediatric-dentistry", ["kid", "child", "bata", "anak", "baby", "pedia", "sedation", "special need", "toddler"]],
    ["general-dentistry", ["clean", "linis", "prophy", "check-up", "checkup", "check up", "root canal", "x-ray", "xray", "gum", "gilagid", "fluoride", "sealant", "pasta", "filling", "cavity", "butas"]]
  ];
  var STOP = (" the a an is are am do does did i my me you your we our us it its this that what how can could will would should to of in on for with and or be " +
              "have has there any about tell please want know need ano ang ng sa po ba ko mo na at para yung kung may mga pag paano ako kayo nyo ninyo " +
              "namin natin si ni kay din rin lang ho opo yes no hi hello ").split(" ");
  function tokens(q) {
    return q.split(" ").filter(function (w) { return w.length > 2 && STOP.indexOf(w) === -1; });
  }
  function svcBySlug(slug) { return info.services.filter(function (x) { return x.slug === slug; })[0]; }

  // Common questions: best keyword match (phrases count more than single words).
  function faqMatch(q) {
    var best = null, bestScore = 0;
    (info.faq || []).forEach(function (f) {
      var sc = 0;
      f.kw.forEach(function (k) {
        k = k.toLowerCase();
        if (q.indexOf(k) !== -1) { sc += k.indexOf(" ") !== -1 ? 3 : 2; return; }
        var ws = k.split(" ").filter(function (w) { return w.length > 2 && STOP.indexOf(w) === -1; });
        if (ws.length > 1 && ws.every(function (w) { return q.indexOf(w) !== -1; })) sc += 2.5;  // same words, any order
      });
      if (sc > bestScore) { bestScore = sc; best = f; }
    });
    return bestScore >= 2 ? best : null;
  }
  function faqAnswer(f) {
    if (f.service) ctxService = svcBySlug(f.service) || ctxService;
    var g = (info.guides || []).filter(function (x) { return f.guide && x.slug === f.guide; })[0];
    say([f[lang === "tl" ? "tl" : "en"], g ? link(g.url, t("read") + g.title) : null]);
    if (f.key === "discount" || f.key === "change_booking") return setChips([[t("c_team"), handoff], [t("c_call"), contacts]]);
    after([[t("c_consult"), book], [t("c_team"), handoff]]);
  }

  // Search inside the patient guides and answer with the best-matching part.
  function sectionMatch(q) {
    var words = tokens(q);
    if (!words.length) return null;
    var best = null, bestScore = 0;
    (info.sections || []).forEach(function (sec) {
      var head = (" " + sec.heading + " " + sec.title + " ").toLowerCase(), body = (" " + sec.text + " ").toLowerCase(), sc = 0;
      words.forEach(function (w) { if (head.indexOf(w) !== -1) sc += 2; else if (body.indexOf(w) !== -1) sc += 1; });
      if (sc > bestScore) { bestScore = sc; best = sec; }
    });
    return bestScore >= Math.max(3, words.length) ? best : null;
  }
  function sectionAnswer(sec) {
    if (sec.service) ctxService = svcBySlug(sec.service) || ctxService;
    var sentences = sec.text.match(/[^.!?]+[.!?]+["”)]?/g) || [sec.text];
    var short = sentences.slice(0, 3).join(" ").trim();
    say([lang === "tl" ? t("guide_intro") : null, el("p", "dh-strong", sec.heading === sec.title ? sec.title : sec.heading), short,
         link(sec.url, t("more_read"))]);
    after([[t("c_consult"), book], [t("c_team"), handoff]]);
  }

  // Prices (only when the clinic has published its price list; demo shows labelled samples).
  function priceMatch(q) {
    var scored = (info.prices || []).map(function (p) {
      var sc = 0;
      p.kw.forEach(function (k) { if (k.length > 2 && q.indexOf(k) !== -1) sc = Math.max(sc, k.length); });
      return [sc, p];
    }).filter(function (x) { return x[0] > 0; });
    if (!scored.length) return [];
    var top = Math.max.apply(null, scored.map(function (x) { return x[0]; }));
    return scored.filter(function (x) { return x[0] >= top - 3; }).map(function (x) { return x[1]; }).slice(0, 4);
  }
  function priceLine(p) {
    return p.name + ": " + (p.range ? "" : t("from")) + p.amount + (p.unit ? " " + p.unit : "");
  }
  function priceAnswer(q) {
    if (!(info.prices || []).length) return price();
    var items = priceMatch(q);
    var intro = null;
    if (!items.length && ctxService) items = info.prices.filter(function (p) { return p.service === ctxService.slug; }).slice(0, 5);
    if (!items.length) {
      var seen = {};
      items = info.prices.filter(function (p) { if (seen[p.service]) return false; seen[p.service] = 1; return true; }).slice(0, 6);
      intro = t("price_list");
    }
    if (items[0] && items[0].service) ctxService = svcBySlug(items[0].service) || ctxService;
    var parts = [intro, list(items.map(priceLine)), t("price_final")];
    if (intro) parts.push(t("price_ask"));
    if (items.some(function (p) { return p.sample; })) parts.push(el("p", "dh-sample", t("sample_note")));
    say(parts);
    after([[t("c_consult"), book], [t("c_team"), handoff]]);
  }

  // Don't give the same answer twice in a row.
  var lastKey = null, lastQ = null;
  function reply(key, fn, q) {
    var same = key === lastKey && q === lastQ;
    lastQ = q;
    if (same && ["book", "hello", "pain", "fallback", "thanks"].indexOf(key) === -1) {
      say(t("again"));
      setChips([[t("c_team"), handoff], [t("c_book"), book]]);
      lastKey = null;
      return;
    }
    lastKey = key;
    if (key !== "fallback") misses = 0;
    fn();
  }

  function answer(text) {
    var q = norm(text);
    // remember a treatment they mention (e.g. "how much are veneers?") so the booking form is pre-filled
    for (var k = 0; k < SERVICE_WORDS.length; k++) {
      if (has(q, SERVICE_WORDS[k][1])) { ctxService = svcBySlug(SERVICE_WORDS[k][0]) || ctxService; break; }
    }
    var faq = faqMatch(q);
    var urgent = has(q, ["emergency", "urgent", "namamaga", "swell", " nana", "abscess", "sobrang sakit", "severe", "toothache", "sakit ng ngipin",
                         "masakit ang ngipin", "masakit ngipin", "masakit na ngipin", "hindi makatulog", "can't sleep", "fever", "lagnat"]);
    var comfortQ = /\b(does|will|would|is|do)\b.*\b(hurt|painful)\b/.test(q) || has(q, ["masakit ba", "sasakit ba", "masakit po ba", "painful ba"]);
    if (comfortQ && !urgent) { var fh = (info.faq || []).filter(function (x) { return x.key === "hurt"; })[0]; if (fh) return reply("faq:hurt", function () { faqAnswer(fh); }, q); }
    if (urgent && !(faq && faq.key === "extraction_after")) return reply("pain", pain, q);
    if (has(q, ["human", "real person", "agent", "receptionist", "talk to", "kausap", "contact me", "call me", "tawagan", "someone call"])) return reply("handoff", handoff, q);
    if (has(q, ["magkano", "presyo", "price", "cost", "how much", "rate", "fee", "halaga", "budget", "mahal ba", "expensive", "cheap", "mura"]) &&
        !(faq && faq.key === "discount" && !has(q, ["magkano", "how much", "price", "presyo"]))) {
      return reply("price", function () { priceAnswer(q); }, q);
    }
    if (faq) return reply("faq:" + faq.key, function () { faqAnswer(faq); }, q);
    if (has(q, ["pain", "masakit", "sakit", "ache", "hurt", "bleed", "dugo", "infect"])) return reply("pain", pain, q);
    var GUIDE_WORDS = [
      ["veneers-vs-crowns", function () { return has(q, ["veneer"]) && has(q, ["crown", "jacket"]) || has(q, ["difference", "pagkakaiba", " vs "]) && has(q, ["veneer", "crown"]); }],
      ["silver-diamine-fluoride", function () { return has(q, [" sdf", "silver diamine", "diamine", "silver fluoride"]); }],
      ["childs-first-dental-visit", function () { return has(q, ["first visit", "first dental", "first check", "unang", "first time"]) && has(q, ["kid", "child", "bata", "anak", "baby", "son", "daughter", "toddler", "visit"]); }],
      ["preventive-dentistry-for-kids", function () { return has(q, ["sealant", "fluoride", "prevent", "iwas"]); }],
      ["white-spots-and-fluorosis", function () { return has(q, ["white spot", "fluorosis", "chalky", "puting", "spots on"]); }],
      ["about-dental-fillings", function () { return has(q, ["what is a filling", "about filling", "does filling hurt", "masakit ba ang pasta"]); }],
      ["caring-for-dentures", function () { return has(q, ["denture care", "clean my denture", "linisin ang pustiso", "new denture"]); }],
      ["braces-or-clear-aligners", function () { return has(q, ["brace", "aligner"]) && has(q, [" or ", " vs ", "difference", "better", "alin"]); }]
    ];
    for (var gi = 0; gi < GUIDE_WORDS.length; gi++) {
      if (GUIDE_WORDS[gi][1]()) { var gs = GUIDE_WORDS[gi][0]; return reply("guide:" + gs, function () { guide(gs); }, q); }
    }
    for (var i = 0; i < info.branches.length; i++) {
      var b = info.branches[i];
      if (q.indexOf(" " + b.name.toLowerCase().split(" ")[0] + " ") !== -1 || (b.slug === "sjdm" && has(q, ["san jose", "sjdm"]))) {
        return reply("branch:" + b.slug, function () { branch(b); }, q);
      }
    }
    if (has(q, ["why", "bakit", "legit", "trusted", "reliable", "maganda ba", "okay ba", "ok ba", "magaling", "recommend", "sulit", "worth"])) return reply("why", why, q);
    if (has(q, ["hour", "open", "close", "oras", "bukas", "sarado", "sunday", "linggo", "saturday", "sabado", "holiday", "what time", "anong oras"])) return reply("hours", allHours, q);
    if (has(q, ["book", "appoint", "schedule", "sched", "reserve", "slot", "magpa", "pa-appoint", "available"])) return reply("book", book, q);
    if (has(q, ["where", "saan", "location", "address", "direction", "map", "branch", "near", "malapit", "located"])) return reply("branches", branchesMenu, q);
    if (has(q, ["phone", "number", "contact", "call", "tawag", "text ", "viber", "cellphone", "mobile", "landline"])) return reply("contacts", contacts, q);
    if (has(q, [" lab", "laborator", "cbct", "scanner", " 3d", "milling", "digital"])) return reply("lab", lab, q);
    var sec = sectionMatch(q);
    if (sec) return reply("sec:" + sec.guide + sec.heading, function () { sectionAnswer(sec); }, q);
    for (var j = 0; j < SERVICE_WORDS.length; j++) {
      if (has(q, SERVICE_WORDS[j][1])) { var sl = SERVICE_WORDS[j][0]; return reply("svc:" + sl, function () { service(sl, t("svc_yes")); }, q); }
    }
    if (has(q, ["service", "offer", "treatment", "procedure", "ginagawa"])) return reply("services", servicesMenu, q);
    if (has(q, ["thank", "salamat", " ty "])) return reply("thanks", function () { say(t("thanks")); setChips(MAIN()); }, q);
    if (has(q, [" hi ", "hello", " hey", "good morning", "good afternoon", "good evening", "magandang", "kumusta", " po "]) && q.length < 30) {
      return reply("hello", function () { say(t("hello")); setChips(MAIN()); }, q);
    }
    return reply("fallback", fallback, q);
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
