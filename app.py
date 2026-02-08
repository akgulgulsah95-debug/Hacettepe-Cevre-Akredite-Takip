import streamlit as st
import pandas as pd
import os
import shutil
import gc

# Sayfa Ayarları
st.set_page_config(page_title="Akredite Takip Sistemi", layout="wide")

# --- 1. AYARLAR VE DEPOLAMA ---
VERI_KLASORU = "Veri_Kayitlari"
if not os.path.exists(VERI_KLASORU):
    os.makedirs(VERI_KLASORU)

YONETICI_SIFRESI = "akredite2026"
all_data = []
mezun_id_listesi = []
arsiv_dosyalari = [f for f in os.listdir(VERI_KLASORU) if f.endswith('.xlsx') or f.endswith('.dat')]

st.title("🎓 Akredite Takip ve Öğrenci Denetim Paneli")

# --- 2. YÖNETİCİ PANELİ (SOL SİDEBAR) ---
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
        if arsiv_dosyalari:
            silinecek = st.selectbox("Dosya Sil:", ["Seçiniz..."] + arsiv_dosyalari)
            if silinecek != "Seçiniz..." and st.button(f"🗑️ Sil: {silinecek}"):
                os.remove(os.path.join(VERI_KLASORU, silinecek))
                st.rerun()
    else:
        st.info("Sadece görüntüleme modu aktif.")

# --- 3. FONKSİYONLAR ---
def veri_temizle(df):
    # Sütun isimlerini normalize et (küçük harf, boşluksuz, Türkçe karakter temizliği)
    df.columns = df.columns.astype(str).str.strip().str.lower()
    df.columns = df.columns.str.replace('ç', 'c').str.replace('ğ', 'g').str.replace('ı', 'i').str.replace('ö', 'o').str.replace('ş', 's').str.replace('ü', 'u')
    return df

def yil_coz(ogrenci_no):
    no_str = str(ogrenci_no).strip()
    if len(no_str) >= 8:
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
                if m_id_col: mezun_id_listesi = m_df[m_id_col].astype(str).tolist()
                del m_df
                continue

            xls = pd.ExcelFile(file_path, engine='openpyxl')
            ders_adi = file_name.replace(".xlsx", "")
            for sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                df = veri_temizle(df)
                
                # Sütun Tespiti
                std_num_col = next((c for c in df.columns if 'number' in c or 'no' in c or 'numara' in c), None)
                name_col = next((c for c in df.columns if 'name' in c or 'ad' in c), None)
                surname_col = next((c for c in df.columns if 'surname' in c or 'soyad' in c), None)
                pc_cols = [c for c in df.columns if c.startswith('pc')]
                
                if std_num_col and pc_cols:
                    # Gerekli sütunları seç ve ID'yi ayarla
                    temp_df = df[[std_num_col] + pc_cols].copy()
                    temp_df.rename(columns={std_num_col: 'ID'}, inplace=True)
                    temp_df['ID'] = temp_df['ID'].astype(str)
                    
                    # AD ve SOYAD BİRLEŞTİRME OPERASYONU
                    current_name_col = f'Name_{ders_adi}'
                    if name_col and surname_col:
                        temp_df[current_name_col] = df[name_col].astype(str).str.title() + " " + df[surname_col].astype(str).str.title()
                    elif name_col:
                        temp_df[current_name_col] = df[name_col].astype(str).str.title()
                    elif surname_col:
                        temp_df[current_name_col] = df[surname_col].astype(str).str.title()
                    
                    # PC Sütunlarını isimlendir
                    for pc in pc_cols:
                        temp_df.rename(columns={pc: f"{pc.upper()} ({ders_adi})"}, inplace=True)
                    
                    all_data.append(temp_df)
                del df
            xls.close()
            del xls
        except Exception as e:
            st.error(f"Hata: {file_name} -> {e}")

# --- 5. ANA EKRAN VE ANALİZ ---
if all_data:
    # Tüm verileri ID (Numara) üzerinden dış birleşim (outer join) ile birleştir
    final_df = all_data[0]
    for d in all_data[1:]:
        final_df = pd.merge(final_df, d, on='ID', how='outer')
    
    # Farklı derslerden gelen isimleri harmanla (ilk bulduğunu al)
    name_cols = [c for c in final_df.columns if c.startswith('Name_')]
    if name_cols:
        final_df['Ad Soyad'] = final_df[name_cols].bfill(axis=1).iloc[:, 0]
    else:
        final_df['Ad Soyad'] = "Bilinmiyor"
    
    # PC Başarı Analizi
    pc_list = [f"PC{i}" for i in range(1, 12)]
    consolidated = pd.DataFrame()
    consolidated['Öğrenci No'] = final_df['ID']
    consolidated['Ad Soyad'] = final_df['Ad Soyad']

    for pc in pc_list:
        relevant = [c for c in final_df.columns if c.startswith(pc)]
        if relevant:
            consolidated[pc] = final_df[relevant].apply(lambda row: 1 if 1 in row.values else 0, axis=1)
        else:
            consolidated[pc] = 0

    consolidated['Başarı (11)'] = consolidated[pc_list].sum(axis=1)
    consolidated['Resmi Durum'] = consolidated['Öğrenci No'].apply(lambda x: "🎓 MEZUN" if x in mezun_id_listesi else "📝 ÖĞRENCİ")
    consolidated['Giriş Yılı'] = consolidated['Öğrenci No'].apply(yil_coz)

    # Görünüm Ayarları
    st.subheader("📊 Filtreli Takip Paneli")
    f1, f2 = st.columns(2)
    with f1: ana_filtre = st.radio("Süzgeç:", ["Hepsi", "Sadece Öğrenciler", "Sadece Mezunlar"], horizontal=True)
    
    temp_filt = consolidated.copy()
    if ana_filtre == "Sadece Öğrenciler": temp_filt = temp_filt[temp_filt['Resmi Durum'] == "📝 ÖĞRENCİ"]
    elif ana_filtre == "Sadece Mezunlar": temp_filt = temp_filt[temp_filt['Resmi Durum'] == "🎓 MEZUN"]
    
    with f2:
        yillar = sorted([y for y in temp_filt['Giriş Yılı'].unique() if y != "Belirsiz"])
        yil_filtre = st.selectbox("Giriş Yılına Göre Filtrele:", ["Tüm Yıllar"] + yillar)

    if yil_filtre != "Tüm Yıllar": temp_filt = temp_filt[temp_filt['Giriş Yılı'] == yil_filtre]
    
    st.dataframe(temp_filt, use_container_width=True)
    
    csv = temp_filt.to_csv(index=False).encode('utf-8-sig')
    st.download_button(f"📥 {ana_filtre} Verisini Excel İçin İndir", csv, "akredite_rapor.csv", "text/csv")

    st.divider()
    st.subheader("👤 Detaylı Öğrenci Karnesi")
    s_list = consolidated.apply(lambda x: f"{x['Öğrenci No']} - {x['Ad Soyad']}", axis=1).tolist()
    secim = st.selectbox("Bir öğrenci seçerek PC karnesini görüntüleyin:", s_list)
    if secim:
        s_id = secim.split(" - ")[0]
        row = consolidated[consolidated['Öğrenci No'] == s_id].iloc[0]
        st.write(f"### {row['Ad Soyad']} - {row['Resmi Durum']}")
        st.write(f"**Giriş Yılı:** {row['Giriş Yılı']} | **Toplam Sağlanan PC:** {row['Başarı (11)']}/11")
        
        cols = st.columns(11)
        for i, p in enumerate(pc_list):
            clr = "#28a745" if row[p] == 1 else "#dc3545"
            cols[i].markdown(f"<div style='background-color:{clr}; color:white; padding:10px; border-radius:10px; text-align:center; font-weight:bold;'>{p}</div>", unsafe_allow_html=True)
        st.progress(float(row['Başarı (11)'] / 11))
else:
    st.info("Sistem şu an boş. Veri yüklemek için sol panelden şifrenizle giriş yapınız.")

