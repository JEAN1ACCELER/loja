import tempfile
import unittest
from pathlib import Path

import app as store


class StoreAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        store.DATABASE = Path(self.temp_dir.name) / "test.db"
        store.init_db()
        store.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = store.app.test_client()
        self.client.get("/login")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        self.client.post(
            "/login",
            data={"csrf_token": token, "email": "admin@loja.local", "password": "admin123"},
        )
        self.client.get("/")
        with self.client.session_transaction() as session:
            self.csrf = session["csrf_token"]

    def tearDown(self):
        self.temp_dir.cleanup()

    def post(self, path, data):
        return self.client.post(path, data={"csrf_token": self.csrf, **data}, follow_redirects=True)

    def add_product(self, stock="8"):
        return self.post(
            "/products/new",
            {
                "name": "Cimento CP-II",
                "sku": "CIM-001",
                "category": "Cimentos",
                "unit": "saco",
                "cost": "25.00",
                "price": "35.50",
                "stock": stock,
                "minimum_stock": "2",
            },
        )

    def test_product_crud_and_search(self):
        self.add_product()
        with store.get_db() as db:
            product_id = db.execute("SELECT id FROM products").fetchone()["id"]
        self.assertIn("Cimento CP-II", self.client.get("/products?q=CIM-001").get_data(as_text=True))
        self.post(
            f"/products/{product_id}/edit",
            {
                "name": "Cimento CP-II reformulado",
                "sku": "CIM-001",
                "category": "Cimentos",
                "unit": "saco",
                "cost": "26.00",
                "price": "37.00",
                "stock": "9",
                "minimum_stock": "3",
            },
        )
        with store.get_db() as db:
            self.assertEqual(db.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()[0], 9)
        response = self.post(f"/products/{product_id}/delete", {})
        self.assertNotIn("Cimento CP-II reformulado", response.get_data(as_text=True))

    def test_sale_reduces_stock_and_rejects_over_sale(self):
        self.add_product(stock="5")
        self.assertEqual(self.client.get("/sales/new").status_code, 200)
        with store.get_db() as db:
            product_id = db.execute("SELECT id FROM products").fetchone()["id"]
        data = {
            "product_id[]": [str(product_id)],
            "quantity[]": ["3"],
            "payment_method": "PIX",
        }
        response = self.post("/sales/new", data)
        self.assertIn("Venda #1 registrada com sucesso.", response.get_data(as_text=True))
        with store.get_db() as db:
            self.assertEqual(db.execute("SELECT stock FROM products").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT total FROM sales").fetchone()[0], 106.5)
        data["quantity[]"] = ["3"]
        response = self.post("/sales/new", data)
        self.assertIn("Estoque insuficiente", response.get_data(as_text=True))
        with store.get_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT stock FROM products").fetchone()[0], 2)

    def test_team_permissions_and_csrf_protection(self):
        response = self.post(
            "/team/new",
            {
                "name": "João Vendedor",
                "email": "joao@loja.local",
                "phone": "11999990000",
                "role": "seller",
                "password": "segura123",
            },
        )
        self.assertIn("João Vendedor", response.get_data(as_text=True))
        self.assertEqual(self.client.post("/products/new", data={}).status_code, 400)
        self.assertIn(
            "Não é possível remover a função do último administrador ativo.",
            self.post(
                "/team/1/edit",
                {
                    "name": "Administrador",
                    "email": "admin@loja.local",
                    "phone": "",
                    "role": "seller",
                    "password": "",
                },
            ).get_data(as_text=True),
        )

        seller_client = store.app.test_client()
        seller_client.get("/login")
        with seller_client.session_transaction() as session:
            token = session["csrf_token"]
        seller_client.post(
            "/login",
            data={"csrf_token": token, "email": "joao@loja.local", "password": "segura123"},
        )
        self.assertEqual(seller_client.get("/team").status_code, 403)

    def test_user_can_change_own_password(self):
        response = self.post(
            "/account/password",
            {
                "current_password": "admin123",
                "new_password": "nova-senha-forte-123",
                "confirm_password": "nova-senha-forte-123",
            },
        )
        self.assertIn("Senha alterada com sucesso.", response.get_data(as_text=True))
        with store.get_db() as db:
            password_hash = db.execute(
                "SELECT password_hash FROM users WHERE email='admin@loja.local'"
            ).fetchone()["password_hash"]
        self.assertTrue(store.check_password_hash(password_hash, "nova-senha-forte-123"))
        self.assertFalse(store.check_password_hash(password_hash, "admin123"))


if __name__ == "__main__":
    unittest.main()
