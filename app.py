import streamlit as st
import pandas as pd
import os
import shutil
import gc
import re

# Sayfa Ayarları
st.set_page_config(page_title="Akredite Takip Sistemi", layout="wide")

# --- 1. AYARLAR ---
VERI_KLASORU = "Veri_Kayitlari"
if not os.path.exists(VERI_KLASORU): os.makedirs(VERI_KLASORU)

YONETICI_SIFRESI = "akredite2026"
all_data = []
mezun_id_listesi = []
arsiv_dosyalari = [f for f in os.listdir(VERI_KLASORU) if f.endswith('.xlsx') or f.endswith('.dat')]

st.title("🎓 Akredite Takip ve Öğrenci Denetim Paneli")

# --- 2. FONKSİYONLAR (SÜPER TEMİZLEYİCİ) ---
def id_temizle(val):
    # Sadece rakamları tutar, diğer her şeyi siler (Hafıza hatalarını önler)
    s = str(val).strip()
    return re.sub(r'\D', '', s)

def veri_temizle(df):
    df.columns = df.columns.astype(str).str.strip().str.lower()
    df.columns = df.columns.str.replace('ç', 'c').str.replace('ğ', 'g').str.replace('ı', 'i').str.replace('ö', 'o').str.replace('ş', 's').str.replace('ü', 'u')
    return df

def yil_coz(ogrenci_no):
    no_str = str(ogrenci_no)
    if len(no_str) >= 3: return "20" + no_str[1:3]
    return "Belirsiz"

# --- 3. VERİ OKUMA ---
if arsiv_dosyalari:
    for file_name in arsiv_dosyalari:
        file_path = os.path.join(VERI_KLASORU, file_name)
        try:
            gc.collect()
            if file_name == "resmi_mezun_listesi_ozel.dat":
                m_df = pd.read_excel(file_path, engine='openpyxl')
                m_df = veri_temizle(m_df)
                m_id_col = next((c for c in m_df.columns if 'no' in c or 'numara' in c), None)
                if m_id_col: mezun_id_listesi = m_df[m_id_col].apply(id_temizle).tolist()
                del m_df
                continue

            xls = pd.ExcelFile(file_path, engine='openpyxl')
            ders_adi = file_name.replace(".xlsx", "")
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
                    
                    # İsim Birleştirme
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
        except Exception as e: st.error(f"Hata: {file_name} -> {e}")

# --- 4. BİRLEŞTİRME VE MÜKERRER KAYITLARI SIFIRLAMA ---
if all_data:
    final_df = all_data[0]
    for d in all_data[1:]:
        final_df = pd.merge(final_df, d, on='ID', how='outer')
    
    # İsimleri harmanla
    n_cols = [c for c in final_df.columns if c.startswith('Name_')]
    final_df['Ad Soyad'] = final_df[n_cols].bfill(axis=1).iloc[:, 0] if n_cols else "Bilinmiyor"
    
    # PC Analizi
    pc_list = [f"PC{i}" for i in range(1, 12)]
    consolidated = pd.DataFrame()
    consolidated['ID'] = final_df['ID']
    consolidated['Ad Soyad'] = final_df['Ad Soyad']

    for pc in pc_list:
        relevant = [c for c in final_df.columns if c.startswith(pc)]
        consolidated[pc] = final_df[relevant].apply(lambda row: 1 if 1 in row.values else 0, axis=1) if relevant else 0

    # --- KRİTİK: GRUPLAMA (Çift Kayıtları Teke İndirir) ---
    # Eğer hala aynı ID'den iki tane varsa, PC verilerini birleştirip teke düşürür
    consolidated = consolidated.groupby('ID').agg({
        'Ad Soyad': 'first',
        **{pc: 'max' for pc in pc_list}
    }).reset_index()

    consolidated['Başarı (11)'] = consolidated[pc_list].sum(axis=1)
    consolidated['Resmi Durum'] = consolidated['ID'].apply(lambda x: "🎓 MEZUN" if x in mezun_id_listesi else "📝 ÖĞRENCİ")
    consolidated['Giriş Yılı'] = consolidated['ID'].apply(yil_coz)

    # --- ARAYÜZ ---
    st.subheader("📊 Akredite Takip Paneli")
    f1, f2 = st.columns(2)
    with f1: ana_filtre = st.radio("Süzgeç:", ["Hepsi", "Sadece Öğrenciler", "Sadece Mezunlar"], horizontal=True)
    
    temp_filt = consolidated.copy()
    if ana_filtre == "Sadece Öğrenciler": temp_filt = temp_filt[temp_filt['Resmi Durum'] == "📝 ÖĞRENCİ"]
    elif ana_filtre == "Sadece Mezunlar": temp_filt = temp_filt[temp_filt['Resmi Durum'] == "🎓 MEZUN"]
    
    with f2:
        yillar = sorted([y for y in temp_filt['Giriş Yılı'].unique() if y != "Belirsiz"])
        yil_filtre = st.selectbox("Giriş Yılı:", ["Tüm Yıllar"] + yillar)

    if yil_filtre != "Tüm Yıllar": temp_filt = temp_filt[temp_filt['Giriş Yılı'] == yil_filtre]
    
    st.dataframe(temp_filt, use_container_width=True)
    st.download_button("📥 İndir", temp_filt.to_csv(index=False).encode('utf-8-sig'), "rapor.csv")
else:
    st.info("Sistem boş. Sol panelden veri yükleyin.")
