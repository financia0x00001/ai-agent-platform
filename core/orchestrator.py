from __future__ import annotations

import asyncio
import time
from typing import Callable

from config import settings
from core.blackboard import Blackboard, Phase, ArtifactType, ApprovalPoint
from core.llm_provider import get_provider, LLMProvider
from agents.pm import ProductManagerAgent
from agents.ui_designer import UIDesignerAgent
from agents.backend_dev import BackendDeveloperAgent
from agents.frontend_dev import FrontendDeveloperAgent
from agents.tester import TesterAgent
from agents.auditor import SecurityAuditorAgent


class Orchestrator:
    def __init__(self, blackboard: Blackboard, llm_config: dict | None = None, project_meta: dict | None = None):
        self.blackboard = blackboard
        self.llm_config = llm_config
        self.project_meta = project_meta
        self._running = False
        self._cancelled = False

        self.pm = ProductManagerAgent()
        self.ui_designer = UIDesignerAgent()
        self.backend_dev = BackendDeveloperAgent()
        self.frontend_dev = FrontendDeveloperAgent()
        self.tester = TesterAgent()
        self.auditor = SecurityAuditorAgent()

    def _get_provider(self) -> LLMProvider:
        if not hasattr(self, '_cached_provider') or self._cached_provider is None:
            self._cached_provider = get_provider(self.llm_config)
        return self._cached_provider

    def get_usage_summary(self) -> dict:
        """获取本次运行的 LLM 用量统计"""
        if hasattr(self, '_cached_provider') and self._cached_provider:
            return self._cached_provider.get_usage_summary()
        return {}

    async def run(self, requirement: str):
        self._running = True
        self._cancelled = False

        try:
            self.blackboard.set_artifact(ArtifactType.USER_REQUIREMENT, requirement)
            await self.blackboard.emit_event("workflow_start", {"requirement": requirement})

            await self._phase_requirement()
            if self._cancelled:
                return

            decision = await self.blackboard.wait_for_approval(ApprovalPoint.AFTER_PRD)
            if self._cancelled:
                return
            while decision.get("action") != "approve":
                if decision.get("action") == "reject":
                    await self._rerun_agents(decision.get("rerun_agents", ["product_manager"]), decision.get("feedback", ""))
                elif decision.get("action") == "rerun":
                    await self._rerun_agents(decision.get("rerun_agents", ["product_manager"]), decision.get("feedback", ""))
                if self._cancelled:
                    return
                decision = await self.blackboard.wait_for_approval(ApprovalPoint.AFTER_PRD)

            await self._phase_design_dev()
            if self._cancelled:
                return

            decision = await self.blackboard.wait_for_approval(ApprovalPoint.AFTER_DESIGN)
            if self._cancelled:
                return
            while decision.get("action") != "approve":
                rerun_list = decision.get("rerun_agents", ["ui_designer", "backend_developer"])
                await self._rerun_agents(rerun_list, decision.get("feedback", ""))
                if self._cancelled:
                    return
                decision = await self.blackboard.wait_for_approval(ApprovalPoint.AFTER_DESIGN)

            await self._phase_frontend()
            if self._cancelled:
                return

            decision = await self.blackboard.wait_for_approval(ApprovalPoint.AFTER_FRONTEND)
            if self._cancelled:
                return
            while decision.get("action") != "approve":
                rerun_list = decision.get("rerun_agents", ["frontend_developer"])
                await self._rerun_agents(rerun_list, decision.get("feedback", ""))
                if self._cancelled:
                    return
                decision = await self.blackboard.wait_for_approval(ApprovalPoint.AFTER_FRONTEND)

            for round_num in range(settings.max_fix_rounds):
                self.blackboard.fix_round = round_num + 1
                await self._phase_qa()
                if self._cancelled:
                    return

                if self._all_passed():
                    break

                await self._phase_fix()
                if self._cancelled:
                    return

            self.blackboard.current_phase = Phase.DONE
            qa_passed = self._all_passed()
            await self.blackboard.emit_event("workflow_done", {
                "fix_rounds": self.blackboard.fix_round,
                "qa_passed": qa_passed,
            })

        except Exception as e:
            await self.blackboard.emit_event("workflow_error", {"error": str(e)})
        finally:
            self._running = False

    async def _phase_requirement(self):
        self.blackboard.current_phase = Phase.REQUIREMENT
        await self.blackboard.emit_event("phase_change", {"phase": "requirement"})

        provider = self._get_provider()
        await self.pm.run(provider, self.blackboard)
        self._auto_save()

    async def _phase_design_dev(self):
        self.blackboard.current_phase = Phase.DESIGN_DEV
        await self.blackboard.emit_event("phase_change", {"phase": "design_dev"})

        provider = self._get_provider()

        ui_task = asyncio.create_task(self.ui_designer.run(provider, self.blackboard))
        be_task = asyncio.create_task(self.backend_dev.run(provider, self.blackboard))

        await asyncio.gather(ui_task, be_task)
        self._auto_save()

        await self.frontend_dev.run(provider, self.blackboard)
        self._auto_save()

    async def _phase_frontend(self):
        self.blackboard.current_phase = Phase.DESIGN_DEV
        provider = self._get_provider()
        await self.frontend_dev.run(provider, self.blackboard)
        self._auto_save()

    async def _phase_qa(self):
        self.blackboard.current_phase = Phase.QA
        await self.blackboard.emit_event("phase_change", {"phase": "qa"})

        provider = self._get_provider()

        test_task = asyncio.create_task(self.tester.run(provider, self.blackboard))
        audit_task = asyncio.create_task(self.auditor.run(provider, self.blackboard))

        await asyncio.gather(test_task, audit_task)
        self._auto_save()

    async def _phase_fix(self):
        self.blackboard.current_phase = Phase.FIX
        await self.blackboard.emit_event("phase_change", {"phase": "fix"})

        provider = self._get_provider()

        self.blackboard.update_agent_status("frontend_developer", "waiting", 0, "修复中...")
        self.blackboard.update_agent_status("backend_developer", "waiting", 0, "修复中...")

        be_task = asyncio.create_task(self.backend_dev.run(provider, self.blackboard, is_fix=True))
        fe_task = asyncio.create_task(self.frontend_dev.run(provider, self.blackboard, is_fix=True))

        await asyncio.gather(be_task, fe_task)
        self._auto_save()

    async def _rerun_agents(self, agent_names: list[str], feedback: str):
        provider = self._get_provider()
        await self.blackboard.emit_event("agents_rerun", {
            "agents": agent_names,
            "feedback": feedback,
        })

        agent_map = {
            "product_manager": (self.pm, {}),
            "ui_designer": (self.ui_designer, {}),
            "backend_developer": (self.backend_dev, {}),
            "frontend_developer": (self.frontend_dev, {}),
            "tester": (self.tester, {}),
            "security_auditor": (self.auditor, {}),
        }

        for name in agent_names:
            if name in agent_map:
                agent, kwargs = agent_map[name]
                self.blackboard.update_agent_status(name, "waiting", 0, "根据反馈修改中...")
                await agent.run(provider, self.blackboard, feedback=feedback, **kwargs)

        self._auto_save()

    def _all_passed(self) -> bool:
        test_report = self.blackboard.get_artifact(ArtifactType.TEST_REPORT)
        security_report = self.blackboard.get_artifact(ArtifactType.SECURITY_REPORT)

        test_passed = True
        if test_report and isinstance(test_report, dict):
            test_passed = test_report.get("all_passed", False)

        security_passed = True
        if security_report and isinstance(security_report, dict):
            security_passed = security_report.get("all_passed", False)

        return test_passed and security_passed

    async def retry_qa(self):
        """仅重跑 QA + 修复阶段，用于 needs_review 项目，保留已有产出物"""
        self._running = True
        self._cancelled = False

        try:
            await self.blackboard.emit_event("workflow_start", {"requirement": "(retry QA)"})

            # 从 QA 阶段开始，利用已有 Bug 清单进行修复
            for round_num in range(settings.max_fix_rounds):
                self.blackboard.fix_round = self.blackboard.fix_round + 1
                await self._phase_qa()
                if self._cancelled:
                    return

                if self._all_passed():
                    break

                await self._phase_fix()
                if self._cancelled:
                    return

            self.blackboard.current_phase = Phase.DONE
            qa_passed = self._all_passed()
            await self.blackboard.emit_event("workflow_done", {
                "fix_rounds": self.blackboard.fix_round,
                "qa_passed": qa_passed,
            })

        except Exception as e:
            await self.blackboard.emit_event("workflow_error", {"error": str(e)})
        finally:
            self._running = False

    def cancel(self):
        self._cancelled = True
        if self.blackboard._approval_event:
            self.blackboard._approval_decision = {"action": "approve"}
            self.blackboard._approval_event.set()

    def _auto_save(self):
        if self.project_meta:
            from core.persistence import save_project
            save_project(self.blackboard.project_id, self.project_meta, self.blackboard)

    @property
    def is_running(self) -> bool:
        return self._running
