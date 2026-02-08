import streamlit as st
import pandas as pd
import os
import gc
import re

# 1. SAYFA AYARLARI
st.set_page_config(page_title="Hacettepe Çevre Akredite Takip", layout="wide")

VERI_KLASORU = "Veri_Kayitlari"
if not os.path.exists(VERI_KLASORU): os.makedirs(VERI_KLASORU)

# 2. SÜPER TEMİZLEYİCİ FONKSİYONLAR
def id_temizle(val):
    s = str(val).strip().split('.')[0]
    return re.sub(r'\D', '', s)

def sütun_normalize(col_name):
    s = str(col_name).strip().lower().replace('ç','c').replace('ğ','g').replace('ı','i').replace('ö','o').replace('ş','s').replace('ü','u')
    return "".join(s.split())

# 3. YÖNETİM PANELİ (SIDEBAR)
with st.sidebar:
    st.header("🔐 Yönetim")
    sifre = st.text_input("Şifre:", type="password")
    arsiv = [f for f in os.listdir(VERI_KLASORU) if f.endswith('.xlsx')]
    
    if sifre == "akredite2026":
        st.success("Yönetici Modu")
        y_ders = st.file_uploader("Dosya Yükle", accept_multiple_files=True, type=['xlsx'])
        if st.button("💾 Kaydet"):
            if y_ders:
                for f in y_ders:
                    with open(os.path.join(VERI_KLASORU, f.name), "wb") as b: b.write(f.getvalue())
                st.rerun()
        if arsiv:
            sil = st.selectbox("Sil:", ["Seç..."] + arsiv)
            if sil != "Seç..." and st.button("🗑️ Sil"):
                os.remove(os.path.join(VERI_KLASORU, sil)); st.rerun()

# 4. ANA ANALİZ MOTORU
st.title("🎓 Öğrenci Akredite Takip Sistemi")

all_dfs = []
if arsiv:
    for file in arsiv:
        try:
            xls = pd.ExcelFile(os.path.join(VERI_KLASORU, file))
            for sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                
                # Sütun Tespit
                id_col = next((c for c in df.columns if 'studentnumber' in sütun_normalize(c) or 'ogrencino' in sütun_normalize(c)), None)
                n_col = next((c for c in df.columns if 'namesurname' in sütun_normalize(c) or 'adsoyad' in sütun_normalize(c) or 'name' in sütun_normalize(c) or 'ad' in sütun_normalize(c)), None)
                s_col = next((c for c in df.columns if 'surname' in sütun_normalize(c) or 'soyad' in sütun_normalize(c)), None)
                pc_cols = [c for c in df.columns if sütun_normalize(c).startswith('pc') or sütun_normalize(c).startswith('pc')]
                
                if id_col and pc_cols:
                    temp = df[[id_col] + pc_cols].copy()
                    temp.rename(columns={id_col: 'ID'}, inplace=True)
                    temp['ID'] = temp['ID'].apply(id_temizle)
                    
                    # İsim Birleştirme (Çiftleme riskini burada bitiriyoruz)
                    if n_col and s_col:
                        temp['Ad Soyad'] = df[n_col].astype(str) + " " + df[s_col].astype(str)
                    elif n_col:
                        temp['Ad Soyad'] = df[n_col].astype(str)
                    
                    # PC Standardizasyonu
                    for pc in pc_cols:
                        num = re.findall(r'\d+', pc)
                        if num: temp.rename(columns={pc: f"PC{num[0]}"}, inplace=True)
                    
                    all_dfs.append(temp)
            xls.close()
        except: continue

if all_dfs:
    # --- 5. MÜKEMMEL BİRLEŞTİRME (GRUPLAMA) ---
    combined = pd.concat(all_dfs, ignore_index=True)
    
    # ID'ye göre grupla: İsim için ilkini al, PC'ler için en yüksek (1) değeri al
    agg_dict = {'Ad Soyad': 'first'}
    for c in combined.columns:
        if c.startswith('PC'): agg_dict[c] = 'max'
    
    final_df = combined.groupby('ID').agg(agg_dict).reset_index()
    final_df['Ad Soyad'] = final_df['Ad Soyad'].fillna("Bilinmiyor").str.strip().str.title()
    
    # Tüm PC'lerin (1-11) olduğundan emin ol
    pc_list = [f"PC{i}" for i in range(1, 12)]
    for p in pc_list:
        if p not in final_df.columns: final_df[p] = 0
    
    final_df['Başarı'] = final_df[pc_list].sum(axis=1)
    
    # Tabloyu Göster
    st.dataframe(final_df[['ID', 'Ad Soyad'] + pc_list + ['Başarı']].sort_values('ID'), use_container_width=True)
    st.download_button("📥 Raporu İndir", final_df.to_csv(index=False).encode('utf-8-sig'), "akredite.csv")
else:
    st.info("Sistemde uygun veri bulunamadı. Lütfen sol panelden yükleme yapın.")
