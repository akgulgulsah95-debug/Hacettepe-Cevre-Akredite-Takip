import streamlit as st
import pandas as pd
import os
import gc
import re

st.set_page_config(page_title="Hacettepe Çevre Akredite", layout="wide")

VERI_KLASORU = "Veri_Kayitlari"
if not os.path.exists(VERI_KLASORU): os.makedirs(VERI_KLASORU)

# --- TEMİZLİK FONKSİYONLARI ---
def id_temizle(val):
    s = str(val).strip().split('.')[0]
    return re.sub(r'\D', '', s)

def sütun_normalize(col_name):
    s = str(col_name).strip().lower().replace('ç','c').replace('ğ','g').replace('ı','i').replace('ö','o').replace('ş','s').replace('ü','u')
    return "".join(s.split())

# --- SIDEBAR ---
with st.sidebar:
    st.header("🔐 Yönetim")
    sifre = st.text_input("Şifre:", type="password")
    arsiv = [f for f in os.listdir(VERI_KLASORU) if f.endswith('.xlsx')]
    
    if sifre == "akredite2026":
        y_ders = st.file_uploader("Dosya Yükle", accept_multiple_files=True, type=['xlsx'])
        if st.button("💾 Kaydet"):
            if y_ders:
                for f in y_ders:
                    with open(os.path.join(VERI_KLASORU, f.name), "wb") as b: b.write(f.getvalue())
                st.rerun()
        if arsiv:
            sil = st.selectbox("Sil:", ["Seç..."] + arsiv)
            if sil != "Seç..." and st.button("🗑️ Sil"):
                os.remove(os.path.join(VERI_KLASORU, sil))
                st.rerun()

# --- ANA EKRAN ---
st.title("🎓 Öğrenci Akredite Takip Sistemi")

all_dfs = []
if arsiv:
    for file in arsiv:
        try:
            xls = pd.ExcelFile(os.path.join(VERI_KLASORU, file))
            ders_adi = file.replace(".xlsx", "")
            for sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                
                # Sütunları tanı
                id_col = next((c for c in df.columns if 'studentnumber' in sütun_normalize(c) or 'ogrencino' in sütun_normalize(c)), None)
                name_col = next((c for c in df.columns if 'namesurname' in sütun_normalize(c) or 'ad' in sütun_normalize(c)), None)
                surname_col = next((c for c in df.columns if 'surname' in sütun_normalize(c)), None)
                pc_cols = [c for c in df.columns if sütun_normalize(c).startswith('pc') or sütun_normalize(c).startswith('pc')]
                
                if id_col and pc_cols:
                    temp = df[[id_col] + pc_cols].copy()
                    temp.rename(columns={id_col: 'ID'}, inplace=True)
                    temp['ID'] = temp['ID'].apply(id_temizle)
                    
                    # İsim belirleme (Bulabildiğini al)
                    if name_col and surname_col:
                        temp['Ad Soyad'] = df[name_col].astype(str) + " " + df[surname_col].astype(str)
                    elif name_col:
                        temp['Ad Soyad'] = df[name_col].astype(str)
                    else:
                        temp['Ad Soyad'] = None
                    
                    # PC'leri standartlaştır (Sadece PC1, PC2... yap)
                    for pc in pc_cols:
                        clean_pc = "PC" + re.findall(r'\d+', pc)[0]
                        temp.rename(columns={pc: clean_pc}, inplace=True)
                    
                    all_dfs.append(temp)
            xls.close()
        except: continue

if all_dfs:
    # --- KRİTİK BİRLEŞTİRME MANTIĞI ---
    # Tüm verileri alt alta ekle
    combined = pd.concat(all_dfs, ignore_index=True)
    
    # ID'ye göre grupla. 
    # İsim için: Boş olmayan ilk ismi al.
    # PC'ler için: En yüksek değeri (1 varsa 1'i) al.
    agg_rules = {'Ad Soyad': 'first'}
    for col in combined.columns:
        if col.startswith('PC'): agg_rules[col] = 'max'
    
    final_df = combined.groupby('ID').agg(agg_rules).reset_index()
    
    # Boş kalan isimleri "Bilinmiyor" yap ve temizle
    final_df['Ad Soyad'] = final_df['Ad Soyad'].fillna("Bilinmiyor").str.strip().str.title()
    
    # PC Listesi (1-11 arası)
    pc_list = [f"PC{i}" for i in range(1, 12)]
    for pc in pc_list:
        if pc not in final_df.columns: final_df[pc] = 0
    
    final_df['Toplam Başarı'] = final_df[pc_list].sum(axis=1)
    
    # Görüntüleme
    st.dataframe(final_df[['ID', 'Ad Soyad'] + pc_list + ['Toplam Başarı']], use_container_width=True)
    st.download_button("📥 Excel İndir", final_df.to_csv(index=False).encode('utf-8-sig'), "akredite.csv")
else:
    st.info("Henüz veri yok.")
