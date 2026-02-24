import streamlit as st
from datetime import datetime
import gspread
import json
import pytz 
import requests
from google.oauth2.service_account import Credentials

# --- 1. 기본 설정 및 시간 (자카르타 기준) ---
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
        "a1": {"title": "Cek Stok BB Sudah steam", "qs": ["Sisa BB sisa shift sebelumya?", "Jumlah bb steam cukup?", "Kalo tidak cukup respon?"]},
        "a2": {"title": "Cek Stok BS (Sudah di defros)", "qs": ["Sudah defros berapa?", "Estimasi kerjakan berapa?", "Jam berapa tambah defros?"]},
        "a3": {"title": "Handover dari shift sebelumnya", "qs": ["sudah dapat handover dari shift sebelumnya", "Produksi jalan sesuai dengan rencana"]},
        "a6": {"title": "List BB butuh kirim", "qs": ["List kirim maksimal jam 12.00 sudah ada", "kordinasi dengan gudang & plantation"]},
        "a7": {"title": "Handover & rencana produksi", "qs": ["rencana produksi sudah dibuat", "handover sudah dibuat", "Sudah baca data stok?"]},
        "a9": {"title": "SISA BARANG", "qs": ["sisa barang masing-masing produk (MAX 1 PACK)", "sisa barang shift sebelumnya apa saja?", "sisa barang apa yang sudah dibereskan?", "di shift mu simpan sisa apa?", "sisa barang mu sudah dihandover?"]},
        "a4": {"title": "QC Tablet", "desc": ["laporan daily kebersihan", "laporan kontaminan kupas", "laporan kontaminan packing"]},
        "a5": {"title": "Steam Test", "desc": ["maksimal jam istirahat 전 완료", "sample kirim/steam/cek", "Laporan update"]},
        "a8": {"title": "Barang Jatuh", "desc": ["1시간 마다 체크", "max 10 nampan", "segera dibereskan"]}
    },
    "B": {
        "b1": {"title": "Cek Absensi", "desc": ["Awal masuk & Istirahat", "Steam/Dry/Kupas/Packing pax"]},
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
    st.session_state.qc_store = {k: [] for k in ITEMS}
    st.session_state.v_map = {k: 0 for k in ITEMS}
    st.session_state.history = {k: [] for k in ITEMS}

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

# --- 4. 사이드바 (루틴 최상단 배치 및 A/B 분리) ---
with st.sidebar:
    st.header("⚙️ 리포트 세부 설정")
    with st.expander("📅 시프트 루틴 설정 (가장 중요)", expanded=True):
        st.caption("🅰️ QC Direct Check")
        sw_a1=st.toggle("A-1 Stok BB", True); sw_a2=st.toggle("A-2 Stok BS", True); sw_a3=st.toggle("A-3 Handover IN", True)
        sw_a6=st.toggle("A-6 List BB", True); sw_a7=st.toggle("A-7 Rencana", True); sw_a9=st.toggle("A-9 Sisa Barang", True)
        st.divider(); st.caption("🅱️ Check TL Reports")
        sw_b1=st.toggle("B-1 Absensi", True)
    with st.expander("⚡ 30분 단위 설정", expanded=False):
        st.caption("🅰️ QC Direct Check")
        sw_a4=st.toggle("A-4 QC Tablet", True); g_a4=st.number_input("A-4 목표", 1, 30, 16)
        sw_a5=st.toggle("A-5 Steam Test", True); g_a5=st.number_input("A-5 목표", 1, 30, 10)
        st.divider(); st.caption("🅱️ Check TL Reports")
        sw_b3=st.toggle("B-3 Kupas", True); g_b3=st.number_input("B-3 목표", 1, 30, 16)
        sw_b4=st.toggle("B-4 Packing", True); g_b4=st.number_input("B-4 목표", 1, 30, 16)
        sw_b5=st.toggle("B-5 Hasil", True); g_b5=st.number_input("B-5 목표", 1, 30, 16)
        sw_b9=st.toggle("B-9 Kondisi BB", True); g_b9=st.number_input("B-9 목표", 1, 30, 16)
    with st.expander("⏰ 1시간 단위 설정", expanded=False):
        st.caption("🅰️ QC Direct Check")
        sw_a8=st.toggle("A-8 Barang Jatuh", True); g_a8=st.number_input("A-8 목표", 1, 24, 8)
        st.divider(); st.caption("🅱️ Check TL Reports")
        sw_b2=st.toggle("B-2 Status Steam", True); g_b2=st.number_input("B-2 목표", 1, 24, 8)
        sw_b6=st.toggle("B-6 Giling", True); g_b6=st.number_input("B-6 목표", 1, 24, 8)
        sw_b7=st.toggle("B-7 Steril", True); g_b7=st.number_input("B-7 목표", 1, 24, 8)
        sw_b8=st.toggle("B-8 Potong", True); g_b8=st.number_input("B-8 목표", 1, 24, 8)
        sw_b10=st.toggle("B-10 Dry", True); g_b10=st.number_input("B-10 목표", 1, 24, 8)

# --- 5. 메인 UI (그리드 레이아웃) ---
st.title("🏭 SOI QC 모니터링 시스템")
c1, c2 = st.columns(2)
with c1: shift_label = st.selectbox("SHIFT", ["Shift 1 (Pagi)", "Shift 2 (Sore)", "Shift tengah"])
with c2: pelapor = st.selectbox("담당자", ["Diana", "Uyun", "Rossa", "Dini", "JUNMO YANG"])

# [섹션 1: 시프트 루틴]
st.subheader("📅 시프트 루틴")
with st.container(border=True):
    cola, colb = st.columns(2)
    with cola:
        st.info("🅰️ QC Direct Check")
        if sw_a1:
            st.markdown(f"**A1. {QC_CONTENT['A']['a1']['title']}**")
            p_a1 = st.pills("Time A1", ["Awal Masuk", "Setelah Istirahat"], selection_mode="multi", key="u_a1")
            ans_a1_1 = st.text_input(f"1. {QC_CONTENT['A']['a1']['qs'][0]}", key="ans_a1_1")
            ans_a1_2 = st.text_input(f"2. {QC_CONTENT['A']['a1']['qs'][1]}", key="ans_a1_2")
            ans_a1_3 = st.text_input(f"3. {QC_CONTENT['A']['a1']['qs'][2]}", key="ans_a1_3"); st.divider()
        if sw_a2:
            st.markdown(f"**A2. {QC_CONTENT['A']['a2']['title']}**")
            p_a2 = st.pills("Time A2", ["Awal Masuk", "Setelah Istirahat"], selection_mode="multi", key="u_a2")
            ans_a2_1 = st.text_input(f"1. {QC_CONTENT['A']['a2']['qs'][0]}", key="ans_a2_1")
            ans_a2_2 = st.text_input(f"2. {QC_CONTENT['A']['a2']['qs'][1]}", key="ans_a2_2")
            ans_a2_3 = st.text_input(f"3. {QC_CONTENT['A']['a2']['qs'][2]}", key="ans_a2_3"); st.divider()
        if sw_a3:
            st.markdown(f"**A3. {QC_CONTENT['A']['a3']['title']}**")
            ans_a3_1 = st.radio(f"-> {QC_CONTENT['A']['a3']['qs'][0]}", ["Yes", "No"], key="ans_a3_1", horizontal=True)
            memo_a3_1 = st.text_input("Memo (A3-1 No)", key="memo_a3_1") if ans_a3_1 == "No" else ""
            ans_a3_2 = st.radio(f"-> {QC_CONTENT['A']['a3']['qs'][1]}", ["Yes", "No"], key="ans_a3_2", horizontal=True)
            memo_a3_2 = st.text_input("Memo (A3-2 No)", key="memo_a3_2") if ans_a3_2 == "No" else ""
            st.divider()
        if sw_a6:
            st.markdown(f"**A6. {QC_CONTENT['A']['a6']['title']}**")
            if "Shift 1" in shift_label: st.warning("⚠️ Khusus Shift 1: Jam 12.00 dan sebelum pulang")
            ans_a6_1 = st.radio(f"-> {QC_CONTENT['A']['a6']['qs'][0]}", ["Yes", "No"], key="ans_a6_1", horizontal=True)
            memo_a6_1 = st.text_input("Memo (A6-1 No)", key="memo_a6_1") if ans_a6_1 == "No" else ""
            ans_a6_2 = st.radio(f"-> {QC_CONTENT['A']['a6']['qs'][1]}", ["Yes", "No"], key="ans_a6_2", horizontal=True)
            memo_a6_2 = st.text_input("Memo (A6-2 No)", key="memo_a6_2") if ans_a6_2 == "No" else ""
            st.divider()
        if sw_a7:
            st.markdown(f"**A7. {QC_CONTENT['A']['a7']['title']}**")
            ans_a7_1 = st.radio(f"-> {QC_CONTENT['A']['a7']['qs'][0]}", ["Yes", "No"], key="ans_a7_1", horizontal=True)
            memo_a7_1 = st.text_input("Memo (A7-1 No)", key="memo_a7_1") if ans_a7_1 == "No" else ""
            ans_a7_2 = st.radio(f"-> {QC_CONTENT['A']['a7']['qs'][1]}", ["Yes", "No"], key="ans_a7_2", horizontal=True)
            if ans_a7_2 == "No": memo_a7_2 = st.text_input("Memo (A7-2 No)", key="memo_a7_2"); name_a7_2 = ""
            else: name_a7_2 = st.text_input("Nama penerima handover", key="name_a7_2"); memo_a7_2 = ""
            ans_a7_3 = st.text_area(f"-> {QC_CONTENT['A']['a7']['qs'][2]}", key="ans_a7_3"); st.divider()
        if sw_a9:
            st.markdown(f"**A9. {QC_CONTENT['A']['a9']['title']}**")
            ans_a9_1 = st.radio(f"1. {QC_CONTENT['A']['a9']['qs'][0]}", ["Sudah check", "Belum"], key="ans_a9_1", horizontal=True)
            memo_a9_1 = st.text_input("Memo (A9-1 Belum)", key="memo_a9_1") if ans_a9_1 == "Belum" else ""
            ans_a9_2 = st.text_area(f"2. {QC_CONTENT['A']['a9']['qs'][1]}", key="ans_a9_2")
            ans_a9_3 = st.text_area(f"3. {QC_CONTENT['A']['a9']['qs'][2]}", key="ans_a9_3")
            ans_a9_4 = st.text_area(f"4. {QC_CONTENT['A']['a9']['qs'][3]}", key="ans_a9_4")
            ans_a9_5 = st.text_area(f"5. {QC_CONTENT['A']['a9']['qs'][4]}", key="ans_a9_5")
    with colb:
        st.warning("🅱️ Check TL Reports")
        if sw_b1:
            st.markdown(f"**B1. {QC_CONTENT['B']['b1']['title']}**")
            st.pills("b1", ["Awal", "Istirahat"], selection_mode="multi", key="u_b1")

# [섹션 2: 30분 단위]
st.subheader("⚡ 30분 단위")
with st.container(border=True):
    ca, cb = st.columns(2)
    with ca:
        for k, g, sw in [("a4", g_a4, sw_a4), ("a5", g_a5, sw_a5)]:
            if sw:
                st.markdown(f"**{k.upper()}. {QC_CONTENT['A'][k]['title']}**")
                v = st.session_state.v_map[k]
                st.pills(k, [str(i) for i in range(1, g+1)], key=f"u_{k}_{v}", on_change=fast_cascade, args=(k,), selection_mode="multi", label_visibility="collapsed", default=st.session_state.qc_store[k])
                st.text_input("코멘트", key=f"m_{k}")
    with cb:
        for k, g, sw in [("b3", g_b3, sw_b3), ("b4", g_b4, sw_b4), ("b5", g_b5, sw_b5), ("b9", g_b9, sw_b9)]:
            if sw:
                st.markdown(f"**{k.upper()}. {QC_CONTENT['B'][k]['title']}**")
                v = st.session_state.v_map[k]
                st.pills(k, [str(i) for i in range(1, g+1)], key=f"u_{k}_{v}", on_change=fast_cascade, args=(k,), selection_mode="multi", label_visibility="collapsed", default=st.session_state.qc_store[k])
                st.text_input("코멘트", key=f"m_{k}")

# [섹션 3: 1시간 단위]
st.subheader("⏰ 1시간 단위")
with st.container(border=True):
    ca, cb = st.columns(2)
    with ca:
        if sw_a8:
            st.markdown(f"**A8. {QC_CONTENT['A']['a8']['title']}**")
            v = st.session_state.v_map["a8"]; st.pills("a8", [str(i) for i in range(1, g_a8+1)], key=f"u_a8_{v}", on_change=fast_cascade, args=("a8",), selection_mode="multi", label_visibility="collapsed", default=st.session_state.qc_store["a8"])
            st.text_input("코멘트", key="m_a8")
    with cb:
        for k, g, sw in [("b2", g_b2, sw_b2), ("b6", g_b6, sw_b6), ("b7", g_b7, sw_b7), ("b8", g_b8, sw_b8), ("b10", g_b10, sw_b10)]:
            if sw:
                st.markdown(f"**{k.upper()}. {QC_CONTENT['B'][k]['title']}**")
                v = st.session_state.v_map[k]; st.pills(k, [str(i) for i in range(1, g+1)], key=f"u_{k}_{v}", on_change=fast_cascade, args=(k,), selection_mode="multi", label_visibility="collapsed", default=st.session_state.qc_store[k])
                st.text_input("코멘트", key=f"m_{k}")

new_memo = st.text_area("종합 메모", key="main_memo")

# --- 6. 저장 및 상세 텔레그램 전송 ---
if st.button("💾 저장 및 텔레그램 전송", type="primary", use_container_width=True):
    try:
        # 히스토리 바 업데이트
        goals = {"a4": g_a4, "a5": g_a5, "b3": g_b3, "b4": g_b4, "b5": g_b5, "b9": g_b9, "a8": g_a8, "b2": g_b2, "b6": g_b6, "b7": g_b7, "b8": g_b8, "b10": g_b10}
        for k, g in goals.items(): st.session_state.history[k].append(get_prog_bar(st.session_state.qc_store[k], g))

        tg_msg = f"🚀 *Laporan QC Lapangan*\n📅 {full_today} | {shift_label}\n👤 QC: {pelapor}\n--------------------------------\n\n*📅 Routine*\n"
        if sw_a1: tg_msg += f"• A-1: {ans_a1_1} / {ans_a1_2}\n"
        if sw_a2: tg_msg += f"• A-2: {ans_a2_1} / {ans_a2_2} / {ans_a2_3}\n"
        if sw_a3: tg_msg += f"• A-3: {ans_a3_1} / {ans_a3_2}\n"
        if sw_a7: tg_msg += f"• A-7: {ans_a7_1} / Handover: {ans_a7_2} (👤 {name_a7_2})\n  Data Stok: {ans_a7_3}\n"
        if sw_a9: tg_msg += f"• A-9: {ans_a9_1}\n  Sisa Shift Ini: {ans_a9_4}\n"
        
        for type_key, type_name in [("A", "🅰️ QC Direct"), ("B", "🅱️ Check TL")]:
            tg_msg += f"\n*{type_name}*\n"
            for k, info in QC_CONTENT[type_key].items():
                if k in st.session_state.history and st.session_state.history[k]:
                    tg_msg += f"• {k.upper()}. {info['title']}\n"
                    for bar in st.session_state.history[k]: tg_msg += f"  -> {bar}\n"

        tg_msg += f"\n📝 *Memo:* {new_memo}\n🕒 *Update:* {datetime.now(jakarta_tz).strftime('%H:%M:%S')}"
        send_telegram(tg_msg)
        st.success("✅ 상세 리포트 전송 완료!")
    except Exception as e: st.error(f"에러: {e}")
