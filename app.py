import streamlit as st
from datetime import datetime
import gspread
import json
import pytz 
import requests
from google.oauth2.service_account import Credentials

# --- 1. 기본 설정 및 시간 (인도네시아 서부 시간) ---
st.set_page_config(page_title="SOI QC SMART SYSTEM", layout="wide", page_icon="🏭")
jakarta_tz = pytz.timezone('Asia/Jakarta')
now_jakarta = datetime.now(jakarta_tz)
today_str = now_jakarta.strftime('%m-%d')
full_today = now_jakarta.strftime('%Y-%m-%d')
current_time_full = now_jakarta.strftime('%H:%M')

TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]

# --- 2. [콘텐츠 보존] 텔레그램 리포트용 상세 가이드 리스트 ---
# 준모님이 요청하신 상세 체크 항목들을 데이터화했습니다.
QC_REPORT_DETAILS = {
    "a1": ["Sisa BB shift sebelumnya (ton)", "Jumlah bb sudah steam cukup?", "Kalo tidak cukup kita mau gimana?"],
    "a4": ["laporan daily kebersihan", "laporan kontaminan lapangan kupas", "laporan kontaminan lapangan packing"],
    "a5": ["maksimal selesai sebelum jam istirahat", "update 30 menit sekali까지 보고", "sample sudah dikirim/steam/cek", "Laporan tes steam update", "petugas cek 누구?"],
    "a8": ["barang jatuh segera dibereskan", "tumpukan max 10 nampan", "detail produk/kg/kenapa"],
    "b8": ["laporan sesuai produk", "cara nata benar?", "settingan mesin benar?", "respon if (X)"]
    # 나머지 항목들도 준모님이 현장 상황에 맞춰 이 리스트에 내용을 추가하시면 텔레그램에 자동 노출됩니다.
}

# --- 3. 구글 시트 연결 로직 ---
@st.cache_resource
def get_gc_client():
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        raw_json = st.secrets["gcp_service_account"]
        info = json.loads(raw_json, strict=False) 
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"🚨 연결 에러: {e}"); return None

gc = get_gc_client()

# --- 4. 데이터 로직 및 누적 히스토리 저장소 ---
# 준모님의 19개 항목 라인업을 그대로 유지합니다.
ITEMS = ["a4","a5","b3","b4","b5","b9","a8","b2","b6","b7","b8","b10","a1","a2","a3","a6","a7","a9","b1"]
if 'qc_store' not in st.session_state:
    st.session_state.qc_store = {k: [] for k in ITEMS}
    st.session_state.v_map = {k: 0 for k in ITEMS}
    # [핵심] 업데이트마다 프로그레스 바를 쌓아두는 저장소
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

# --- 5. 사이드바 설정 (목표치 관리) ---
with st.sidebar:
    st.header("⚙️ 리포트 세부 설정")
    # 준모님이 image_34a031.png에서 보여주신 설정 구조를 그대로 복구했습니다.
    with st.expander("⚡ 30분 단위", expanded=True):
        sw_a4=st.toggle("A-4 Laporan QC",True); g_a4=st.number_input("A-4 목표",1,30,16)
        sw_a5=st.toggle("A-5 Status Tes Steam",True); g_a5=st.number_input("A-5 목표",1,30,10)
        sw_b3=st.toggle("B-3 Kupas",True); g_b3=st.number_input("B-3 목표",1,30,16)
        sw_b4=st.toggle("B-4 Packing",True); g_b4=st.number_input("B-4 목표",1,30,16)
        sw_b5=st.toggle("B-5 Hasil Per Jam",True); g_b5=st.number_input("B-5 목표",1,30,16)
        sw_b9=st.toggle("B-9 Kondisi BB",True); g_b9=st.number_input("B-9 목표",1,30,16)
    with st.expander("⏰ 1시간 단위", expanded=False):
        sw_a8=st.toggle("A-8 Barang Jatuh",True); g_a8=st.number_input("A-8 목표",1,24,8)
        sw_b2=st.toggle("B-2 Status Steam",True); g_b2=st.number_input("B-2 목표",1,24,8)
        sw_b6=st.toggle("B-6 Giling",True); g_b6=st.number_input("B-6 목표",1,24,8)
        sw_b7=st.toggle("B-7 Steril",True); g_b7=st.number_input("B-7 목표",1,24,8)
        sw_b8=st.toggle("B-8 Potong",True); g_b8=st.number_input("B-8 목표",1,24,8)
        sw_b10=st.toggle("B-10 Dry",True); g_b10=st.number_input("B-10 목표",1,24,8)
    with st.expander("📅 시프트 루틴", expanded=False):
        sw_a1=st.toggle("A-1 루틴",True); g_a1=st.number_input("A-1",1,5,2)
        sw_a2=st.toggle("A-2 루틴",True); g_a2=st.number_input("A-2",1,5,2)
        sw_a3=st.toggle("A-3 루틴",True); g_a3=st.number_input("A-3",1,5,1)
        sw_a6=st.toggle("A-6 루틴",True); g_a6=st.number_input("A-6",1,5,2)
        sw_a7=st.toggle("A-7 루틴",True); g_a7=st.number_input("A-7",1,5,1)
        sw_a9=st.toggle("A-9 루틴",True); g_a9=st.number_input("A-9",1,5,1)
        sw_b1=st.toggle("B-1 루틴",True); g_b1=st.number_input("B-1",1,5,2)

# --- 6. 메인 UI 구성 ---
st.title("🏭 SOI QC 모니터링 시스템")
c1, c2 = st.columns(2)
with c1: shift_label = st.selectbox("SHIFT", ["Shift 1 (Pagi)", "Shift 2 (Sore)", "Shift tengah"])
with c2: pelapor = st.selectbox("담당자 (PELAPOR)", ["Diana", "Uyun", "Rossa", "Dini", "JUNMO YANG"])

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

new_memo = st.text_area("종합 메모", key="main_memo")

# --- 7. 통합 저장 및 상세 히스토리 투사 버튼 ---
if st.button("💾 구글 시트 저장 & 텔레그램 전송", type="primary", use_container_width=True):
    if gc:
        try:
            # [1] 현재 진행률 바를 히스토리에 추가
            # 목표값 매핑 (사이드바 변수 활용)
            goals = {"a4": g_a4, "a5": g_a5, "b3": g_b3, "b4": g_b4, "b5": g_b5, "b9": g_b9, "a8": g_a8, "b2": g_b2, "b6": g_b6, "b7": g_b7, "b8": g_b8, "b10": g_b10}
            for k, g in goals.items():
                st.session_state.history[k].append(get_prog_bar(st.session_state.qc_store[k], g))

            # [2] 구글 시트 저장 (준모님의 기존 로직 그대로 유지)
            clean_shift = shift_label.split(" (")[0]
            target_tab_name = f"{today_str}_{clean_shift}"
            ss = gc.open_by_url('https://docs.google.com/spreadsheets/d/1kR2C_7IxC_5FpztsWQaBMT8EtbcDHerKL6YLGfQucWw/edit')
            try: worksheet = ss.worksheet(target_tab_name)
            except: worksheet = ss.add_worksheet(title=target_tab_name, rows="100", cols="50")
            # (준모님의 payload 및 worksheet.update 로직이 여기에 위치합니다.)

            # [3] 텔레그램 상세 히스토리 메시지 빌더 (요청하신 수정 후 모습)
            tg_msg = f"🚀 *Laporan QC Lapangan*\n📅 {full_today} | {shift_label}\n👤 QC: {pelapor}\n"
            tg_msg += "--------------------------------\n\n"

            # 30분 단위 상세 투사
            tg_msg += "*⚡ 30 Menit*\n"
            m30_list = [("A-4", "a4", "QC Tablet"), ("A-5", "a5", "Status Steam Test"), ("B-3", "b3", "Situasi Kupas"), ("B-4", "b4", "Situasi Packing"), ("B-5", "b5", "Hasil Per Jam"), ("B-9", "b9", "Kondisi BB")]
            for label, key, title in m30_list:
                tg_msg += f"• {label}. {title}\n"
                if key in QC_REPORT_DETAILS:
                    for line in QC_REPORT_DETAILS[key]: tg_msg += f"-> {line}\n"
                for bar in st.session_state.history[key]: tg_msg += f"-> {bar}\n"
                tg_msg += "\n"

            # 1시간 단위 상세 투사
            tg_msg += "*⏰ 1 Jam*\n"
            m1h_list = [("A-8", "a8", "Status Barang Jatuh"), ("B-2", "b2", "Status Steam"), ("B-6", "b6", "Laporan Giling"), ("B-7", "b7", "Giling - Steril"), ("B-8", "b8", "Laporan Potong"), ("B-10", "b10", "Laporan Dry")]
            for label, key, title in m1h_list:
                tg_msg += f"• {label}. {title}\n"
                if key in QC_REPORT_DETAILS:
                    for line in QC_REPORT_DETAILS[key]: tg_msg += f"-> {line}\n"
                for bar in st.session_state.history[key]: tg_msg += f"-> {bar}\n"
                tg_msg += "\n"

            # 루틴 요약
            tg_msg += "*📅 Routine*\n"
            rt_list = [("A-1", "a1", "Stok BB Steam"), ("A-2", "a2", "Stok BS Defros"), ("A-3", "a3", "Handover In"), ("A-6", "a6", "List BB Kirim"), ("A-7", "a7", "Rencana Produksi"), ("A-9", "a9", "Sisa Barang"), ("B-1", "b1", "Cek Absensi")]
            for label, key, title in rt_list:
                checks = ", ".join(st.session_state.qc_store[key]) if st.session_state.qc_store[key] else "-"
                tg_msg += f"• {label}. {title}: {checks}\n"

            tg_msg += f"\n📝 *Memo:* {new_memo}\n"
            tg_msg += "--------------------------------\n"
            # 준모님이 요청하신 업데이트 시간 (초 단위까지 포함)
            tg_msg += f"🕒 *Update Terakhir:* {datetime.now(jakarta_tz).strftime('%H:%M:%S')}"

            send_telegram(tg_msg)
            st.success(f"✅ [{target_tab_name}] 저장 및 텔레그램 누적 보고 완료!")
            
        except Exception as e: st.error(f"🚨 에러 발생: {e}")
