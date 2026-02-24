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

# --- 2. [데이터 보존] 19개 전 항목 상세 가이드 및 질문 데이터 ---
QC_CONTENT = {
    "A": {
        "a1": {"title": "Cek Stok BB Sudah steam", "qs": ["Sisa BB sisa shift sebelumya?", "Jumlah bb steam 충분?", "Respon if kurang?"]},
        "a2": {"title": "Cek Stok BS (Sudah defros)", "qs": ["Sudah defros 얼마?", "Estimasi 작업량?", "Jam tambah defros?"]},
        "a3": {"title": "Handover shift 전", "qs": ["Sudah dapat handover?", "Produksi sesuai rencana?"]},
        "a6": {"title": "List BB butuh kirim", "qs": ["List kirim jam 12.00?", "Kordinasi gudang?"]},
        "a7": {"title": "Handover & rencana", "qs": ["Rencana sudah dibuat?", "Handover sudah dibuat?", "Sudah baca data stok?"]},
        "a9": {"title": "SISA BARANG", "qs": ["Check MAX 1 PACK", "Sisa shift prev?", "Sudah dibereskan?", "Simpan sisa apa?", "Handover sisa?"]},
        "a4": {"title": "Laporan QC di tablet", "check_items": ["daily kebersihan", "kontaminan kupas", "kontaminan packing"]},
        "a5": {"title": "Steam Test", "desc": ["maksimal jam istirahat 전 완료"]},
        "a8": {"title": "Barang Jatuh", "desc": ["check 1시간 마다", "max 10 nampan"]}
    },
    "B": {
        "b1": {"title": "Cek Absensi", "desc": ["Awal masuk & Istirahat"]},
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

def fast_cascade(key):
    v_idx = st.session_state.v_map[key]
    raw = st.session_state[f"u_{key}_{v_idx}"]
    if not raw: st.session_state.qc_store[key] = []
    else:
        nums = [int(x) for x in raw if x.isdigit()]
        if nums: st.session_state.qc_store[key] = [str(i) for i in range(1, max(nums) + 1)]
    st.session_state.v_map[key] += 1

def get_prog_bar(val, goal):
    perc = int((len(val)/goal)*100) if goal > 0 else 0
    return f"{'■' * (perc // 10)}{'□' * (10 - (perc // 10))} ({perc}%)"

def send_telegram(text):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})

# --- 4. [복구] 사이드바 설정 (A/B 분리 및 루틴 최상단) ---
with st.sidebar:
    st.header("⚙️ 리포트 세부 설정")
    with st.expander("📅 시프트 루틴 설정", expanded=True):
        st.caption("🅰️ QC Direct"); sw_a1=st.toggle("A-1",True); sw_a2=st.toggle("A-2",True); sw_a3=st.toggle("A-3",True); sw_a6=st.toggle("A-6",True); sw_a7=st.toggle("A-7",True); sw_a9=st.toggle("A-9",True)
        st.divider(); st.caption("🅱️ Check TL"); sw_b1=st.toggle("B-1",True)
    with st.expander("⚡ 30분 단위 설정", expanded=False):
        st.caption("🅰️ QC Direct"); sw_a4=st.toggle("A-4",True); sw_a5=st.toggle("A-5",True); g_a5=st.number_input("A5 목표",1,30,10)
        st.divider(); st.caption("🅱️ Check TL"); sw_b3=st.toggle("B-3",True); g_b3=16; sw_b4=st.toggle("B-4",True); g_b4=16; sw_b5=st.toggle("B-5",True); g_b5=16; sw_b9=st.toggle("B-9",True); g_b9=16
    with st.expander("⏰ 1시간 단위 설정", expanded=False):
        st.caption("🅰️ QC Direct"); sw_a8=st.toggle("A-8",True); g_a8=8
        st.divider(); st.caption("🅱️ Check TL"); sw_b2=st.toggle("B-2",True); g_b2=8; sw_b6=st.toggle("B-6",True); g_b6=8; sw_b7=st.toggle("B-7",True); g_b7=8; sw_b8=st.toggle("B-8",True); g_b8=8; sw_b10=st.toggle("B-10",True); g_b10=8

# --- 5. 메인 UI (A/B 분리 레이아웃) ---
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
        if sw_a1:
            st.markdown(f"**A1. {QC_CONTENT['A']['a1']['title']}**")
            p_a1 = st.pills("Time A1", ["Awal Masuk", "Setelah Istirahat"], selection_mode="multi", key="u_a1")
            ans_a1_1 = st.text_input(f"1. {QC_CONTENT['A']['a1']['qs'][0]}", key="a1_1"); ans_a1_2 = st.text_input(f"2. {QC_CONTENT['A']['a1']['qs'][1]}", key="a1_2"); ans_a1_3 = st.text_input(f"3. {QC_CONTENT['A']['a1']['qs'][2]}", key="a1_3"); st.divider()
        if sw_a2:
            st.markdown(f"**A2. {QC_CONTENT['A']['a2']['title']}**")
            p_a2 = st.pills("Time A2", ["Awal Masuk", "Setelah Istirahat"], selection_mode="multi", key="u_a2")
            ans_a2_1 = st.text_input(f"1. {QC_CONTENT['A']['a2']['qs'][0]}", key="a2_1"); ans_a2_2 = st.text_input(f"2. {QC_CONTENT['A']['a2']['qs'][1]}", key="a2_2"); ans_a2_3 = st.text_input(f"3. {QC_CONTENT['A']['a2']['qs'][2]}", key="a2_3"); st.divider()
        if sw_a3:
            st.markdown(f"**A3. {QC_CONTENT['A']['a3']['title']}**")
            ans_a3_1 = st.radio(f"-> {QC_CONTENT['A']['a3']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a3_1")
            memo_a3_1 = st.text_input("Memo A3-1", key="m_a3_1") if ans_a3_1 == "No" else ""
            ans_a3_2 = st.radio(f"-> {QC_CONTENT['A']['a3']['qs'][1]}", ["Yes", "No"], horizontal=True, key="a3_2")
            memo_a3_2 = st.text_input("Memo A3-2", key="m_a3_2") if ans_a3_2 == "No" else ""
            st.divider()
        if sw_a6:
            st.markdown(f"**A6. {QC_CONTENT['A']['a6']['title']}**")
            if "Shift 1" in shift_label: st.warning("⚠️ Shift 1: Jam 12.00 & sebelum pulang")
            ans_a6_1 = st.radio(f"-> {QC_CONTENT['A']['a6']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a6_1")
            memo_a6_1 = st.text_input("Memo A6-1", key="m_a6_1") if ans_a6_1 == "No" else ""
            ans_a6_2 = st.radio(f"-> {QC_CONTENT['A']['a6']['qs'][1]}", ["Yes", "No"], horizontal=True, key="a6_2")
            memo_a6_2 = st.text_input("Memo A6-2", key="m_a6_2") if ans_a6_2 == "No" else ""
            st.divider()
        if sw_a7:
            st.markdown(f"**A7. {QC_CONTENT['A']['a7']['title']}**")
            ans_a7_1 = st.radio(f"-> {QC_CONTENT['A']['a7']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a7_1")
            memo_a7_1 = st.text_input("Memo A7-1", key="m_a7_1") if ans_a7_1 == "No" else ""
            ans_a7_2 = st.radio(f"-> {QC_CONTENT['A']['a7']['qs'][1]}", ["Yes", "No"], horizontal=True, key="a7_2")
            if ans_a7_2 == "No": memo_a7_2 = st.text_input("Memo A7-2", key="m_a7_2"); name_a7_2 = ""
            else: name_a7_2 = st.text_input("Penerima Handover", key="n_a7_2"); memo_a7_2 = ""
            ans_a7_3 = st.text_area(f"-> {QC_CONTENT['A']['a7']['qs'][2]}", key="a7_3"); st.divider()
        if sw_a9:
            st.markdown(f"**A9. {QC_CONTENT['A']['a9']['title']}**")
            ans_a9_1 = st.radio(f"1. {QC_CONTENT['A']['a9']['qs'][0]}", ["Sudah check", "Belum"], horizontal=True, key="a9_1")
            memo_a9_1 = st.text_input("Memo A9-1", key="m_a9_1") if ans_a9_1 == "Belum" else ""
            ans_a9_2 = st.text_area(f"2. {QC_CONTENT['A']['a9']['qs'][1]}", key="a9_2")
            ans_a9_3 = st.text_area(f"3. {QC_CONTENT['A']['a9']['qs'][2]}", key="a9_3")
            ans_a9_4 = st.text_area(f"4. {QC_CONTENT['A']['a9']['qs'][3]}", key="a9_4")
            ans_a9_5 = st.text_area(f"5. {QC_CONTENT['A']['a9']['qs'][4]}", key="a9_5")
    with cb:
        st.warning("🅱️ Check TL Reports")
        if sw_b1: st.markdown("**B1. Absensi**"); st.pills("b1", ["Awal", "Istirahat"], selection_mode="multi", key="u_b1")

# [섹션 2: 30분 단위]
st.subheader("⚡ 30분 단위")
with st.container(border=True):
    ca, cb = st.columns(2)
    with ca:
        st.info("🅰️ QC Direct Check")
        if sw_a4: # A-4 타임스탬프 로직
            st.markdown(f"**A4. {QC_CONTENT['A']['a4']['title']}**")
            for item in QC_CONTENT['A']['a4']['check_items']: st.caption(f"-> {item}")
            cols = st.columns(4)
            for i in range(16):
                with cols[i % 4]:
                    txt = st.session_state.a4_ts[i] if i < len(st.session_state.a4_ts) else str(i+1)
                    if st.button(txt, key=f"a4_b_{i}", disabled=(i != len(st.session_state.a4_ts)), use_container_width=True):
                        st.session_state.a4_ts.append(datetime.now(jakarta_tz).strftime("%H:%M")); st.rerun()
            st.text_input("A4 코멘트", key="m_a4")
        if sw_a5:
            st.markdown(f"**A5. {QC_CONTENT['A']['a5']['title']}**")
            v5 = st.session_state.v_map["a5"]; st.pills("a5", [str(i) for i in range(1, g_a5+1)], key=f"u_a5_{v5}", on_change=fast_cascade, args=("a5",), selection_mode="multi", label_visibility="collapsed", default=st.session_state.qc_store["a5"])
            st.text_input("A5 코멘트", key="m_a5")
    with cb:
        st.warning("🅱️ Check TL Reports")
        for k in ["b3", "b4", "b5", "b9"]:
            if eval(f"sw_{k}"):
                st.markdown(f"**{k.upper()}. {QC_CONTENT['B'][k]['title']}**")
                vk = st.session_state.v_map[k]; st.pills(k, [str(i) for i in range(1, 17)], key=f"u_{k}_{vk}", on_change=fast_cascade, args=(k,), selection_mode="multi", label_visibility="collapsed", default=st.session_state.qc_store[k])
                st.text_input(f"{k} 코멘트", key=f"m_{k}")

# [섹션 3: 1시간 단위]
st.subheader("⏰ 1시간 단위")
with st.container(border=True):
    ca, cb = st.columns(2)
    with ca:
        if sw_a8:
            st.markdown(f"**A8. {QC_CONTENT['A']['a8']['title']}**")
            v8 = st.session_state.v_map["a8"]; st.pills("a8", [str(i) for i in range(1, 9)], key=f"u_a8_{v8}", on_change=fast_cascade, args=("a8",), selection_mode="multi", label_visibility="collapsed", default=st.session_state.qc_store["a8"])
            st.text_input("A8 코멘트", key="m_a8")
    with cb:
        for k in ["b2", "b6", "b7", "b8", "b10"]:
            if eval(f"sw_{k}"):
                st.markdown(f"**{k.upper()}. {QC_CONTENT['B'][k]['title']}**")
                vk = st.session_state.v_map[k]; st.pills(k, [str(i) for i in range(1, 9)], key=f"u_{k}_{vk}", on_change=fast_cascade, args=(k,), selection_mode="multi", label_visibility="collapsed", default=st.session_state.qc_store[k])
                st.text_input(f"{k} 코멘트", key=f"m_{k}")

new_memo = st.text_area("종합 특이사항", key="main_memo")

# --- 6. 저장 및 상세 전송 로직 ---
if st.button("💾 저장 및 텔레그램 전송", type="primary", use_container_width=True):
    try:
        # 히스토리 바 업데이트
        goals = {"a4": 16, "a5": g_a5, "b3": 16, "b4": 16, "b5": 16, "b9": 16, "a8": 8, "b2": 8, "b6": 8, "b7": 8, "b8": 8, "b10": 8}
        for k, g in goals.items():
            current_data = st.session_state.a4_ts if k == "a4" else st.session_state.qc_store[k]
            st.session_state.history[k].append(get_prog_bar(current_data, g))

        tg_msg = f"🚀 *Laporan QC Lapangan*\n📅 {full_today} | {shift_label}\n👤 QC: {pelapor}\n--------------------------------\n\n*📅 Routine*\n"
        if sw_a1: tg_msg += f"• A-1: {ans_a1_1} / {ans_a1_2}\n"
        if sw_a3: tg_msg += f"• A-3 Handover: {ans_a3_1}" + (f"({memo_a3_1})" if memo_a3_1 else "") + "\n"
        if sw_a7: tg_msg += f"• A-7: {ans_a7_1} / Handover: {ans_a7_2} (👤 {name_a7_2})\n  Data Stok: {ans_a7_3}\n"
        if sw_a9: tg_msg += f"• A-9: {ans_a9_1}\n  Sisa Shift Ini: {ans_a9_4}\n"
        
        for type_key, type_name in [("A", "🅰️ QC Direct"), ("B", "🅱️ Check TL")]:
            tg_msg += f"\n*{type_name}*\n"
            for k, info in QC_CONTENT[type_key].items():
                if k in st.session_state.history and st.session_state.history[k]:
                    tg_msg += f"• {k.upper()}. {info['title']}\n"
                    if k == "a4" and st.session_state.a4_ts: tg_msg += f"  🕒 TS: {' | '.join(st.session_state.a4_ts)}\n"
                    for bar in st.session_state.history[k]: tg_msg += f"  -> {bar}\n"

        tg_msg += f"\n📝 *Memo:* {new_memo}\n🕒 *Update:* {datetime.now(jakarta_tz).strftime('%H:%M:%S')}"
        send_telegram(tg_msg); st.success("✅ 상세 보고 완료!")
    except Exception as e: st.error(f"에러: {e}")
