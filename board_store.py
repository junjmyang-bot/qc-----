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
    board_has_meaningful_data,
    build_board_view,
    build_slot_schedule,
    display_time,
    dt_to_storage,
    empty_board_state,
    empty_report_state,
    now_local,
    normalize_board_state,
    serialize_global_state,
    serialize_report_state,
)

SHEET_URL = "https://docs.google.com/spreadsheets/d/1kR2C_7IxC_5FpztsWQaBMT8EtbcDHerKL6YLGfQucWw/edit"
LOCAL_CACHE_PATH = Path(__file__).with_name("board_state_local.json")
CREDENTIALS_PATH = Path(__file__).with_name("credentials.json")

PROGRESS_30 = ["a4", "a5", "b3", "b4", "b5", "b9"]
PROGRESS_1H = ["a8", "b2", "b6", "b7", "b8", "b10"]
ROUTINE_SHIFT = ["a1", "a2", "a3", "a6", "a7", "a9", "b1"]


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
    if worksheet is None:
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
                if isinstance(payload.get("telegram"), dict):
                    board["telegram"] = payload["telegram"]
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
    if worksheet is None:
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
    now = now_local()
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
        comment = (
            f"{report_eval['department']} | {report_eval['frequency_label']} | "
            f"Due {report_eval['latest_due_label']} {display_time(report_eval['latest_due_at'])}\n"
            f"Submitted: {submitted_summary}\n"
            f"Summary: {report_eval['submission_summary'] or '-'}\n"
            f"Action: {report_eval['submission_action_text'] or '-'}"
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
