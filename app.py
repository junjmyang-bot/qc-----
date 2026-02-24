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
        "a1": {"title": "Cek Stok BB Sudah steam", "questions": ["Sisa BB sisa shift sebelumya berapa?", "Jumlah bb sudah steam cukup?", "Kalo tidak cukup respon gimana?"]},
        "a2": {"title": "Stok BS Defros", "desc": ["Sudah defros 얼마?", "Estimasi 작업량", "Jam tambah defros"]},
        "a3": {"title": "Handover IN", "desc": ["Dapat handover", "Perubahan rencana 확인"]},
        "a4": {"title": "QC Tablet", "desc": ["laporan daily kebersihan", "laporan kontaminan kupas", "laporan kontaminan packing"]},
        "a5": {"title": "Steam Test", "desc": ["maksimal jam istirahat 전 완료", "sample kirim/steam/cek", "Laporan update"]},
        "a6": {"title": "List BB Kirim", "desc": ["Maksimal jam 12", "Koordinasi gudang/plantation"]},
        "a7": {"title": "Rencana Produksi", "desc": ["Rencana sudah dibuat", "Handover sudah dibuat"]},
        "a8": {"title": "Barang Jatuh", "desc": ["check 1 jam sekali", "max 10 nampan", "segera dibereskan"]},
        "a9": {"title": "Sisa Barang", "desc": ["Maksimal 1 pack", "Sudah dibereskan?", "Baca data stok"]}
    },
    "B": {
        "b1": {"title": "Cek Absensi", "desc": ["Awal masuk & Istirahat", "Steam/Dry/Kupas/Packing pax"]},
        "b2": {"title": "Status Steam", "desc": ["1시간 마다", "Cara isi benar", "Laporan sesuai"]},
        "b3": {"title": "Situasi Kupas", "desc": ["TL sudah update", "Kroscek 본인 확인", "Koordinasi TL packing"]},
        "b4": {"title": "Situasi Packing", "desc": ["TL sudah update", "Kroscek 본인 확인", "Koordinasi TL kupas"]},
        "b5": {"title": "Hasil Per Jam", "desc": ["Sesuai 제품", "TL update 확인"]},
        "b6": {"title": "Laporan Giling", "desc": ["Sesuai 제품", "TL update 확인"]},
        "b7": {"title": "Steril BB", "desc": ["Sesuai 제품", "TL update 확인"]},
        "b8": {"title": "Laporan Potong", "desc": ["Sesuai 제품", "Cara nata & Machine Setting"]},
        "b9": {"title": "Kondisi BB", "desc": ["30분 마다 업데이트", "Laporan sesuai"]},
        "b10": {"title": "Laporan Dry", "desc": ["TL update 확인", "Status mesin 2 kali"]}
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
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, data=payload)

@st.cache_resource
def get_gc_client():
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        raw_json = st.secrets["gcp_service_account"]
        info = json.loads(raw_json, strict=False) 
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        return gspread.authorize(creds)
    except: return None

# --- 4. 사이드바 (루틴 최상단 배치) ---
with st.sidebar:
    st.header("⚙️ 리포트 세부 설정")
    with st.expander("📅 시프트 루틴 설정", expanded=True):
        sw_a1=st.toggle("A-1 Stok BB", True); sw_a2=st.toggle("A-2 Stok BS", True); sw_a3=st.toggle("A-3 Handover IN", True)
        sw_a6=st.toggle("A-6 List BB", True); sw_a7=st.toggle("A-7 Rencana", True); sw_a9=st.toggle("A-9 Sisa Barang", True)
        st.divider(); sw_b1=st.toggle("B-1 Absensi", True)
    with st.expander("⚡ 30분 단위 설정", expanded=False):
        sw_a4=st.toggle("A-4 Laporan QC",True); g_a4=st.number_input("A-4 목표",1,30,16)
        sw_a5=st.toggle("A-5 Status Tes Steam",True); g_a5=st.number_input("A-5 목표",1,30,10)
        sw_b3=st.toggle("B-3 Kupas",True); g_b3=st.number_input("B-3 목표",1,30,16)
        sw_b4=st.toggle("B-4 Packing",True); g_b4=st.number_input("B-4 목표",1,30,16)
        sw_b5=st.toggle("B-5 Hasil",True); g_b5=st.number_input("B-5 목표",1,30,16)
        sw_b9=st.toggle("B-9 Kondisi BB",True); g_b9=st.number_input("B-9 목표",1,30,16)
    with st.expander("⏰ 1시간 단위 설정", expanded=False):
        sw_a8=st.toggle("A-8 Barang Jatuh",True); g_a8=st.number_input("A-8 목표",1,24,8)
        sw_b2=st.toggle("B-2 Status Steam",True); g_b2=st.number_input("B-2 목표",1,24,8)
        sw_b6=st.toggle("B-6 Giling",True); g_b6=st.number_input("B-6 목표",1,24,8)
        sw_b7=st.toggle("B-7 Steril",True); g_b7=st.number_input("B-7 목표",1,24,8)
        sw_b8=st.toggle("B-8 Potong",True); g_b8=st.number_input("B-8 목표",1,24,8)
        sw_b10=st.toggle("B-10 Dry",True); g_b10=st.number_input("B-10 목표",1,24,8)

# --- 5. 메인 UI (루틴 최상단) ---
st.title("🏭 SOI QC 모니터링 시스템")
c1, c2 = st.columns(2)
with c1: shift_label = st.selectbox("SHIFT", ["Shift 1 (Pagi)", "Shift 2 (Sore)", "Shift tengah"])
with c2: pelapor = st.selectbox("담당자", ["Diana", "Uyun", "Rossa", "Dini", "JUNMO YANG"])

# [섹션 1: 시프트 루틴]
st.subheader("📅 시프트 루틴")
with st.container(border=True):
    col_a, col_b = st.columns(2)
    with col_a:
        st.info("🅰️ QC Direct Check")
        if sw_a1: # A-1 상세 매뉴얼 기입
            st.markdown(f"**A1. {QC_CONTENT['A']['a1']['title']}**")
            p_a1 = st.pills("Time", ["Awal Masuk", "Setelah Istirahat"], selection_mode="multi", key="u_a1")
            ans_a1_1 = st.text_input(QC_CONTENT['A']['a1']['questions'][0], key="ans_a1_1")
            ans_a1_2 = st.text_input(QC_CONTENT['A']['a1']['questions'][1], key="ans_a1_2")
            ans_a1_3 = st.text_input(QC_CONTENT['A']['a1']['questions'][2], key="ans_a1_3")
        for k in ["a2", "a3", "a6", "a7", "a9"]:
            if eval(f"sw_{k}"):
                st.markdown(f"**{k.upper()}. {QC_CONTENT['A'][k]['title']}**")
                st.pills(k, ["Awal", "Istirahat", "Jam 12", "Handover", "Closing"], selection_mode="multi", key=f"u_{k}", label_visibility="collapsed")
    with col_b:
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

# --- 6. 저장 및 상세 전송 로직 ---
if st.button("💾 구글 시트 저장 & 텔레그램 전송", type="primary", use_container_width=True):
    try:
        # 히스토리 바 업데이트
        goals = {"a4": g_a4, "a5": g_a5, "b3": g_b3, "b4": g_b4, "b5": g_b5, "b9": g_b9, "a8": g_a8, "b2": g_b2, "b6": g_b6, "b7": g_b7, "b8": g_b8, "b10": g_b10}
        for k, g in goals.items(): st.session_state.history[k].append(get_prog_bar(st.session_state.qc_store[k], g))

        # 텔레그램 메시지 빌더
        tg_msg = f"🚀 *Laporan QC Lapangan*\n📅 {full_today} | {shift_label}\n👤 QC: {pelapor}\n"
        tg_msg += "--------------------------------\n\n"
        
        # [Routine 투사]
        tg_msg += "*📅 Routine*\n"
        if sw_a1:
            tg_msg += f"• A-1. {QC_CONTENT['A']['a1']['title']}\n"
            tg_msg += f"  -> {', '.join(p_a1) if p_a1 else '-'}\n"
            tg_msg += f"  -> Sisa BB: {ans_a1_1}\n  -> Cukup?: {ans_a1_2}\n  -> Respon: {ans_a1_3}\n"
        
        # [30분/1시간 투사]
        for type_key, type_name in [("A", "🅰️ QC Direct"), ("B", "🅱️ Check TL")]:
            tg_msg += f"\n*{type_name}*\n"
            for k, info in QC_CONTENT[type_key].items():
                if k in st.session_state.history and st.session_state.history[k]:
                    tg_msg += f"• {k.upper()}. {info['title']}\n"
                    if 'desc' in info:
                        for line in info['desc']: tg_msg += f"  -> {line}\n"
                    for bar in st.session_state.history[k]: tg_msg += f"  -> {bar}\n"

        tg_msg += f"\n📝 *Memo:* {new_memo}\n🕒 *Update:* {datetime.now(jakarta_tz).strftime('%H:%M:%S')}"
        send_telegram(tg_msg)
        st.success("✅ 저장 및 전송 완료!")
    except Exception as e: st.error(f"에러: {e}")
