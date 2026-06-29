from apscheduler.schedulers.asyncio import AsyncIOScheduler

import app.main as main
import app.scheduler.billing_scheduler as billing_scheduler_module


class TestBillingScheduler:
    def test_main_uses_billing_scheduler_module_wrapper(self):
        """
        main.py は AsyncIOScheduler インスタンスではなく、
        job登録を行う billing_scheduler module wrapper を参照する。
        """
        assert main.billing_scheduler is billing_scheduler_module

    def test_start_registers_billing_jobs(self, monkeypatch):
        """start() wrapper が課金バッチ用 job を登録することを検証。"""
        scheduler = AsyncIOScheduler()
        monkeypatch.setattr(billing_scheduler_module, "billing_scheduler", scheduler)

        billing_scheduler_module.start()

        try:
            job_ids = {job.id for job in scheduler.get_jobs()}
            assert job_ids == {
                "check_trial_expiration",
                "check_scheduled_cancellation",
            }
            assert scheduler.running is True
        finally:
            billing_scheduler_module.shutdown()

    def test_multiple_start_calls_do_not_duplicate_jobs(self, monkeypatch):
        """start() を複数回呼んでも job が重複しないことを検証。"""
        scheduler = AsyncIOScheduler()
        monkeypatch.setattr(billing_scheduler_module, "billing_scheduler", scheduler)

        billing_scheduler_module.start()
        billing_scheduler_module.start()

        try:
            jobs = scheduler.get_jobs()
            assert len(jobs) == 2
            assert {job.id for job in jobs} == {
                "check_trial_expiration",
                "check_scheduled_cancellation",
            }
        finally:
            billing_scheduler_module.shutdown()

    def test_shutdown_before_start_is_safe(self, monkeypatch):
        """未起動状態で shutdown() を呼んでも例外にならないことを検証。"""
        scheduler = AsyncIOScheduler()
        monkeypatch.setattr(billing_scheduler_module, "billing_scheduler", scheduler)

        billing_scheduler_module.shutdown()
