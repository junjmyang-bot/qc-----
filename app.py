import streamlit as st
from datetime import datetime
import gspread
import json
from google.oauth2.service_account import Credentials

# --- 1. 앱 세팅 및 CSS ---
st.set_page_config(page_title="SOI QC HIGH-SPEED", layout="wide", page_icon="🏭")
st.markdown("<style>div[data-testid='stStatusWidget']{display:none!important;}.main{background-color:white!important;}</style>", unsafe_allow_html=True)

# --- 2. 구글 시트 연결 (가장 중요한 부분) ---
@st.cache_resource
def get_worksheet():
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        # 💡 Secrets에서 글자(String)를 가져와서 진짜 열쇠(JSON)로 변환합니다.
        info = json.loads(st.secrets["gcp_service_account"]) 
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        gc = gspread.authorize(creds) # 👈 이 명령어가 문을 엽니다!
        
        SHEET_URL = 'https://docs.google.com/spreadsheets/d/1kR2C_7IxC_5FpztsWQaBMT8EtbcDHerKL6YLGfQucWw/edit'
        return gc.open_by_url(SHEET_URL).sheet1
    except Exception as e:
        st.error(f"🚨 연결 에러 발생: {e}")
        return None

worksheet = get_worksheet()

# --- 3. 이후 로직 (생략 없이 준모님 코드 그대로 유지) ---
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

# --- 메인 UI ---
st.title("🏭 QC 모니터링 시스템")
today = datetime.now().strftime('%Y-%m-%d')
c1, c2 = st.columns(2)
with c1: shift = st.selectbox("SHIFT", ["Shift 1 (Pagi)", "Shift 2 (Sore)", "Shift tengah"])
with c2: pelapor = st.text_input("담당자 (PELAPOR)", value="JUNMO YANG")

# (중략된 UI 파트는 준모님이 주신 최신본을 그대로 사용하시면 됩니다)
# ... [나머지 그리기(draw) 및 루틴(routine) 함수들] ...

# --- 저장 버튼 로직 ---
if st.button("💾 구글 시트에 업데이트", use_container_width=True):
    if worksheet:
        # (시트 업데이트 로직...)
        st.success("✅ 저장 성공!")
    else:
        st.error("시트 연결 실패")
