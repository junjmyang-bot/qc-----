import json
import unittest
from datetime import datetime
from unittest.mock import patch

import app
import board_store
import telegram_flow
from board_logic import (
    add_exception_instruction,
    build_board_view,
    build_slot_schedule,
    empty_board_state,
    evaluate_report,
    finish_exception_instruction,
    record_qc_check,
    record_submission,
    reset_operational_state,
    serialize_global_state,
    update_active_reports,
    update_lineup,
)


SHIFT_NAME = "Shift 1 (Pagi)"
BASE_DAY = datetime(2026, 3, 29)


class FakeWorksheet:
    def __init__(self, values):
        self._values = values

    def get_all_values(self):
        return self._values


class SupervisoryBoardLogicTests(unittest.TestCase):
    def test_setup_starts_incomplete_and_has_no_active_reports(self):
        board = empty_board_state()

        self.assertFalse(board["setup"]["setup_completed"])
        self.assertEqual(board["setup"]["active_report_ids"], [])

    def test_not_reported_when_latest_due_slot_missing(self):
        board = empty_board_state()
        now = datetime(2026, 3, 29, 8, 10)

        result = evaluate_report(board, "a4", SHIFT_NAME, now=now)

        self.assertEqual(result["status"], "Not Reported")
        self.assertEqual(result["latest_due_slot_key"], "3")

    def test_in_progress_when_latest_due_slot_has_submission(self):
        board = empty_board_state()
        now = datetime(2026, 3, 29, 8, 10)

        record_submission(board, "a4", "3", "Operator A", recorded_at=now)
        result = evaluate_report(board, "a4", SHIFT_NAME, now=now)

        self.assertEqual(result["status"], "In Progress")
        self.assertEqual(result["submitted_by"], "Operator A")

    def test_existing_qc_data_does_not_change_submission_based_status(self):
        board = empty_board_state()
        now = datetime(2026, 3, 29, 8, 10)

        submission = record_submission(board, "a4", "3", "Operator A", recorded_at=now)
        record_qc_check(board, "a4", submission["id"], "QC A", recorded_at=now)
        result = evaluate_report(board, "a4", SHIFT_NAME, now=now)

        self.assertEqual(result["status"], "In Progress")
        self.assertEqual(result["submitted_by"], "Operator A")

    def test_complete_only_after_last_required_slot(self):
        board = empty_board_state()
        slots = build_slot_schedule("a4", BASE_DAY.date(), SHIFT_NAME)
        after_last_slot = datetime(2026, 3, 29, 15, 0)

        for slot in slots:
            record_submission(board, "a4", slot["slot_key"], "Operator A", recorded_at=slot["due_at"])

        before_last_slot = datetime(2026, 3, 29, 14, 0)
        before_result = evaluate_report(board, "a4", SHIFT_NAME, now=before_last_slot)
        after_result = evaluate_report(board, "a4", SHIFT_NAME, now=after_last_slot)

        self.assertEqual(before_result["status"], "In Progress")
        self.assertEqual(after_result["status"], "Complete")

    def test_latest_submission_updates_visible_latest_report(self):
        board = empty_board_state()
        first_time = datetime(2026, 3, 29, 8, 10)
        second_time = datetime(2026, 3, 29, 8, 20)

        first_submission = record_submission(board, "a4", "3", "Operator A", recorded_at=first_time)
        record_qc_check(board, "a4", first_submission["id"], "QC A", recorded_at=first_time)
        record_submission(board, "a4", "3", "Operator B", recorded_at=second_time)

        result = evaluate_report(board, "a4", SHIFT_NAME, now=second_time)

        self.assertEqual(result["status"], "In Progress")
        self.assertEqual(result["submitted_by"], "Operator B")

    def test_submission_summary_is_retained_on_board_view(self):
        board = empty_board_state()
        now = datetime(2026, 3, 29, 8, 10)

        update_active_reports(board, ["a4"], "Supervisor", recorded_at=now)
        record_submission(
            board,
            "a4",
            "3",
            "TL Kupas",
            summary="Kupas line stable, no major issue",
            action_text="Asked packing to monitor incoming flow",
            recorded_at=now,
            shift_name=SHIFT_NAME,
        )

        result = evaluate_report(board, "a4", SHIFT_NAME, now=now)

        self.assertEqual(result["submitted_by"], "TL Kupas")
        self.assertEqual(result["submission_summary"], "Kupas line stable, no major issue")
        self.assertEqual(result["submission_action_text"], "Asked packing to monitor incoming flow")
        stored = board["reports"]["a4"]["submissions"][0]
        self.assertEqual(stored["date"], "2026-03-29")
        self.assertEqual(stored["shift"], SHIFT_NAME)
        self.assertEqual(stored["report_code"], "A-4")
        self.assertEqual(stored["report_name"], "Laporan QC di Tablet")
        self.assertEqual(stored["department"], "QC")
        self.assertEqual(stored["interval"], "30 min")

    def test_submission_history_appends_and_latest_snapshot_uses_last_entry(self):
        board = empty_board_state()
        first_time = datetime(2026, 3, 29, 8, 10)
        second_time = datetime(2026, 3, 29, 8, 35)

        update_active_reports(board, ["a4"], "Supervisor", recorded_at=first_time)
        record_submission(
            board,
            "a4",
            "3",
            "TL Kupas",
            summary="First update",
            action_text="Initial action",
            recorded_at=first_time,
            shift_name=SHIFT_NAME,
        )
        record_submission(
            board,
            "a4",
            "4",
            "TL Kupas",
            summary="Second update",
            action_text="Second action",
            recorded_at=second_time,
            shift_name=SHIFT_NAME,
        )

        result = evaluate_report(board, "a4", SHIFT_NAME, now=second_time)

        self.assertEqual(len(board["reports"]["a4"]["submissions"]), 2)
        self.assertEqual(result["submitted_at"], second_time.isoformat(timespec="seconds"))
        self.assertEqual(result["submission_summary"], "Second update")
        self.assertEqual(result["submission_action_text"], "Second action")

    def test_lineup_and_exception_logs_are_supported_together(self):
        board = empty_board_state()
        now = datetime(2026, 3, 29, 9, 0)

        update_active_reports(board, ["a4"], "Supervisor", recorded_at=now)
        update_lineup(board, True, "Supervisor", recorded_at=now)
        add_exception_instruction(
            board,
            "Use temporary steam threshold",
            "Steam",
            "Manager A",
            recorded_at=now,
            checked_by_team="QC Uyun",
            worker_name="Operator Steam A",
            instructed_by="Manager A",
            approved_by="Senior QC",
            estimated_end_at=datetime(2026, 3, 29, 11, 0).isoformat(timespec="seconds"),
        )

        view = build_board_view(board, SHIFT_NAME, now=now)

        self.assertTrue(board["lineup"]["lineup_exists"])
        self.assertEqual(len(view["active_instructions"]), 1)
        self.assertEqual(view["active_instructions"][0]["instruction_text"], "Use temporary steam threshold")
        self.assertEqual(view["active_instructions"][0]["checked_by_team"], "QC Uyun")
        self.assertEqual(view["active_instructions"][0]["worker_name"], "Operator Steam A")

    def test_off_today_reports_are_split_out(self):
        board = empty_board_state()
        update_active_reports(board, ["a4", "b3"], "Supervisor", recorded_at=datetime(2026, 3, 29, 6, 50))

        view = build_board_view(board, SHIFT_NAME, now=datetime(2026, 3, 29, 8, 10))

        active_ids = {item["report_id"] for item in view["active_reports"]}
        off_today_ids = {item["report_id"] for item in view["off_today_reports"]}
        self.assertEqual(active_ids, {"a4", "b3"})
        self.assertIn("a5", off_today_ids)

    def test_setup_marks_only_selected_reports_active_and_groups_them(self):
        board = empty_board_state()
        update_active_reports(board, ["a4", "b2", "a1"], "Supervisor", recorded_at=datetime(2026, 3, 29, 6, 50))

        view = build_board_view(board, SHIFT_NAME, now=datetime(2026, 3, 29, 6, 55))

        active_ids = {item["report_id"] for item in view["active_reports"]}
        self.assertTrue(view["setup_completed"])
        self.assertEqual(active_ids, {"a4", "b2", "a1"})
        self.assertEqual(view["summary"]["In Progress"], 0)
        self.assertEqual(len(view["active_reports_by_group"]["30 min reports"]), 1)
        self.assertEqual(len(view["active_reports_by_group"]["1 hour reports"]), 1)
        self.assertEqual(len(view["active_reports_by_group"]["shift reports"]), 1)

    def test_no_submissions_start_at_zero_before_any_due_slot(self):
        board = empty_board_state()
        update_active_reports(board, ["a4", "b2", "a1"], "Supervisor", recorded_at=datetime(2026, 3, 29, 6, 50))

        view = build_board_view(board, SHIFT_NAME, now=datetime(2026, 3, 29, 6, 55))

        self.assertEqual(view["summary"]["Not Reported"], 0)
        self.assertEqual(view["summary"]["In Progress"], 0)
        self.assertEqual(view["summary"]["Complete"], 0)
        self.assertTrue(all(not item["status"] for item in view["active_reports"]))

    def test_first_setup_can_reset_existing_operational_state(self):
        board = empty_board_state()
        now = datetime(2026, 3, 29, 9, 0)

        update_active_reports(board, ["a4"], "Supervisor", recorded_at=now)
        update_lineup(board, True, "Supervisor", recorded_at=now)
        submission = record_submission(board, "a4", "3", "Operator A", recorded_at=now)
        record_qc_check(board, "a4", submission["id"], "QC A", recorded_at=now)
        add_exception_instruction(board, "Use temporary steam threshold", "Steam", "Manager A", recorded_at=now)

        reset_operational_state(board)

        self.assertFalse(board["lineup"]["lineup_exists"])
        self.assertEqual(board["reports"]["a4"]["submissions"], [])
        self.assertEqual(board["reports"]["a4"]["qc_checks"], [])
        self.assertEqual(board["exception_instructions"], [])

    def test_submission_time_parser_accepts_hhmm(self):
        schedule = build_slot_schedule("a4", BASE_DAY.date(), SHIFT_NAME)
        parsed = app.parse_submitted_at(schedule, "0805")

        self.assertEqual(parsed, datetime(2026, 3, 29, 8, 5))


class SupervisoryBoardTelegramTests(unittest.TestCase):
    def test_start_new_telegram_cycle_preserves_board_data_and_only_resets_telegram_thread(self):
        board = empty_board_state()
        now = datetime(2026, 3, 30, 8, 5)
        update_active_reports(board, ["a4", "b2"], "Supervisor", recorded_at=now)
        record_submission(board, "a4", "3", "TL Kupas", summary="stok aman", recorded_at=now, shift_name=SHIFT_NAME)
        add_exception_instruction(board, "Temporary instruction", "Steam", "Manager A", recorded_at=now)

        telegram_flow.start_new_telegram_cycle(board, "2026-03-30 (Shift 1 (Pagi))", started_at=now)
        view = build_board_view(board, SHIFT_NAME, now=now)

        self.assertEqual(view["summary"]["Not Reported"], 1)
        self.assertEqual(view["summary"]["In Progress"], 1)
        self.assertEqual(view["summary"]["Complete"], 0)
        self.assertEqual(board["setup"]["active_report_ids"], ["a4", "b2"])
        self.assertEqual(board["telegram"]["root_message_id"], 0)
        self.assertEqual(len(view["active_instructions"]), 1)
        self.assertEqual(len(board["reports"]["a4"]["submissions"]), 1)

    def test_build_active_report_rows_returns_full_names(self):
        rows = app.build_active_report_rows(["a4", "b2"])

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["code"], "A-4")
        self.assertEqual(rows[0]["full report name"], "Laporan QC di Tablet")
        self.assertEqual(rows[1]["code"], "B-2")
        self.assertEqual(rows[1]["full report name"], "Laporan Status Steam")

    def test_build_current_summary_parts_uses_active_reports_only_and_includes_general_note(self):
        board = empty_board_state()
        now = datetime(2026, 3, 30, 8, 5)
        update_active_reports(board, ["a4"], "Supervisor", recorded_at=now)
        board["general_note"] = "Perhatikan line steam setelah jam 10"
        record_submission(
            board,
            "a4",
            "3",
            "TL Kupas",
            summary="stok aman",
            recorded_at=now,
            shift_name=SHIFT_NAME,
        )

        parts = telegram_flow.build_current_summary_parts(
            board,
            "2026-03-30 (Shift 1 (Pagi))",
            SHIFT_NAME,
            "QC Uyun",
        )

        self.assertEqual(len(parts), 1)
        self.assertIn("🚀 Laporan QC Lapangan", parts[0])
        self.assertIn("👤 QC: QC Uyun", parts[0])
        self.assertIn("• A-4. Laporan QC di Tablet", parts[0])
        self.assertNotIn("B-2", parts[0])
        self.assertIn("📝 General note", parts[0])

    def test_build_current_summary_parts_splits_without_breaking_report_format(self):
        board = empty_board_state()
        now = datetime(2026, 3, 30, 8, 5)
        update_active_reports(board, ["a4", "a5", "b3"], "Supervisor", recorded_at=now)
        for report_id in ["a4", "a5", "b3"]:
            record_submission(
                board,
                report_id,
                "3",
                "TL Test",
                summary="ringkasan sangat panjang " * 10,
                recorded_at=now,
                shift_name=SHIFT_NAME,
            )

        parts = telegram_flow.build_current_summary_parts(
            board,
            "2026-03-30 (Shift 1 (Pagi))",
            SHIFT_NAME,
            "QC Uyun",
            max_chars=350,
        )

        self.assertGreater(len(parts), 1)
        self.assertLessEqual(len(parts), 3)
        self.assertTrue(parts[0].startswith("(1/"))

    def test_first_telegram_send_creates_root_message(self):
        board = empty_board_state()
        now = datetime(2026, 3, 30, 8, 5)
        update_active_reports(board, ["a4"], "Supervisor", recorded_at=now)
        record_submission(board, "a4", "3", "TL Kupas", summary="stok aman", recorded_at=now, shift_name=SHIFT_NAME)

        with patch.object(telegram_flow, "telegram_ready", return_value=True), patch.object(
            telegram_flow,
            "send_telegram_text",
            return_value=(True, "ok", 777),
        ) as mocked_send:
            result = telegram_flow.sync_telegram_update(board, "2026-03-30 (Shift 1 (Pagi))", SHIFT_NAME, event={"event_id": "sub-1", "kind": "submission", "report_label": "A-4 Laporan QC di Tablet", "submitted_at": "08:05", "summary": "stok aman"})

        self.assertIn("root sent", result)
        self.assertEqual(board["telegram"]["root_message_id"], 777)
        self.assertEqual(mocked_send.call_count, 1)
        self.assertEqual(mocked_send.call_args.kwargs.get("reply_to_message_id"), None)

    def test_second_send_replies_to_existing_root(self):
        board = empty_board_state()
        now = datetime(2026, 3, 30, 8, 5)
        update_active_reports(board, ["a4"], "Supervisor", recorded_at=now)
        board["telegram"] = {
            "cycle_key": "2026-03-30 (Shift 1 (Pagi))",
            "root_message_id": 777,
            "last_submission_id": "",
            "last_sent_at": "",
            "last_error": "",
            "pending_notice": {},
        }

        with patch.object(telegram_flow, "telegram_ready", return_value=True), patch.object(
            telegram_flow,
            "send_telegram_text",
            return_value=(True, "ok", 778),
        ) as mocked_send:
            result = telegram_flow.sync_telegram_update(board, "2026-03-30 (Shift 1 (Pagi))", SHIFT_NAME, event={"event_id": "sub-2", "kind": "submission", "report_label": "A-4 Laporan QC di Tablet", "submitted_at": "08:35", "summary": "update kedua"})

        self.assertIn("reply sent", result)
        self.assertEqual(mocked_send.call_count, 1)
        self.assertEqual(mocked_send.call_args.kwargs.get("reply_to_message_id"), 777)

    def test_new_date_starts_new_root_cycle(self):
        board = empty_board_state()
        board["telegram"] = {
            "cycle_key": "2026-03-30 (Shift 1 (Pagi))",
            "root_message_id": 777,
            "last_submission_id": "old",
            "last_sent_at": "",
            "last_error": "",
            "pending_notice": {},
        }

        with patch.object(telegram_flow, "telegram_ready", return_value=True), patch.object(
            telegram_flow,
            "send_telegram_text",
            return_value=(True, "ok", 888),
        ):
            result = telegram_flow.sync_telegram_update(board, "2026-03-31 (Shift 1 (Pagi))", SHIFT_NAME, event={"event_id": "sub-new-date", "kind": "submission", "report_label": "A-4 Laporan QC di Tablet"})

        self.assertIn("root sent", result)
        self.assertEqual(board["telegram"]["cycle_key"], "2026-03-31 (Shift 1 (Pagi))")
        self.assertEqual(board["telegram"]["root_message_id"], 888)

    def test_new_shift_starts_new_root_cycle(self):
        board = empty_board_state()
        board["telegram"] = {
            "cycle_key": "2026-03-30 (Shift 1 (Pagi))",
            "root_message_id": 777,
            "last_submission_id": "old",
            "last_sent_at": "",
            "last_error": "",
            "pending_notice": {},
        }

        with patch.object(telegram_flow, "telegram_ready", return_value=True), patch.object(
            telegram_flow,
            "send_telegram_text",
            return_value=(True, "ok", 889),
        ):
            result = telegram_flow.sync_telegram_update(board, "2026-03-30 (Shift 2 (Sore))", "Shift 2 (Sore)", event={"event_id": "sub-new-shift", "kind": "submission", "report_label": "A-4 Laporan QC di Tablet"})

        self.assertIn("root sent", result)
        self.assertEqual(board["telegram"]["cycle_key"], "2026-03-30 (Shift 2 (Sore))")
        self.assertEqual(board["telegram"]["root_message_id"], 889)

    def test_update_notice_is_short(self):
        text = telegram_flow.build_update_notice(
            {
                "kind": "submission",
                "report_label": "A-2 Cek Stok BS",
                "submitted_at": "10:30",
                "summary": "stok aman dan line berjalan stabil tanpa kendala besar sama sekali sampai saat ini",
            }
        )

        self.assertIn("laporan sudah diupdate", text)
        self.assertIn("report: A-2 Cek Stok BS", text)
        self.assertLessEqual(len(text.splitlines()), 4)

    def test_telegram_failure_sets_pending_without_crashing(self):
        board = empty_board_state()
        update_active_reports(board, ["a4"], "Supervisor", recorded_at=datetime(2026, 3, 30, 8, 5))

        with patch.object(telegram_flow, "telegram_ready", return_value=True), patch.object(
            telegram_flow,
            "send_telegram_text",
            return_value=(False, "network down", None),
        ):
            result = telegram_flow.sync_telegram_update(board, "2026-03-30 (Shift 1 (Pagi))", SHIFT_NAME, event={"event_id": "sub-fail", "kind": "submission", "report_label": "A-4 Laporan QC di Tablet"})

        self.assertIn("failed", result)
        self.assertTrue(board["telegram"]["pending_notice"]["text"])
        self.assertEqual(board["telegram"]["last_error"], "network down")

    def test_retry_pending_marks_last_submission_id_to_prevent_duplicate_reply(self):
        board = empty_board_state()
        board["telegram"] = {
            "cycle_key": "2026-03-30 (Shift 1 (Pagi))",
            "root_message_id": 777,
            "cycle_started_at": "",
            "last_submission_id": "",
            "last_sent_at": "",
            "last_error": "network down",
            "pending_notice": {
                "kind": "reply",
                "event_id": "sub-retry",
                "text": "laporan sudah diupdate",
                "reply_to_message_id": 777,
                "created_at": now.isoformat(timespec="seconds") if (now := datetime(2026, 3, 30, 8, 40)) else "",
            },
        }

        with patch.object(telegram_flow, "telegram_ready", return_value=True), patch.object(
            telegram_flow,
            "send_telegram_text",
            return_value=(True, "ok", 778),
        ):
            result = telegram_flow.sync_telegram_update(board, "2026-03-30 (Shift 1 (Pagi))", SHIFT_NAME, retry_pending=True)

        self.assertIn("pending update sent", result)
        self.assertEqual(board["telegram"]["last_submission_id"], "sub-retry")
        self.assertEqual(board["telegram"]["pending_notice"]["text"], "")

    def test_send_current_summary_to_telegram_uses_root_then_replies_for_extra_parts(self):
        board = empty_board_state()
        update_active_reports(board, ["a4"], "Supervisor", recorded_at=datetime(2026, 3, 30, 8, 5))

        with patch.object(telegram_flow, "telegram_ready", return_value=True), patch.object(
            telegram_flow,
            "build_current_summary_parts",
            return_value=["part 1", "part 2"],
        ), patch.object(
            telegram_flow,
            "send_telegram_text",
            side_effect=[(True, "ok", 900), (True, "ok", 901)],
        ) as mocked_send:
            result = telegram_flow.send_current_summary_to_telegram(
                board,
                "2026-03-30 (Shift 1 (Pagi))",
                SHIFT_NAME,
                "QC Uyun",
            )

        self.assertIn("2 part(s)", result)
        self.assertEqual(board["telegram"]["root_message_id"], 900)
        first_call = mocked_send.call_args_list[0]
        second_call = mocked_send.call_args_list[1]
        self.assertIsNone(first_call.kwargs.get("reply_to_message_id"))
        self.assertEqual(second_call.kwargs.get("reply_to_message_id"), 900)

    def test_send_current_summary_to_telegram_edits_existing_root_and_replies_notice(self):
        board = empty_board_state()
        update_active_reports(board, ["a4"], "Supervisor", recorded_at=datetime(2026, 3, 30, 8, 5))
        board["telegram"] = {
            "cycle_key": "2026-03-30 (Shift 1 (Pagi))",
            "root_message_id": 900,
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

        with patch.object(telegram_flow, "telegram_ready", return_value=True), patch.object(
            telegram_flow,
            "build_current_summary_parts",
            return_value=["updated root text"],
        ), patch.object(
            telegram_flow,
            "edit_telegram_text",
            return_value=(True, "edited"),
        ) as mocked_edit, patch.object(
            telegram_flow,
            "send_telegram_text",
            return_value=(True, "ok", 901),
        ) as mocked_send:
            result = telegram_flow.send_current_summary_to_telegram(
                board,
                "2026-03-30 (Shift 1 (Pagi))",
                SHIFT_NAME,
                "QC Uyun",
            )

        self.assertIn("updated", result)
        mocked_edit.assert_called_once_with(900, "updated root text")
        self.assertEqual(mocked_send.call_count, 1)
        self.assertEqual(mocked_send.call_args.kwargs.get("reply_to_message_id"), 900)
        self.assertIn("ringkasan board sudah diperbarui", mocked_send.call_args.args[0])

    def test_retry_pending_summary_edit_edits_root_then_sends_remaining_replies(self):
        board = empty_board_state()
        board["telegram"] = {
            "cycle_key": "2026-03-30 (Shift 1 (Pagi))",
            "root_message_id": 900,
            "cycle_started_at": "",
            "last_submission_id": "",
            "last_sent_at": "",
            "last_error": "network down",
            "pending_notice": {
                "kind": "summary_edit",
                "event_id": "manual-summary:2026-03-30T10:00:00",
                "text": "updated root text",
                "reply_to_message_id": 900,
                "edit_message_id": 900,
                "created_at": "2026-03-30T10:00:10",
                "remaining_parts": ["ringkasan board sudah diperbarui"],
            },
        }

        with patch.object(telegram_flow, "telegram_ready", return_value=True), patch.object(
            telegram_flow,
            "edit_telegram_text",
            return_value=(True, "edited"),
        ) as mocked_edit, patch.object(
            telegram_flow,
            "send_telegram_text",
            return_value=(True, "ok", 901),
        ) as mocked_send:
            result = telegram_flow.sync_telegram_update(
                board,
                "2026-03-30 (Shift 1 (Pagi))",
                SHIFT_NAME,
                retry_pending=True,
            )

        self.assertIn("pending update sent", result)
        mocked_edit.assert_called_once_with(900, "updated root text")
        self.assertEqual(mocked_send.call_args.kwargs.get("reply_to_message_id"), 900)
        self.assertEqual(board["telegram"]["last_submission_id"], "manual-summary:2026-03-30T10:00:00")
        self.assertEqual(board["telegram"]["pending_notice"]["text"], "")

    def test_load_board_state_from_sheet_restores_telegram_state(self):
        today_key = "2026-03-30 (Shift 1 (Pagi))"
        board = empty_board_state()
        update_active_reports(board, ["a4"], "Supervisor", recorded_at=datetime(2026, 3, 30, 7, 0))
        board["telegram"] = {
            "cycle_key": today_key,
            "root_message_id": 777,
            "cycle_started_at": "2026-03-30T08:00:00",
            "last_submission_id": "sub-1",
            "last_sent_at": "2026-03-30T08:05:00",
            "last_error": "",
            "pending_notice": {
                "kind": "reply",
                "event_id": "sub-2",
                "text": "laporan sudah diupdate",
                "reply_to_message_id": 777,
                "created_at": "2026-03-30T08:06:00",
            },
        }
        values = [["", "", ""] for _ in range(board_store.LAYOUT["total"])]
        values[1][2] = today_key
        values[board_store.LAYOUT["top"] - 1][2] = serialize_global_state(board)
        worksheet = FakeWorksheet(values)

        loaded, found = board_store.load_board_state_from_sheet(worksheet, today_key, BASE_DAY.date(), SHIFT_NAME)

        self.assertTrue(found)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["telegram"]["root_message_id"], 777)
        self.assertEqual(loaded["telegram"]["last_submission_id"], "sub-1")
        self.assertEqual(loaded["telegram"]["pending_notice"]["event_id"], "sub-2")

    def test_normalize_service_account_secret_accepts_json_string(self):
        payload = {"type": "service_account", "project_id": "demo"}

        result = board_store.normalize_service_account_secret(json.dumps(payload))

        self.assertEqual(result, payload)

    def test_normalize_service_account_secret_accepts_mapping(self):
        payload = {"type": "service_account", "project_id": "demo"}

        result = board_store.normalize_service_account_secret(payload)

        self.assertEqual(result, payload)

    def test_get_worksheet_exposes_last_sheet_error_on_secret_failure(self):
        board_store.get_worksheet.clear()
        try:
            with patch.object(board_store, "try_load_service_account", side_effect=ValueError("bad secret")):
                result = board_store.get_worksheet()
            self.assertIsNone(result)
            self.assertIn("ValueError", board_store.get_last_sheet_error())
            self.assertIn("bad secret", board_store.get_last_sheet_error())
        finally:
            board_store.get_worksheet.clear()

    def test_finish_exception_instruction_stores_handover_fields(self):
        board = empty_board_state()
        now = datetime(2026, 3, 30, 13, 30)
        instruction = add_exception_instruction(
            board,
            "stick is buang simparan",
            "jun",
            "jun",
            recorded_at=now,
            checked_by_team="A-4 team",
            worker_name="worker A",
            instructed_by="QC Leader",
            approved_by="Management",
            estimated_end_at=datetime(2026, 3, 30, 15, 0).isoformat(timespec="seconds"),
        )

        ok = finish_exception_instruction(
            board,
            instruction["id"],
            "QC Leader",
            recorded_at=datetime(2026, 3, 30, 16, 0),
            handover_to="TL Shift 2",
            handover_note="Continue on next shift",
            informed_next_team=True,
        )

        self.assertTrue(ok)
        saved = board["exception_instructions"][0]
        self.assertFalse(saved["is_active"])
        self.assertEqual(saved["handover_to"], "TL Shift 2")
        self.assertEqual(saved["handover_note"], "Continue on next shift")
        self.assertTrue(saved["informed_next_team"])


if __name__ == "__main__":
    unittest.main()
