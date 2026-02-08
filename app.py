import streamlit as st
import pandas as pd
import os
import re
import tempfile
from io import BytesIO

# =========================================================
#  Hacettepe Çevre Akredite Takip Sistemi (app.py)
#  - Excel'lerden PC/PÇ çıktılarını tek tabloda birleştirir
#  - ID (Öğrenci No) üzerinden tekilleştirir (duplicate engeller)
#  - Mezun listesi ayrı yüklenir ve Durum filtresi sağlar
# =========================================================

st.set_page_config(page_title="Hacettepe Çevre Akredite", layout="wide")

VERI_KLASORU = "Veri_Kayitlari"
os.makedirs(VERI_KLASORU, exist_ok=True)

SIFRE = "akredite2026"
MEZUN_DOSYA_ADI = "MEZUN_LISTESI.xlsx"

# Okul numaraları genelde 9-11 hane ise bunu 9/10/11 yapmanız önerilir.
MIN_ID_LEN = 7


# =======================
#  HELPERS
# =======================
def normalize_colname(c: str) -> str:
    """Kolon adlarını normalize eder: lower + trim + tek boşluk."""
    s = str(c).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def atomic_write(path: str, data: bytes) -> None:
    """Streamlit Cloud'da dosya yazımını daha güvenli hale getirir (atomik replace)."""
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=".bin")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except:
                pass

def id_temizle(val) -> str:
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

def yil_coz(no: str) -> str:
    s = str(no).strip()
    if len(s) >= 3 and s[1:3].isdigit():
        return "20" + s[1:3]
    return "Belirsiz"

def pick_id_column(df: pd.DataFrame, min_len: int = MIN_ID_LEN):
    """
    Sıra No tuzağına düşmemek için ID kolonunu skorlayarak seçer.
    - Adaylar: 'öğrenci/student' içerenler; yoksa 'no/number' içerenler
    - Skor: uzun ID oranı + medyan uzunluk
    - 'sıra/sira/index/row' geçen kolonlar cezalandırılır
    """
    cols = [normalize_colname(c) for c in df.columns]
    dfx = df.copy()
    dfx.columns = cols

    # Öncelik: öğrenci/student
    candidates = [c for c in cols if ("öğrenci" in c or "ogrenci" in c or "student" in c)]
    if not candidates:
        candidates = [c for c in cols if ("no" in c or "number" in c)]

    best_col, best_score = None, -1

    for c in candidates:
        # sıra/indeks barizse direkt geriye it
        if any(k in c for k in ["sıra", "sira", "index", "row", "satır", "satir", "sr no", "s.no"]):
            penalty = 60
        else:
            penalty = 0

        series = dfx[c].apply(id_temizle)
        series = series[series != ""]
        if series.empty:
            continue

        lens = series.str.len()
        long_ratio = (lens >= min_len).mean()
        med_len = lens.median()
        score = long_ratio * 100 + med_len - penalty

        if score > best_score:
            best_score = score
            best_col = c

    return best_col

def build_fullname(df: pd.DataFrame) -> pd.Series:
    """Name/Surname ayrı ya da tek sütun olabilir. En iyi Ad Soyad'ı üretir."""
    cols = list(df.columns)

    # normalize edilmiş kolon adları ile çalışalım
    # (df dışarıda normalize ediliyor ama burada garanti olsun)
    df2 = df.copy()
    df2.columns = [normalize_colname(c) for c in df2.columns]
    cols = list(df2.columns)

    # Tek kolon ad soyad / name surname
    one_col = next((c for c in cols if c in ["name surname", "namesurname", "ad soyad", "adsoyad"]), None)

    ad = next((c for c in cols if c in ["ad", "name", "first name", "firstname"]), None)
    soyad = next((c for c in cols if c in ["soyad", "surname", "last name", "lastname"]), None)

    if ad and soyad and ad != soyad:
        full = df2[ad].astype(str).fillna("") + " " + df2[soyad].astype(str).fillna("")
    elif one_col:
        full = df2[one_col].astype(str).fillna("")
    elif ad:
        full = df2[ad].astype(str).fillna("")
    else:
        full = pd.Series([""] * len(df2))

    full = full.str.replace(r"\s+", " ", regex=True).str.strip()
    return full

def standardize_pc_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    PC/PÇ kolonlarını PC1, PC2... formatına çevirir.
    Örn: 'PÇ4', 'PC 4', 'pc4 ', 'pç 4' -> 'PC4'
    """
    out = df.copy()
    rename_map = {}
    for c in out.columns:
        cl = normalize_colname(c)
        # pc veya pç geçen kolonlar
        if ("pc" in cl) or ("pç" in cl) or ("pç" in cl):
            nums = re.findall(r"\d+", cl)
            if nums:
                rename_map[c] = f"PC{nums[0]}"
    if rename_map:
        out.rename(columns=rename_map, inplace=True)
    return out

def coerce_pc_to01(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if str(c).startswith("PC"):
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype(int).clip(0, 1)
    return out

def first_non_empty(x: pd.Series) -> str:
    x = x.dropna().astype(str).str.strip()
    x = x[x != ""]
    return x.iloc[0] if len(x) else ""

def read_mezun_listesi(folder: str, log: list) -> set:
    """MEZUN_LISTESI.xlsx içinden mezun ID'lerini topla."""
    path = os.path.join(folder, MEZUN_DOSYA_ADI)
    if not os.path.exists(path):
        log.append("ℹ️ Mezun listesi bulunamadı (MEZUN_LISTESI.xlsx yok).")
        return set()

    mezun_ids = set()
    try:
        df_dict = pd.read_excel(path, sheet_name=None)
        for sh, df in df_dict.items():
            if df is None or df.empty:
                continue
            df = df.copy()
            df.columns = [normalize_colname(c) for c in df.columns]
            id_col = pick_id_column(df, min_len=MIN_ID_LEN)
            if not id_col:
                log.append(f"⚠️ Mezun/{sh}: ID kolonu bulunamadı.")
                continue
            ids = normalize_and_validate_id(df[id_col], min_len=MIN_ID_LEN)
            ids = ids[ids != ""]
            mezun_ids.update(ids.tolist())
        log.append(f"✅ Mezun listesi yüklendi: {len(mezun_ids)} kişi")
    except Exception as e:
        log.append(f"❌ Mezun listesi okunamadı: {e}")
        return set()

    return mezun_ids


# =======================
#  SESSION STATE (donma/rerun kontrolü)
# =======================
if "refresh" not in st.session_state:
    st.session_state.refresh = 0

def trigger_refresh():
    st.session_state.refresh += 1


# =======================
#  SIDEBAR (Yönetim)
# =======================
with st.sidebar:
    st.header("🔐 Yönetim")
    pw = st.text_input("Şifre:", type="password")

    if pw == SIFRE:
        st.subheader("1) Ders Excel'leri")
        ders_dosyalar = st.file_uploader(
            "Ders dosyalarını yükle (.xlsx)", type=["xlsx"], accept_multiple_files=True
        )

        if st.button("💾 Ders dosyalarını kaydet", use_container_width=True):
            if ders_dosyalar:
                for f in ders_dosyalar:
                    save_path = os.path.join(VERI_KLASORU, f.name)
                    atomic_write(save_path, f.getvalue())
                st.success("Ders dosyaları kaydedildi.")
                trigger_refresh()
            else:
                st.warning("Ders dosyası seçilmedi.")

        st.divider()

        st.subheader("2) Mezun Listesi (tek dosya)")
        mezun_dosya = st.file_uploader(
            "Mezun listesini yükle (.xlsx)\n(Sistem bunu MEZUN_LISTESI.xlsx olarak saklar)",
            type=["xlsx"],
            accept_multiple_files=False,
        )

        if st.button("🎓 Mezun listesini kaydet", use_container_width=True):
            if mezun_dosya is not None:
                save_path = os.path.join(VERI_KLASORU, MEZUN_DOSYA_ADI)
                atomic_write(save_path, mezun_dosya.getvalue())
                st.success("Mezun listesi kaydedildi.")
                trigger_refresh()
            else:
                st.warning("Mezun listesi dosyası seçilmedi.")

        st.divider()

        st.subheader("3) Kayıtlı dosyalar / Sil")
        arsiv = sorted([f for f in os.listdir(VERI_KLASORU) if f.lower().endswith(".xlsx")])

        if arsiv:
            sil = st.selectbox("Sil:", ["Seç..."] + arsiv)
            if st.button("🗑️ Seçili dosyayı sil", use_container_width=True):
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

# rerun'u tek noktadan ve kontrollü yap
if st.session_state.refresh > 0:
    st.session_state.refresh = 0
    st.rerun()


# =======================
#  MAIN
# =======================
st.title("📊 Öğrenci Akreditasyon (PC/PÇ) Takip Sistemi")

arsiv = sorted([f for f in os.listdir(VERI_KLASORU) if f.lower().endswith(".xlsx")])
if not arsiv:
    st.info("Veri yok. Sol menüden Excel dosyalarını yükleyin.")
    st.stop()

# Log: "neden veri çıkmadı?" sorusuna cevap verir
log = []

# Mezun listesi
mezunlar = read_mezun_listesi(VERI_KLASORU, log)

# Mezun dosyası ders gibi okunmasın
ders_arsiv = [f for f in arsiv if f != MEZUN_DOSYA_ADI]

all_dfs = []

for f_name in ders_arsiv:
    full_path = os.path.join(VERI_KLASORU, f_name)
    try:
        df_dict = pd.read_excel(full_path, sheet_name=None)
    except Exception as e:
        log.append(f"❌ {f_name}: okunamadı ({e})")
        continue

    used_any = False

    for sh, df in df_dict.items():
        if df is None or df.empty:
            log.append(f"⚠️ {f_name}/{sh}: boş sayfa")
            continue

        df = df.copy()
        df.columns = [normalize_colname(c) for c in df.columns]

        # PC kolonları: PC veya PÇ + sayı içerenleri hedefle
        pc_cols = []
        for c in df.columns:
            cl = normalize_colname(c)
            if (("pc" in cl) or ("pç" in cl) or ("pç" in cl)) and re.search(r"\d+", cl):
                pc_cols.append(c)

        if not pc_cols:
            log.append(f"⚠️ {f_name}/{sh}: PC/PÇ kolonu bulunamadı -> atlandı")
            continue

        id_col = pick_id_column(df, min_len=MIN_ID_LEN)
        if not id_col:
            log.append(f"⚠️ {f_name}/{sh}: ID kolonu bulunamadı -> atlandı")
            continue

        temp = df[[id_col] + pc_cols].copy()
        temp.rename(columns={id_col: "ID"}, inplace=True)

        # ID temizle + kısa ID'leri ele
        before = len(temp)
        temp["ID"] = normalize_and_validate_id(temp["ID"], min_len=MIN_ID_LEN)
        temp = temp[temp["ID"] != ""].copy()
        after = len(temp)

        if temp.empty:
            log.append(f"⚠️ {f_name}/{sh}: ID filtre sonrası 0 satır (önce {before})")
            continue

        # İsim
        temp["Ad Soyad"] = build_fullname(df)

        # PC kolonlarını standardize et ve 0/1'e zorla
        temp = standardize_pc_columns(temp)
        temp = coerce_pc_to01(temp)

        all_dfs.append(temp)
        used_any = True
        log.append(f"✅ {f_name}/{sh}: eklendi | satır {after}/{before} | id_col='{id_col}' | pc={len(pc_cols)}")

    if not used_any:
        log.append(f"ℹ️ {f_name}: hiçbir sheet kullanılmadı (ID/PC bulunamadı olabilir)")

if not all_dfs:
    st.warning("Geçerli PC/PÇ verisi bulunamadı. Log'dan dosya/sheet neden atlandı kontrol edin.")
    with st.expander("🧾 Log (Neden veri çıkmadı?)", expanded=True):
        st.write("\n".join(log) if log else "Log yok.")
    st.stop()

final = pd.concat(all_dfs, ignore_index=True)

# Birleştirme: ID bazında max (1'ler korunur)
agg = {"Ad Soyad": first_non_empty}
for c in final.columns:
    if str(c).startswith("PC"):
        agg[c] = "max"

res = final.groupby("ID", as_index=False).agg(agg)
res["Ad Soyad"] = res["Ad Soyad"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip().str.title()
res["Durum"] = res["ID"].apply(lambda x: "🎓 MEZUN" if x in mezunlar else "📝 ÖĞRENCİ")
res["Yıl"] = res["ID"].apply(yil_coz)

# =======================
#  FILTERS
# =======================
st.subheader("🔎 Filtreler")

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
    filtered = filtered[
        filtered["ID"].astype(str).str.contains(q, case=False, na=False)
        | filtered["Ad Soyad"].astype(str).str.contains(q, case=False, na=False)
    ]

# =======================
#  DISPLAY
# =======================
st.subheader("📌 Sonuçlar")

pc_sorted = sorted(
    [c for c in filtered.columns if str(c).startswith("PC")],
    key=lambda x: int(re.findall(r"\d+", x)[0]) if re.findall(r"\d+", x) else 9999,
)

ordered_cols = ["ID", "Ad Soyad", "Yıl", "Durum"] + pc_sorted
ordered_cols = [c for c in ordered_cols if c in filtered.columns]

st.caption(f"Toplam öğrenci: {len(res)} | Mezun listesi: {len(mezunlar)} kişi | Gösterilen: {len(filtered)}")
st.dataframe(filtered[ordered_cols], use_container_width=True)

# Excel indir
buf = BytesIO()
filtered[ordered_cols].to_excel(buf, index=False, engine="openpyxl")
buf.seek(0)

st.download_button(
    "⬇️ Filtrelenmiş tabloyu Excel indir",
    data=buf,
    file_name="PC_PC_Takip_Sonuclari.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

with st.expander("🧾 Log (Dosyalar nasıl okundu?)", expanded=False):
    st.write("\n".join(log) if log else "Log yok.")
