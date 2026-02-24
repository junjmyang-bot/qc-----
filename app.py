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

# --- 2. [데이터 보존] 19개 전 항목 상세 가이드 및 질문 데이터 ---
QC_CONTENT = {
    "A": {
        "a1": {"title": "Cek Stok BB Sudah steam", "qs": ["Sisa BB sisa shift sebelumya?", "Jumlah bb steam 충분?", "Respon if kurang?"]},
        "a2": {"title": "Cek Stok BS (Sudah defros)", "qs": ["Sudah defros 얼마?", "Estimasi 작업량?", "Jam tambah defros?"]},
        "a3": {"title": "Handover shift 전", "qs": ["Sudah dapat handover?", "Produksi sesuai rencana?"]},
        "a7": {"title": "Handover & rencana", "qs": ["Rencana sudah dibuat?", "Handover sudah dibuat?", "Sudah baca data stok?"]},
        "a9": {"title": "SISA BARANG", "qs": ["Check MAX 1 PACK", "Sisa shift prev?", "Sudah dibereskan?", "Simpan sisa?", "Handover sisa?"]},
        "a4": {"title": "Laporan QC di tablet", "check_items": ["daily kebersihan", "kontaminan kupas", "kontaminan packing"]},
        "a5": {"title": "Status tes steam", "desc": ["maksimal selesai jam 13.00", "update laporan 30분 마다", "cek sampel", "cek laporan"]},
        "a6": {"title": "List BB butuh kirim", "qs": ["List kirim jam 12.00?", "Kordinasi gudang?"]},
        "a8": {"title": "Status barang jatuh", "areas": ["steam", "kupas", "dry", "packing", "cuci"]}
    },
    "B": {
        "b1": {"title": "Cek Laporan Absensi", "desc": ["Durasi 2 kali awal masuk과 후식 후", "Perubahan 인원 확인"], "areas": ["Steam", "Dry", "Kupas", "Packing"]},
        "b2": {"title": "Status Steam", "desc": ["1시간 마다", "Laporan 확인"]},
        "b3": {"title": "Situasi Kupas", "desc": ["TL update", "Kroscek 본인"]},
        "b4": {"title": "Situasi Packing", "desc": ["TL update", "Kroscek 본인"]},
        "b5": {"title": "Hasil Per Jam", "desc": ["제품 확인", "TL update"]},
        "b6": {"title": "Laporan Giling", "desc": ["제품 확인", "TL update"]},
        "b7": {"title": "Steril BB", "desc": ["TL update 확인"]},
        "b8": {"title": "Laporan Potong", "desc": ["Cara nata", "Machine Setting"]},
        "b9": {"title": "Kondisi BB", "desc": ["30분 마다 업데이트"]},
        "b10": {"title": "Laporan Dry", "desc": ["TL update", "Status mesin"]}
    }
}

# --- 3. 세션 상태 초기화 (에러 방지를 위해 기존 키 강제 업데이트) ---
ITEMS = ["a4","a5","b3","b4","b5","b9","a8","b2","b6","b7","b8","b10","a1","a2","a3","a6","a7","a9","b1"]
if 'qc_store' not in st.session_state: st.session_state.qc_store = {k: [] for k in ITEMS}
if 'v_map' not in st.session_state: st.session_state.v_map = {k: 0 for k in ITEMS}
if 'a4_ts' not in st.session_state: st.session_state.a4_ts = []
if 'a8_logs' not in st.session_state: st.session_state.a8_logs = []

# [해결] B-1 데이터 키를 명확히 고정하여 KeyError 원천 차단
TARGET_LABELS = ["Awal Masuk", "Setelah Istirahat"]
if 'b1_data' not in st.session_state or list(st.session_state.b1_data.keys()) != TARGET_LABELS:
    st.session_state.b1_data = {t: {a: {"jam": "", "pax": "", "st": "O"} for a in QC_CONTENT['B']['b1']['areas']} for t in TARGET_LABELS}

def get_prog_bar(val, goal):
    perc = int((len(val)/goal)*100) if goal > 0 else 0
    return f"{'■' * (perc // 10)}{'□' * (10 - (perc // 10))} ({perc}%)"

def send_telegram(text):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})

@st.dialog("Konfirmasi Pembatalan")
def confirm_cancel_dialog(idx):
    st.warning(f"Apakah Anda yakin ingin menghapus 기록?")
    if st.button("Ya, Hapus (확인)", type="primary", use_container_width=True):
        st.session_state.a4_ts = st.session_state.a4_ts[:idx]; st.rerun()

# --- 4. 사이드바 설정 (19개 전 항목 보존) ---
with st.sidebar:
    st.header("⚙️ 리포트 세부 설정")
    with st.expander("📅 시프트 루틴 설정", expanded=True):
        st.caption("🅰️ QC Routine (Others)")
        sw_a1=st.toggle(f"A-1 {QC_CONTENT['A']['a1']['title']}", True); sw_a2=st.toggle(f"A-2 {QC_CONTENT['A']['a2']['title']}", True); sw_a3=st.toggle("A-3", True); sw_a7=st.toggle("A-7", True); sw_a9=st.toggle("A-9", True)
        st.divider(); st.info("📦 Bahan Baku")
        sw_a5=st.toggle("A-5", True); sw_a6=st.toggle("A-6", True)
        st.divider(); st.caption("🅱️ Check TL Reports")
        sw_b1=st.toggle("B-1 Absensi", True)
    with st.expander("⚡ 30분 단위 설정", expanded=False):
        sw_a4=st.toggle("A-4", True); sw_b3=st.toggle("B-3",True); sw_b4=st.toggle("B-4",True); sw_b5=st.toggle("B-5",True); sw_b9=st.toggle("B-9",True)
    with st.expander("⏰ 1시간 단위 설정", expanded=False):
        sw_a8=st.toggle("A-8", True); sw_b2=st.toggle("B-2",True); sw_b6=st.toggle("B-6",True); sw_b7=st.toggle("B-7",True); sw_b8=st.toggle("B-8",True); sw_b10=st.toggle("B-10",True)

# --- 5. 메인 UI ---
st.title("🏭 SOI QC 모니터링 시스템")
c1, c2 = st.columns(2)
with c1: shift_label = st.selectbox("SHIFT", ["Shift 1 (Pagi)", "Shift 2 (Sore)", "Shift tengah"])
with c2: pelapor = st.selectbox("담당자", ["Diana", "Uyun", "Rossa", "Dini", "JUNMO YANG"])

# [섹션 1: 시프트 루틴]
st.subheader("📅 시프트 루틴")
with st.container(border=True):
    cola, colb = st.columns(2)
    with cola:
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
            st.markdown("**A3. Handover shift 전**")
            ans_a3_1 = st.radio(f"-> {QC_CONTENT['A']['a3']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a3_1")
            memo_a3_1 = st.text_input("Memo A3-1", key="m_a3_1") if ans_a3_1 == "No" else ""
            ans_a3_2 = st.radio(f"-> {QC_CONTENT['A']['a3']['qs'][1]}", ["Yes", "No"], horizontal=True, key="a3_2")
            memo_a3_2 = st.text_input("Memo A3-2", key="m_a3_2") if ans_a3_2 == "No" else ""; st.divider()
        if sw_a7:
            st.markdown("**A7. Handover & rencana**")
            ans_a7_1 = st.radio(f"-> {QC_CONTENT['A']['a7']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a7_1")
            memo_a7_1 = st.text_input("Memo A7-1", key="m_a7_1") if ans_a7_1 == "No" else ""
            ans_a7_2 = st.radio(f"-> {QC_CONTENT['A']['a7']['qs'][1]}", ["Yes", "No"], horizontal=True, key="a7_2")
            if ans_a7_2 == "No": memo_a7_2 = st.text_input("Memo A7-2", key="m_a7_2"); name_a7_2 = ""
            else: name_a7_2 = st.text_input("Nama 수령인", key="n_a7_2"); memo_a7_2 = ""
            ans_a7_3 = st.text_area(f"-> {QC_CONTENT['A']['a7']['qs'][2]}", key="a7_3"); st.divider()
        if sw_a9:
            st.markdown("**A9. SISA BARANG**")
            ans_a9_1 = st.radio(f"1. {QC_CONTENT['A']['a9']['qs'][0]}", ["Sudah check", "Belum"], horizontal=True, key="a9_1")
            memo_a9_1 = st.text_input("Memo A9-1", key="m_a9_1") if ans_a9_1 == "Belum" else ""
            ans_a9_2 = st.text_area(f"2. {QC_CONTENT['A']['a9']['qs'][1]}", key="a9_2")
            ans_a9_5 = st.text_area(f"5. {QC_CONTENT['A']['a9']['qs'][4]}", key="a9_5"); st.divider()

        st.markdown("##### 📦 Bahan Baku")
        if "Shift 1" in shift_label: st.warning("⚠️ **Khusus Shift 1 Only**")
        if sw_a5:
            st.markdown(f"**A5. {QC_CONTENT['A']['a5']['title']}**")
            for item in QC_CONTENT['A']['a5']['desc']: st.markdown(f"<span style='color:black;'>→ {item}</span>", unsafe_allow_html=True)
            ans_a5 = st.radio("A5 Status", ["Done", "Not done"], horizontal=True, key="a5_st", label_visibility="collapsed")
            memo_a5 = st.text_input("Memo (A5)", key="m_a5") if ans_a5 == "Not done" else ""; st.divider()
        if sw_a6:
            st.markdown("**A6. List BB butuh kirim**")
            ans_a6_1 = st.radio(f"-> {QC_CONTENT['A']['a6']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a6_1")
            memo_a6_1 = st.text_input("Memo A6-1", key="m_a6_1") if ans_a6_1 == "No" else ""
            ans_a6_2 = st.radio(f"-> {QC_CONTENT['A']['a6']['qs'][1]}", ["Yes", "No"], horizontal=True, key="a6_2")
            memo_a6_2 = st.text_input("Memo A6-2", key="m_a6_2") if ans_a6_2 == "No" else ""

    with colb:
        st.warning("🅱️ Check TL Reports")
        # [수정] B-1 Absensi: Setelah Istirahat 라벨링 완벽 반영
        if sw_b1:
            st.markdown(f"**B1. {QC_CONTENT['B']['b1']['title']}**")
            t1, t2 = st.tabs(["🌅 Awal Masuk", "☕ Setelah Istirahat"])
            for t_label, tab in [("Awal Masuk", t1), ("Setelah Istirahat", t2)]:
                with tab:
                    for area in QC_CONTENT['B']['b1']['areas']:
                        st.markdown(f"**{area} Absensi**")
                        r1, r2, r3 = st.columns([1.5, 1, 1])
                        # KeyError 방지를 위한 정확한 t_label 매칭
                        with r1: st.session_state.b1_data[t_label][area]['jam'] = st.text_input(f"Jam {area} {t_label}", key=f"b1_{t_label}_{area}_j", placeholder="07.30")
                        with r2: st.session_state.b1_data[t_label][area]['pax'] = st.text_input(f"Pax {area} {t_label}", key=f"b1_{t_label}_{area}_p", placeholder="2 pax")
                        with r3: st.session_state.b1_data[t_label][area]['st'] = st.radio(f"S/T {area} {t_label}", ["O", "X"], key=f"b1_{t_label}_{area}_s", horizontal=True)

# [섹션 2/3: 30분 및 1시간 단위 (조작 방지 및 인지 강화 보존)]
st.subheader("⚡ 30분 단위")
with st.container(border=True):
    ca, cb = st.columns(2)
    with ca:
        if sw_a4:
            st.markdown(f"**A4. {QC_CONTENT['A']['a4']['title']}**")
            for item in QC_CONTENT['A']['a4']['check_items']: st.markdown(f"<span style='color:black;'>→ {item}</span>", unsafe_allow_html=True)
            cols = st.columns(4)
            for i in range(16):
                with cols[i % 4]:
                    is_f = i < len(st.session_state.a4_ts)
                    txt = st.session_state.a4_ts[i] if is_f else str(i+1)
                    if is_f:
                        if st.button(txt, key=f"a4_b_{i}", type="secondary", use_container_width=True): confirm_cancel_dialog(i)
                    else:
                        if st.button(txt, key=f"a4_b_{i}", disabled=(i != len(st.session_state.a4_ts)), type="primary", use_container_width=True):
                            st.session_state.a4_ts.append(datetime.now(jakarta_tz).strftime("%H:%M")); st.rerun()
            st.text_input("A4 코멘트", key="m_a4")
    with cb:
        for k in ["b3", "b4", "b5", "b9"]:
            if eval(f"sw_{k}"):
                st.markdown(f"**{k.upper()}. {QC_CONTENT['B'][k]['title']}**")
                st.pills(k, [str(i) for i in range(1, 17)], key=f"u_{k}_{i}", selection_mode="multi", label_visibility="collapsed")
                st.text_input(f"Comment {k}", key=f"m_{k}")

st.subheader("⏰ 1시간 단위")
with st.container(border=True):
    ca, cb = st.columns(2)
    with ca:
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
                    if st.button(f"Confirm Hour {curr_a8 + 1}", type="primary"):
                        st.session_state.a8_logs.append({"t": datetime.now(jakarta_tz).strftime("%H:%M"), "f": has_f, "d": f_inf if has_f=="Yes" else None}); st.rerun()
            for i, log in enumerate(st.session_state.a8_logs): st.success(f"Hour {i+1} [{log['t']}] Fall: {log['f']}")
    with cb:
        for k in ["b2", "b6", "b7", "b8", "b10"]:
            if eval(f"sw_{k}"):
                st.markdown(f"**{k.upper()}. {QC_CONTENT['B'][k]['title']}**")
                st.pills(k, [str(i) for i in range(1, 9)], key=f"u_{k}_{i}", selection_mode="multi", label_visibility="collapsed")
                st.text_input(f"Comment {k}", key=f"m_{k}")

main_memo = st.text_area("종합 특이사항 입력", key="main_memo_v")

# --- 6. [최고도화] 텔레그램 상세 리포트 엔진 ---
if st.button("💾 저장 및 텔레그램 전송", type="primary", use_container_width=True):
    try:
        tg_msg = f"🚀 *Laporan QC Lapangan*\n📅 {full_today} | {shift_label}\n👤 QC: {pelapor}\n--------------------------------\n\n"
        
        # [A: Routine Others] 질문과 답변 상세 투사
        tg_msg += "📅 *Routine Others*\n"
        if sw_a1: tg_msg += f"• A-1. {QC_CONTENT['A']['a1']['title']}\n  ({', '.join(p_a1) if p_a1 else 'Belum'})\n  - Q1: {ans_a1_1 if ans_a1_1 else '-'}\n  - Q2: {ans_a1_2 if ans_a1_2 else '-'}\n\n"
        if sw_a7: tg_msg += f"• A-7. Rencana: {ans_a7_1} | Handover: {ans_a7_2} (👤 {name_a7_2})\n  - Data Stok: {ans_a7_3}\n"
        
        # [B-1 Absensi 상세 투사]
        if sw_b1:
            tg_msg += "\n👥 *B-1. Laporan Absensi*\n"
            for tl in ["Awal Masuk", "Setelah Istirahat"]:
                tg_msg += f"  [{tl}]\n"
                for ar in QC_CONTENT['B']['b1']['areas']:
                    dat = st.session_state.b1_data[tl][ar]
                    tg_msg += f"  - {ar}: {dat['jam'] if dat['jam'] else '00.00'} / {dat['pax'] if dat['pax'] else '0 pax'} / ({dat['st']})\n"

        # [Section: Bahan Baku / A-4 / A-8]
        if sw_a5: tg_msg += f"\n📦 *A-5 Status Steam:* {ans_a5}" + (f" (💬 {memo_a5})" if memo_a5 else "") + "\n"
        if sw_a4: tg_msg += f"⚡ *A-4 Records:* {' | '.join(st.session_state.a4_ts)}\n"
        if sw_a8 and st.session_state.a8_logs:
            tg_msg += "⏰ *A-8 Status Barang Jatuh*\n"
            for log in st.session_state.a8_logs: tg_msg += f"  Hr({log['t']}): Fall {log['f']}\n"

        tg_msg += f"\n📝 *Memo:* {main_memo if main_memo else '-'}\n🕒 *Update:* {datetime.now(jakarta_tz).strftime('%H:%M:%S')}"
        send_telegram(tg_msg); st.success("✅ 상세 보고 전송 완료!")
    except Exception as e: st.error(f"에러: {e}")
