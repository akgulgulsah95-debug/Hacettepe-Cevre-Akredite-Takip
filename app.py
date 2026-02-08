import streamlit as st
import pandas as pd
import os
import re
import tempfile
from io import BytesIO
from typing import List

# =========================================================
#  Hacettepe Çevre Akredite Takip Sistemi (FAST app.py)
#  - Excel'ler SADECE veri değişince yeniden okunur
#  - Filtre/arama anında (RAM üzerinden) çalışır
# =========================================================

st.set_page_config(page_title="Hacettepe Çevre Akredite", layout="wide")

VERI_KLASORU = "Veri_Kayitlari"
os.makedirs(VERI_KLASORU, exist_ok=True)

SIFRE = "akredite2026"
MEZUN_DOSYA_ADI = "MEZUN_LISTESI.xlsx"
MIN_ID_LEN = 7  # 9-11 ise 9/10/11 yapmanız önerilir


# =======================
#  HELPERS
# =======================
def normalize_colname(c: str) -> str:
    s = str(c).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def atomic_write(path: str, data: bytes) -> None:
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
            except Exception:
                pass

def id_temizle(val) -> str:
    if pd.isna(val):
        return ""
    s = str(val).strip()
    s = s.split(".")[0]
    return re.sub(r"\D", "", s)

def normalize_and_validate_id(series: pd.Series, min_len: int = MIN_ID_LEN) -> pd.Series:
    s = series.apply(id_temizle)
    return s.where(s.str.len() >= min_len, "")

def yil_coz(no: str) -> str:
    s = str(no).strip()
    if len(s) >= 3 and s[1:3].isdigit():
        return "20" + s[1:3]
    return "Belirsiz"

def list_xlsx_files(folder: str) -> List[str]:
    return sorted([f for f in os.listdir(folder) if f.lower().endswith(".xlsx")])

def pick_id_column(df: pd.DataFrame, min_len: int = MIN_ID_LEN):
    cols = [normalize_colname(c) for c in df.columns]
    dfx = df.copy()
    dfx.columns = cols

    candidates = [c for c in cols if ("öğrenci" in c or "ogrenci" in c or "student" in c)]
    if not candidates:
        candidates = [c for c in cols if ("no" in c or "number" in c)]

    best_col, best_score = None, -1
    for c in candidates:
        penalty = 60 if any(k in c for k in ["sıra", "sira", "index", "row", "satır", "satir", "sr no", "s.no"]) else 0
        series = dfx[c].apply(id_temizle)
        series = series[series != ""]
        if series.empty:
            continue
        lens = series.str.len()
        score = (lens >= min_len).mean() * 100 + lens.median() - penalty
        if score > best_score:
            best_score = score
            best_col = c
    return best_col

def build_fullname(df: pd.DataFrame) -> pd.Series:
    df2 = df.copy()
    df2.columns = [normalize_colname(c) for c in df2.columns]
    cols = list(df2.columns)

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

    return full.str.replace(r"\s+", " ", regex=True).str.strip()

def standardize_pc_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    rename_map = {}
    for c in out.columns:
        cl = normalize_colname(c)
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
    path = os.path.join(folder, MEZUN_DOSYA_ADI)
    if not os.path.exists(path):
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
    except Exception as e:
        log.append(f"❌ Mezun listesi okunamadı: {e}")
        return set()
    return mezun_ids


# =======================
#  CACHE: Excel'ler sadece veri değişince okunur
# =======================
@st.cache_data(show_spinner=False)
def build_result_table_cached(folder: str, data_version: int):
    log = []
    arsiv = list_xlsx_files(folder)
    if not arsiv:
        return None, log

    mezunlar = read_mezun_listesi(folder, log)
    ders_arsiv = [f for f in arsiv if f != MEZUN_DOSYA_ADI]

    all_dfs = []
    for f_name in ders_arsiv:
        full_path = os.path.join(folder, f_name)
        try:
            df_dict = pd.read_excel(full_path, sheet_name=None)
        except Exception as e:
            log.append(f"❌ {f_name}: okunamadı ({e})")
            continue

        for sh, df in df_dict.items():
            if df is None or df.empty:
                continue

            df = df.copy()
            df.columns = [normalize_colname(c) for c in df.columns]

            pc_cols = [c for c in df.columns if (("pc" in c) or ("pç" in c) or ("pç" in c)) and re.search(r"\d+", c)]
            if not pc_cols:
                continue

            id_col = pick_id_column(df, min_len=MIN_ID_LEN)
            if not id_col:
                continue

            temp = df[[id_col] + pc_cols].copy()
            temp.rename(columns={id_col: "ID"}, inplace=True)

            temp["ID"] = normalize_and_validate_id(temp["ID"], min_len=MIN_ID_LEN)
            temp = temp[temp["ID"] != ""].copy()
            if temp.empty:
                continue

            temp["Ad Soyad"] = build_fullname(df)
            temp = standardize_pc_columns(temp)
            temp = coerce_pc_to01(temp)

            all_dfs.append(temp)

    if not all_dfs:
        log.append("⚠️ Hiçbir dosyada PC/PÇ + ID birlikte yakalanamadı.")
        return None, log

    final = pd.concat(all_dfs, ignore_index=True)

    agg = {"Ad Soyad": first_non_empty}
    for c in final.columns:
        if str(c).startswith("PC"):
            agg[c] = "max"

    res = final.groupby("ID", as_index=False).agg(agg)
    res["Ad Soyad"] = res["Ad Soyad"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip().str.title()
    res["Durum"] = res["ID"].apply(lambda x: "🎓 MEZUN" if x in mezunlar else "📝 ÖĞRENCİ")
    res["Yıl"] = res["ID"].apply(yil_coz)

    return res, log


# =======================
#  SESSION STATE
# =======================
if "refresh" not in st.session_state:
    st.session_state.refresh = 0
if "debug_mode" not in st.session_state:
    st.session_state.debug_mode = False
if "data_version" not in st.session_state:
    st.session_state.data_version = 0

def trigger_refresh():
    # Veri değişti -> cache invalidation
    st.session_state.data_version += 1
    st.session_state.refresh += 1


# =======================
#  SIDEBAR
# =======================
with st.sidebar:
    st.header("🔐 Yönetim")
    pw = st.text_input("Şifre:", type="password")

    if pw == SIFRE:
        st.session_state.debug_mode = st.checkbox("🛠️ Teşhis Modu (geçici)", value=st.session_state.debug_mode)

        st.subheader("1) Ders Excel'leri")
        ders_dosyalar = st.file_uploader("Ders dosyalarını yükle (.xlsx)", type=["xlsx"], accept_multiple_files=True)

        if st.button("💾 Ders dosyalarını kaydet", use_container_width=True):
            if ders_dosyalar:
                for f in ders_dosyalar:
                    atomic_write(os.path.join(VERI_KLASORU, f.name), f.getvalue())
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
                atomic_write(os.path.join(VERI_KLASORU, MEZUN_DOSYA_ADI), mezun_dosya.getvalue())
                st.success("Mezun listesi kaydedildi.")
                trigger_refresh()
            else:
                st.warning("Mezun listesi dosyası seçilmedi.")

        st.divider()

        st.subheader("3) Kayıtlı dosyalar / Sil")
        arsiv = list_xlsx_files(VERI_KLASORU)
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

# controlled rerun
if st.session_state.refresh > 0:
    st.session_state.refresh = 0
    st.rerun()


# =======================
#  MAIN
# =======================
st.title("📊 Öğrenci Akreditasyon (PC/PÇ) Takip Sistemi")

arsiv_names = list_xlsx_files(VERI_KLASORU)
if not arsiv_names:
    st.info("Veri yok. Sol menüden Excel dosyalarını yükleyin.")
    st.stop()

if st.session_state.debug_mode:
    with st.expander("🧰 Sistem Durumu", expanded=False):
        st.write(f"📁 Klasör: `{VERI_KLASORU}`")
        st.write(f"📄 Bulunan .xlsx: **{len(arsiv_names)}**")
        st.write(arsiv_names)
        st.write(f"🧩 data_version: {st.session_state.data_version}")

with st.spinner("İlk açılışta dosyalar okunuyor (sonraki filtrelerde çok hızlı olacak)..."):
    res, log = build_result_table_cached(VERI_KLASORU, st.session_state.data_version)

if res is None or res.empty:
    st.error("Tablo üretilemedi. PC/PÇ kolonları veya ID kolonu bulunamadı.")
    st.info("Teşhis Modu’nu açarsanız detaylı log görüntülenir.")
    if st.session_state.debug_mode:
        with st.expander("🧾 Log", expanded=True):
            st.write("\n".join(log) if log else "Log yok.")
    st.stop()

mezun_count = int((res["Durum"] == "🎓 MEZUN").sum())
st.success(f"✅ Hazır: {len(res)} öğrenci | Mezun: {mezun_count} | Dosya: {len(arsiv_names)}")

# =======================
#  FILTERS (RAM üzerinde, çok hızlı)
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

filtered = res
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

st.caption(f"Gösterilen kayıt: {len(filtered)}")
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

if st.session_state.debug_mode:
    with st.expander("🧾 Log (özet)", expanded=False):
        st.write("\n".join(log[:200]) if log else "Log yok.")
