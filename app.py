import math
import os
import secrets
import sqlite3
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("DATABASE_PATH", str(BASE_DIR / "loja.db"))).resolve()

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


@contextmanager
def get_db():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db():
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'seller')),
                phone TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sku TEXT NOT NULL UNIQUE COLLATE NOCASE,
                category TEXT NOT NULL,
                unit TEXT NOT NULL,
                cost REAL NOT NULL CHECK (cost >= 0),
                price REAL NOT NULL CHECK (price >= 0),
                stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
                minimum_stock INTEGER NOT NULL DEFAULT 0 CHECK (minimum_stock >= 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES users(id),
                total REAL NOT NULL CHECK (total >= 0),
                payment_method TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
                product_id INTEGER NOT NULL REFERENCES products(id),
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                unit_price REAL NOT NULL CHECK (unit_price >= 0),
                subtotal REAL NOT NULL CHECK (subtotal >= 0)
            );
            """
        )
        if not db.execute("SELECT id FROM users LIMIT 1").fetchone():
            initial_password = os.environ.get("INITIAL_ADMIN_PASSWORD", "admin123")
            db.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
                ("Administrador", "admin@loja.local", generate_password_hash(initial_password), "admin"),
            )


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped


@app.before_request
def protect_post_requests():
    if request.method == "POST":
        token = session.get("csrf_token")
        submitted = request.form.get("csrf_token")
        if not token or not submitted or not secrets.compare_digest(token, submitted):
            abort(400, description="Token de segurança inválido. Atualize a página e tente novamente.")


@app.context_processor
def inject_template_values():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {"current_user": session.get("user_name"), "user_role": session.get("role")}


@app.template_filter("currency")
def currency(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@app.route("/")
@login_required
def dashboard():
    with get_db() as db:
        summary = {
            "products": db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
            "team": db.execute("SELECT COUNT(*) FROM users WHERE active = 1").fetchone()[0],
            "sales_today": db.execute(
                "SELECT COUNT(*) FROM sales WHERE date(created_at, 'localtime') = date('now', 'localtime')"
            ).fetchone()[0],
            "revenue_today": db.execute(
                "SELECT COALESCE(SUM(total), 0) FROM sales "
                "WHERE date(created_at, 'localtime') = date('now', 'localtime')"
            ).fetchone()[0],
        }
        low_stock = db.execute(
            "SELECT * FROM products WHERE stock <= minimum_stock ORDER BY stock, name LIMIT 6"
        ).fetchall()
        recent_sales = db.execute(
            """SELECT sales.*, users.name AS seller_name
               FROM sales JOIN users ON users.id = sales.seller_id
               ORDER BY sales.id DESC LIMIT 5"""
        ).fetchall()
    return render_template("dashboard.html", summary=summary, low_stock=low_stock, recent_sales=recent_sales)


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        with get_db() as db:
            user = db.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE AND active = 1", (email,)
            ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["role"] = user["role"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            return redirect(url_for("dashboard"))
        flash("E-mail ou senha inválidos.", "error")
    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/account/password", methods=["GET", "POST"])
@login_required
def account_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        with get_db() as db:
            user = db.execute(
                "SELECT password_hash FROM users WHERE id=? AND active=1",
                (session["user_id"],),
            ).fetchone()
            if not user or not check_password_hash(user["password_hash"], current_password):
                flash("A senha atual está incorreta.", "error")
            elif len(new_password) < 12:
                flash("A nova senha deve ter pelo menos 12 caracteres.", "error")
            elif new_password != confirm_password:
                flash("A confirmação da nova senha não corresponde.", "error")
            else:
                db.execute(
                    "UPDATE users SET password_hash=? WHERE id=?",
                    (generate_password_hash(new_password), session["user_id"]),
                )
                flash("Senha alterada com sucesso.", "success")
                return redirect(url_for("dashboard"))
    return render_template("account_password.html")


@app.route("/products")
@login_required
def products():
    search = request.args.get("q", "").strip()
    with get_db() as db:
        rows = db.execute(
            """SELECT * FROM products
               WHERE name LIKE ? OR sku LIKE ? OR category LIKE ?
               ORDER BY name""",
            (f"%{search}%", f"%{search}%", f"%{search}%"),
        ).fetchall()
    return render_template("products.html", products=rows, search=search)


def product_values(form):
    name = form.get("name", "").strip()
    sku = form.get("sku", "").strip()
    category = form.get("category", "").strip()
    unit = form.get("unit", "").strip()
    if not all((name, sku, category, unit)):
        raise ValueError("Preencha todos os campos obrigatórios.")
    try:
        cost = float(form.get("cost", ""))
        price = float(form.get("price", ""))
        stock = int(form.get("stock", ""))
        minimum_stock = int(form.get("minimum_stock", ""))
    except ValueError as exc:
        raise ValueError("Informe valores numéricos válidos para custos, preços e estoque.") from exc
    if not math.isfinite(cost) or not math.isfinite(price):
        raise ValueError("Informe valores monetários válidos.")
    if cost < 0 or price < 0 or stock < 0 or minimum_stock < 0:
        raise ValueError("Os valores não podem ser negativos.")
    return (name, sku, category, unit, cost, price, stock, minimum_stock)


@app.route("/products/new", methods=["GET", "POST"])
@login_required
def product_new():
    if request.method == "POST":
        try:
            values = product_values(request.form)
            with get_db() as db:
                db.execute(
                    """INSERT INTO products
                       (name, sku, category, unit, cost, price, stock, minimum_stock)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    values,
                )
            flash("Produto cadastrado com sucesso.", "success")
            return redirect(url_for("products"))
        except ValueError as exc:
            flash(str(exc), "error")
        except sqlite3.IntegrityError:
            flash("Já existe um produto com esse código SKU.", "error")
    return render_template("product_form.html", product=None)


@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def product_edit(product_id):
    with get_db() as db:
        product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        abort(404)
    if request.method == "POST":
        try:
            values = product_values(request.form)
            with get_db() as db:
                db.execute(
                    """UPDATE products SET name=?, sku=?, category=?, unit=?, cost=?, price=?,
                       stock=?, minimum_stock=? WHERE id=?""",
                    (*values, product_id),
                )
            flash("Produto atualizado com sucesso.", "success")
            return redirect(url_for("products"))
        except ValueError as exc:
            flash(str(exc), "error")
        except sqlite3.IntegrityError:
            flash("Já existe outro produto com esse código SKU.", "error")
    return render_template("product_form.html", product=product)


@app.post("/products/<int:product_id>/delete")
@login_required
def product_delete(product_id):
    with get_db() as db:
        try:
            db.execute("DELETE FROM products WHERE id = ?", (product_id,))
            flash("Produto excluído.", "success")
        except sqlite3.IntegrityError:
            flash("Este produto possui vendas registradas e não pode ser excluído.", "error")
    return redirect(url_for("products"))


@app.route("/team")
@admin_required
def team():
    with get_db() as db:
        users = db.execute("SELECT * FROM users ORDER BY active DESC, name").fetchall()
    return render_template("team.html", users=users)


def user_values(form, existing=None):
    name = form.get("name", "").strip()
    email = form.get("email", "").strip()
    phone = form.get("phone", "").strip()
    role = form.get("role", "")
    password = form.get("password", "")
    if not name or not email or role not in ("admin", "seller"):
        raise ValueError("Informe nome, e-mail e uma função válida.")
    if not existing and len(password) < 8:
        raise ValueError("A senha deve ter pelo menos 8 caracteres.")
    if password and len(password) < 8:
        raise ValueError("A nova senha deve ter pelo menos 8 caracteres.")
    return name, email, phone, role, password


@app.route("/team/new", methods=["GET", "POST"])
@admin_required
def user_new():
    if request.method == "POST":
        try:
            name, email, phone, role, password = user_values(request.form)
            with get_db() as db:
                db.execute(
                    """INSERT INTO users (name, email, phone, role, password_hash)
                       VALUES (?, ?, ?, ?, ?)""",
                    (name, email, phone, role, generate_password_hash(password)),
                )
            flash("Usuário cadastrado com sucesso.", "success")
            return redirect(url_for("team"))
        except ValueError as exc:
            flash(str(exc), "error")
        except sqlite3.IntegrityError:
            flash("Já existe um usuário com esse e-mail.", "error")
    return render_template("user_form.html", user=None)


@app.route("/team/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def user_edit(user_id):
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        abort(404)
    if request.method == "POST":
        try:
            name, email, phone, role, password = user_values(request.form, user)
            if user["active"] and user["role"] == "admin" and role != "admin":
                with get_db() as db:
                    admin_count = db.execute(
                        "SELECT COUNT(*) FROM users WHERE role='admin' AND active=1"
                    ).fetchone()[0]
                if admin_count <= 1:
                    raise ValueError("Não é possível remover a função do último administrador ativo.")
            with get_db() as db:
                if password:
                    db.execute(
                        """UPDATE users SET name=?, email=?, phone=?, role=?, password_hash=?
                           WHERE id=?""",
                        (name, email, phone, role, generate_password_hash(password), user_id),
                    )
                else:
                    db.execute(
                        "UPDATE users SET name=?, email=?, phone=?, role=? WHERE id=?",
                        (name, email, phone, role, user_id),
                    )
            if user_id == session["user_id"]:
                session["user_name"] = name
                session["role"] = role
            flash("Usuário atualizado com sucesso.", "success")
            return redirect(url_for("team"))
        except ValueError as exc:
            flash(str(exc), "error")
        except sqlite3.IntegrityError:
            flash("Já existe outro usuário com esse e-mail.", "error")
    return render_template("user_form.html", user=user)


@app.post("/team/<int:user_id>/toggle")
@admin_required
def user_toggle(user_id):
    if user_id == session["user_id"]:
        flash("Você não pode desativar a própria conta.", "error")
        return redirect(url_for("team"))
    with get_db() as db:
        user = db.execute("SELECT role, active FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            abort(404)
        if user["role"] == "admin" and user["active"]:
            admin_count = db.execute(
                "SELECT COUNT(*) FROM users WHERE role='admin' AND active=1"
            ).fetchone()[0]
            if admin_count <= 1:
                flash("Não é possível desativar o último administrador ativo.", "error")
                return redirect(url_for("team"))
        db.execute("UPDATE users SET active = 1 - active WHERE id = ?", (user_id,))
    flash("Status do usuário atualizado.", "success")
    return redirect(url_for("team"))


@app.route("/sales")
@login_required
def sales():
    with get_db() as db:
        rows = db.execute(
            """SELECT sales.*, users.name AS seller_name
               FROM sales JOIN users ON users.id = sales.seller_id
               ORDER BY sales.id DESC LIMIT 100"""
        ).fetchall()
    return render_template("sales.html", sales=rows)


@app.route("/sales/new", methods=["GET", "POST"])
@login_required
def sale_new():
    with get_db() as db:
        available_products = db.execute(
            "SELECT id, name, sku, price, stock, unit FROM products WHERE stock > 0 ORDER BY name"
        ).fetchall()
        sellers = db.execute(
            "SELECT id, name FROM users WHERE role='seller' AND active=1 ORDER BY name"
        ).fetchall()
    if request.method == "POST":
        product_ids = request.form.getlist("product_id[]")
        quantities = request.form.getlist("quantity[]")
        payment = request.form.get("payment_method", "")
        seller_id = session["user_id"]
        if session.get("role") == "admin":
            try:
                seller_id = int(request.form.get("seller_id", seller_id))
            except ValueError:
                flash("Selecione um vendedor válido.", "error")
                return render_template("sale_form.html", products=available_products, sellers=sellers)
        if payment not in ("Dinheiro", "PIX", "Cartão de débito", "Cartão de crédito"):
            flash("Selecione uma forma de pagamento válida.", "error")
            return render_template("sale_form.html", products=available_products, sellers=sellers)
        try:
            if not product_ids or len(product_ids) != len(quantities):
                raise ValueError("Adicione pelo menos um produto à venda.")
            requested = {}
            for product_id, quantity in zip(product_ids, quantities):
                product_id = int(product_id)
                quantity = int(quantity)
                if quantity < 1:
                    raise ValueError("A quantidade deve ser maior que zero.")
                requested[product_id] = requested.get(product_id, 0) + quantity
            with get_db() as db:
                seller = db.execute(
                    "SELECT id FROM users WHERE id=? AND active=1 AND role IN ('admin','seller')",
                    (seller_id,),
                ).fetchone()
                if not seller:
                    raise ValueError("O vendedor selecionado não está ativo.")
                lines = []
                total = 0.0
                for product_id, quantity in requested.items():
                    product = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
                    if not product:
                        raise ValueError("Um dos produtos selecionados não existe.")
                    if quantity > product["stock"]:
                        raise ValueError(f"Estoque insuficiente para {product['name']}.")
                    subtotal = round(product["price"] * quantity, 2)
                    total += subtotal
                    lines.append((product, quantity, subtotal))
                cursor = db.execute(
                    "INSERT INTO sales (seller_id, total, payment_method) VALUES (?, ?, ?)",
                    (seller_id, round(total, 2), payment),
                )
                sale_id = cursor.lastrowid
                for product, quantity, subtotal in lines:
                    db.execute(
                        """INSERT INTO sale_items
                           (sale_id, product_id, product_name, quantity, unit_price, subtotal)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (sale_id, product["id"], product["name"], quantity, product["price"], subtotal),
                    )
                    updated = db.execute(
                        "UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?",
                        (quantity, product["id"], quantity),
                    )
                    if updated.rowcount != 1:
                        raise ValueError(f"Estoque insuficiente para {product['name']}.")
            flash(f"Venda #{sale_id} registrada com sucesso.", "success")
            return redirect(url_for("sale_detail", sale_id=sale_id))
        except (ValueError, TypeError) as exc:
            flash(str(exc) or "Dados da venda inválidos.", "error")
        except sqlite3.IntegrityError as exc:
            flash(f"Não foi possível registrar a venda: {exc}.", "error")
        with get_db() as db:
            available_products = db.execute(
                "SELECT id, name, sku, price, stock, unit FROM products WHERE stock > 0 ORDER BY name"
            ).fetchall()
    return render_template("sale_form.html", products=available_products, sellers=sellers)


@app.route("/sales/<int:sale_id>")
@login_required
def sale_detail(sale_id):
    with get_db() as db:
        sale = db.execute(
            """SELECT sales.*, users.name AS seller_name
               FROM sales JOIN users ON users.id=sales.seller_id WHERE sales.id=?""",
            (sale_id,),
        ).fetchone()
        if not sale:
            abort(404)
        items = db.execute("SELECT * FROM sale_items WHERE sale_id=? ORDER BY id", (sale_id,)).fetchall()
    return render_template("sale_detail.html", sale=sale, items=items)


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403, message="Você não tem permissão para acessar esta página."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="A página ou registro solicitado não foi encontrado."), 404


@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", code=400, message=error.description or "Solicitação inválida."), 400


init_db()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
