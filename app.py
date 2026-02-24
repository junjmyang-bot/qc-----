import streamlit as st
from datetime import datetime
import pytz 
import requests

# --- 1. Konfigurasi Dasar & Waktu (WIB) ---
st.set_page_config(page_title="SOI QC SMART SYSTEM", layout="wide", page_icon="🏭")
jakarta_tz = pytz.timezone('Asia/Jakarta')
now_jakarta = datetime.now(jakarta_tz)
today_str = now_jakarta.strftime('%Y-%m-%d')

TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]

# --- 2. [Data Konten] Panduan Detail & Pertanyaan 19 Item ---
QC_CONTENT = {
    "A": {
        "a1": {"title": "Cek Stok BB Sudah steam", "qs": ["Sisa BB sisa shift sebelumya?", "Jumlah bb steam cukup?", "Respon jika kurang?"]},
        "a2": {"title": "Cek Stok BS (Sudah defros)", "qs": ["Sudah defros berapa?", "Estimasi jumlah kerja?", "Jam tambah defros?"]},
        "a3": {"title": "Handover shift", "qs": ["Sudah dapat handover?", "Produksi sesuai rencana?"]},
        "a7": {"title": "Handover & rencana", "qs": ["Rencana sudah dibuat?", "Handover sudah dibuat?", "Sudah baca data stok?"]},
        "a9": {"title": "SISA BARANG", "qs": ["Check MAX 1 PACK (Sudah check?)", "Sisa shift prev?", "Sudah dibereskan?", "Simpan sisa?", "Handover sisa?"]},
        "a4": {"title": "Laporan QC pada Tablet", "check_items": ["Kebersihan harian", "Kontaminan kupas", "Kontaminan packing"]},
        "a5": {"title": "Status Tes Steam", "desc": ["Maksimal selesai jam 13.00", "Update laporan setiap 30 menit", "Cek sampel & update laporan"]},
        "a6": {"title": "List BB butuh kirim", "qs": ["List kirim jam 12.00 sudah ada?", "Kordinasi gudang?"]},
        "a8": {"title": "Status Barang Jatuh", "areas": ["steam", "kupas", "dry", "packing", "cuci"]}
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

# --- 4. Sidebar: Pengaturan ---
with st.sidebar:
    st.header("⚙️ Pengaturan Laporan")
    with st.expander("📅 Visibilitas Rutinitas Shift", expanded=True):
        sw_a1=st.toggle(f"A-1 Stok BB Steam", True)
        sw_a2=st.toggle(f"A-2 Stok BS Defros", True)
        sw_a3=st.toggle("A-3 Handover Masuk", True)
        sw_a7=st.toggle("A-7 Rencana & Handover", True)
        sw_a9=st.toggle("A-9 Sisa Barang", True)
        st.divider(); st.info("📦 Bahan Baku")
        sw_a5=st.toggle(f"A-5 Tes Steam", True)
        sw_a6=st.toggle("A-6 List Kirim BB", True) # [복구 대상]
        st.divider(); st.caption("🅱️ Laporan Team Leader")
        sw_b1=st.toggle("B-1 Absensi Laporan", True)

    with st.expander("⚡ Interval 30 Menit (Target)", expanded=False):
        for k in ["a4", "b3", "b4", "b5", "b9"]:
            st.session_state[f"sw_{k}"] = st.toggle(f"Aktifkan {k.upper()}", True, key=f"tg_sw_{k}")
            if st.session_state[f"sw_{k}"]:
                st.session_state.targets[k] = st.number_input(f"Target {k.upper()}", 0, 48, st.session_state.targets[k], key=f"inp_{k}")

    with st.expander("⏰ Interval 1 Jam (Target)", expanded=False):
        for k in ["a8", "b2", "b6", "b7", "b8", "b10"]:
            st.session_state[f"sw_{k}"] = st.toggle(f"Aktifkan {k.upper()}", True, key=f"tg_sw_{k}")
            if st.session_state[f"sw_{k}"]:
                st.session_state.targets[k] = st.number_input(f"Target {k.upper()}", 0, 24, st.session_state.targets[k], key=f"inp_{k}")

# --- 5. Main UI ---
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
            p_a1 = st.pills("Waktu Cek A1", ["Awal Masuk", "Setelah Istirahat"], selection_mode="multi", key="u_a1")
            ans_a1_1=st.text_input(f"1. {QC_CONTENT['A']['a1']['qs'][0]}", key="a1_1"); ans_a1_2=st.text_input(f"2. {QC_CONTENT['A']['a1']['qs'][1]}", key="a1_2"); st.divider()
        if sw_a2:
            st.markdown(f"**A2. {QC_CONTENT['A']['a2']['title']}**")
            ans_a2_1=st.text_input(f"1. {QC_CONTENT['A']['a2']['qs'][0]}", key="a2_1"); ans_a2_2=st.text_input(f"2. {QC_CONTENT['A']['a2']['qs'][1]}", key="a2_2"); st.divider()
        if sw_a3:
            st.markdown("**A3. Handover Masuk**")
            ans_a3_1=st.radio(f"-> {QC_CONTENT['A']['a3']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a3_1"); st.divider()
        if sw_a7:
            st.markdown("**A7. Handover & Rencana**")
            ans_a7_1=st.radio(f"-> {QC_CONTENT['A']['a7']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a7_1")
            ans_a7_3=st.text_area("Data Stok BB", key="a7_3"); st.divider()
        if sw_a9:
            st.markdown("**A9. Sisa Barang**")
            ans_a9_1=st.radio(f"-> {QC_CONTENT['A']['a9']['qs'][0]}", ["Sudah check", "Belum"], horizontal=True, key="a9_1"); st.divider()

        st.markdown("##### 📦 Bahan Baku")
        if sw_a5:
            st.markdown(f"**A5. {QC_CONTENT['A']['a5']['title']}**")
            for it in QC_CONTENT['A']['a5']['desc']: st.markdown(f"<span style='color:black; font-weight:500;'>→ {it}</span>", unsafe_allow_html=True)
            ans_a5=st.radio("Status A5", ["Done", "Not done"], key="a5_st", horizontal=True, label_visibility="collapsed"); st.divider()
        # [A-6 복구 코드]
        if sw_a6:
            st.markdown(f"**A6. {QC_CONTENT['A']['a6']['title']}**")
            ans_a6_1=st.radio(f"-> {QC_CONTENT['A']['a6']['qs'][0]}", ["Yes", "No"], horizontal=True, key="a6_1")
            ans_a6_2=st.radio(f"-> {QC_CONTENT['A']['a6']['qs'][1]}", ["Yes", "No"], horizontal=True, key="a6_2")
            st.divider()

    with cb:
        st.warning("🅱️ Check TL Reports")
        if sw_b1:
            st.markdown(f"**B1. {QC_CONTENT['B']['b1']['title']}**")
            t1, t2 = st.tabs(["🌅 Awal Masuk", "☕ Setelah Istirahat"])
            for tl, tab in [("Awal Masuk", t1), ("Setelah Istirahat", t2)]:
                with tab:
                    for ar in QC_CONTENT['B']['b1']['areas']:
                        r1, r2, r3 = st.columns([1.5, 1, 1])
                        with r1: st.session_state.b1_data[tl][ar]['jam']=st.text_input(f"Jam {ar} {tl}", key=f"b1_{tl}_{ar}_j")
                        with r2: st.session_state.b1_data[tl][ar]['pax']=st.text_input(f"Pax {ar} {tl}", key=f"b1_{tl}_{ar}_p")
                        with r3: st.session_state.b1_data[tl][ar]['st']=st.radio(f"S/T {ar} {tl}", ["O", "X"], key=f"b1_{tl}_{ar}_s", horizontal=True)

# [Interval Sections - Error Fixed line 125]
for tit, keys, a_ks, b_ks in [("⚡ Interval 30 Menit", ["a4","b3","b4","b5","b9"], ["a4"], ["b3","b4","b5","b9"]), ("⏰ Interval 1 Jam", ["a8","b2","b6","b7","b8","b10"], ["a8"], ["b2","b6","b7","b8","b10"])]:
    st.subheader(tit)
    with st.container(border=True): # 줄바꿈으로 SyntaxError 해결
        ca, cb = st.columns(2)
        with ca:
            st.info("🅰️ QC Direct Check")
            for k in a_ks:
                if st.session_state.get(f"sw_{k}", True) and st.session_state.targets[k] > 0:
                    info = QC_CONTENT['A'][k]
                    st.markdown(f"**{k.upper()}. {info['title']}** (Target: {st.session_state.targets[k]}x)")
                    if 'check_items' in info:
                        for it in info['check_items']: st.markdown(f"<span style='color:black; font-weight:500;'>→ {it}</span>", unsafe_allow_html=True)
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
                        with st.expander("Verifikasi A-8", expanded=True):
                            if st.text_input("Barang segera dibereskan? (Type 'YES')", key="a8_v").strip().upper() == "YES" and st.button("Confirm"):
                                st.session_state.a8_logs.append({"t": datetime.now(jakarta_tz).strftime("%H:%M")})
                                del st.session_state.active_a8; st.rerun()
        with cb:
            st.warning("🅱️ Check TL Reports")
            for k in b_ks:
                if st.session_state.get(f"sw_{k}", True) and st.session_state.targets[k] > 0:
                    info = QC_CONTENT['B'][k]
                    st.markdown(f"**{k.upper()}. {info['title']}**")
                    for q in info['qs']: st.markdown(f"<span style='color:black; font-size:0.85rem;'>✓ {q}</span>", unsafe_allow_html=True)
                    cols = st.columns(4); logs = st.session_state.b_logs[k]
                    for i in range(st.session_state.targets[k]):
                        with cols[i % 4]:
                            is_f = i < len(logs)
                            txt = logs[i]['t'] if is_f else str(i+1)
                            if st.button(txt, key=f"btn_{k}_{i}", type="secondary" if is_f else "primary", use_container_width=True, disabled=(not is_f and i != len(logs))):
                                if is_f: confirm_cancel_dialog(k, i)
                                else: st.session_state[f"active_{k}"] = True; st.rerun()
                    if st.session_state.get(f"active_{k}"):
                        with st.expander(f"Verifikasi {k.upper()} Step {len(logs)+1}", expanded=True):
                            res = {q: st.radio(f"→ {q}", ["O", "X"], key=f"q_{k}_{len(logs)}_{q}", horizontal=True) for q in info['qs']}
                            memo = st.text_input("Catatan / Respon (Jika X)", key=f"m_{k}_{len(logs)}")
                            if st.button("Simpan Data", key=f"sav_{k}"):
                                st.session_state.b_logs[k].append({"t": datetime.now(jakarta_tz).strftime("%H:%M"), "chk": res, "memo": memo})
                                del st.session_state[f"active_{k}"]; st.rerun()

main_memo = st.text_area("Input Catatan Tambahan (Khusus)", key="main_memo_v")

# --- 6. [A+B 완벽 통합] Telegram Message Builder ---
if st.button("💾 SIMPAN & KIRIM LAPORAN KE TELEGRAM", type="primary", use_container_width=True):
    try:
        tg_msg = f"🚀 *Laporan QC Lapangan*\n📅 {today_str} | {shift_label}\n👤 Penanggung Jawab: {pelapor}\n--------------------------------\n\n"
        
        # [A 섹션 복구]
        tg_msg += "📅 *Rutinitas QC (Direct Check)*\n"
        if sw_a1: tg_msg += f"• A-1. Stok BB Steam: {ans_a1_1 if ans_a1_1 else '-'}\n"
        if sw_a2: tg_msg += f"• A-2. Stok BS Defros: {ans_a2_1 if ans_a2_1 else '-'}\n"
        if sw_a3: tg_msg += f"• A-3. Handover: {ans_a3_1}\n"
        if sw_a7: tg_msg += f"• A-7. Rencana: {ans_a7_1} | Stok: {ans_a7_3 if ans_a7_3 else '-'}\n"
        if sw_a9: tg_msg += f"• A-9. Sisa Barang: {ans_a9_1}\n"
        if sw_a5: tg_msg += f"• A-5. Status Tes Steam: {ans_a5}\n"
        if sw_a6: tg_msg += f"• A-6. List BB Jam 12.00: {ans_a6_1} | Kordinasi: {ans_a6_2}\n"
        
        # [A: Interval Check 복구]
        if st.session_state.targets['a4'] > 0 and st.session_state.a4_ts:
            tg_msg += f"\n⚡ *A-4. {QC_CONTENT['A']['a4']['title']}*\n"
            tg_msg += f"  └ {get_prog_bar(len(st.session_state.a4_ts), st.session_state.targets['a4'])} ({len(st.session_state.a4_ts)}/{st.session_state.targets['a4']})\n"
            tg_msg += f"  🕒 {', '.join(st.session_state.a4_ts)}\n"
        
        if st.session_state.targets['a8'] > 0 and st.session_state.a8_logs:
            tg_msg += f"\n⏰ *A-8. {QC_CONTENT['A']['a8']['title']}*\n"
            tg_msg += f"  └ {get_prog_bar(len(st.session_state.a8_logs), st.session_state.targets['a8'])}\n"

        # [B 섹션]
        if sw_b1:
            tg_msg += "\n👥 *B-1. Laporan Absensi*\n"
            for tl in TARGET_LABELS:
                tg_msg += f"  [{tl}]\n"
                for ar in QC_CONTENT['B']['b1']['areas']:
                    d = st.session_state.b1_data[tl][ar]
                    tg_msg += f"  - {ar}: {d['jam'] if d['jam'] else '00.00'} / {d['pax'] if d['pax'] else '0'} / ({d['st']})\n"

        tg_msg += "\n🅱️ *Detail Laporan Team Leader*\n"
        for k in B_KEYS:
            target = st.session_state.targets[k]
            if st.session_state.get(f"sw_{k}", True) and target > 0 and st.session_state.b_logs[k]:
                tg_msg += f"• {k.upper()}. {QC_CONTENT['B'][k]['title']}\n"
                tg_msg += f"  └ Progress: {get_prog_bar(len(st.session_state.b_logs[k]), target)} ({len(st.session_state.b_logs[k])}/{target})\n"
                for log in st.session_state.b_logs[k]:
                    res_str = " / ".join([f"({v})" for v in log['chk'].values()])
                    tg_msg += f"  - {log['t']} / {res_str}" + (f" / {log['memo']}" if log['memo'] else "") + "\n"
                tg_msg += "\n"
        
        tg_msg += f"📝 *Catatan:* {main_memo if main_memo else '-'}\n🕒 *Update Terakhir:* {datetime.now(jakarta_tz).strftime('%H:%M:%S')}"
        send_telegram(tg_msg); st.success("✅ Laporan Full (A+B) Berhasil Dikirim!")
    except Exception as e: st.error(f"Gagal mengirim: {e}")
