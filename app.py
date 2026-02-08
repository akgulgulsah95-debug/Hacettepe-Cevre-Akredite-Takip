import streamlit as st
import pandas as pd
import os
import shutil
import gc
import re

# --- 1. SAYFA AYARLARI ---
st.set_page_config(page_title="Hacettepe Çevre Akredite Takip", layout="wide")

VERI_KLASORU = "Veri_Kayitlari"
if not os.path.exists(VERI_KLASORU):
    os.makedirs(VERI_KLASORU)

YONETICI_SIFRESI = "akredite2026"

# --- 2. GELİŞMİŞ NORMALİZASYON FONKSİYONLARI ---
def id_temizle(val):
    s = str(val).strip().split('.')[0]
    return re.sub(r'\D', '', s)

def sütun_normalize(col_name):
    # Sütun isimlerini eşleşme için standart hale getirir
    s = str(col_name).strip().lower()
    s = s.replace('ç', 'c').replace('ğ', 'g').replace('ı', 'i').replace('ö', 'o').replace('ş', 's').replace('ü', 'u')
    s = s.replace(' ', '').replace('_', '').replace('-', '')
    return s

# --- 3. SIDEBAR (YÖNETİM PANELİ) ---
with st.sidebar:
    st.header("🔐 Yönetim Paneli")
    mevcutlar = [f for f in os.listdir(VERI_KLASORU) if f.endswith('.xlsx') or f.endswith('.dat')]
    
    if mevcutlar:
        st.subheader("📂 Arşivdeki Dosyalar")
        for m in mevcutlar: st.caption(f"• {m}")
    
    st.divider()
    sifre = st.text_input("Yönetici Şifresi:", type="password")
    
    if sifre == YONETICI_SIFRESI:
        st.success("Yönetici Erişimi Aktif")
        y_ders = st.file_uploader("Excel Yükle", accept_multiple_files=True, type=['xlsx'])
        if st.button("💾 Kaydet ve Analiz Et"):
            if y_ders:
                for f in y_ders:
                    with open(os.path.join(VERI_KLASORU, f.name), "wb") as b:
                        b.write(f.getbuffer())
                st.rerun()
        
        if mevcutlar:
            st.divider()
            secilen = st.selectbox("Dosya Sil:", ["Seç..."] + mevcutlar)
            if secilen != "Seç..." and st.button("🗑️ SİL"):
                os.remove(os.path.join(VERI_KLASORU, secilen))
                st.rerun()

# --- 4. ANA EKRAN VE VERİ İŞLEME ---
st.title("🎓 Akredite Takip ve Öğrenci Denetim Paneli")

all_data = []
mezun_id_listesi = []

if mevcutlar:
    for file_name in mevcutlar:
        file_path = os.path.join(VERI_KLASORU, file_name)
        try:
            gc.collect()
            if file_name == "resmi_mezun_listesi_ozel.dat":
                m_df = pd.read_excel(file_path, engine='openpyxl')
                id_col = next((c for c in m_df.columns if 'no' in sütun_normalize(c) or 'number' in sütun_normalize(c)), None)
                if id_col: mezun_id_listesi = m_df[id_col].apply(id_temizle).tolist()
                continue

            xls = pd.ExcelFile(file_path, engine='openpyxl')
            ders_adi = file_name.replace(".xlsx", "").replace(".XLSX", "")
            
            for sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                
                # Sütun Tespiti (Gelişmiş Filtreleme)
                std_num_col = next((c for c in df.columns if 'studentnumber' in sütun_normalize(c) or 'ogrencino' in sütun_normalize(c)), None)
                name_col = next((c for c in df.columns if 'namesurname' in sütun_normalize(c) or 'adsoyad' in sütun_normalize(c)), None)
                surname_col = next((c for c in df.columns if 'surname' in sütun_normalize(c) or 'soyad' in sütun_normalize(c)), None)
                # PC veya PÇ ile başlayan tüm sütunları yakala
                pc_cols = [c for c in df.columns if sütun_normalize(c).startswith('pc') or sütun_normalize(c).startswith('pc')]
                
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
                    
                    # PC Başlıklarını Standartlaştır: "PC1 (DersAdı)"
                    for pc in pc_cols:
                        clean_pc = sütun_normalize(pc).upper().replace('PC', 'PC')
                        temp_df.rename(columns={pc: f"{clean_pc} ({ders_adi})"}, inplace=True)
                    
                    all_data.append(temp_df)
            xls.close()
        except Exception as e:
            st.warning(f"⚠️ {file_name} okunurken bir sorun oluştu.")

# --- 5. BİRLEŞTİRME VE TABLO ---
if all_data:
    final_df = all_data[0]
    for d in all_data[1:]:
        final_df = pd.merge(final_df, d, on='ID', how='outer')
    
    n_cols = [c for c in final_df.columns if c.startswith('Name_')]
    final_df['Ad Soyad'] = final_df[n_cols].bfill(axis=1).iloc[:, 0] if n_cols else "Bilinmiyor"
    
    pc_list = [f"PC{i}" for i in range(1, 12)]
    consolidated = pd.DataFrame()
    consolidated['Öğrenci No'] = final_df['ID']
    consolidated['Ad Soyad'] = final_df['Ad Soyad']

    for pc in pc_list:
        relevant = [c for c in final_df.columns if c.split(' ')[0] == pc]
        if relevant:
            consolidated[pc] = final_df[relevant].apply(lambda row: 1 if 1 in row.values else 0, axis=1)
        else:
            consolidated[pc] = 0

    # ID'ye göre grupla (Çift kayıtları engeller)
    consolidated = consolidated.groupby('Öğrenci No').agg({'Ad Soyad': 'first', **{pc: 'max' for pc in pc_list}}).reset_index()
    
    consolidated['Başarı (11)'] = consolidated[pc_list].sum(axis=1)
    consolidated['Durum'] = consolidated['Öğrenci No'].apply(lambda x: "🎓 MEZUN" if x in mezun_id_listesi else "📝 ÖĞRENCİ")

    st.subheader("📊 Genel Akreditasyon Tablosu")
    st.dataframe(consolidated, use_container_width=True)
    
    csv = consolidated.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 Tüm Listeyi İndir (CSV)", csv, "akredite_rapor.csv")
else:
    st.info("Sistemde dosya var ancak 'Student Number' veya 'PC/PÇ' sütunları eşleşmedi. Lütfen sol panelden dosyalarınızı kontrol edin.")
