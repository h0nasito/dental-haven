"""Price list: the clinic's 2026 price list is used by the chat (and quotations) only, never on website pages."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestPrices(Base):
    def _info(self):
        return self.app.test_client().get("/chat/info.json").get_json()

    def test_clinic_price_list_loaded_for_chat_only(self):
        from app.prices_content import CLINIC_PRICES
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM price_items WHERE sample = 1"), 0)
        names = {r["name"] for r in self.conn.all("SELECT name FROM price_items")}
        self.assertTrue({p[0] for p in CLINIC_PRICES} <= names)
        prices = {p["name"]: p for p in self._info()["prices"]}
        self.assertEqual(prices["Oral prophylaxis (cleaning): moderate"]["amount"], "₱1,700 – ₱2,300")
        self.assertEqual(prices["Tooth extraction"]["amount"], "₱980")
        self.assertFalse(prices["Tooth extraction"]["fixed"])              # "980 minimum" → "from ₱980"
        self.assertTrue(prices["Dental examination (check-up)"]["fixed"])  # exactly ₱650
        self.assertIn("downpayment", prices["Metal braces: Class 1"]["note"])
        for n in ("Porcelain E.max crown / bridge", "Zirconia crown / bridge", "Veneers: direct composite", "Endo crown: ceramic"):
            self.assertEqual(prices[n]["unit"], "per tooth", n)
        # no guessed prices where the PDF has none
        self.assertFalse(any("implant" in n.lower() for n in prices))
        self.assertFalse(any("sapphire" in n.lower() for n in prices))
        # never shown on the website pages themselves
        c = self.app.test_client()
        for path in ("/", "/services/prosthodontics", "/services/orthodontics", "/guides", "/branches/malolos"):
            html = c.get(path).data.decode()
            self.assertNotIn("₱", html, path)
            self.assertIsNone(re.search(r"\b35,000\b|\b9,500\b", html), path)

    def test_upgrade_replaces_only_sample_prices(self):
        from app import settings
        from app.seed import seed_base
        svc = self.q("SELECT id FROM services WHERE slug = 'general-dentistry'")["id"]
        self.conn.execute("DELETE FROM price_items WHERE name = 'Dental examination (check-up)'")
        self.conn.insert("price_items", {"name": "Old dummy item", "service_id": svc, "price_from_cents": 100, "sample": 1, "updated_at": "x"})
        self.conn.insert("price_items", {"name": "Staff-added item", "service_id": svc, "price_from_cents": 200, "sample": 0, "updated_at": "x"})
        settings.put("seed.clinic_prices_version", 0, None, self.conn)
        seed_base(self.conn)
        names = {r["name"] for r in self.conn.all("SELECT name FROM price_items")}
        self.assertNotIn("Old dummy item", names)
        self.assertIn("Staff-added item", names)
        self.assertIn("Dental examination (check-up)", names)

    def test_v1_install_gets_per_tooth_units(self):
        from app import settings
        from app.seed import seed_base
        self.conn.execute("UPDATE price_items SET unit = '' WHERE name LIKE 'Veneers:%' OR name LIKE '%crown%bridge%'")
        self.conn.execute("UPDATE price_items SET name = 'Porcelain E.max crown / 3-unit bridge' WHERE name = 'Porcelain E.max crown / bridge'")
        self.conn.execute("UPDATE price_items SET unit = 'per arch' WHERE name = 'Veneers: ceramic'")  # a staff edit
        settings.put("seed.clinic_prices_version", 1, None, self.conn)
        settings.put("prices.show_public", False, None, self.conn)  # hidden by a super admin
        seed_base(self.conn)
        units = {r["name"]: r["unit"] for r in self.conn.all("SELECT name, unit FROM price_items")}
        self.assertEqual(units["Porcelain E.max crown / bridge"], "per tooth")
        self.assertEqual(units["Veneers: zirconia"], "per tooth")
        self.assertEqual(units["Veneers: ceramic"], "per arch")
        self.assertFalse(settings.get("prices.show_public", self.conn))

    def test_admin_edit_and_visibility(self):
        c = self.login("admin")
        page = c.get("/staff/admin/prices").data.decode()
        self.assertIn("Shown to patients", page)
        exam = self.q("SELECT * FROM price_items WHERE name = 'Dental examination (check-up)'")
        rows = self.conn.all("SELECT * FROM price_items")
        form = {"action": "save"}
        for row in rows:
            form.update({f"name_{row['id']}": row["name"], f"from_{row['id']}": str(row["price_from_cents"] // 100),
                         f"to_{row['id']}": str(row["price_to_cents"] // 100) if row["price_to_cents"] else "",
                         f"unit_{row['id']}": row["unit"], f"keywords_{row['id']}": row["keywords"], f"kind_{row['id']}": row["kind"],
                         f"service_{row['id']}": str(row["service_id"] or ""), f"published_{row['id']}": "1"})
        form[f"from_{exam['id']}"] = "700"
        self.assertEqual(c.post("/staff/admin/prices", data=form).status_code, 302)
        self.assertEqual(self.q("SELECT price_from_cents FROM price_items WHERE id = ?", (exam["id"],))["price_from_cents"], 70000)
        self.assertEqual({p["name"]: p for p in self._info()["prices"]}["Dental examination (check-up)"]["amount"], "₱700")
        # hide / show
        self.assertEqual(self.login("reception.malolos").post("/staff/admin/prices", data={"action": "visibility", "show": "0"}).status_code, 403)
        c.post("/staff/admin/prices", data={"action": "visibility", "show": "0"})
        self.assertEqual(self._info()["prices"], [])
        # a sample price blocks showing prices again
        self.conn.insert("price_items", {"name": "Dummy", "price_from_cents": 100, "sample": 1, "published": 1, "updated_at": "x"})
        r = c.post("/staff/admin/prices", data={"action": "visibility", "show": "1", "confirm": "1"}, follow_redirects=True)
        self.assertIn(b"still sample prices", r.data)
        self.conn.execute("DELETE FROM price_items WHERE name = 'Dummy'")
        c.post("/staff/admin/prices", data={"action": "visibility", "show": "1", "confirm": "1"})
        self.conn.execute("UPDATE price_items SET price_from_cents = 65000 WHERE id = ?", (exam["id"],))
        self.assertTrue(self._info()["prices"])
