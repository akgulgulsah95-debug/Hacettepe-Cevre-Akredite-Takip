import streamlit as st
import pandas as pd
import os
import shutil
import gc
import re

# --- 1. SAYFA AYARLARI (EN BAŞTA OLMALI) ---
st.set_page_config(page_title="Akredite Takip Sistemi", layout="wide")

# --- 2. DEĞİŞKENLER VE KLASÖR AYARLARI ---
VERI_KLASORU = "Veri_Kayitlari"
if not os.path.exists(VERI_KLASORU):
    os.makedirs(VERI_KLASORU)

YONETICI_SIFRESI = "akredite2026"
all_data = []
mezun_id_listesi = []

# Klasörü tara
arsiv_dosyalari = [f for f in os.listdir(VERI_KLASORU) if f.endswith('.xlsx') or f.endswith('.dat')]

# --- 3. YARDIMCI FONKSİYONLAR ---
def id_temizle(val):
    s = str(val).strip()
    return re.sub(r'\D', '', s) # Sadece rakamları tutar

def veri_temizle(df):
    df.columns = df.columns.astype(str).str.strip().str.lower()
    df.columns = df.columns.str.replace('ç', 'c').str.replace('ğ', 'g').str.replace('ı', 'i').str.replace('ö', 'o').str.replace('ş', 's').str.replace('ü', 'u')
    return df

def yil_coz(ogrenci_no):
    no_str = str(ogrenci_no)
    if len(no_str) >= 3:
        return "20" + no_str[1:3]
    return "Belirsiz"

# --- 4. SOL PANEL (SIDEBAR) - ARTIK KAYBOLMAYACAK ---
with st.sidebar:
    st.header("🔐 Yönetim Paneli")
    st.title("🎓 Akredite Takip")
    girilen_sifre = st.text_input("Şifre Girin:", type="password")
    
    if girilen_sifre == YONETICI_SIFRESI:
        st.success("Yönetici Modu Aktif")
        st.divider()
        st.header("📥 Dosya Yükle")
        yeni_dersler = st.file_uploader("Ders Dosyaları (.xlsx)", accept_multiple_files=True, type=['xlsx'])
        yeni_mezun = st.file_uploader("Mezun Listesi (.xlsx)", type=['xlsx'])
        
        if st.button("💾 Kaydet ve Arşivle"):
            if yeni_dersler:
                for f in yeni_dersler:
                    with open(os.path.join(VERI_KLASORU, f.name), "wb") as buffer:
                        shutil.copyfileobj(f, buffer)
            if yeni_mezun:
                with open(os.path.join(VERI_KLASORU, "resmi_mezun_listesi_ozel.dat"), "wb") as buffer:
                    shutil.copyfileobj(yeni_mezun, buffer)
            st.rerun()

        st.divider()
        st.header("📂 Arşiv")
        if arsiv_dosyalari:
            silinecek = st.selectbox("Dosya Sil:", ["Seçiniz..."] + arsiv_dosyalari)
            if silinecek != "Seçiniz..." and st.button(f"🗑️ Sil"):
                os.remove(os.path.join(VERI_KLASORU, silinecek))
                st.rerun()
    else:
        st.info("İnceleme modu. Veri girişi için şifre gereklidir.")

# --- 5. ANA BAŞLIK ---
st.title("📊 Akredite Takip ve Öğrenci Denetim Paneli")

# --- 6. VERİ OKUMA VE BİRLEŞTİRME ---
if arsiv_dosyalari:
    for file_name in arsiv_dosyalari:
        file_path = os.path.join(VERI_KLASORU, file_name)
        try:
            gc.collect()
            if file_name == "resmi_mezun_listesi_ozel.dat":
                m_df = pd.read_excel(file_path, engine='openpyxl')
                m_df = veri_temizle(m_df)
                m_id_col = next((c for c in m_df.columns if 'no' in c or 'numara' in c), None)
                if m_id_col:
                    mezun_id_listesi = m_df[m_id_col].apply(id_temizle).tolist()
                del m_df
                continue

            xls = pd.ExcelFile(file_path, engine='openpyxl')
            ders_adi = file_name.replace(".xlsx", "").replace(".XLSX", "")
            for sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                df = veri_temizle(df)
                std_num_col = next((c for c in df.columns if 'no' in c or 'numara' in c), None)
                name_col = next((c for c in df.columns if 'ad' in c or 'name' in c), None)
                surname_col = next((c for c in df.columns if 'soyad' in c or 'surname' in c), None)
                pc_cols = [c for c in df.columns if c.startswith('pc')]
                
                if std_num_col and pc_cols:
                    temp_df = df[[std_num_col] + pc_cols].copy()
                    temp_df.rename(columns={std_num_col: 'ID'}, inplace=True)
                    temp_df['ID'] = temp_df['ID'].apply(id_temizle)
                    
                    c_name = f'Name_{ders_adi}'
                    if name_col and surname_col:
                        temp_df[c_name] = df[name_col].astype(str).str.title() + " " + df[surname_col].astype(str).str.title()
                    elif name_col:
                        temp_df[c_name] = df[name_col].astype(str).str.title()

                    for pc in pc_cols:
                        temp_df.rename(columns={pc: f"{pc.upper()} ({ders_adi})"}, inplace=True)
                    
                    all_data.append(temp_df)
                del df
            xls.close()
        except Exception as e:
            st.error(f"Hata ({file_name}): {e}")

# --- 7. TABLO OLUŞTURMA VE GÖSTERİM ---
if all_data:
    final_df = all_data[0]
    for d in all_data[1:]:
        final_df = pd.merge(final_df, d, on='ID', how='outer')
    
    n_cols = [c for c in final_df.columns if c.startswith('Name_')]
    final_df['Ad Soyad'] = final_df[n_cols].bfill(axis=1).iloc[:, 0] if n_cols else "Bilinmiyor"
    
    pc_list = [f"PC{i}" for i in range(1, 12)]
    consolidated = pd.DataFrame()
    consolidated['ID'] = final_df['ID']
    consolidated['Ad Soyad'] = final_df['Ad Soyad']

    for pc in pc_list:
        relevant = [c for c in final_df.columns if c.startswith(pc)]
        consolidated[pc] = final_df[relevant].apply(lambda row: 1 if 1 in row.values else 0, axis=1) if relevant else 0

    # Çift kayıtları temizle (ID'ye göre grupla)
    consolidated = consolidated.groupby('ID').agg({'Ad Soyad': 'first', **{pc: 'max' for pc in pc_list}}).reset_index()

    consolidated['Başarı (11)'] = consolidated[pc_list].sum(axis=1)
    consolidated['Resmi Durum'] = consolidated['ID'].apply(lambda x: "🎓 MEZUN" if x in mezun_id_listesi else "📝 ÖĞRENCİ")
    consolidated['Giriş Yılı'] = consolidated['ID'].apply(yil_coz)

    # --- FİLTRELER ---
    f1, f2 = st.columns(2)
    with f1:
        ana_filtre = st.radio("Durum:", ["Hepsi", "Öğrenciler", "Mezunlar"], horizontal=True)
    
    temp_filt = consolidated.copy()
    if ana_filtre == "Öğrenciler": temp_filt = temp_filt[temp_filt['Resmi Durum'] == "📝 ÖĞRENCİ"]
    elif ana_filtre == "Mezunlar": temp_filt = temp_filt[temp_filt['Resmi Durum'] == "🎓 MEZUN"]
    
    with f2:
        yillar = sorted([y for y in temp_filt['Giriş Yılı'].unique() if y != "Belirsiz"])
        yil_filtre = st.selectbox("Giriş Yılı:", ["Tümü"] + yillar)
    if yil_filtre != "Tümü": temp_filt = temp_filt[temp_filt['Giriş Yılı'] == yil_filtre]
    
    st.dataframe(temp_filt, use_container_width=True)
    st.download_button("📥 Excel Raporu İndir", temp_filt.to_csv(index=False).encode('utf-8-sig'), "rapor.csv")

    # Karneler
    st.divider()
    secim = st.selectbox("Öğrenci Detayı:", consolidated.apply(lambda x: f"{x['ID']} - {x['Ad Soyad']}", axis=1))
    if secim:
        s_id = secim.split(" - ")[0]
        row = consolidated[consolidated['ID'] == s_id].iloc[0]
        st.write(f"### {row['Ad Soyad']} ({row['Resmi Durum']})")
        cols = st.columns(11)
        for i, p in enumerate(pc_list):
            clr = "#28a745" if row[p] == 1 else "#dc3545"
            cols[i].markdown(f"<div style='background-color:{clr}; color:white; padding:10px; border-radius:10px; text-align:center;'>{p}</div>", unsafe_allow_html=True)
else:
    st.info("Sistem şu an boş veya dosyalar okunamadı. Lütfen sol panelden verileri kontrol edin.")
