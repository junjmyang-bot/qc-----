import streamlit as st
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 초고속 설정을 위한 캐싱 및 앱 세팅 ---
st.set_page_config(page_title="SOI QC HIGH-SPEED", layout="wide", page_icon="🏭")

# 🌟 하얀 화면(로딩 마스크)을 물리적으로 제거하는 최적화 CSS
st.markdown("""
    <style>
    div[data-testid="stAppViewBlockContainer"], 
    div[data-testid="stSidebarUserContent"], 
    section[data-testid="stSidebar"],
    .stApp.Element-Loading { opacity: 1 !important; transition: none !important; }
    div[data-testid="stStatusWidget"], .stDeployButton { display: none !important; }
    .main { background-color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# 🌟 [초고속 비결] 구글 시트 연결을 메모리에 고정합니다.
@st.cache_resource
def get_worksheet():
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file('credentials.json', scopes=scopes)
        gc = gspread.authorize(creds)
        # 준모님 전용 시트 URL
        SHEET_URL = 'https://docs.google.com/spreadsheets/d/1kR2C_7IxC_5FpztsWQaBMT8EtbcDHerKL6YLGfQucWw/edit'
        return gc.open_by_url(SHEET_URL).sheet1
    except: return None

worksheet = get_worksheet()

# --- 2. 데이터 저장소 및 원터치 로직 ---
ITEMS = ["a4","a5","b3","b4","b5","b9","a8","b2","b6","b7","b8","b10","a1","a2","a3","a6","a7","a9","b1"]

if 'qc_store' not in st.session_state:
    st.session_state.qc_store = {k: [] for k in ITEMS}
    st.session_state.v_map = {k: 0 for k in ITEMS} # 개별 버전 번호

def fast_cascade(key):
    v_idx = st.session_state.v_map[key]
    raw = st.session_state[f"u_{key}_{v_idx}"]
    if not raw: st.session_state.qc_store[key] = []
    else:
        nums = [int(x) for x in raw if x.isdigit()]
        if nums: st.session_state.qc_store[key] = [str(i) for i in range(1, max(nums) + 1)]
    st.session_state.v_map[key] += 1 # 해당 항목만 즉시 갱신

def get_prog_bar(val, goal):
    perc = int((len(val)/goal)*100) if goal > 0 else 0
    if perc > 100: perc = 100
    return f"{'■' * (perc // 10)}{'□' * (10 - (perc // 10))} ({perc}%)"

# --- 3. 사이드바: 19개 항목 ON/OFF 및 목표 설정 복구 ---
with st.sidebar:
    st.header("⚙️ 리포트 세부 설정")
    
    with st.expander("⚡ 30분 단위 설정", expanded=True):
        sw_a4=st.toggle("A-4 Laporan QC",True); g_a4=st.number_input("A-4 목표",1,30,16,key="ga4")
        sw_a5=st.toggle("A-5 Status Tes Steam",True); g_a5=st.number_input("A-5 목표",1,30,10,key="ga5")
        sw_b3=st.toggle("B-3 Kupas 상황보고",True); g_b3=st.number_input("B-3 목표",1,30,16,key="gb3")
        sw_b4=st.toggle("B-4 Packing 상황보고",True); g_b4=st.number_input("B-4 목표",1,30,16,key="gb4")
        sw_b5=st.toggle("B-5 시간당 결과",True); g_b5=st.number_input("B-5 목표",1,30,16,key="gb5")
        sw_b9=st.toggle("B-9 원료 조건 보고",True); g_b9=st.number_input("B-9 목표",1,30,16,key="gb9")

    with st.expander("⏰ 1시간 단위 설정", expanded=False):
        sw_a8=st.toggle("A-8 낙하물 상태",True); g_a8=st.number_input("A-8 목표",1,24,8,key="ga8")
        sw_b2=st.toggle("B-2 스팀 상태",True); g_b2=st.number_input("B-2 목표",1,24,8,key="gb2")
        sw_b6=st.toggle("B-6 분쇄 보고",True); g_b6=st.number_input("B-6 목표",1,24,8,key="gb6")
        sw_b7=st.toggle("B-7 분쇄 보고(살균)",True); g_b7=st.number_input("B-7 목표",1,24,8,key="gb7")
        sw_b8=st.toggle("B-8 절단 보고",True); g_b8=st.number_input("B-8 목표",1,24,8,key="gb8")
        sw_b10=st.toggle("B-10 건조 보고",True); g_b10=st.number_input("B-10 목표",1,24,8,key="gb10")

    with st.expander("📅 시프트 루틴 설정", expanded=False):
        sw_a1=st.toggle("A-1 루틴",True); g_a1=st.number_input("A-1 체크수",1,5,2,key="ga1")
        sw_a2=st.toggle("A-2 루틴",True); g_a2=st.number_input("A-2 체크수",1,5,2,key="ga2")
        sw_a3=st.toggle("A-3 루틴",True); g_a3=st.number_input("A-3 체크수",1,5,1,key="ga3")
        sw_a6=st.toggle("A-6 루틴",True); g_a6=st.number_input("A-6 체크수",1,5,2,key="ga6")
        sw_a7=st.toggle("A-7 루틴",True); g_a7=st.number_input("A-7 체크수",1,5,1,key="ga7")
        sw_a9=st.toggle("A-9 루틴",True); g_a9=st.number_input("A-9 체크수",1,5,1,key="ga9")
        sw_b1=st.toggle("B-1 루틴",True); g_b1=st.number_input("B-1 체크수",1,5,2,key="gb1")

# --- 4. 메인 UI 디자인 ---
st.title("🏭 QC 모니터링 시스템")
today = datetime.now().strftime('%Y-%m-%d')

c1, c2 = st.columns(2)
with c1: shift = st.selectbox("SHIFT", ["Shift 1 (Pagi)", "Shift 2 (Sore)", "Shift tengah"])
with c2: pelapor = st.text_input("담당자 (PELAPOR)", value="JUNMO YANG")

def draw(label, key, goal, show):
    if show:
        st.markdown(f"**{label}**")
        v = st.session_state.v_map[key]
        st.pills(label, [str(i) for i in range(1, goal+1)], key=f"u_{key}_{v}", on_change=fast_cascade, args=(key,), selection_mode="multi", label_visibility="collapsed", default=st.session_state.qc_store[key])
        return st.text_input(f"{label} 코멘트", key=f"m_{key}")
    return ""

st.subheader("⚡ 30분 단위")
with st.container(border=True):
    m_a4=draw("A-4 Laporan QC di Tablet","a4",g_a4,sw_a4); m_a5=draw("A-5 Status Tes Steam","a5",g_a5,sw_a5)
    m_b3=draw("B-3 Laporan Situasi Kupas","b3",g_b3,sw_b3); m_b4=draw("B-4 Laporan Situasi Packing","b4",g_b4,sw_b4)
    m_b5=draw("B-5 Hasil Per Jam","b5",g_b5,sw_b5); m_b9=draw("B-9 Laporan Kondisi BB","b9",g_b9,sw_b9)

st.subheader("⏰ 1시간 단위")
with st.container(border=True):
    m_a8=draw("A-8 Status Barang Jatuh","a8",g_a8,sw_a8); m_b2=draw("B-2 Laporan Status Steam","b2",g_b2,sw_b2)
    m_b6=draw("B-6 Laporan Giling","b6",g_b6,sw_b6); m_b7=draw("B-7 Laporan Giling (Steril)","b7",g_b7,sw_b7)
    m_b8=draw("B-8 Laporan Potong","b8",g_b8,sw_b8); m_b10=draw("B-10 Laporan Dry","b10",g_b10,sw_b10)

st.subheader("📅 시프트 루틴")
with st.container(border=True):
    def routine(label, g, show, key):
        if show:
            st.markdown(f"**{label}**")
            opts = ["Awal", "Istirahat", "Jam 12", "Handover", "Closing"][:g]
            p = st.pills(label, opts, selection_mode="multi", key=f"u_{key}", label_visibility="collapsed")
            m = st.text_input(f"{label} 메모", key=f"m_{key}")
            return p, m
        return [], ""
    p_a1,m_a1=routine("A-1 Cek Stok BB Steam",g_a1,sw_a1,"a1"); p_a2,m_a2=routine("A-2 Cek Stok BS",g_a2,sw_a2,"a2")
    p_a3,m_a3=routine("A-3 Handover IN",g_a3,sw_a3,"a3"); p_a6,m_a6=routine("A-6 List BB Butuh Kirim",g_a6,sw_a6,"a6")
    p_a7,m_a7=routine("A-7 Handover & Rencana",g_a7,sw_a7,"a7"); p_a9,m_a9=routine("A-9 Sisa Barang",g_a9,sw_a9,"a9")
    p_b1,m_b1=routine("B-1 Cek Laporan Absensi",g_b1,sw_b1,"b1")

st.subheader("📝 종합 메모")
new_memo = st.text_area("특이사항 입력", key="main_memo")
if st.button("💾 구글 시트에 업데이트", use_container_width=True):
    if worksheet:
        all_v = worksheet.get_all_values()
        t_key = f"{today} ({shift})"; head = all_v[1] if len(all_v) > 1 else []
        idx = -1; old_m = ""
        for i, v in enumerate(head):
            if v == t_key: 
                idx = i + 1
                if len(all_v) > 63: old_m = all_v[63][i]
                break
        final_m = old_m + f"\n[{datetime.now().strftime('%H:%M')}] {new_memo}" if new_memo else old_m
        def cv(v): return ", ".join(v) if isinstance(v, list) else v
        # 65행 양식 기둥 데이터 구성
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
            cv(p_b1) if sw_b1 else "-", m_b1, "", final_m, datetime.now().strftime('%H:%M:%S')
        ]
        if idx == -1: idx = len(head) + 1 if len(head) >= 3 else 3
        def get_c(n):
            r = ""
            while n > 0: n, rem = divmod(n - 1, 26); r = chr(65 + rem) + r
            return r
        worksheet.update(f"{get_c(idx)}1", [[v] for v in payload])
        st.success("✅ 저장 성공!")
    else: st.error("시트 연결 실패")
streamlit
gspread
google-auth
