from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any
from urllib import error as urlerror
from urllib import parse, request

import streamlit as st

from board_logic import build_board_view, display_dt, dt_to_storage, now_local

TELEGRAM_MESSAGE_LIMIT = 3200


def get_config_value(
    key: str,
    default: str = "",
    *,
    aliases: list[str] | None = None,
    nested_paths: list[tuple[str, str]] | None = None,
) -> str:
    aliases = aliases or []
    nested_paths = nested_paths or []
    names = [key] + aliases
    for name in names:
        value = os.environ.get(name)
        if value:
            return str(value)
    for name in names:
        try:
            value = st.secrets.get(name)
            if value:
                return str(value)
        except Exception:
            pass
    for path in nested_paths:
        try:
            current: Any = st.secrets
            for part in path:
                current = current[part]
            if current:
                return str(current)
        except Exception:
            continue
    return default


def telegram_ready() -> bool:
    token = get_config_value(
        "TELEGRAM_BOT_TOKEN",
        aliases=["BOT_TOKEN", "TELEGRAM_TOKEN"],
        nested_paths=[("TELEGRAM", "BOT_TOKEN"), ("telegram", "bot_token"), ("telegram", "token")],
    )
    chat_id = get_config_value(
        "TELEGRAM_CHAT_ID",
        aliases=["CHAT_ID", "TELEGRAM_CHATID"],
        nested_paths=[("TELEGRAM", "CHAT_ID"), ("telegram", "chat_id")],
    )
    return bool(token and chat_id)


def telegram_api(method: str, payload: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    token = get_config_value(
        "TELEGRAM_BOT_TOKEN",
        aliases=["BOT_TOKEN", "TELEGRAM_TOKEN"],
        nested_paths=[("TELEGRAM", "BOT_TOKEN"), ("telegram", "bot_token"), ("telegram", "token")],
    )
    if not token:
        return False, "TELEGRAM_BOT_TOKEN is not configured.", {}
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = parse.urlencode(payload).encode("utf-8")
    req = request.Request(url, data=data, method="POST")
    try:
        with request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            parsed = json.loads(body)
            if parsed.get("ok"):
                return True, "OK", parsed.get("result", {})
            return False, f"Telegram response error: {parsed}", {}
    except urlerror.HTTPError as err:
        try:
            body = err.read().decode("utf-8", errors="ignore")
            parsed = json.loads(body)
            return False, f"Telegram API HTTP {err.code}: {parsed.get('description') or body}", {}
        except Exception:
            return False, f"Telegram API HTTP {err.code}", {}
    except Exception as err:
        return False, f"Telegram API error: {err}", {}


def send_telegram_text(text: str, reply_to_message_id: int | None = None) -> tuple[bool, str, int | None]:
    chat_id = get_config_value(
        "TELEGRAM_CHAT_ID",
        aliases=["CHAT_ID", "TELEGRAM_CHATID"],
        nested_paths=[("TELEGRAM", "CHAT_ID"), ("telegram", "chat_id")],
    )
    if not chat_id:
        return False, "TELEGRAM_CHAT_ID is not configured.", None
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_to_message_id:
        payload["reply_to_message_id"] = int(reply_to_message_id)
    ok, msg, data = telegram_api("sendMessage", payload)
    if not ok:
        return False, msg, None
    return True, "Telegram message sent", int(data.get("message_id", 0) or 0)


def edit_telegram_text(message_id: int, text: str) -> tuple[bool, str]:
    chat_id = get_config_value(
        "TELEGRAM_CHAT_ID",
        aliases=["CHAT_ID", "TELEGRAM_CHATID"],
        nested_paths=[("TELEGRAM", "CHAT_ID"), ("telegram", "chat_id")],
    )
    if not chat_id:
        return False, "TELEGRAM_CHAT_ID is not configured."
    payload: dict[str, Any] = {"chat_id": chat_id, "message_id": int(message_id), "text": text}
    ok, msg, _ = telegram_api("editMessageText", payload)
    if ok:
        return True, "Telegram message edited"
    if "message is not modified" in msg.lower():
        return True, "Telegram message already up to date"
    return False, msg


def ensure_telegram_cycle(board: dict[str, Any], today_key: str) -> dict[str, Any]:
    telegram = board.setdefault("telegram", {})
    if telegram.get("cycle_key") != today_key:
        telegram.clear()
        telegram.update(
            {
                "cycle_key": today_key,
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
                    "edit_message_id": 0,
                    "created_at": "",
                    "remaining_parts": [],
                },
            }
        )
    telegram.setdefault("root_message_id", 0)
    telegram.setdefault("cycle_started_at", "")
    telegram.setdefault("last_submission_id", "")
    telegram.setdefault("last_sent_at", "")
    telegram.setdefault("last_error", "")
    telegram.setdefault("pending_notice", {})
    pending_notice = telegram["pending_notice"] if isinstance(telegram.get("pending_notice"), dict) else {}
    pending_notice.setdefault("kind", "")
    pending_notice.setdefault("event_id", "")
    pending_notice.setdefault("text", "")
    pending_notice.setdefault("reply_to_message_id", 0)
    pending_notice.setdefault("edit_message_id", 0)
    pending_notice.setdefault("created_at", "")
    pending_notice.setdefault("remaining_parts", [])
    telegram["pending_notice"] = pending_notice
    return telegram


def start_new_telegram_cycle(board: dict[str, Any], today_key: str, started_at: datetime | None = None) -> None:
    ts = dt_to_storage(started_at or now_local())
    board["telegram"] = {
        "cycle_key": today_key,
        "root_message_id": 0,
        "cycle_started_at": ts,
        "last_submission_id": "",
        "last_sent_at": "",
        "last_error": "",
        "pending_notice": {
            "kind": "",
            "event_id": "",
            "text": "",
            "reply_to_message_id": 0,
            "edit_message_id": 0,
            "created_at": "",
            "remaining_parts": [],
        },
    }


def build_supervisory_root_message(today_key: str, shift_name: str, board_view: dict[str, Any]) -> str:
    latest_reports = sorted(
        [item for item in board_view["active_reports"] if item["status_updated_at"]],
        key=lambda item: item["status_updated_at"],
        reverse=True,
    )[:3]
    lines = [
        "QC Supervisory Board",
        f"Date: {today_key.split(' (', 1)[0]}",
        f"Shift: {shift_name}",
        f"Active reports: {len(board_view['active_reports'])}",
        f"Not Reported: {board_view['summary']['Not Reported']}",
        f"In Progress: {board_view['summary']['In Progress']}",
        f"Complete: {board_view['summary']['Complete']}",
        f"Active exception: {len(board_view['active_instructions'])}",
    ]
    if latest_reports:
        lines.append("Latest updated reports:")
        for item in latest_reports:
            lines.append(
                f"- {item['code']} {item['name']} | {display_dt(item['status_updated_at'])} | {item['status'] or 'No due slot yet'}"
            )
    else:
        lines.append("Latest updated reports: belum ada update")
    return "\n".join(lines)


def shorten_text(value: str, limit: int = 80) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def build_update_notice(event: dict[str, Any]) -> str:
    kind = event.get("kind", "update")
    lines = ["laporan sudah diupdate"]
    if kind == "submission":
        lines.append(f"report: {event.get('report_label', '-')}")
        if event.get("submitted_at"):
            lines.append(f"submitted at: {event['submitted_at']}")
        if event.get("summary"):
            lines.append(f"summary: {shorten_text(event['summary'])}")
    elif kind == "issue":
        lines.append(f"report: {event.get('report_label', '-')}")
        if event.get("problem"):
            lines.append(f"issue: {shorten_text(event['problem'])}")
        if event.get("action"):
            lines.append(f"action: {shorten_text(event['action'])}")
    elif kind == "exception":
        lines.append(f"report: {event.get('report_label', '-')}")
        if event.get("instruction_text"):
            lines.append(f"exception: {shorten_text(event['instruction_text'])}")
    else:
        lines.append(shorten_text(event.get("notice", "board updated")))
    return "\n".join(lines[:4])


def latest_report_line(report_eval: dict[str, Any]) -> str:
    summary = shorten_text(report_eval.get("submission_summary", ""), limit=120)
    if summary:
        return summary
    if report_eval.get("submitted_at"):
        return "Sudah ada update, ringkasan belum diisi"
    return "Belum ada update"


def build_current_summary_parts(
    board: dict[str, Any],
    today_key: str,
    shift_name: str,
    actor: str,
    *,
    max_chars: int = TELEGRAM_MESSAGE_LIMIT,
) -> list[str]:
    board_view = build_board_view(board, shift_name, now=now_local())
    date_label = today_key.split(" (", 1)[0]
    active_reports = board_view["active_reports"]
    report_blocks: list[str] = []
    for item in active_reports:
        report_blocks.append(
            "\n".join(
                [
                    f"• {item['code']}. {item['name']}",
                    f"- Status: {item['status'] or 'Belum mulai'}",
                    f"- Latest: {latest_report_line(item)}",
                    f"- Updated: {display_dt(item['status_updated_at']) if item['status_updated_at'] else '-'} by {item['submitted_by'] or '-'}",
                ]
            )
        )

    if not report_blocks:
        report_blocks.append("• Belum ada active report yang dipilih hari ini")

    sections: list[str] = []
    intro_lines = [
        "🚀 Laporan QC Lapangan",
        f"📅 {date_label} | {shift_name}",
        f"👤 QC: {actor or '-'}",
        "",
        "--------------------",
        "",
        "📌 Active Reports",
    ]
    sections.append("\n".join(intro_lines))
    sections.extend(report_blocks)

    if board_view["active_instructions"]:
        exception_lines = ["--------------------", "⚠️ Active Exception"]
        for instruction in board_view["active_instructions"]:
            exception_lines.append(
                f"• {shorten_text(instruction.get('related_department_or_report') or 'General', 40)}: "
                f"{shorten_text(instruction.get('instruction_text', ''), 100)}"
            )
        sections.append("\n".join(exception_lines))

    if str(board.get("general_note", "")).strip():
        sections.append(
            "\n".join(
                [
                    "--------------------",
                    "📝 General note",
                    f"- {shorten_text(str(board.get('general_note', '')).strip(), 500)}",
                ]
            )
        )

    parts: list[str] = []
    current_part = ""
    for block in sections:
        candidate = block if not current_part else f"{current_part}\n\n{block}"
        if current_part and len(candidate) > max_chars and len(parts) < 2:
            parts.append(current_part)
            current_part = block
        else:
            current_part = candidate
    if current_part:
        parts.append(current_part)

    if len(parts) > 3:
        merged = parts[:2]
        merged.append("\n\n".join(parts[2:]))
        parts = merged

    if len(parts) > 1:
        total = len(parts)
        parts = [f"({idx}/{total})\n{part}" for idx, part in enumerate(parts, start=1)]
    return parts


def _clear_pending_notice(telegram: dict[str, Any]) -> None:
    telegram["pending_notice"] = {
        "kind": "",
        "event_id": "",
        "text": "",
        "reply_to_message_id": 0,
        "edit_message_id": 0,
        "created_at": "",
        "remaining_parts": [],
    }


def _store_pending_notice(
    telegram: dict[str, Any],
    *,
    kind: str,
    event_id: str,
    text: str,
    reply_to_message_id: int,
    edit_message_id: int = 0,
    remaining_parts: list[str] | None = None,
) -> None:
    telegram["pending_notice"] = {
        "kind": kind,
        "event_id": event_id,
        "text": text,
        "reply_to_message_id": int(reply_to_message_id or 0),
        "edit_message_id": int(edit_message_id or 0),
        "created_at": dt_to_storage(now_local()),
        "remaining_parts": list(remaining_parts or []),
    }


def _send_parts_sequence(
    telegram: dict[str, Any],
    parts: list[str],
    *,
    event_id: str,
    root_id: int = 0,
) -> tuple[bool, str]:
    active_root_id = int(root_id or telegram.get("root_message_id", 0) or 0)
    for idx, text in enumerate(parts):
        reply_to = active_root_id or None
        ok, msg, message_id = send_telegram_text(text, reply_to_message_id=reply_to)
        if not ok:
            _store_pending_notice(
                telegram,
                kind="summary_root" if idx == 0 and not active_root_id else "summary_reply",
                event_id=event_id,
                text=text,
                reply_to_message_id=active_root_id,
                remaining_parts=parts[idx + 1 :],
            )
            telegram["last_error"] = msg
            return False, msg
        if idx == 0 and not active_root_id and message_id:
            active_root_id = int(message_id)
            telegram["root_message_id"] = active_root_id
    telegram["last_submission_id"] = event_id
    _clear_pending_notice(telegram)
    telegram["last_error"] = ""
    telegram["last_sent_at"] = dt_to_storage(now_local())
    return True, f"Telegram summary sent ({len(parts)} part(s))"


def _send_reply_parts(
    telegram: dict[str, Any],
    parts: list[str],
    *,
    event_id: str,
    root_id: int,
) -> tuple[bool, str]:
    for idx, text in enumerate(parts):
        ok, msg, _ = send_telegram_text(text, reply_to_message_id=root_id)
        if not ok:
            _store_pending_notice(
                telegram,
                kind="summary_reply",
                event_id=event_id,
                text=text,
                reply_to_message_id=root_id,
                remaining_parts=parts[idx + 1 :],
            )
            telegram["last_error"] = msg
            return False, msg
    telegram["last_submission_id"] = event_id
    _clear_pending_notice(telegram)
    telegram["last_error"] = ""
    telegram["last_sent_at"] = dt_to_storage(now_local())
    return True, f"Telegram summary updated ({len(parts)} reply part(s))"


def build_summary_update_notice(actor: str) -> str:
    return "\n".join(
        [
            "ringkasan board sudah diperbarui",
            f"updated at: {now_local().strftime('%H:%M')}",
            f"by: {actor or '-'}",
        ]
    )


def send_current_summary_to_telegram(
    board: dict[str, Any],
    today_key: str,
    shift_name: str,
    actor: str,
) -> str:
    telegram = ensure_telegram_cycle(board, today_key)
    if not telegram_ready():
        telegram["last_error"] = "Telegram is not configured."
        return "Telegram skipped: not configured"
    parts = build_current_summary_parts(board, today_key, shift_name, actor)
    event_id = f"manual-summary:{dt_to_storage(now_local())}"
    root_id = int(telegram.get("root_message_id", 0) or 0)
    if not root_id:
        ok, message = _send_parts_sequence(
            telegram,
            parts,
            event_id=event_id,
            root_id=0,
        )
        if ok:
            return message
        return f"Telegram summary failed: {message}"

    ok, msg = edit_telegram_text(root_id, parts[0])
    if not ok:
        _store_pending_notice(
            telegram,
            kind="summary_edit",
            event_id=event_id,
            text=parts[0],
            reply_to_message_id=root_id,
            edit_message_id=root_id,
            remaining_parts=parts[1:] + [build_summary_update_notice(actor)],
        )
        telegram["last_error"] = msg
        return f"Telegram summary failed: {msg}"

    reply_parts = parts[1:] + [build_summary_update_notice(actor)]
    if reply_parts:
        ok, message = _send_reply_parts(
            telegram,
            reply_parts,
            event_id=event_id,
            root_id=root_id,
        )
        if ok:
            return message
        return f"Telegram summary failed: {message}"

    telegram["last_submission_id"] = event_id
    _clear_pending_notice(telegram)
    telegram["last_error"] = ""
    telegram["last_sent_at"] = dt_to_storage(now_local())
    return "Telegram summary updated"


def sync_telegram_update(
    board: dict[str, Any],
    today_key: str,
    shift_name: str,
    *,
    event: dict[str, Any] | None = None,
    retry_pending: bool = False,
) -> str:
    telegram = ensure_telegram_cycle(board, today_key)
    if not telegram_ready():
        telegram["last_error"] = "Telegram is not configured."
        return "Telegram skipped: not configured"

    board_view = build_board_view(board, shift_name, now=now_local())
    pending = telegram.get("pending_notice") or {}
    if retry_pending and pending.get("text"):
        if pending.get("kind") == "summary_edit":
            ok, msg = edit_telegram_text(
                int(pending.get("edit_message_id", 0) or 0),
                str(pending.get("text", "")),
            )
            if not ok:
                telegram["last_error"] = msg
                return f"Telegram pending retry failed: {msg}"
            remaining_parts = [
                str(item) for item in pending.get("remaining_parts", []) if str(item).strip()
            ]
            if remaining_parts:
                ok, message = _send_reply_parts(
                    telegram,
                    remaining_parts,
                    event_id=str(pending.get("event_id", "")),
                    root_id=int(pending.get("reply_to_message_id", 0) or 0),
                )
                if ok:
                    return "Telegram pending update sent"
                return f"Telegram pending retry failed: {message}"
            telegram["last_submission_id"] = str(pending.get("event_id", ""))
            _clear_pending_notice(telegram)
            telegram["last_error"] = ""
            telegram["last_sent_at"] = dt_to_storage(now_local())
            return "Telegram pending update sent"
        pending_parts = [str(pending.get("text", ""))] + [
            str(item) for item in pending.get("remaining_parts", []) if str(item).strip()
        ]
        ok, message = _send_parts_sequence(
            telegram,
            pending_parts,
            event_id=str(pending.get("event_id", "")),
            root_id=int(pending.get("reply_to_message_id", 0) or 0),
        )
        if ok:
            return "Telegram pending update sent"
        return f"Telegram pending retry failed: {message}"

    event_id = str(event.get("event_id", "")) if event else ""
    if event_id and telegram.get("last_submission_id") == event_id:
        return "Telegram skipped: duplicate event"

    root_id = int(telegram.get("root_message_id", 0) or 0)
    if not root_id:
        root_text = build_supervisory_root_message(today_key, shift_name, board_view)
        ok, msg, message_id = send_telegram_text(root_text)
        if not ok:
            _store_pending_notice(
                telegram,
                kind="root",
                event_id=event_id,
                text=root_text,
                reply_to_message_id=0,
            )
            telegram["last_error"] = msg
            return f"Telegram root failed: {msg}"
        telegram["root_message_id"] = int(message_id or 0)
        telegram["last_submission_id"] = event_id
        _clear_pending_notice(telegram)
        telegram["last_error"] = ""
        telegram["last_sent_at"] = dt_to_storage(now_local())
        return f"Telegram root sent (message_id={message_id})"

    if not event:
        return "Telegram root already exists"

    notice = build_update_notice(event)
    ok, msg, _ = send_telegram_text(notice, reply_to_message_id=root_id)
    if not ok:
        _store_pending_notice(
            telegram,
            kind="reply",
            event_id=event_id,
            text=notice,
            reply_to_message_id=root_id,
        )
        telegram["last_error"] = msg
        return f"Telegram update failed: {msg}"
    telegram["last_submission_id"] = event_id
    _clear_pending_notice(telegram)
    telegram["last_error"] = ""
    telegram["last_sent_at"] = dt_to_storage(now_local())
    return "Telegram update reply sent"
