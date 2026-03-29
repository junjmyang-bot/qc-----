from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

from board_logic import (
    REPORTS,
    REPORT_ORDER,
    add_exception_instruction,
    add_issue_log,
    board_has_meaningful_data,
    build_board_view,
    build_slot_schedule,
    display_dt,
    display_time,
    dt_to_storage,
    empty_board_state,
    empty_report_state,
    finish_exception_instruction,
    normalize_board_state,
    record_qc_check,
    record_submission,
    serialize_global_state,
    serialize_report_state,
    update_active_reports,
    update_lineup,
)

SHEET_URL = "https://docs.google.com/spreadsheets/d/1kR2C_7IxC_5FpztsWQaBMT8EtbcDHerKL6YLGfQucWw/edit"
LOCAL_CACHE_PATH = Path(__file__).with_name("board_state_local.json")
CREDENTIALS_PATH = Path(__file__).with_name("credentials.json")

PROGRESS_30 = ["a4", "a5", "b3", "b4", "b5", "b9"]
PROGRESS_1H = ["a8", "b2", "b6", "b7", "b8", "b10"]
ROUTINE_SHIFT = ["a1", "a2", "a3", "a6", "a7", "a9", "b1"]

STATUS_TONES = {
    "Not Reported": "metric-red",
    "Sudah disubmit, perlu dicek QC": "metric-amber",
    "In Progress": "metric-blue",
    "Complete": "metric-green",
    "Issue Logged": "metric-slate",
}


def configure_page() -> None:
    st.set_page_config(
        page_title="QC Supervisory Board v1",
        layout="wide",
        page_icon="factory",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
        <style>
        .main {
            background: linear-gradient(180deg, #f7f7f2 0%, #eef2ec 100%) !important;
        }
        div[data-testid="stStatusWidget"], .stDeployButton {
            display: none !important;
        }
        .metric-card {
            border-radius: 18px;
            padding: 18px 18px 14px 18px;
            border: 1px solid rgba(15, 23, 42, 0.08);
            background: white;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.05);
            min-height: 116px;
        }
        .metric-card.metric-red { background: linear-gradient(180deg, #fff4f2 0%, #ffe7e2 100%); }
        .metric-card.metric-amber { background: linear-gradient(180deg, #fff8ea 0%, #ffefc7 100%); }
        .metric-card.metric-blue { background: linear-gradient(180deg, #f2f8ff 0%, #e0efff 100%); }
        .metric-card.metric-green { background: linear-gradient(180deg, #effcf2 0%, #dff5e6 100%); }
        .metric-card.metric-slate { background: linear-gradient(180deg, #f5f7f9 0%, #e7edf2 100%); }
        .metric-label {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #475569;
            font-weight: 700;
            margin-bottom: 10px;
        }
        .metric-value {
            font-size: 2rem;
            line-height: 1;
            font-weight: 800;
            color: #0f172a;
            margin-bottom: 8px;
        }
        .metric-note {
            font-size: 0.8rem;
            color: #475569;
        }
        .status-pill {
            display: inline-block;
            padding: 0.2rem 0.65rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 700;
            margin-right: 0.35rem;
            margin-bottom: 0.35rem;
            border: 1px solid transparent;
        }
        .status-red { background: #fee2e2; color: #b91c1c; border-color: #fecaca; }
        .status-amber { background: #fef3c7; color: #b45309; border-color: #fde68a; }
        .status-blue { background: #dbeafe; color: #1d4ed8; border-color: #bfdbfe; }
        .status-green { background: #dcfce7; color: #15803d; border-color: #bbf7d0; }
        .status-slate { background: #e2e8f0; color: #334155; border-color: #cbd5e1; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def build_layout() -> dict[str, Any]:
    row = 1
    out: dict[str, Any] = {"top": row}
    row += 1
    out["date"] = row
    row += 1
    out["pelapor"] = row
    row += 3

    progress_rows: dict[str, dict[str, int]] = {}
    for report_id in PROGRESS_30:
        progress_rows[report_id] = {"value": row, "comment": row + 1, "meta": row + 2}
        row += 3
    row += 1
    for report_id in PROGRESS_1H:
        progress_rows[report_id] = {"value": row, "comment": row + 1, "meta": row + 2}
        row += 3
    row += 1

    routine_rows: dict[str, dict[str, int]] = {}
    for report_id in ROUTINE_SHIFT:
        routine_rows[report_id] = {"value": row, "comment": row + 1, "meta": row + 2}
        row += 3

    out["progress"] = progress_rows
    out["routine"] = routine_rows
    out["memo"] = row
    out["saved"] = row + 1
    out["total"] = row + 1
    return out


LAYOUT = build_layout()


def safe_cell(matrix: list[list[str]], row_idx: int, col_idx: int, default: str = "") -> str:
    if row_idx < 0 or col_idx < 0 or row_idx >= len(matrix):
        return default
    row = matrix[row_idx]
    if col_idx >= len(row):
        return default
    return row[col_idx]


def to_column_name(num: int) -> str:
    result = ""
    while num > 0:
        num, rem = divmod(num - 1, 26)
        result = chr(65 + rem) + result
    return result


def get_column_values(matrix: list[list[str]], col_index: int, row_count: int) -> list[str]:
    if col_index <= 0:
        return [""] * row_count
    return [safe_cell(matrix, row - 1, col_index - 1, "") for row in range(1, row_count + 1)]


def try_load_service_account() -> dict[str, Any] | None:
    try:
        secret_value = st.secrets.get("gcp_service_account")
        if secret_value:
            return json.loads(secret_value)
    except Exception:
        pass

    if CREDENTIALS_PATH.exists():
        try:
            return json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


@st.cache_resource
def get_worksheet():
    info = try_load_service_account()
    if not info:
        return None
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        return gspread.authorize(creds).open_by_url(SHEET_URL).sheet1
    except Exception:
        return None


def load_local_cache() -> dict[str, Any]:
    if not LOCAL_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(LOCAL_CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_local_cache(cache: dict[str, Any]) -> None:
    LOCAL_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def legacy_note_from_comment(comment: str) -> str:
    if not comment:
        return ""
    for marker in ("\n\n[riwayat_cek]\n", "\n\n[checks]\n"):
        if marker in comment:
            return comment.split(marker, 1)[0].strip()
    return comment.strip()


def combine_day_and_clock(day: date, clock_text: str) -> str:
    text = (clock_text or "").strip()
    if not text:
        return ""
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(text, fmt).time()
            return datetime.combine(day, parsed).isoformat(timespec="seconds")
        except ValueError:
            continue
    return ""


def migrate_legacy_interval_report(meta_text: str, comment_text: str, report_id: str, day: date, shift_name: str) -> dict[str, Any]:
    report_state = empty_report_state()
    report_state["notes"] = legacy_note_from_comment(comment_text)
    try:
        payload = json.loads(meta_text)
    except json.JSONDecodeError:
        return report_state

    if not isinstance(payload, dict) or payload.get("version") != 2:
        return report_state

    report_state["notes"] = str(payload.get("note", report_state["notes"]))
    entries = payload.get("checks", [])
    if not isinstance(entries, list):
        return report_state

    selected: list[str] = []
    latest_times: dict[str, str] = {}
    schedule = {slot["slot_key"]: slot for slot in build_slot_schedule(report_id, day, shift_name)}

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
        slot_key = str(entry.get("slot", entry.get("index", ""))).strip()
        slot_list = status.get("selected_slots")
        if isinstance(slot_list, list):
            selected = [str(item) for item in slot_list if str(item).isdigit()]
        elif slot_key.isdigit():
            action = str(status.get("action", "checked")).lower()
            if action == "unchecked":
                selected = [item for item in selected if item != slot_key]
            elif slot_key not in selected:
                selected.append(slot_key)
        if slot_key.isdigit() and entry.get("timestamp"):
            latest_times[slot_key] = str(entry["timestamp"])

    for slot_key in selected:
        submitted_at = combine_day_and_clock(day, latest_times.get(slot_key, "")) or dt_to_storage(schedule.get(slot_key, {}).get("due_at"))
        report_state["submissions"].append(
            {
                "id": f"legacy-{report_id}-{slot_key}",
                "slot_key": slot_key,
                "submitted_at": submitted_at,
                "submitted_by": "",
            }
        )
    if report_state["submissions"]:
        report_state["status_updated_at"] = report_state["submissions"][-1]["submitted_at"]
    return report_state


def migrate_legacy_named_report(meta_text: str, comment_text: str, report_id: str, day: date, shift_name: str) -> dict[str, Any]:
    report_state = empty_report_state()
    report_state["notes"] = legacy_note_from_comment(comment_text)
    try:
        payload = json.loads(meta_text)
    except json.JSONDecodeError:
        return report_state

    if not isinstance(payload, dict) or payload.get("version") != 2:
        return report_state

    report_state["notes"] = str(payload.get("note", report_state["notes"]))
    picks = payload.get("checks", [])
    if not isinstance(picks, list):
        return report_state

    schedule = build_slot_schedule(report_id, day, shift_name)
    label_lookup = {slot["label"].strip().lower(): slot for slot in schedule}
    for label in picks:
        slot = label_lookup.get(str(label).strip().lower())
        if not slot:
            continue
        report_state["submissions"].append(
            {
                "id": f"legacy-{report_id}-{slot['slot_key']}",
                "slot_key": slot["slot_key"],
                "submitted_at": dt_to_storage(slot["due_at"]),
                "submitted_by": "",
            }
        )
    if report_state["submissions"]:
        report_state["status_updated_at"] = report_state["submissions"][-1]["submitted_at"]
    return report_state


def parse_report_state(meta_text: str, comment_text: str, report_id: str, day: date, shift_name: str) -> dict[str, Any]:
    if meta_text.strip():
        try:
            payload = json.loads(meta_text)
            if isinstance(payload, dict) and payload.get("version") == 3:
                board = normalize_board_state({"reports": {report_id: payload}})
                report_state = board["reports"][report_id]
                if not report_state["notes"]:
                    report_state["notes"] = legacy_note_from_comment(comment_text)
                return report_state
        except json.JSONDecodeError:
            pass

    if REPORTS[report_id]["kind"] == "interval":
        return migrate_legacy_interval_report(meta_text, comment_text, report_id, day, shift_name)
    return migrate_legacy_named_report(meta_text, comment_text, report_id, day, shift_name)


def load_board_state_from_sheet(worksheet: Any, today_key: str, day: date, shift_name: str) -> tuple[dict[str, Any] | None, bool]:
    if not worksheet:
        return None, False
    try:
        all_values = worksheet.get_all_values()
    except Exception:
        return None, False

    header = all_values[1] if len(all_values) > 1 else []
    col_index = -1
    for idx, value in enumerate(header):
        if value == today_key:
            col_index = idx + 1
            break
    if col_index == -1:
        return None, False

    col_values = get_column_values(all_values, col_index, LAYOUT["total"])
    board = empty_board_state()

    top_raw = col_values[LAYOUT["top"] - 1].strip()
    if top_raw:
        try:
            payload = json.loads(top_raw)
            if isinstance(payload, dict):
                if isinstance(payload.get("setup"), dict):
                    board["setup"] = payload["setup"]
                if isinstance(payload.get("lineup"), dict):
                    board["lineup"] = payload["lineup"]
                if isinstance(payload.get("issue_logs"), list):
                    board["issue_logs"] = payload["issue_logs"]
                if isinstance(payload.get("exception_instructions"), list):
                    board["exception_instructions"] = payload["exception_instructions"]
        except json.JSONDecodeError:
            pass

    for report_id in REPORT_ORDER:
        rows = LAYOUT["progress"].get(report_id) or LAYOUT["routine"].get(report_id)
        if not rows:
            continue
        board["reports"][report_id] = parse_report_state(
            meta_text=col_values[rows["meta"] - 1],
            comment_text=col_values[rows["comment"] - 1],
            report_id=report_id,
            day=day,
            shift_name=shift_name,
        )

    board["general_note"] = col_values[LAYOUT["memo"] - 1].strip()
    return normalize_board_state(board), True


def load_board_state(worksheet: Any, today_key: str, day: date, shift_name: str) -> tuple[dict[str, Any], str]:
    sheet_state, found_sheet_column = load_board_state_from_sheet(worksheet, today_key, day, shift_name)
    if found_sheet_column and sheet_state is not None:
        return normalize_board_state(sheet_state), "Google Sheet"

    local_cache = load_local_cache()
    local_state = normalize_board_state(local_cache.get(today_key))
    if board_has_meaningful_data(local_state):
        return local_state, "Local cache"
    return empty_board_state(), "New board"


def save_board_state_to_sheet(worksheet: Any, today_key: str, shift_name: str, actor: str, board: dict[str, Any]) -> str:
    if not worksheet:
        return "Saved to local cache only"

    all_values = worksheet.get_all_values()
    header = all_values[1] if len(all_values) > 1 else []
    col_index = -1
    for idx, value in enumerate(header):
        if value == today_key:
            col_index = idx + 1
            break
    if col_index == -1:
        col_index = len(header) + 1 if len(header) >= 3 else 3

    before = get_column_values(all_values, col_index if col_index > 0 else -1, LAYOUT["total"])
    after = before[:]
    now = datetime.now()
    board_view = build_board_view(board, shift_name, now=now)
    eval_lookup = {
        item["report_id"]: item
        for item in board_view["active_reports"] + board_view["off_today_reports"]
    }

    updates: dict[int, str] = {
        LAYOUT["top"]: serialize_global_state(board),
        LAYOUT["date"]: today_key,
        LAYOUT["pelapor"]: actor.strip(),
        LAYOUT["memo"]: board.get("general_note", "").strip(),
        LAYOUT["saved"]: now.strftime("%H:%M:%S"),
    }

    for report_id in REPORT_ORDER:
        rows = LAYOUT["progress"].get(report_id) or LAYOUT["routine"].get(report_id)
        if not rows:
            continue

        report_eval = eval_lookup[report_id]
        value = "OFF TODAY" if not report_eval["active"] else report_eval["status"]
        submitted_summary = f"{display_time(report_eval['submitted_at'])} | {report_eval['submitted_by'] or '-'}"
        qc_summary = (
            f"{display_time(report_eval['checked_at'])} | {report_eval['checked_by'] or '-'}"
            if report_eval["qc_checked"]
            else "Belum"
        )
        comment = (
            f"{report_eval['department']} | {report_eval['frequency_label']} | "
            f"Due {report_eval['latest_due_label']} {display_time(report_eval['latest_due_at'])}\n"
            f"Submitted: {submitted_summary}\n"
            f"QC: {qc_summary}\n"
            f"Issue logs: {report_eval['issue_log_count']}"
        )
        updates[rows["value"]] = value
        updates[rows["comment"]] = comment
        updates[rows["meta"]] = serialize_report_state(board["reports"][report_id])

    for row_num, value in updates.items():
        after[row_num - 1] = value

    changed_rows = [row_num for row_num in sorted(updates) if before[row_num - 1] != after[row_num - 1]]
    if changed_rows:
        column_name = to_column_name(col_index)
        batch = [
            {"range": f"{column_name}{row_num}", "values": [[after[row_num - 1]]]}
            for row_num in changed_rows
        ]
        worksheet.batch_update(batch)
    return "Saved to Google Sheet and local cache"


def save_board_state(worksheet: Any, today_key: str, shift_name: str, actor: str, board: dict[str, Any]) -> str:
    normalized = normalize_board_state(board)
    cache = load_local_cache()
    cache[today_key] = normalized
    save_local_cache(cache)
    try:
        return save_board_state_to_sheet(worksheet, today_key, shift_name, actor, normalized)
    except Exception as exc:
        return f"Saved to local cache only (sheet sync failed: {exc})"


def init_session_state() -> None:
    st.session_state.setdefault("loaded_board_key", "")
    st.session_state.setdefault("board_state", empty_board_state())
    st.session_state.setdefault("storage_source", "New board")
    st.session_state.setdefault("persist_message", "Belum disimpan.")
    st.session_state.setdefault("current_user", "QC / Management")


def ensure_board_loaded(worksheet: Any, today_key: str, day: date, shift_name: str) -> None:
    if st.session_state.loaded_board_key == today_key:
        return
    board, source = load_board_state(worksheet, today_key, day, shift_name)
    st.session_state.board_state = board
    st.session_state.loaded_board_key = today_key
    st.session_state.storage_source = source
    st.session_state.persist_message = f"Loaded from {source}"


def commit_board_change(worksheet: Any, today_key: str, shift_name: str, actor: str, notice: str) -> None:
    message = save_board_state(worksheet, today_key, shift_name, actor, st.session_state.board_state)
    st.session_state.board_state = normalize_board_state(st.session_state.board_state)
    st.session_state.persist_message = f"{notice} | {message}"
    st.rerun()


def tone_for_status(status: str) -> str:
    if status == "Not Reported":
        return "status-red"
    if status == "Sudah disubmit, perlu dicek QC":
        return "status-amber"
    if status == "Complete":
        return "status-green"
    if status == "Issue Logged":
        return "status-slate"
    return "status-blue"


def render_metric_card(title: str, value: int, note: str) -> str:
    return f"""
    <div class="metric-card {STATUS_TONES[title]}">
        <div class="metric-label">{title}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-note">{note}</div>
    </div>
    """


def render_status_pills(report_eval: dict[str, Any]) -> str:
    pills = [
        f'<span class="status-pill {tone_for_status(report_eval["status"])}">{report_eval["status"]}</span>'
    ]
    if report_eval["has_issue_badge"]:
        pills.append('<span class="status-pill status-slate">Issue Logged</span>')
    return "".join(pills)


def report_option_label(report_id: str) -> str:
    report = REPORTS[report_id]
    return f"{report['code']} | {report['label']} | {report['department']}"


def render_report_card(
    worksheet: Any,
    today_key: str,
    shift_name: str,
    current_user: str,
    report_eval: dict[str, Any],
) -> None:
    report_id = report_eval["report_id"]
    report = REPORTS[report_id]
    board = st.session_state.board_state
    schedule = report_eval["slot_schedule"]
    slot_options = [slot["slot_key"] for slot in schedule]
    slot_label_map = {
        slot["slot_key"]: f"{slot['label']} ({slot['due_label']})"
        for slot in schedule
    }
    default_slot = report_eval["latest_due_slot_key"] or (slot_options[0] if slot_options else "")
    default_index = slot_options.index(default_slot) if default_slot in slot_options else 0

    with st.container(border=True):
        st.markdown(f"**{report['code']} {report['label']}**")
        st.markdown(render_status_pills(report_eval), unsafe_allow_html=True)
        st.caption(
            f"{report_eval['department']} | {report_eval['frequency_label']} | "
            f"Latest due: {report_eval['latest_due_label']} {display_time(report_eval['latest_due_at'])}"
        )
        st.caption(report["description"])

        info_cols = st.columns(2)
        with info_cols[0]:
            st.write(f"Submitted: {display_dt(report_eval['submitted_at'])}")
            st.write(f"Submitted by: {report_eval['submitted_by'] or '-'}")
            st.write(f"QC checked: {'Sudah' if report_eval['qc_checked'] else 'Belum'}")
            st.write(f"Last slot due: {display_dt(report_eval['last_slot_due_at'])}")
        with info_cols[1]:
            st.write(f"Checked at: {display_dt(report_eval['checked_at'])}")
            st.write(f"Checked by: {report_eval['checked_by'] or '-'}")
            st.write(f"Issue logs: {report_eval['issue_log_count']}")
            st.write(f"Status updated: {display_dt(report_eval['status_updated_at'])}")

        with st.expander("Actions", expanded=False):
            with st.form(f"submit_form_{report_id}"):
                selected_slot = st.selectbox(
                    "Record submission for slot",
                    options=slot_options,
                    index=default_index,
                    format_func=lambda key: slot_label_map[key],
                    key=f"submit_slot_{report_id}",
                )
                submitter = st.text_input(
                    "submitted_by",
                    value=current_user,
                    key=f"submitter_{report_id}",
                )
                submit_clicked = st.form_submit_button("Record Submission", use_container_width=True)

            if submit_clicked:
                record_submission(board, report_id, selected_slot, submitter)
                commit_board_change(
                    worksheet,
                    today_key,
                    shift_name,
                    submitter or current_user,
                    f"{report['code']} submission recorded",
                )

            qc_disabled = not report_eval["latest_submission_id"] or report_eval["qc_checked"]
            if st.button(
                "QC Check Latest Submission",
                key=f"qc_check_{report_id}",
                use_container_width=True,
                disabled=qc_disabled,
            ):
                record_qc_check(board, report_id, report_eval["latest_submission_id"], current_user)
                commit_board_change(
                    worksheet,
                    today_key,
                    shift_name,
                    current_user,
                    f"{report['code']} QC check recorded",
                )

            with st.form(f"issue_form_{report_id}"):
                problem = st.text_input("Problem", key=f"issue_problem_{report_id}")
                action = st.text_input("Action / Tindakan", key=f"issue_action_{report_id}")
                issue_actor = st.text_input(
                    "Entered by",
                    value=current_user,
                    key=f"issue_actor_{report_id}",
                )
                issue_clicked = st.form_submit_button("Add Issue Log", use_container_width=True)

            if issue_clicked and problem.strip():
                add_issue_log(
                    board,
                    related_id=report_id,
                    related_label=f"{report['code']} {report['label']}",
                    problem=problem,
                    action=action,
                    actor=issue_actor or current_user,
                )
                st.session_state[f"issue_problem_{report_id}"] = ""
                st.session_state[f"issue_action_{report_id}"] = ""
                commit_board_change(
                    worksheet,
                    today_key,
                    shift_name,
                    issue_actor or current_user,
                    f"{report['code']} issue log added",
                )


def main() -> None:
    configure_page()
    init_session_state()
    worksheet = get_worksheet()

    st.title("QC Supervisory Board v1")
    st.caption("current track / 내일부터 바로 사용")

    header_cols = st.columns([1.2, 1, 1])
    with header_cols[0]:
        current_user = st.text_input("Current user", key="current_user")
    with header_cols[1]:
        shift_name = st.selectbox(
            "Shift",
            options=["Shift 1 (Pagi)", "Shift Tengah", "Shift 2 (Sore)"],
            key="shift_name",
        )
    with header_cols[2]:
        today = datetime.now().date()
        st.text_input("Today", value=today.isoformat(), disabled=True)

    today_key = f"{today.isoformat()} ({shift_name})"
    ensure_board_loaded(worksheet, today_key, today, shift_name)
    board = st.session_state.board_state
    board_view = build_board_view(board, shift_name, now=datetime.now())

    st.caption(
        f"Storage source: {st.session_state.storage_source} | "
        f"Key: {today_key} | {st.session_state.persist_message}"
    )
    if not worksheet:
        st.warning("Google Sheet connection is unavailable. Actions will still save to local cache.")

    summary_cols = st.columns([1, 1, 1, 1, 1, 1.2])
    summary_notes = {
        "Not Reported": "지금 제출돼 있어야 하는 최신 슬롯 누락",
        "Sudah disubmit, perlu dicek QC": "제출은 되었고 QC 확인 대기",
        "In Progress": "현재 시점 기준 흐름 정상",
        "Complete": "오늘 마지막 required slot까지 완료",
        "Issue Logged": "이슈/조치 로그가 붙은 active report",
    }
    metric_titles = [
        "Not Reported",
        "Sudah disubmit, perlu dicek QC",
        "In Progress",
        "Complete",
        "Issue Logged",
    ]

    for col, title in zip(summary_cols[:5], metric_titles):
        with col:
            st.markdown(
                render_metric_card(title, board_view["summary"][title], summary_notes[title]),
                unsafe_allow_html=True,
            )

    with summary_cols[5]:
        with st.container(border=True):
            lineup = board["lineup"]
            st.markdown("**Starting Lineup**")
            st.write(f"Status: {'Ada' if lineup['lineup_exists'] else 'Belum'}")
            st.write(f"Updated at: {display_dt(lineup['lineup_updated_at'])}")
            st.write(f"Updated by: {lineup['lineup_updated_by'] or '-'}")
            lineup_cols = st.columns(2)
            with lineup_cols[0]:
                if st.button("Set Ada", key="lineup_yes", use_container_width=True):
                    update_lineup(board, True, current_user)
                    commit_board_change(worksheet, today_key, shift_name, current_user, "Starting Lineup updated to Ada")
            with lineup_cols[1]:
                if st.button("Set Belum", key="lineup_no", use_container_width=True):
                    update_lineup(board, False, current_user)
                    commit_board_change(worksheet, today_key, shift_name, current_user, "Starting Lineup updated to Belum")

    with st.expander("Today Setup / Active Reports 설정", expanded=False):
        st.caption("오늘 필요한 리포트만 active로 유지하고, 나머지는 OFF TODAY로 보냅니다.")
        with st.form("today_setup_form"):
            selected_reports = st.multiselect(
                "Active reports for today",
                options=REPORT_ORDER,
                default=board["setup"]["active_report_ids"],
                format_func=report_option_label,
            )
            general_note = st.text_area(
                "General note (optional)",
                value=board.get("general_note", ""),
            )
            setup_clicked = st.form_submit_button("Save Today Setup", use_container_width=True)
        if setup_clicked:
            board["general_note"] = general_note.strip()
            update_active_reports(board, selected_reports, current_user)
            commit_board_change(worksheet, today_key, shift_name, current_user, "Today Setup saved")
        st.caption(
            f"Setup updated: {display_dt(board['setup']['updated_at'])} | "
            f"by {board['setup']['updated_by'] or '-'}"
        )

    st.subheader("Report Status Board")
    st.caption("오늘 필요한 리포트의 제출 여부, 최신 제출본 기준 QC 체크 여부, 빠진 리포트를 한 화면에서 봅니다.")

    active_reports = board_view["active_reports"]
    for index in range(0, len(active_reports), 2):
        cols = st.columns(2)
        for col, report_eval in zip(cols, active_reports[index:index + 2]):
            with col:
                render_report_card(worksheet, today_key, shift_name, current_user, report_eval)

    st.subheader("Active Exception Instructions")
    with st.container(border=True):
        st.caption("Issue / Tindakan Log와 분리된, 현재도 따라야 하는 특별 지시 영역입니다.")

        with st.form("exception_instruction_form"):
            exc_cols = st.columns([2.2, 1.3, 1])
            with exc_cols[0]:
                instruction_text = st.text_input("instruction_text")
            with exc_cols[1]:
                related_target = st.text_input("related_department_or_report")
            with exc_cols[2]:
                instruction_actor = st.text_input("started_by", value=current_user)
            exc_submit = st.form_submit_button("Add Exception Instruction", use_container_width=True)

        if exc_submit and instruction_text.strip():
            add_exception_instruction(
                board,
                instruction_text=instruction_text,
                related_department_or_report=related_target,
                actor=instruction_actor or current_user,
            )
            commit_board_change(
                worksheet,
                today_key,
                shift_name,
                instruction_actor or current_user,
                "Exception Instruction added",
            )

        if board_view["active_instructions"]:
            for instruction in board_view["active_instructions"]:
                with st.container(border=True):
                    st.markdown('<span class="status-pill status-blue">Masih berlaku</span>', unsafe_allow_html=True)
                    st.write(instruction["instruction_text"])
                    st.caption(
                        f"Related: {instruction['related_department_or_report'] or '-'} | "
                        f"Started: {display_dt(instruction['started_at'])} | "
                        f"By: {instruction['started_by'] or '-'}"
                    )
                    if st.button("Selesai", key=f"finish_instruction_{instruction['id']}"):
                        finish_exception_instruction(board, instruction["id"], current_user)
                        commit_board_change(worksheet, today_key, shift_name, current_user, "Exception Instruction closed")
        else:
            st.info("현재 active한 Exception Instruction이 없습니다.")

        if board_view["completed_instructions"]:
            with st.expander("Completed Exception Instructions", expanded=False):
                for instruction in board_view["completed_instructions"]:
                    with st.container(border=True):
                        st.markdown('<span class="status-pill status-slate">Selesai</span>', unsafe_allow_html=True)
                        st.write(instruction["instruction_text"])
                        st.caption(
                            f"Related: {instruction['related_department_or_report'] or '-'} | "
                            f"Started: {display_dt(instruction['started_at'])} | "
                            f"Ended: {display_dt(instruction['ended_at'])}"
                        )

    st.subheader("Issue / Tindakan Log")
    with st.container(border=True):
        st.caption("문제와 조치 기록 전용 영역입니다. Exception Instruction과 섞이지 않게 별도 관리합니다.")

        with st.form("global_issue_form"):
            log_cols = st.columns([1.4, 1.5, 1.5, 1])
            with log_cols[0]:
                related_report = st.selectbox(
                    "Department / Report",
                    options=["general"] + REPORT_ORDER,
                    format_func=lambda key: "General / Common" if key == "general" else report_option_label(key),
                )
            with log_cols[1]:
                problem_text = st.text_input("Problem")
            with log_cols[2]:
                action_text = st.text_input("Action / Tindakan")
            with log_cols[3]:
                log_actor = st.text_input("Entered by", value=current_user)
            global_log_submit = st.form_submit_button("Add Issue Log", use_container_width=True)

        if global_log_submit and problem_text.strip():
            related_id = "" if related_report == "general" else related_report
            related_label = "General / Common" if related_report == "general" else report_option_label(related_report)
            add_issue_log(
                board,
                related_id=related_id,
                related_label=related_label,
                problem=problem_text,
                action=action_text,
                actor=log_actor or current_user,
            )
            commit_board_change(worksheet, today_key, shift_name, log_actor or current_user, "Issue Log added")

        recent_logs = board_view["recent_issue_logs"]
        if recent_logs:
            for log in recent_logs[:12]:
                with st.container(border=True):
                    st.write(f"{display_dt(log['logged_at'])} | {log['related_label'] or '-'}")
                    st.write(f"Problem: {log['problem'] or '-'}")
                    st.write(f"Action: {log['action'] or '-'}")
                    st.caption(f"Entered by: {log['entered_by'] or '-'}")
        else:
            st.info("오늘 기록된 Issue / Tindakan Log가 없습니다.")

    st.subheader("OFF TODAY")
    with st.container(border=True):
        st.caption("오늘 active가 아닌 리포트는 여기에서 확인합니다.")
        off_today_reports = board_view["off_today_reports"]
        if off_today_reports:
            for report_eval in off_today_reports:
                with st.container(border=True):
                    st.write(f"{report_eval['code']} | {report_eval['name']}")
                    st.caption(f"{report_eval['department']} | inactive in Today Setup")
        else:
            st.info("OFF TODAY로 내려간 리포트가 없습니다.")


if __name__ == "__main__":
    main()
