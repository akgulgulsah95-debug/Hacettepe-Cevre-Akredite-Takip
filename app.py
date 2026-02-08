import streamlit as st
import pandas as pd
import os
import shutil
import gc
import re

# 1. AYARLAR
st.set_page_config(page_title="Akredite Takip Sistemi", layout="wide")

VERI_KLASORU = "Veri_Kayitlari"
if not os.path.exists(VERI_KLASORU):
    os.makedirs(VERI_KLASORU)

YONETICI_SIFRESI = "akredite2026"

# 2. TEMİZLİK FONKSİYONLARI
def id_temizle(val):
    return re.sub(r'\D', '', str(val).strip())

def veri_temizle(df):
    df.columns = df.columns.astype(str).str.strip().str.lower().str.replace('ç', 'c').str.replace('ğ', 'g').str.replace('ı', 'i').str.replace('ö', 'o').str.replace('ş', 's').str.replace('ü', 'u')
    return df

# 3. SOL PANEL (SIDEBAR)
with st.sidebar:
    st.header("🔐 Yönetim Paneli")
    girilen_sifre = st.text_input("Şifre Girin:", type="password")
    
    if girilen_sifre == YONETICI_SIFRESI:
        st.success("Yönetici Modu Aktif")
        st.divider()
        
        yeni_dersler = st.file_uploader("Ders Dosyaları", accept_multiple_files=True, type=['xlsx'])
        yeni_mezun = st.file_uploader("Mezun Listesi", type=['xlsx'])
        
        if st.button("💾 Kaydet ve Arşivle"):
            if yeni_dersler:
                for f in yeni_dersler:
                    with open(os.path.join(VERI_KLASORU, f.name), "wb") as buffer:
                        buffer.write(f.getvalue())
                st.success("Dersler kaydedildi!")
            
            if yeni_mezun:
                with open(os.path.join(VERI_KLASORU, "resmi_mezun_listesi_ozel.dat"), "wb") as buffer:
                    buffer.write(yeni_mezun.getvalue())
                st.success("Mezun listesi güncellendi!")
            
            st.rerun()

        st.divider()
        mevcut_dosyalar = [f for f in os.listdir(VERI_KLASORU) if f.endswith('.xlsx') or f.endswith('.dat')]
        if mevcut_dosyalar:
            silinecek = st.selectbox("Dosya Sil:", ["Seçiniz..."] + mevcut_dosyalar)
            if silinecek != "Seçiniz..." and st.button("🗑️ Seçileni Sil"):
                os.remove(os.path.join(VERI_KLASORU, silinecek))
                st.success("Dosya silindi!")
                st.rerun()
    else:
        st.info("İnceleme modu. Düzenleme için şifre girin.")

# 4. VERİ OKUMA VE BİRLEŞTİRME
st.title("🎓 Akredite Takip ve Öğrenci Denetim Paneli")

all_data = []
mezun_id_listesi = []
arsiv_dosyalari = [f for f in os.listdir(VERI_KLASORU) if f.endswith('.xlsx') or f.endswith('.dat')]

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
                    
                    c_name = f'Name_{ders_adi}'
                    if name_col and surname_col:
                        temp_df[c_name] = df[name_col].astype(str).str.title() + " " + df[surname_col].astype(str).str.title()
                    elif name_col:
                        temp_df[c_name] = df[name_col].astype(str).str.title()

                    for pc in pc_cols:
                        temp_df.rename(columns={pc: f"{pc.upper()} ({ders_adi})"}, inplace=True)
                    all_data.append(temp_df)
            xls.close()
        except Exception as e:
            st.error(f"Hata ({file_name}): {e}")

# 5. TABLO GÖSTERİMİ
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

    consolidated = consolidated.groupby('ID').agg({'Ad Soyad': 'first', **{pc: 'max' for pc in pc_list}}).reset_index()
    consolidated['Başarı (11)'] = consolidated[pc_list].sum(axis=1)
    consolidated['Durum'] = consolidated['ID'].apply(lambda x: "🎓 MEZUN" if x in mezun_id_listesi else "📝 ÖĞRENCİ")

    st.dataframe(consolidated, use_container_width=True)
    st.download_button("📥 Excel İndir", consolidated.to_csv(index=False).encode('utf-8-sig'), "akredite_liste.csv")
else:
    st.info("Sistem şu an boş. Sol panelden veri yükleyiniz.")
