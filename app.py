import streamlit as st
from datetime import datetime
import gspread
import json
import pytz 
import requests
from google.oauth2.service_account import Credentials

# --- 1. 기본 설정 및 보안 키 ---
st.set_page_config(page_title="SOI QC SMART SYSTEM", layout="wide", page_icon="🏭")
jakarta_tz = pytz.timezone('Asia/Jakarta')
now_jakarta = datetime.now(jakarta_tz)
today_str = now_jakarta.strftime('%m-%d')
full_today = now_jakarta.strftime('%Y-%m-%d')
current_time_full = now_jakarta.strftime('%H:%M')

TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]

# --- 2. 항목별 상세 가이드라인 (UI 노출용) ---
GUIDE_MAP = {
    "a1": "✅ Sisa BB shift sebelumnya (ton)\n✅ Cukup untuk shift 지금/다음?",
    "a4": "✅ Update 30분 마다\n✅ Kebersihan & Kontaminan Kupas/Packing",
    "a8": "✅ 1시간 마다 체크\n✅ 바닥 물건 즉시 정리 (Max 10 nampan)",
    "b8": "✅ 제품 일치 확인\n✅ Cara nata & Machine Setting 확인",
    "b10": "✅ 1시간 마다\n✅ Status Mesin (Istirahat & Pulang 전)"
}

# --- 3. 구글 시트 연결 ---
@st.cache_resource
def get_gc_client():
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        raw_json = st.secrets["gcp_service_account"]
        info = json.loads(raw_json, strict=False) 
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"🚨 연결 에러: {e}")
        return None

gc = get_gc_client()

# --- 4. 데이터 로직 (High-Speed) ---
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

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, data=payload)

# --- 5. 사이드바 설정 ---
with st.sidebar:
    st.header("⚙️ 리포트 세부 설정")
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

# --- 6. 메인 UI ---
st.title("🏭 SOI QC 모니터링 시스템")
c1, c2 = st.columns(2)
with c1: 
    shift_label = st.selectbox("SHIFT", ["Shift 1 (Pagi)", "Shift 2 (Sore)", "Shift tengah"])
with c2: 
    pelapor = st.selectbox("PELAPOR", ["Diana", "Uyun", "Rossa", "Dini", "JUNMO YANG"])

def draw(label, key, goal, show):
    if show:
        st.markdown(f"**{label}**")
        if key in GUIDE_MAP: st.caption(f"💡 {GUIDE_MAP[key]}")
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
            if key in GUIDE_MAP: st.caption(f"💡 {GUIDE_MAP[key]}")
            p = st.pills(label, ["Awal", "Istirahat", "Jam 12", "Handover", "Closing"][:g], selection_mode="multi", key=f"u_{key}")
            return p, st.text_input(f"{label} 메모", key=f"m_{key}")
        return [], ""
    p_a1,m_a1=routine("A-1 Stok BB",g_a1,sw_a1,"a1"); p_a2,m_a2=routine("A-2 Stok BS",g_a2,sw_a2,"a2")
    p_a3,m_a3=routine("A-3 Handover IN",g_a3,sw_a3,"a3"); p_a6,m_a6=routine("A-6 List BB",g_a6,sw_a6,"a6")
    p_a7,m_a7=routine("A-7 Rencana",g_a7,sw_a7,"a7"); p_a9,m_a9=routine("A-9 Sisa Barang",g_a9,sw_a9,"a9")
    p_b1,m_b1=routine("B-1 Absensi",g_b1,sw_b1,"b1")

new_memo = st.text_area("종합 특이사항 입력", key="main_memo")

# --- 7. 통합 저장 및 전송 버튼 ---
if st.button("💾 구글 시트 저장 & 텔레그램 전송", type="primary", use_container_width=True):
    if gc:
        try:
            # [1] 구글 시트 업데이트 로직
            clean_shift = shift_label.split(" (")[0]
            target_tab_name = f"{today_str}_{clean_shift}"
            SHEET_URL = 'https://docs.google.com/spreadsheets/d/1kR2C_7IxC_5FpztsWQaBMT8EtbcDHerKL6YLGfQucWw/edit'
            ss = gc.open_by_url(SHEET_URL)
            try: worksheet = ss.worksheet(target_tab_name)
            except: worksheet = ss.add_worksheet(title=target_tab_name, rows="100", cols="50")
            
            header_title = f"{full_today} | {pelapor} | {current_time_full}"
            def cv(v): return ", ".join(v) if isinstance(v, list) else v
            labels = ["▶ 보고서 정보", "담당자", "", "", "▶ 30분 단위", "A-4 QC", "A-4 코멘트", "", "A-5 Steam", "A-5 코멘트", "", "B-3 Kupas", "B-3 코멘트", "", "B-4 Packing", "B-4 코멘트", "", "B-5 Hasil", "B-5 코멘트", "", "B-9 Kondisi", "B-9 코멘트", "", "▶ 1시간 단위", "A-8 Barang", "A-8 코멘트", "", "B-2 Steam", "B-2 코멘트", "", "B-6 Giling", "B-6 코멘트", "", "B-7 Steril", "B-7 코멘트", "", "B-8 Potong", "B-8 코멘트", "", "B-10 Dry", "B-10 코멘트", "", "▶ 시프트 루틴", "A-1 Stok", "A-1 메모", "", "A-2 BS", "A-2 메모", "", "A-3 Handover", "A-3 메모", "", "A-6 List", "A-6 메모", "", "A-7 Rencana", "A-7 메모", "", "A-9 Sisa", "A-9 메모", "", "B-1 Absen", "B-1 메모", "", "▶ 종합 메모", "기록 시각"]
            payload = [header_title, pelapor, "", "", "", get_prog_bar(st.session_state.qc_store["a4"], g_a4) if sw_a4 else "-", m_a4, "", get_prog_bar(st.session_state.qc_store["a5"], g_a5) if sw_a5 else "-", m_a5, "", get_prog_bar(st.session_state.qc_store["b3"], g_b3) if sw_b3 else "-", m_b3, "", get_prog_bar(st.session_state.qc_store["b4"], g_b4) if sw_b4 else "-", m_b4, "", get_prog_bar(st.session_state.qc_store["b5"], g_b5) if sw_b5 else "-", m_b5, "", get_prog_bar(st.session_state.qc_store["b9"], g_b9) if sw_b9 else "-", m_b9, "", "", get_prog_bar(st.session_state.qc_store["a8"], g_a8) if sw_a8 else "-", m_a8, "", get_prog_bar(st.session_state.qc_store["b2"], g_b2) if sw_b2 else "-", m_b2, "", get_prog_bar(st.session_state.qc_store["b6"], g_b6) if sw_b6 else "-", m_b6, "", get_prog_bar(st.session_state.qc_store["b7"], g_b7) if sw_b7 else "-", m_b7, "", get_prog_bar(st.session_state.qc_store["b8"], g_b8) if sw_b8 else "-", m_b8, "", get_prog_bar(st.session_state.qc_store["b10"], g_b10) if sw_b10 else "-", m_b10, "", "", cv(p_a1) if sw_a1 else "-", m_a1, "", cv(p_a2) if sw_a2 else "-", m_a2, "", cv(p_a3) if sw_a3 else "-", m_a3, "", cv(p_a6) if sw_a6 else "-", m_a6, "", cv(p_a7) if sw_a7 else "-", m_a7, "", cv(p_a9) if sw_a9 else "-", m_a9, "", cv(p_b1) if sw_b1 else "-", m_b1, "", new_memo, current_time_full]

            all_v = worksheet.get_all_values()
            current_cols = len(all_v[1]) if len(all_v) > 1 else 2
            new_idx = current_cols + 1
            def get_c(n):
                r = ""
                while n > 0: n, rem = divmod(n - 1, 26); r = chr(65 + rem) + r
                return r
            worksheet.update("B2", [[v] for v in labels])
            worksheet.update(f"{get_c(new_idx)}2", [[v] for v in payload])

            # [2] 텔레그램 상세 메시지 빌더 (타이틀 추가 버전 결합)
            tg_msg = f"🚀 *Laporan QC Lapangan*\n📅 {full_today} | {shift_label}\n👤 QC: {pelapor}\n"
            tg_msg += "--------------------------------\n\n"

            # 30분 단위 요약
            tg_msg += "*⚡ 30 Menit*\n"
            m30_items = [
                ("A-4", "a4", g_a4, sw_a4, m_a4, "QC Tablet"), 
                ("A-5", "a5", g_a5, sw_a5, m_a5, "Status Steam Test"), 
                ("B-3", "b3", g_b3, sw_b3, m_b3, "Situasi Kupas"), 
                ("B-4", "b4", g_b4, sw_b4, m_b4, "Situasi Packing"), 
                ("B-5", "b5", g_b5, sw_b5, m_b5, "Hasil Per Jam"), 
                ("B-9", "b9", g_b9, sw_b9, m_b9, "Kondisi BB")
            ]
            for label, key, goal, sw, m, title in m30_items:
                if sw:
                    tg_msg += f"• {label}. {title}: {get_prog_bar(st.session_state.qc_store[key], goal)}\n"
                    if m: tg_msg += f"  └ 💬 {m}\n"

            # 1시간 단위 요약
            tg_msg += "\n*⏰ 1 Jam*\n"
            m1h_items = [
                ("A-8", "a8", g_a8, sw_a8, m_a8, "Status Barang Jatuh"), 
                ("B-2", "b2", g_b2, sw_b2, m_b2, "Status Steam"), 
                ("B-6", "b6", g_b6, sw_b6, m_b6, "Laporan Giling"), 
                ("B-7", "b7", g_b7, sw_b7, m_b7, "Giling - Steril"), 
                ("B-8", "b8", g_b8, sw_b8, m_b8, "Laporan Potong"), 
                ("B-10", "b10", g_b10, sw_b10, m_b10, "Laporan Dry")
            ]
            for label, key, goal, sw, m, title in m1h_items:
                if sw:
                    tg_msg += f"• {label}. {title}: {get_prog_bar(st.session_state.qc_store[key], goal)}\n"
                    if m: tg_msg += f"  └ 💬 {m}\n"

            # 루틴 요약
            tg_msg += "\n*📅 Routine*\n"
            rt_items = [
                ("A-1", "a1", sw_a1, p_a1, m_a1, "Stok BB Steam"), 
                ("A-2", "a2", sw_a2, p_a2, m_a2, "Stok BS Defros"), 
                ("A-3", "a3", sw_a3, p_a3, m_a3, "Handover In"), 
                ("A-6", "a6", sw_a6, p_a6, m_a6, "List BB Kirim"), 
                ("A-7", "a7", sw_a7, p_a7, m_a7, "Rencana Produksi"), 
                ("A-9", "a9", sw_a9, p_a9, m_a9, "Sisa Barang"), 
                ("B-1", "b1", sw_b1, p_b1, m_b1, "Cek Absensi")
            ]
            for label, key, sw, checks, m, title in rt_items:
                if sw:
                    tg_msg += f"• {label}. {title}: {', '.join(checks) if checks else '-'}\n"
                    if m: tg_msg += f"  └ 💬 {m}\n"
            
            tg_msg += f"\n📝 *Memo:* {new_memo}"
            
            # [3] 최종 발송
            send_telegram(tg_msg)
            st.success(f"✅ [{target_tab_name}] 저장 및 텔레그램 상세 보고 완료!")
            
        except Exception as e: st.error(f"🚨 에러: {e}")
    else: st.error("시트 연결 실패")
