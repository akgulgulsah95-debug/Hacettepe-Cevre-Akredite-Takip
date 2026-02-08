import streamlit as st
import pandas as pd
import os
import gc
import re

# 1. AYARLAR
st.set_page_config(page_title="Hacettepe Çevre Akredite Takip", layout="wide")

VERI_KLASORU = "Veri_Kayitlari"
if not os.path.exists(VERI_KLASORU): os.makedirs(VERI_KLASORU)

YONETICI_SIFRESI = "akredite2026"

# 2. YIL VE ID TEMİZLEME FONKSİYONLARI (En Sağlam Hali)
def yil_coz(ogrenci_no):
    no_str = str(ogrenci_no).strip()
    if len(no_str) >= 3:
        yil_kod = no_str[:3]
        if yil_kod.startswith('21') or yil_kod.startswith('22'):
            return "20" + yil_kod[:2]
    return "Belirsiz"

def id_temizle(val):
    s = str(val).strip().split('.')[0]
    return re.sub(r'\D', '', s)

def sütun_normalize(col_name):
    s = str(col_name).strip().lower().replace('ç','c').replace('ğ','g').replace('ı','i').replace('ö','o').replace('ş','s').replace('ü','u')
    return "".join(s.split())

# 3. SIDEBAR
with st.sidebar:
    st.header("🔐 Yönetim Paneli")
    mevcutlar = [f for f in os.listdir(VERI_KLASORU) if f.endswith('.xlsx') or f.endswith('.dat')]
    sifre = st.text_input("Şifre:", type="password")
    
    if sifre == YONETICI_SIFRESI:
        st.success("Yönetici Aktif")
        y_ders = st.file_uploader("Dosya Yükle", accept_multiple_files=True, type=['xlsx', 'dat'])
        if st.button("💾 Kaydet ve Analiz Et"):
            if y_ders:
                for f in y_ders:
                    with open(os.path.join(VERI_KLASORU, f.name), "wb") as b: b.write(f.getvalue())
                st.rerun()
        if mevcutlar:
            secilen = st.selectbox("Dosya Sil:", ["Seç..."] + mevcutlar)
            if secilen != "Seç..." and st.button("🗑️ SİL"):
                os.remove(os.path.join(VERI_KLASORU, secilen)); st.rerun()

# 4. ANA MOTOR
st.title("🎓 Akredite Takip ve Öğrenci Denetim Paneli")

all_data = []
mezun_id_listesi = []

if mevcutlar:
    for file_name in mevcutlar:
        file_path = os.path.join(VERI_KLASORU, file_name)
        try:
            # Mezun Listesi Kontrolü (.dat veya özel isimli dosya)
            if "mezun" in file_name.lower():
                m_df = pd.read_excel(file_path)
                id_col = next((c for c in m_df.columns if 'no' in sütun_normalize(c) or 'number' in sütun_normalize(c)), None)
                if id_col: mezun_id_listesi = m_df[id_col].apply(id_temizle).tolist()
                continue

            xls = pd.ExcelFile(file_path)
            for sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                id_col = next((c for c in df.columns if 'number' in sütun_normalize(c) or 'no' in sütun_normalize(c)), None)
                name_col = next((c for c in df.columns if 'name' in sütun_normalize(c) or 'ad' in sütun_normalize(c)), None)
                pc_cols = [c for c in df.columns if sütun_normalize(c).startswith('pc') or sütun_normalize(c).startswith('pc')]
                
                if id_col and pc_cols:
                    temp = df[[id_col] + pc_cols].copy()
                    temp.rename(columns={id_col: 'ID'}, inplace=True)
                    temp['ID'] = temp['ID'].apply(id_temizle)
                    if name_col: temp['Ad Soyad'] = df[name_col].astype(str)
                    
                    # PC Standardizasyonu
                    for pc in pc_cols:
                        num = re.findall(r'\d+', pc)
                        if num: temp.rename(columns={pc: f"PC{num[0]}"}, inplace=True)
                    all_data.append(temp)
            xls.close()
        except: continue

if all_data:
    combined = pd.concat(all_data, ignore_index=True)
    
    # Gruplama
    agg_rules = {}
    if 'Ad Soyad' in combined.columns: agg_rules['Ad Soyad'] = 'first'
    for c in combined.columns:
        if c.startswith('PC'): agg_rules[c] = 'max'
    
    final_df = combined.groupby('ID').agg(agg_rules).reset_index()
    
    # Eksik PC'leri tamamla
    pc_list = [f"PC{i}" for i in range(1, 12)]
    for p in pc_list:
        if p not in final_df.columns: final_df[p] = 0
    
    # YILLAR VE MEZUN DURUMU (Geri Gelen Özellikler)
    final_df['Giriş Yılı'] = final_df['ID'].apply(yil_coz)
    final_df['Durum'] = final_df['ID'].apply(lambda x: "🎓 MEZUN" if x in mezun_id_listesi else "📝 ÖĞRENCİ")
    final_df['Toplam Başarı'] = final_df[pc_list].sum(axis=1)

    # Tabloyu Göster
    st.dataframe(final_df[['ID', 'Ad Soyad', 'Giriş Yılı', 'Durum'] + pc_list + ['Toplam Başarı']], use_container_width=True)
    st.download_button("📥 Excel Raporu", final_df.to_csv(index=False).encode('utf-8-sig'), "akredite.csv")
else:
    st.info("Sistem hazır, lütfen dosya yükleyin.")
