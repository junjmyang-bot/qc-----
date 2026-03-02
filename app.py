import streamlit as st
from datetime import datetime
import json
import gspread
from google.oauth2.service_account import Credentials
from typing import Any

st.set_page_config(page_title="SOI QC Smart System", layout="wide", page_icon="factory")

st.markdown(
    """
    <style>
    .main { background-color: white !important; }
    div[data-testid="stStatusWidget"], .stDeployButton { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

SHEET_URL = "https://docs.google.com/spreadsheets/d/1kR2C_7IxC_5FpztsWQaBMT8EtbcDHerKL6YLGfQucWw/edit"

PROGRESS_30 = ["a4", "a5", "b3", "b4", "b5", "b9"]
PROGRESS_1H = ["a8", "b2", "b6", "b7", "b8", "b10"]
ROUTINE_SHIFT = ["a1", "a2", "a3", "a6", "a7", "a9", "b1"]

REPORTS = {
    "a4": {"code": "A-4", "kind": "progress", "group": "30min", "label": "Laporan QC di Tablet", "goal_default": 16, "goal_max": 30},
    "a5": {"code": "A-5", "kind": "progress", "group": "30min", "label": "Status Tes Steam", "goal_default": 10, "goal_max": 30},
    "b3": {"code": "B-3", "kind": "progress", "group": "30min", "label": "Laporan Situasi Kupas", "goal_default": 16, "goal_max": 30},
    "b4": {"code": "B-4", "kind": "progress", "group": "30min", "label": "Laporan Situasi Packing", "goal_default": 16, "goal_max": 30},
    "b5": {"code": "B-5", "kind": "progress", "group": "30min", "label": "Hasil Per Jam", "goal_default": 16, "goal_max": 30},
    "b9": {"code": "B-9", "kind": "progress", "group": "30min", "label": "Laporan Kondisi BB", "goal_default": 16, "goal_max": 30},
    "a8": {"code": "A-8", "kind": "progress", "group": "1hour", "label": "Status Barang Jatuh", "goal_default": 8, "goal_max": 24},
    "b2": {"code": "B-2", "kind": "progress", "group": "1hour", "label": "Laporan Status Steam", "goal_default": 8, "goal_max": 24},
    "b6": {"code": "B-6", "kind": "progress", "group": "1hour", "label": "Laporan Giling", "goal_default": 8, "goal_max": 24},
    "b7": {"code": "B-7", "kind": "progress", "group": "1hour", "label": "Laporan Giling (Steril)", "goal_default": 8, "goal_max": 24},
    "b8": {"code": "B-8", "kind": "progress", "group": "1hour", "label": "Laporan Potong", "goal_default": 8, "goal_max": 24},
    "b10": {"code": "B-10", "kind": "progress", "group": "1hour", "label": "Laporan Dry", "goal_default": 8, "goal_max": 24},
    "a1": {"code": "A-1", "kind": "routine", "group": "shift", "label": "Cek Stok BB Steam", "goal_default": 2, "goal_max": 5},
    "a2": {"code": "A-2", "kind": "routine", "group": "shift", "label": "Cek Stok BS", "goal_default": 2, "goal_max": 5},
    "a3": {"code": "A-3", "kind": "routine", "group": "shift", "label": "Handover IN", "goal_default": 1, "goal_max": 5},
    "a6": {"code": "A-6", "kind": "routine", "group": "shift", "label": "List BB Butuh Kirim", "goal_default": 2, "goal_max": 5},
    "a7": {"code": "A-7", "kind": "routine", "group": "shift", "label": "Handover & Rencana", "goal_default": 1, "goal_max": 5},
    "a9": {"code": "A-9", "kind": "routine", "group": "shift", "label": "Sisa Barang", "goal_default": 1, "goal_max": 5},
    "b1": {"code": "B-1", "kind": "routine", "group": "shift", "label": "Cek Laporan Absensi", "goal_default": 2, "goal_max": 5},
}

ROUTINE_SLOTS = ["Awal", "Istirahat", "Jam 12", "Handover", "Closing"]


def safe_cell(matrix: list[list[str]], row_idx: int, col_idx: int, default: str = "") -> str:
    if row_idx < 0 or col_idx < 0:
        return default
    if row_idx >= len(matrix):
        return default
    row = matrix[row_idx]
    if col_idx >= len(row):
        return default
    return row[col_idx]


@st.cache_resource
def get_worksheet():
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        info = json.loads(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        gc = gspread.authorize(creds)
        return gc.open_by_url(SHEET_URL).sheet1
    except Exception as exc:
        st.error(f"Koneksi Google Sheet gagal: {exc}")
        return None


def init_state():
    if "qc_store" not in st.session_state:
        st.session_state.qc_store = {key: [] for key in PROGRESS_30 + PROGRESS_1H}
    if "v_map" not in st.session_state:
        st.session_state.v_map = {key: 0 for key in PROGRESS_30 + PROGRESS_1H}


def update_progress_slots(item_id: str) -> None:
    version = st.session_state.v_map[item_id]
    raw_values = st.session_state.get(f"u_{item_id}_{version}", [])
    if not raw_values:
        st.session_state.qc_store[item_id] = []
    else:
        numbers = [int(value) for value in raw_values if value.isdigit()]
        if numbers:
            st.session_state.qc_store[item_id] = [str(i) for i in range(1, max(numbers) + 1)]
        else:
            st.session_state.qc_store[item_id] = []
    st.session_state.v_map[item_id] += 1


def progress_bar(values: list[str], goal: int) -> str:
    if goal <= 0:
        return "[----------] (0%)"
    percent = min(100, int((len(values) / goal) * 100))
    filled = percent // 10
    return f"[{'#' * filled}{'-' * (10 - filled)}] ({percent}%)"


def to_column_name(num: int) -> str:
    result = ""
    while num > 0:
        num, rem = divmod(num - 1, 26)
        result = chr(65 + rem) + result
    return result


def join_values(values: Any) -> str:
    if isinstance(values, list):
        return ", ".join(values)
    return values or ""


def render_sidebar_settings() -> dict[str, dict[str, Any]]:
    settings: dict[str, dict[str, Any]] = {}
    with st.sidebar:
        st.header("Pengaturan Laporan")

        with st.expander("30 Menit (A/B)", expanded=True):
            for item_id in PROGRESS_30:
                report = REPORTS[item_id]
                settings[item_id] = {
                    "show": st.toggle(f"{report['code']} {report['label']}", value=True, key=f"sw_{item_id}"),
                    "goal": st.number_input(
                        f"Target {report['code']}",
                        min_value=1,
                        max_value=report["goal_max"],
                        value=report["goal_default"],
                        key=f"g_{item_id}",
                    ),
                }

        with st.expander("1 Jam (A/B)", expanded=False):
            for item_id in PROGRESS_1H:
                report = REPORTS[item_id]
                settings[item_id] = {
                    "show": st.toggle(f"{report['code']} {report['label']}", value=True, key=f"sw_{item_id}"),
                    "goal": st.number_input(
                        f"Target {report['code']}",
                        min_value=1,
                        max_value=report["goal_max"],
                        value=report["goal_default"],
                        key=f"g_{item_id}",
                    ),
                }

        with st.expander("Shift Routine", expanded=False):
            for item_id in ROUTINE_SHIFT:
                report = REPORTS[item_id]
                settings[item_id] = {
                    "show": st.toggle(f"{report['code']} {report['label']}", value=True, key=f"sw_{item_id}"),
                    "goal": st.number_input(
                        f"Jumlah Cek {report['code']}",
                        min_value=1,
                        max_value=report["goal_max"],
                        value=report["goal_default"],
                        key=f"g_{item_id}",
                    ),
                }
    return settings


def render_progress_item(item_id, settings):
    report = REPORTS[item_id]
    show = settings[item_id]["show"]
    goal = settings[item_id]["goal"]
    if not show:
        return ""

    st.markdown(f"**{report['code']} {report['label']}**")
    version = st.session_state.v_map[item_id]
    options = [str(i) for i in range(1, goal + 1)]
    st.pills(
        report["label"],
        options,
        key=f"u_{item_id}_{version}",
        on_change=update_progress_slots,
        args=(item_id,),
        selection_mode="multi",
        label_visibility="collapsed",
        default=st.session_state.qc_store[item_id],
    )
    return st.text_input(f"Komentar {report['code']}", key=f"m_{item_id}")


def render_routine_item(item_id, settings):
    report = REPORTS[item_id]
    show = settings[item_id]["show"]
    goal = settings[item_id]["goal"]
    if not show:
        return [], ""

    st.markdown(f"**{report['code']} {report['label']}**")
    options = ROUTINE_SLOTS[:goal]
    picks = st.pills(
        report["label"],
        options,
        selection_mode="multi",
        key=f"u_{item_id}",
        label_visibility="collapsed",
    )
    memo = st.text_input(f"Memo {report['code']}", key=f"m_{item_id}")
    return picks, memo


def build_payload(
    today_key: str,
    pelapor: str,
    settings: dict[str, dict[str, Any]],
    progress_comments: dict[str, str],
    routine_checks: dict[str, list[str]],
    routine_comments: dict[str, str],
    final_memo: str,
) -> list[str]:
    payload = ["", today_key, pelapor, "", ""]

    for item_id in PROGRESS_30:
        show = settings[item_id]["show"]
        goal = settings[item_id]["goal"]
        value = progress_bar(st.session_state.qc_store[item_id], goal) if show else "-"
        payload.extend([value, progress_comments.get(item_id, ""), ""])

    payload.append("")

    for item_id in PROGRESS_1H:
        show = settings[item_id]["show"]
        goal = settings[item_id]["goal"]
        value = progress_bar(st.session_state.qc_store[item_id], goal) if show else "-"
        payload.extend([value, progress_comments.get(item_id, ""), ""])

    payload.append("")

    for item_id in ROUTINE_SHIFT:
        show = settings[item_id]["show"]
        value = join_values(routine_checks.get(item_id, [])) if show else "-"
        payload.extend([value, routine_comments.get(item_id, ""), ""])

    payload.extend([final_memo, datetime.now().strftime("%H:%M:%S")])
    return payload


def append_memo(old_memo: str, new_memo: str) -> str:
    if not new_memo:
        return old_memo
    timestamp = datetime.now().strftime("%H:%M")
    prefix = f"[{timestamp}] {new_memo}"
    if not old_memo:
        return prefix
    return f"{old_memo}\n{prefix}"


def render_progress_section(title: str, item_ids: list[str], settings: dict[str, dict[str, Any]]) -> dict[str, str]:
    st.subheader(title)
    comments: dict[str, str] = {}
    with st.container(border=True):
        for item_id in item_ids:
            comments[item_id] = render_progress_item(item_id, settings)
    return comments


def render_routine_section(settings: dict[str, dict[str, Any]]) -> tuple[dict[str, list[str]], dict[str, str]]:
    st.subheader("Shift Routine")
    checks: dict[str, list[str]] = {}
    comments: dict[str, str] = {}
    with st.container(border=True):
        for item_id in ROUTINE_SHIFT:
            check_values, memo = render_routine_item(item_id, settings)
            checks[item_id] = check_values
            comments[item_id] = memo
    return checks, comments


def save_to_sheet(
    worksheet: Any,
    today: str,
    shift: str,
    pelapor: str,
    settings: dict[str, dict[str, Any]],
    progress_comments: dict[str, str],
    routine_checks: dict[str, list[str]],
    routine_comments: dict[str, str],
    new_memo: str,
) -> None:
    all_values = worksheet.get_all_values()
    today_key = f"{today} ({shift})"
    header_row = all_values[1] if len(all_values) > 1 else []

    col_index = -1
    for i, value in enumerate(header_row):
        if value == today_key:
            col_index = i + 1
            break

    old_memo = ""
    if col_index > 0:
        old_memo = safe_cell(all_values, 63, col_index - 1, "")

    final_memo = append_memo(old_memo, new_memo)
    payload = build_payload(
        today_key=today_key,
        pelapor=pelapor,
        settings=settings,
        progress_comments=progress_comments,
        routine_checks=routine_checks,
        routine_comments=routine_comments,
        final_memo=final_memo,
    )

    if col_index == -1:
        col_index = len(header_row) + 1 if len(header_row) >= 3 else 3

    start_col = to_column_name(col_index)
    worksheet.update(f"{start_col}1", [[value] for value in payload])


def main() -> None:
    init_state()
    worksheet = get_worksheet()
    settings = render_sidebar_settings()

    st.title("SOI QC Smart System")
    today = datetime.now().strftime("%Y-%m-%d")

    col1, col2 = st.columns(2)
    with col1:
        shift = st.selectbox("Shift", ["Shift 1 (Pagi)", "Shift 2 (Sore)", "Shift tengah"])
    with col2:
        pelapor = st.text_input("Pelapor", value="JUNMO YANG")

    progress_comments: dict[str, str] = {}
    progress_comments.update(render_progress_section("30 Menit", PROGRESS_30, settings))
    progress_comments.update(render_progress_section("1 Jam", PROGRESS_1H, settings))
    routine_checks, routine_comments = render_routine_section(settings)

    st.subheader("Memo Umum")
    new_memo = st.text_area("Catatan tambahan", key="main_memo")

    if st.button("Update ke Google Sheet", use_container_width=True):
        if not worksheet:
            st.error("Koneksi sheet gagal.")
            return

        save_to_sheet(
            worksheet=worksheet,
            today=today,
            shift=shift,
            pelapor=pelapor,
            settings=settings,
            progress_comments=progress_comments,
            routine_checks=routine_checks,
            routine_comments=routine_comments,
            new_memo=new_memo,
        )
        st.success("Data berhasil disimpan.")


main()
