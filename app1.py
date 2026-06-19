import streamlit as st
import os
# ... TODO 8: pindahkan fungsi pipeline ke sini & buat UI chat ...
# Import pandas untuk data tabel
import pandas as pd
# Import client Gemini
from google import genai
# Import 'types' untuk konfigurasi (system prompt, temperature)
from google.genai import types

# Judul & caption halaman
st.title("Mini Project Use Case C: Chatbot Analitik PLN - Aset Gangguan")
st.caption("Conversational Analytics - Streamlit Community Cloud")
# ======================
# 1. Konfigurasi
# ======================
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    st.error("GOOGLE_API_KEY belum ditemukan.")
    st.stop()

genai.configure(api_key=GOOGLE_API_KEY)

MODEL_NAME = "gemini-2.5-flash"
model = genai.GenerativeModel(MODEL_NAME)

DB_URL = os.getenv(
    "DB_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/miniproject"
)

engine = create_engine(DB_URL)

SCHEMA_STR = """assets(asset_id, nama, jenis, lokasi)
outages(outage_id, asset_id, mulai, selesai, durasi_menit, penyebab)

Relasi:
- outages.asset_id -> assets.asset_id
Catatan: 'mulai' & 'selesai' berformat 'YYYY-MM-DD HH:MM'.
         durasi_menit = lama gangguan dalam menit."""

FORBIDDEN = ["drop", "delete", "update", "insert", "alter", "truncate", "create", "grant"]


# ======================
# 2. Pipeline Text-to-SQL
# ======================
def build_prompt(question: str) -> str:
    return f"""
Anda adalah ahli SQL PostgreSQL.

Tugas Anda:
- Ubah pertanyaan pengguna menjadi SATU query SQL PostgreSQL.
- Gunakan HANYA tabel dan kolom yang ada pada skema.
- Query harus berupa SELECT saja.
- Jangan gunakan INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE.
- Jika perlu data aset/gardu, JOIN outages ke assets melalui asset_id.
- Untuk pertanyaan "bulan ini", gunakan rentang tanggal Juni 2026:
  mulai >= '2026-06-01' AND mulai < '2026-07-01'
- Balas HANYA query SQL, tanpa penjelasan, tanpa markdown, tanpa ```sql.

Skema database:
{SCHEMA_STR}

Contoh:
Pertanyaan: Berapa jumlah gangguan per aset pada bulan ini?
SQL:
SELECT a.nama, COUNT(*) AS jumlah_gangguan
FROM outages o
JOIN assets a ON a.asset_id = o.asset_id
WHERE o.mulai >= '2026-06-01' AND o.mulai < '2026-07-01'
GROUP BY a.nama
ORDER BY jumlah_gangguan DESC

Pertanyaan: Berapa rata-rata durasi pemulihan per jenis aset?
SQL:
SELECT a.jenis, AVG(o.durasi_menit) AS rata_durasi_menit
FROM outages o
JOIN assets a ON a.asset_id = o.asset_id
GROUP BY a.jenis
ORDER BY rata_durasi_menit DESC

Pertanyaan: {question}
SQL:
"""


def _bersihkan_sql(teks: str) -> str:
    teks = teks.strip()

    if teks.startswith("```"):
        teks = re.sub(r"^```(?:sql)?", "", teks).strip()
        teks = re.sub(r"```$", "", teks).strip()

    match = re.search(r"(SELECT[\s\S]*)", teks, flags=re.IGNORECASE)
    if match:
        teks = match.group(1)

    return teks.rstrip(";").strip()


def generate_sql(question: str) -> str:
    prompt = build_prompt(question)
    resp = model.generate_content(prompt)
    return _bersihkan_sql(resp.text)


def validate_sql(sql: str) -> bool:
    teks = sql.strip().rstrip(";").strip()
    low = teks.lower()

    if not low:
        return False

    if not low.startswith("select"):
        return False

    for kata in FORBIDDEN:
        if re.search(rf"\b{kata}\b", low):
            return False

    if ";" in teks.rstrip(";"):
        return False

    return True


def run_sql(sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


def jawab(question: str):
    sql = generate_sql(question)

    if not validate_sql(sql):
        sql = generate_sql(question)

        if not validate_sql(sql):
            return sql, None, "SQL yang dihasilkan tidak aman untuk dijalankan."

    try:
        df = run_sql(sql)
        return sql, df, None
    except Exception as e:
        return sql, None, str(e)


def tampilkan_chart(df: pd.DataFrame):
    if df is None or df.empty:
        return

    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    if len(df.columns) < 2 or not numeric_cols:
        return

    x_col = df.columns[0]
    y_col = numeric_cols[0]

    chart_df = df[[x_col, y_col]].set_index(x_col)

    nama_x = x_col.lower()
    is_time = (
        "tanggal" in nama_x
        or "bulan" in nama_x
        or "periode" in nama_x
        or "waktu" in nama_x
        or "mulai" in nama_x
    )

    if is_time:
        st.line_chart(chart_df)
    else:
        st.bar_chart(chart_df)


# ======================
# 3. Streamlit UI
# ======================
st.set_page_config(page_title="Chatbot Aset & Gangguan", page_icon="⚡")

st.title("⚡ Chatbot Analitik Aset & Gangguan")
st.caption("Mini Project Conversational Analytics — Text-to-SQL")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

question = st.chat_input("Tanyakan data aset/gangguan...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Membuat SQL dan mengambil data..."):
            sql, df, error = jawab(question)

        if error:
            st.error(error)
            if sql:
                st.code(sql, language="sql")
            response = "Maaf, query gagal dijalankan."

        else:
            st.markdown("**SQL yang dijalankan:**")
            st.code(sql, language="sql")

            st.markdown("**Hasil query:**")
            st.dataframe(df)

            st.markdown("**Visualisasi:**")
            tampilkan_chart(df)

            response = "Berikut hasil query dan visualisasinya."

    st.session_state.messages.append({"role": "assistant", "content": response})

print("TODO 8 (opsional): kerjakan jika waktu masih cukup.")
