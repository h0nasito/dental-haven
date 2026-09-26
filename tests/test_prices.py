"""Price list: sample prices never reach patients on the live site until the clinic confirms real prices."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestPrices(Base):
    def _info(self):
        return self.app.test_client().get("/chat/info.json").get_json()

    def test_samples_hidden_on_live_and_labelled_on_demo(self):
        self.assertTrue(self.conn.scalar("SELECT COUNT(*) FROM price_items WHERE sample = 1") > 20)
        self.assertEqual(self._info()["prices"], [])
        self.app.config["APP_ENV"] = "demo"
        try:
            prices = self._info()["prices"]
        finally:
            self.app.config["APP_ENV"] = "development"
        self.assertTrue(prices)
        self.assertTrue(all(p["sample"] for p in prices))  # demo, not confirmed: always labelled as samples
        self.assertTrue(all(p["amount"].startswith("₱") for p in prices))

    def test_admin_edit_and_confirm(self):
        c = self.login("admin")
        page = c.get("/staff/admin/prices").data.decode()
        self.assertIn("sample prices for testing only", page)
        self.assertIn("Hidden from patients", page)
        # can't show while sample prices are published
        r = c.post("/staff/admin/prices", data={"action": "visibility", "show": "1", "confirm": "1"}, follow_redirects=True)
        self.assertIn(b"still sample prices", r.data)
        rows = self.conn.all("SELECT * FROM price_items")
        form = {"action": "save"}
        for row in rows:
            form.update({f"name_{row['id']}": row["name"], f"from_{row['id']}": str(row["price_from_cents"] // 100),
                         f"to_{row['id']}": str(row["price_to_cents"] // 100) if row["price_to_cents"] else "",
                         f"unit_{row['id']}": row["unit"], f"keywords_{row['id']}": row["keywords"],
                         f"service_{row['id']}": str(row["service_id"] or "")})
        veneer = next(r for r in rows if r["name"] == "Composite veneers")
        form[f"from_{veneer['id']}"] = "3,500"          # a real price typed in → no longer a sample
        form[f"published_{veneer['id']}"] = "1"         # every other row unticked → hidden
        form.update({"name_new": "Night guard", "from_new": "5000", "keywords_new": "night guard, bruxism"})
        self.assertEqual(c.post("/staff/admin/prices", data=form).status_code, 302)
        v = self.q("SELECT * FROM price_items WHERE id = ?", (veneer["id"],))
        self.assertEqual((v["price_from_cents"], v["sample"], v["published"]), (350000, 0, 1))
        self.assertEqual(self.q("SELECT sample, published FROM price_items WHERE name = 'Night guard'")["sample"], 0)
        # needs the confirmation tick, then shows
        r = c.post("/staff/admin/prices", data={"action": "visibility", "show": "1"}, follow_redirects=True)
        self.assertIn(b"Tick the box", r.data)
        c.post("/staff/admin/prices", data={"action": "visibility", "show": "1", "confirm": "1"})
        names = {p["name"]: p for p in self._info()["prices"]}
        self.assertEqual(set(names), {"Composite veneers", "Night guard"})
        self.assertFalse(names["Composite veneers"]["sample"])
        self.assertEqual(names["Composite veneers"]["amount"], "₱3,500")
        # only super admin can switch visibility
        self.assertEqual(self.login("reception.malolos").post("/staff/admin/prices", data={"action": "visibility", "show": "0"}).status_code, 403)
        c.post("/staff/admin/prices", data={"action": "visibility", "show": "0"})
        self.assertEqual(self._info()["prices"], [])
