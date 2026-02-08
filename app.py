import streamlit as st
import pandas as pd
import os
import gc
import re

# 1. SAYFA AYARLARI
st.set_page_config(page_title="Hacettepe Çevre Akredite Takip", layout="wide")

VERI_KLASORU = "Veri_Kayitlari"
if not os.path.exists(VERI_KLASORU): os.makedirs(VERI_KLASORU)

YONETICI_SIFRESI = "akredite2026"

# 2. KRİTİK TEMİZLEME FONKSİYONLARI
def id_temizle(val):
    s = str(val).strip().split('.')[0]
    return re.sub(r'\D', '', s)

def yil_coz(ogrenci_no):
    no_str = str(ogrenci_no).strip()
    if len(no_str) >= 3:
        # Hacettepe formatı: 219... -> 2019, 221... -> 2021
        return "20" + no_str[1:3]
    return "Belirsiz"

def sütun_normalize(col_name):
    s = str(col_name).strip().lower().replace('ç','c').replace('ğ','g').replace('ı','i').replace('ö','o').replace('ş','s').replace('ü','u')
    return "".join(s.split())

# 3. YÖNETİM PANELİ (SOLDA)
with st.sidebar:
    st.header("🔐 Yönetim Paneli")
    sifre = st.text_input("Şifre:", type="password")
    arsiv_dosyalari = [f for f in os.listdir(VERI_KLASORU) if f.endswith('.xlsx')]
    
    if sifre == YONETICI_SIFRESI:
        st.success("Yönetici Modu")
        y_yukle = st.file_uploader("Excel Dosyası Yükle", accept_multiple_files=True, type=['xlsx'])
        if st.button("💾 Kaydet ve Analiz Et"):
            if y_yukle:
                for f in y_yukle:
                    with open(os.path.join(VERI_KLASORU, f.name), "wb") as b: b.write(f.getvalue())
                st.rerun()
        if arsiv_dosyalari:
            st.divider()
            sil = st.selectbox("Arşivden Sil:", ["Seçiniz..."] + arsiv_dosyalari)
            if sil != "Seçiniz..." and st.button("🗑️ DOSYAYI SİL"):
                os.remove(os.path.join(VERI_KLASORU, sil)); st.rerun()
    else:
        st.info("İnceleme modu aktiftir.")

# 4. ANA ANALİZ MOTORU
st.title("🎓 Akredite Takip ve Öğrenci Denetim Paneli")

all_dfs = []
mezun_id_listesi = []

if arsiv_dosyalari:
    for file_name in arsiv_dosyalari:
        file_path = os.path.join(VERI_KLASORU, file_name)
        try:
            # Mezun Listesi Okuma
            if "mezun" in file_name.lower():
                m_df = pd.read_excel(file_path)
                m_id = next((c for c in m_df.columns if 'student' in sütun_normalize(c) or 'ogrenci' in sütun_normalize(c)), None)
                if m_id: mezun_id_listesi.extend(m_df[m_id].apply(id_temizle).tolist())
                continue

            xls = pd.ExcelFile(file_path)
            for sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                
                # TUZAKLARA DÜŞMEYEN SÜTUN TESPİTİ
                # "Sıra no"yu atlayıp gerçek öğrenci numarasını bulur
                id_col = next((c for c in df.columns if ('student' in sütun_normalize(c) or 'ogrenci' in sütun_normalize(c)) and 'no' in sütun_normalize(c)), None)
                if not id_col: id_col = next((c for c in df.columns if 'number' in sütun_normalize(c) or 'numara' in sütun_normalize(c)), None)
                
                n_col = next((c for c in df.columns if 'namesurname' in sütun_normalize(c) or 'adsoyad' in sütun_normalize(c) or 'name' in sütun_normalize(c) or 'ad' in sütun_normalize(c)), None)
                s_col = next((c for c in df.columns if 'surname' in sütun_normalize(c) or 'soyad' in sütun_normalize(c)), None)
                pc_cols = [c for c in df.columns if sütun_normalize(c).startswith('pc') or sütun_normalize(c).startswith('pc')]
                
                if id_col and pc_cols:
                    temp = df[[id_col] + pc_cols].copy()
                    temp.rename(columns={id_col: 'ID'}, inplace=True)
                    temp['ID'] = temp['ID'].apply(id_temizle)
                    
                    if n_col and s_col:
                        temp['Ad Soyad'] = df[n_col].astype(str) + " " + df[s_col].astype(str)
                    elif n_col:
                        temp['Ad Soyad'] = df[n_col].astype(str)
                    
                    for pc in pc_cols:
                        num = re.findall(r'\d+', pc)
                        if num: temp.rename(columns={pc: f"PC{num[0]}"}, inplace=True)
                    all_dfs.append(temp)
            xls.close()
        except: continue

if all_dfs:
    # 5. MÜKEMMEL BİRLEŞTİRME
    combined = pd.concat(all_dfs, ignore_index=True)
    
    # ID'ye göre grupla ve temizle
    agg_dict = {'Ad Soyad': 'first'}
    for col in combined.columns:
        if col.startswith('PC'): agg_dict[col] = 'max'
    
    final_df = combined.groupby('ID').agg(agg_dict).reset_index()
    final_df['Ad Soyad'] = final_df['Ad Soyad'].fillna("Bilinmiyor").str.strip().str.upper()
    
    # Tüm filtreleri ve özellikleri geri yükle
    pc_list = [f"PC{i}" for i in range(1, 12)]
    for p in pc_list:
        if p not in final_df.columns: final_df[p] = 0
        final_df[p] = final_df[p].fillna(0).astype(int)
    
    final_df['Giriş Yılı'] = final_df['ID'].apply(yil_coz)
    final_df['Durum'] = final_df['ID'].apply(lambda x: "🎓 MEZUN" if x in mezun_id_listesi else "📝 ÖĞRENCİ")
    final_df['Toplam Başarı'] = final_df[pc_list].sum(axis=1)

    # 6. FİLTRELEME ARAYÜZÜ
    st.subheader("📊 Akredite Takip ve Filtreleme")
    c1, c2 = st.columns(2)
    with c1:
        ana_filtre = st.radio("Listele:", ["Hepsi", "Sadece Öğrenciler", "Sadece Mezunlar"], horizontal=True)
    
    view_df = final_df.copy()
    if ana_filtre == "Sadece Öğrenciler": view_df = view_df[view_df['Durum'] == "📝 ÖĞRENCİ"]
    elif ana_filtre == "Sadece Mezunlar": view_df = view_df[view_df['Durum'] == "🎓 MEZUN"]
    
    with c2:
        yillar = sorted([y for y in view_df['Giriş Yılı'].unique() if y != "Belirsiz"])
        secilen_yil = st.selectbox("Giriş Yılı Filtresi:", ["Tüm Yıllar"] + yillar)
    
    if secilen_yil != "Tüm Yıllar": view_df = view_df[view_df['Giriş Yılı'] == secilen_yil]

    st.dataframe(view_df[['ID', 'Ad Soyad', 'Giriş Yılı', 'Durum'] + pc_list + ['Toplam Başarı']].sort_values('ID'), use_container_width=True)
    st.download_button("📥 Excel Olarak İndir", view_df.to_csv(index=False).encode('utf-8-sig'), "akredite_rapor.csv")
else:
    st.info("Lütfen sol taraftan veri yükleyin.")
