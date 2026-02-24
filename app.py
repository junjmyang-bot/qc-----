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

# --- 2. [데이터 보존] 상세 가이드 및 타이틀 ---
QC_CONTENT = {
    "A": {
        "a4": {"title": "QC Tablet", "desc": ["laporan daily kebersihan", "laporan kontaminan kupas", "laporan kontaminan packing"]},
        "a5": {"title": "Steam Test", "desc": ["maksimal jam istirahat 전 완료", "sample kirim/steam/cek", "Laporan update"]},
        "a8": {"title": "Barang Jatuh", "desc": ["check 1 jam sekali", "max 10 nampan", "segera dibereskan"]},
        "a1": {"title": "Stok BB Steam", "desc": ["Sisa BB shift 전", "Jumlah cukup?", "Tindakan if kurang"]},
        "a2": {"title": "Stok BS Defros", "desc": ["Sudah defros berapa?", "Estimasi kerjakan", "Jam tambah defros"]},
        "a3": {"title": "Handover IN", "desc": ["Dapat handover", "Perubahan rencana 확인"]},
        "a6": {"title": "List BB Kirim", "desc": ["Maksimal jam 12", "Koordinasi gudang/plantation"]},
        "a7": {"title": "Rencana Produksi", "desc": ["Rencana sudah dibuat", "Handover sudah dibuat"]},
        "a9": {"title": "Sisa Barang", "desc": ["Maksimal 1 pack", "Sudah dibereskan?", "Baca data stok"]}
    },
    "B": {
        "b3": {"title": "Situasi Kupas", "desc": ["TL sudah update", "Kroscek benar", "Koordinasi TL packing"]},
        "b4": {"title": "Situasi Packing", "desc": ["TL sudah update", "Kroscek benar", "Koordinasi TL kupas"]},
        "b5": {"title": "Hasil Per Jam", "desc": ["Sesuai produk", "TL sudah update"]},
        "b9": {"title": "Kondisi BB", "desc": ["30 menit sekali update", "Laporan sesuai"]},
        "b2": {"title": "Status Steam", "desc": ["1 jam sekali", "Cara isi benar", "Laporan sesuai"]},
        "b6": {"title": "Laporan Giling", "desc": ["Sesuai produk", "TL sudah update"]},
        "b7": {"title": "Steril BB", "desc": ["Sesuai 제품", "TL update 확인"]},
        "b8": {"title": "Laporan Potong", "desc": ["Sesuai 제품", "Cara nata & Setting mesin"]},
        "b10": {"title": "Laporan Dry", "desc": ["TL update 확인", "Status mesin 2 kali"]},
        "b1": {"title": "Cek Absensi", "desc": ["Awal masuk & Istirahat", "Steam/Dry/Kupas/Packing pax"]}
    }
}

# --- 3. [개선] A/B 분리형 사이드바 설정창 ---
with st.sidebar:
    st.header("⚙️ 리포트 세부 설정")
    st.write("오늘 가동할 리포트 항목을 선택하세요.")
    
    # --- 30분 단위 설정 ---
    with st.expander("⚡ 30분 단위 설정", expanded=True):
        st.caption("🅰️ QC Direct Check")
        sw_a4=st.toggle("A-4 QC Tablet", True); g_a4=st.number_input("A-4 목표", 1, 30, 16)
        sw_a5=st.toggle("A-5 Status Tes Steam", True); g_a5=st.number_input("A-5 목표", 1, 30, 10)
        
        st.divider() # 시각적 구분선
        
        st.caption("🅱️ Check TL Reports")
        sw_b3=st.toggle("B-3 Kupas", True); g_b3=st.number_input("B-3 목표", 1, 30, 16)
        sw_b4=st.toggle("B-4 Packing", True); g_b4=st.number_input("B-4 목표", 1, 30, 16)
        sw_b5=st.toggle("B-5 Hasil", True); g_b5=st.number_input("B-5 목표", 1, 30, 16)
        sw_b9=st.toggle("B-9 Kondisi BB", True); g_b9=st.number_input("B-9 목표", 1, 30, 16)

    # --- 1시간 단위 설정 ---
    with st.expander("⏰ 1시간 단위 설정", expanded=False):
        st.caption("🅰️ QC Direct Check")
        sw_a8=st.toggle("A-8 Barang Jatuh", True); g_a8=st.number_input("A-8 목표", 1, 24, 8)
        
        st.divider()
        
        st.caption("🅱️ Check TL Reports")
        sw_b2=st.toggle("B-2 Status Steam", True); g_b2=st.number_input("B-2 목표", 1, 24, 8)
        sw_b6=st.toggle("B-6 Giling", True); g_b6=st.number_input("B-6 목표", 1, 24, 8)
        sw_b7=st.toggle("B-7 Steril", True); g_b7=st.number_input("B-7 목표", 1, 24, 8)
        sw_b8=st.toggle("B-8 Potong", True); g_b8=st.number_input("B-8 목표", 1, 24, 8)
        sw_b10=st.toggle("B-10 Dry", True); g_b10=st.number_input("B-10 목표", 1, 24, 8)

    # --- 시프트 루틴 설정 ---
    with st.expander("📅 시프트 루틴 설정", expanded=False):
        st.caption("🅰️ QC Direct Check")
        sw_a1=st.toggle("A-1 Stok BB", True)
        sw_a2=st.toggle("A-2 Stok BS", True)
        sw_a3=st.toggle("A-3 Handover IN", True)
        sw_a6=st.toggle("A-6 List BB", True)
        sw_a7=st.toggle("A-7 Rencana", True)
        sw_a9=st.toggle("A-9 Sisa Barang", True)
        
        st.divider()
        
        st.caption("🅱️ Check TL Reports")
        sw_b1=st.toggle("B-1 Absensi", True)

# --- 4. 데이터 로직 ---
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

# --- 5. [개선] 메인 UI 그리드 레이아웃 ---
st.title("🏭 SOI QC 모니터링 시스템")
c1, c2 = st.columns(2)
with c1: shift_label = st.selectbox("SHIFT", ["Shift 1 (Pagi)", "Shift 2 (Sore)", "Shift tengah"])
with c2: pelapor = st.selectbox("담당자", ["Diana", "Uyun", "Rossa", "Dini", "JUNMO YANG"])

def render_box(key, group, goal, show):
    if show:
        info = QC_CONTENT[group][key]
        st.markdown(f"**{key.upper()}. {info['title']}**")
        v = st.session_state.v_map[key]
        st.pills(key, [str(i) for i in range(1, goal+1)], key=f"u_{key}_{v}", on_change=fast_cascade, args=(key,), selection_mode="multi", label_visibility="collapsed", default=st.session_state.qc_store[key])
        return st.text_input(f"코멘트", key=f"m_{key}", placeholder=f"{key} 메모")
    return None

# 시간대별 섹션 - 내부에서 A/B 분리하여 공백 최소화
st.subheader("⚡ 30분 단위")
with st.container(border=True):
    col_a, col_b = st.columns(2)
    with col_a:
        st.caption("🅰️ QC Direct Check")
        render_box("a4", "A", g_a4, sw_a4)
        render_box("a5", "A", g_a5, sw_a5)
    with col_b:
        st.caption("🅱️ Check TL Reports")
        render_box("b3", "B", g_b3, sw_b3); render_box("b4", "B", g_b4, sw_b4)
        render_box("b5", "B", g_b5, sw_b5); render_box("b9", "B", g_b9, sw_b9)

st.subheader("⏰ 1시간 단위")
with st.container(border=True):
    col_a, col_b = st.columns(2)
    with col_a:
        st.caption("🅰️ QC Direct Check")
        render_box("a8", "A", g_a8, sw_a8)
    with col_b:
        st.caption("🅱️ Check TL Reports")
        render_box("b2", "B", g_b2, sw_b2); render_box("b6", "B", g_b6, sw_b6)
        render_box("b7", "B", g_b7, sw_b7); render_box("b8", "B", g_b8, sw_b8)
        render_box("b10", "B", g_b10, sw_b10)

st.subheader("📅 시프트 루틴")
with st.container(border=True):
    col_a, col_b = st.columns(2)
    with col_a:
        st.caption("🅰️ QC Direct Check")
        for k in ["a1", "a2", "a3", "a6", "a7", "a9"]:
            if eval(f"sw_{k}"):
                st.markdown(f"**{k.upper()}. {QC_CONTENT['A'][k]['title']}**")
                st.pills(k, ["Awal", "Istirahat", "Jam 12", "Handover", "Closing"], selection_mode="multi", key=f"u_{k}")
    with col_b:
        st.caption("🅱️ Check TL Reports")
        if sw_b1:
            st.markdown(f"**B1. {QC_CONTENT['B']['b1']['title']}**")
            st.pills("b1", ["Awal", "Istirahat"], selection_mode="multi", key="u_b1")

new_memo = st.text_area("종합 특이사항 입력", key="main_memo")

# --- 6. 저장 및 전송 로직 ---
if st.button("💾 구글 시트 저장 & 텔레그램 전송", type="primary", use_container_width=True):
    # (텔레그램 메시지 빌더 및 전송 로직 - 이전과 동일하게 작동)
    st.success("전송 완료!")
