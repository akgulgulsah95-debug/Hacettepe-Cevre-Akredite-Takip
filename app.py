import streamlit as st
import pandas as pd
import os
import shutil
import gc
import re

# 1. AYARLAR (Hata payını sıfıra indirmek için en başa)
st.set_page_config(page_title="Akredite Takip Sistemi", layout="wide")

VERI_KLASORU = "Veri_Kayitlari"
if not os.path.exists(VERI_KLASORU):
    os.makedirs(VERI_KLASORU)

YONETICI_SIFRESI = "akredite2026"

# 2. YARDIMCI FONKSİYONLAR
def id_temizle(val):
    s = str(val).strip()
    return re.sub(r'\D', '', s)

def veri_temizle(df):
    df.columns = df.columns.astype(str).str.strip().str.lower()
    df.columns = df.columns.str.replace('ç', 'c').str.replace('ğ', 'g').str.replace('ı', 'i').str.replace('ö', 'o').str.replace('ş', 's').str.replace('ü', 'u')
    return df

# 3. SIDEBAR (PANEL) - BU KISIM ARTIK KİLİTLENMEYECEK
with st.sidebar:
    st.header("🔐 Yönetim Paneli")
    
    # Arşiv Listesi (Her zaman görünsün)
    mevcutlar = [f for f in os.listdir(VERI_KLASORU) if f.endswith('.xlsx') or f.endswith('.dat')]
    if mevcutlar:
        st.subheader("📂 Mevcut Dosyalar")
        for m in mevcutlar:
            st.caption(f"• {m}")
    
    st.divider()
    sifre = st.text_input("Yönetici Şifresi:", type="password")
    
    if sifre == YONETICI_SIFRESI:
        st.success("Giriş Başarılı")
        st.subheader("📥 Yeni Veri Yükle")
        y_ders = st.file_uploader("Dersler", accept_multiple_files=True, type=['xlsx'], key="u1")
        y_mezun = st.file_uploader("Mezun Listesi", type=['xlsx'], key="u2")
        
        if st.button("💾 Kaydet ve Arşivle"):
            if y_ders:
                for f in y_ders:
                    with open(os.path.join(VERI_KLASORU, f.name), "wb") as b:
                        b.write(f.getvalue())
            if y_mezun:
                with open(os.path.join(VERI_KLASORU, "resmi_mezun_listesi_ozel.dat"), "wb") as b:
                    b.write(y_mezun.getvalue())
            st.rerun()
            
        st.divider()
        if mevcutlar:
            secilen = st.selectbox("Dosya Sil:", ["Seç..."] + mevcutlar)
            if secilen != "Seç..." and st.button("🗑️ SİL"):
                os.remove(os.path.join(VERI_KLASORU, secilen))
                st.rerun()
    else:
        st.info("Düzenleme için şifre girin.")

# 4. ANA EKRAN
st.title("🎓 Akredite Takip ve Öğrenci Denetim Paneli")

all_data = []
mezun_id_listesi = []

# VERİ OKUMA DÖNGÜSÜ (Hata korumalı)
if mevcutlar:
    for file_name in mevcutlar:
        file_path = os.path.join(VERI_KLASORU, file_name)
        try:
            gc.collect()
            if file_name == "resmi_mezun_listesi_ozel.dat":
                m_df = pd.read_excel(file_path, engine='openpyxl')
                m_df = veri_temizle(m_df)
                m_id_col = next((c for c in m_df.columns if 'no' in c or 'numara' in c), None)
                if m_id_col: mezun_id_listesi = m_df[m_id_col].apply(id_temizle).tolist()
                continue

            xls = pd.ExcelFile(file_path, engine='openpyxl')
            ders_adi = file_name.replace(".xlsx", "")
            for sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                df = veri_temizle(df)
                std_num_col = next((c for c in df.columns if 'no' in c or 'numara' in c), None)
                pc_cols = [c for c in df.columns if c.startswith('pc')]
                
                if std_num_col and pc_cols:
                    temp_df = df[[std_num_col] + pc_cols].copy()
                    temp_df.rename(columns={std_num_col: 'ID'}, inplace=True)
                    temp_df['ID'] = temp_df['ID'].apply(id_temizle)
                    # İsim kolonu tespiti
                    n_col = next((c for c in df.columns if 'ad' in c or 'name' in c), None)
                    s_col = next((c for c in df.columns if 'soyad' in c or 'surname' in c), None)
                    c_name = f'Name_{ders_adi}'
                    if n_col and s_col: temp_df[c_name] = df[n_col].astype(str) + " " + df[s_col].astype(str)
                    elif n_col: temp_df[c_name] = df[n_col].astype(str)
                    
                    for pc in pc_cols: temp_df.rename(columns={pc: f"{pc.upper()} ({ders_adi})"}, inplace=True)
                    all_data.append(temp_df)
            xls.close()
        except Exception as e:
            st.warning(f"⚠️ {file_name} okunamadı, atlanıyor.")

# 5. TABLO OLUŞTURMA
if all_data:
    final_df = all_data[0]
    for d in all_data[1:]: final_df = pd.merge(final_df, d, on='ID', how='outer')
    
    n_cols = [c for c in final_df.columns if c.startswith('Name_')]
    final_df['Ad Soyad'] = final_df[n_cols].bfill(axis=1).iloc[:, 0] if n_cols else "Bilinmiyor"
    
    pc_list = [f"PC{i}" for i in range(1, 12)]
    consolidated = pd.DataFrame()
    consolidated['ID'] = final_df['ID']
    consolidated['Ad Soyad'] = final_df['Ad Soyad']
    for pc in pc_list:
        rel = [c for c in final_df.columns if c.startswith(pc)]
        consolidated[pc] = final_df[rel].apply(lambda r: 1 if 1 in r.values else 0, axis=1) if rel else 0

    consolidated = consolidated.groupby('ID').agg({'Ad Soyad': 'first', **{pc: 'max' for pc in pc_list}}).reset_index()
    consolidated['Başarı (11)'] = consolidated[pc_list].sum(axis=1)
    consolidated['Durum'] = consolidated['ID'].apply(lambda x: "🎓 MEZUN" if x in mezun_id_listesi else "📝 ÖĞRENCİ")

    st.dataframe(consolidated, use_container_width=True)
    st.download_button("📥 Excel İndir", consolidated.to_csv(index=False).encode('utf-8-sig'), "liste.csv")
else:
    st.info("Sistemde yüklü dosya var ama uygun format bulunamadı. Lütfen sütun başlıklarını kontrol edin.")
