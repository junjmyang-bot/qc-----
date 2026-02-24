import streamlit as st
from datetime import datetime
import pytz 
import requests

# --- 1. 기본 설정 및 시간 (자카르타 기준) ---
st.set_page_config(page_title="SOI QC SMART SYSTEM", layout="wide", page_icon="🏭")
jakarta_tz = pytz.timezone('Asia/Jakarta')
now_jakarta = datetime.now(jakarta_tz)
today_str = now_jakarta.strftime('%Y-%m-%d')

TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]

# --- 2. [데이터 보존] 19개 전 항목 상세 가이드 및 질문 데이터 ---
QC_CONTENT = {
    "A": {
        "a1": {"title": "Cek Stok BB Sudah steam", "qs": ["Sisa BB sisa shift sebelumya?", "Jumlah bb steam 충분?", "Respon if kurang?"]},
        "a2": {"title": "Cek Stok BS (Sudah defros)", "qs": ["Sudah defros 얼마?", "Estimasi 작업량?", "Jam tambah defros?"]},
        "a3": {"title": "Handover shift 전", "qs": ["Sudah dapat handover?", "Produksi sesuai rencana?"]},
        "a7": {"title": "Handover & rencana", "qs": ["Rencana sudah dibuat?", "Handover sudah dibuat?", "Sudah baca data stok?"]},
        "a9": {"title": "SISA BARANG", "qs": ["Check MAX 1 PACK (Sudah check?)", "Sisa shift prev?", "Sudah dibereskan?", "Simpan sisa?", "Handover sisa?"]},
        "a4": {"title": "Laporan QC di tablet", "check_items": ["daily kebersihan", "kontaminan kupas", "kontaminan packing"]},
        "a5": {"title": "Status tes steam", "desc": ["maksimal jam 13.00 완료", "update laporan 30분 마다 보고", "cek sample & laporan update"]},
        "a6": {"title": "List BB butuh kirim", "qs": ["List kirim jam 12.00?", "Kordinasi gudang?"]},
        "a8": {"title": "Status barang jatuh", "areas": ["steam", "kupas", "dry", "packing", "cuci"]}
    },
    "B": {
        "b1": {"title": "Cek Laporan Absensi", "desc": ["Durasi 2 kali (Awal & Setelah Istirahat)", "Perubahan 인원 tak terduga 확인"], "areas": ["Steam", "Dry", "Kupas", "Packing"]},
        "b2": {"title": "Laporan Status steam", "steps": 8, "qs": ["laporan sesuai", "cara isi laporan benar"]},
        "b3": {"title": "Laporan Situasi kupas", "steps": 16, "qs": ["TL/petugas sudah update", "kroscek sudah benar?", "sudah kordinasi TL kupas-packing?", "laporan sesuai"]},
        "b4": {"title": "Laporan Situasi packing", "steps": 16, "qs": ["TL/petugas sudah update", "kroscek sudah benar?", "sudah kordinasi TL kupas-packing?", "laporan sesuai"]},
        "b5": {"title": "Hasil per jam kupas/packing", "steps": 16, "qs": ["laporan sesuai produk", "TL/petugas sudah update", "laporan sesuai"]},
        "b6": {"title": "Laporan Giling", "steps": 8, "qs": ["laporan sesuai 제품", "TL/petugas update", "laporan sesuai"]},
        "b7": {"title": "Laporan Giling - steril", "steps": 8, "qs": ["laporan sesuai 제품", "TL/petugas update", "laporan sesuai"]},
        "b8": {"title": "Laporan potong", "steps": 8, "qs": ["laporan sesuai 제품", "TL update", "cara nata benar?", "settingan mesin benar?", "laporan sesuai"]},
        "b9": {"title": "Laporan kondisi BB", "steps": 16, "qs": ["TL/petugas update", "laporan sesuai"]},
        "b10": {"title": "Laporan Dry", "steps": 8, "qs": ["TL/petugas update", "laporan sesuai", "status mesin 2회 체크(휴식 전/후)"]}
    }
}

# --- 3. 세션 상태 초기화 (에러 원천 차단) ---
B_KEYS = ["b2","b3","b4","b5","b6","b7","b8","b9","b10"]
if 'b_logs' not in st.session_state: st.session_state.b_logs = {k: [] for k in B_KEYS}
if 'a4_ts' not in st.session_state: st.session_state.a4_ts = []
if 'a8_logs' not in st.session_state: st.session_state.a8_logs = []
TARGET_LABELS = ["Awal Masuk", "Setelah Istirahat"]
if 'b1_data' not in st.session_state or list(st.session_state.b1_data.keys()) != TARGET_LABELS:
    st.session_state.b1_data = {t: {a: {"jam": "", "pax": "", "st": "O"} for a in QC_CONTENT['B']['b1']['areas']} for t in TARGET_LABELS}

def get_prog_bar(val_len, goal):
    perc = int((val_len/goal)*100) if goal > 0 else 0
    return f"{'■' * (perc // 10)}{'□' * (10 - (perc // 10))} ({perc}%)"

def send_telegram(text):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})

@st.dialog("Konfirmasi Pembatalan")
def confirm_cancel_dialog(key, idx):
    st.warning(f"Apakah Anda yakin ingin menghapus 기록?")
    if st.button("Ya, Hapus (확인)", type="primary", use_container_width=True):
        if key == "a4": st.session_state.a4_ts = st.session_state.a4_ts[:idx]
        elif key == "a8": st.session_state.a8_logs = st.session_state.a8_logs[:idx]
        else: st.session_state.b_logs[key] = st.session_state.b_logs[key][:idx]
        st.rerun()

# --- 4. 사이드바 설정 (범주형 정돈) ---
with st.sidebar:
    st.header("⚙️ 리포트 세부 설정")
    with st.expander("📅 시프트 루틴 설정", expanded=True):
        st.caption("🅰️ QC Routine (Others)")
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
    ca, cb = st.columns(2)
    with ca:
        st.info("🅰️ QC Direct Check")
        if sw_a1:
            st.markdown(f"**A1. {QC_CONTENT['A']['a1']['title']}**")
            p_a1 = st.pills("Time A1", ["Awal Masuk", "Setelah Istirahat"], selection_mode="multi", key="u_a1")
            ans_a1_1=st.text_input(f"1. {QC_CONTENT['A']['a1']['qs'][0]}", key="a1_1"); ans_a1_2=st.text_input(f"2. {QC_CONTENT['A']['a1']['qs'][1]}", key="a1_2"); st.divider()
        if sw_a7:
            st.markdown("**A7. Handover & rencana**")
            ans_a7_1=st.radio(f"-> {QC_CONTENT['A']['a7']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a7_1")
            ans_a7_3=st.text_area("Data Stok", key="a7_3"); st.divider()
        st.markdown("##### 📦 Bahan Baku")
        if "Shift 1" in shift_label: st.warning("⚠️ **Khusus Shift 1 Only**")
        if sw_a5:
            st.markdown(f"**A5. {QC_CONTENT['A']['a5']['title']}**")
            for item in QC_CONTENT['A']['a5']['desc']: st.markdown(f"<span style='color:black; font-weight:500;'>→ {item}</span>", unsafe_allow_html=True)
            ans_a5=st.radio("A5 Status", ["Done", "Not done"], key="a5_st", label_visibility="collapsed", horizontal=True); st.divider()
    with cb:
        st.warning("🅱️ Check TL Reports")
        if sw_b1:
            st.markdown(f"**B1. {QC_CONTENT['B']['b1']['title']}**")
            t1, t2 = st.tabs(["🌅 Awal Masuk", "☕ Setelah Istirahat"])
            for t_lab, tab in [("Awal Masuk", t1), ("Setelah Istirahat", t2)]:
                with tab:
                    for area in QC_CONTENT['B']['b1']['areas']:
                        st.markdown(f"**{area} Absensi**")
                        r1, r2, r3 = st.columns([1.5, 1, 1])
                        with r1: st.session_state.b1_data[t_lab][area]['jam']=st.text_input(f"Jam {area} {t_lab}", key=f"b1_{t_lab}_{area}_j")
                        with r2: st.session_state.b1_data[t_lab][area]['pax']=st.text_input(f"Pax {area} {t_lab}", key=f"b1_{t_lab}_{area}_p")
                        with r3: st.session_state.b1_data[t_lab][area]['st']=st.radio(f"S/T {area} {t_lab}", ["O", "X"], key=f"b1_{t_lab}_{area}_s", horizontal=True)

# [섹션 2: 30분 단위 - 숫자 그리드 + 내용 검증 통합]
st.subheader("⚡ 30분 단위")
with st.container(border=True):
    ca, cb = st.columns(2)
    with ca:
        if sw_a4:
            st.markdown("**A4. Laporan QC di tablet**")
            for item in QC_CONTENT['A']['a4']['check_items']: st.markdown(f"<span style='color:black; font-weight:500;'>→ {item}</span>", unsafe_allow_html=True)
            cols = st.columns(4)
            for i in range(16):
                with cols[i % 4]:
                    is_f = i < len(st.session_state.a4_ts)
                    txt = st.session_state.a4_ts[i] if is_f else str(i+1)
                    if st.button(txt, key=f"a4_{i}", type="secondary" if is_f else "primary", use_container_width=True, disabled=(not is_f and i != len(st.session_state.a4_ts))):
                        if is_f: confirm_cancel_dialog("a4", i)
                        else: st.session_state.a4_ts.append(datetime.now(jakarta_tz).strftime("%H:%M")); st.rerun()
    with cb:
        for k in ["b3", "b4", "b5", "b9"]:
            if eval(f"sw_{k}"):
                info = QC_CONTENT['B'][k]
                st.markdown(f"**{k.upper()}. {info['title']}**")
                for q_text in info['qs']: st.markdown(f"<span style='color:black; font-size:0.9rem;'>✓ {q_text}</span>", unsafe_allow_html=True)
                cols = st.columns(4)
                logs = st.session_state.b_logs[k]
                for i in range(16):
                    with cols[i % 4]:
                        is_f = i < len(logs)
                        txt = logs[i]['t'] if is_f else str(i+1)
                        if st.button(txt, key=f"btn_{k}_{i}", type="secondary" if is_f else "primary", use_container_width=True, disabled=(not is_f and i != len(logs))):
                            if is_f: confirm_cancel_dialog(k, i)
                            else: st.session_state[f"active_{k}"] = True; st.rerun()
                if st.session_state.get(f"active_{k}"):
                    with st.expander(f"📝 Step {len(logs)+1} 검증 입력", expanded=True):
                        res = {q: st.radio(f"→ {q}", ["O", "X"], key=f"q_{k}_{len(logs)}_{q}", horizontal=True) for q in info['qs']}
                        memo = st.text_input("Memo/Respon (Jika X)", key=f"m_{k}_{len(logs)}")
                        if st.button("Confirm & Save", key=f"sav_{k}"):
                            st.session_state.b_logs[k].append({"t": datetime.now(jakarta_tz).strftime("%H:%M"), "chk": res, "memo": memo})
                            del st.session_state[f"active_{k}"]; st.rerun()

# [섹션 3: 1시간 단위 - 숫자 그리드 + 내용 검증 통합]
st.subheader("⏰ 1시간 단위")
with st.container(border=True):
    ca, cb = st.columns(2)
    with ca:
        if sw_a8:
            st.markdown("**A8. Status barang jatuh**")
            cols = st.columns(4)
            for i in range(8):
                with cols[i % 4]:
                    is_f = i < len(st.session_state.a8_logs)
                    txt = st.session_state.a8_logs[i]['t'] if is_f else str(i+1)
                    if st.button(txt, key=f"a8_{i}", type="secondary" if is_f else "primary", use_container_width=True, disabled=(not is_f and i != len(st.session_state.a8_logs))):
                        if is_f: confirm_cancel_dialog("a8", i)
                        else: st.session_state.active_a8 = True; st.rerun()
            if st.session_state.get("active_a8"):
                with st.expander(f"🔔 Hour {len(st.session_state.a8_logs)+1} 인지 확인", expanded=True):
                    v1 = st.text_input("Barang dibereskan? (Type 'YES')", key="a8_v1")
                    if v1.strip().upper() == "YES" and st.button("Confirm Hour"):
                        st.session_state.a8_logs.append({"t": datetime.now(jakarta_tz).strftime("%H:%M")})
                        del st.session_state.active_a8; st.rerun()
    with cb:
        for k in ["b2", "b6", "b7", "b8", "b10"]:
            if eval(f"sw_{k}"):
                info = QC_CONTENT['B'][k]
                st.markdown(f"**{k.upper()}. {info['title']}**")
                for q_text in info['qs']: st.markdown(f"<span style='color:black; font-size:0.9rem;'>✓ {q_text}</span>", unsafe_allow_html=True)
                cols = st.columns(4)
                logs = st.session_state.b_logs[k]
                for i in range(8):
                    with cols[i % 4]:
                        is_f = i < len(logs)
                        txt = logs[i]['t'] if is_f else str(i+1)
                        if st.button(txt, key=f"btn_{k}_{i}", type="secondary" if is_f else "primary", use_container_width=True, disabled=(not is_f and i != len(logs))):
                            if is_f: confirm_cancel_dialog(k, i)
                            else: st.session_state[f"active_{k}"] = True; st.rerun()
                if st.session_state.get(f"active_{k}"):
                    with st.expander(f"📝 Step {len(logs)+1} 검증 입력", expanded=True):
                        res = {q: st.radio(f"→ {q}", ["O", "X"], key=f"q_{k}_{len(logs)}_{q}", horizontal=True) for q in info['qs']}
                        memo = st.text_input("Memo/Respon (Jika X)", key=f"m_{k}_{len(logs)}")
                        if st.button("Confirm & Save", key=f"sav_{k}"):
                            st.session_state.b_logs[k].append({"t": datetime.now(jakarta_tz).strftime("%H:%M"), "chk": res, "memo": memo})
                            del st.session_state[f"active_{k}"]; st.rerun()

main_memo = st.text_area("종합 특이사항 입력", key="main_memo_v")

# --- 6. 텔레그램 전송 엔진 (상세 투사) ---
if st.button("💾 저장 및 텔레그램 전송", type="primary", use_container_width=True):
    try:
        tg_msg = f"🚀 *Laporan QC Lapangan*\n📅 {today_str} | {shift_label}\n👤 QC: {pelapor}\n--------------------------------\n\n"
        if sw_b1:
            tg_msg += "👥 *B-1. Absensi (Detail)*\n"
            for tl in TARGET_LABELS:
                tg_msg += f"  [{tl}]\n"
                for ar in QC_CONTENT['B']['b1']['areas']:
                    d = st.session_state.b1_data[tl][ar]
                    tg_msg += f"  - {ar}: {d['jam'] if d['jam'] else '00.00'} / {d['pax'] if d['pax'] else '0'} / ({d['st']})\n"
        tg_msg += "\n🅱️ *Check TL Reports (Detail)*\n"
        for k in B_KEYS:
            if st.session_state.b_logs[k]:
                tg_msg += f"• {k.upper()}. {QC_CONTENT['B'][k]['title']}\n"
                for log in st.session_state.b_logs[k]:
                    res_str = " / ".join([f"({v})" for v in log['chk'].values()])
                    tg_msg += f"  - {log['t']} / {res_str}" + (f" / {log['memo']}" if log['memo'] else "") + "\n"
                tg_msg += "\n"
        send_telegram(tg_msg); st.success("✅ 상세 데이터 전송 완료!")
    except Exception as e: st.error(f"에러: {e}")
