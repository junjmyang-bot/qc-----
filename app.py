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

# --- 2. [데이터 보존] 19개 전 항목 고도화 상세 가이드 및 질문 데이터 ---
QC_CONTENT = {
    "A": {
        "a1": {"title": "Cek Stok BB Sudah steam", "qs": ["Sisa BB sisa shift sebelumya?", "Jumlah bb steam 충분?", "Respon if kurang?"]},
        "a2": {"title": "Cek Stok BS (Sudah defros)", "qs": ["Sudah defros 얼마?", "Estimasi 작업량?", "Jam tambah defros?"]},
        "a3": {"title": "Handover shift 전", "qs": ["Sudah dapat handover?", "Produksi sesuai rencana?"]},
        "a7": {"title": "Handover & rencana", "qs": ["Rencana sudah dibuat?", "Handover sudah dibuat?", "Sudah baca data stok?"]},
        "a9": {"title": "SISA BARANG", "qs": ["Check MAX 1 PACK (Sudah check?)", "Sisa shift prev?", "Sudah dibereskan?", "Simpan sisa?", "Handover sisa?"]},
        "a4": {"title": "Laporan QC di tablet", "check_items": ["daily kebersihan", "kontaminan kupas", "kontaminan packing"]},
        "a5": {"title": "Status tes steam", "desc": ["maksimal jam 13.00", "update laporan 30분 마다", "cek 샘플/보고서"]},
        "a6": {"title": "List BB butuh kirim", "qs": ["List kirim jam 12.00?", "Kordinasi gudang?"]},
        "a8": {"title": "Status barang jatuh", "areas": ["steam", "kupas", "dry", "packing", "cuci"]}
    },
    "B": {
        "b1": {"title": "Cek Laporan Absensi", "desc": ["Durasi 2 kali (Awal & 후식 후)", "인원 변동 확인"], "areas": ["Steam", "Dry", "Kupas", "Packing"]},
        "b2": {"title": "Laporan Status steam", "interval": 60, "steps": 8, "qs": ["laporan sesuai", "cara isi laporan benar"]},
        "b3": {"title": "Laporan Situasi kupas", "interval": 30, "steps": 16, "qs": ["TL/petugas sudah update", "kroscek sudah benar?", "sudah kordinasi TL kupas/packing?", "laporan sesuai"]},
        "b4": {"title": "Laporan Situasi packing", "interval": 30, "steps": 16, "qs": ["TL/petugas sudah update", "kroscek sudah benar?", "sudah kordinasi TL kupas/packing?", "laporan sesuai"]},
        "b5": {"title": "Hasil per jam kupas/packing", "interval": 30, "steps": 16, "qs": ["laporan sesuai 제품", "TL/petugas sudah update", "laporan sesuai"]},
        "b6": {"title": "Laporan Giling", "interval": 60, "steps": 8, "qs": ["laporan sesuai 제품", "TL/petugas update", "laporan sesuai"]},
        "b7": {"title": "Laporan Giling - barang steril", "interval": 60, "steps": 8, "qs": ["laporan sesuai 제품", "TL/petugas update", "laporan sesuai"]},
        "b8": {"title": "Laporan potong", "interval": 60, "steps": 8, "qs": ["laporan sesuai 제품", "TL update", "cara nata benar", "settingan mesin benar", "laporan sesuai"]},
        "b9": {"title": "Laporan kondisi BB", "interval": 30, "steps": 16, "qs": ["TL/petugas update", "laporan sesuai"]},
        "b10": {"title": "Laporan Dry", "interval": 60, "steps": 8, "qs": ["TL/petugas update", "laporan sesuai", "status mesin 2 kali(휴식 전/후)"]}
    }
}

# --- 3. 세션 상태 초기화 (KeyError 및 AttributeError 원천 차단) ---
B_KEYS = ["b2","b3","b4","b5","b6","b7","b8","b9","b10"]
if 'b_logs' not in st.session_state: st.session_state.b_logs = {k: [] for k in B_KEYS}
if 'a4_ts' not in st.session_state: st.session_state.a4_ts = []
if 'a8_logs' not in st.session_state: st.session_state.a8_logs = []
if 'b1_data' not in st.session_state or list(st.session_state.b1_data.keys()) != ["Awal Masuk", "Setelah Istirahat"]:
    st.session_state.b1_data = {t: {a: {"jam": "", "pax": "", "st": "O"} for a in QC_CONTENT['B']['b1']['areas']} for t in ["Awal Masuk", "Setelah Istirahat"]}

def get_prog_bar(val_len, goal):
    perc = int((val_len/goal)*100) if goal > 0 else 0
    return f"{'■' * (perc // 10)}{'□' * (10 - (perc // 10))} ({perc}%)"

def send_telegram(text):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})

@st.dialog("Konfirmasi Pembatalan")
def confirm_cancel_dialog(idx):
    st.warning(f"Apakah Anda yakin ingin menghapus 기록?")
    if st.button("Ya, Hapus (확인)", type="primary", use_container_width=True):
        st.session_state.a4_ts = st.session_state.a4_ts[:idx]; st.rerun()

# --- 4. 사이드바 설정 (범주형 정돈) ---
with st.sidebar:
    st.header("⚙️ 리포트 세부 설정")
    with st.expander("📅 시프트 루틴 설정", expanded=True):
        st.caption("🅰️ Routine Others")
        sw_a1=st.toggle("A-1", True); sw_a2=st.toggle("A-2", True); sw_a3=st.toggle("A-3", True); sw_a7=st.toggle("A-7", True); sw_a9=st.toggle("A-9", True)
        st.divider(); st.info("📦 Bahan Baku"); sw_a5=st.toggle("A-5", True); sw_a6=st.toggle("A-6", True)
        st.divider(); st.caption("🅱️ Check TL Reports"); sw_b1=st.toggle("B-1 Absensi", True)
    with st.expander("⚡ 30분 단위 설정", expanded=False):
        sw_a4=st.toggle("A-4 Timestamp", True); sw_b3=st.toggle("B-3", True); sw_b4=st.toggle("B-4", True); sw_b5=st.toggle("B-5", True); sw_b9=st.toggle("B-9", True)
    with st.expander("⏰ 1시간 단위 설정", expanded=False):
        sw_a8=st.toggle("A-8 Cognitive", True); sw_b2=st.toggle("B-2", True); sw_b6=st.toggle("B-6", True); sw_b7=st.toggle("B-7", True); sw_b8=st.toggle("B-8", True); sw_b10=st.toggle("B-10", True)

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
        if sw_a1:
            st.markdown(f"**A1. {QC_CONTENT['A']['a1']['title']}**")
            p_a1 = st.pills("Time A1", ["Awal Masuk", "Setelah Istirahat"], selection_mode="multi", key="u_a1")
            ans_a1_1=st.text_input(f"1. {QC_CONTENT['A']['a1']['qs'][0]}", key="a1_1"); ans_a1_2=st.text_input(f"2. {QC_CONTENT['A']['a1']['qs'][1]}", key="a1_2"); st.divider()
        if sw_a3:
            st.markdown("**A3. Handover shift 전**")
            ans_a3_1=st.radio(f"-> {QC_CONTENT['A']['a3']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a3_1")
            m_a3_1=st.text_input("Memo A3", key="m_a3_1") if ans_a3_1=="No" else ""; st.divider()
        if sw_a7:
            st.markdown("**A7. Handover & rencana**")
            ans_a7_1=st.radio(f"-> {QC_CONTENT['A']['a7']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a7_1")
            n_a7_2=st.text_input("수령인 성함", key="n_a7_2") if ans_a7_1=="Yes" else ""; st.divider()
        st.markdown("##### 📦 Bahan Baku")
        if sw_a5:
            st.markdown(f"**A5. {QC_CONTENT['A']['a5']['title']}**")
            for desc in QC_CONTENT['A']['a5']['desc']: st.markdown(f"<span style='color:black;'>→ {desc}</span>", unsafe_allow_html=True)
            ans_a5=st.radio("A5 Status", ["Done", "Not done"], key="a5_st", label_visibility="collapsed", horizontal=True); st.divider()

    with colb:
        st.warning("🅱️ Check TL Reports")
        if sw_b1:
            st.markdown(f"**B1. {QC_CONTENT['B']['b1']['title']}**")
            t1, t2 = st.tabs(["🌅 Awal Masuk", "☕ Setelah Istirahat"])
            for t_lab, tab in [("Awal Masuk", t1), ("Setelah Istirahat", t2)]:
                with tab:
                    for ar in QC_CONTENT['B']['b1']['areas']:
                        st.markdown(f"**{ar} Absensi**")
                        r1, r2, r3 = st.columns([1.5, 1, 1])
                        with r1: st.session_state.b1_data[t_lab][ar]['jam']=st.text_input(f"Jam {ar} {t_lab}", key=f"b1_{t_lab}_{ar}_j")
                        with r2: st.session_state.b1_data[t_lab][ar]['pax']=st.text_input(f"Pax {ar} {t_lab}", key=f"b1_{t_lab}_{ar}_p")
                        with r3: st.session_state.b1_data[t_lab][ar]['st']=st.radio(f"S/T {ar} {t_lab}", ["O", "X"], key=f"b1_{t_lab}_{ar}_s", horizontal=True)

# [섹션 2: 30분 단위 - B 시리즈 고도화]
st.subheader("⚡ 30분 단위")
with st.container(border=True):
    cola, colb = st.columns(2)
    with cola:
        if sw_a4:
            st.markdown("**A4. Laporan QC di tablet**")
            for item in QC_CONTENT['A']['a4']['check_items']: st.markdown(f"<span style='color:black;'>→ {item}</span>", unsafe_allow_html=True)
            cols = st.columns(4)
            for i in range(16):
                with cols[i % 4]:
                    is_f = i < len(st.session_state.a4_ts)
                    txt = st.session_state.a4_ts[i] if is_f else str(i+1)
                    if is_f:
                        if st.button(txt, key=f"a4_{i}", type="secondary", use_container_width=True): confirm_cancel_dialog(i)
                    else:
                        if st.button(txt, key=f"a4_{i}", disabled=(i != len(st.session_state.a4_ts)), type="primary", use_container_width=True):
                            st.session_state.a4_ts.append(datetime.now(jakarta_tz).strftime("%H:%M")); st.rerun()
    with colb:
        for k in ["b3", "b4", "b5", "b9"]:
            if eval(f"sw_{k}"):
                info = QC_CONTENT['B'][k]
                st.markdown(f"**{k.upper()}. {info['title']}**")
                curr_log = st.session_state.b_logs[k]
                if len(curr_log) < info['steps']:
                    with st.expander(f"📌 Step {len(curr_log)+1} 입력", expanded=True):
                        res = {}
                        for q in info['qs']: res[q] = st.radio(f"→ {q}", ["O", "X"], key=f"{k}_q_{len(curr_log)}_{q}", horizontal=True)
                        memo = st.text_input("Memo/Respon (Jika X)", key=f"{k}_m_{len(curr_log)}")
                        if st.button(f"Confirm {k.upper()} Step {len(curr_log)+1}", key=f"btn_{k}"):
                            st.session_state.b_logs[k].append({"t": datetime.now(jakarta_tz).strftime("%H:%M"), "chk": res, "memo": memo}); st.rerun()
                for i, l in enumerate(curr_log): st.success(f"S{i+1} [{l['t']}] {list(l['chk'].values())} {l['memo']}")

# [섹션 3: 1시간 단위 - B 시리즈 고도화]
st.subheader("⏰ 1시간 단위")
with st.container(border=True):
    cola, colb = st.columns(2)
    with cola:
        if sw_a8:
            st.markdown("**A8. Status barang jatuh**")
            curr_a8 = len(st.session_state.a8_logs)
            if curr_a8 < 8:
                v1 = st.text_input(f"H{curr_a8+1}. Barang dibereskan? (Type 'YES')", key=f"a8_v1_{curr_a8}")
                if v1.strip().upper() == "YES":
                    if st.button(f"Confirm H{curr_a8+1}"):
                        st.session_state.a8_logs.append({"t": datetime.now(jakarta_tz).strftime("%H:%M")}); st.rerun()
            for i, l in enumerate(st.session_state.a8_logs): st.success(f"H{i+1} [{l['t']}] OK")
    with colb:
        for k in ["b2", "b6", "b7", "b8", "b10"]:
            if eval(f"sw_{k}"):
                info = QC_CONTENT['B'][k]
                st.markdown(f"**{k.upper()}. {info['title']}**")
                curr_log = st.session_state.b_logs[k]
                if len(curr_log) < info['steps']:
                    with st.expander(f"📌 Step {len(curr_log)+1} 입력", expanded=True):
                        res = {}
                        for q in info['qs']: res[q] = st.radio(f"→ {q}", ["O", "X"], key=f"{k}_q_{len(curr_log)}_{q}", horizontal=True)
                        memo = st.text_input("Memo/Respon (Jika X)", key=f"{k}_m_{len(curr_log)}")
                        if st.button(f"Confirm {k.upper()} Step {len(curr_log)+1}", key=f"btn_{k}"):
                            st.session_state.b_logs[k].append({"t": datetime.now(jakarta_tz).strftime("%H:%M"), "chk": res, "memo": memo}); st.rerun()
                for i, l in enumerate(curr_log): st.success(f"S{i+1} [{l['t']}] {list(l['chk'].values())} {l['memo']}")

# --- 6. [전면 개편] 텔레그램 상세 투사 엔진 (A + B 통합) ---
if st.button("💾 저장 및 텔레그램 전송", type="primary", use_container_width=True):
    try:
        tg_msg = f"🚀 *Laporan QC Lapangan*\n📅 {full_today} | {shift_label}\n👤 QC: {pelapor}\n"
        tg_msg += "--------------------------------\n\n"
        
        # [Routine Others]
        tg_msg += "📅 *Routine Others*\n"
        if sw_a1: tg_msg += f"• A-1. Stok BB: {ans_a1_1 if sw_a1 else '-'}\n"
        if sw_a7: tg_msg += f"• A-7. Penerima: {n_a7_2 if n_a7_2 else '-'}\n"

        # [B-1 Absensi 상세 투사]
        if sw_b1:
            tg_msg += "\n👥 *B-1. Laporan Absensi*\n"
            for tl in ["Awal Masuk", "Setelah Istirahat"]:
                tg_msg += f"  [{tl}]\n"
                for ar in QC_CONTENT['B']['b1']['areas']:
                    d = st.session_state.b1_data[tl][ar]
                    tg_msg += f"  - {ar}: {d['jam'] if d['jam'] else '00.00'} / {d['pax'] if d['pax'] else '0'} / ({d['st']})\n"

        # [B-2 to B-10 상세 투사]
        tg_msg += "\n🅱️ *Check TL Reports (Detail)*\n"
        for k in ["b2","b3","b4","b5","b6","b7","b8","b9","b10"]:
            if st.session_state.b_logs[k]:
                tg_msg += f"• {k.upper()}. {QC_CONTENT['B'][k]['title']}\n"
                for log in st.session_state.b_logs[k]:
                    checks = " / ".join([f"({v})" for v in log['chk'].values()])
                    tg_msg += f"  - {log['t']} / {checks}" + (f" / {log['memo']}" if log['memo'] else "") + "\n"
                tg_msg += "\n"

        tg_msg += f"🕒 *Update:* {datetime.now(jakarta_tz).strftime('%H:%M:%S')}"
        send_telegram(tg_msg); st.success("✅ 모든 상세 데이터가 텔레그램으로 전송되었습니다!")
    except Exception as e: st.error(f"에러: {e}")
