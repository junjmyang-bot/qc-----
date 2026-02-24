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

# --- 2. [콘텐츠 보존] 전 항목 상세 타이틀 및 가이드 ---
# A와 B의 역할을 명확히 구분하여 데이터화했습니다.
QC_CONTENT = {
    "A": { # QC Direct Check
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
    "B": { # Check TL Reports
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

# --- [3. 데이터 로직 및 세션 상태] ---
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

# --- [4. UI 구성] ---
st.title("🏭 SOI QC 모니터링 (A/B 분리형)")
c1, c2 = st.columns(2)
with c1: shift_label = st.selectbox("SHIFT", ["Shift 1 (Pagi)", "Shift 2 (Sore)", "Shift tengah"])
with c2: pelapor = st.selectbox("담당자", ["Diana", "Uyun", "Rossa", "Dini", "JUNMO YANG"])

def draw_item(key, info, goal):
    st.markdown(f"**{key.upper()}. {info['title']}**")
    v = st.session_state.v_map[key]
    st.pills(info['title'], [str(i) for i in range(1, goal+1)], key=f"u_{key}_{v}", on_change=fast_cascade, args=(key,), selection_mode="multi", label_visibility="collapsed", default=st.session_state.qc_store[key])
    return st.text_input(f"{info['title']} 코멘트", key=f"m_{key}")

# 섹션별 렌더링 (A/B 분리)
sections = [
    ("⚡ 30분 단위", [("a4", 16), ("a5", 10)], [("b3", 16), ("b4", 16), ("b5", 16), ("b9", 16)]),
    ("⏰ 1시간 단위", [("a8", 8)], [("b2", 8), ("b6", 8), ("b7", 8), ("b8", 8), ("b10", 8)]),
]

for sec_title, a_keys, b_keys in sections:
    st.subheader(sec_title)
    col_a, col_b = st.columns(2)
    with col_a:
        st.info("🅰️ QC Direct Check")
        for k, g in a_keys: draw_item(k, QC_CONTENT["A"][k], g)
    with col_b:
        st.warning("🅱️ Check TL Reports")
        for k, g in b_keys: draw_item(k, QC_CONTENT["B"][k], g)

st.subheader("📅 시프트 루틴")
cola, colb = st.columns(2)
with cola:
    st.info("🅰️ QC Direct Check")
    for k in ["a1", "a2", "a3", "a6", "a7", "a9"]:
        st.markdown(f"**{k.upper()}. {QC_CONTENT['A'][k]['title']}**")
        st.pills(k, ["Awal", "Istirahat", "Jam 12", "Handover", "Closing"][:2], selection_mode="multi", key=f"u_{k}")
with colb:
    st.warning("🅱️ Check TL Reports")
    st.markdown(f"**B1. {QC_CONTENT['B']['b1']['title']}**")
    st.pills("b1", ["Awal", "Istirahat"], selection_mode="multi", key="u_b1")

# --- [5. 저장 및 텔레그램 빌더] ---
if st.button("💾 구글 시트 저장 & 텔레그램 전송", type="primary", use_container_width=True):
    try:
        # 히스토리 기록
        for k in ITEMS:
            st.session_state.history[k].append(get_prog_bar(st.session_state.qc_store[k], 16))

        # 텔레그램 메시지 조립
        tg_msg = f"🚀 *Laporan QC Lapangan*\n📅 {full_today} | {shift_label}\n👤 QC: {pelapor}\n"
        tg_msg += "--------------------------------\n\n"

        for type_key, type_name in [("A", "🅰️ QC Direct Check"), ("B", "🅱️ Check TL Reports")]:
            tg_msg += f"*{type_name}*\n"
            for k, info in QC_CONTENT[type_key].items():
                tg_msg += f"• {k.upper()}. {info['title']}\n"
                for line in info['desc']: tg_msg += f"  -> {line}\n"
                for bar in st.session_state.history[k]: tg_msg += f"  -> {bar}\n"
                tg_msg += "\n"
        
        tg_msg += f"🕒 *Update:* {datetime.now(jakarta_tz).strftime('%H:%M:%S')}"
        send_telegram(tg_msg)
        st.success("✅ A/B 분리 리포트 전송 완료!")
    except Exception as e: st.error(f"🚨 에러: {e}")
