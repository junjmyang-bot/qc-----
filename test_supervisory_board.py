import unittest
from datetime import datetime

from board_logic import (
    add_exception_instruction,
    add_issue_log,
    build_board_view,
    build_slot_schedule,
    empty_board_state,
    evaluate_report,
    record_qc_check,
    record_submission,
    update_active_reports,
    update_lineup,
)


SHIFT_NAME = "Shift 1 (Pagi)"
BASE_DAY = datetime(2026, 3, 29)


class SupervisoryBoardLogicTests(unittest.TestCase):
    def test_not_reported_when_latest_due_slot_missing(self):
        board = empty_board_state()
        now = datetime(2026, 3, 29, 8, 10)

        result = evaluate_report(board, "a4", SHIFT_NAME, now=now)

        self.assertEqual(result["status"], "Not Reported")
        self.assertEqual(result["latest_due_slot_key"], "3")

    def test_submitted_but_needs_qc(self):
        board = empty_board_state()
        now = datetime(2026, 3, 29, 8, 10)

        record_submission(board, "a4", "3", "Operator A", recorded_at=now)
        result = evaluate_report(board, "a4", SHIFT_NAME, now=now)

        self.assertEqual(result["status"], "Sudah disubmit, perlu dicek QC")
        self.assertFalse(result["qc_checked"])

    def test_in_progress_when_latest_due_slot_has_submission_and_qc_but_day_not_finished(self):
        board = empty_board_state()
        now = datetime(2026, 3, 29, 8, 10)

        submission = record_submission(board, "a4", "3", "Operator A", recorded_at=now)
        record_qc_check(board, "a4", submission["id"], "QC A", recorded_at=now)
        result = evaluate_report(board, "a4", SHIFT_NAME, now=now)

        self.assertEqual(result["status"], "In Progress")
        self.assertTrue(result["qc_checked"])

    def test_complete_only_after_last_required_slot(self):
        board = empty_board_state()
        slots = build_slot_schedule("a4", BASE_DAY.date(), SHIFT_NAME)
        after_last_slot = datetime(2026, 3, 29, 15, 0)

        for slot in slots:
            submission = record_submission(board, "a4", slot["slot_key"], "Operator A", recorded_at=slot["due_at"])
            record_qc_check(board, "a4", submission["id"], "QC A", recorded_at=slot["due_at"])

        before_last_slot = datetime(2026, 3, 29, 14, 0)
        before_result = evaluate_report(board, "a4", SHIFT_NAME, now=before_last_slot)
        after_result = evaluate_report(board, "a4", SHIFT_NAME, now=after_last_slot)

        self.assertEqual(before_result["status"], "In Progress")
        self.assertEqual(after_result["status"], "Complete")

    def test_latest_submission_reopens_qc_status(self):
        board = empty_board_state()
        first_time = datetime(2026, 3, 29, 8, 10)
        second_time = datetime(2026, 3, 29, 8, 20)

        first_submission = record_submission(board, "a4", "3", "Operator A", recorded_at=first_time)
        record_qc_check(board, "a4", first_submission["id"], "QC A", recorded_at=first_time)
        record_submission(board, "a4", "3", "Operator B", recorded_at=second_time)

        result = evaluate_report(board, "a4", SHIFT_NAME, now=second_time)

        self.assertEqual(result["status"], "Sudah disubmit, perlu dicek QC")
        self.assertFalse(result["qc_checked"])
        self.assertEqual(result["submitted_by"], "Operator B")

    def test_lineup_and_exception_logs_are_separate_from_issue_logs(self):
        board = empty_board_state()
        now = datetime(2026, 3, 29, 9, 0)

        update_lineup(board, True, "Supervisor", recorded_at=now)
        add_issue_log(board, "a4", "A-4 Laporan QC di Tablet", "Missed photo", "Requested resend", "QC A", recorded_at=now)
        add_exception_instruction(board, "Use temporary steam threshold", "Steam", "Manager A", recorded_at=now)

        view = build_board_view(board, SHIFT_NAME, now=now)

        self.assertTrue(board["lineup"]["lineup_exists"])
        self.assertEqual(len(view["active_instructions"]), 1)
        self.assertEqual(len(view["recent_issue_logs"]), 1)
        a4_result = next(item for item in view["active_reports"] if item["report_id"] == "a4")
        self.assertEqual(a4_result["issue_log_count"], 1)

    def test_off_today_reports_are_split_out(self):
        board = empty_board_state()
        update_active_reports(board, ["a4", "b3"], "Supervisor", recorded_at=datetime(2026, 3, 29, 6, 50))

        view = build_board_view(board, SHIFT_NAME, now=datetime(2026, 3, 29, 8, 10))

        active_ids = {item["report_id"] for item in view["active_reports"]}
        off_today_ids = {item["report_id"] for item in view["off_today_reports"]}
        self.assertEqual(active_ids, {"a4", "b3"})
        self.assertIn("a5", off_today_ids)


if __name__ == "__main__":
    unittest.main()
