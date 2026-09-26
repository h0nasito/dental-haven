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
      a_what: "What is it?", a_duration: "How long does it take?", a_pain: "Does it hurt?", a_recovery: "Recovery", a_lasts: "How long does it last?",
      a_prepare: "How to prepare", a_avoid: "What to avoid after", a_risks: "Risks & side effects", a_alternatives: "Alternatives",
      a_materials: "Materials", a_before: "Is an X-ray needed?", a_contact: "When to call us", yes_offer: function (n) { return "Yes, we offer " + n + "."; },
      generic_pick: "That depends a little on the treatment. Tell me which one and I'll be more specific:",
      open_now: function (until) { return "Yes, we're open now, until " + until + " today."; },
      closed_now: function (when) { return "We're closed right now. We open again " + when + "."; },
      today: "today", tomorrow: "tomorrow", at: " at ",
      er: "Please go to the nearest hospital emergency room now, or call 911. Uncontrolled bleeding, trouble breathing or swallowing, or a serious injury needs emergency care right away. Once you're safe, call your branch and we'll help with follow-up care.",
      slots_title: function (day) { return "Online appointments available " + day + " (check-up):"; },
      slots_none: "I couldn't find open online slots in the next few days. Please call your branch: they may still be able to fit you in.",
      slots_more: "Pick your time on the booking page:", checking: "Checking available times…",
      a_price: "Price", which_proc: "Which treatment are you asking about? Tap one, or type its name:",
      proc_note: "Every patient is different: your dentist will confirm the details for you at your consultation.",
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
      a_what: "Ano ito?", a_duration: "Gaano katagal?", a_pain: "Masakit ba?", a_recovery: "Paggaling", a_lasts: "Gaano tatagal?",
      a_prepare: "Paano maghanda", a_avoid: "Iiwasan pagkatapos", a_risks: "Panganib at side effects", a_alternatives: "Ibang opsyon",
      a_materials: "Materyales", a_before: "Kailangan ba ng X-ray?", a_contact: "Kailan tatawag", yes_offer: function (n) { return "Opo, mayroon kaming " + n + "."; },
      generic_pick: "Depende po ito nang kaunti sa treatment. Sabihin kung alin para mas eksakto ang sagot ko:",
      open_now: function (until) { return "Opo, bukas kami ngayon, hanggang " + until + " ngayong araw."; },
      closed_now: function (when) { return "Sarado po kami ngayon. Magbubukas ulit " + when + "."; },
      today: "ngayong araw", tomorrow: "bukas", at: " nang ",
      er: "Pumunta po agad sa pinakamalapit na emergency room ng ospital, o tumawag sa 911. Ang pagdurugong hindi tumitigil, hirap huminga o lumunok, o malubhang pinsala ay kailangan ng emergency care agad. Kapag ligtas na kayo, tumawag sa branch at tutulungan namin kayo sa follow-up.",
      slots_title: function (day) { return "May bakanteng online appointment " + day + " (check-up):"; },
      slots_none: "Wala akong nakitang bakanteng online slot sa susunod na ilang araw. Pakitawagan ang branch: baka maisingit pa kayo.",
      slots_more: "Pumili ng oras sa booking page:", checking: "Tinitingnan ang mga bakanteng oras…",
      a_price: "Presyo", which_proc: "Anong treatment po ang tinutukoy ninyo? Pumili o i-type ang pangalan:",
      proc_note: "Iba-iba ang bawat pasyente: kukumpirmahin ng dentista ang detalye para sa inyo sa konsulta.",
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
  function norm(t) { return (" " + (t || "").toLowerCase().replace(/[’']/g, "").replace(/[^a-z0-9ñ\s-]/g, " ").replace(/\s+/g, " ") + " "); }
  function kwn(w) { return w.toLowerCase().replace(/[’']/g, ""); }
  function has(t, words) { return words.some(function (w) { return t.indexOf(kwn(w)) !== -1; }); }

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
      if (b.facebook) { li.append(" · "); li.appendChild(link(b.facebook, "Facebook", true)); }
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
    ["periodontal-care", ["gum disease", "periodont", "deep clean", "root planing", "gum graft", "receding", "gilagid", "gums"]],
    ["aesthetic-dentistry", ["whiten", "bleach", "makeover", "cosmetic", "aesthetic", "smile design", "bonding"]],
    ["prosthodontics", ["denture", "pustiso", "flexite", "prostho", "implant", "veneer", "replace", "missing"]],
    ["restorative-dentistry", ["crown", "jacket", "bridge", "zirconia", "inlay", "onlay", "root canal", "pasta", "filling", "cavity", "butas", "restor", "endo"]],
    ["oral-surgery", ["extract", "bunot", "wisdom", "surgery", "opera", "impacted", "bone graft", "third molar"]],
    ["orthodontics", ["brace", "bracket", "aligner", "invisalign", "retainer", "ortho", "tmj", "jaw", "panga", "sungki", "crooked"]],
    ["pediatric-dentistry", ["kid", "child", "bata", "anak", "baby", "pedia", "sedation", "special need", "toddler"]],
    ["general-dentistry", ["clean", "linis", "prophy", "check-up", "checkup", "check up", "x-ray", "xray", "cbct", "panoramic", "fluoride", "sealant", "screening", "cancer"]]
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
        k = kwn(k);
        var single = k.indexOf(" ") === -1;
        if (single ? new RegExp("(^|\\s)" + k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "(s|es)?(\\s|$)").test(q) : q.indexOf(k) !== -1) { sc += single ? 2 : 3; return; }
        var ws = k.split(" ").filter(function (w) { return w.length > 2 && STOP.indexOf(w) === -1; });
        if (ws.length > 1 && ws.every(function (w) { return q.indexOf(w) !== -1; })) sc += 2.5;  // same words, any order
      });
      if (sc > bestScore) { bestScore = sc; best = f; }
    });
    if (best) best = Object.assign({}, best, { strong: bestScore >= 3 });
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
  function priceMatch(q, all) {
    var scored = (info.prices || []).map(function (p) {
      var sc = 0;
      p.kw.forEach(function (k) { if (k.length > 2 && q.indexOf(k) !== -1) sc = Math.max(sc, k.length); });
      return [sc, p];
    }).filter(function (x) { return x[0] > 0; });
    if (!scored.length) return [];
    var top = Math.max.apply(null, scored.map(function (x) { return x[0]; }));
    return scored.filter(function (x) { return all || x[0] >= top - 3; }).map(function (x) { return x[1]; }).slice(0, all ? 5 : 4);
  }
  function priceLine(p) {
    return p.name + ": " + (p.range ? "" : t("from")) + p.amount + (p.unit ? " " + p.unit : "");
  }
  function priceAnswer(q) {
    if (!(info.prices || []).length) return price();
    var items = priceMatch(q);
    var intro = null;
    if (!items.length && ctxProc) items = priceMatch(" " + ctxProc.kw.concat([ctxProc.name.toLowerCase()]).join(" ") + " ", true);
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

  // Procedures: which treatment + what the patient wants to know about it.
  var ctxProc = null;
  var PROC_GUIDE = { filling: "about-dental-fillings", crown: "veneers-vs-crowns", veneer: "veneers-vs-crowns", implant: "dental-implants-what-to-expect",
                     denture: "caring-for-dentures", braces: "braces-or-clear-aligners", aligners: "braces-or-clear-aligners",
                     sdf: "silver-diamine-fluoride", sealant: "preventive-dentistry-for-kids", fluoride: "preventive-dentistry-for-kids" };
  var SECONDARY = ["sedation", "xray", "checkup"];  // "anesthesia or sedation for a filling" is about the filling
  function procMatch(q) {
    var best = null, bestLen = 0;
    (info.procedures || []).forEach(function (p) {
      if (SECONDARY.indexOf(p.key) !== -1) return;
      p.kw.forEach(function (k) {
        k = k.toLowerCase();
        var hit = k.length <= 4 ? q.indexOf(" " + k + " ") !== -1 || q.indexOf(" " + k + "s ") !== -1 : q.indexOf(k) !== -1;
        if (hit && k.length > bestLen) { bestLen = k.length; best = p; }
      });
    });
    if (best) return best;
    (info.procedures || []).forEach(function (p) {
      if (SECONDARY.indexOf(p.key) === -1) return;
      p.kw.forEach(function (k) {
        k = k.toLowerCase();
        var hit = k.length <= 4 ? q.indexOf(" " + k + " ") !== -1 || q.indexOf(" " + k + "s ") !== -1 : q.indexOf(k) !== -1;
        if (hit && k.length > bestLen) { bestLen = k.length; best = p; }
      });
    });
    return best;
  }
  function aspectOf(q) {
    if (has(q, ["when should i call", "when to call", "when should i contact", "contact the clinic after", "call the clinic after", "call you after",
                "pain after", "swelling after", "bleeding after", "sumakit pagkatapos", "namaga pagkatapos", "masakit pa rin", "still hurts", "still painful",
                "kailan tatawag", "kailan ako tatawag"])) return "contact";
    if (/how long (does|do|will|would) (it|they|this|that|the \w+|\w+) ?(\w+ )?last/.test(q) || has(q, ["tatagal ba", "ilang taon tatagal", "gaano tatagal",
        "gaano katagal tatagal", "last long", "permanent ba", "is it permanent", "lifespan", "how many years"])) return "lasts";
    if (has(q, ["x-ray needed", "xray needed", "need an x-ray", "need x-ray", "need xray", "need a consultation", "consultation needed", "consultation first",
                "x-ray first", "xray first", "consultation or x-ray", "kailangan ba ng x-ray", "kailangan ba ng xray", "kailangan ba ng konsulta", "need a check-up first",
                "need a checkup first"])) return "before";
    if (has(q, ["prepare", "preparation", "maghanda", "paghahanda", "get ready", "before the procedure", "before surgery", "before my procedure",
                "before the extraction", "before extraction", "before treatment", "bago ang procedure", "bago magpa"])) return "prepare";
    if (has(q, ["avoid", "bawal", "iwasan", "iiwasan", "should not eat", "shouldn't eat", "can't eat", "cannot eat", "foods to", "food to", "hindi puwedeng kainin",
                "hindi pwedeng kainin", "activities after", "exercise after", "can i smoke", "coffee", "kape", "can i drink", "puwede uminom", "pwede uminom"])) return "avoid";
    if (has(q, ["risk", "side effect", "side-effect", "complication", "danger", "delikado", "safe ba", "is it safe", "ligtas ba", "masama ba"])) return "risks";
    if (has(q, ["alternative", "other option", "instead of", "ibang paraan", "ibang opsyon", "iba pang opsyon", "other than"])) return "alternatives";
    if (has(q, ["recover", "heal", "gumaling", "hilom", "downtime", "aftercare", "after care", "pagkatapos", "after the procedure", "afterwards", "expect after",
                "bed rest", "back to work", "back to school", "work after", "school after", "swelling after", "can i eat", "puwede kumain", "pwede kumain",
                "pwede na kumain", "puwede na kumain", " after "])) return "recovery";
    if (has(q, ["how long", "gaano katagal", "katagal", "ilang oras", "ilang minuto", "how many hours", "how many minutes", "how many visits", "appointments will",
                "how many appointments", "ilang balik", "ilang beses", "duration", "how much time", "take long", "same day", "one day", "isang araw", "one visit",
                "isang balik", "gaano kabilis", "how fast", "how quick", "ilang araw", "how many days", "how many sessions", "session"])) return "duration";
    if (/\b(does|will|would|is|do)\b.*\b(hurt|painful)\b/.test(q) || has(q, ["masakit ba", "sasakit", "masakit po ba", "painful", "anesthesia",
                "anaesthesia", "numb", "turok", "manhid", "pain free", "painless", "sedation for", "need sedation"])) return "pain";
    if (has(q, ["material", "made of", "gawa sa", "yari sa", "materyales", "porcelain", "ceramic", "zirconia", "metal", "acrylic", "titanium",
                "composite", "amalgam", "types of", "kinds of", "klase ng", "uri ng", "temporary"])) return "materials";
    if (has(q, ["do you offer", "do you do", "do you provide", "do you make", "do you have", "do you perform", "offer ba", "meron ba", "mayroon ba",
                "may ginagawa", "gumagawa ba", "gumagawa kayo", "nagpapa", "can you do", "can i get", "pwede ba magpa", "puwede ba magpa"])) return "offer";
    if (has(q, ["what is", "what's", "what are", "whats", "ano ang", "ano yung", "ano po ang", "ano ba ang", "explain", "how is it done",
                "paano ginagawa", "what happens", "how does it work", "paano", "meaning", "ibig sabihin", "procedure for", "process"])) return "what";
    return null;
  }
  function procMatchAll(q) {
    var found = [];
    (info.procedures || []).forEach(function (p) {
      if (p.kw.some(function (k) { k = k.toLowerCase(); return k.length <= 4 ? q.indexOf(" " + k + " ") !== -1 || q.indexOf(" " + k + "s ") !== -1 : q.indexOf(k) !== -1; })) found.push(p);
    });
    return found;
  }
  function genericAnswer(aspect) {
    var L = lang === "tl" ? "tl" : "en";
    say([info.generic[aspect][L], t("generic_pick")]);
    var common = ["extraction", "wisdom", "root_canal", "filling", "implant", "braces", "whitening", "deep_cleaning"];
    setChips((info.procedures || []).filter(function (p) { return common.indexOf(p.key) !== -1; }).slice(0, 6).map(function (p) {
      return [p.name, function () { procAnswer(p, aspect); }];
    }));
  }

  // "Are you open now?" from each branch's hours, in Philippine time.
  function manilaNow() {
    var parts = {};
    new Intl.DateTimeFormat("en-US", { timeZone: "Asia/Manila", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false, year: "numeric", month: "2-digit", day: "2-digit" })
      .formatToParts(new Date()).forEach(function (x) { parts[x.type] = x.value; });
    var wd = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].indexOf(parts.weekday);
    return { wd: wd, min: (parseInt(parts.hour, 10) % 24) * 60 + parseInt(parts.minute, 10), date: parts.year + "-" + parts.month + "-" + parts.day };
  }
  function hm(s) { return parseInt(s.slice(0, 2), 10) * 60 + parseInt(s.slice(3, 5), 10); }
  function t12(s) { var h = parseInt(s.slice(0, 2), 10), m = s.slice(3, 5); return ((h + 11) % 12 + 1) + (m !== "00" ? ":" + m : "") + (h < 12 ? " AM" : " PM"); }
  var DAYNAMES = { en: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], tl: ["Lunes", "Martes", "Miyerkules", "Huwebes", "Biyernes", "Sabado", "Linggo"] };
  function openNow() {
    var b = info.branches[0];
    if (!b || !b.week || !b.week.length) return allHours();
    var now = manilaNow(), day = b.week.filter(function (d) { return d.wd === now.wd; })[0];
    if (day && !day.closed && now.min >= hm(day.open) && now.min < hm(day.close)) {
      say([t("open_now")(t12(day.close)), t("hours_book")]);
    } else {
      var when = null;
      if (day && !day.closed && now.min < hm(day.open)) when = t("today") + t("at") + t12(day.open);
      for (var i = 1; !when && i <= 7; i++) {
        var wd = (now.wd + i) % 7, d = b.week.filter(function (x) { return x.wd === wd; })[0];
        if (d && !d.closed) when = (i === 1 ? t("tomorrow") : DAYNAMES[lang === "tl" ? "tl" : "en"][wd]) + t("at") + t12(d.open);
      }
      say([t("closed_now")(when || "soon"), t("hours_book")]);
    }
    after([[t("c_branches"), branchesMenu]]);
  }

  // "Any appointments available today?" from the live booking system.
  function availability() {
    var svc = svcBySlug("general-dentistry") || info.services[0], now = manilaNow();
    say(t("checking"));
    var base = new Date(now.date + "T00:00:00");
    function ymd(d) { return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2); }
    function tryDay(offset) {
      if (offset > 6) { say(t("slots_none")); return setChips([[t("c_call"), contacts], [t("c_team"), handoff]]); }
      var d = new Date(base.getTime() + offset * 86400000), day = ymd(d);
      Promise.all(info.branches.map(function (b) {
        return fetch(info.slots + "?branch_id=" + b.id + "&service_id=" + svc.id + "&date=" + day, { credentials: "same-origin" })
          .then(function (r) { return r.json(); }).then(function (j) { return { b: b, labels: j.labels || [] }; })
          .catch(function () { return { b: b, labels: [] }; });
      })).then(function (res) {
        var open = res.filter(function (x) { return x.labels.length; });
        if (!open.length) return tryDay(offset + 1);
        var label = offset === 0 ? t("today") : offset === 1 ? t("tomorrow") : DAYNAMES[lang === "tl" ? "tl" : "en"][(d.getDay() + 6) % 7];
        var a = link(info.book, t("book_cta")); a.className = "dh-cta";
        say([t("slots_title")(label), list(open.map(function (x) { return x.b.name + ": " + x.labels.slice(0, 4).join(", ") + (x.labels.length > 4 ? "…" : ""); })), t("slots_more"), a]);
        after([[t("c_team"), handoff]]);
      });
    }
    tryDay(0);
  }
  function er() {
    say(el("p", "dh-warn", t("er")));
    setChips([[t("c_call"), contacts]]);
  }
  function procPrice(p) { ctxProc = p; priceAnswer(" "); }
  function procAnswer(p, aspect) {
    ctxProc = p;
    ctxService = svcBySlug(p.service) || ctxService;
    var L = lang === "tl" ? "tl" : "en";
    var text = p[aspect] ? p[aspect][L] : (info.generic && info.generic[aspect] ? info.generic[aspect][L] : null);
    var lead = null;
    if (aspect === "offer") { lead = t("yes_offer")(p.name); text = null; aspect = "what"; }
    if (!text) { aspect = "what"; text = p.what[L]; }
    var g = (info.guides || []).filter(function (x) { return x.slug === PROC_GUIDE[p.key]; })[0];
    var parts = lead ? [el("p", "dh-strong", lead), text] : [el("p", "dh-strong", p.name), text];
    if (aspect === "duration" || aspect === "recovery" || aspect === "lasts") parts.push(el("p", "dh-note", t("proc_note")));
    if (g) parts.push(link(g.url, t("read") + g.title));
    say(parts);
    var chips = [[t("c_book_this"), book]];
    var NEXT = { what: p.materials ? ["duration", "materials"] : ["duration", "pain", "recovery"], duration: ["pain", "recovery"], pain: ["duration", "recovery"], recovery: ["avoid", "contact"],
                 avoid: ["recovery", "contact"], lasts: ["duration", "alternatives"], prepare: ["duration", "pain"], risks: ["alternatives", "recovery"],
                 alternatives: ["what", "risks"], before: ["prepare", "duration"], contact: ["recovery", "avoid"],
                 materials: ["lasts", "duration"] }[aspect] || ["duration", "pain"];
    NEXT.forEach(function (a) {
      if (chips.length < 3 && (p[a] || (info.generic && info.generic[a]))) chips.push([t("a_" + a), function () { procAnswer(p, a); }]);
    });
    if ((info.prices || []).length) chips.push([t("a_price"), function () { procPrice(p); }]);
    else chips.push([t("c_team"), handoff]);
    setChips(chips);
  }
  function askWhichProc(aspect) {
    say(t("which_proc"));
    var common = ["extraction", "cleaning", "filling", "root_canal", "braces", "implant", "crown", "whitening"];
    setChips((info.procedures || []).filter(function (p) { return common.indexOf(p.key) !== -1; }).slice(0, 6).map(function (p) {
      return [p.name, function () { procAnswer(p, aspect); }];
    }));
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
    if (has(q, ["uncontrolled bleeding", "won't stop bleeding", "wont stop bleeding", "bleeding won't stop", "bleeding wont stop", "bleeding that won",
                "can't stop the bleeding", "hindi tumitigil ang dugo", "hindi tumitigil ang pagdurugo", "trouble breathing", "hard to breathe", "difficulty breathing",
                "can't breathe", "cant breathe", "hirap huminga", "trouble swallowing", "hard to swallow", "difficulty swallowing", "hirap lumunok",
                "serious injury", "serious dental injury", "accident", "naaksidente", "nabangga"]) ||
        (has(q, ["hirap", "nahihirapan"]) && has(q, ["huminga", "lumunok", "paghinga"]))) return reply("er", er, q);
    var urgent = has(q, ["emergency", "urgent", "namamaga", "swell", "swollen", " nana", "abscess", "sobrang sakit", "severe", "toothache", "sakit ng ngipin",
                         "masakit ang ngipin", "masakit ngipin", "masakit na ngipin", "hindi makatulog", "can't sleep", "fever", "lagnat"]);
    var proc = procMatch(q), aspect = aspectOf(q);
    if (proc) { ctxProc = proc; ctxService = svcBySlug(proc.service) || ctxService; }
    var severe = has(q, ["swollen", "swell", "namamaga", "fever", "lagnat", "abscess", " nana", "can't sleep", "hindi makatulog", "severe", "sobrang sakit"]);
    if (faq && ["medication", "toothache_cause", "emergency_offer", "knocked_out", "temporary", "allergy", "material_cost", "material_diff",
                "materials_safe", "choose_material", "samples", "dont_see", "which_right"].indexOf(faq.key) !== -1 && !severe) return reply("faq:" + faq.key, function () { faqAnswer(faq); }, q);
    if (urgent && !(faq && faq.key === "extraction_after") && aspect !== "recovery" && aspect !== "contact") return reply("pain", pain, q);
    var comfortQ = /\b(does|will|would|is|do)\b.*\b(hurt|painful)\b/.test(q) || has(q, ["masakit ba", "sasakit ba", "masakit po ba", "painful ba"]);
    if (comfortQ && !proc && ctxProc) { var cpp = ctxProc; return reply("proc:" + cpp.key + "pain", function () { procAnswer(cpp, "pain"); }, q); }
    if (comfortQ && !proc) { var fh = (info.faq || []).filter(function (x) { return x.key === "hurt"; })[0]; if (fh) return reply("faq:hurt", function () { faqAnswer(fh); }, q); }
    if (has(q, ["human", "real person", "agent", "receptionist", "talk to", "kausap", "contact me", "call me", "tawagan", "someone call"])) return reply("handoff", handoff, q);
    if (has(q, ["magkano", "presyo", "price", "cost", "how much", " rate ", " rates ", " fee ", " fees ", "halaga", "budget", "mahal ba", "expensive", "cheap", " mura"]) &&
        !(faq && faq.key === "discount" && !has(q, ["magkano", "how much", "price", "presyo"]))) {
      return reply("price", function () { priceAnswer(q); }, q);
    }
    if (has(q, ["weekend", "sunday", "linggo", "saturday", "sabado", "holiday"])) return reply("hours", allHours, q);
    if (has(q, ["open today", "open now", "open ngayon", "bukas ngayon", "bukas ba kayo", "bukas po ba", "bukas ba", "is the clinic open", "are you open",
                "is it open", "open ba", "open po ba", "open pa ba", "open right now"])) return reply("opennow", openNow, q);
    if (has(q, ["available today", "appointments today", "appointment today", "available appointment", "available slot", "slots", "available times",
                "times are available", "appointment times", "bakante", "may slot", "available ba", "free slot", "open slot", "schedule available"])) return reply("avail", availability, q);
    if (aspect === "offer") {
      var all = procMatchAll(q);
      if (all.length > 1) return reply("offer:" + q, function () {
        say([el("p", "dh-strong", t("yes_offer")(all.map(function (x) { return x.name; }).join(" & ")))]);
        setChips(all.slice(0, 3).map(function (x) { return [x.name, function () { procAnswer(x, "what"); }]; }).concat([[t("c_book"), book]]));
      }, q);
    }
    if (proc && aspect) return reply("proc:" + proc.key + aspect, function () { procAnswer(proc, aspect); }, q);
    if (!proc && aspect && ["what", "offer"].indexOf(aspect) === -1 && (!faq || (!faq.strong && ctxProc))) {
      // follow-up like "how long does it take?" about the treatment we were just talking about
      if (ctxProc) { var cp = ctxProc; return reply("proc:" + cp.key + aspect, function () { procAnswer(cp, aspect); }, q); }
      if (info.generic && info.generic[aspect]) return reply("gen:" + aspect, function () { genericAnswer(aspect); }, q);
      if (aspect !== "pain") return reply("which:" + aspect, function () { askWhichProc(aspect); }, q);
    }
    if (faq) return reply("faq:" + faq.key, function () { faqAnswer(faq); }, q);
    if (proc && proc.key === "tmj") return reply("proc:tmjwhat", function () { procAnswer(proc, "what"); }, q);
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
    if (proc) return reply("proc:" + proc.key + "what", function () { procAnswer(proc, "what"); }, q);
    for (var i = 0; i < info.branches.length; i++) {
      var b = info.branches[i];
      if (q.indexOf(" " + b.name.toLowerCase().split(" ")[0] + " ") !== -1 || (b.slug === "sjdm" && has(q, ["san jose", "sjdm"]))) {
        return reply("branch:" + b.slug, function () { branch(b); }, q);
      }
    }
    if (has(q, ["why", "bakit", "legit", "trusted", "reliable", "maganda ba", "okay ba", "ok ba", "magaling", "recommend", "sulit", "worth"])) return reply("why", why, q);
    if (has(q, ["hour", "open", "close", "oras", "bukas", "sarado", "sunday", "linggo", "saturday", "sabado", "holiday", "what time", "anong oras"])) return reply("hours", allHours, q);
    if (has(q, ["book", "appoint", "schedule", "sched", "reserve", "slot", "magpa", "pa-appoint", "available"])) return reply("book", book, q);
    if (has(q, ["where", "saan", "location", "address", "direction", "map", "branch", "near", "malapit", "located", "how do i get", "get there",
                "paano pumunta", "commute", "waze"])) return reply("branches", branchesMenu, q);
    if (has(q, ["phone", "number", "contact", "call", "tawag", "text ", "viber", "cellphone", "mobile", "landline", "message you", "messenger",
                "facebook", "email", "reach you"])) return reply("contacts", contacts, q);
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
