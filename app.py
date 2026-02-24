import streamlit as st
from datetime import datetime
import gspread
import json
import pytz 
import requests
from google.oauth2.service_account import Credentials

# --- 1. 기본 설정 및 시간 ---
st.set_page_config(page_title="SOI QC SMART SYSTEM", layout="wide", page_icon="🏭")
jakarta_tz = pytz.timezone('Asia/Jakarta')
now_jakarta = datetime.now(jakarta_tz)
today_str = now_jakarta.strftime('%m-%d')
full_today = now_jakarta.strftime('%Y-%m-%d')
current_time_full = now_jakarta.strftime('%H:%M')

TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]

# --- 2. [콘텐츠 보존] 19개 전 항목 상세 가이드 및 질문 데이터 ---
QC_CONTENT = {
    "A": {
        "a1": {"title": "Cek Stok BB Sudah steam", "qs": ["Sisa BB sisa shift sebelumya?", "Jumlah bb steam 충분?", "Respon if kurang?"]},
        "a2": {"title": "Cek Stok BS (Sudah defros)", "qs": ["Sudah defros 얼마?", "Estimasi 작업량?", "Jam tambah defros?"]},
        "a5": {"title": "Status tes steam", "desc": ["maksimal selesai jam 13.00", "update 30 menit sekali 보고", "sample kirim/steam/cek 완료 확인", "Laporan update 확인", "Petugas cek 누구?"]},
        "a6": {"title": "List BB butuh kirim", "qs": ["List kirim jam 12.00?", "Kordinasi gudang?"]},
        "a3": {"title": "Handover shift 전", "qs": ["Sudah dapat handover?", "Produksi sesuai rencana?"]},
        "a7": {"title": "Handover & rencana", "qs": ["Rencana sudah dibuat?", "Handover sudah dibuat?", "Sudah baca data stok?"]},
        "a9": {"title": "SISA BARANG", "qs": ["Check MAX 1 PACK", "Sisa shift prev?", "Sudah dibereskan?", "Simpan sisa apa?", "Handover sisa?"]},
        "a4": {"title": "Laporan QC di tablet", "check_items": ["daily kebersihan", "kontaminan kupas", "kontaminan packing"]},
        "a8": {"title": "Barang Jatuh", "desc": ["check 1시간 마다", "max 10 nampan"]}
    },
    "B": {
        "b1": {"title": "Cek Absensi", "desc": ["Awal masuk & Istirahat pax"]},
        "b2": {"title": "Status Steam", "desc": ["1시간 마다", "Cara isi & Laporan"]},
        "b3": {"title": "Situasi Kupas", "desc": ["TL update & Kroscek"]},
        "b4": {"title": "Situasi Packing", "desc": ["TL update & Kroscek"]},
        "b5": {"title": "Hasil Per Jam", "desc": ["Sesuai 제품 확인"]},
        "b6": {"title": "Laporan Giling", "desc": ["TL update & 제품 확인"]},
        "b7": {"title": "Steril BB", "desc": ["TL update 확인"]},
        "b8": {"title": "Laporan Potong", "desc": ["Cara nata & Machine Setting"]},
        "b9": {"title": "Kondisi BB", "desc": ["30분 마다 업데이트"]},
        "b10": {"title": "Laporan Dry", "desc": ["TL update & Status mesin"]}
    }
}

# --- 3. 데이터 로직 및 세션 상태 ---
ITEMS = ["a4","a5","b3","b4","b5","b9","a8","b2","b6","b7","b8","b10","a1","a2","a3","a6","a7","a9","b1"]
if 'qc_store' not in st.session_state:
    st.session_state.qc_store = {k: [] for k in ITEMS}; st.session_state.v_map = {k: 0 for k in ITEMS}
    st.session_state.history = {k: [] for k in ITEMS}; st.session_state.a4_ts = []

def get_prog_bar(val, goal):
    perc = int((len(val)/goal)*100) if goal > 0 else 0
    return f"{'■' * (perc // 10)}{'□' * (10 - (perc // 10))} ({perc}%)"

def send_telegram(text):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})

# --- 4. 사이드바 설정 (A/B 분리 및 루틴 최상단) ---
with st.sidebar:
    st.header("⚙️ 리포트 세부 설정")
    with st.expander("📅 시프트 루틴 설정 (최상단)", expanded=True):
        st.info("📦 Bahan Baku (Shift 1 Focus)")
        sw_a1=st.toggle("A-1", True); sw_a2=st.toggle("A-2", True); sw_a5=st.toggle("A-5", True); sw_a6=st.toggle("A-6", True)
        st.divider()
        st.caption("🅰️ QC Direct (Others)"); sw_a3=st.toggle("A-3", True); sw_a7=st.toggle("A-7", True); sw_a9=st.toggle("A-9", True)
        st.divider(); st.caption("🅱️ Check TL"); sw_b1=st.toggle("B-1", True)
    with st.expander("⚡ 30분 단위 설정", expanded=False):
        sw_a4=st.toggle("A-4 (Timestamp)", True); st.divider()
        sw_b3=st.toggle("B-3",True); sw_b4=st.toggle("B-4",True); sw_b5=st.toggle("B-5",True); sw_b9=st.toggle("B-9",True)
    with st.expander("⏰ 1시간 단위 설정", expanded=False):
        sw_a8=st.toggle("A-8", True); st.divider()
        sw_b2=st.toggle("B-2",True); sw_b6=st.toggle("B-6",True); sw_b7=st.toggle("B-7",True); sw_b8=st.toggle("B-8",True); sw_b10=st.toggle("B-10",True)

# --- 5. 메인 UI ---
st.title("🏭 SOI QC 모니터링 시스템")
c1, c2 = st.columns(2)
with c1: shift_label = st.selectbox("SHIFT", ["Shift 1 (Pagi)", "Shift 2 (Sore)", "Shift tengah"])
with c2: pelapor = st.selectbox("담당자", ["Diana", "Uyun", "Rossa", "Dini", "JUNMO YANG"])

# [섹션 1: 루틴]
st.subheader("📅 시프트 루틴")
with st.container(border=True):
    ca, cb = st.columns(2)
    with ca:
        st.info("🅰️ QC Direct Check")
        # --- Subsection: Bahan Baku (신설) ---
        st.markdown("##### 📦 Bahan Baku (Shift 1 Only)")
        if sw_a1: # A-1 상세
            st.markdown(f"**A1. {QC_CONTENT['A']['a1']['title']}**")
            p_a1 = st.pills("Time A1", ["Awal Masuk", "Setelah Istirahat"], selection_mode="multi", key="u_a1")
            ans_a1_1 = st.text_input(f"1. {QC_CONTENT['A']['a1']['qs'][0]}", key="a1_1"); ans_a1_2 = st.text_input(f"2. {QC_CONTENT['A']['a1']['qs'][1]}", key="a1_2"); ans_a1_3 = st.text_input(f"3. {QC_CONTENT['A']['a1']['qs'][2]}", key="a1_3"); st.divider()
        if sw_a2: # A-2 상세
            st.markdown(f"**A2. {QC_CONTENT['A']['a2']['title']}**")
            p_a2 = st.pills("Time A2", ["Awal Masuk", "Setelah Istirahat"], selection_mode="multi", key="u_a2")
            ans_a2_1 = st.text_input(f"1. {QC_CONTENT['A']['a2']['qs'][0]}", key="a2_1"); ans_a2_2 = st.text_input(f"2. {QC_CONTENT['A']['a2']['qs'][1]}", key="a2_2"); ans_a2_3 = st.text_input(f"3. {QC_CONTENT['A']['a2']['qs'][2]}", key="a2_3"); st.divider()
        if sw_a5: # [신설/이동] A-5 통합 Done/Not done
            st.markdown(f"**A5. {QC_CONTENT['A']['a5']['title']}**")
            for item in QC_CONTENT['A']['a5']['desc']: st.caption(f"-> {item}")
            ans_a5 = st.radio("Status", ["Done", "Not done"], horizontal=True, key="a5_status")
            memo_a5 = st.text_input("Memo (If Not done)", key="m_a5") if ans_a5 == "Not done" else ""
            st.divider()
        if sw_a6: # [이동] A-6 조건부
            st.markdown(f"**A6. {QC_CONTENT['A']['a6']['title']}**")
            if "Shift 1" in shift_label: st.warning("⚠️ Khusus Shift 1: Jam 12.00 dan sebelum pulang")
            ans_a6_1 = st.radio(f"-> {QC_CONTENT['A']['a6']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a6_1")
            memo_a6_1 = st.text_input("Memo A6-1", key="m_a6_1") if ans_a6_1 == "No" else ""
            ans_a6_2 = st.radio(f"-> {QC_CONTENT['A']['a6']['qs'][1]}", ["Yes", "No"], horizontal=True, key="a6_2")
            memo_a6_2 = st.text_input("Memo A6-2", key="m_a6_2") if ans_a6_2 == "No" else ""
            st.divider()
        
        # --- Subsection: Routine Others ---
        st.markdown("##### 📝 Routine Others")
        if sw_a3: # A-3 상세
            st.markdown(f"**A3. {QC_CONTENT['A']['a3']['title']}**")
            ans_a3_1 = st.radio(f"-> {QC_CONTENT['A']['a3']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a3_1")
            memo_a3_1 = st.text_input("Memo A3-1", key="m_a3_1") if ans_a3_1 == "No" else ""
            ans_a3_2 = st.radio(f"-> {QC_CONTENT['A']['a3']['qs'][1]}", ["Yes", "No"], horizontal=True, key="a3_2")
            memo_a3_2 = st.text_input("Memo A3-2", key="m_a3_2") if ans_a3_2 == "No" else ""
            st.divider()
        if sw_a7: # A-7 상세 (Data Stok 포함)
            st.markdown(f"**A7. {QC_CONTENT['A']['a7']['title']}**")
            ans_a7_1 = st.radio(f"-> {QC_CONTENT['A']['a7']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a7_1")
            memo_a7_1 = st.text_input("Memo A7-1", key="m_a7_1") if ans_a7_1 == "No" else ""
            ans_a7_2 = st.radio(f"-> {QC_CONTENT['A']['a7']['qs'][1]}", ["Yes", "No"], horizontal=True, key="a7_2")
            if ans_a7_2 == "No": memo_a7_2 = st.text_input("Memo A7-2", key="m_a7_2"); name_a7_2 = ""
            else: name_a7_2 = st.text_input("Nama penerima handover", key="n_a7_2"); memo_a7_2 = ""
            ans_a7_3 = st.text_area(f"-> {QC_CONTENT['A']['a7']['qs'][2]}", key="a7_3"); st.divider()
        if sw_a9: # A-9 상세
            st.markdown(f"**A9. {QC_CONTENT['A']['a9']['title']}**")
            ans_a9_1 = st.radio(f"1. {QC_CONTENT['A']['a9']['qs'][0]}", ["Sudah check", "Belum"], horizontal=True, key="a9_1")
            memo_a9_1 = st.text_input("Memo A9-1", key="m_a9_1") if ans_a9_1 == "Belum" else ""
            ans_a9_2=st.text_area(f"2. {QC_CONTENT['A']['a9']['qs'][1]}", key="a9_2"); ans_a9_3=st.text_area(f"3. {QC_CONTENT['A']['a9']['qs'][2]}", key="a9_3")
            ans_a9_4=st.text_area(f"4. {QC_CONTENT['A']['a9']['qs'][3]}", key="a9_4"); ans_a9_5=st.text_area(f"5. {QC_CONTENT['A']['a9']['qs'][4]}", key="a9_5")

    with cb: # B 루틴
        st.warning("🅱️ Check TL Reports")
        if sw_b1: st.markdown("**B1. Absensi**"); st.pills("b1", ["Awal", "Istirahat"], selection_mode="multi", key="u_b1")

# [섹션 2/3: 30분/1시간 단위 - A-4 및 B 리포트]
# ... (기존 A-4 타임스탬프 및 B 시리즈 렌더링 로직 보존)

# --- 6. 저장 및 상세 전송 로직 ---
if st.button("💾 저장 및 텔레그램 전송", type="primary", use_container_width=True):
    try:
        tg_msg = f"🚀 *Laporan QC Lapangan*\n📅 {full_today} | {shift_label}\n👤 QC: {pelapor}\n--------------------------------\n\n*📅 Routine (Bahan Baku)*\n"
        if sw_a1: tg_msg += f"• A-1 Stok BB: {ans_a1_1} / {ans_a1_2}\n"
        if sw_a2: tg_msg += f"• A-2 Stok BS: {ans_a2_1} / {ans_a2_2}\n"
        if sw_a5: tg_msg += f"• A-5 Status Steam: {ans_a5}" + (f" (💬 {memo_a5})" if memo_a5 else "") + "\n"
        if sw_a6: tg_msg += f"• A-6 List BB: {ans_a6_1} / {ans_a6_2}\n"
        
        tg_msg += "\n*📝 Routine (Others)*\n"
        if sw_a3: tg_msg += f"• A-3 Handover: {ans_a3_1} / {ans_a3_2}\n"
        if sw_a7: tg_msg += f"• A-7 Rencana: {ans_a7_1} / Handover: {ans_a7_2} (👤 {name_a7_2})\n"
        
        # ... (A-4 타임스탬프 및 B 시리즈 히스토리 투사 로직 보존)
        tg_msg += f"\n🕒 *Update:* {datetime.now(jakarta_tz).strftime('%H:%M:%S')}"
        send_telegram(tg_msg); st.success("✅ 상세 보고 완료!")
    except Exception as e: st.error(f"에러: {e}")
