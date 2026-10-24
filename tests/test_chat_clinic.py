"""Website chat: the front desk's most-asked questions (app/chat_clinic.py) are served to the chat and well formed."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402

from app.chat_clinic import CLINIC_FAQ, POLICY_QUESTIONS  # noqa: E402
from app.chat_procedures import PROCEDURES  # noqa: E402


def words_in(q: str, alt: list[str]) -> bool:
    """Same rule as chat.js wordsIn(): short words must be whole words, longer ones may be part of a word."""
    return all(re.search(r"(^|\s)" + re.escape(w) + r"(\s|$)", q) if len(w) <= 3 else w in q for w in alt)


def best(question: str, price_q: bool = False):
    q = " " + re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ\s-]", " ", question.lower().replace("’", "").replace("'", ""))) + " "
    q = re.sub(r" po(?= )", "", q)
    top, out = 0, None
    for e in CLINIC_FAQ:
        if price_q and not e.get("price"):
            continue
        sc = max((len(" ".join(a)) + 10 * len(a) for a in e["need"] if words_in(q, a)), default=0)
        if sc > top:
            top, out = sc, e["key"]
    return out


class TestClinicFaq(Base):
    def test_entries_are_complete(self):
        keys = [e["key"] for e in CLINIC_FAQ]
        self.assertEqual(len(keys), len(set(keys)))
        procs = {p["key"] for p in PROCEDURES}
        for e in CLINIC_FAQ:
            self.assertTrue(e["need"] and all(e["need"]), e["key"])
            if not e.get("aspect"):
                self.assertTrue(e["en"] and e["tl"], e["key"])
            if e.get("proc"):
                self.assertIn(e["proc"], procs, e["key"])
        for k, _ in POLICY_QUESTIONS:       # every open policy question points at a pending answer
            self.assertIn(k, keys)
            self.assertTrue(next(e for e in CLINIC_FAQ if e["key"] == k).get("pending"), k)

    def test_served_to_the_chat(self):
        info = self.app.test_client().get("/chat/info.json").get_json()
        self.assertEqual(len(info["pri"]), len(CLINIC_FAQ))

    def test_questions_find_their_answer(self):
        cases = {
            "Per tooth po ba ang bayad?": "per_tooth",
            "Pwede po bang magpa-pasta kahit masakit yung ngipin?": "filling_painful",
            "Pwede po bang magpabunot kahit namamaga yung gums?": "extract_swollen",
            "Pwede po bang magpakabit agad sa first visit?": "braces_first_visit",
            "Pwede po bang magpa-pasta agad kahit first visit?": "same_day_first_visit",
            "Ilang beses po kailangang bumalik para sa adjustment?": "braces_adjust_freq",
            "Ano po ang difference ng ordinary at Lucitone na pustiso?": "denture_bases",
            "Pwede po bang upper lang ang ipagawa?": "denture_one_jaw",
            "Ano po ang mas okay, fixed bridge or implant?": "bridge_vs_implant",
            "Pwede po bang tanggalin kahit hindi pa lumalabas?": "wisdom_unerupted",
            "Kasama na po ba yung crown sa presyo ng root canal?": "rct_crown_included",
            "Pumuputi rin po ba ang pustiso or crown?": "whitening_restorations",
            "Pwede po bang magpagawa ng fixed bridge kahit may pustiso na?": "bridge_from_denture",
            "Ano po ang difference ng jacket crown at pasta?": "crown_vs_filling",
            "Kailangan po ba ng root canal bago magpakabit ng jacket crown?": "crown_rct_needed",
            "Ano po ang difference ng veneers at jacket crown?": "veneer_vs_crown",
            "May available po ba kayong iba't ibang kulay ng veneers?": "veneer_shades",
            "Kailangan po ba talagang bawasan ang ngipin bago magpakabit ng veneers?": "veneer_prep",
            "Pwede po bang magpa-veneers agad sa first visit?": "veneer_first_visit",
        }
        for q, want in cases.items():
            self.assertEqual(best(q, price_q="presyo" in q.lower()), want, q)
        # not caught: general questions keep their usual answers
        for q in ("Masakit po ba magpabunot?", "My filling fell out", "Pwede po mamaya?", "Natanggal po ang pasta ko",
                  "Magkano po magpa-pasta?", "Kailangan po ba ng medical clearance para sa surgery?",
                  "Magkano po per tooth ang veneers?", "Ilang balik po ang kailangan bago matapos ang veneers?"):
            self.assertIsNone(best(q, price_q="magkano" in q.lower()), q)
