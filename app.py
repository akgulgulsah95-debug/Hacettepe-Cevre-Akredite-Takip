import streamlit as st
import pandas as pd
import os
import shutil
import gc 

# Verileri Okuma Bölümü
if arsiv_dosyalari:
    for file_name in arsiv_dosyalari:
        file_path = os.path.join(VERI_KLASORU, file_name)
        try:
            # Belleği rahatlatmak için her dosyadan önce temizlik yap
            gc.collect() 
            
            if file_name == "resmi_mezun_listesi_ozel.dat":
                # Mezun listesini daha az hafıza kullanarak oku
                m_df = pd.read_excel(file_path, engine='openpyxl')
                # ... (sütun işlemleri aynı kalsın)
                del m_df # İşlem bitince değişkeni sil
                continue

            # Ders dosyalarını okurken sadece gerekli sayfaları al
            xls = pd.ExcelFile(file_path, engine='openpyxl')
            for sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                # ... (diğer işlemler)
                del df # Her sayfa bittiğinde tabloyu hafızadan at
            
        except Exception as e:
            st.error(f"Hata: {file_name} -> {e}")
# Sayfa Ayarları
st.set_page_config(page_title="Akredite Takip Sistemi", layout="wide")

# --- KALICI DEPOLAMA AYARI ---
VERI_KLASORU = VERI_KLASORU = "Veri_Kayitlari"
if not os.path.exists(VERI_KLASORU):
    os.makedirs(VERI_KLASORU)

# --- ŞİFRE KONTROLÜ ---
YONETICI_SIFRESI = "akredite2026"

st.title("🎓 Akredite Takip ve Öğrenci Denetim Paneli")

# --- SOL PANEL: YÖNETİCİ GİRİŞİ ---
with st.sidebar:
    st.header("🔐 Yönetim Paneli")
    girilen_sifre = st.text_input("Dosya yönetimi için şifre girin:", type="password")
    
    if girilen_sifre == YONETICI_SIFRESI:
        st.success("Yönetici Modu Aktif")
        st.divider()
        st.header("📥 Yeni Dosya Yükle")
        yeni_dersler = st.file_uploader("Ders Dosyaları", accept_multiple_files=True, type=['xlsx'])
        yeni_mezun = st.file_uploader("Mezun Listesi", type=['xlsx'])
        
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
        st.header("📂 Arşiv Yönetimi")
        arsiv_dosyalari = [f for f in os.listdir(VERI_KLASORU) if f.endswith('.xlsx') or f.endswith('.dat')]
        if arsiv_dosyalari:
            silinecek = st.selectbox("Dosya Sil:", ["Seçiniz..."] + arsiv_dosyalari)
            if silinecek != "Seçiniz..." and st.button(f"🗑️ Sil: {silinecek}"):
                os.remove(os.path.join(VERI_KLASORU, silinecek))
                st.rerun()
    else:
        st.info("Sadece görüntüleme modu aktif. Veri girişi için yetkili şifresi gereklidir.")

# --- VERİ İŞLEME FONKSİYONLARI ---
def veri_temizle(df):
    df.columns = df.columns.astype(str).str.strip().str.lower().str.replace('ç', 'c')
    return df

def yil_coz(ogrenci_no):
    no_str = str(ogrenci_no).strip()
    if len(no_str) >= 8:
        return "20" + no_str[1:3]
    return "Belirsiz"

all_data = []
mezun_id_listesi = []
arsiv_dosyalari = [f for f in os.listdir(VERI_KLASORU) if f.endswith('.xlsx') or f.endswith('.dat')]

# Verileri Okuma
if arsiv_dosyalari:
    for file_name in arsiv_dosyalari:
        file_path = os.path.join(VERI_KLASORU, file_name)
        try:
            if file_name == "resmi_mezun_listesi_ozel.dat":
                m_df = pd.read_excel(file_path)
                m_df = veri_temizle(m_df)
                m_id_col = next((c for c in m_df.columns if 'number' in c or 'no' in c or 'numara' in c), None)
                if m_id_col: mezun_id_listesi = m_df[m_id_col].astype(str).tolist()
                continue

            xls = pd.ExcelFile(file_path)
            ders_adi = file_name.replace(".xlsx", "")
            for sheet in xls.sheet_names:
                df = pd.read_excel(file_path, sheet_name=sheet)
                df = veri_temizle(df)
                std_num_col = next((c for c in df.columns if 'number' in c or 'no' in c or 'numara' in c), None)
                name_col = next((c for c in df.columns if 'name' in c or 'ad' in c or 'soyad' in c), None)
                pc_cols = [c for c in df.columns if c.startswith('pc')]
                
                if std_num_col and pc_cols:
                    temp_df = df[[std_num_col] + ([name_col] if name_col else []) + pc_cols].copy()
                    temp_df[std_num_col] = temp_df[std_num_col].astype(str)
                    if name_col: temp_df[name_col] = temp_df[name_col].astype(str).str.title()
                    
                    rename_dict = {std_num_col: 'ID'}
                    if name_col: rename_dict[name_col] = f'Name_{ders_adi}'
                    for pc in pc_cols: rename_dict[pc] = f"{pc.upper()} ({ders_adi})"
                    
                    temp_df.rename(columns=rename_dict, inplace=True)
                    all_data.append(temp_df)
        except Exception as e:
            st.error(f"Hata: {file_name} -> {e}")

# --- ANALİZ VE ANA EKRAN ---
if all_data:
    final_df = all_data[0]
    for d in all_data[1:]:
        final_df = pd.merge(final_df, d, on='ID', how='outer')
    
    name_cols = [c for c in final_df.columns if c.startswith('Name_')]
    final_df['Ad Soyad'] = final_df[name_cols].bfill(axis=1).iloc[:, 0] if name_cols else "Bilinmiyor"
    
    pc_list = [f"PC{i}" for i in range(1, 12)]
    consolidated = pd.DataFrame()
    consolidated['Öğrenci No'] = final_df['ID']
    consolidated['Ad Soyad'] = final_df['Ad Soyad']

    for pc in pc_list:
        relevant = [c for c in final_df.columns if c.startswith(pc)]
        consolidated[pc] = final_df[relevant].apply(lambda row: 1 if 1 in row.values else 0, axis=1) if relevant else 0

    consolidated['Başarı (11)'] = consolidated[pc_list].sum(axis=1)
    consolidated['Resmi Durum'] = consolidated['Öğrenci No'].apply(lambda x: "🎓 MEZUN" if x in mezun_id_listesi else "📝 ÖĞRENCİ")
    consolidated['Giriş Yılı'] = consolidated['Öğrenci No'].apply(yil_coz)

    # --- FİLTRELEME ---
    st.subheader("📊 Genel Durum Listesi")
    col_f1, col_f2 = st.columns(2)
    
    with col_f1:
        ana_filtre = st.radio("Sınıflandır:", ["Hepsi", "Sadece Öğrenciler", "Sadece Mezunlar"], horizontal=True)
    
    temp_filt = consolidated.copy()
    if ana_filtre == "Sadece Öğrenciler": temp_filt = temp_filt[temp_filt['Resmi Durum'] == "📝 ÖĞRENCİ"]
    elif ana_filtre == "Sadece Mezunlar": temp_filt = temp_filt[temp_filt['Resmi Durum'] == "🎓 MEZUN"]
    
    with col_f2:
        mevcut_yillar = sorted([y for y in temp_filt['Giriş Yılı'].unique() if y != "Belirsiz"])
        yil_filtre = st.selectbox("Giriş Yılı:", ["Tüm Yıllar"] + mevcut_yillar)

    if yil_filtre != "Tüm Yıllar":
        temp_filt = temp_filt[temp_filt['Giriş Yılı'] == yil_filtre]

    st.dataframe(temp_filt, use_container_width=True)
    
    csv = temp_filt.to_csv(index=False).encode('utf-8-sig')
    st.download_button(f"📥 {ana_filtre} Listesini İndir", csv, "akredite_rapor.csv", "text/csv")

    st.divider()

    # --- BİREYSEL SORGULAMA ---
    st.subheader("👤 Öğrenci Detayı")
    s_list = consolidated.apply(lambda x: f"{x['Öğrenci No']} - {x['Ad Soyad']}", axis=1).tolist()
    secim = st.selectbox("Bir öğrenci seçin:", s_list)
    
    if secim:
        s_id = secim.split(" - ")[0]
        row = consolidated[consolidated['Öğrenci No'] == s_id].iloc[0]
        st.write(f"### {row['Ad Soyad']} - {row['Resmi Durum']} ({row['Giriş Yılı']} Girişli)")
        
        cols = st.columns(11)
        for i, p in enumerate(pc_list):
            clr = "#28a745" if row[p] == 1 else "#dc3545"
            cols[i].markdown(f"<div style='background-color:{clr}; color:white; padding:8px; border-radius:8px; text-align:center; font-size:12px;'>{p}</div>", unsafe_allow_html=True)
        st.progress(row['Başarı (11)'] / 11)
else:

    st.info("Arşiv boş. Lütfen yönetici şifresini girerek dosyaları yükleyin.")
