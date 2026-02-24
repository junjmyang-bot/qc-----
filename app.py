import streamlit as st
from datetime import datetime
import pytz 
import requests

# --- 1. 기본 설정 및 시간 ---
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
        "a5": {"title": "Status tes steam", "desc": ["maksimal jam 13.00 완료", "update laporan 30분 마다 보고", "cek 샘플 & 보고서"]},
        "a6": {"title": "List BB butuh kirim", "qs": ["List kirim jam 12.00?", "Kordinasi gudang?"]},
        "a8": {"title": "Status barang jatuh", "areas": ["steam", "kupas", "dry", "packing", "cuci"]}
    },
    "B": {
        "b1": {"title": "Cek Laporan Absensi", "desc": ["Durasi 2 kali (Awal & Setelah Istirahat)", "인원 변동 확인"], "areas": ["Steam", "Dry", "Kupas", "Packing"]},
        "b2": {"title": "Laporan Status steam", "qs": ["laporan sesuai", "cara isi laporan benar"]},
        "b3": {"title": "Laporan Situasi kupas", "qs": ["TL 이미 update 완료?", "kroscek 결과 이상무?", "TL kordinasi?", "laporan 내용 일치?"]},
        "b4": {"title": "Laporan Situasi packing", "qs": ["TL 이미 update 완료?", "kroscek 결과 이상무?", "TL kordinasi?", "laporan 내용 일치?"]},
        "b5": {"title": "Hasil per jam kupas/packing", "qs": ["produk 일치 확인", "TL update 여부", "laporan 내용 일치?"]},
        "b6": {"title": "Laporan Giling", "qs": ["produk 일치 확인", "TL update 여부", "laporan 내용 일치?"]},
        "b7": {"title": "Laporan Giling - steril", "qs": ["produk 일치 확인", "TL update 여부", "laporan 내용 일치?"]},
        "b8": {"title": "Laporan potong", "qs": ["produk 일치 확인", "TL update", "cara nata benar?", "settingan mesin benar?", "laporan 내용 일치?"]},
        "b9": {"title": "Laporan kondisi BB", "qs": ["TL update 여부", "laporan 내용 일치?"]},
        "b10": {"title": "Laporan Dry", "qs": ["TL update 여부", "laporan 내용 일치?", "status mesin 2회 체크?"]}
    }
}

# --- 3. 세션 상태 초기화 ---
B_KEYS = ["b2","b3","b4","b5","b6","b7","b8","b9","b10"]
GRID_KEYS = ["a4", "a8"] + B_KEYS

if 'b_logs' not in st.session_state: st.session_state.b_logs = {k: [] for k in B_KEYS}
if 'a4_ts' not in st.session_state: st.session_state.a4_ts = []
if 'a8_logs' not in st.session_state: st.session_state.a8_logs = []
if 'targets' not in st.session_state: st.session_state.targets = {k: 0 for k in GRID_KEYS}
if 'b1_data' not in st.session_state:
    st.session_state.b1_data = {t: {a: {"jam": "", "pax": "", "st": "O"} for a in QC_CONTENT['B']['b1']['areas']} for t in ["Awal Masuk", "Setelah Istirahat"]}

def get_prog_bar(val_len, goal):
    perc = int((val_len/goal)*100) if goal > 0 else 0
    return f"{'■' * (perc // 10)}{'□' * (10 - (perc // 10))} ({perc}%)"

def send_telegram(text):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})

@st.dialog("Konfirmasi Pembatalan")
def confirm_cancel_dialog(key, idx):
    st.warning("Apakah Anda yakin ingin menghapus 기록?")
    if st.button("Ya, Hapus (확인)", type="primary", use_container_width=True):
        if key == "a4": st.session_state.a4_ts = st.session_state.a4_ts[:idx]
        elif key == "a8": st.session_state.a8_logs = st.session_state.a8_logs[:idx]
        else: st.session_state.b_logs[key] = st.session_state.b_logs[key][:idx]
        st.rerun()

# --- 4. 사이드바 설정 (토글 + 매뉴얼 횟수 입력 통합) ---
with st.sidebar:
    st.header("⚙️ 리포트 세부 설정")
    
    with st.expander("📅 시프트 루틴 노출 설정", expanded=True):
        sw_a1=st.toggle(f"A-1 {QC_CONTENT['A']['a1']['title']}", True)
        sw_a2=st.toggle(f"A-2 {QC_CONTENT['A']['a2']['title']}", True)
        sw_a3=st.toggle("A-3 Handover In", True)
        sw_a7=st.toggle("A-7 Rencana Prod", True)
        sw_a9=st.toggle("A-9 Sisa Barang", True)
        st.divider(); st.info("📦 Bahan Baku")
        sw_a5=st.toggle(f"A-5 {QC_CONTENT['A']['a5']['title']}", True)
        sw_a6=st.toggle("A-6 List BB", True)
        st.divider(); st.caption("🅱️ Check TL Reports")
        sw_b1=st.toggle("B-1 Absensi", True)

    # [수정] 토글을 끄면 메인에서도 사라지게 변수 생성
    with st.expander("⚡ 30분 단위 설정 (토글 & 목표)", expanded=False):
        sw_a4=st.toggle(f"A-4 {QC_CONTENT['A']['a4']['title']}", True)
        if sw_a4: st.session_state.targets['a4'] = st.number_input("A-4 목표 횟수", 0, 48, st.session_state.targets['a4'], key="inp_a4")
        st.divider()
        sw_b3=st.toggle("B-3 Situasi Kupas", True)
        if sw_b3: st.session_state.targets['b3'] = st.number_input("B-3 목표 횟수", 0, 48, st.session_state.targets['b3'], key="inp_b3")
        sw_b4=st.toggle("B-4 Situasi Packing", True)
        if sw_b4: st.session_state.targets['b4'] = st.number_input("B-4 목표 횟수", 0, 48, st.session_state.targets['b4'], key="inp_b4")
        sw_b5=st.toggle("B-5 Hasil Per Jam", True)
        if sw_b5: st.session_state.targets['b5'] = st.number_input("B-5 목표 횟수", 0, 48, st.session_state.targets['b5'], key="inp_b5")
        sw_b9=st.toggle("B-9 Kondisi BB", True)
        if sw_b9: st.session_state.targets['b9'] = st.number_input("B-9 목표 횟수", 0, 48, st.session_state.targets['b9'], key="inp_b9")

    with st.expander("⏰ 1시간 단위 설정 (토글 & 목표)", expanded=False):
        sw_a8=st.toggle(f"A-8 {QC_CONTENT['A']['a8']['title']}", True)
        if sw_a8: st.session_state.targets['a8'] = st.number_input("A-8 목표 횟수", 0, 24, st.session_state.targets['a8'], key="inp_a8")
        st.divider()
        sw_b2=st.toggle("B-2 Status Steam", True)
        if sw_b2: st.session_state.targets['b2'] = st.number_input("B-2 목표 횟수", 0, 24, st.session_state.targets['b2'], key="inp_b2")
        sw_b6=st.toggle("B-6 Laporan Giling", True)
        if sw_b6: st.session_state.targets['b6'] = st.number_input("B-6 목표 횟수", 0, 24, st.session_state.targets['b6'], key="inp_b6")
        sw_b7=st.toggle("B-7 Laporan Giling-Steril", True)
        if sw_b7: st.session_state.targets['b7'] = st.number_input("B-7 목표 횟수", 0, 24, st.session_state.targets['b7'], key="inp_b7")
        sw_b8=st.toggle("B-8 Laporan Potong", True)
        if sw_b8: st.session_state.targets['b8'] = st.number_input("B-8 목표 횟수", 0, 24, st.session_state.targets['b8'], key="inp_b8")
        sw_b10=st.toggle("B-10 Laporan Dry", True)
        if sw_b10: st.session_state.targets['b10'] = st.number_input("B-10 목표 횟수", 0, 24, st.session_state.targets['b10'], key="inp_b10")

# --- 5. 메인 UI (A/B 리포트 클리어한 분리) ---
st.title("🏭 SOI QC 모니터링 시스템")
c1, c2 = st.columns(2)
with c1: shift_label = st.selectbox("SHIFT", ["Shift 1 (Pagi)", "Shift 2 (Sore)", "Shift tengah"])
with c2: pelapor = st.selectbox("담당자", ["Diana", "Uyun", "Rossa", "Dini", "JUNMO YANG"])

# [섹션 1: 시프트 루틴]
st.subheader("📅 시프트 루틴")
with st.container(border=True):
    cola, colb = st.columns(2)
    with cola: # (A-Routine)
        if sw_a1:
            st.markdown(f"**A1. {QC_CONTENT['A']['a1']['title']}**")
            p_a1 = st.pills("Time A1", ["Awal Masuk", "Setelah Istirahat"], selection_mode="multi", key="u_a1")
            ans_a1_1=st.text_input(f"1. {QC_CONTENT['A']['a1']['qs'][0]}", key="a1_1"); ans_a1_2=st.text_input(f"2. {QC_CONTENT['A']['a1']['qs'][1]}", key="a1_2"); st.divider()
        if sw_a7:
            st.markdown("**A7. Handover & rencana**")
            ans_a7_1=st.radio(f"-> {QC_CONTENT['A']['a7']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a7_1")
            ans_a7_3=st.text_area("Data Stok", key="a7_3"); st.divider()
        if sw_a5:
            st.markdown(f"**A5. {QC_CONTENT['A']['a5']['title']}**")
            for item in QC_CONTENT['A']['a5']['desc']: st.markdown(f"<span style='color:black; font-weight:500;'>→ {item}</span>", unsafe_allow_html=True)
            ans_a5=st.radio("A5 Status", ["Done", "Not done"], key="a5_st", label_visibility="collapsed", horizontal=True); st.divider()
    with colb: # (B-Routine)
        if sw_b1:
            st.markdown(f"**B1. {QC_CONTENT['B']['b1']['title']}**")
            t1, t2 = st.tabs(["🌅 Awal Masuk", "☕ Setelah Istirahat"])
            for t_lab, tab in [("Awal Masuk", t1), ("Setelah Istirahat", t2)]:
                with tab:
                    for area in QC_CONTENT['B']['b1']['areas']:
                        r1, r2, r3 = st.columns([1.5, 1, 1])
                        with r1: st.session_state.b1_data[t_lab][area]['jam']=st.text_input(f"Jam {area} {t_lab}", key=f"b1_{t_lab}_{area}_j")
                        with r2: st.session_state.b1_data[t_lab][area]['pax']=st.text_input(f"Pax {area} {t_lab}", key=f"b1_{t_lab}_{area}_p")
                        with r3: st.session_state.b1_data[t_lab][area]['st']=st.radio(f"S/T {area} {t_lab}", ["O", "X"], key=f"b1_{t_lab}_{area}_s", horizontal=True)

# [섹션 2/3: A리포트(왼쪽) vs B리포트(오른쪽) 클리어 분리]
for title, keys, a_keys, b_keys in [("⚡ 30분 단위", ["a4","b3","b4","b5","b9"], ["a4"], ["b3","b4","b5","b9"]), 
                                  ("⏰ 1시간 단위", ["a8","b2","b6","b7","b8","b10"], ["a8"], ["b2","b6","b7","b8","b10"])]:
    st.subheader(title)
    with st.container(border=True):
        ca, cb = st.columns(2)
        with ca:
            st.info("🅰️ QC Direct Check")
            for k in a_keys:
                if globals().get(f"sw_{k}", True) and st.session_state.targets[k] > 0:
                    info = QC_CONTENT['A'][k]
                    st.markdown(f"**{k.upper()}. {info['title']}** (목표: {st.session_state.targets[k]}회)")
                    if 'check_items' in info:
                        for i_ in info['check_items']: st.markdown(f"<span style='color:black; font-weight:500;'>→ {i_}</span>", unsafe_allow_html=True)
                    cols = st.columns(4)
                    for i in range(st.session_state.targets[k]):
                        with cols[i % 4]:
                            is_f = (i < len(st.session_state.a4_ts)) if k=="a4" else (i < len(st.session_state.a8_logs))
                            txt = (st.session_state.a4_ts[i] if k=="a4" else st.session_state.a8_logs[i]['t']) if is_f else str(i+1)
                            if st.button(txt, key=f"btn_{k}_{i}", type="secondary" if is_f else "primary", use_container_width=True, disabled=(not is_f and i != (len(st.session_state.a4_ts) if k=="a4" else len(st.session_state.a8_logs)))):
                                if is_f: confirm_cancel_dialog(k, i)
                                else:
                                    if k=="a4": st.session_state.a4_ts.append(datetime.now(jakarta_tz).strftime("%H:%M"))
                                    else: st.session_state.active_a8 = True
                                    st.rerun()
                    if k == "a8" and st.session_state.get("active_a8"):
                        with st.expander("🔔 Hour 확인", expanded=True):
                            if st.text_input("Barang dibereskan? ('YES')", key="a8_v").strip().upper() == "YES" and st.button("Confirm"):
                                st.session_state.a8_logs.append({"t": datetime.now(jakarta_tz).strftime("%H:%M")})
                                del st.session_state.active_a8; st.rerun()
        with cb:
            st.warning("🅱️ Check TL Reports")
            for k in b_keys:
                if globals().get(f"sw_{k}", True) and st.session_state.targets[k] > 0:
                    info = QC_CONTENT['B'][k]
                    st.markdown(f"**{k.upper()}. {info['title']}**")
                    for q_ in info['qs']: st.markdown(f"<span style='color:black; font-size:0.8rem;'>✓ {q_}</span>", unsafe_allow_html=True)
                    cols = st.columns(4)
                    logs = st.session_state.b_logs[k]
                    for i in range(st.session_state.targets[k]):
                        with cols[i % 4]:
                            is_f = i < len(logs)
                            if st.button(logs[i]['t'] if is_f else str(i+1), key=f"btn_{k}_{i}", type="secondary" if is_f else "primary", use_container_width=True, disabled=(not is_f and i != len(logs))):
                                if is_f: confirm_cancel_dialog(k, i)
                                else: st.session_state[f"active_{k}"] = True; st.rerun()
                    if st.session_state.get(f"active_{k}"):
                        with st.expander(f"📝 {k.upper()} Step {len(logs)+1} 검증", expanded=True):
                            res = {q: st.radio(f"→ {q}", ["O", "X"], key=f"q_{k}_{len(logs)}_{q}", horizontal=True) for q in info['qs']}
                            memo = st.text_input("Memo/Respon", key=f"m_{k}_{len(logs)}")
                            if st.button("Confirm & Save", key=f"sav_{k}"):
                                st.session_state.b_logs[k].append({"t": datetime.now(jakarta_tz).strftime("%H:%M"), "chk": res, "memo": memo})
                                del st.session_state[f"active_{k}"]; st.rerun()

main_memo = st.text_area("종합 특이사항 입력", key="main_memo_v")

# --- 6. 텔레그램 상세 전송 엔진 (진행률 포함) ---
if st.button("💾 저장 및 텔레그램 전송", type="primary", use_container_width=True):
    try:
        tg_msg = f"🚀 *Laporan QC Lapangan*\n📅 {today_str} | {shift_label}\n👤 QC: {pelapor}\n--------------------------------\n\n"
        # (B-1 및 B-2~10 상세 투사 로직 유지...)
        tg_msg += "🅱️ *Check TL Reports (Detail)*\n"
        for k in B_KEYS:
            target = st.session_state.targets[k]
            if globals().get(f"sw_{k}", True) and target > 0:
                logs = st.session_state.b_logs[k]
                tg_msg += f"• {k.upper()}. {QC_CONTENT['B'][k]['title']}\n  └ {get_prog_bar(len(logs), target)} ({len(logs)}/{target})\n"
        send_telegram(tg_msg); st.success("✅ 상세 데이터 전송 완료!")
    except Exception as e: st.error(f"에러: {e}")
