import unittest
from unittest.mock import MagicMock, patch

from app.db.models import Task, TaskRun
from app.core.config import settings
from app.services import autoexp_callback_service


class TestAutoExpCallbackService(unittest.TestCase):
    def setUp(self):
        self._old_url = settings.AUTOEXP_CALLBACK_URL
        self._old_token = settings.AUTOEXP_CALLBACK_TOKEN
        self._old_retries = settings.AUTOEXP_CALLBACK_MAX_RETRIES

    def tearDown(self):
        settings.AUTOEXP_CALLBACK_URL = self._old_url
        settings.AUTOEXP_CALLBACK_TOKEN = self._old_token
        settings.AUTOEXP_CALLBACK_MAX_RETRIES = self._old_retries

    def test_disabled_when_url_empty(self):
        settings.AUTOEXP_CALLBACK_URL = ""
        task = Task(id="T1", status="SUCCEEDED")
        ok = autoexp_callback_service.maybe_send_autoexp_callback(
            db=MagicMock(),
            task=task,
            task_run=None,
            mode="final",
            run_dir="/tmp/x",
        )
        self.assertFalse(ok)

    def test_skips_when_not_external(self):
        settings.AUTOEXP_CALLBACK_URL = "http://example/cb"
        task = Task(id="T1", status="SUCCEEDED", user_id=None)
        with patch.object(autoexp_callback_service, "_is_external_task", return_value=False), patch.object(
            autoexp_callback_service._http, "request"
        ) as req:
            ok = autoexp_callback_service.maybe_send_autoexp_callback(
                db=MagicMock(),
                task=task,
                task_run=None,
                mode="final",
                run_dir="/tmp/x",
            )
        self.assertFalse(ok)
        req.assert_not_called()

    def test_sends_when_external_and_2xx(self):
        settings.AUTOEXP_CALLBACK_URL = "http://example/cb"
        settings.AUTOEXP_CALLBACK_TOKEN = "tok"
        settings.AUTOEXP_CALLBACK_MAX_RETRIES = 0

        task = Task(id="T1", status="SUCCEEDED")
        task_run = TaskRun(id="R1", run_mode="final")

        resp = MagicMock()
        resp.status = 200

        with patch.object(autoexp_callback_service, "_is_external_task", return_value=True), patch.object(
            autoexp_callback_service._http, "request", return_value=resp
        ) as req:
            ok = autoexp_callback_service.maybe_send_autoexp_callback(
                db=MagicMock(),
                task=task,
                task_run=task_run,
                mode="final",
                run_dir="/tmp/x",
            )

        self.assertTrue(ok)
        args, kwargs = req.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "http://example/cb")
        self.assertIn("headers", kwargs)
        self.assertEqual(kwargs["headers"].get("X-Callback-Token"), "tok")
        self.assertIn("body", kwargs)

    def test_returns_false_on_non_2xx(self):
        settings.AUTOEXP_CALLBACK_URL = "http://example/cb"
        settings.AUTOEXP_CALLBACK_MAX_RETRIES = 0

        task = Task(id="T1", status="FAILED")
        task_run = TaskRun(id="R1", run_mode="final")

        resp = MagicMock()
        resp.status = 500

        with patch.object(autoexp_callback_service, "_is_external_task", return_value=True), patch.object(
            autoexp_callback_service._http, "request", return_value=resp
        ):
            ok = autoexp_callback_service.maybe_send_autoexp_callback(
                db=MagicMock(),
                task=task,
                task_run=task_run,
                mode="final",
                run_dir="/tmp/x",
                error_code="GUV_RUN_FAILED",
                error_message="x",
            )

        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()

