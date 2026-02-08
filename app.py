import streamlit as st
import pandas as pd
import os
import re
import tempfile

# =======================
#  CONFIG
# =======================
st.set_page_config(page_title="Hacettepe Çevre Akredite", layout="wide")

VERI_KLASORU = "Veri_Kayitlari"
if not os.path.exists(VERI_KLASORU):
    os.makedirs(VERI_KLASORU)

SIFRE = "akredite2026"
MIN_ID_LEN = 7  # okul numarana göre 9-11 ise bunu yükseltebilirsin (örn 9 veya 10)

# =======================
#  HELPERS
# =======================
def atomic_write(path: str, data: bytes):
    """Streamlit Cloud'da yarım yazım / kilitlenme riskini azaltmak için atomik yazım."""
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=".bin")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)  # atomic replace
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except:
                pass

def id_temizle(val):
    """ID içindeki sayı dışı her şeyi at; excel 123.0 -> 123 düzelt."""
    if pd.isna(val):
        return ""
    s = str(val).strip()
    s = s.split(".")[0]
    return re.sub(r"\D", "", s)

def normalize_and_validate_id(series: pd.Series, min_len: int = MIN_ID_LEN) -> pd.Series:
    s = series.apply(id_temizle)
    s = s.where(s.str.len() >= min_len, "")
    return s

def yil_coz(no):
    s = str(no).strip()
    if len(s) >= 3 and s[1:3].isdigit():
        return "20" + s[1:3]
    return "Belirsiz"

def pick_id_column(df: pd.DataFrame, min_len: int = MIN_ID_LEN):
    """Sıra No tuzağına düşmemek için 'ID gibi görünen' sütunu skorlayarak seç."""
    cols = [str(c).strip().lower() for c in df.columns]
    dfx = df.copy()
    dfx.columns = cols

    # adaylar: önce öğrenci/student, yoksa no/number
    candidates = [c for c in cols if ("öğrenci" in c or "ogrenci" in c or "student" in c)]
    if not candidates:
        candidates = [c for c in cols if ("no" in c or "number" in c)]

    best_col, best_score = None, -1

    for c in candidates:
        series = dfx[c].apply(id_temizle)
        series = series[series != ""]
        if series.empty:
            continue

        lens = series.str.len()
        long_ratio = (lens >= min_len).mean()
        med_len = lens.median()
        score = long_ratio * 100 + med_len

        # "sıra" kelimesi geçen kolonları cezalandır
        if "sıra" in c or "sira" in c:
            score -= 50

        if score > best_score:
            best_score = score
            best_col = c

    return best_col

def build_fullname(df: pd.DataFrame) -> pd.Series:
    """Name/Surname ayrı veya tek sütun olabilir; mümkün olan en iyi Ad Soyad üret."""
    cols = list(df.columns)

    # daha yaygın varyasyonları da yakala
    ad = next((c for c in cols if c in ["ad", "name", "first name", "firstname"]), None)
    soyad = next((c for c in cols if c in ["soyad", "surname", "last name", "lastname"]), None)

    if ad and soyad and ad != soyad:
        full = df[ad].astype(str).fillna("") + " " + df[soyad].astype(str).fillna("")
    elif ad:
        full = df[ad].astype(str).fillna("")
    else:
        # bazı dosyalarda direkt "ad soyad" gibi bir kolon olabilir
        adsoyad = next((c for c in cols if ("ad soyad" in c or "name surname" in c or "namesurname" in c)), None)
        if adsoyad:
            full = df[adsoyad].astype(str).fillna("")
        else:
            full = pd.Series([""] * len(df))

    full = full.str.replace(r"\s+", " ", regex=True).str.strip()
    return full

def first_non_empty(x: pd.Series) -> str:
    x = x.dropna().astype(str).str.strip()
    x = x[x != ""]
    return x.iloc[0] if len(x) else ""

def standardize_pc_columns(df: pd.DataFrame) -> pd.DataFrame:
    """PC/PÇ kolonlarını PC1, PC2... formatına çevir."""
    out = df.copy()
    rename_map = {}
    for c in out.columns:
        cl = str(c).strip().lower()
        if ("pc" in cl) or ("pç" in cl):
            n = re.findall(r"\d+", cl)
            if n:
                rename_map[c] = f"PC{n[0]}"
    if rename_map:
        out.rename(columns=rename_map, inplace=True)
    return out

def coerce_pc_to01(df: pd.DataFrame) -> pd.DataFrame:
    """PC kolonlarını 0/1 integer'a zorla."""
    out = df.copy()
    for c in out.columns:
        if str(c).startswith("PC"):
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype(int).clip(0, 1)
    return out

# =======================
#  SESSION STATE
# =======================
if "refresh" not in st.session_state:
    st.session_state.refresh = 0

def trigger_refresh():
    st.session_state.refresh += 1

# =======================
#  SIDEBAR (ADMIN)
# =======================
with st.sidebar:
    st.header("🔐 Yönetim")
    pw = st.text_input("Şifre:", type="password")

    if pw == SIFRE:
        y_dosya = st.file_uploader("Excel Yükle (.xlsx)", type=["xlsx"], accept_multiple_files=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Kaydet", use_container_width=True):
                if y_dosya:
                    for f in y_dosya:
                        save_path = os.path.join(VERI_KLASORU, f.name)
                        atomic_write(save_path, f.getvalue())
                    st.success("Dosyalar kaydedildi.")
                    trigger_refresh()
                else:
                    st.warning("Yüklenecek dosya seçilmedi.")

        # arşiv listele & sil
        arsiv = sorted([f for f in os.listdir(VERI_KLASORU) if f.lower().endswith(".xlsx")])
        if arsiv:
            sil = st.selectbox("Sil:", ["Seç..."] + arsiv)
            with col2:
                if st.button("🗑️ Sil", use_container_width=True):
                    if sil != "Seç...":
                        try:
                            os.remove(os.path.join(VERI_KLASORU, sil))
                            st.success("Dosya silindi.")
                            trigger_refresh()
                        except Exception as e:
                            st.error(f"Silme hatası: {e}")
                    else:
                        st.warning("Silmek için dosya seç.")
        else:
            st.info("Kayıtlı dosya yok.")

# rerun'u tek noktadan ve şartlı yap (Cloud donmasını azaltır)
if st.session_state.refresh > 0:
    st.session_state.refresh = 0
    st.rerun()

# =======================
#  MAIN - ANALYSIS
# =======================
st.title("📊 Öğrenci Akreditasyon (PC/PÇ) Takip Sistemi")

arsiv = sorted([f for f in os.listdir(VERI_KLASORU) if f.lower().endswith(".xlsx")])

if not arsiv:
    st.info("Veri yok. Sol menüden Excel dosyalarını yükleyin.")
    st.stop()

all_dfs = []
mezunlar = set()

for f_name in arsiv:
    full_path = os.path.join(VERI_KLASORU, f_name)
    try:
        df_dict = pd.read_excel(full_path, sheet_name=None)
    except Exception as e:
        st.warning(f"Okunamadı: {f_name} ({e})")
        continue

    for sheet, df in df_dict.items():
        if df is None or df.empty:
            continue

        df = df.copy()
        df.columns = [str(c).strip().lower() for c in df.columns]

        # PC kolonları
        pc_cols = [c for c in df.columns if ("pc" in c or "pç" in c)]
        if not pc_cols:
            continue

        # ID kolonunu güvenle seç
        id_col = pick_id_column(df, min_len=MIN_ID_LEN)
        if not id_col:
            continue

        # temel tablo
        temp = df[[id_col] + pc_cols].copy()
        temp.rename(columns={id_col: "ID"}, inplace=True)

        temp["ID"] = normalize_and_validate_id(temp["ID"], min_len=MIN_ID_LEN)
        temp = temp[temp["ID"] != ""].copy()
        if temp.empty:
            continue

        # Ad Soyad
        temp["Ad Soyad"] = build_fullname(df)

        # PC kolon standardizasyonu ve 0/1'e çevirme
        temp = standardize_pc_columns(temp)
        temp = coerce_pc_to01(temp)

        # mezun dosyası mı?
        if "mezun" in f_name.lower():
            mezunlar.update(temp["ID"].tolist())
        else:
            all_dfs.append(temp)

if not all_dfs:
    st.info("PC/PÇ içeren geçerli veri bulunamadı.")
    st.stop()

final = pd.concat(all_dfs, ignore_index=True)

# groupby + max (1'ler korunur), isim için first_non_empty
agg_rules = {"Ad Soyad": first_non_empty}
for c in final.columns:
    if str(c).startswith("PC"):
        agg_rules[c] = "max"

res = final.groupby("ID", as_index=False).agg(agg_rules)

# son temizlikler
res["Ad Soyad"] = res["Ad Soyad"].astype(str).str.strip().str.replace(r"\s+", " ", regex=True).str.title()
res["Durum"] = res["ID"].apply(lambda x: "🎓 MEZUN" if x in mezunlar else "📝 ÖĞRENCİ")
res["Yıl"] = res["ID"].apply(yil_coz)

# =======================
#  FILTERS
# =======================
st.subheader("🔎 Filtreler")

# Yıl filtre seçenekleri
yil_ops = sorted([y for y in res["Yıl"].dropna().unique().tolist() if y != "Belirsiz"])
yil_ops = ["Tümü"] + yil_ops + (["Belirsiz"] if "Belirsiz" in res["Yıl"].unique() else [])

durum_ops = ["Tümü", "📝 ÖĞRENCİ", "🎓 MEZUN"]

c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    sec_yil = st.selectbox("Giriş Yılı", yil_ops, index=0)
with c2:
    sec_durum = st.selectbox("Durum", durum_ops, index=0)
with c3:
    q = st.text_input("Ara (ID / Ad Soyad)", value="").strip()

filtered = res.copy()

if sec_yil != "Tümü":
    filtered = filtered[filtered["Yıl"] == sec_yil]

if sec_durum != "Tümü":
    filtered = filtered[filtered["Durum"] == sec_durum]

if q:
    qq = q.lower()
    filtered = filtered[
        filtered["ID"].astype(str).str.contains(qq, case=False, na=False)
        | filtered["Ad Soyad"].astype(str).str.lower().str.contains(qq, na=False)
    ]

# =======================
#  DISPLAY
# =======================
st.subheader("📌 Sonuçlar")

# kolon sırası
pc_sorted = sorted([c for c in filtered.columns if str(c).startswith("PC")],
                   key=lambda x: int(re.findall(r"\d+", x)[0]) if re.findall(r"\d+", x) else 9999)

ordered_cols = ["ID", "Ad Soyad", "Yıl", "Durum"] + pc_sorted
ordered_cols = [c for c in ordered_cols if c in filtered.columns]

st.dataframe(filtered[ordered_cols], use_container_width=True)

# indirilebilir çıktı
st.download_button(
    "⬇️ Sonuçları Excel olarak indir",
    data=filtered[ordered_cols].to_excel(index=False, engine="openpyxl"),
    file_name="PC_PC_Takip_Sonuclari.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
