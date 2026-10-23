"""Spam checks for the public website forms (inquiry form and the chat's "send to our team").

Bots fill in contact forms on thousands of sites with sales pitches ("include your site in Google's search index",
SEO, web design, crypto...). Messages that look like that are still saved, but marked as spam: they go to the
Leads > Spam tab instead of New, don't count anywhere, and staff can restore one with "Not spam". The visitor sees
the normal thank-you page either way, so bots learn nothing.
"""
from __future__ import annotations

import re

# a link: http(s)://..., www...., or a bare domain such as example.site
_LINK = re.compile(r"(https?://\S+|www\.\S+|\b[a-z0-9][a-z0-9-]{1,62}\.(?:com|net|org|site|online|xyz|info|biz|top|io|co|ru|cn|store|shop|"
                   r"click|link|app|pro|me|us|live|space|website|today|agency|digital|tech|club|ly|gl|to)\b)", re.I)
# typical pitches; each is a whole phrase, so ordinary patient messages don't match
PHRASES = [
    "search index", "search engine", "google's search", "google search results", "first page of google", "seo", "backlink", "rank your",
    "ranking", "web traffic", "website traffic", "more traffic", "domain", "submit your site", "submit your website", "web design",
    "website design", "redesign your", "app development", "lead generation", "generate leads", "digital marketing", "marketing services",
    "social media marketing", "guest post", "sponsored post", "crypto", "bitcoin", "forex", "investment opportunity", "business loan",
    "unsubscribe", "opt out", "opt-out", "reply stop", "business proposal", "virtual assistant", "outsourcing", "per hour",
    "free trial", "limited time offer", "special offer", "increase your sales", "boost your", "grow your business", "your website",
]
_PHRASE_RE = re.compile(r"(?<![a-z])(" + "|".join(re.escape(p) for p in PHRASES) + r")(?![a-z])", re.I)
_FOREIGN = re.compile(r"[Ѐ-ӿ؀-ۿ฀-๿぀-ヿ一-鿿가-힯]")
THRESHOLD = 4


def phone_ok(phone: str) -> bool:
    """A Philippine mobile (0917 123 4567, +63 917 123 4567) or landline with area code (044 123 4567, 02 8123 4567),
    or a number from another country written with + and the country code."""
    p = (phone or "").strip()
    if not p:
        return True
    if not re.fullmatch(r"[0-9+()\-.\s]{7,22}", p):
        return False
    digits = re.sub(r"\D", "", p)
    if p.startswith("+") and not digits.startswith("63"):
        return 8 <= len(digits) <= 15                      # abroad, e.g. +971 50 123 4567
    if digits.startswith("63") and len(digits) in (11, 12):
        digits = "0" + digits[2:]
    return bool(re.fullmatch(r"09\d{9}", digits) or re.fullmatch(r"0[2-8]\d{7,9}", digits))


PHONE_HELP = "Enter a mobile number like 0917 123 4567 (or a landline with area code, e.g. 044 123 4567)."


def spam_reasons(full_name: str, email: str, message: str) -> list[str]:
    """Why a website message looks like spam (empty list = looks fine)."""
    text = f"{full_name}\n{message}"
    score, why = 0, []
    links = _LINK.findall(message or "")
    if links:
        score += min(4, 2 * len(links))
        why.append(f"{len(links)} link{'s' if len(links) > 1 else ''}")
    hits = sorted({m.lower() for m in _PHRASE_RE.findall(text)})
    if hits:
        score += 2 * len(hits)
        why.append("sales words: " + ", ".join(hits[:4]))
    dom = (email or "").rsplit("@", 1)[-1].lower() if "@" in (email or "") else ""
    if dom and "dentalhaven" in dom.replace("-", "").replace(".", ""):
        score += 3
        why.append(f"email pretends to be from Dental Haven ({dom})")
    letters = re.findall(r"[^\W\d_]", text)
    foreign = _FOREIGN.findall(text)
    if letters and len(foreign) / len(letters) > 0.3:
        score += 4
        why.append("written in a foreign script")
    if re.search(r"<a\s+href|\[url=", message or "", re.I):
        score += 4
        why.append("hidden links")
    return why if score >= THRESHOLD else []
