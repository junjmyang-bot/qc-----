import streamlit as st
from datetime import datetime
import gspread
import json
import pytz 
import requests
from google.oauth2.service_account import Credentials

# --- 1. Konfigurasi Dasar & Waktu (WIB) ---
st.set_page_config(page_title="SOI QC SMART SYSTEM", layout="wide", page_icon="🏭")
jakarta_tz = pytz.timezone('Asia/Jakarta')
now_jakarta = datetime.now(jakarta_tz)
today_str = now_jakarta.strftime('%m-%d')
full_today = now_jakarta.strftime('%Y-%m-%d')
current_time_full = now_jakarta.strftime('%H:%M:%S')

st.markdown("<style>div[data-testid='stStatusWidget']{display:none!important;}.main{background-color:white!important;}</style>", unsafe_allow_html=True)

TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]

# 🌟 Engine Google Sheets (Koneksi Sheet)
@st.cache_resource
def get_gc_client():
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        raw_json = st.secrets["gcp_service_account"]
        info = json.loads(raw_json, strict=False) if isinstance(raw_json, str) else raw_json
        return gspread.authorize(Credentials.from_service_account_info(info, scopes=scopes))
    except Exception as e:
        st.error(f"🚨 Koneksi Sheet Gagal: {e}"); return None

gc = get_gc_client()

# --- 2. [Data Konten] Panduan Detail 19 Item (현지화 완료) ---
QC_CONTENT = {
    "A": {
        "a1": {"title": "Cek Stok BB Sudah steam", "qs": ["Sisa BB sisa shift sebelumnya?", "Jumlah bb steam cukup?", "Respon jika kurang?"]},
        "a2": {"title": "Cek Stok BS (Sudah defros)", "qs": ["Sudah defros berapa?", "Estimasi jumlah kerja?", "Jam tambah defros?"]},
        "a3": {"title": "Handover shift Masuk", "qs": ["Sudah dapat handover?", "Produksi sesuai rencana?"]},
        "a7": {"title": "Handover & rencana", "qs": ["Rencana sudah dibuat?", "Handover sudah dibuat?", "Sudah baca data stok?"]},
        "a9": {"title": "SISA BARANG", "qs": ["Check MAX 1 PACK (Sudah check?)", "Sisa shift prev?", "Sudah dibereskan?", "Simpan sisa?", "Handover sisa?"]},
        "a4": {"title": "Laporan QC pada Tablet", "check_items": ["Kebersihan harian", "Kontaminan kupas", "Kontaminan packing"]},
        "a5": {"title": "Status Tes Steam", "desc": ["Maksimal selesai jam 13.00", "Update laporan setiap 30 menit", "Cek sampel & update laporan"]},
        "a6": {"title": "List BB butuh kirim", "qs": ["List kirim jam 12.00 sudah ada?", "Kordinasi gudang?"]},
        "a8": {"title": "Status Barang Jatuh", "areas": ["Steam Area", "Kupas Area", "Dry Area", "Packing Area", "Cuci Area"]}
    },
    "B": {
        "b1": {"title": "Cek Laporan Absensi", "desc": ["Durasi 2 kali (Awal & Setelah Istirahat)", "Cek perubahan jumlah orang"], "areas": ["Steam", "Dry", "Kupas", "Packing"]},
        "b2": {"title": "Laporan Status steam", "qs": ["Laporan sesuai", "Cara isi laporan benar"]},
        "b3": {"title": "Laporan Situasi kupas", "qs": ["TL sudah update?", "Kroscek benar?", "Kordinasi TL kupas-packing?", "Laporan sesuai?"]},
        "b4": {"title": "Laporan Situasi packing", "qs": ["TL sudah update?", "Kroscek benar?", "Kordinasi TL kupas-packing?", "Laporan sesuai?"]},
        "b5": {"title": "Hasil per jam kupas/packing", "qs": ["Produk sesuai", "TL sudah update", "Laporan sesuai"]},
        "b6": {"title": "Laporan Giling", "qs": ["Produk sesuai", "TL sudah update", "Laporan sesuai"]},
        "b7": {"title": "Laporan Giling - steril", "qs": ["Produk sesuai", "TL sudah update", "Laporan sesuai"]},
        "b8": {"title": "Laporan potong", "qs": ["Produk sesuai", "TL update", "Cara nata benar?", "Settingan mesin benar?", "Laporan sesuai"]},
        "b9": {"title": "Laporan kondisi BB", "qs": ["TL update", "Laporan sesuai"]},
        "b10": {"title": "Laporan Dry", "qs": ["TL update", "Laporan sesuai", "Status mesin 2 kali"]}
    }
}

# --- 3. Inisialisasi Session State ---
B_KEYS = ["b2","b3","b4","b5","b6","b7","b8","b9","b10"]
GRID_KEYS = ["a4", "a8"] + B_KEYS

if 'b_logs' not in st.session_state: st.session_state.b_logs = {k: [] for k in B_KEYS}
if 'a4_ts' not in st.session_state: st.session_state.a4_ts = []
if 'a8_logs' not in st.session_state: st.session_state.a8_logs = []
if 'targets' not in st.session_state: st.session_state.targets = {k: 0 for k in GRID_KEYS}
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
    st.warning("Apakah Anda yakin ingin menghapus record ini?")
    if st.button("Ya, Hapus", type="primary", use_container_width=True):
        if key == "a4": st.session_state.a4_ts = st.session_state.a4_ts[:idx]
        elif key == "a8": st.session_state.a8_logs = st.session_state.a8_logs[:idx]
        else: st.session_state.b_logs[key] = st.session_state.b_logs[key][:idx]
        st.rerun()

# --- 4. Sidebar: Pengaturan Detail (현지화 완료) ---
with st.sidebar:
    st.header("⚙️ Pengaturan Laporan")
    with st.expander("📅 Visibilitas Rutinitas Shift", expanded=True):
        sw_a1=st.toggle(f"A-1 {QC_CONTENT['A']['a1']['title']}", True); sw_a2=st.toggle(f"A-2 {QC_CONTENT['A']['a2']['title']}", True)
        sw_a3=st.toggle("A-3 Handover Masuk", True); sw_a7=st.toggle("A-7 Rencana & Handover", True); sw_a9=st.toggle("A-9 Sisa Barang", True)
        st.divider(); sw_a5=st.toggle(f"A-5 {QC_CONTENT['A']['a5']['title']}", True); sw_a6=st.toggle("A-6 List Kirim BB", True)
        st.divider(); sw_b1=st.toggle("B-1 Absensi Laporan", True)

    with st.expander("⚡ Target Interval 30 Menit", expanded=False):
        for k in ["a4", "b3", "b4", "b5", "b9"]:
            info = QC_CONTENT['A' if 'a' in k else 'B'][k]
            st.session_state[f"sw_{k}"] = st.toggle(f"{k.upper()} {info['title']}", True, key=f"tog_{k}")
            if st.session_state[f"sw_{k}"]:
                st.session_state.targets[k] = st.number_input(f"Target {k.upper()}", 0, 48, st.session_state.targets[k], key=f"inp_{k}")

    with st.expander("⏰ Target Interval 1 Jam", expanded=False):
        for k in ["a8", "b2", "b6", "b7", "b8", "b10"]:
            info = QC_CONTENT['A' if 'a' in k else 'B'][k]
            st.session_state[f"sw_{k}"] = st.toggle(f"{k.upper()} {info['title']}", True, key=f"tog_{k}")
            if st.session_state[f"sw_{k}"]:
                st.session_state.targets[k] = st.number_input(f"Target {k.upper()}", 0, 48, st.session_state.targets[k], key=f"inp_{k}")

# --- 5. Main UI (Pemisahan Seksi) ---
st.title("🏭 SOI QC MONITORING SYSTEM")
ch1, ch2 = st.columns(2)
with ch1: shift_label = st.selectbox("SHIFT", ["Shift 1 (Pagi)", "Shift 2 (Sore)", "Shift Tengah"])
with ch2: pelapor = st.selectbox("Penanggung Jawab", ["Diana", "Uyun", "Rossa", "Dini", "JUNMO YANG"])

st.subheader("📅 Rutinitas Shift")
with st.container(border=True):
    ca, cb = st.columns(2)
    with ca:
        st.info("🅰️ QC Direct Check")
        if sw_a1:
            st.markdown(f"**A1. {QC_CONTENT['A']['a1']['title']}**")
            st.pills("Waktu Cek A1", TARGET_LABELS, selection_mode="multi", key="p_a1")
            st.text_input(f"1. {QC_CONTENT['A']['a1']['qs'][0]}", key="ans_a1_1")
            st.text_input(f"2. {QC_CONTENT['A']['a1']['qs'][1]}", key="ans_a1_2")
            st.text_input(f"3. {QC_CONTENT['A']['a1']['qs'][2]}", key="ans_a1_3"); st.divider()
        if sw_a2:
            st.markdown(f"**A2. {QC_CONTENT['A']['a2']['title']}**")
            st.pills("Waktu Cek A2", TARGET_LABELS, selection_mode="multi", key="p_a2")
            st.text_input(f"1. {QC_CONTENT['A']['a2']['qs'][0]}", key="ans_a2_1")
            st.text_input(f"2. {QC_CONTENT['A']['a2']['qs'][1]}", key="ans_a2_2")
            st.text_input(f"3. {QC_CONTENT['A']['a2']['qs'][2]}", key="ans_a2_3"); st.divider()
        if sw_a3:
            st.markdown(f"**A3. {QC_CONTENT['A']['a3']['title']}**")
            st.radio(f"1. {QC_CONTENT['A']['a3']['qs'][0]}", ["Yes", "No"], horizontal=True, key="ans_a3_1")
            st.radio(f"2. {QC_CONTENT['A']['a3']['qs'][1]}", ["Yes", "No"], horizontal=True, key="ans_a3_2"); st.divider()
        if sw_a7:
            st.markdown(f"**A7. {QC_CONTENT['A']['a7']['title']}**")
            st.radio(f"1. {QC_CONTENT['A']['a7']['qs'][0]}", ["Yes", "No"], horizontal=True, key="ans_a7_1")
            st.radio(f"2. {QC_CONTENT['A']['a7']['qs'][1]}", ["Yes", "No"], horizontal=True, key="ans_a7_2")
            st.text_input("Nama Penerima Handover (Jika Ya)", key="ans_a7_name")
            st.text_input(f"3. {QC_CONTENT['A']['a7']['qs'][2]}", key="ans_a7_3"); st.divider()
        if sw_a9:
            st.markdown(f"**A9. {QC_CONTENT['A']['a9']['title']}**")
            st.radio(f"1. {QC_CONTENT['A']['a9']['qs'][0]}", ["Sudah check", "Belum"], horizontal=True, key="ans_a9_1")
            st.text_input(f"2. {QC_CONTENT['A']['a9']['qs'][1]}", key="ans_a9_2")
            st.text_input(f"3. {QC_CONTENT['A']['a9']['qs'][2]}", key="ans_a9_3")
            st.text_input(f"4. {QC_CONTENT['A']['a9']['qs'][3]}", key="ans_a9_4")
            st.text_input(f"5. {QC_CONTENT['A']['a9']['qs'][4]}", key="ans_a9_5"); st.divider()
        if sw_a5:
            st.markdown(f"**A5. {QC_CONTENT['A']['a5']['title']}**")
            for it in QC_CONTENT['A']['a5']['desc']: st.markdown(f"<span style='color:black;'>→ {it}</span>", unsafe_allow_html=True)
            st.radio("Status A5", ["Done", "Not done"], key="ans_a5", horizontal=True, label_visibility="collapsed"); st.divider()
        if sw_a6:
            st.markdown(f"**A6. {QC_CONTENT['A']['a6']['title']}**")
            st.radio(f"1. {QC_CONTENT['A']['a6']['qs'][0]}", ["Yes", "No"], horizontal=True, key="ans_a6_1")
            st.radio(f"2. {QC_CONTENT['A']['a6']['qs'][1]}", ["Yes", "No"], horizontal=True, key="ans_a6_2")
    with cb:
        st.warning("🅱️ Check TL Reports")
        if sw_b1:
            st.markdown(f"**B1. {QC_CONTENT['B']['b1']['title']}**")
            t1, t2 = st.tabs(["🌅 Awal Masuk", "☕ Setelah Istirahat"])
            for tl, tab in [("Awal Masuk", t1), ("Setelah Istirahat", t2)]:
                with tab:
                    for ar in QC_CONTENT['B']['b1']['areas']:
                        r1, r2, r3 = st.columns([1.5, 1, 1])
                        with r1: st.session_state.b1_data[tl][ar]['jam']=st.text_input(f"Jam {ar} {tl}", key=f"inp_{tl}_{ar}_j")
                        with r2: st.session_state.b1_data[tl][ar]['pax']=st.text_input(f"Pax {ar} {tl}", key=f"inp_{tl}_{ar}_p")
                        with r3: st.session_state.b1_data[tl][ar]['st']=st.radio(f"S/T {ar} {tl}", ["O", "X"], key=f"inp_{tl}_{ar}_s", horizontal=True)

# [섹션 2: 30분 단위]
st.subheader("⚡ Interval 30 Menit")
with st.container(border=True):
    ca, cb = st.columns(2)
    with ca:
        st.info("🅰️ QC Direct Check")
        if st.session_state.get("sw_a4") and st.session_state.targets['a4'] > 0:
            st.markdown(f"**A4. {QC_CONTENT['A']['a4']['title']}**")
            for it in QC_CONTENT['A']['a4']['check_items']: st.markdown(f"<span style='color:black;'>→ {it}</span>", unsafe_allow_html=True)
            cols = st.columns(4)
            for i in range(st.session_state.targets['a4']):
                with cols[i % 4]:
                    is_f = i < len(st.session_state.a4_ts)
                    txt = st.session_state.a4_ts[i] if is_f else str(i+1)
                    if st.button(txt, key=f"btn_a4_{i}", type="secondary" if is_f else "primary", use_container_width=True):
                        if is_f: confirm_cancel_dialog("a4", i)
                        else: st.session_state.a4_ts.append(datetime.now(jakarta_tz).strftime("%H:%M")); st.rerun()
    with cb:
        st.warning("🅱️ Check TL Reports")
        for k in ["b3","b4","b5","b9"]:
            if st.session_state.get(f"sw_{k}") and st.session_state.targets[k] > 0:
                st.markdown(f"**{k.upper()}. {QC_CONTENT['B'][k]['title']}**")
                for q_ in QC_CONTENT['B'][k]['qs']: st.markdown(f"<span style='color:black; font-size:0.85rem;'>✓ {q_}</span>", unsafe_allow_html=True)
                cols = st.columns(4); logs = st.session_state.b_logs[k]
                for i in range(st.session_state.targets[k]):
                    with cols[i % 4]:
                        is_f = i < len(logs)
                        if st.button(logs[i]['t'] if is_f else str(i+1), key=f"btn_{k}_{i}", type="secondary" if is_f else "primary", use_container_width=True):
                            if is_f: confirm_cancel_dialog(k, i)
                            else: st.session_state[f"active_{k}"] = True; st.rerun()
                if st.session_state.get(f"active_{k}"):
                    with st.expander(f"Verifikasi {k.upper()} Step {len(logs)+1}", expanded=True):
                        res = {q: st.radio(f"→ {q}", ["O", "X"], key=f"q_{k}_{len(logs)}_{q}", horizontal=True) for q in QC_CONTENT['B'][k]['qs']}
                        memo = st.text_input("Catatan / Respon (Jika X)", key=f"m_{k}_{len(logs)}")
                        if st.button("Simpan Data", key=f"sv_{k}"):
                            st.session_state.b_logs[k].append({"t": datetime.now(jakarta_tz).strftime("%H:%M"), "chk": res, "memo": memo})
                            del st.session_state[f"active_{k}"]; st.rerun()
                st.divider()

# [섹션 3: 1시간 단위]
st.subheader("⏰ Interval 1 Jam")
with st.container(border=True):
    ca, cb = st.columns(2)
    with ca:
        st.info("🅰️ QC Direct Check")
        if st.session_state.get("sw_a8") and st.session_state.targets['a8'] > 0:
            st.markdown(f"**A8. {QC_CONTENT['A']['a8']['title']}**")
            cols = st.columns(4)
            for i in range(st.session_state.targets['a8']):
                with cols[i % 4]:
                    is_f = i < len(st.session_state.a8_logs)
                    txt = st.session_state.a8_logs[i]['t'] if is_f else str(i+1)
                    if st.button(txt, key=f"btn_a8_{i}", type="secondary" if is_f else "primary", use_container_width=True):
                        if is_f: confirm_cancel_dialog("a8", i)
                        else: st.session_state.active_a8 = True; st.rerun()
            if st.session_state.get("active_a8"):
                with st.expander(f"📝 Periksa Hour {len(st.session_state.a8_logs)+1}", expanded=True):
                    st.info("Periksa kondisi barang jatuh di setiap area (O: Aman / X: Butuh Tindakan)")
                    a8_res = {ar: st.radio(f"→ {ar}", ["O", "X"], key=f"a8_{len(st.session_state.a8_logs)}_{ar}", horizontal=True) for ar in QC_CONTENT['A']['a8']['areas']}
                    v_a8 = st.text_input("Barang segera dibereskan? (Ketik 'YES' untuk konfirmasi)", key="v_a8_inp")
                    if v_a8.strip().upper() == "YES" and st.button("Konfirmasi & Simpan A8"):
                        st.session_state.a8_logs.append({"t": datetime.now(jakarta_tz).strftime("%H:%M"), "res": a8_res})
                        del st.session_state.active_a8; st.rerun()
    with cb:
        st.warning("🅱️ Check TL Reports")
        for k in ["b2","b6","b7","b8","b10"]:
            if st.session_state.get(f"sw_{k}") and st.session_state.targets[k] > 0:
                st.markdown(f"**{k.upper()}. {QC_CONTENT['B'][k]['title']}**")
                for q_ in QC_CONTENT['B'][k]['qs']: st.markdown(f"<span style='color:black; font-size:0.85rem;'>✓ {q_}</span>", unsafe_allow_html=True)
                cols = st.columns(4); logs = st.session_state.b_logs[k]
                for i in range(st.session_state.targets[k]):
                    with cols[i % 4]:
                        is_f = i < len(logs)
                        if st.button(logs[i]['t'] if is_f else str(i+1), key=f"btn_{k}_{i}", type="secondary" if is_f else "primary", use_container_width=True):
                            if is_f: confirm_cancel_dialog(k, i)
                            else: st.session_state[f"active_{k}"] = True; st.rerun()
                if st.session_state.get(f"active_{k}"):
                    with st.expander(f"Verifikasi {k.upper()} Step {len(logs)+1}", expanded=True):
                        res = {q: st.radio(f"→ {q}", ["O", "X"], key=f"q_{k}_{len(logs)}_{q}", horizontal=True) for q in QC_CONTENT['B'][k]['qs']}
                        memo = st.text_input("Catatan / Respon (Jika X)", key=f"m_{k}_{len(logs)}")
                        if st.button("Simpan Data", key=f"sv_{k}"):
                            st.session_state.b_logs[k].append({"t": datetime.now(jakarta_tz).strftime("%H:%M"), "chk": res, "memo": memo})
                            del st.session_state[f"active_{k}"]; st.rerun()
                st.divider()

main_memo = st.text_area("Input Catatan Tambahan (Khusus)", key="v_main_memo")

# --- 6. [전송 및 저장] 텔레그램 리포트 & 구글 시트 엔진 통합 ---
if st.button("💾 SIMPAN & KIRIM LAPORAN", type="primary", use_container_width=True):
    try:
        tg_msg = f"🚀 *Laporan QC Lapangan*\n📅 {full_today} | {shift_label}\n👤 QC: {pelapor}\n--------------------------------\n\n"
        
        # [A 섹션 상세 투사]
        tg_msg += "📅 *Rutinitas QC*\n"
        for k in ["a1","a2","a3","a5","a6","a7","a9"]:
            if globals().get(f"sw_{k}"):
                info = QC_CONTENT['A'][k]
                tg_msg += f"• {k.upper()}. {info['title']}\n"
                if k in ["a1","a2"]: 
                    p_val = st.session_state.get(f"p_{k}", [])
                    tg_msg += f"({', '.join(p_val) if p_val else 'Belum'})\n"

                if k == "a5":
                    tg_msg += f"  └ {st.session_state.get('ans_a5', '-')}\n"
                elif 'qs' in info:
                    for idx, q in enumerate(info['qs']):
                        val = st.session_state.get(f"ans_{k}_{idx+1}", "-")
                        if k == "a7" and idx == 1 and val == "Yes": val += f" (Penerima: {st.session_state.get('ans_a7_name','')})"
                        tg_msg += f"- {q}\n  └ {val}\n"
                tg_msg += "\n"

        if sw_b1:
            tg_msg += "--------------------------------\n\n👥 *B-1. Laporan Absensi*\n"
            for idx, tl in enumerate(TARGET_LABELS):
                if idx == 1: tg_msg += "\n" # [수정] Spacing 적용
                tg_msg += f"  {tl}\n"
                for ar in QC_CONTENT['B']['b1']['areas']:
                    d = st.session_state.b1_data[tl][ar]
                    tg_msg += f"  - {ar}: {d['jam'] if d['jam'] else '00.00'} / {d['pax'] if d['pax'] else '0'} / ({d['st']})\n"
            tg_msg += "\n"

        tg_msg += "⚡ *Interval Check Status*\n"
        if st.session_state.targets['a4'] > 0:
            tg_msg += f"• A-4. {QC_CONTENT['A']['a4']['title']}\n"
            tg_msg += f"  └ {get_prog_bar(len(st.session_state.a4_ts), st.session_state.targets['a4'])} ({len(st.session_state.a4_ts)}/{st.session_state.targets['a4']})\n\n"
        if st.session_state.targets['a8'] > 0:
            tg_msg += f"• A-8. {QC_CONTENT['A']['a8']['title']}\n"
            tg_msg += f"  └ {get_prog_bar(len(st.session_state.a8_logs), st.session_state.targets['a8'])} ({len(st.session_state.a8_logs)}/{st.session_state.targets['a8']})\n"
            for idx, log in enumerate(st.session_state.a8_logs):
                if isinstance(log, dict) and 'res' in log:
                    a8_str = "/".join([f"({v})" for v in log['res'].values()])
                    tg_msg += f"  - H{idx+1} [{log['t']}] {a8_str}\n"
            tg_msg += "\n"

        tg_msg += "🅱️ *Detail Laporan Team Leader*\n"
        for k in B_KEYS:
            target = st.session_state.targets[k]
            if st.session_state.get(f"sw_{k}") and target > 0:
                logs = st.session_state.b_logs[k]
                tg_msg += f"• {k.upper()}. {QC_CONTENT['B'][k]['title']}\n"
                tg_msg += f"  └ Progress: {get_prog_bar(len(logs), target)} ({len(logs)}/{target})\n"
                for l in logs:
                    chks = " / ".join([f"({v})" for v in l['chk'].values()])
                    tg_msg += f"  - {l['t']} / {chks}" + (f" / {l['memo']}" if l['memo'] else "") + "\n"
                tg_msg += "\n"

        tg_msg += f"📝 *Catatan:* {main_memo if main_memo else '-'}\n🕒 *Update:* {current_time_full}"
        
        # [Google Sheets 저장 엔진]
        if gc:
            ss = gc.open_by_url('https://docs.google.com/spreadsheets/d/1kR2C_7IxC_5FpztsWQaBMT8EtbcDHerKL6YLGfQucWw/edit')
            target_tab = f"{today_str}_{shift_label.split(' (')[0]}"
            try: worksheet = ss.worksheet(target_tab)
            except: 
                worksheet = ss.add_worksheet(title=target_tab, rows="100", cols="50")
                st.info(f"✨ Sheet Baru Dibuat: {target_tab}")
            
            all_v = worksheet.get_all_values()
            new_col = (len(all_v[1]) if len(all_v) > 1 else 1) + 1
            def get_c(n):
                r = ""; 
                while n > 0: n, rem = divmod(n - 1, 26); r = chr(65 + rem) + r
                return r
            header = [f"{full_today} {current_time_full}", pelapor, main_memo, str(st.session_state.a4_ts)]
            worksheet.update(f"{get_c(new_col)}2", [[v] for v in header])
            st.success(f"✅ Data Berhasil Disimpan di Sheet: {target_tab}")

        send_telegram(tg_msg); st.success("✅ Laporan Berhasil Dikirim ke Telegram!")
    except Exception as e: st.error(f"🚨 Error: {e}")
