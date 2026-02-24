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

# --- 2. [데이터 보존] 19개 전 항목 가이드 및 질문 데이터 ---
QC_CONTENT = {
    "A": {
        "a1": {"title": "Cek Stok BB Sudah steam", "qs": ["Sisa BB sisa shift sebelumya?", "Jumlah bb steam 충분?", "Respon if kurang?"]},
        "a2": {"title": "Cek Stok BS (Sudah defros)", "qs": ["Sudah defros 얼마?", "Estimasi 작업량?", "Jam tambah defros?"]},
        "a5": {
            "title": "Status tes steam", 
            "desc": ["maksimal jam 13.00", "update laporan setiap 30 menit", "cek sampel", "cek pembaruan laporan"]
        },
        "a6": {"title": "List BB butuh kirim", "qs": ["List kirim jam 12.00 sudah ada?", "Kordinasi gudang & plantation?"]},
        "a3": {"title": "Handover shift 전", "qs": ["Sudah dapat handover?", "Produksi sesuai rencana?"]},
        "a7": {"title": "Handover & rencana", "qs": ["Rencana sudah dibuat?", "Handover sudah dibuat?", "Sudah baca data stok?"]},
        "a9": {"title": "SISA BARANG", "qs": ["Check MAX 1 PACK", "Sisa shift prev?", "Sudah dibereskan?", "Simpan sisa?", "Handover sisa?"]},
        "a4": {"title": "Laporan QC di tablet", "check_items": ["daily kebersihan", "kontaminan kupas", "kontaminan packing"]},
        "a8": {"title": "Status barang jatuh", "areas": ["steam", "kupas", "dry", "packing", "cuci"]}
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

# --- 3. 세션 상태 초기화 (AttributeError 방지) ---
ITEMS = ["a4","a5","b3","b4","b5","b9","a8","b2","b6","b7","b8","b10","a1","a2","a3","a6","a7","a9","b1"]
if 'qc_store' not in st.session_state: st.session_state.qc_store = {k: [] for k in ITEMS}
if 'v_map' not in st.session_state: st.session_state.v_map = {k: 0 for k in ITEMS}
if 'history' not in st.session_state: st.session_state.history = {k: [] for k in ITEMS}
if 'a4_ts' not in st.session_state: st.session_state.a4_ts = []
if 'a8_logs' not in st.session_state: st.session_state.a8_logs = []

def get_prog_bar(val, goal):
    perc = int((len(val)/goal)*100) if goal > 0 else 0
    return f"{'■' * (perc // 10)}{'□' * (10 - (perc // 10))} ({perc}%)"

def send_telegram(text):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})

@st.dialog("Konfirmasi Pembatalan")
def confirm_cancel_dialog(idx):
    st.warning(f"Apakah Anda yakin ingin menghapus waktu di kolom {idx+1}?")
    if st.button("Ya, Hapus (취소)", type="primary", use_container_width=True):
        st.session_state.a4_ts = st.session_state.a4_ts[:idx]
        st.rerun()

# --- 4. 사이드바 설정 ---
with st.sidebar:
    st.header("⚙️ 리포트 세부 설정")
    with st.expander("📅 시프트 루틴 설정 (최상단)", expanded=True):
        st.caption("🅰️ Routine Others")
        sw_a1=st.toggle(f"A-1 {QC_CONTENT['A']['a1']['title']}", True); sw_a2=st.toggle(f"A-2 {QC_CONTENT['A']['a2']['title']}", True)
        sw_a3=st.toggle(f"A-3 {QC_CONTENT['A']['a3']['title']}", True); sw_a7=st.toggle(f"A-7 {QC_CONTENT['A']['a7']['title']}", True); sw_a9=st.toggle(f"A-9 {QC_CONTENT['A']['a9']['title']}", True)
        st.divider(); st.info("📦 Bahan Baku")
        sw_a5=st.toggle(f"A-5 {QC_CONTENT['A']['a5']['title']}", True); sw_a6=st.toggle(f"A-6 {QC_CONTENT['A']['a6']['title']}", True)
        st.divider(); st.caption("🅱️ Check TL Reports")
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

# --- 5. 메인 UI ---
st.title("🏭 SOI QC 모니터링 시스템")
c1, c2 = st.columns(2)
with c1: shift_label = st.selectbox("SHIFT", ["Shift 1 (Pagi)", "Shift 2 (Sore)", "Shift tengah"])
with c2: pelapor = st.selectbox("담당자", ["Diana", "Uyun", "Rossa", "Dini", "JUNMO YANG"])

st.subheader("📅 시프트 루틴")
with st.container(border=True):
    ca, cb = st.columns(2)
    with ca:
        st.info("🅰️ QC Direct Check")
        st.markdown("##### 📝 Routine Others")
        if sw_a1:
            st.markdown(f"**A1. {QC_CONTENT['A']['a1']['title']}**")
            p_a1 = st.pills("Time A1", ["Awal Masuk", "Setelah Istirahat"], selection_mode="multi", key="u_a1")
            ans_a1_1 = st.text_input(f"1. {QC_CONTENT['A']['a1']['qs'][0]}", key="a1_1"); ans_a1_2 = st.text_input(f"2. {QC_CONTENT['A']['a1']['qs'][1]}", key="a1_2"); ans_a1_3 = st.text_input(f"3. {QC_CONTENT['A']['a1']['qs'][2]}", key="a1_3"); st.divider()
        if sw_a2:
            st.markdown(f"**A2. {QC_CONTENT['A']['a2']['title']}**")
            p_a2 = st.pills("Time A2", ["Awal Masuk", "Setelah Istirahat"], selection_mode="multi", key="u_a2")
            ans_a2_1 = st.text_input(f"1. {QC_CONTENT['A']['a2']['qs'][0]}", key="a2_1"); ans_a2_2 = st.text_input(f"2. {QC_CONTENT['A']['a2']['qs'][1]}", key="a2_2"); ans_a2_3 = st.text_input(f"3. {QC_CONTENT['A']['a2']['qs'][2]}", key="a2_3"); st.divider()
        if sw_a3:
            st.markdown(f"**A3. {QC_CONTENT['A']['a3']['title']}**")
            ans_a3_1 = st.radio(f"-> {QC_CONTENT['A']['a3']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a3_1")
            memo_a3_1 = st.text_input("Memo A3-1", key="m_a3_1") if ans_a3_1 == "No" else ""
            ans_a3_2 = st.radio(f"-> {QC_CONTENT['A']['a3']['qs'][1]}", ["Yes", "No"], horizontal=True, key="a3_2")
            memo_a3_2 = st.text_input("Memo A3-2", key="m_a3_2") if ans_a3_2 == "No" else ""; st.divider()
        if sw_a7:
            st.markdown(f"**A7. {QC_CONTENT['A']['a7']['title']}**")
            ans_a7_1 = st.radio(f"-> {QC_CONTENT['A']['a7']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a7_1")
            memo_a7_1 = st.text_input("Memo A7-1", key="m_a7_1") if ans_a7_1 == "No" else ""
            ans_a7_2 = st.radio(f"-> {QC_CONTENT['A']['a7']['qs'][1]}", ["Yes", "No"], horizontal=True, key="a7_2")
            if ans_a7_2 == "No": memo_a7_2 = st.text_input("Memo A7-2", key="m_a7_2"); name_a7_2 = ""
            else: name_a7_2 = st.text_input("Nama 수령인", key="n_a7_2"); memo_a7_2 = ""
            ans_a7_3 = st.text_area(f"-> {QC_CONTENT['A']['a7']['qs'][2]}", key="a7_3"); st.divider()
        if sw_a9:
            st.markdown(f"**A9. {QC_CONTENT['A']['a9']['title']}**")
            ans_a9_1 = st.radio(f"1. {QC_CONTENT['A']['a9']['qs'][0]}", ["Sudah check", "Belum"], horizontal=True, key="a9_1")
            memo_a9_1 = st.text_input("Memo A9-1", key="m_a9_1") if ans_a9_1 == "Belum" else ""
            ans_a9_2=st.text_area(f"2. {QC_CONTENT['A']['a9']['qs'][1]}", key="a9_2"); ans_a9_3=st.text_area(f"3. {QC_CONTENT['A']['a9']['qs'][2]}", key="a9_3")
            ans_a9_4=st.text_area(f"4. {QC_CONTENT['A']['a9']['qs'][3]}", key="a9_4"); ans_a9_5=st.text_area(f"5. {QC_CONTENT['A']['a9']['qs'][4]}", key="a9_5"); st.divider()

        st.markdown("##### 📦 Bahan Baku")
        if "Shift 1" in shift_label: st.warning("⚠️ Khusus Shift 1 Only")
        if sw_a5:
            st.markdown(f"**A5. {QC_CONTENT['A']['a5']['title']}**")
            for item in QC_CONTENT['A']['a5']['desc']: st.markdown(f"<span style='color:black;'>→ {item}</span>", unsafe_allow_html=True)
            ans_a5 = st.radio("A5 Status", ["Done", "Not done"], horizontal=True, key="a5_st", label_visibility="collapsed")
            memo_a5 = st.text_input("Memo (A5 Not done)", key="m_a5") if ans_a5 == "Not done" else ""; st.divider()
        if sw_a6:
            st.markdown(f"**A6. {QC_CONTENT['A']['a6']['title']}**")
            ans_a6_1 = st.radio(f"-> {QC_CONTENT['A']['a6']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a6_1")
            memo_a6_1 = st.text_input("Memo A6-1", key="m_a6_1") if ans_a6_1 == "No" else ""
            ans_a6_2 = st.radio(f"-> {QC_CONTENT['A']['a6']['qs'][1]}", ["Yes", "No"], horizontal=True, key="a6_2")
            memo_a6_2 = st.text_input("Memo A6-2", key="m_a6_2") if ans_a6_2 == "No" else ""

    with cb:
        st.warning("🅱️ Check TL Reports")
        if sw_b1: st.markdown("**B1. Absensi**"); st.pills("b1", ["Awal", "Istirahat"], selection_mode="multi", key="u_b1")

st.subheader("⚡ 30분 단위")
with st.container(border=True):
    col_a, col_b = st.columns(2)
    with col_a:
        st.info("🅰️ QC Direct Check")
        if sw_a4:
            st.markdown(f"**A4. {QC_CONTENT['A']['a4']['title']}**")
            for item in QC_CONTENT['A']['a4']['check_items']: st.markdown(f"<span style='color:black;'>→ {item}</span>", unsafe_allow_html=True)
            cols = st.columns(4)
            for i in range(16):
                with cols[i % 4]:
                    is_filled = i < len(st.session_state.a4_ts)
                    txt = st.session_state.a4_ts[i] if is_filled else str(i+1)
                    if is_filled:
                        if st.button(txt, key=f"a4_b_{i}", type="secondary", use_container_width=True): confirm_cancel_dialog(i)
                    else:
                        is_disabled = (i != len(st.session_state.a4_ts))
                        if st.button(txt, key=f"a4_b_{i}", disabled=is_disabled, type="primary", use_container_width=True):
                            st.session_state.a4_ts.append(datetime.now(jakarta_tz).strftime("%H:%M")); st.rerun()
            st.text_input("A4 코멘트", key="m_a4")

st.subheader("⏰ 1시간 단위")
with st.container(border=True):
    col_a, col_b = st.columns(2)
    with col_a:
        st.info("🅰️ QC Direct Check")
        if sw_a8:
            st.markdown(f"**A8. {QC_CONTENT['A']['a8']['title']}**")
            curr_a8 = len(st.session_state.a8_logs)
            if curr_a8 < 8:
                st.write(f"🔔 **Hour {curr_a8 + 1} Cognitive Check**")
                v1 = st.text_input("1. Barang segera dibereskan? (Type 'YES')", key=f"a8_1_{curr_a8}")
                v2 = st.text_input("2. Tumpukan max 10 nampan? (Type 'YES')", key=f"a8_2_{curr_a8}")
                has_f = st.radio("3. Ada barang jatuh?", ["No", "Yes"], horizontal=True, key=f"a8_r_{curr_a8}")
                f_inf = {}
                if has_f == "Yes":
                    f_inf['p'] = st.text_input("Produk", key=f"a8_p_{curr_a8}"); f_inf['k'] = st.text_input("Kg/Pcs", key=f"a8_k_{curr_a8}"); f_inf['r'] = st.text_area("Alasan", key=f"a8_re_{curr_a8}")
                if v1.strip().upper() == "YES" and v2.strip().upper() == "YES":
                    if st.button(f"Confirm Hour {curr_a8+1}", type="primary"):
                        st.session_state.a8_logs.append({"t": datetime.now(jakarta_tz).strftime("%H:%M"), "f": has_f, "d": f_inf if has_f=="Yes" else None}); st.rerun()
            for i, log in enumerate(st.session_state.a8_logs): st.success(f"Hour {i+1} [{log['t']}] Fall: {log['f']}")

# --- 6. 저장 및 [수정] 텔레그램 전송 엔진 ---
if st.button("💾 저장 및 텔레그램 전송", type="primary", use_container_width=True):
    try:
        # 메시지 헤더
        tg_msg = f"🚀 *Laporan QC Lapangan*\n📅 {full_today} | {shift_label}\n👤 QC: {pelapor}\n"
        tg_msg += "--------------------------------\n\n"
        
        # [Section 1] Routine Others (상세 데이터 투사)
        tg_msg += "*📅 Routine Others*\n"
        if sw_a1: tg_msg += f"• A-1 Stok BB: {ans_a1_1 if ans_a1_1 else '-'} / {ans_a1_2 if ans_a1_2 else '-'}\n"
        if sw_a2: tg_msg += f"• A-2 Stok BS: {ans_a2_1 if ans_a2_1 else '-'} / {ans_a2_2 if ans_a2_2 else '-'}\n"
        if sw_a3: tg_msg += f"• A-3 Handover: {ans_a3_1}" + (f" (💬 {memo_a3_1})" if memo_a3_1 else "") + f" | Sesuai: {ans_a3_2}\n"
        if sw_a7: tg_msg += f"• A-7 Rencana: {ans_a7_1} / Handover: {ans_a7_2}" + (f" (👤 {name_a7_2})" if name_a7_2 else "") + "\n"
        if sw_a9: tg_msg += f"• A-9 Sisa Barang: {ans_a9_1}\n"
        if sw_b1: tg_msg += f"• B-1 Absensi: {', '.join(st.session_state.u_b1) if st.session_state.u_b1 else '-'}\n"
        
        # [Section 2] Bahan Baku (Shift 1 Focus)
        tg_msg += "\n*📦 Bahan Baku (Shift 1)*\n"
        if sw_a5: tg_msg += f"• A-5 Status Steam: {ans_a5}" + (f" (💬 {memo_a5})" if memo_a5 else "") + "\n"
        if sw_a6: tg_msg += f"• A-6 List BB: {ans_a6_1}" + (f" (💬 {memo_a6_1})" if memo_a6_1 else "") + f" | Kordinasi: {ans_a6_2}\n"
        
        # [Section 3] 30분 단위 (A-4 타임스탬프)
        if sw_a4:
            tg_msg += f"\n*⚡ A-4. {QC_CONTENT['A']['a4']['title']}*\n"
            if st.session_state.a4_ts: tg_msg += f"🕒 기록: {' | '.join(st.session_state.a4_ts)}\n"
            tg_msg += f"{get_prog_bar(st.session_state.a4_ts, 16)}\n"
            
        # [Section 4] 1시간 단위 (A-8 상세 로그)
        if sw_a8 and st.session_state.a8_logs:
            tg_msg += f"\n*⏰ A-8. {QC_CONTENT['A']['a8']['title']}*\n"
            for i, log in enumerate(st.session_state.a8_logs):
                tg_msg += f"  Hr{i+1}({log['t']}): Fall {log['f']}\n"
                if log['f'] == "Yes": tg_msg += f"    └ 📦 {log['d']['p']} / 💬 {log['d']['r']}\n"

        # [Section 5] Check TL Reports (B-Series)
        tg_msg += "\n*🅱️ Check TL Reports*\n"
        for k in ["b3", "b4", "b5", "b9", "b2", "b6", "b7", "b8", "b10"]:
            if eval(f"sw_{k}"):
                # B-series는 Pills 선택 정보를 history에서 가져와서 바(bar)로 표시
                goal = 16 if k in ["b3","b4","b5","b9"] else 8
                # 현재 선택된 값을 가져와서 바 생성
                # 세션 상태에서 직접 값을 읽어오기 위해 u_{k}_{idx} 가 아닌 실제 위젯 값을 찾아야함
                # 여기서는 임시로 progress_bar 함수 활용
                tg_msg += f"• {k.upper()}. {QC_CONTENT['B'][k]['title']}\n"
        
        # 하단 메모 및 전송
        tg_msg += f"\n📝 *Memo:* {st.session_state.main_memo if 'main_memo' in st.session_state else '-'}\n"
        tg_msg += f"🕒 *Update Terakhir:* {datetime.now(jakarta_tz).strftime('%H:%M:%S')}"
        
        send_telegram(tg_msg)
        st.success("✅ 상세 보고가 텔레그램으로 전송되었습니다!")
    except Exception as e: st.error(f"전송 에러: {e}")
