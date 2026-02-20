import streamlit as st
from datetime import datetime, timedelta
import gspread
import json
import pytz  # 👈 자카르타 시간 설정을 위한 부품
from google.oauth2.service_account import Credentials

# --- 1. 앱 세팅 및 자카르타 시간 설정 ---
st.set_page_config(page_title="SOI QC HIGH-SPEED", layout="wide", page_icon="🏭")

# 자카르타 시간(WIB) 고정
jakarta_tz = pytz.timezone('Asia/Jakarta')
now_jakarta = datetime.now(jakarta_tz)
today = now_jakarta.strftime('%Y-%m-%d')
current_time_full = now_jakarta.strftime('%H:%M:%S')

# 🌟 화면 최적화 CSS
st.markdown("<style>div[data-testid='stStatusWidget']{display:none!important;}.main{background-color:white!important;}</style>", unsafe_allow_html=True)

# 🌟 구글 시트 연결
@st.cache_resource
def get_worksheet():
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        raw_json = st.secrets["gcp_service_account"]
        info = json.loads(raw_json, strict=False) 
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        gc = gspread.authorize(creds)
        SHEET_URL = 'https://docs.google.com/spreadsheets/d/1kR2C_7IxC_5FpztsWQaBMT8EtbcDHerKL6YLGfQucWw/edit'
        return gc.open_by_url(SHEET_URL).sheet1
    except Exception as e:
        st.error(f"🚨 연결 에러: {e}")
        return None

worksheet = get_worksheet()

# --- 2. 데이터 저장소 설정 ---
ITEMS = ["a4","a5","b3","b4","b5","b9","a8","b2","b6","b7","b8","b10","a1","a2","a3","a6","a7","a9","b1"]
if 'qc_store' not in st.session_state:
    st.session_state.qc_store = {k: [] for k in ITEMS}
    st.session_state.v_map = {k: 0 for k in ITEMS}

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

# --- 3. 사이드바 설정 (항목 사라짐 방지) ---
with st.sidebar:
    st.header("⚙️ 리포트 세부 설정")
    with st.expander("⚡ 30분 단위", expanded=True):
        sw_a4=st.toggle("A-4",True); g_a4=st.number_input("A-4 목표",1,30,16)
        sw_a5=st.toggle("A-5",True); g_a5=st.number_input("A-5 목표",1,30,10)
        sw_b3=st.toggle("B-3",True); g_b3=st.number_input("B-3 목표",1,30,16)
        sw_b4=st.toggle("B-4",True); g_b4=st.number_input("B-4 목표",1,30,16)
        sw_b5=st.toggle("B-5",True); g_b5=st.number_input("B-5 목표",1,30,16)
        sw_b9=st.toggle("B-9",True); g_b9=st.number_input("B-9 목표",1,30,16)
    with st.expander("⏰ 1시간 단위", expanded=False):
        sw_a8=st.toggle("A-8",True); g_a8=st.number_input("A-8 목표",1,24,8)
        sw_b2=st.toggle("B-2",True); g_b2=st.number_input("B-2 목표",1,24,8)
        sw_b6=st.toggle("B-6",True); g_b6=st.number_input("B-6 목표",1,24,8)
        sw_b7=st.toggle("B-7",True); g_b7=st.number_input("B-7 목표",1,24,8)
        sw_b8=st.toggle("B-8",True); g_b8=st.number_input("B-8 목표",1,24,8)
        sw_b10=st.toggle("B-10",True); g_b10=st.number_input("B-10 목표",1,24,8)
    with st.expander("📅 시프트 루틴", expanded=False):
        sw_a1=st.toggle("A-1",True); g_a1=st.number_input("A-1 목표",1,5,2)
        sw_a2=st.toggle("A-2",True); g_a2=st.number_input("A-2 목표",1,5,2)
        sw_a3=st.toggle("A-3",True); g_a3=st.number_input("A-3 목표",1,5,1)
        sw_a6=st.toggle("A-6",True); g_a6=st.number_input("A-6 목표",1,5,2)
        sw_a7=st.toggle("A-7",True); g_a7=st.number_input("A-7 목표",1,5,1)
        sw_a9=st.toggle("A-9",True); g_a9=st.number_input("A-9 목표",1,5,1)
        sw_b1=st.toggle("B-1",True); g_b1=st.number_input("B-1 목표",1,5,2)

# --- 4. 메인 UI ---
st.title("🏭 QC 모니터링 시스템")
c1, c2 = st.columns(2)
with c1: shift = st.selectbox("SHIFT", ["Shift 1 (Pagi)", "Shift 2 (Sore)", "Shift tengah"])
with c2: pelapor = st.text_input("담당자", value="JUNMO YANG")

def draw(label, key, goal, show):
    if show:
        st.markdown(f"**{label}**")
        v = st.session_state.v_map[key]
        st.pills(label, [str(i) for i in range(1, goal+1)], key=f"u_{key}_{v}", on_change=fast_cascade, args=(key,), selection_mode="multi", label_visibility="collapsed", default=st.session_state.qc_store[key])
        return st.text_input(f"{label} 코멘트", key=f"m_{key}")
    return ""

st.subheader("⚡ 30분 단위")
with st.container(border=True):
    m_a4=draw("A-4 QC Tablet","a4",g_a4,sw_a4); m_a5=draw("A-5 Steam Test","a5",g_a5,sw_a5)
    m_b3=draw("B-3 Kupas","b3",g_b3,sw_b3); m_b4=draw("B-4 Packing","b4",g_b4,sw_b4)
    m_b5=draw("B-5 Hasil Per Jam","b5",g_b5,sw_b5); m_b9=draw("B-9 Kondisi BB","b9",g_b9,sw_b9)

st.subheader("⏰ 1시간 단위")
with st.container(border=True):
    m_a8=draw("A-8 Barang Jatuh","a8",g_a8,sw_a8); m_b2=draw("B-2 Status Steam","b2",g_b2,sw_b2)
    m_b6=draw("B-6 Giling","b6",g_b6,sw_b6); m_b7=draw("B-7 Steril","b7",g_b7,sw_b7)
    m_b8=draw("B-8 Potong","b8",g_b8,sw_b8); m_b10=draw("B-10 Dry","b10",g_b10,sw_b10)

st.subheader("📅 시프트 루틴")
with st.container(border=True):
    def routine(label, g, show, key):
        if show:
            st.markdown(f"**{label}**")
            p = st.pills(label, ["Awal", "Istirahat", "Jam 12", "Handover", "Closing"][:g], selection_mode="multi", key=f"u_{key}")
            return p, st.text_input(f"{label} 메모", key=f"m_{key}")
        return [], ""
    p_a1,m_a1=routine("A-1 Stok BB",g_a1,sw_a1,"a1"); p_a2,m_a2=routine("A-2 Stok BS",g_a2,sw_a2,"a2")
    p_a3,m_a3=routine("A-3 Handover IN",g_a3,sw_a3,"a3"); p_a6,m_a6=routine("A-6 List BB",g_a6,sw_a6,"a6")
    p_a7,m_a7=routine("A-7 Rencana",g_a7,sw_a7,"a7"); p_a9,m_a9=routine("A-9 Sisa Barang",g_a9,sw_a9,"a9")
    p_b1,m_b1=routine("B-1 Absensi",g_b1,sw_b1,"b1")

st.subheader("📝 종합 메모")
new_memo = st.text_area("특이사항 입력", key="main_memo")

if st.button("💾 구글 시트에 업데이트", use_container_width=True):
    if worksheet:
        all_v = worksheet.get_all_values()
        t_key = f"{today} ({shift})"
        # 65행 양식에 맞춘 데이터 구성 (공백 포함)
        def cv(v): return ", ".join(v) if isinstance(v, list) else v
        payload = [
            "", t_key, pelapor, "", "", 
            get_prog_bar(st.session_state.qc_store["a4"], g_a4) if sw_a4 else "-", m_a4, "", 
            get_prog_bar(st.session_state.qc_store["a5"], g_a5) if sw_a5 else "-", m_a5, "", 
            get_prog_bar(st.session_state.qc_store["b3"], g_b3) if sw_b3 else "-", m_b3, "", 
            get_prog_bar(st.session_state.qc_store["b4"], g_b4) if sw_b4 else "-", m_b4, "", 
            get_prog_bar(st.session_state.qc_store["b5"], g_b5) if sw_b5 else "-", m_b5, "", 
            get_prog_bar(st.session_state.qc_store["b9"], g_b9) if sw_b9 else "-", m_b9, "", 
            "", get_prog_bar(st.session_state.qc_store["a8"], g_a8) if sw_a8 else "-", m_a8, "", 
            get_prog_bar(st.session_state.qc_store["b2"], g_b2) if sw_b2 else "-", m_b2, "", 
            get_prog_bar(st.session_state.qc_store["b6"], g_b6) if sw_b6 else "-", m_b6, "", 
            get_prog_bar(st.session_state.qc_store["b7"], g_b7) if sw_b7 else "-", m_b7, "", 
            get_prog_bar(st.session_state.qc_store["b8"], g_b8) if sw_b8 else "-", m_b8, "", 
            get_prog_bar(st.session_state.qc_store["b10"], g_b10) if sw_b10 else "-", m_b10, "", 
            "", cv(p_a1) if sw_a1 else "-", m_a1, "", cv(p_a2) if sw_a2 else "-", m_a2, "", 
            cv(p_a3) if sw_a3 else "-", m_a3, "", cv(p_a6) if sw_a6 else "-", m_a6, "", 
            cv(p_a7) if sw_a7 else "-", m_a7, "", cv(p_a9) if sw_a9 else "-", m_a9, "", 
            cv(p_b1) if sw_b1 else "-", m_b1, "", new_memo, current_time_full
        ]
        # 열 찾기 (중략)
        head = all_v[1] if len(all_v) > 1 else []
        idx = -1
        for i, v in enumerate(head):
            if v == t_key: idx = i + 1; break
        if idx == -1: idx = len(head) + 1 if len(head) >= 3 else 3
        
        def get_c(n):
            r = ""
            while n > 0: n, rem = divmod(n - 1, 26); r = chr(65 + rem) + r
            return r
        worksheet.update(f"{get_c(idx)}1", [[v] for v in payload])
        st.success(f"✅ 저장 성공! (시간: {current_time_full})")
    else: st.error("시트 연결 실패")
