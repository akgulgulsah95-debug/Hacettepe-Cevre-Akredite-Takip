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
if not os.path.exists(VERI_KLASORU):
    os.makedirs(VERI_KLASORU)

YONETICI_SIFRESI = "akredite2026"
all_data = []
mezun_id_listesi = []

# Arşivdeki dosyaları al
arsiv_dosyalari = [f for f in os.listdir(VERI_KLASORU) if f.endswith('.xlsx') or f.endswith('.dat')]

st.title("🎓 Akredite Takip ve Öğrenci Denetim Paneli")

# --- 2. YÖNETİCİ PANELİ (Garantici Buton Yapısı) ---
with st.sidebar:
    st.header("🔐 Yönetim Paneli")
    girilen_sifre = st.text_input("Şifre girin:", type="password")
    
    if girilen_sifre == YONETICI_SIFRESI:
        st.success("Yönetici Modu Aktif")
        st.divider()
        st.header("📥 Yeni Dosya Yükle")
        
        # Butonun donmasını engellemek için dosyaları hafızaya alıyoruz
        yeni_dersler = st.file_uploader("Ders Dosyaları", accept_multiple_files=True, type=['xlsx'], key="uploader_ders")
        yeni_mezun = st.file_uploader("Mezun Listesi", type=['xlsx'], key="uploader_mezun")
        
        if st.button("💾 Kaydet ve Arşivle", use_container_width=True):
            if yeni_dersler:
                for f in yeni_dersler:
                    with open(os.path.join(VERI_KLASORU, f.name), "wb") as buffer:
                        buffer.write(f.getbuffer())
                st.success("Dersler kaydedildi!")
            if yeni_mezun:
                with open(os.path.join(VERI_KLASORU, "resmi_mezun_listesi_ozel.dat"), "wb") as buffer:
                    buffer.write(yeni_mezun.getbuffer())
                st.success("Mezun listesi kaydedildi!")
            # st.rerun() yerine sayfanın kendisini yenilemesini bekliyoruz, bu butonun kitlenmesini önler.
            st.info("Değişiklikleri görmek için lütfen sayfayı yenileyin.")

        st.divider()
        st.header("📂 Arşiv Yönetimi")
        if arsiv_dosyalari:
            silinecek = st.selectbox("Dosya Sil:", ["Seçiniz..."] + arsiv_dosyalari)
            if silinecek != "Seçiniz..." and st.button(f"🗑️ Sil"):
                os.remove(os.path.join(VERI_KLASORU, silinecek))
                st.warning("Dosya silindi.")
    else:
        st.info("Hocalar için sadece görüntüleme modu aktif.")

# --- 3. FONKSİYONLAR (Hatasız Mantık) ---
def veri_temizle(df):
    df.columns = df.columns.astype(str).str.strip().str.lower()
    df.columns = df.columns.str.replace('ç', 'c').str.replace('ğ', 'g').str.replace('ı', 'i').str.replace('ö', 'o').str.replace('ş', 's').str.replace('ü', 'u')
    return df

def id_temizle(val):
    s = str(val).strip().split('.')[0]
    return re.sub(r'\D', '', s)

def yil_coz(ogrenci_no):
    no_str = str(ogrenci_no).strip()
    if len(no_str) >= 3:
        return "20" + no_str[1:3]
    return "Belirsiz"

# --- 4. VERİ OKUMA VE AD-SOYAD BİRLEŞTİRME ---
if arsiv_dosyalari:
    for file_name in arsiv_dosyalari:
        file_path = os.path.join(VERI_KLASORU, file_name)
        try:
            gc.collect()
            if file_name == "resmi_mezun_listesi_ozel.dat":
                m_df = pd.read_excel(file_path, engine='openpyxl')
                m_df = veri_temizle(m_df)
                m_id_col = next((c for c in m_df.columns if 'number' in c or 'no' in c or 'numara' in c), None)
                if m_id_col: mezun_id_listesi = m_df[m_id_col].apply(id_temizle).tolist()
                del m_df
                continue

            xls = pd.ExcelFile(file_path, engine='openpyxl')
            ders_adi = file_name.replace(".xlsx", "")
            for sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                df = veri_temizle(df)
                
                std_num_col = next((c for c in df.columns if 'number' in c or 'no' in c or 'numara' in c), None)
                # Ad ve Soyad tespiti
                name_col = next((c for c in df.columns if ('ad' in c or 'name' in c) and 'soyad' not in c and 'surname' not in c), None)
                surname_col = next((c for c in df.columns if 'soyad' in c or 'surname' in c), None)
                pc_cols = [c for c in df.columns if c.startswith('pc')]
                
                if std_num_col and pc_cols:
                    temp_df = df[[std_num_col] + pc_cols].copy()
                    temp_df.rename(columns={std_num_col: 'ID'}, inplace=True)
                    temp_df['ID'] = temp_df['ID'].apply(id_temizle)
                    
                    # AD ve SOYAD BİRLEŞTİRME
                    c_name_col = f'Name_{ders_adi}'
                    if name_col and surname_col:
                        temp_df[c_name_col] = df[name_col].astype(str).str.title() + " " + df[surname_col].astype(str).str.title()
                    elif name_col:
                        temp_df[c_name_col] = df[name_col].astype(str).str.title()
                    
                    for pc in pc_cols:
                        temp_df.rename(columns={pc: f"{pc.upper()} ({ders_adi})"}, inplace=True)
                    all_data.append(temp_df)
            xls.close()
        except: continue

# --- 5. TABLO VE GÖRSELLEŞTİRME ---
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
        rel = [c for c in final_df.columns if c.startswith(pc)]
        consolidated[pc] = final_df[rel].apply(lambda r: 1 if 1 in r.values else 0, axis=1) if rel else 0

    # GRUPLAMA (İsim ve PC'leri tek satıra indirir)
    consolidated = consolidated.groupby('Öğrenci No').agg({'Ad Soyad': 'first', **{pc: 'max' for pc in pc_list}}).reset_index()

    consolidated['Başarı (11)'] = consolidated[pc_list].sum(axis=1)
    consolidated['Resmi Durum'] = consolidated['Öğrenci No'].apply(lambda x: "🎓 MEZUN" if x in mezun_id_listesi else "📝 ÖĞRENCİ")
    consolidated['Giriş Yılı'] = consolidated['Öğrenci No'].apply(yil_coz)

    # Filtreler
    st.subheader("📊 Akredite Takip Paneli")
    f1, f2 = st.columns(2)
    with f1: ana_filtre = st.radio("Süzgeç:", ["Hepsi", "Öğrenciler", "Mezunlar"], horizontal=True)
    temp_filt = consolidated.copy()
    if ana_filtre == "Öğrenciler": temp_filt = temp_filt[temp_filt['Resmi Durum'] == "📝 ÖĞRENCİ"]
    elif ana_filtre == "Mezunlar": temp_filt = temp_filt[temp_filt['Resmi Durum'] == "🎓 MEZUN"]
    
    with f2:
        yillar = sorted([y for y in temp_filt['Giriş Yılı'].unique() if y != "Belirsiz"])
        yil_filtre = st.selectbox("Giriş Yılı:", ["Tüm Yıllar"] + yillar)

    if yil_filtre != "Tüm Yıllar": temp_filt = temp_filt[temp_filt['Giriş Yılı'] == yil_filtre]
    
    st.dataframe(temp_filt, use_container_width=True)
    st.download_button("📥 Excel İndir", temp_filt.to_csv(index=False).encode('utf-8-sig'), "rapor.csv")
else:
    st.info("Sistem boş. Sol panelden yükleme yapın.")
