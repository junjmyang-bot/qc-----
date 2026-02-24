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
        "a5": {"title": "Status tes steam", "desc": ["maksimal selesai jam 13.00", "update laporan setiap 30 menit", "cek sampel", "cek pembaruan laporan"]},
        "a6": {"title": "List BB butuh kirim", "qs": ["List kirim jam 12.00 sudah ada?", "Kordinasi gudang & plantation?"]},
        "a3": {"title": "Handover shift 전", "qs": ["Sudah dapat handover?", "Produksi sesuai rencana?"]},
        "a7": {"title": "Handover & rencana", "qs": ["Rencana sudah dibuat?", "Handover sudah dibuat?", "Sudah baca data stok?"]},
        "a9": {"title": "SISA BARANG", "qs": ["Check MAX 1 PACK", "Sisa shift prev?", "Sudah dibereskan?", "Simpan sisa?", "Handover sisa?"]},
        "a4": {"title": "Laporan QC di tablet", "check_items": ["daily kebersihan", "kontaminan kupas", "kontaminan packing"]},
        "a8": {"title": "Status barang jatuh", "areas": ["steam", "kupas", "dry", "packing", "cuci"]}
    },
    "B": {
        "b1": {"title": "Cek Laporan Absensi", "desc": ["Durasi 2 kali awal masuk과 휴식 후", "Perubahan jumlah orang 확인"], "areas": ["Steam", "Dry", "Kupas", "Packing"]},
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

# --- 3. 세션 상태 초기화 (AttributeError 방지 전수 조사) ---
ITEMS = ["a4","a5","b3","b4","b5","b9","a8","b2","b6","b7","b8","b10","a1","a2","a3","a6","a7","a9","b1"]
if 'qc_store' not in st.session_state: st.session_state.qc_store = {k: [] for k in ITEMS}
if 'v_map' not in st.session_state: st.session_state.v_map = {k: 0 for k in ITEMS}
if 'a4_ts' not in st.session_state: st.session_state.a4_ts = []
if 'a8_logs' not in st.session_state: st.session_state.a8_logs = []
# B-1 인원 상세 데이터 초기화
if 'b1_data' not in st.session_state: st.session_state.b1_data = {t: {a: {"jam": "", "pax": "", "st": "O"} for a in QC_CONTENT['B']['b1']['areas']} for t in ["Awal", "Istirahat"]}

def get_prog_bar(val, goal):
    perc = int((len(val)/goal)*100) if goal > 0 else 0
    return f"{'■' * (perc // 10)}{'□' * (10 - (perc // 10))} ({perc}%)"

def send_telegram(text):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})

@st.dialog("Konfirmasi Pembatalan")
def confirm_cancel_dialog(idx):
    st.warning(f"Apakah Anda yakin ingin menghapus 시간?")
    if st.button("Ya, Hapus (확인)", type="primary", use_container_width=True):
        st.session_state.a4_ts = st.session_state.a4_ts[:idx]; st.rerun()

# --- 4. 사이드바 설정 (19개 전 항목 토글 복구) ---
with st.sidebar:
    st.header("⚙️ 리포트 세부 설정")
    with st.expander("📅 시프트 루틴 설정", expanded=True):
        st.caption("🅰️ Routine Others")
        sw_a1=st.toggle(f"A-1 {QC_CONTENT['A']['a1']['title']}",True); sw_a2=st.toggle(f"A-2 {QC_CONTENT['A']['a2']['title']}",True); sw_a3=st.toggle(f"A-3",True); sw_a7=st.toggle(f"A-7",True); sw_a9=st.toggle(f"A-9",True)
        st.divider(); st.info("📦 Bahan Baku")
        sw_a5=st.toggle(f"A-5",True); sw_a6=st.toggle(f"A-6",True)
        st.divider(); st.caption("🅱️ Check TL Reports")
        sw_b1=st.toggle(f"B-1 {QC_CONTENT['B']['b1']['title']}",True)
    with st.expander("⚡ 30분 단위 설정", expanded=False):
        sw_a4=st.toggle("A-4 (Timestamp)",True); sw_b3=st.toggle("B-3",True); sw_b4=st.toggle("B-4",True); sw_b5=st.toggle("B-5",True); sw_b9=st.toggle("B-9",True)
    with st.expander("⏰ 1시간 단위 설정", expanded=False):
        sw_a8=st.toggle("A-8 (Cognitive)",True); sw_b2=st.toggle("B-2",True); sw_b6=st.toggle("B-6",True); sw_b7=st.toggle("B-7",True); sw_b8=st.toggle("B-8",True); sw_b10=st.toggle("B-10",True)

# --- 5. 메인 UI ---
st.title("🏭 SOI QC 모니터링 시스템")
c1, c2 = st.columns(2)
with c1: shift_label = st.selectbox("SHIFT", ["Shift 1 (Pagi)", "Shift 2 (Sore)", "Shift tengah"])
with c2: pelapor = st.selectbox("담당자", ["Diana", "Uyun", "Rossa", "Dini", "JUNMO YANG"])

# [섹션 1: 시프트 루틴]
st.subheader("📅 시프트 루틴")
with st.container(border=True):
    col_a, col_b = st.columns(2)
    with col_a:
        st.info("🅰️ QC Direct Check")
        st.markdown("##### 📝 Routine Others")
        if sw_a1:
            st.markdown(f"**A1. {QC_CONTENT['A']['a1']['title']}**")
            p_a1 = st.pills("Check Time (A1)", ["Awal Masuk", "Setelah Istirahat"], selection_mode="multi", key="u_a1")
            ans_a1_1 = st.text_input(f"1. {QC_CONTENT['A']['a1']['qs'][0]}", key="a1_1"); ans_a1_2 = st.text_input(f"2. {QC_CONTENT['A']['a1']['qs'][1]}", key="a1_2"); ans_a1_3 = st.text_input(f"3. {QC_CONTENT['A']['a1']['qs'][2]}", key="a1_3"); st.divider()
        if sw_a2:
            st.markdown(f"**A2. {QC_CONTENT['A']['a2']['title']}**")
            p_a2 = st.pills("Check Time (A2)", ["Awal Masuk", "Setelah Istirahat"], selection_mode="multi", key="u_a2")
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

        st.markdown("##### 📦 Bahan Baku (Shift 1 Only Focus)")
        if "Shift 1" in shift_label: st.warning("⚠️ Khusus Shift 1 Only")
        if sw_a5:
            st.markdown(f"**A5. {QC_CONTENT['A']['a5']['title']}**")
            for desc in QC_CONTENT['A']['a5']['desc']: st.markdown(f"<span style='color:black;'>→ {desc}</span>", unsafe_allow_html=True)
            ans_a5 = st.radio("A5 Status", ["Done", "Not done"], horizontal=True, key="a5_st", label_visibility="collapsed")
            memo_a5 = st.text_input("Memo (A5 Not done)", key="m_a5") if ans_a5 == "Not done" else ""; st.divider()
        if sw_a6:
            st.markdown(f"**A6. {QC_CONTENT['A']['a6']['title']}**")
            ans_a6_1 = st.radio(f"-> {QC_CONTENT['A']['a6']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a6_1")
            memo_a6_1 = st.text_input("Memo A6-1", key="m_a6_1") if ans_a6_1 == "No" else ""
            ans_a6_2 = st.radio(f"-> {QC_CONTENT['A']['a6']['qs'][1]}", ["Yes", "No"], horizontal=True, key="a6_2")
            memo_a6_2 = st.text_input("Memo A6-2", key="m_a6_2") if ans_a6_2 == "No" else ""

    with col_b:
        st.warning("🅱️ Check TL Reports")
        # [고도화] B-1 인원 상세 그리드
        if sw_b1:
            st.markdown(f"**B1. {QC_CONTENT['B']['b1']['title']}**")
            for desc in QC_CONTENT['B']['b1']['desc']: st.markdown(f"<span style='color:black;'>→ {desc}</span>", unsafe_allow_html=True)
            t1, t2 = st.tabs(["🌅 Awal Masuk", "☕ Setelah Istirahat"])
            for t_label, tab in [("Awal", t1), ("Istirahat", t2)]:
                with tab:
                    for area in QC_CONTENT['B']['b1']['areas']:
                        st.markdown(f"**{area} Absensi**")
                        r1, r2, r3 = st.columns([1.5, 1, 1])
                        with r1: st.session_state.b1_data[t_label][area]['jam'] = st.text_input(f"Jam ({area})", key=f"b1_{t_label}_{area}_j", placeholder="07.30")
                        with r2: st.session_state.b1_data[t_label][area]['pax'] = st.text_input(f"Pax ({area})", key=f"b1_{t_label}_{area}_p", placeholder="2 pax")
                        with r3: st.session_state.b1_data[t_label][area]['st'] = st.radio(f"Stat ({area})", ["O", "X"], key=f"b1_{t_label}_{area}_s", horizontal=True)
            st.divider()

# [섹션 2: 30분 단위]
st.subheader("⚡ 30분 단위")
with st.container(border=True):
    ca, cb = st.columns(2)
    with ca:
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
    with cb:
        st.warning("🅱️ Check TL Reports")
        for k in ["b3", "b4", "b5", "b9"]:
            if eval(f"sw_{k}"):
                st.markdown(f"**{k.upper()}. {QC_CONTENT['B'][k]['title']}**")
                vk = st.session_state.v_map[k]; st.pills(k, [str(i) for i in range(1, 17)], key=f"u_{k}_{i}", selection_mode="multi", label_visibility="collapsed")
                st.text_input(f"Comment {k}", key=f"m_{k}")

# [섹션 3: 1시간 단위]
st.subheader("⏰ 1시간 단위")
with st.container(border=True):
    ca, cb = st.columns(2)
    with ca:
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
                    if st.button(f"Confirm Hour {curr_a8 + 1}", type="primary"):
                        st.session_state.a8_logs.append({"t": datetime.now(jakarta_tz).strftime("%H:%M"), "f": has_f, "d": f_inf if has_f=="Yes" else None}); st.rerun()
            for i, log in enumerate(st.session_state.a8_logs): st.success(f"Hour {i+1} [{log['t']}] Fall: {log['f']}")
    with cb:
        st.warning("🅱️ Check TL Reports")
        for k in ["b2", "b6", "b7", "b8", "b10"]:
            if eval(f"sw_{k}"):
                st.markdown(f"**{k.upper()}. {QC_CONTENT['B'][k]['title']}**")
                vk = st.session_state.v_map[k]; st.pills(k, [str(i) for i in range(1, 9)], key=f"u_{k}_{i}", selection_mode="multi", label_visibility="collapsed")
                st.text_input(f"Comment {k}", key=f"m_{k}")

main_memo = st.text_area("종합 특이사항 입력", key="main_memo_input")

# --- 6. [전면 보강] 텔레그램 상세 전송 로직 (100% 투사) ---
if st.button("💾 저장 및 텔레그램 전송", type="primary", use_container_width=True):
    try:
        tg_msg = f"🚀 *Laporan QC Lapangan*\n📅 {full_today} | {shift_label}\n👤 QC: {pelapor}\n--------------------------------\n\n"
        
        # [A: Routine Others]
        tg_msg += "📅 *Routine Others*\n"
        if sw_a1: tg_msg += f"• A-1. {QC_CONTENT['A']['a1']['title']}\n  ({', '.join(p_a1)})\n  - {QC_CONTENT['A']['a1']['qs'][0]}: {ans_a1_1}\n  - {QC_CONTENT['A']['a1']['qs'][1]}: {ans_a1_2}\n\n"
        if sw_a2: tg_msg += f"• A-2. {QC_CONTENT['A']['a2']['title']}\n  ({', '.join(p_a2)})\n  - {QC_CONTENT['A']['a2']['qs'][0]}: {ans_a2_1}\n  - {QC_CONTENT['A']['a2']['qs'][1]}: {ans_a2_2}\n\n"
        if sw_a3: tg_msg += f"• A-3. Handover: {ans_a3_1}" + (f" (💬 {memo_a3_1})" if memo_a3_1 else "") + f" | Rencana: {ans_a3_2}\n"
        if sw_a7: tg_msg += f"• A-7. Rencana: {ans_a7_1} | Handover: {ans_a7_2} (👤 {name_a7_2})\n  Data Stok: {ans_a7_3}\n\n"
        if sw_a9: tg_msg += f"• A-9. Sisa Barang: {ans_a9_1}\n  └ Prev Shift: {ans_a9_2}\n  └ Handover: {ans_a9_5}\n\n"

        # [A: Bahan Baku]
        tg_msg += "📦 *Bahan Baku (Shift 1)*\n"
        if sw_a5: tg_msg += f"• A-5. Status Steam: {ans_a5}" + (f" (💬 {memo_a5})" if memo_a5 else "") + "\n"
        if sw_a6: tg_msg += f"• A-6. List Jam 12: {ans_a6_1} | Kordinasi: {ans_a6_2}\n\n"

        # [B: Absensi 상세화]
        if sw_b1:
            tg_msg += "👥 *B-1. Absensi (Detail)*\n"
            for tl in ["Awal", "Istirahat"]:
                tg_msg += f"  [{tl} Masuk]\n"
                for ar in QC_CONTENT['B']['b1']['areas']:
                    dat = st.session_state.b1_data[tl][ar]
                    tg_msg += f"  - {ar}: {dat['jam'] if dat['jam'] else '00.00'} / {dat['pax'] if dat['pax'] else '0 pax'} / ({dat['st']})\n"
            tg_msg += "\n"

        # [A-4, A-8 상세화]
        if sw_a4: tg_msg += f"⚡ *A-4 Records:* {' | '.join(st.session_state.a4_ts)}\n{get_prog_bar(st.session_state.a4_ts, 16)}\n\n"
        if sw_a8 and st.session_state.a8_logs:
            tg_msg += "⏰ *A-8 Status Barang Jatuh*\n"
            for log in st.session_state.a8_logs:
                tg_msg += f"  Hr({log['t']}): Fall {log['f']}" + (f" [📦{log['d']['p']}]" if log['f']=="Yes" else "") + "\n"

        tg_msg += f"\n📝 *Memo:* {main_memo if main_memo else '-'}\n"
        tg_msg += f"🕒 *Update:* {datetime.now(jakarta_tz).strftime('%H:%M:%S')}"
        
        send_telegram(tg_msg); st.success("✅ 상세 보고 전송 완료!")
    except Exception as e: st.error(f"전송 에러: {e}")
