"""
Olivarda — Zeytinyağı Alım ve Cari Takip Uygulaması
=====================================================
Streamlit tabanlı, SQLite veritabanı kullanan web uygulaması.

Özellikler:
 • Kurumsal kimlik (Olivarda / Erengül Zeytinyağı)
 • Güvenli giriş + "Beni Hatırla" (cookie token, 30 gün)
 • Müşteri yönetimi (aktif / pasif filtreleme)
 • Yağ alım kaydı (fotoğraf + kamera desteği)
 • Ödeme takibi (makbuz fotoğraf + kamera)
 • Depo & satış (asit bazlı stok, expander detaylar)
 • Müşteri detay (cari hesap özeti)
 • Kullanıcı yönetimi & işlem loglama (created_by)
 • Mobil uyumlu buton-tabanlı sidebar menü
 • Flash message sistemi (kayıt sonrası otomatik yenileme)
"""

import streamlit as st
import sqlite3
import os
import hashlib
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
import extra_streamlit_components as stx

# ============================================================
# YAPILANDIRMA
# ============================================================
DB_PATH = "olivearda.db"
UPLOAD_DIR = "uploads"
DEFAULT_USER = "admin"
DEFAULT_PASS = "1234"
TOKEN_EXPIRY_DAYS = 30

st.set_page_config(
    page_title="Olivarda | Erengül Zeytinyağı",
    page_icon="🫒",
    layout="wide",
    initial_sidebar_state="collapsed",
)

OLIVE_GREEN = "#6B8E23"
OLIVE_DARK = "#556B2F"

# ============================================================
# GLOBAL CSS
# ============================================================
st.markdown(f"""
<style>
/* --- Kurumsal Logo / Başlık --- */
.brand-header {{
    text-align: center;
    padding: 8px 0 4px 0;
}}
.brand-name {{
    font-size: 1.65rem;
    font-weight: 800;
    color: {OLIVE_GREEN};
    letter-spacing: 1.5px;
    line-height: 1.2;
}}
.brand-subtitle {{
    font-size: 0.72rem;
    color: #6c757d;
    font-weight: 500;
    letter-spacing: 0.3px;
    margin-top: 2px;
}}
.brand-divider {{
    width: 50px;
    height: 3px;
    background: {OLIVE_GREEN};
    border-radius: 2px;
    margin: 8px auto 0 auto;
}}
/* --- Footer --- */
.sidebar-footer {{
    text-align: center;
    font-size: 0.65rem;
    color: #adb5bd;
    padding: 12px 0 4px 0;
    border-top: 1px solid #e9ecef;
    margin-top: 16px;
}}
/* --- KPI Kartları --- */
.kpi-grid {{
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin: 12px 0 20px 0;
}}
.kpi-card {{
    flex: 1 1 180px;
    max-width: 100%;
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-top: 3px solid {OLIVE_GREEN};
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    transition: box-shadow 0.2s ease;
}}
.kpi-card:hover {{
    box-shadow: 0 3px 12px rgba(0,0,0,0.10);
}}
.kpi-label {{
    font-size: 0.78rem;
    color: #6c757d;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    font-weight: 600;
    margin-bottom: 4px;
}}
.kpi-value {{
    font-size: 1.45rem;
    font-weight: 700;
    color: #212529;
    line-height: 1.2;
}}
.kpi-value.positive {{ color: #198754; }}
.kpi-value.negative {{ color: #dc3545; }}
.kpi-value.info     {{ color: {OLIVE_GREEN}; }}
.kpi-value.warning  {{ color: #e67e22; }}
@media (max-width: 640px) {{
    .kpi-card  {{ flex: 1 1 100%; }}
    .kpi-value {{ font-size: 1.25rem; }}
}}
/* --- Sidebar Menü Buton Stilleri --- */
[data-testid="stSidebar"] .stButton > button {{
    width: 100%;
    text-align: left !important;
    justify-content: flex-start !important;
    padding: 14px 16px !important;
    margin-bottom: 4px !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    border: 1px solid transparent !important;
    border-radius: 10px !important;
    background: transparent !important;
    color: #495057 !important;
    transition: all 0.2s ease !important;
    min-height: 48px !important;
    line-height: 1.3 !important;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
    background: rgba(107,142,35,0.08) !important;
    border-color: rgba(107,142,35,0.2) !important;
    color: {OLIVE_GREEN} !important;
}}
[data-testid="stSidebar"] .stButton > button:active,
[data-testid="stSidebar"] .stButton > button:focus {{
    background: rgba(107,142,35,0.12) !important;
    border-color: {OLIVE_GREEN} !important;
    color: {OLIVE_GREEN} !important;
    box-shadow: none !important;
}}
</style>
""", unsafe_allow_html=True)


# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================

def get_cookie_manager():
    """session_state'te saklanan tek CookieManager instance'ını döndürür."""
    return st.session_state.get("_cookie_manager")


def render_kpi_cards(cards: list):
    """cards: [{icon, label, value, color}, ...]  color: positive|negative|info|warning|''"""
    html = '<div class="kpi-grid">'
    for c in cards:
        cls = c.get("color", "")
        html += (
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{c.get("icon","")} {c["label"]}</div>'
            f'<div class="kpi-value {cls}">{c["value"]}</div>'
            f'</div>'
        )
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def show_flash_message():
    """session_state'te bekleyen flash mesajı gösterir ve temizler."""
    if "flash_success" in st.session_state:
        st.success(st.session_state.pop("flash_success"))
    if "flash_error" in st.session_state:
        st.error(st.session_state.pop("flash_error"))


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def format_currency(amount: float) -> str:
    return f"₺{amount:,.2f}"


def format_kg(kg: float) -> str:
    return f"{kg:,.1f} kg"


def save_uploaded_file(uploaded_file, subfolder: str = "") -> str:
    if uploaded_file is None:
        return ""
    target_dir = os.path.join(UPLOAD_DIR, subfolder)
    os.makedirs(target_dir, exist_ok=True)
    ext = Path(uploaded_file.name).suffix if hasattr(uploaded_file, "name") else ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(target_dir, filename)
    with open(filepath, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return filepath


def save_camera_photo(camera_data, subfolder: str = "") -> str:
    if camera_data is None:
        return ""
    target_dir = os.path.join(UPLOAD_DIR, subfolder)
    os.makedirs(target_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = os.path.join(target_dir, filename)
    with open(filepath, "wb") as f:
        f.write(camera_data.getbuffer())
    return filepath


# ============================================================
# VERİTABANI BAŞLATMA
# ============================================================

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS customers (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            phone      TEXT,
            address    TEXT,
            durum      INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS oil_purchases (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id   INTEGER NOT NULL,
            purchase_date DATE NOT NULL,
            kg            REAL NOT NULL,
            acidity       REAL,
            unit_price    REAL NOT NULL,
            total_amount  REAL NOT NULL,
            note          TEXT,
            photo_path    TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by    TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS payments (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id   INTEGER NOT NULL,
            payment_date  DATE NOT NULL,
            amount        REAL NOT NULL,
            payment_type  TEXT NOT NULL,
            note          TEXT,
            receipt_photo TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by    TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS sales (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_date     DATE NOT NULL,
            buyer_company TEXT NOT NULL,
            acidity       REAL NOT NULL,
            kg            REAL NOT NULL,
            unit_price    REAL NOT NULL,
            total_amount  REAL NOT NULL,
            note          TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by    TEXT
        );
        CREATE TABLE IF NOT EXISTS auth_tokens (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            token      TEXT UNIQUE NOT NULL,
            username   TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Eski veritabanı uyumluluğu — durum sütunu yoksa ekle
    try:
        cur.execute("ALTER TABLE customers ADD COLUMN durum INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass

    # Varsayılan admin kullanıcısı (ilk kurulumda)
    if not cur.execute("SELECT 1 FROM users WHERE username=?", (DEFAULT_USER,)).fetchone():
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (?,?)",
            (DEFAULT_USER, hash_password(DEFAULT_PASS)),
        )

    conn.commit()
    conn.close()


# ============================================================
# AUTH TOKEN İŞLEMLERİ
# ============================================================

def create_auth_token(username: str) -> str:
    token = uuid.uuid4().hex
    expires = datetime.now() + timedelta(days=TOKEN_EXPIRY_DAYS)
    conn = get_db()
    conn.execute(
        "INSERT INTO auth_tokens (token, username, expires_at) VALUES (?,?,?)",
        (token, username, expires.isoformat()),
    )
    conn.commit()
    conn.close()
    return token


def verify_auth_token(token: str):
    if not token:
        return None
    conn = get_db()
    row = conn.execute(
        "SELECT username, expires_at FROM auth_tokens WHERE token=?", (token,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    if datetime.now() > datetime.fromisoformat(row["expires_at"]):
        delete_auth_token(token)
        return None
    return row["username"]


def delete_auth_token(token: str):
    if not token:
        return
    conn = get_db()
    conn.execute("DELETE FROM auth_tokens WHERE token=?", (token,))
    conn.commit()
    conn.close()


def delete_user_tokens(username: str):
    conn = get_db()
    conn.execute("DELETE FROM auth_tokens WHERE username=?", (username,))
    conn.commit()
    conn.close()


def cleanup_expired_tokens():
    conn = get_db()
    conn.execute("DELETE FROM auth_tokens WHERE expires_at < ?", (datetime.now().isoformat(),))
    conn.commit()
    conn.close()


# ============================================================
# VERİTABANI SORGULARI — KULLANICILAR
# ============================================================

def get_users():
    conn = get_db()
    rows = conn.execute("SELECT id, username, created_at FROM users ORDER BY username").fetchall()
    conn.close()
    return rows


def add_user(username, password):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?,?)",
            (username, hash_password(password)),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def change_password(user_id, new_password):
    conn = get_db()
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(new_password), user_id))
    conn.commit()
    conn.close()


def delete_user(user_id):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()


# ============================================================
# VERİTABANI SORGULARI — MÜŞTERİLER
# ============================================================

def add_customer(name, phone, address):
    conn = get_db()
    conn.execute("INSERT INTO customers (name,phone,address) VALUES (?,?,?)", (name, phone, address))
    conn.commit()
    conn.close()


def get_customers(only_active=False):
    conn = get_db()
    sql = "SELECT * FROM customers WHERE durum=1 ORDER BY name" if only_active else "SELECT * FROM customers ORDER BY name"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return rows


def delete_customer(customer_id):
    conn = get_db()
    conn.execute("DELETE FROM customers WHERE id=?", (customer_id,))
    conn.commit()
    conn.close()


def toggle_customer_status(customer_id, current_status):
    new_status = 0 if current_status == 1 else 1
    conn = get_db()
    conn.execute("UPDATE customers SET durum=? WHERE id=?", (new_status, customer_id))
    conn.commit()
    conn.close()


# ============================================================
# VERİTABANI SORGULARI — YAĞ ALIM
# ============================================================

def add_oil_purchase(customer_id, purchase_date, kg, acidity, unit_price, total_amount, note, photo_path, created_by):
    conn = get_db()
    conn.execute(
        """INSERT INTO oil_purchases
           (customer_id, purchase_date, kg, acidity, unit_price, total_amount, note, photo_path, created_by)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (customer_id, purchase_date, kg, acidity, unit_price, total_amount, note, photo_path, created_by),
    )
    conn.commit()
    conn.close()


def get_oil_purchases(customer_id=None):
    conn = get_db()
    if customer_id:
        rows = conn.execute(
            """SELECT op.*, c.name AS customer_name
               FROM oil_purchases op JOIN customers c ON op.customer_id=c.id
               WHERE op.customer_id=? ORDER BY op.purchase_date DESC""",
            (customer_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT op.*, c.name AS customer_name
               FROM oil_purchases op JOIN customers c ON op.customer_id=c.id
               ORDER BY op.purchase_date DESC"""
        ).fetchall()
    conn.close()
    return rows


def delete_oil_purchase(purchase_id):
    conn = get_db()
    conn.execute("DELETE FROM oil_purchases WHERE id=?", (purchase_id,))
    conn.commit()
    conn.close()


# ============================================================
# VERİTABANI SORGULARI — ÖDEMELER
# ============================================================

def add_payment(customer_id, payment_date, amount, payment_type, note, receipt_photo, created_by):
    conn = get_db()
    conn.execute(
        """INSERT INTO payments
           (customer_id, payment_date, amount, payment_type, note, receipt_photo, created_by)
           VALUES (?,?,?,?,?,?,?)""",
        (customer_id, payment_date, amount, payment_type, note, receipt_photo, created_by),
    )
    conn.commit()
    conn.close()


def get_payments(customer_id=None):
    conn = get_db()
    if customer_id:
        rows = conn.execute(
            """SELECT p.*, c.name AS customer_name
               FROM payments p JOIN customers c ON p.customer_id=c.id
               WHERE p.customer_id=? ORDER BY p.payment_date DESC""",
            (customer_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT p.*, c.name AS customer_name
               FROM payments p JOIN customers c ON p.customer_id=c.id
               ORDER BY p.payment_date DESC"""
        ).fetchall()
    conn.close()
    return rows


def delete_payment(payment_id):
    conn = get_db()
    conn.execute("DELETE FROM payments WHERE id=?", (payment_id,))
    conn.commit()
    conn.close()


# ============================================================
# VERİTABANI SORGULARI — SATIŞLAR
# ============================================================

def add_sale(sale_date, buyer_company, acidity, kg, unit_price, total_amount, note, created_by):
    conn = get_db()
    conn.execute(
        """INSERT INTO sales
           (sale_date, buyer_company, acidity, kg, unit_price, total_amount, note, created_by)
           VALUES (?,?,?,?,?,?,?,?)""",
        (sale_date, buyer_company, acidity, kg, unit_price, total_amount, note, created_by),
    )
    conn.commit()
    conn.close()


def get_sales():
    conn = get_db()
    rows = conn.execute("SELECT * FROM sales ORDER BY sale_date DESC").fetchall()
    conn.close()
    return rows


def delete_sale(sale_id):
    conn = get_db()
    conn.execute("DELETE FROM sales WHERE id=?", (sale_id,))
    conn.commit()
    conn.close()


# ============================================================
# VERİTABANI SORGULARI — İSTATİSTİKLER & STOK
# ============================================================

def get_acidity_details(acidity):
    conn = get_db()
    rows = conn.execute(
        """SELECT op.purchase_date, op.kg, c.name AS customer_name
           FROM oil_purchases op JOIN customers c ON op.customer_id=c.id
           WHERE op.acidity=? ORDER BY op.purchase_date DESC""",
        (acidity,),
    ).fetchall()
    conn.close()
    return rows


def get_stock_by_acidity():
    """Asit derecesine göre net stok: Alım − Satış."""
    conn = get_db()
    rows = conn.execute("""
        SELECT acidity,
               COALESCE(purchased,0) AS purchased,
               COALESCE(sold,0)      AS sold,
               COALESCE(purchased,0)-COALESCE(sold,0) AS net_stock
        FROM (
            SELECT acidity, SUM(kg) AS purchased
            FROM oil_purchases WHERE acidity IS NOT NULL AND acidity>0
            GROUP BY acidity
        ) p
        LEFT JOIN (
            SELECT acidity AS sa, SUM(kg) AS sold FROM sales GROUP BY acidity
        ) s ON p.acidity=s.sa

        UNION

        SELECT sa AS acidity,
               COALESCE(purchased,0) AS purchased,
               COALESCE(sold,0)      AS sold,
               COALESCE(purchased,0)-COALESCE(sold,0) AS net_stock
        FROM (
            SELECT acidity AS sa, SUM(kg) AS sold FROM sales GROUP BY acidity
        ) s2
        LEFT JOIN (
            SELECT acidity, SUM(kg) AS purchased
            FROM oil_purchases WHERE acidity IS NOT NULL AND acidity>0
            GROUP BY acidity
        ) p2 ON s2.sa=p2.acidity
        WHERE p2.acidity IS NULL

        ORDER BY acidity
    """).fetchall()
    conn.close()
    return rows


def get_available_stock(acidity_value: float) -> float:
    conn = get_db()
    purchased = conn.execute(
        "SELECT COALESCE(SUM(kg),0) AS t FROM oil_purchases WHERE acidity=?", (acidity_value,)
    ).fetchone()["t"]
    sold = conn.execute(
        "SELECT COALESCE(SUM(kg),0) AS t FROM sales WHERE acidity=?", (acidity_value,)
    ).fetchone()["t"]
    conn.close()
    return purchased - sold


def get_customer_summary():
    conn = get_db()
    rows = conn.execute("""
        SELECT c.id, c.name, c.phone, c.address, c.durum,
               COALESCE(SUM(op.kg),0)           AS total_kg,
               COALESCE(SUM(op.total_amount),0)  AS total_purchase_amount,
               COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.customer_id=c.id),0) AS total_paid,
               COALESCE(SUM(op.total_amount),0)
                 - COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.customer_id=c.id),0) AS balance
        FROM customers c
        LEFT JOIN oil_purchases op ON c.id=op.customer_id
        GROUP BY c.id
        ORDER BY c.name
    """).fetchall()
    conn.close()
    return rows


def get_dashboard_stats():
    conn = get_db()
    s = {}
    s["total_customers"] = conn.execute("SELECT COUNT(*) AS c FROM customers").fetchone()["c"]
    r = conn.execute("SELECT COALESCE(SUM(kg),0) AS kg, COALESCE(SUM(total_amount),0) AS amt FROM oil_purchases").fetchone()
    s["total_kg"] = r["kg"]
    s["total_purchase_amount"] = r["amt"]
    s["total_paid"] = conn.execute("SELECT COALESCE(SUM(amount),0) AS t FROM payments").fetchone()["t"]
    s["total_balance"] = s["total_purchase_amount"] - s["total_paid"]
    s["total_purchases"] = conn.execute("SELECT COUNT(*) AS c FROM oil_purchases").fetchone()["c"]
    s["total_sold_kg"] = conn.execute("SELECT COALESCE(SUM(kg),0) AS t FROM sales").fetchone()["t"]
    s["total_sale_amount"] = conn.execute("SELECT COALESCE(SUM(total_amount),0) AS t FROM sales").fetchone()["t"]
    s["net_stock_kg"] = s["total_kg"] - s["total_sold_kg"]
    conn.close()
    return s


# ============================================================
# SAYFA: GİRİŞ
# ============================================================

def render_login():
    cookie_manager = get_cookie_manager()

    st.markdown("""
    <div class="brand-header">
        <div class="brand-name">🫒 Olivarda</div>
        <div class="brand-subtitle">Erengül Zeytinyağı Ticareti</div>
        <div class="brand-divider"></div>
    </div>
    """, unsafe_allow_html=True)
    st.write("")
    st.divider()

    username = st.text_input("Kullanıcı Adı", placeholder="admin")
    password = st.text_input("Şifre", type="password", placeholder="••••")
    remember_me = st.checkbox("🔒 Beni Hatırla (30 gün)")

    if st.button("🚀 Giriş Yap", use_container_width=True):
        if not username or not password:
            st.error("Kullanıcı adı ve şifre boş bırakılamaz.")
            return
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password_hash=?",
            (username, hash_password(password)),
        ).fetchone()
        conn.close()
        if user:
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            if remember_me:
                token = create_auth_token(username)
                cookie_manager.set(
                    "olivarda_auth_token", token,
                    expires_at=datetime.now() + timedelta(days=TOKEN_EXPIRY_DAYS),
                )
            st.rerun()
        else:
            st.error("❌ Kullanıcı adı veya şifre hatalı!")

    st.info("Varsayılan giriş: **admin** / **1234**")


# ============================================================
# SAYFA: GENEL BAKIŞ
# ============================================================

def render_dashboard():
    st.header("📊 Genel Bakış")
    st.caption("Tüm işlemlerinizin özet görünümü")

    stats = get_dashboard_stats()

    render_kpi_cards([
        {"icon": "👥", "label": "Toplam Müşteri",      "value": stats["total_customers"],                          "color": "info"},
        {"icon": "🛢️", "label": "Toplam Alınan Yağ",   "value": format_kg(stats["total_kg"])},
        {"icon": "📦", "label": "Depoda Kalan Yağ",     "value": format_kg(stats["net_stock_kg"]),                  "color": "info"},
        {"icon": "💰", "label": "Toplam Hak Ediş",      "value": format_currency(stats["total_purchase_amount"]),   "color": "warning"},
        {"icon": "💸", "label": "Toplam Ödenen",         "value": format_currency(stats["total_paid"]),              "color": "positive"},
        {"icon": "📋", "label": "Kalan Bakiye",          "value": format_currency(stats["total_balance"]),
         "color": "negative" if stats["total_balance"] > 0 else "positive"},
        {"icon": "🏷️", "label": "Toplam Satış Geliri",  "value": format_currency(stats["total_sale_amount"]),       "color": "positive"},
    ])

    st.divider()

    st.subheader("🕐 Son Yağ Alımları")
    recent = get_oil_purchases()[:5]
    if recent:
        for p in recent:
            with st.container(border=True):
                st.write(f"**{p['customer_name']}** — {format_currency(p['total_amount'])}")
                st.caption(f"{p['purchase_date']} · {format_kg(p['kg'])} · Asit: %{p['acidity'] or '-'}")
    else:
        st.info("Henüz yağ alım kaydı yok.")

    st.subheader("💸 Son Ödemeler")
    recent_pay = get_payments()[:5]
    if recent_pay:
        for p in recent_pay:
            with st.container(border=True):
                st.write(f"**{p['customer_name']}** — {format_currency(p['amount'])}")
                st.caption(f"{p['payment_date']} · {p['payment_type']}")
    else:
        st.info("Henüz ödeme kaydı yok.")


# ============================================================
# SAYFA: MÜŞTERİLER
# ============================================================

def render_customers():
    st.header("👥 Müşteri Yönetimi")
    st.caption("Müşterilerinizi ekleyin ve cari hesaplarını takip edin")
    show_flash_message()

    tab_list, tab_new = st.tabs(["📋 Müşteri Listesi", "➕ Yeni Müşteri"])

    # --- LİSTE ---
    with tab_list:
        summaries = get_customer_summary()
        if not summaries:
            st.info("Henüz müşteri eklenmemiş. '➕ Yeni Müşteri' sekmesinden ekleyebilirsiniz.")
        else:
            search = st.text_input("🔍 Müşteri Ara", placeholder="İsim veya telefon ile arayın...")
            for row in summaries:
                if search:
                    q = search.lower()
                    if q not in row["name"].lower() and q not in (row["phone"] or "").lower():
                        continue

                balance = row["balance"]
                badge = (
                    f"🔴 Borç: {format_currency(balance)}" if balance > 0
                    else f"🟢 Alacak: {format_currency(abs(balance))}" if balance < 0
                    else "✅ Hesap Kapalı"
                )
                status_val = row["durum"] if row["durum"] is not None else 1
                status_text = "🟢 Aktif" if status_val == 1 else "🔴 Pasif"

                with st.container(border=True):
                    st.write(f"**{row['name']}**  ({status_text})")
                    st.caption(f"📞 {row['phone'] or '—'}  ·  📍 {row['address'] or '—'}")
                    st.write(badge)
                    st.caption(
                        f"🛢️ Yağ: {format_kg(row['total_kg'])}  ·  "
                        f"💰 Hak Ediş: {format_currency(row['total_purchase_amount'])}  ·  "
                        f"💸 Ödenen: {format_currency(row['total_paid'])}  ·  "
                        f"📋 Bakiye: {format_currency(balance)}"
                    )
                    if st.button("🔄 Durumu Değiştir", key=f"toggle_{row['id']}"):
                        toggle_customer_status(row["id"], status_val)
                        st.session_state["flash_success"] = f"✅ {row['name']} durumu güncellendi."
                        st.rerun()
                    if st.button("🗑️ Sil", key=f"del_cust_{row['id']}"):
                        delete_customer(row["id"])
                        st.session_state["flash_success"] = f"✅ {row['name']} silindi."
                        st.rerun()

    # --- YENİ MÜŞTERİ ---
    with tab_new:
        st.subheader("Yeni Müşteri Ekle")
        with st.form("new_customer_form", clear_on_submit=True):
            name    = st.text_input("Ad Soyad *", placeholder="Örn: Ahmet Yılmaz")
            phone   = st.text_input("Telefon",    placeholder="Örn: 0532 123 4567")
            address = st.text_input("Adres / Bölge", placeholder="Örn: Aydın / Germencik")
            if st.form_submit_button("✅ Müşteriyi Kaydet", use_container_width=True):
                if not name.strip():
                    st.error("Ad Soyad alanı zorunludur!")
                else:
                    add_customer(name.strip(), phone.strip(), address.strip())
                    st.session_state["flash_success"] = f"✅ **{name}** başarıyla eklendi!"
                    st.rerun()


# ============================================================
# SAYFA: YAĞ ALIMI
# ============================================================

def render_oil_purchase():
    st.header("🛢️ Yağ Alım Kaydı")
    st.caption("Müstahsilden gelen zeytinyağı alımlarını kaydedin")
    show_flash_message()

    tab_new, tab_history = st.tabs(["➕ Yeni Alım", "📋 Alım Geçmişi"])

    with tab_new:
        customers = get_customers(only_active=True)
        if not customers:
            st.warning("⚠️ Aktif müşteri bulunamadı! Lütfen önce aktif bir müşteri ekleyin.")
        else:
            cust_opts = {f"{c['name']} ({c['phone'] or 'Tel yok'})": c["id"] for c in customers}

            # Fotoğraf — form dışında (camera_input form içinde çalışmaz)
            st.subheader("📸 Fotoğraf (Opsiyonel)")
            photo_method = st.radio(
                "Yöntem", ["📁 Dosyadan Yükle", "📸 Kameradan Çek"],
                horizontal=True, key="oil_photo_method", label_visibility="collapsed",
            )
            photo_file = camera_photo = None
            if photo_method == "📁 Dosyadan Yükle":
                photo_file = st.file_uploader("Fotoğraf Seçin", type=["jpg","jpeg","png","webp"], key="oil_photo_file")
            else:
                camera_photo = st.camera_input("📸 Fotoğraf Çekin", key="oil_camera")
            st.divider()

            with st.form("new_oil_form", clear_on_submit=True):
                selected   = st.selectbox("Müşteri Seçin *", list(cust_opts.keys()), index=None, placeholder="Lütfen Seçiniz")
                p_date     = st.date_input("Tarih *", value=date.today())
                kg         = st.number_input("Miktar (KG) *", min_value=0.0, step=0.5, format="%.1f")
                acidity    = st.number_input("Asit Derecesi (Dizyem)", min_value=0.0, max_value=100.0, step=0.1, format="%.1f")
                unit_price = st.number_input("KG Birim Fiyatı (₺) *", min_value=0.0, step=1.0, format="%.2f")
                st.info("💡 Toplam tutar kayıt sırasında otomatik hesaplanır: KG × Birim Fiyat")
                note = st.text_area("Not (Opsiyonel)", placeholder="Varsa açıklama yazın...")

                if st.form_submit_button("💾 Alımı Kaydet", use_container_width=True):
                    if not selected:
                        st.error("Lütfen bir müşteri seçin!")
                    elif kg <= 0:
                        st.error("Miktar 0'dan büyük olmalıdır!")
                    elif unit_price <= 0:
                        st.error("Birim fiyat 0'dan büyük olmalıdır!")
                    else:
                        cid = cust_opts[selected]
                        total = kg * unit_price
                        path = ""
                        if photo_file:
                            path = save_uploaded_file(photo_file, "oil_photos")
                        elif camera_photo:
                            path = save_camera_photo(camera_photo, "oil_photos")
                        who = st.session_state.get("username", "admin")
                        add_oil_purchase(cid, p_date.isoformat(), kg, acidity, unit_price, total, note, path, who)
                        st.session_state["flash_success"] = f"✅ {format_kg(kg)} yağ alımı kaydedildi! Toplam: {format_currency(total)}"
                        st.rerun()

    with tab_history:
        all_custs = get_customers()
        filt = {"Tüm Müşteriler": None}
        filt.update({c["name"]: c["id"] for c in all_custs})
        sel = st.selectbox("Müşteriye Göre Filtrele", list(filt.keys()), key="oil_filter")
        purchases = get_oil_purchases(filt[sel])
        if not purchases:
            st.info("Kayıtlı yağ alımı bulunamadı.")
        else:
            for p in purchases:
                with st.container(border=True):
                    st.write(f"**{p['customer_name']}** — {format_currency(p['total_amount'])}")
                    st.caption(
                        f"{p['purchase_date']}  ·  ⚖️ {format_kg(p['kg'])}  ·  "
                        f"💲 {format_currency(p['unit_price'])}/kg  ·  🧪 %{p['acidity'] or '-'}"
                    )
                    st.caption(f"👤 İşlem: {p['created_by'] or 'Bilinmiyor'}")
                    if p["note"]:
                        st.caption(f"📝 {p['note']}")
                    if p["photo_path"] and os.path.exists(p["photo_path"]):
                        with st.expander("📸 Fotoğrafı Gör"):
                            st.image(p["photo_path"], width=300)
                    if st.button("🗑️ Sil", key=f"del_oil_{p['id']}"):
                        delete_oil_purchase(p["id"])
                        st.session_state["flash_success"] = "✅ Kayıt silindi."
                        st.rerun()


# ============================================================
# SAYFA: ÖDEMELER
# ============================================================

def render_payments():
    st.header("💸 Ödeme İşlemleri")
    st.caption("Müşterilere yapılan ödemeleri kaydedin ve takip edin")
    show_flash_message()

    tab_new, tab_history = st.tabs(["➕ Yeni Ödeme", "📋 Ödeme Geçmişi"])

    with tab_new:
        customers = get_customers(only_active=True)
        if not customers:
            st.warning("⚠️ Aktif müşteri bulunamadı! Lütfen önce aktif bir müşteri ekleyin.")
        else:
            cust_opts = {f"{c['name']} ({c['phone'] or 'Tel yok'})": c["id"] for c in customers}
            selected = st.selectbox("Müşteri Seçin *", list(cust_opts.keys()), index=None, placeholder="Lütfen Seçiniz", key="pay_customer")

            customer_id = None
            if selected:
                customer_id = cust_opts[selected]
                sums = get_customer_summary()
                s = next((x for x in sums if x["id"] == customer_id), None)
                if s:
                    render_kpi_cards([
                        {"icon": "💰", "label": "Hak Ediş",      "value": format_currency(s["total_purchase_amount"]), "color": "warning"},
                        {"icon": "💸", "label": "Ödenen",         "value": format_currency(s["total_paid"]),             "color": "positive"},
                        {"icon": "📋", "label": "Güncel Bakiye",  "value": format_currency(s["balance"]),
                         "color": "negative" if s["balance"] > 0 else "positive"},
                    ])

            # Makbuz — form dışında (kamera desteği)
            st.subheader("🧾 Makbuz Fotoğrafı (Opsiyonel)")
            rcpt_method = st.radio(
                "Yöntem", ["📁 Dosyadan Yükle", "📸 Kameradan Çek"],
                horizontal=True, key="pay_rcpt_method", label_visibility="collapsed",
            )
            rcpt_file = rcpt_camera = None
            if rcpt_method == "📁 Dosyadan Yükle":
                rcpt_file = st.file_uploader("Makbuz Seçin", type=["jpg","jpeg","png","webp"], key="pay_rcpt_file")
            else:
                rcpt_camera = st.camera_input("📸 Makbuz Çekin", key="pay_camera")
            st.divider()

            with st.form("new_payment_form", clear_on_submit=True):
                pay_date = st.date_input("Ödeme Tarihi *", value=date.today())
                amount   = st.number_input("Ödenen Tutar (₺) *", min_value=0.0, step=100.0, format="%.2f")
                pay_type = st.radio("Ödeme Türü *", ["Nakit", "Havale"], horizontal=True)
                note     = st.text_area("Not (Opsiyonel)", placeholder="Varsa açıklama yazın...")

                if st.form_submit_button("💾 Ödemeyi Kaydet", use_container_width=True):
                    if not customer_id:
                        st.error("Lütfen bir müşteri seçin!")
                    elif amount <= 0:
                        st.error("Ödeme tutarı 0'dan büyük olmalıdır!")
                    else:
                        path = ""
                        if rcpt_file:
                            path = save_uploaded_file(rcpt_file, "receipts")
                        elif rcpt_camera:
                            path = save_camera_photo(rcpt_camera, "receipts")
                        who = st.session_state.get("username", "admin")
                        add_payment(customer_id, pay_date.isoformat(), amount, pay_type, note, path, who)
                        st.session_state["flash_success"] = f"✅ {format_currency(amount)} ödeme kaydedildi!"
                        st.rerun()

    with tab_history:
        all_custs = get_customers()
        filt = {"Tüm Müşteriler": None}
        filt.update({c["name"]: c["id"] for c in all_custs})
        sel = st.selectbox("Müşteriye Göre Filtrele", list(filt.keys()), key="pay_filter")
        payments = get_payments(filt[sel])
        if not payments:
            st.info("Kayıtlı ödeme bulunamadı.")
        else:
            for p in payments:
                with st.container(border=True):
                    st.write(f"**{p['customer_name']}** — {format_currency(p['amount'])}")
                    st.caption(f"{p['payment_date']}  ·  💳 {p['payment_type']}")
                    st.caption(f"👤 İşlem: {p['created_by'] or 'Bilinmiyor'}")
                    if p["note"]:
                        st.caption(f"📝 {p['note']}")
                    if p["receipt_photo"] and os.path.exists(p["receipt_photo"]):
                        with st.expander("🧾 Makbuzu Gör"):
                            st.image(p["receipt_photo"], width=300)
                    if st.button("🗑️ Sil", key=f"del_pay_{p['id']}"):
                        delete_payment(p["id"])
                        st.session_state["flash_success"] = "✅ Ödeme silindi."
                        st.rerun()


# ============================================================
# SAYFA: DEPO VE SATIŞ
# ============================================================

def render_warehouse():
    st.header("📦 Depo ve Satış")
    st.caption("Stok durumunu takip edin ve satış kayıtlarını girin")
    show_flash_message()

    tab_stock, tab_new_sale, tab_history = st.tabs(["📊 Stok Durumu", "➕ Yeni Satış", "📋 Satış Geçmişi"])

    # --- STOK ---
    with tab_stock:
        st.subheader("Depo Stok Durumu (Asit Bazında)")
        stock = get_stock_by_acidity()
        if not stock:
            st.info("Henüz depoda kayıtlı yağ bulunmuyor.")
        else:
            tp = sum(r["purchased"] for r in stock)
            ts = sum(r["sold"] for r in stock)
            tn = sum(r["net_stock"] for r in stock)
            render_kpi_cards([
                {"icon": "🛢️", "label": "Toplam Alınan",  "value": format_kg(tp)},
                {"icon": "🏷️", "label": "Toplam Satılan", "value": format_kg(ts), "color": "warning"},
                {"icon": "📦", "label": "Depoda Kalan",    "value": format_kg(tn), "color": "info"},
            ])
            st.divider()

            for r in stock:
                net = r["net_stock"]
                icon = "🟢" if net > 0 else ("⚪" if net == 0 else "🔴")
                with st.container(border=True):
                    st.write(f"{icon} **Asit: %{r['acidity']}**")
                    st.caption(
                        f"Alınan: {format_kg(r['purchased'])}  ·  "
                        f"Satılan: {format_kg(r['sold'])}  ·  "
                        f"**Kalan: {format_kg(net)}**"
                    )
                    with st.expander("🔍 Kaynak Detaylarını Gör"):
                        details = get_acidity_details(r["acidity"])
                        if details:
                            for d in details:
                                st.write(f"- **{d['customer_name']}**: {format_kg(d['kg'])} ({d['purchase_date']})")
                        else:
                            st.caption("Detay bulunamadı.")

    # --- YENİ SATIŞ ---
    with tab_new_sale:
        st.subheader("Yeni Satış Kaydı")
        stock = get_stock_by_acidity()
        avail = [r for r in stock if r["net_stock"] > 0]
        if not avail:
            st.warning("⚠️ Depoda satılacak yağ bulunmuyor. Önce yağ alımı yapmanız gerekiyor.")
        else:
            st.info("📦 **Mevcut Stok:**  " + "  ·  ".join(
                [f"%{r['acidity']} → {format_kg(r['net_stock'])}" for r in avail]
            ))
            acid_opts = [r["acidity"] for r in avail]

            with st.form("new_sale_form", clear_on_submit=True):
                s_date  = st.date_input("Satış Tarihi *", value=date.today())
                buyer   = st.text_input("Alıcı Firma *", placeholder="Örn: Tariş Zeytin A.Ş.")
                s_acid  = st.selectbox("Asit Derecesi *", options=acid_opts, index=None, placeholder="Lütfen Seçiniz", format_func=lambda x: f"%{x}")
                s_kg    = st.number_input("Miktar (KG) *", min_value=0.0, step=0.5, format="%.1f")
                s_price = st.number_input("KG Birim Fiyatı (₺) *", min_value=0.0, step=1.0, format="%.2f")
                st.info("💡 Toplam tutar kayıt sırasında otomatik hesaplanır: KG × Birim Fiyat")
                s_note = st.text_area("Not (Opsiyonel)", placeholder="Varsa açıklama yazın...")

                if st.form_submit_button("💾 Satışı Kaydet", use_container_width=True):
                    if not s_acid:
                        st.error("Lütfen asit derecesi seçin!")
                    elif not buyer.strip():
                        st.error("Alıcı firma adı zorunludur!")
                    elif s_kg <= 0:
                        st.error("Miktar 0'dan büyük olmalıdır!")
                    elif s_price <= 0:
                        st.error("Birim fiyat 0'dan büyük olmalıdır!")
                    else:
                        avail_kg = get_available_stock(s_acid)
                        if s_kg > avail_kg:
                            st.error(
                                f"🚫 **STOK YETERSİZ!** %{s_acid} asit derecesinde depoda "
                                f"yalnızca **{format_kg(avail_kg)}** yağ var."
                            )
                        else:
                            total = s_kg * s_price
                            who = st.session_state.get("username", "admin")
                            add_sale(s_date.isoformat(), buyer.strip(), s_acid, s_kg, s_price, total, s_note, who)
                            st.session_state["flash_success"] = (
                                f"✅ Satış kaydedildi! {format_kg(s_kg)} (%{s_acid} asit) → "
                                f"**{buyer}** · Toplam: {format_currency(total)}"
                            )
                            st.rerun()

    # --- SATIŞ GEÇMİŞİ ---
    with tab_history:
        st.subheader("Satış Geçmişi")
        sales = get_sales()
        if not sales:
            st.info("Henüz satış kaydı bulunmuyor.")
        else:
            for s in sales:
                with st.container(border=True):
                    st.write(f"**{s['buyer_company']}** — {format_currency(s['total_amount'])}")
                    st.caption(
                        f"{s['sale_date']}  ·  ⚖️ {format_kg(s['kg'])}  ·  "
                        f"🧪 %{s['acidity']}  ·  💲 {format_currency(s['unit_price'])}/kg"
                    )
                    st.caption(f"👤 İşlem: {s['created_by'] or 'Bilinmiyor'}")
                    if s["note"]:
                        st.caption(f"📝 {s['note']}")
                    if st.button("🗑️ Sil", key=f"del_sale_{s['id']}"):
                        delete_sale(s["id"])
                        st.session_state["flash_success"] = "✅ Satış kaydı silindi."
                        st.rerun()


# ============================================================
# SAYFA: MÜŞTERİ DETAYI
# ============================================================

def render_customer_detail():
    st.header("🔎 Müşteri Detayı")
    st.caption("Bir müşterinin tüm alım ve ödeme geçmişini görüntüleyin")

    customers = get_customers()
    if not customers:
        st.info("Henüz müşteri eklenmemiş.")
        return

    opts = {c["name"]: c["id"] for c in customers}
    selected = st.selectbox("Müşteri Seçin", list(opts.keys()), key="detail_customer")
    cid = opts[selected]

    sums = get_customer_summary()
    summary = next((x for x in sums if x["id"] == cid), None)
    if summary:
        render_kpi_cards([
            {"icon": "🛢️", "label": "Toplam Yağ", "value": format_kg(summary["total_kg"])},
            {"icon": "💰", "label": "Hak Ediş",   "value": format_currency(summary["total_purchase_amount"]), "color": "warning"},
            {"icon": "💸", "label": "Ödenen",      "value": format_currency(summary["total_paid"]),            "color": "positive"},
            {"icon": "📋", "label": "Bakiye",      "value": format_currency(summary["balance"]),
             "color": "negative" if summary["balance"] > 0 else "positive"},
        ])

    st.divider()
    t1, t2 = st.tabs(["🛢️ Yağ Alımları", "💸 Ödemeler"])

    with t1:
        purchases = get_oil_purchases(cid)
        if not purchases:
            st.info("Bu müşteriye ait alım kaydı yok.")
        else:
            for p in purchases:
                with st.container(border=True):
                    st.write(f"**{format_currency(p['total_amount'])}**")
                    st.caption(
                        f"{p['purchase_date']}  ·  ⚖️ {format_kg(p['kg'])}  ·  "
                        f"💲 {format_currency(p['unit_price'])}/kg  ·  🧪 %{p['acidity'] or '-'}"
                    )
                    if p["note"]:
                        st.caption(f"📝 {p['note']}")

    with t2:
        payments = get_payments(cid)
        if not payments:
            st.info("Bu müşteriye ait ödeme kaydı yok.")
        else:
            for p in payments:
                with st.container(border=True):
                    st.write(f"**{format_currency(p['amount'])}**")
                    st.caption(f"{p['payment_date']}  ·  {p['payment_type']}")
                    if p["note"]:
                        st.caption(f"📝 {p['note']}")


# ============================================================
# SAYFA: AYARLAR / KULLANICILAR
# ============================================================

def render_settings_users():
    st.header("⚙️ Ayarlar / Kullanıcılar")
    st.caption("Kullanıcıları yönetin ve şifrenizi güncelleyin")

    tab_users, tab_profile = st.tabs(["👥 Sistem Kullanıcıları", "🔑 Profilimi Güncelle"])

    with tab_users:
        st.subheader("Mevcut Kullanıcılar")
        users = get_users()
        for u in users:
            with st.container(border=True):
                st.write(f"**👤 {u['username']}**")
                st.caption(f"Kayıt: {u['created_at']}")
                if u["username"] != "admin" and u["username"] != st.session_state.get("username"):
                    if st.button("🗑️ Sil", key=f"del_usr_{u['id']}"):
                        delete_user(u["id"])
                        st.session_state["flash_success"] = "✅ Kullanıcı silindi."
                        st.rerun()

        st.divider()
        st.subheader("Yeni Kullanıcı Ekle")
        with st.form("new_user_form", clear_on_submit=True):
            nu = st.text_input("Kullanıcı Adı *")
            np = st.text_input("Şifre *", type="password")
            if st.form_submit_button("✅ Ekle", use_container_width=True):
                if not nu.strip() or not np:
                    st.error("Kullanıcı adı ve şifre zorunludur.")
                elif add_user(nu.strip(), np):
                    st.session_state["flash_success"] = f"✅ {nu} eklendi."
                    st.rerun()
                else:
                    st.error("Bu kullanıcı adı zaten mevcut.")

    with tab_profile:
        st.subheader("Şifremi Değiştir")
        with st.form("change_pw_form", clear_on_submit=True):
            cur_user = next((u for u in get_users() if u["username"] == st.session_state.get("username")), None)
            pw1 = st.text_input("Yeni Şifre *", type="password")
            pw2 = st.text_input("Yeni Şifre (Tekrar) *", type="password")
            if st.form_submit_button("💾 Şifreyi Güncelle", use_container_width=True):
                if pw1 != pw2:
                    st.error("Şifreler uyuşmuyor!")
                elif len(pw1) < 4:
                    st.error("Şifre en az 4 karakter olmalıdır.")
                elif cur_user:
                    change_password(cur_user["id"], pw1)
                    delete_user_tokens(st.session_state["username"])
                    try:
                        get_cookie_manager().delete("olivarda_auth_token")
                    except Exception:
                        pass
                    st.session_state["authenticated"] = False
                    st.session_state.pop("username", None)
                    st.session_state["flash_success"] = "✅ Şifre güncellendi. Lütfen tekrar giriş yapın."
                    st.rerun()


# ============================================================
# MENÜ YAPILANDIRMASI
# ============================================================

MENU_ITEMS = [
    {"key": "dashboard",       "icon": "📊", "label": "Genel Bakış"},
    {"key": "customers",       "icon": "👥", "label": "Müşteriler"},
    {"key": "oil_purchase",    "icon": "🛢️", "label": "Yağ Alımı"},
    {"key": "payments",        "icon": "💸", "label": "Ödemeler"},
    {"key": "warehouse",       "icon": "📦", "label": "Depo ve Satış"},
    {"key": "customer_detail", "icon": "🔎", "label": "Müşteri Detayı"},
    {"key": "settings",        "icon": "⚙️", "label": "Ayarlar"},
]

PAGE_RENDERERS = {
    "dashboard":       render_dashboard,
    "customers":       render_customers,
    "oil_purchase":    render_oil_purchase,
    "payments":        render_payments,
    "warehouse":       render_warehouse,
    "customer_detail": render_customer_detail,
    "settings":        render_settings_users,
}


# ============================================================
# ANA UYGULAMA
# ============================================================

def main():
    init_db()
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    cleanup_expired_tokens()

    # CookieManager — her render döngüsünde TEK SEFER oluşturulur
    cookie_manager = stx.CookieManager(key="olivarda_cookies")
    st.session_state["_cookie_manager"] = cookie_manager

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    # Cookie'den otomatik giriş
    if not st.session_state["authenticated"]:
        try:
            token = cookie_manager.get("olivarda_auth_token")
            if token:
                uname = verify_auth_token(token)
                if uname:
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = uname
                else:
                    cookie_manager.delete("olivarda_auth_token")
        except Exception:
            pass

    if not st.session_state["authenticated"]:
        render_login()
        return

    if "active_page" not in st.session_state:
        st.session_state["active_page"] = "dashboard"

    # --- SIDEBAR ---
    with st.sidebar:
        st.markdown("""
        <div class="brand-header">
            <div class="brand-name">🫒 Olivarda</div>
            <div class="brand-subtitle">Erengül Zeytinyağı Ticareti</div>
            <div class="brand-divider"></div>
        </div>
        """, unsafe_allow_html=True)
        st.write("")
        st.divider()

        for item in MENU_ITEMS:
            is_active = st.session_state["active_page"] == item["key"]
            label = f"{item['icon']}  {item['label']}"
            if st.button(label, key=f"menu_{item['key']}", use_container_width=True,
                         type="primary" if is_active else "secondary"):
                st.session_state["active_page"] = item["key"]
                st.rerun()

        st.divider()
        st.caption(f"👤 {st.session_state.get('username', 'admin')}")
        st.caption(f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}")

        if st.button("🚪 Çıkış Yap", use_container_width=True):
            try:
                tok = cookie_manager.get("olivarda_auth_token")
                if tok:
                    delete_auth_token(tok)
                cookie_manager.delete("olivarda_auth_token")
            except Exception:
                pass
            st.session_state["authenticated"] = False
            st.session_state.pop("username", None)
            st.session_state.pop("active_page", None)
            st.rerun()

        st.markdown("""
        <div class="sidebar-footer">
            © 2026 Olivarda — Erengül Zeytinyağı Ticareti
        </div>
        """, unsafe_allow_html=True)

    # --- SAYFA RENDER ---
    renderer = PAGE_RENDERERS.get(st.session_state["active_page"], render_dashboard)
    renderer()


if __name__ == "__main__":
    main()
