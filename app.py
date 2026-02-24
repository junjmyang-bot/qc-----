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

# --- 2. [데이터 보존] 19개 전 항목 상세 가이드 데이터 ---
QC_CONTENT = {
    "A": {
        "a1": {"title": "Cek Stok BB Sudah steam", "qs": ["Sisa BB sisa shift sebelumya?", "Jumlah bb steam 충분?", "Respon if kurang?"]},
        "a2": {"title": "Cek Stok BS (Sudah di defros)", "qs": ["Sudah defros 얼마?", "Estimasi 작업량?", "Jam tambah defros?"]},
        "a5": {"title": "Status tes steam", "desc": ["maksimal jam 13.00 완료", "update 30분 마다 보고", "sample 확인", "Laporan update 확인"]},
        "a6": {"title": "List BB butuh kirim", "qs": ["List kirim jam 12.00?", "Kordinasi gudang?"]},
        "a3": {"title": "Handover shift 전", "qs": ["Sudah dapat handover?", "Produksi sesuai rencana?"]},
        "a7": {"title": "Handover & rencana", "qs": ["Rencana sudah dibuat?", "Handover sudah dibuat?", "Sudah baca data stok?"]},
        "a9": {"title": "SISA BARANG", "qs": ["Check MAX 1 PACK", "Sisa shift prev?", "Sudah dibereskan?", "Simpan sisa?", "Handover sisa?"]},
        "a4": {"title": "Laporan QC di tablet", "check_items": ["daily kebersihan", "kontaminan kupas", "kontaminan packing"]},
        "a8": {"title": "Barang Jatuh", "desc": ["check 1시간 마다", "max 10 nampan"]}
    },
    "B": {
        "b1": {"title": "Cek Absensi", "desc": ["Awal masuk & Istirahat pax"]},
        "b2": {"title": "Status Steam", "desc": ["1시간 마다 체크", "Laporan 확인"]},
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

def send_telegram(text):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})

# --- 4. 사이드바 설정 (이름 복구 및 A/B 분리) ---
with st.sidebar:
    st.header("⚙️ 리포트 세부 설정")
    with st.expander("📅 시프트 루틴 설정 (최상단)", expanded=True):
        st.info("📦 Bahan Baku")
        sw_a1=st.toggle(f"A-1 {QC_CONTENT['A']['a1']['title']}", True)
        sw_a2=st.toggle(f"A-2 {QC_CONTENT['A']['a2']['title']}", True)
        sw_a5=st.toggle(f"A-5 {QC_CONTENT['A']['a5']['title']}", True)
        sw_a6=st.toggle(f"A-6 {QC_CONTENT['A']['a6']['title']}", True)
        st.divider(); st.caption("🅰️ Routine Others")
        sw_a3=st.toggle(f"A-3 {QC_CONTENT['A']['a3']['title']}", True)
        sw_a7=st.toggle(f"A-7 {QC_CONTENT['A']['a7']['title']}", True)
        sw_a9=st.toggle(f"A-9 {QC_CONTENT['A']['a9']['title']}", True)
        st.divider(); st.caption("🅱️ Check TL")
        sw_b1=st.toggle(f"B-1 {QC_CONTENT['B']['b1']['title']}", True)
    
    with st.expander("⚡ 30분 단위 설정", expanded=False):
        st.caption("🅰️ QC Direct"); sw_a4=st.toggle(f"A-4 {QC_CONTENT['A']['a4']['title']}", True)
        st.divider(); st.caption("🅱️ Check TL")
        sw_b3=st.toggle(f"B-3 {QC_CONTENT['B']['b3']['title']}", True); sw_b4=st.toggle(f"B-4 {QC_CONTENT['B']['b4']['title']}", True)
        sw_b5=st.toggle(f"B-5 {QC_CONTENT['B']['b5']['title']}", True); sw_b9=st.toggle(f"B-9 {QC_CONTENT['B']['b9']['title']}", True)

    with st.expander("⏰ 1시간 단위 설정", expanded=False):
        st.caption("🅰️ QC Direct"); sw_a8=st.toggle(f"A-8 {QC_CONTENT['A']['a8']['title']}", True)
        st.divider(); st.caption("🅱️ Check TL")
        sw_b2=st.toggle(f"B-2 {QC_CONTENT['B']['b2']['title']}", True); sw_b6=st.toggle(f"B-6 {QC_CONTENT['B']['b6']['title']}", True)
        sw_b7=st.toggle(f"B-7 {QC_CONTENT['B']['b7']['title']}", True); sw_b8=st.toggle(f"B-8 {QC_CONTENT['B']['b8']['title']}", True); sw_b10=st.toggle(f"B-10 {QC_CONTENT['B']['b10']['title']}", True)

# --- 5. 메인 UI (그리드 레이아웃) ---
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
        st.markdown("##### 📦 Bahan Baku (Shift 1 Only)")
        if sw_a1:
            st.markdown(f"**A1. {
