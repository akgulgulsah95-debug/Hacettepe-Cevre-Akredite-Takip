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

# --- 2. FONKSİYONLAR ---
def id_temizle(val):
    s = str(val).strip().split('.')[0]
    return re.sub(r'\D', '', s)

def yil_coz(ogrenci_no):
    no_str = str(ogrenci_no).strip()
    if len(no_str) >= 3:
        return "20" + no_str[1:3]
    return "Belirsiz"

def veri_temizle(df):
    df.columns = df.columns.astype(str).str.strip().str.lower()
    df.columns = df.columns.str.replace('ç', 'c').str.replace('ğ', 'g').str.replace('ı', 'i').str.replace('ö', 'o').str.replace('ş', 's').str.replace('ü', 'u')
    return df

# --- 3. YÖNETİCİ PANELİ (SOL SİDEBAR) ---
with st.sidebar:
    st.header("🔐 Yönetim Paneli")
    girilen_sifre = st.text_input("Şifre girin:", type="password")
    
    if girilen_sifre == YONETICI_SIFRESI:
        st.success("Yönetici Modu Aktif")
        st.divider()
        st.header("📥 Yeni Dosya Yükle")
        
        yeni_dersler = st.file_uploader("Ders Dosyaları", accept_multiple_files=True, type=['xlsx'])
        yeni_mezun = st.file_uploader("Mezun Listesi", type=['xlsx'])
        
        # Buton işlemi: Dosyaları yaz ve anında göster
        if st.button("💾 Kaydet ve Analiz Et", use_container_width=True):
            islem_yapildi = False
            if yeni_dersler:
                for f in yeni_dersler:
                    with open(os.path.join(VERI_KLASORU, f.name), "wb") as buffer:
                        buffer.write(f.getbuffer())
                islem_yapildi = True
            
            if yeni_mezun:
                with open(os.path.join(VERI_KLASORU, "resmi_mezun_listesi_ozel.dat"), "wb") as buffer:
                    buffer.write(yeni_mezun.getbuffer())
                islem_yapildi = True
            
            if islem_yapildi:
                st.success("Veriler Arşivlendi!")
                st.rerun() # Sayfayı otomatik olarak en güncel veriyle başlatır

        st.divider()
        st.header("📂 Arşiv Yönetimi")
        mevcut_arsiv = [f for f in os.listdir(VERI_KLASORU) if f.endswith('.xlsx') or f.endswith('.dat')]
        if mevcut_arsiv:
            silinecek = st.selectbox("Dosya Sil:", ["Seçiniz..."] + mevcut_arsiv)
            if silinecek != "Seçiniz..." and st.button(f"🗑️ Sil"):
                os.remove(os.path.join(VERI_KLASORU, silinecek))
                st.rerun()
    else:
        st.info("Düzenleme için şifre gereklidir.")

# --- 4. VERİ ANALİZ MOTORU ---
st.title("🎓 Akredite Takip ve Öğrenci Denetim Paneli")

all_data = []
mezun_id_listesi = []
arsiv_dosyalari = [f for f in os.listdir(VERI_KLASORU) if f.endswith('.xlsx') or f.endswith('.dat')]

if arsiv_dosyalari:
    for file_name in arsiv_dosyalari:
        file_path = os.path.join(VERI_KLASORU, file_name)
        try:
            gc.collect()
            if "mezun" in file_name.lower() or file_name.endswith(".dat"):
                m_df = pd.read_excel(file_path, engine='openpyxl')
                m_df = veri_temizle(m_df)
                m_id_col = next((c for c in m_df.columns if 'number' in c or 'no' in c or 'numara' in c), None)
                if m_id_col: mezun_id_listesi.extend(m_df[m_id_col].apply(id_temizle).tolist())
                continue

            xls = pd.ExcelFile(file_path, engine='openpyxl')
            ders_adi = file_name.replace(".xlsx", "")
            for sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                df = veri_temizle(df)
                
                std_num_col = next((c for c in df.columns if 'number' in c or 'no' in c or 'numara' in c), None)
                # Ad-Soyad Ayrıysa Birleştirme
                ad_col = next((c for c in df.columns if ('ad' in c or 'name' in c) and 'soyad' not in c and 'surname' not in c), None)
                soyad_col = next((c for c in df.columns if 'soyad' in c or 'surname' in c), None)
                
                pc_cols = [c for c in df.columns if c.startswith('pc')]
                
                if std_num_col and pc_cols:
                    temp_df = df[[std_num_col] + pc_cols].copy()
                    temp_df.rename(columns={std_num_col: 'ID'}, inplace=True)
                    temp_df['ID'] = temp_df['ID'].apply(id_temizle)
                    
                    # Dinamik İsim Oluşturma
                    c_name = f'Name_{ders_adi}'
                    if ad_col and soyad_col:
                        temp_df[c_name] = df[ad_col].astype(str).str.title() + " " + df[soyad_col].astype(str).str.title()
                    elif ad_col:
                        temp_df[c_name] = df[ad_col].astype(str).str.title()
                    
                    for pc in pc_cols:
                        temp_df.rename(columns={pc: f"{pc.upper()} ({ders_adi})"}, inplace=True)
                    all_data.append(temp_df)
            xls.close()
        except: continue

# --- 5. BİRLEŞTİRME VE GÖRÜNÜM ---
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

    # Çift kayıtları teke indir
    consolidated = consolidated.groupby('Öğrenci No').agg({'Ad Soyad': 'first', **{pc: 'max' for pc in pc_list}}).reset_index()

    consolidated['Başarı (11)'] = consolidated[pc_list].sum(axis=1)
    consolidated['Durum'] = consolidated['Öğrenci No'].apply(lambda x: "🎓 MEZUN" if x in mezun_id_listesi else "📝 ÖĞRENCİ")
    consolidated['Giriş Yılı'] = consolidated['Öğrenci No'].apply(yil_coz)

    # Filtreler
    c1, c2 = st.columns(2)
    with c1: filter_type = st.radio("Süzgeç:", ["Hepsi", "Öğrenciler", "Mezunlar"], horizontal=True)
    temp_filt = consolidated.copy()
    if filter_type == "Öğrenciler": temp_filt = temp_filt[temp_filt['Durum'] == "📝 ÖĞRENCİ"]
    elif filter_type == "Mezunlar": temp_filt = temp_filt[temp_filt['Durum'] == "🎓 MEZUN"]
    
    with c2:
        yillar = sorted([y for y in temp_filt['Giriş Yılı'].unique() if y != "Belirsiz"])
        yil_filtre = st.selectbox("Giriş Yılı:", ["Tüm Yıllar"] + yillar)
    if yil_filtre != "Tüm Yıllar": temp_filt = temp_filt[temp_filt['Giriş Yılı'] == yil_filtre]
    
    st.dataframe(temp_filt, use_container_width=True)
    st.download_button("📥 Excel İndir", temp_filt.to_csv(index=False).encode('utf-8-sig'), "rapor.csv")
else:
    st.info("Veri Kayitlari klasörü boş veya dosyalar okunamadı. Lütfen sol panelden yükleme yapın.")
