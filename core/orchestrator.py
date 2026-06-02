from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)

from config import settings
from core.blackboard import Blackboard, Phase, ArtifactType, ApprovalPoint
from core.llm_provider import get_provider, LLMProvider
from agents.pm import ProductManagerAgent
from agents.ui_designer import UIDesignerAgent
from agents.backend_dev import BackendDeveloperAgent
from agents.frontend_dev import FrontendDeveloperAgent
from agents.qa_engineer import QAEngineerAgent


def _bugs_affect_agent(bugs: list, vulns: list, area: str) -> bool:
    """判断 Bug 或漏洞是否影响指定领域（backend/frontend）"""
    keywords_map = {
        "backend": ["api", "后端", "backend", "server", "数据库", "database", "sql", "路由",
                     "route", "认证", "auth", "权限", "permission", "接口", "endpoint",
                     "fastapi", "python", "模型", "model", "schema", "import", "依赖"],
        "frontend": ["前端", "frontend", "html", "css", "js", "javascript", "页面",
                      "page", "组件", "component", "ui", "样式", "style", "渲染",
                      "render", "表单", "form", "xss", "dom", "浏览器", "browser"],
    }
    keywords = keywords_map.get(area, [])
    items = list(bugs) + list(vulns)
    for item in items:
        if not isinstance(item, dict):
            continue
        text = json.dumps(item, ensure_ascii=False).lower()
        if any(kw in text for kw in keywords):
            return True
    # 无法判断时只修复前端（前端错误更可见，后端影响面更大时会在第二轮被 QA 捕获）
    return area == "frontend"



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
        self.qa_engineer = QAEngineerAgent()

    def _get_provider(self) -> LLMProvider:
        if not hasattr(self, '_cached_provider') or self._cached_provider is None:
            self._cached_provider = get_provider(self.llm_config)
        return self._cached_provider

    def get_usage_summary(self) -> dict:
        """获取本次运行的 LLM 用量统计"""
        summary = {}
        if hasattr(self, '_cached_provider') and self._cached_provider:
            summary = self._cached_provider.get_usage_summary()
        # 合并输入指纹去重统计
        cache_stats = self.blackboard.get_cache_stats()
        if cache_stats.get("skipped_calls", 0) > 0:
            summary["fingerprint_cache"] = cache_stats
        return summary

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

            await self._resolve_negotiations(max_rounds=1)

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
        # 记录指纹，后续 _phase_frontend() 会检测是否重复
        fp = self.blackboard.input_fingerprint("frontend_developer", self.frontend_dev.get_dependencies())
        self.blackboard.check_and_update_fingerprint("frontend_developer", fp, est_tokens=0)
        self._auto_save()

        await self._resolve_negotiations()

    async def _resolve_negotiations(self, max_rounds: int = 2):
        provider = self._get_provider()
        agent_map = {
            "product_manager": self.pm,
            "ui_designer": self.ui_designer,
            "backend_developer": self.backend_dev,
            "frontend_developer": self.frontend_dev,
            "qa_engineer": self.qa_engineer,
        }

        for _ in range(max_rounds):
            unresolved = [n for n in self.blackboard.negotiation_log if not n.get("resolved")]
            if not unresolved:
                break

            affected_agents = set()
            for neg in unresolved:
                to_agent = neg["to_agent"]
                if to_agent in agent_map:
                    await self.blackboard.emit_event("negotiation_started", {
                        "from": neg["from_agent"],
                        "to": to_agent,
                        "issue": neg["issue"],
                    })
                    agent = agent_map[to_agent]
                    await agent.run(provider, self.blackboard, feedback=neg["suggestion"])
                    neg["resolved"] = True
                    await self.blackboard.emit_event("negotiation_resolved", {
                        "from": neg["from_agent"],
                        "to": to_agent,
                    })
                    affected_agents.add(neg["from_agent"])
                    affected_agents.add(to_agent)

            downstream = set()
            for agent_name in affected_agents:
                if agent_name == "product_manager":
                    downstream.update(["ui_designer", "backend_developer"])
                elif agent_name in ("ui_designer", "backend_developer"):
                    downstream.add("frontend_developer")

            for agent_name in downstream:
                if agent_name in agent_map and agent_name not in affected_agents:
                    await agent_map[agent_name].run(provider, self.blackboard)

            self._auto_save()

    async def _phase_frontend(self):
        self.blackboard.current_phase = Phase.DESIGN_DEV
        # 指纹去重：如果 _phase_design_dev() 已跑过前端且输入未变，跳过
        fp = self.blackboard.input_fingerprint("frontend_developer", self.frontend_dev.get_dependencies())
        if self.blackboard.check_and_update_fingerprint("frontend_developer", fp, est_tokens=6000):
            self.blackboard.update_agent_status("frontend_developer", "completed", 100, "输入未变,跳过重复调用(省6000 tokens)")
            await self.blackboard.emit_event("agent_done", {"agent": "frontend_developer", "display_name": "前端开发", "output_type": "frontend_code", "cached": True})
            logger.info(f"跳过重复Frontend调用，节省约6000 tokens")
            return
        provider = self._get_provider()
        await self.frontend_dev.run(provider, self.blackboard)
        self.blackboard.check_and_update_fingerprint("frontend_developer", fp, est_tokens=0)  # 记录已执行
        self._auto_save()

    async def _phase_qa(self):
        self.blackboard.current_phase = Phase.QA
        await self.blackboard.emit_event("phase_change", {"phase": "qa"})

        provider = self._get_provider()
        # R1: 全量测试+审计；R2+: 增量复查（只验证上一轮的Bug是否修复）
        use_delta = self.blackboard.fix_round > 1
        await self.qa_engineer.run(provider, self.blackboard, is_delta=use_delta)
        self._auto_save()

    async def _phase_fix(self):
        self.blackboard.current_phase = Phase.FIX
        await self.blackboard.emit_event("phase_change", {"phase": "fix"})

        provider = self._get_provider()

        # 智能修复：只修有 Bug 的 Agent，跳过无 Bug 的 + 指纹去重
        test_report = self.blackboard.get_artifact(ArtifactType.TEST_REPORT)
        security_report = self.blackboard.get_artifact(ArtifactType.SECURITY_REPORT)
        bugs = test_report.get("bugs", []) if isinstance(test_report, dict) else []
        vulns = security_report.get("vulnerabilities", []) if isinstance(security_report, dict) else []

        need_backend = _bugs_affect_agent(bugs, vulns, "backend")
        need_frontend = _bugs_affect_agent(bugs, vulns, "frontend")

        tasks = []
        if need_backend:
            fp_be = self.blackboard.input_fingerprint("backend_developer_fix", self.backend_dev.get_dependencies())
            if self.blackboard.check_and_update_fingerprint("backend_developer_fix", fp_be, est_tokens=7000):
                self.blackboard.update_agent_status("backend_developer", "completed", 100, "输入未变,跳过修复(省7000 tokens)")
                await self.blackboard.emit_event("agent_done", {"agent": "backend_developer", "display_name": "后端开发", "cached": True})
            else:
                self.blackboard.update_agent_status("backend_developer", "waiting", 0, "修复中...")
                tasks.append(asyncio.create_task(self.backend_dev.run(provider, self.blackboard, is_fix=True)))
        else:
            self.blackboard.update_agent_status("backend_developer", "skipped", 100, "无相关Bug,跳过")

        if need_frontend:
            fp_fe = self.blackboard.input_fingerprint("frontend_developer_fix", self.frontend_dev.get_dependencies())
            if self.blackboard.check_and_update_fingerprint("frontend_developer_fix", fp_fe, est_tokens=6000):
                self.blackboard.update_agent_status("frontend_developer", "completed", 100, "输入未变,跳过修复(省6000 tokens)")
                await self.blackboard.emit_event("agent_done", {"agent": "frontend_developer", "display_name": "前端开发", "cached": True})
            else:
                self.blackboard.update_agent_status("frontend_developer", "waiting", 0, "修复中...")
                tasks.append(asyncio.create_task(self.frontend_dev.run(provider, self.blackboard, is_fix=True)))
        else:
            self.blackboard.update_agent_status("frontend_developer", "skipped", 100, "无相关Bug,跳过")

        if tasks:
            await asyncio.gather(*tasks)
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
            "qa_engineer": (self.qa_engineer, {}),
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
