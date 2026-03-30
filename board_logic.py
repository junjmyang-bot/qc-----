from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import uuid4

REPORT_ORDER = [
    "a4",
    "a5",
    "b3",
    "b4",
    "b5",
    "b9",
    "a8",
    "b2",
    "b6",
    "b7",
    "b8",
    "b10",
    "a1",
    "a2",
    "a3",
    "a6",
    "a7",
    "a9",
    "b1",
]

STATUS_ORDER = {
    "Not Reported": 0,
    "In Progress": 1,
    "Complete": 2,
    "": 3,
}

SHIFT_SCHEDULES = {
    "Shift 1 (Pagi)": {
        "start": time(7, 0),
        "break": time(12, 0),
        "mid": time(11, 0),
        "end": time(15, 0),
    },
    "Shift Tengah": {
        "start": time(11, 0),
        "break": time(15, 0),
        "mid": time(15, 0),
        "end": time(19, 0),
    },
    "Shift 2 (Sore)": {
        "start": time(15, 0),
        "break": time(19, 0),
        "mid": time(19, 0),
        "end": time(23, 0),
    },
}

REPORTS = {
    "a4": {
        "code": "A-4",
        "label": "Laporan QC di Tablet",
        "department": "QC",
        "frequency_label": "30 min",
        "kind": "interval",
        "interval_minutes": 30,
        "slot_count": 16,
        "description": "Kebersihan, kontaminan, kondisi line",
    },
    "a5": {
        "code": "A-5",
        "label": "Status Tes Steam",
        "department": "Steam",
        "frequency_label": "30 min",
        "kind": "interval",
        "interval_minutes": 30,
        "slot_count": 10,
        "description": "Update tes steam saat jam operasi utama",
    },
    "b3": {
        "code": "B-3",
        "label": "Laporan Situasi Kupas",
        "department": "Kupas",
        "frequency_label": "30 min",
        "kind": "interval",
        "interval_minutes": 30,
        "slot_count": 16,
        "description": "Kondisi line kupas dan kebutuhan tindak lanjut",
    },
    "b4": {
        "code": "B-4",
        "label": "Laporan Situasi Packing",
        "department": "Packing",
        "frequency_label": "30 min",
        "kind": "interval",
        "interval_minutes": 30,
        "slot_count": 16,
        "description": "Kondisi line packing dan koordinasi TL",
    },
    "b5": {
        "code": "B-5",
        "label": "Hasil Per Jam",
        "department": "Produksi",
        "frequency_label": "30 min",
        "kind": "interval",
        "interval_minutes": 30,
        "slot_count": 16,
        "description": "Output per jam dan ketepatan laporan",
    },
    "b9": {
        "code": "B-9",
        "label": "Laporan Kondisi BB",
        "department": "Bahan Baku",
        "frequency_label": "30 min",
        "kind": "interval",
        "interval_minutes": 30,
        "slot_count": 16,
        "description": "Kondisi bahan baku dan isu kualitas",
    },
    "a8": {
        "code": "A-8",
        "label": "Status Barang Jatuh",
        "department": "QC",
        "frequency_label": "1 hour",
        "kind": "interval",
        "interval_minutes": 60,
        "slot_count": 8,
        "description": "Barang jatuh di area kupas, packing, steam, dry",
    },
    "b2": {
        "code": "B-2",
        "label": "Laporan Status Steam",
        "department": "Steam",
        "frequency_label": "1 hour",
        "kind": "interval",
        "interval_minutes": 60,
        "slot_count": 8,
        "description": "Status steam, kendala, dan kepatuhan laporan",
    },
    "b6": {
        "code": "B-6",
        "label": "Laporan Giling",
        "department": "Giling",
        "frequency_label": "1 hour",
        "kind": "interval",
        "interval_minutes": 60,
        "slot_count": 8,
        "description": "Monitoring line giling reguler",
    },
    "b7": {
        "code": "B-7",
        "label": "Laporan Giling (Steril)",
        "department": "Giling Steril",
        "frequency_label": "1 hour",
        "kind": "interval",
        "interval_minutes": 60,
        "slot_count": 8,
        "description": "Monitoring line steril dan kebutuhan kontrol",
    },
    "b8": {
        "code": "B-8",
        "label": "Laporan Potong",
        "department": "Potong",
        "frequency_label": "1 hour",
        "kind": "interval",
        "interval_minutes": 60,
        "slot_count": 8,
        "description": "Setting mesin, nata, dan kondisi line potong",
    },
    "b10": {
        "code": "B-10",
        "label": "Laporan Dry",
        "department": "Dry",
        "frequency_label": "1 hour",
        "kind": "interval",
        "interval_minutes": 60,
        "slot_count": 8,
        "description": "Status line dry dan kebutuhan tindak lanjut",
    },
    "a1": {
        "code": "A-1",
        "label": "Cek Stok BB Steam",
        "department": "Steam",
        "frequency_label": "shift",
        "kind": "named",
        "slot_blueprint": [
            {"key": "awal", "label": "Awal", "anchor": "start", "offset_minutes": 0},
            {"key": "istirahat", "label": "Istirahat", "anchor": "break", "offset_minutes": 0},
        ],
        "description": "Cek stok bahan baku steam di awal dan istirahat",
    },
    "a2": {
        "code": "A-2",
        "label": "Cek Stok BS",
        "department": "BS / Defrost",
        "frequency_label": "shift",
        "kind": "named",
        "slot_blueprint": [
            {"key": "cek_1", "label": "Cek 1", "anchor": "start", "offset_minutes": 60},
            {"key": "cek_2", "label": "Cek 2", "anchor": "break", "offset_minutes": 0},
        ],
        "description": "Cek stok BS / defrost selama shift berjalan",
    },
    "a3": {
        "code": "A-3",
        "label": "Handover IN",
        "department": "Handover",
        "frequency_label": "shift",
        "kind": "named",
        "slot_blueprint": [
            {"key": "handover_in", "label": "Handover", "anchor": "start", "offset_minutes": 0},
        ],
        "description": "Penerimaan handover dari shift sebelumnya",
    },
    "a6": {
        "code": "A-6",
        "label": "List BB Butuh Kirim",
        "department": "Logistik BB",
        "frequency_label": "shift",
        "kind": "named",
        "slot_blueprint": [
            {"key": "jam_12", "label": "Jam 12", "anchor": "mid", "offset_minutes": 0},
            {"key": "pulang", "label": "Pulang", "anchor": "end", "offset_minutes": -15},
        ],
        "description": "Daftar bahan baku yang perlu dikirim sebelum akhir shift",
    },
    "a7": {
        "code": "A-7",
        "label": "Handover & Rencana",
        "department": "Handover",
        "frequency_label": "shift",
        "kind": "named",
        "slot_blueprint": [
            {"key": "handover_out", "label": "Handover", "anchor": "end", "offset_minutes": -15},
        ],
        "description": "Handover keluar dan rencana shift berikutnya",
    },
    "a9": {
        "code": "A-9",
        "label": "Sisa Barang",
        "department": "Closing",
        "frequency_label": "shift",
        "kind": "named",
        "slot_blueprint": [
            {"key": "closing", "label": "Closing", "anchor": "end", "offset_minutes": -15},
        ],
        "description": "Cek sisa barang saat closing shift",
    },
    "b1": {
        "code": "B-1",
        "label": "Cek Laporan Absensi",
        "department": "Absensi",
        "frequency_label": "shift",
        "kind": "named",
        "slot_blueprint": [
            {"key": "awal", "label": "Awal", "anchor": "start", "offset_minutes": 0},
            {"key": "istirahat", "label": "Istirahat", "anchor": "break", "offset_minutes": 0},
        ],
        "description": "Cek laporan absensi di awal dan istirahat",
    },
}


def now_local() -> datetime:
    return datetime.now()


def dt_to_storage(value: datetime | None) -> str:
    return value.isoformat(timespec="seconds") if value else ""


def dt_from_storage(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def display_dt(value: str, fallback: str = "-") -> str:
    parsed = dt_from_storage(value)
    return parsed.strftime("%Y-%m-%d %H:%M") if parsed else fallback


def display_time(value: str, fallback: str = "-") -> str:
    parsed = dt_from_storage(value)
    return parsed.strftime("%H:%M") if parsed else fallback


def anchor_datetime(day: date, shift_name: str, anchor: str, offset_minutes: int = 0) -> datetime:
    schedule = SHIFT_SCHEDULES[shift_name]
    base = datetime.combine(day, schedule[anchor])
    return base + timedelta(minutes=offset_minutes)


def build_slot_schedule(report_id: str, day: date, shift_name: str) -> list[dict[str, Any]]:
    config = REPORTS[report_id]
    slots: list[dict[str, Any]] = []
    if config["kind"] == "interval":
        start = anchor_datetime(day, shift_name, "start")
        interval = config["interval_minutes"]
        for index in range(1, config["slot_count"] + 1):
            due_at = start + timedelta(minutes=interval * (index - 1))
            slots.append(
                {
                    "slot_key": str(index),
                    "label": f"Slot {index}",
                    "short_label": str(index),
                    "due_at": due_at,
                    "due_label": due_at.strftime("%H:%M"),
                    "sequence": index,
                }
            )
        return slots

    for index, blueprint in enumerate(config["slot_blueprint"], start=1):
        due_at = anchor_datetime(
            day,
            shift_name,
            blueprint["anchor"],
            blueprint.get("offset_minutes", 0),
        )
        slots.append(
            {
                "slot_key": blueprint["key"],
                "label": blueprint["label"],
                "short_label": blueprint["label"],
                "due_at": due_at,
                "due_label": due_at.strftime("%H:%M"),
                "sequence": index,
            }
        )
    return slots


def empty_report_state() -> dict[str, Any]:
    return {
        "submissions": [],
        "qc_checks": [],
        "notes": "",
        "status_updated_at": "",
    }


def empty_board_state() -> dict[str, Any]:
    return {
        "version": 1,
        "setup": {
            "setup_completed": False,
            "active_report_ids": [],
            "updated_at": "",
            "updated_by": "",
        },
        "lineup": {
            "lineup_exists": False,
            "lineup_updated_at": "",
            "lineup_updated_by": "",
        },
        "reports": {report_id: empty_report_state() for report_id in REPORT_ORDER},
        "issue_logs": [],
        "exception_instructions": [],
        "general_note": "",
        "telegram": {
            "cycle_key": "",
            "root_message_id": 0,
            "cycle_started_at": "",
            "last_submission_id": "",
            "last_sent_at": "",
            "last_error": "",
            "pending_notice": {
                "kind": "",
                "event_id": "",
                "text": "",
                "reply_to_message_id": 0,
                "created_at": "",
                "remaining_parts": [],
            },
        },
    }


def _normalize_submission(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    slot_key = str(raw.get("slot_key", "")).strip()
    if not slot_key:
        return None
    return {
        "id": str(raw.get("id") or uuid4()),
        "date": str(raw.get("date", "")),
        "shift": str(raw.get("shift", "")),
        "report_code": str(raw.get("report_code", "")),
        "report_name": str(raw.get("report_name", "")),
        "department": str(raw.get("department", "")),
        "interval": str(raw.get("interval", "")),
        "slot_key": slot_key,
        "submitted_at": str(raw.get("submitted_at", "")),
        "submitted_by": str(raw.get("submitted_by", "")),
        "summary": str(raw.get("summary", "")).strip(),
        "action_text": str(raw.get("action_text", "")).strip(),
    }


def _normalize_qc_check(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    submission_id = str(raw.get("submission_id", "")).strip()
    if not submission_id:
        return None
    return {
        "id": str(raw.get("id") or uuid4()),
        "submission_id": submission_id,
        "checked_at": str(raw.get("checked_at", "")),
        "checked_by": str(raw.get("checked_by", "")),
    }


def _normalize_issue_log(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    return {
        "id": str(raw.get("id") or uuid4()),
        "logged_at": str(raw.get("logged_at", "")),
        "related_id": str(raw.get("related_id", "")),
        "related_label": str(raw.get("related_label", "")),
        "problem": str(raw.get("problem", "")),
        "action": str(raw.get("action", "")),
        "entered_by": str(raw.get("entered_by", "")),
    }


def _normalize_instruction(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    return {
        "id": str(raw.get("id") or uuid4()),
        "instruction_text": str(raw.get("instruction_text", "")),
        "related_department_or_report": str(raw.get("related_department_or_report", "")),
        "checked_by_team": str(raw.get("checked_by_team", "")),
        "worker_name": str(raw.get("worker_name", "")),
        "instructed_by": str(raw.get("instructed_by", "")),
        "approved_by": str(raw.get("approved_by", "")),
        "started_at": str(raw.get("started_at", "")),
        "estimated_end_at": str(raw.get("estimated_end_at", "")),
        "started_by": str(raw.get("started_by", "")),
        "handover_to": str(raw.get("handover_to", "")),
        "handover_note": str(raw.get("handover_note", "")),
        "handover_at": str(raw.get("handover_at", "")),
        "handover_by": str(raw.get("handover_by", "")),
        "informed_next_team": bool(raw.get("informed_next_team", False)),
        "is_active": bool(raw.get("is_active", True)),
        "ended_at": str(raw.get("ended_at", "")),
        "ended_by": str(raw.get("ended_by", "")),
    }


def normalize_board_state(raw: Any) -> dict[str, Any]:
    base = empty_board_state()
    if not isinstance(raw, dict):
        return base

    setup = raw.get("setup") if isinstance(raw.get("setup"), dict) else {}
    lineup = raw.get("lineup") if isinstance(raw.get("lineup"), dict) else {}
    reports = raw.get("reports") if isinstance(raw.get("reports"), dict) else {}
    telegram = raw.get("telegram") if isinstance(raw.get("telegram"), dict) else {}

    setup_completed = bool(setup.get("setup_completed", False))
    if not setup_completed and (setup.get("updated_at") or setup.get("updated_by")):
        setup_completed = True

    active_ids = [report_id for report_id in setup.get("active_report_ids", []) if report_id in REPORTS]
    if not setup_completed:
        active_ids = []

    base["setup"] = {
        "setup_completed": setup_completed,
        "active_report_ids": active_ids,
        "updated_at": str(setup.get("updated_at", "")),
        "updated_by": str(setup.get("updated_by", "")),
    }
    base["lineup"] = {
        "lineup_exists": bool(lineup.get("lineup_exists", False)),
        "lineup_updated_at": str(lineup.get("lineup_updated_at", "")),
        "lineup_updated_by": str(lineup.get("lineup_updated_by", "")),
    }
    base["general_note"] = str(raw.get("general_note", ""))
    pending_notice = telegram.get("pending_notice") if isinstance(telegram.get("pending_notice"), dict) else {}
    base["telegram"] = {
        "cycle_key": str(telegram.get("cycle_key", "")),
        "root_message_id": int(telegram.get("root_message_id", 0) or 0),
        "cycle_started_at": str(telegram.get("cycle_started_at", "")),
        "last_submission_id": str(telegram.get("last_submission_id", "")),
        "last_sent_at": str(telegram.get("last_sent_at", "")),
        "last_error": str(telegram.get("last_error", "")),
        "pending_notice": {
            "kind": str(pending_notice.get("kind", "")),
            "event_id": str(pending_notice.get("event_id", "")),
            "text": str(pending_notice.get("text", "")),
            "reply_to_message_id": int(pending_notice.get("reply_to_message_id", 0) or 0),
            "created_at": str(pending_notice.get("created_at", "")),
            "remaining_parts": [
                str(item) for item in pending_notice.get("remaining_parts", []) if str(item).strip()
            ],
        },
    }

    normalized_reports: dict[str, dict[str, Any]] = {}
    for report_id in REPORT_ORDER:
        current = reports.get(report_id) if isinstance(reports.get(report_id), dict) else {}
        submissions = [_normalize_submission(item) for item in current.get("submissions", [])]
        qc_checks = [_normalize_qc_check(item) for item in current.get("qc_checks", [])]
        normalized_reports[report_id] = {
            "submissions": [item for item in submissions if item],
            "qc_checks": [item for item in qc_checks if item],
            "notes": str(current.get("notes", "")),
            "status_updated_at": str(current.get("status_updated_at", "")),
        }
    base["reports"] = normalized_reports

    issue_logs = [_normalize_issue_log(item) for item in raw.get("issue_logs", [])]
    base["issue_logs"] = [item for item in issue_logs if item]

    instructions = [_normalize_instruction(item) for item in raw.get("exception_instructions", [])]
    base["exception_instructions"] = [item for item in instructions if item]
    return base


def board_has_meaningful_data(board: dict[str, Any]) -> bool:
    normalized = normalize_board_state(board)
    if normalized["setup"]["setup_completed"]:
        return True
    if normalized["telegram"]["root_message_id"]:
        return True
    if normalized["lineup"]["lineup_updated_at"]:
        return True
    if normalized["issue_logs"] or normalized["exception_instructions"]:
        return True
    if normalized["general_note"].strip():
        return True
    for report_id in REPORT_ORDER:
        report_state = normalized["reports"][report_id]
        if report_state["submissions"] or report_state["qc_checks"] or report_state["notes"].strip():
            return True
    return False


def set_report_status_updated(board: dict[str, Any], report_id: str, at_text: str) -> None:
    if report_id in board["reports"]:
        board["reports"][report_id]["status_updated_at"] = at_text


def update_active_reports(board: dict[str, Any], active_ids: list[str], actor: str, recorded_at: datetime | None = None) -> None:
    ts = dt_to_storage(recorded_at or now_local())
    board["setup"]["setup_completed"] = True
    board["setup"]["active_report_ids"] = [report_id for report_id in REPORT_ORDER if report_id in active_ids]
    board["setup"]["updated_at"] = ts
    board["setup"]["updated_by"] = actor.strip()


def setup_completed(board: dict[str, Any]) -> bool:
    return bool(normalize_board_state(board)["setup"]["setup_completed"])


def reset_operational_state(board: dict[str, Any]) -> None:
    board["lineup"] = {
        "lineup_exists": False,
        "lineup_updated_at": "",
        "lineup_updated_by": "",
    }
    board["reports"] = {report_id: empty_report_state() for report_id in REPORT_ORDER}
    board["issue_logs"] = []
    board["exception_instructions"] = []


def update_lineup(board: dict[str, Any], exists: bool, actor: str, recorded_at: datetime | None = None) -> None:
    ts = dt_to_storage(recorded_at or now_local())
    board["lineup"]["lineup_exists"] = bool(exists)
    board["lineup"]["lineup_updated_at"] = ts
    board["lineup"]["lineup_updated_by"] = actor.strip()


def record_submission(
    board: dict[str, Any],
    report_id: str,
    slot_key: str,
    actor: str,
    summary: str = "",
    action_text: str = "",
    recorded_at: datetime | None = None,
    shift_name: str = "",
) -> dict[str, str]:
    ts = dt_to_storage(recorded_at or now_local())
    config = REPORTS[report_id]
    submission_time = recorded_at or now_local()
    submission = {
        "id": str(uuid4()),
        "date": submission_time.date().isoformat(),
        "shift": shift_name.strip(),
        "report_code": config["code"],
        "report_name": config["label"],
        "department": config["department"],
        "interval": config["frequency_label"],
        "slot_key": slot_key,
        "submitted_at": ts,
        "submitted_by": actor.strip(),
        "summary": summary.strip(),
        "action_text": action_text.strip(),
    }
    board["reports"][report_id]["submissions"].append(submission)
    set_report_status_updated(board, report_id, ts)
    return submission


def record_qc_check(
    board: dict[str, Any],
    report_id: str,
    submission_id: str,
    actor: str,
    recorded_at: datetime | None = None,
) -> dict[str, str]:
    ts = dt_to_storage(recorded_at or now_local())
    check = {
        "id": str(uuid4()),
        "submission_id": submission_id,
        "checked_at": ts,
        "checked_by": actor.strip(),
    }
    board["reports"][report_id]["qc_checks"].append(check)
    set_report_status_updated(board, report_id, ts)
    return check


def add_issue_log(
    board: dict[str, Any],
    related_id: str,
    related_label: str,
    problem: str,
    action: str,
    actor: str,
    recorded_at: datetime | None = None,
) -> dict[str, str]:
    ts = dt_to_storage(recorded_at or now_local())
    issue = {
        "id": str(uuid4()),
        "logged_at": ts,
        "related_id": related_id.strip(),
        "related_label": related_label.strip(),
        "problem": problem.strip(),
        "action": action.strip(),
        "entered_by": actor.strip(),
    }
    board["issue_logs"].append(issue)
    if related_id in board["reports"]:
        set_report_status_updated(board, related_id, ts)
    return issue


def add_exception_instruction(
    board: dict[str, Any],
    instruction_text: str,
    related_department_or_report: str,
    actor: str,
    recorded_at: datetime | None = None,
    *,
    checked_by_team: str = "",
    worker_name: str = "",
    instructed_by: str = "",
    approved_by: str = "",
    estimated_end_at: str = "",
) -> dict[str, Any]:
    ts = dt_to_storage(recorded_at or now_local())
    instruction = {
        "id": str(uuid4()),
        "instruction_text": instruction_text.strip(),
        "related_department_or_report": related_department_or_report.strip(),
        "checked_by_team": checked_by_team.strip(),
        "worker_name": worker_name.strip(),
        "instructed_by": instructed_by.strip(),
        "approved_by": approved_by.strip(),
        "started_at": ts,
        "estimated_end_at": estimated_end_at.strip(),
        "started_by": actor.strip(),
        "handover_to": "",
        "handover_note": "",
        "handover_at": "",
        "handover_by": "",
        "informed_next_team": False,
        "is_active": True,
        "ended_at": "",
        "ended_by": "",
    }
    board["exception_instructions"].append(instruction)
    return instruction


def finish_exception_instruction(
    board: dict[str, Any],
    instruction_id: str,
    actor: str,
    recorded_at: datetime | None = None,
    *,
    handover_to: str = "",
    handover_note: str = "",
    informed_next_team: bool = False,
) -> bool:
    ts = dt_to_storage(recorded_at or now_local())
    for instruction in board["exception_instructions"]:
        if instruction["id"] != instruction_id:
            continue
        instruction["is_active"] = False
        instruction["ended_at"] = ts
        instruction["ended_by"] = actor.strip()
        instruction["handover_to"] = handover_to.strip()
        instruction["handover_note"] = handover_note.strip()
        instruction["handover_at"] = ts if handover_to.strip() or handover_note.strip() else instruction.get("handover_at", "")
        instruction["handover_by"] = actor.strip() if handover_to.strip() or handover_note.strip() else instruction.get("handover_by", "")
        instruction["informed_next_team"] = bool(informed_next_team)
        return True
    return False


def handover_exception_instruction(
    board: dict[str, Any],
    instruction_id: str,
    actor: str,
    *,
    handover_to: str,
    handover_note: str = "",
    informed_next_team: bool = False,
    recorded_at: datetime | None = None,
) -> bool:
    ts = dt_to_storage(recorded_at or now_local())
    for instruction in board["exception_instructions"]:
        if instruction["id"] != instruction_id:
            continue
        instruction["handover_to"] = handover_to.strip()
        instruction["handover_note"] = handover_note.strip()
        instruction["handover_at"] = ts
        instruction["handover_by"] = actor.strip()
        instruction["informed_next_team"] = bool(informed_next_team)
        return True
    return False


def latest_submission_for_slot(report_state: dict[str, Any], slot_key: str) -> dict[str, str] | None:
    for submission in reversed(report_state["submissions"]):
        if submission["slot_key"] == slot_key:
            return submission
    return None


def latest_qc_for_submission(report_state: dict[str, Any], submission_id: str) -> dict[str, str] | None:
    for check in reversed(report_state["qc_checks"]):
        if check["submission_id"] == submission_id:
            return check
    return None


def issue_log_count(board: dict[str, Any], report_id: str) -> int:
    return sum(1 for item in board["issue_logs"] if item["related_id"] == report_id)


def latest_issue_log_at(board: dict[str, Any], report_id: str) -> str:
    for item in reversed(board["issue_logs"]):
        if item["related_id"] == report_id:
            return item["logged_at"]
    return ""


def derive_status_updated_at(board: dict[str, Any], report_id: str) -> str:
    report_state = board["reports"][report_id]
    timestamps = [report_state.get("status_updated_at", ""), latest_issue_log_at(board, report_id)]
    if report_state["submissions"]:
        timestamps.append(report_state["submissions"][-1]["submitted_at"])
    valid = [item for item in timestamps if item]
    if not valid:
        return ""
    return max(valid)


def evaluate_report(
    board: dict[str, Any],
    report_id: str,
    shift_name: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or now_local()
    day = current_time.date()
    config = REPORTS[report_id]
    report_state = board["reports"][report_id]
    slots = build_slot_schedule(report_id, day, shift_name)
    effective_slots = slots
    due_slots = [slot for slot in effective_slots if slot["due_at"] <= current_time]
    latest_due_slot = due_slots[-1] if due_slots else None
    latest_submission = report_state["submissions"][-1] if report_state["submissions"] else None
    latest_due_submission = latest_submission_for_slot(report_state, latest_due_slot["slot_key"]) if latest_due_slot else None

    all_complete = False
    if effective_slots and current_time >= effective_slots[-1]["due_at"]:
        all_complete = True
        for slot in effective_slots:
            submission = latest_submission_for_slot(report_state, slot["slot_key"])
            if not submission:
                all_complete = False
                break

    if not latest_due_slot and not latest_submission:
        status = ""
        overdue_minutes = 0
    elif latest_due_slot and not latest_due_submission:
        status = "Not Reported"
        overdue_minutes = max(0, int((current_time - latest_due_slot["due_at"]).total_seconds() // 60))
    elif all_complete:
        status = "Complete"
        overdue_minutes = 0
    else:
        status = "In Progress" if (latest_due_slot or latest_submission) else ""
        overdue_minutes = 0

    issue_count = issue_log_count(board, report_id)
    active_ids = set(board["setup"]["active_report_ids"])
    status_updated_at = derive_status_updated_at(board, report_id)

    return {
        "report_id": report_id,
        "code": config["code"],
        "name": config["label"],
        "department": config["department"],
        "description": config["description"],
        "frequency_label": config["frequency_label"],
        "status": status,
        "status_rank": STATUS_ORDER[status],
        "active": report_id in active_ids,
        "submitted_at": latest_due_submission["submitted_at"] if latest_due_submission else (latest_submission["submitted_at"] if latest_submission else ""),
        "submitted_by": latest_due_submission["submitted_by"] if latest_due_submission else (latest_submission["submitted_by"] if latest_submission else ""),
        "submission_summary": latest_due_submission["summary"] if latest_due_submission else (latest_submission["summary"] if latest_submission else ""),
        "submission_action_text": latest_due_submission["action_text"] if latest_due_submission else (latest_submission["action_text"] if latest_submission else ""),
        "issue_log_count": issue_count,
        "has_issue_badge": issue_count > 0,
        "status_updated_at": status_updated_at,
        "last_slot_due_at": dt_to_storage(effective_slots[-1]["due_at"]) if effective_slots else "",
        "latest_due_at": dt_to_storage(latest_due_slot["due_at"]) if latest_due_slot else "",
        "latest_due_label": latest_due_slot["label"] if latest_due_slot else "-",
        "latest_due_slot_key": latest_due_slot["slot_key"] if latest_due_slot else "",
        "latest_submission_id": latest_due_submission["id"] if latest_due_submission else (latest_submission["id"] if latest_submission else ""),
        "latest_submission_slot_label": latest_due_slot["label"] if latest_due_slot else "-",
        "overdue_minutes": overdue_minutes,
        "slot_schedule": effective_slots,
    }


def build_board_view(board: dict[str, Any], shift_name: str, now: datetime | None = None) -> dict[str, Any]:
    normalized = normalize_board_state(board)
    evaluations = [evaluate_report(normalized, report_id, shift_name, now=now) for report_id in REPORT_ORDER]
    active = [item for item in evaluations if item["active"]]
    off_today = [item for item in evaluations if not item["active"]]

    order_index = {report_id: index for index, report_id in enumerate(REPORT_ORDER)}
    active.sort(
        key=lambda item: (
            item["status_rank"],
            -item["overdue_minutes"],
            order_index[item["report_id"]],
        )
    )
    off_today.sort(key=lambda item: order_index[item["report_id"]])

    summary = {
        "Not Reported": sum(1 for item in active if item["status"] == "Not Reported"),
        "In Progress": sum(1 for item in active if item["status"] == "In Progress"),
        "Complete": sum(1 for item in active if item["status"] == "Complete"),
    }

    instructions = sorted(
        normalized["exception_instructions"],
        key=lambda item: (
            0 if item["is_active"] else 1,
            item["started_at"],
        ),
        reverse=False,
    )
    active_instructions = [item for item in instructions if item["is_active"]]
    completed_instructions = [item for item in instructions if not item["is_active"]]

    issue_logs = sorted(normalized["issue_logs"], key=lambda item: item["logged_at"], reverse=True)
    active_reports_by_group = {
        "30 min reports": [item for item in active if REPORTS[item["report_id"]]["frequency_label"] == "30 min"],
        "1 hour reports": [item for item in active if REPORTS[item["report_id"]]["frequency_label"] == "1 hour"],
        "shift reports": [item for item in active if REPORTS[item["report_id"]]["frequency_label"] == "shift"],
    }
    return {
        "setup_completed": normalized["setup"]["setup_completed"],
        "summary": summary,
        "active_reports": active,
        "active_reports_by_group": active_reports_by_group,
        "off_today_reports": off_today,
        "active_instructions": active_instructions,
        "completed_instructions": completed_instructions,
        "recent_issue_logs": issue_logs,
    }


def serialize_report_state(report_state: dict[str, Any]) -> str:
    payload = {
        "version": 3,
        "submissions": report_state["submissions"],
        "qc_checks": report_state["qc_checks"],
        "notes": report_state.get("notes", ""),
        "status_updated_at": report_state.get("status_updated_at", ""),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def serialize_global_state(board: dict[str, Any]) -> str:
    payload = {
        "version": 1,
        "setup": board["setup"],
        "lineup": board["lineup"],
        "issue_logs": board["issue_logs"],
        "exception_instructions": board["exception_instructions"],
        "telegram": board.get("telegram", {}),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
