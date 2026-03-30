from __future__ import annotations

from datetime import date, datetime
from typing import Any

import streamlit as st

from board_logic import (
    REPORTS,
    REPORT_ORDER,
    add_exception_instruction,
    build_board_view,
    build_slot_schedule,
    display_dt,
    display_time,
    dt_to_storage,
    empty_board_state,
    now_local,
    finish_exception_instruction,
    handover_exception_instruction,
    normalize_board_state,
    record_submission,
    reset_operational_state,
    update_active_reports,
    update_lineup,
)
from board_store import get_last_sheet_error, get_service_account_debug_info, get_worksheet, load_board_state, save_board_state
from telegram_flow import (
    build_current_summary_parts,
    ensure_telegram_cycle,
    send_current_summary_to_telegram,
    start_new_telegram_cycle,
    sync_telegram_update,
    telegram_ready,
)

STATUS_TONES = {
    "Not Reported": "metric-red",
    "In Progress": "metric-blue",
    "Complete": "metric-green",
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
        .helper-text {
            font-size: 0.9rem;
            color: #334155;
            font-style: italic;
            line-height: 1.5;
            margin: 0.1rem 0 0.65rem 0;
        }
        .section-title {
            font-size: 1.05rem;
            font-weight: 800;
            color: #0f172a;
            margin: 0.8rem 0 0.45rem 0;
        }
        .history-line {
            font-size: 0.96rem;
            color: #0f172a;
            font-weight: 600;
            margin: 0.15rem 0;
        }
        .history-meta {
            font-size: 0.9rem;
            color: #334155;
            line-height: 1.45;
            margin: 0 0 0.7rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_session_state() -> None:
    st.session_state.setdefault("loaded_board_key", "")
    st.session_state.setdefault("board_state", empty_board_state())
    st.session_state.setdefault("storage_source", "New board")
    st.session_state.setdefault("persist_message", "Belum disimpan.")
    st.session_state.setdefault("current_user", "QC Leader")
    st.session_state.setdefault("telegram_preview_parts", [])
    st.session_state.setdefault("pending_toast", "")


def ensure_board_loaded(worksheet: Any, today_key: str, day: date, shift_name: str) -> None:
    if st.session_state.loaded_board_key == today_key:
        return
    board, source = load_board_state(worksheet, today_key, day, shift_name)
    st.session_state.board_state = board
    st.session_state.loaded_board_key = today_key
    st.session_state.storage_source = source
    st.session_state.persist_message = f"Loaded from {source}"
    st.session_state["today_setup_selected_reports"] = list(board["setup"]["active_report_ids"])
    st.session_state["today_setup_general_note"] = str(board.get("general_note", ""))


def commit_board_change(
    worksheet: Any,
    today_key: str,
    shift_name: str,
    actor: str,
    notice: str,
    *,
    telegram_event: dict[str, Any] | None = None,
    retry_telegram: bool = False,
) -> None:
    st.session_state["telegram_preview_parts"] = []
    message = save_board_state(worksheet, today_key, shift_name, actor, st.session_state.board_state)
    telegram_message = ""
    if telegram_event or retry_telegram:
        telegram_message = sync_telegram_update(
            st.session_state.board_state,
            today_key,
            shift_name,
            event=telegram_event,
            retry_pending=retry_telegram,
        )
        message = f"{message} | {save_board_state(worksheet, today_key, shift_name, actor, st.session_state.board_state)}"
    st.session_state.board_state = normalize_board_state(st.session_state.board_state)
    if telegram_message:
        st.session_state.persist_message = f"{notice} | {message} | {telegram_message}"
    else:
        st.session_state.persist_message = f"{notice} | {message}"
    st.rerun()


def tone_for_status(status: str) -> str:
    if status == "Not Reported":
        return "status-red"
    if status == "Complete":
        return "status-green"
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
    pills: list[str] = []
    if report_eval["status"]:
        pills.append(
            f'<span class="status-pill {tone_for_status(report_eval["status"])}">{report_eval["status"]}</span>'
        )
    return "".join(pills)


def report_option_label(report_id: str) -> str:
    report = REPORTS[report_id]
    return f"{report['code']} | {report['label']} | {report['department']}"


def render_helper_text(text: str) -> None:
    st.markdown(f'<div class="helper-text">{text}</div>', unsafe_allow_html=True)


def render_section_title(text: str) -> None:
    st.markdown(f'<div class="section-title">{text}</div>', unsafe_allow_html=True)


def build_active_report_rows(active_ids: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    ordered = [report_id for report_id in REPORT_ORDER if report_id in active_ids]
    for report_id in ordered:
        report = REPORTS[report_id]
        rows.append(
            {
                "code": report["code"],
                "full report name": report["label"],
                "department": report["department"],
                "interval": report["frequency_label"],
                "short description": report["description"],
            }
        )
    return rows


def slot_key_for_reference_time(schedule: list[dict[str, Any]], reference_time: datetime) -> str:
    if not schedule:
        return ""
    due_slots = [slot for slot in schedule if slot["due_at"] <= reference_time]
    if due_slots:
        return due_slots[-1]["slot_key"]
    return schedule[0]["slot_key"]


def parse_submitted_at(schedule: list[dict[str, Any]], submitted_at_text: str) -> datetime | None:
    if not schedule:
        return None
    text = submitted_at_text.strip()
    if not text:
        return None
    for fmt in ("%H:%M", "%H:%M:%S", "%H%M"):
        try:
            parsed = datetime.strptime(text, fmt).time()
            return datetime.combine(schedule[0]["due_at"].date(), parsed)
        except ValueError:
            continue
    return None


def parse_flexible_datetime_text(reference_day: date, text: str) -> datetime | None:
    value = text.strip()
    if not value:
        return None
    for fmt in ("%H:%M", "%H%M"):
        try:
            parsed = datetime.strptime(value, fmt).time()
            return datetime.combine(reference_day, parsed)
        except ValueError:
            continue
    for fmt in ("%m-%d %H:%M", "%m%d %H%M", "%m/%d %H:%M"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.replace(year=reference_day.year)
        except ValueError:
            continue
    return None


def fill_now_time_field(key: str) -> None:
    st.session_state[key] = now_local().strftime("%H%M")


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
    slot_label_map = {slot["slot_key"]: f"{slot['label']} ({slot['due_label']})" for slot in schedule}
    submitted_at_key = f"submitted_at_input_{report_id}"
    submitter_key = f"submitter_input_{report_id}"
    summary_key = f"submit_summary_{report_id}"
    st.session_state.setdefault(submitted_at_key, "")
    st.session_state.setdefault(submitter_key, "")
    st.session_state.setdefault(summary_key, "")

    with st.container(border=True):
        st.markdown(f"**{report['code']} {report['label']}**")
        st.markdown(render_status_pills(report_eval), unsafe_allow_html=True)
        st.caption(
            f"{report_eval['department']} | {report_eval['frequency_label']} | "
            f"Latest due: {report_eval['latest_due_label']} {display_time(report_eval['latest_due_at'])}"
        )
        render_helper_text(report["description"])

        info_cols = st.columns(2)
        with info_cols[0]:
            st.write(f"Submitted: {display_dt(report_eval['submitted_at'])}")
            st.write(f"Submitted by: {report_eval['submitted_by'] or '-'}")
            st.write(f"Summary: {report_eval['submission_summary'] or '-'}")
        with info_cols[1]:
            st.write(f"Last slot due: {display_dt(report_eval['last_slot_due_at'])}")
            st.write(f"Status updated: {display_dt(report_eval['status_updated_at'])}")

        with st.expander("Actions", expanded=False):
            submitted_time_cols = st.columns([5, 1])
            with submitted_time_cols[0]:
                submitted_at_text = st.text_input(
                    "Submitted at",
                    key=submitted_at_key,
                    placeholder="08:05 / 0805",
                )
            with submitted_time_cols[1]:
                st.write("")
                st.button(
                    "NOW",
                    key=f"now_{submitted_at_key}",
                    use_container_width=True,
                    on_click=fill_now_time_field,
                    args=(submitted_at_key,),
                )
            submitter = st.text_input(
                "Submitted by",
                key=submitter_key,
                placeholder="TL Kupas / QC Rossa / Admin Gudang",
            )
            summary_text = st.text_area(
                "Ringkasan laporan / Action Tindakan",
                key=summary_key,
                height=120,
                placeholder="Short report summary and tindakan in one field",
            )
            submit_clicked = st.button("Record Submission", key=f"submit_btn_{report_id}", use_container_width=True)

            if submit_clicked:
                before_status = report_eval["status"]
                recorded_at = parse_submitted_at(schedule, submitted_at_text)
                if not recorded_at:
                    st.error("Submitted at must be entered as HH:MM or HHMM, for example 08:05 or 0805.")
                    return
                slot_key = slot_key_for_reference_time(schedule, recorded_at)
                record_submission(
                    board,
                    report_id,
                    slot_key,
                    submitter.strip() or current_user,
                    summary=summary_text,
                    action_text="",
                    recorded_at=recorded_at,
                    shift_name=shift_name,
                )
                updated_view = build_board_view(board, shift_name, now=recorded_at)
                updated_eval = next(
                    (item for item in updated_view["active_reports"] if item["report_id"] == report_id),
                    None,
                )
                after_status = updated_eval["status"] if updated_eval else before_status
                if after_status == "Complete" and before_status != "Complete":
                    st.session_state["pending_toast"] = f"{report['code']} complete. Today's required submissions are done."
                    notice = f"{report['code']} submission recorded | status now Complete"
                else:
                    st.session_state["pending_toast"] = f"{report['code']} submission saved."
                    notice = f"{report['code']} submission recorded"
                commit_board_change(
                    worksheet,
                    today_key,
                    shift_name,
                    submitter.strip() or current_user,
                    notice,
                )

        history_items = list(reversed(board["reports"][report_id]["submissions"]))
        history_label = f"Today submission history ({len(history_items)})"
        with st.expander(history_label, expanded=False):
            if history_items:
                for entry in history_items:
                    slot_label = slot_label_map.get(entry.get("slot_key", ""), entry.get("slot_key", "-"))
                    st.markdown(
                        f'<div class="history-line">{display_dt(entry.get("submitted_at", ""))} | '
                        f'{entry.get("submitted_by", "") or "-"} | {slot_label}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div class="history-meta">Summary: {entry.get("summary", "") or "-"} | '
                        f'Action: {entry.get("action_text", "") or "-"}</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.info("No submission history for this report yet.")


def render_today_setup_form(
    worksheet: Any,
    today_key: str,
    shift_name: str,
    current_user: str,
    board: dict[str, Any],
    *,
    expanded: bool,
    gate_mode: bool,
) -> None:
    title = "Today Setup / Active Reports"
    context = st.container(border=True) if gate_mode else st.expander(title, expanded=expanded)
    with context:
        if gate_mode:
            st.subheader(title)
            st.info("Select today's active reports first. The board will appear only after setup is saved.")
        else:
            render_helper_text("Only today's active reports will be calculated on the board. All others move to OFF TODAY.")

        selected_reports = st.multiselect(
            "Active reports for today",
            options=REPORT_ORDER,
            key="today_setup_selected_reports",
            format_func=report_option_label,
        )
        general_note = st.text_area(
            "General note (optional)",
            key="today_setup_general_note",
        )
        setup_clicked = st.button("Save Today Setup", key="today_setup_save_btn", use_container_width=True)

        active_rows = build_active_report_rows(selected_reports)
        if active_rows:
            render_helper_text("Selected active reports are expanded below in full so names do not get truncated in the multiselect.")
            st.dataframe(active_rows, use_container_width=True, hide_index=True)
        else:
            render_helper_text("No active reports are selected yet.")

        if setup_clicked:
            first_setup = not board["setup"]["setup_completed"]
            if first_setup:
                reset_operational_state(board)
            board["general_note"] = general_note.strip()
            update_active_reports(board, selected_reports, current_user)
            commit_board_change(worksheet, today_key, shift_name, current_user, "Today Setup saved")

        if board["setup"]["updated_at"]:
            render_helper_text(
                f"Setup updated: {display_dt(board['setup']['updated_at'])} | "
                f"by {board['setup']['updated_by'] or '-'}"
            )


def render_report_groups(
    worksheet: Any,
    today_key: str,
    shift_name: str,
    current_user: str,
    board_view: dict[str, Any],
) -> None:
    st.subheader("Report Status Board")
    render_helper_text("Only today's active reports are shown below, grouped by interval for faster scanning.")

    group_order = [
        ("1. 30 min reports", "30 min reports"),
        ("2. 1 hour reports", "1 hour reports"),
        ("3. shift reports", "shift reports"),
    ]
    for display_title, group_title in group_order:
        items = board_view["active_reports_by_group"][group_title]
        if not items:
            continue
        with st.expander(display_title, expanded=True):
            for index in range(0, len(items), 2):
                cols = st.columns(2)
                for col, report_eval in zip(cols, items[index:index + 2]):
                    with col:
                        render_report_card(worksheet, today_key, shift_name, current_user, report_eval)


def main() -> None:
    configure_page()
    init_session_state()
    worksheet = get_worksheet()

    st.title("QC Supervisory Board v1")
    render_helper_text("current track / ready for immediate operational use")
    toast_message = st.session_state.pop("pending_toast", "")
    if toast_message:
        st.toast(toast_message, icon="✅")

    header_cols = st.columns([1.2, 1, 1])
    with header_cols[0]:
        current_user = st.text_input(
            "Current actor",
            value=st.session_state.get("current_user", "QC Leader"),
            placeholder="QC Uyun / Rossa / Yuni",
        ).strip() or "QC Leader"
        st.session_state["current_user"] = current_user
    with header_cols[1]:
        shift_name = st.selectbox(
            "Shift",
            options=["Shift 1 (Pagi)", "Shift Tengah", "Shift 2 (Sore)"],
            key="shift_name",
        )
    with header_cols[2]:
        today = now_local().date()
        st.text_input("Today", value=today.isoformat(), disabled=True)

    today_key = f"{today.isoformat()} ({shift_name})"
    ensure_board_loaded(worksheet, today_key, today, shift_name)
    board = st.session_state.board_state

    render_helper_text(
        f"Storage source: {st.session_state.storage_source} | "
        f"Key: {today_key} | {st.session_state.persist_message}"
    )
    if worksheet is None:
        st.warning("Google Sheet connection is unavailable. Actions will still save to local cache.")
        last_sheet_error = get_last_sheet_error()
        if last_sheet_error:
            st.error(f"Google Sheet error: {last_sheet_error}")
        debug_info = get_service_account_debug_info()
        st.caption(
            "Sheet debug | "
            f"has gcp_service_account: {debug_info['has_gcp_service_account']} | "
            f"type: {debug_info['gcp_service_account_type']} | "
            f"local credentials.json: {debug_info['local_credentials_json']}"
        )
    else:
        st.info("Google Sheet connection is active. Actions will save to Google Sheet and local cache.")

    telegram = ensure_telegram_cycle(board, today_key)
    with st.expander("Telegram Flow", expanded=False):
        render_helper_text("Record Submission hanya menyimpan update internal board. Preview Telegram Summary menunjukkan teks final yang akan dikirim. Send Current Summary to Telegram mengirim ringkasan board saat ini ke thread Telegram.")
        st.write(f"Telegram ready: {'Yes' if telegram_ready() else 'No'}")
        st.write(f"Cycle key: {telegram.get('cycle_key') or today_key}")
        st.write(f"Root message id: {telegram.get('root_message_id') or '-'}")
        st.write(f"Last sent at: {display_dt(telegram.get('last_sent_at', ''))}")
        st.write(f"Pending notice: {'Yes' if (telegram.get('pending_notice') or {}).get('text') else 'No'}")
        if telegram.get("last_error"):
            st.warning(f"Last Telegram error: {telegram['last_error']}")
        tg_cols = st.columns(4)
        with tg_cols[0]:
            if st.button("Preview Telegram Summary", use_container_width=True):
                st.session_state["telegram_preview_parts"] = build_current_summary_parts(
                    board,
                    today_key,
                    shift_name,
                    current_user,
                )
        with tg_cols[1]:
            if st.button("Send Current Summary to Telegram", use_container_width=True):
                telegram_message = send_current_summary_to_telegram(
                    board,
                    today_key,
                    shift_name,
                    current_user,
                )
                message = save_board_state(worksheet, today_key, shift_name, current_user, board)
                st.session_state.board_state = normalize_board_state(board)
                st.session_state.persist_message = f"Telegram summary send requested | {message} | {telegram_message}"
                st.rerun()
        with tg_cols[2]:
            if st.button(
                "Retry Pending Telegram",
                use_container_width=True,
                disabled=not (telegram.get("pending_notice") or {}).get("text"),
            ):
                commit_board_change(
                    worksheet,
                    today_key,
                    shift_name,
                    current_user,
                    "Telegram retry requested",
                    retry_telegram=True,
                )
        with tg_cols[3]:
            if st.button("Start New Telegram Cycle", use_container_width=True):
                start_new_telegram_cycle(board, today_key)
                commit_board_change(worksheet, today_key, shift_name, current_user, "New Telegram cycle started")
        preview_parts = st.session_state.get("telegram_preview_parts") or []
        if preview_parts:
            render_helper_text("Preview below shows the exact current-summary text that will be sent to Telegram.")
            for index, part in enumerate(preview_parts, start=1):
                st.text_area(
                    f"Telegram preview part {index}",
                    value=part,
                    height=240,
                    disabled=True,
                    key=f"telegram_preview_display_{index}",
                )

    if not board["setup"]["setup_completed"]:
        render_today_setup_form(
            worksheet=worksheet,
            today_key=today_key,
            shift_name=shift_name,
            current_user=current_user,
            board=board,
            expanded=True,
            gate_mode=True,
        )
        return

    board_view = build_board_view(board, shift_name, now=now_local())
    summary_cols = st.columns([1, 1, 1, 1.2])
    summary_notes = {
        "Not Reported": "A required latest due slot is still missing.",
        "In Progress": "The latest required report is already submitted and the day is still ongoing.",
        "Complete": "All required slots for today are already reported.",
    }
    metric_titles = [
        "Not Reported",
        "In Progress",
        "Complete",
    ]

    for col, title in zip(summary_cols[:3], metric_titles):
        with col:
            st.markdown(
                render_metric_card(title, board_view["summary"][title], summary_notes[title]),
                unsafe_allow_html=True,
            )

    with summary_cols[3]:
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

    render_today_setup_form(
        worksheet=worksheet,
        today_key=today_key,
        shift_name=shift_name,
        current_user=current_user,
        board=board,
        expanded=False,
        gate_mode=False,
    )

    render_report_groups(
        worksheet=worksheet,
        today_key=today_key,
        shift_name=shift_name,
        current_user=current_user,
        board_view=board_view,
    )

    with st.expander("Active Exception Instructions", expanded=True):
        with st.container(border=True):
            render_helper_text("This area shows active operating exceptions that are still in effect.")

            exc_started_key = "exception_started_at"
            exc_estimated_key = "exception_estimated_end_at"
            st.session_state.setdefault(exc_started_key, "")
            st.session_state.setdefault(exc_estimated_key, "")
            exc_row_1 = st.columns([1.8, 1.2, 1.1, 1.1])
            with exc_row_1[0]:
                instruction_text = st.text_input("Instruction")
            with exc_row_1[1]:
                related_target = st.text_input("Bagian / Report")
            with exc_row_1[2]:
                checked_by_team = st.text_input("Dicek oleh")
            with exc_row_1[3]:
                worker_name = st.text_input("Pekerja")
            exc_row_2 = st.columns([1.1, 1.1, 1.2, 0.45, 1.2, 0.45])
            with exc_row_2[0]:
                instructed_by = st.text_input("Beri instruksi")
            with exc_row_2[1]:
                approved_by = st.text_input("Approved by / Disetujui oleh")
            with exc_row_2[2]:
                started_at_text = st.text_input("Exception mulai", key=exc_started_key, placeholder="13:30 / 1330")
            with exc_row_2[3]:
                st.write("")
                st.button("NOW", key="now_exception_start", on_click=fill_now_time_field, args=(exc_started_key,), use_container_width=True)
            with exc_row_2[4]:
                estimated_end_text = st.text_input("Estimasi selesai", key=exc_estimated_key, placeholder="15:00 / 1500")
            with exc_row_2[5]:
                st.write("")
                st.button("NOW", key="now_exception_end", on_click=fill_now_time_field, args=(exc_estimated_key,), use_container_width=True)
            exc_submit = st.button("Add Exception Instruction", key="add_exception_btn", use_container_width=True)

            if exc_submit and instruction_text.strip():
                started_at_value = parse_flexible_datetime_text(today, started_at_text)
                if not started_at_value:
                    st.error("Exception mulai must be entered as HH:MM or HHMM, for example 13:30 or 1330.")
                    return
                estimated_end_value = parse_flexible_datetime_text(today, estimated_end_text) if estimated_end_text.strip() else None
                add_exception_instruction(
                    board,
                    instruction_text=instruction_text,
                    related_department_or_report=related_target,
                    actor=current_user,
                    recorded_at=started_at_value,
                    checked_by_team=checked_by_team,
                    worker_name=worker_name,
                    instructed_by=instructed_by or current_user,
                    approved_by=approved_by,
                    estimated_end_at=dt_to_storage(estimated_end_value) if estimated_end_value else "",
                )
                st.session_state["pending_toast"] = "Exception instruction saved."
                commit_board_change(
                    worksheet,
                    today_key,
                    shift_name,
                    current_user,
                    "Exception Instruction added",
                )

            if board_view["active_instructions"]:
                for instruction in board_view["active_instructions"]:
                    with st.container(border=True):
                        st.markdown('<span class="status-pill status-blue">Masih berlaku</span>', unsafe_allow_html=True)
                        exc_display_1 = st.columns([1.8, 1.1, 1.1, 1.1])
                        with exc_display_1[0]:
                            st.write(f"Instruction: {instruction['instruction_text'] or '-'}")
                        with exc_display_1[1]:
                            st.write(f"Bagian: {instruction['related_department_or_report'] or '-'}")
                        with exc_display_1[2]:
                            st.write(f"Dicek: {instruction.get('checked_by_team') or '-'}")
                        with exc_display_1[3]:
                            st.write(f"Pekerja: {instruction.get('worker_name') or '-'}")
                        exc_display_2 = st.columns([1.1, 1.1, 1, 1])
                        with exc_display_2[0]:
                            st.write(f"Beri instruksi: {instruction.get('instructed_by') or '-'}")
                        with exc_display_2[1]:
                            st.write(f"Approved by: {instruction.get('approved_by') or '-'}")
                        with exc_display_2[2]:
                            st.write(f"Mulai: {display_dt(instruction['started_at'])}")
                        with exc_display_2[3]:
                            st.write(f"Estimasi selesai: {display_dt(instruction.get('estimated_end_at', ''))}")
                        if instruction.get("handover_at"):
                            st.markdown(
                                f'<div class="history-meta">Still active and handed over at {display_dt(instruction.get("handover_at", ""))} '
                                f'by {instruction.get("handover_by") or "-"} to {instruction.get("handover_to") or "-"} | '
                                f'Informed next team: {"Yes" if instruction.get("informed_next_team") else "No"} | '
                                f'Note: {instruction.get("handover_note") or "-"}</div>',
                                unsafe_allow_html=True,
                            )

                        with st.expander("Still active, hand over to next shift", expanded=False):
                            handover_time_key = f"handover_time_{instruction['id']}"
                            st.session_state.setdefault(handover_time_key, "")
                            handover_cols = st.columns([1.2, 0.45, 1.2, 1.2])
                            with handover_cols[0]:
                                handover_time_text = st.text_input(
                                    "Handover at",
                                    key=handover_time_key,
                                    placeholder="18:00 / 1800",
                                )
                            with handover_cols[1]:
                                st.write("")
                                st.button(
                                    "NOW",
                                    key=f"now_handover_{instruction['id']}",
                                    on_click=fill_now_time_field,
                                    args=(handover_time_key,),
                                    use_container_width=True,
                                )
                            with handover_cols[2]:
                                active_handover_to = st.text_input(
                                    "Handover to",
                                    key=f"active_handover_to_{instruction['id']}",
                                    placeholder="TL shift berikutnya / nama pekerja",
                                )
                            with handover_cols[3]:
                                active_handover_note = st.text_input(
                                    "Catatan handover",
                                    key=f"active_handover_note_{instruction['id']}",
                                    placeholder="Masih lanjut di shift berikutnya",
                                )
                            active_informed = st.checkbox(
                                "Yes, TL dan pekerja shift selanjutnya sudah diberi tahu",
                                key=f"active_handover_confirm_{instruction['id']}",
                            )
                            if st.button("Still active, save handover", key=f"handover_instruction_{instruction['id']}"):
                                handover_at = parse_flexible_datetime_text(today, handover_time_text)
                                if not handover_at:
                                    st.error("Handover at must be entered as HH:MM, HHMM, or MM-DD HH:MM.")
                                    return
                                if not active_handover_to.strip():
                                    st.error("Please fill who this active exception was handed over to.")
                                    return
                                if not active_informed:
                                    st.error("Please confirm that the next TL / pekerja has been informed.")
                                    return
                                handover_exception_instruction(
                                    board,
                                    instruction["id"],
                                    current_user,
                                    handover_to=active_handover_to,
                                    handover_note=active_handover_note,
                                    informed_next_team=True,
                                    recorded_at=handover_at,
                                )
                                st.session_state["pending_toast"] = "Exception handover saved."
                                commit_board_change(worksheet, today_key, shift_name, current_user, "Exception Instruction handed over")

                        with st.expander("Selesai / handover", expanded=False):
                            finished_key = f"finish_time_{instruction['id']}"
                            st.session_state.setdefault(finished_key, "")
                            finished_at_text = st.text_input(
                                "Finished at",
                                key=finished_key,
                                placeholder="03-30 18:20 / 1820",
                            )
                            st.button(
                                "NOW",
                                key=f"now_finish_{instruction['id']}",
                                on_click=fill_now_time_field,
                                args=(finished_key,),
                            )
                            informed_next_team = st.checkbox(
                                "Yes, exception ini sudah selesai dan sudah diberi tahu kepada TL dan pekerja selanjutnya",
                                key=f"finish_confirm_{instruction['id']}",
                            )
                            finish_cols = st.columns(2)
                            with finish_cols[0]:
                                handover_to = st.text_input(
                                    "Kalau sempat handover, berikutnya ke siapa",
                                    key=f"handover_to_{instruction['id']}",
                                    placeholder="TL shift berikutnya / nama pekerja",
                                )
                            with finish_cols[1]:
                                handover_note = st.text_input(
                                    "Catatan handover",
                                    key=f"handover_note_{instruction['id']}",
                                    placeholder="Dilanjutkan shift 2 / tunggu material / dll",
                                )
                            if st.button("Yes, mark Selesai", key=f"finish_instruction_{instruction['id']}"):
                                finished_at = parse_flexible_datetime_text(today, finished_at_text)
                                if not finished_at:
                                    st.error("Finished at must be entered as HH:MM, HHMM, or MM-DD HH:MM.")
                                    return
                                if not informed_next_team:
                                    st.error("Please confirm that TL and the next worker have been informed before closing.")
                                    return
                                finish_exception_instruction(
                                    board,
                                    instruction["id"],
                                    current_user,
                                    recorded_at=finished_at,
                                    handover_to=handover_to,
                                    handover_note=handover_note,
                                    informed_next_team=True,
                                )
                                st.session_state["pending_toast"] = "Exception marked selesai."
                                commit_board_change(worksheet, today_key, shift_name, current_user, "Exception Instruction closed")
            else:
                st.info("There are no active Exception Instructions right now.")

            if board_view["completed_instructions"]:
                with st.expander("Completed Exception Instructions", expanded=False):
                    for instruction in board_view["completed_instructions"]:
                        with st.container(border=True):
                            st.markdown('<span class="status-pill status-slate">Selesai</span>', unsafe_allow_html=True)
                            st.write(instruction["instruction_text"])
                            st.markdown(
                                f'<div class="history-meta">Bagian: {instruction["related_department_or_report"] or "-"} | '
                                f'Dicek: {instruction.get("checked_by_team") or "-"} | '
                                f'Pekerja: {instruction.get("worker_name") or "-"}</div>'
                                f'<div class="history-meta">Beri instruksi: {instruction.get("instructed_by") or "-"} | '
                                f'Approved by: {instruction.get("approved_by") or "-"} | '
                                f'Mulai: {display_dt(instruction["started_at"])} | '
                                f'Estimasi selesai: {display_dt(instruction.get("estimated_end_at", ""))}</div>'
                                f'<div class="history-meta">Selesai: {display_dt(instruction["ended_at"])} | '
                                f'Closed by: {instruction.get("ended_by") or "-"} | '
                                f'Informed next team: {"Yes" if instruction.get("informed_next_team") else "No"} | '
                                f'Handover to: {instruction.get("handover_to") or "-"}</div>'
                                f'<div class="history-meta">Catatan handover: {instruction.get("handover_note") or "-"}</div>',
                                unsafe_allow_html=True,
                            )

    off_today_reports = board_view["off_today_reports"]
    with st.expander(f"OFF TODAY ({len(off_today_reports)})", expanded=False):
        render_helper_text("Reports not selected in Today Setup are listed here only.")
        if off_today_reports:
            for report_eval in off_today_reports:
                with st.container(border=True):
                    st.write(f"{report_eval['code']} | {report_eval['name']}")
                    st.markdown(
                        f'<div class="history-meta">{report_eval["department"]} | inactive in Today Setup</div>',
                        unsafe_allow_html=True,
                    )
        else:
            st.info("There are no reports in OFF TODAY.")


if __name__ == "__main__":
    main()
