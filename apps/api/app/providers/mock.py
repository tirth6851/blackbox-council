"""Deterministic, scripted provider used for mock mode and for every
automated council/counterfactual test. It never calls a network and never
follows instructions embedded in repository content — it only reads the
task text and the fixed fixture facts it is handed."""
from __future__ import annotations

import datetime as dt

from app.council.contracts import ActionAssessment, ArbiterOutput, Concern, PlannerOutput, PrivacyOutput, RedTeamOutput
from app.counterfactuals.scoring import compute_risk_ratings
from app.providers.base import CallMetadata, Provider, ProviderResult
from app.schemas import CandidateAction, ContextItem, PolicyFinding, Scenario
from app.services.fixture_loader import RetentionPolicy
from app.services.policy_engine import evaluate_context

_DELETE_SYNONYMS = ("delet", "remov")
_READ_ONLY_MARKERS = ("dry run only", "do not change")

MODEL_NAME = "scripted-mock-v1"


def _is_read_only(task: str) -> bool:
    lowered = task.lower()
    return any(marker in lowered for marker in _READ_ONLY_MARKERS)


def _is_delete_capable(task: str) -> bool:
    lowered = task.lower()
    return any(syn in lowered for syn in _DELETE_SYNONYMS)


def _has_inactivity_constraint(task: str) -> bool:
    return "inactive" in task.lower()


def _eligible_file_ids(files: dict[str, dict], policy: dict) -> list[str]:
    eligible = []
    for fid, meta in files.items():
        if policy["exclude_legal_hold"] and meta["legal_hold"]:
            continue
        if meta["inactive_days"] < policy["inactive_days_min"]:
            continue
        if meta["modified_days"] < policy["modified_days_min"]:
            continue
        if policy["require_known_owner"] and meta["owner_id"] is None:
            continue
        eligible.append(fid)
    return sorted(eligible)


def _unknown_owner_file_ids(files: dict[str, dict]) -> list[str]:
    return sorted(fid for fid, meta in files.items() if meta["owner_id"] is None)


def _generic_scenarios(candidate: CandidateAction) -> list[Scenario]:
    op = candidate.operation
    files_txt = ",".join(candidate.file_ids) if candidate.file_ids else "no specific file"
    return [
        Scenario(
            id=f"scenario-best-{candidate.id}",
            candidate_id=candidate.id,
            kind="best",
            premise="A human reviews the proposal exactly as scoped.",
            outcome=f"The {op} proposal for {files_txt} proceeds exactly as scoped; nothing outside it is touched.",
            evidence_ids=["ctx-policy", "ctx-metadata"],
            mitigation="None required; safeguards already match policy.",
        ),
        Scenario(
            id=f"scenario-likely-failure-{candidate.id}",
            candidate_id=candidate.id,
            kind="likely_failure",
            premise="The proposal is reviewed before every prerequisite is satisfied.",
            outcome=(
                f"A prerequisite for the {op} proposal (approval, a missing fact, or a "
                "safeguard) is not yet satisfied when first reviewed."
            ),
            evidence_ids=["ctx-policy"],
            mitigation="Surface the missing prerequisite before approval is possible.",
        ),
        Scenario(
            id=f"scenario-worst-{candidate.id}",
            candidate_id=candidate.id,
            kind="worst",
            premise="An operator tries to widen scope after the plan is generated.",
            outcome=(
                f"An operator tries to broaden the {op} proposal beyond {files_txt}; "
                "deterministic policy checks refuse the broadened request regardless."
            ),
            evidence_ids=["ctx-metadata"],
            mitigation="Deterministic policy checks are re-run at execution time, not only at plan time.",
        ),
    ]


class MockProvider(Provider):
    name = "mock"

    async def generate(self, *, role, system_prompt, input_payload, output_model, prompt_version):
        requested_at = dt.datetime.now(dt.timezone.utc)
        builders = {
            "planner": self._build_planner,
            "red_team": self._build_red_team,
            "privacy": self._build_privacy,
            "arbiter": self._build_arbiter,
        }
        builder = builders.get(role)
        if builder is None:
            raise ValueError(f"MockProvider has no scripted builder for role {role!r}")
        output = builder(input_payload)
        completed_at = dt.datetime.now(dt.timezone.utc)
        metadata = CallMetadata(
            provider=self.name,
            model=MODEL_NAME,
            role=role,
            prompt_version=prompt_version,
            schema_version="1.0",
            requested_at=requested_at,
            completed_at=completed_at,
            duration_ms=(completed_at - requested_at).total_seconds() * 1000,
            input_tokens=None,
            output_tokens=None,
            attempt=1,
            finish_reason="stop",
            validation_status="valid",
            provider_request_id=None,
            error_category=None,
        )
        return ProviderResult(output=output, metadata=metadata)

    # -- role builders --------------------------------------------------

    def _build_planner(self, payload: dict) -> PlannerOutput:
        task: str = payload["task"]
        files: dict[str, dict] = payload["files"]
        policy: dict = payload["policy"]

        eligible = _eligible_file_ids(files, policy)
        primary_id = eligible[0] if eligible else None
        unknown_owner = _unknown_owner_file_ids(files)
        read_only = _is_read_only(task)
        delete_capable = _is_delete_capable(task)
        has_constraint = _has_inactivity_constraint(task)

        candidates: list[CandidateAction] = []

        if not delete_capable:
            # e.g. replace_verb: the user asked to archive, not delete.
            if primary_id:
                candidates.append(
                    CandidateAction(
                        id="archive",
                        operation="archive",
                        file_ids=[primary_id],
                        dry_run=True,
                        backup_manifest=True,
                        recovery_days=policy["recovery_days_min"],
                        rationale=f"Archive eligible file {primary_id} with dry run, backup manifest, and recovery window.",
                    )
                )
                candidates.append(
                    CandidateAction(
                        id="dry_run",
                        operation="dry_run",
                        file_ids=[primary_id],
                        dry_run=True,
                        backup_manifest=False,
                        recovery_days=0,
                        rationale=f"Produce a read-only dry run identifying eligible file {primary_id}.",
                    )
                )
        elif read_only:
            if primary_id:
                candidates.append(
                    CandidateAction(
                        id="dry_run",
                        operation="dry_run",
                        file_ids=[primary_id],
                        dry_run=True,
                        backup_manifest=False,
                        recovery_days=0,
                        rationale=(
                            f"The task explicitly requests a dry run only; produce a read-only "
                            f"manifest for eligible file {primary_id} and change nothing."
                        ),
                    )
                )
        else:
            delete_scope = (
                eligible if has_constraint else sorted(
                    fid for fid, meta in files.items()
                    if not (policy["exclude_legal_hold"] and meta["legal_hold"])
                )
            )
            candidates.append(
                CandidateAction(
                    id="delete",
                    operation="delete",
                    file_ids=delete_scope,
                    dry_run=False,
                    backup_manifest=False,
                    recovery_days=0,
                    rationale="Directly delete the requested files to reduce storage costs.",
                )
            )
            if primary_id:
                candidates.append(
                    CandidateAction(
                        id="dry_run",
                        operation="dry_run",
                        file_ids=[primary_id],
                        dry_run=True,
                        backup_manifest=False,
                        recovery_days=0,
                        rationale=f"Produce a read-only dry run identifying eligible file {primary_id}.",
                    )
                )
                candidates.append(
                    CandidateAction(
                        id="archive",
                        operation="archive",
                        file_ids=[primary_id],
                        dry_run=True,
                        backup_manifest=True,
                        recovery_days=policy["recovery_days_min"],
                        rationale=f"Archive eligible file {primary_id} with dry run, backup manifest, and recovery window.",
                    )
                )

        if unknown_owner and len(candidates) < 4:
            candidates.append(
                CandidateAction(
                    id="clarify",
                    operation="clarify",
                    file_ids=[],
                    dry_run=True,
                    backup_manifest=False,
                    recovery_days=0,
                    rationale=f"Ask whether {', '.join(unknown_owner)} should be included once ownership is confirmed.",
                )
            )

        if not candidates:
            candidates.append(
                CandidateAction(
                    id="clarify",
                    operation="clarify",
                    file_ids=[],
                    dry_run=True,
                    backup_manifest=False,
                    recovery_days=0,
                    rationale="No file is currently eligible or clearly in scope; ask for clarification.",
                )
            )

        archive_id = next((c.id for c in candidates if c.operation == "archive"), None)
        dry_run_id = next((c.id for c in candidates if c.operation == "dry_run"), None)
        clarify_id = next((c.id for c in candidates if c.operation == "clarify"), None)
        preferred_id = archive_id or dry_run_id or clarify_id or candidates[0].id

        if archive_id:
            suggested_outcome = "approval_required"
        elif dry_run_id and preferred_id == dry_run_id:
            suggested_outcome = "safe"
        else:
            suggested_outcome = "clarification_required"

        preferred_candidate = next(c for c in candidates if c.id == preferred_id)
        scenarios = _generic_scenarios(preferred_candidate)

        assumptions = [f"{fid} meets the current eligibility policy." for fid in eligible]
        unanswered = [f"Who owns {fid}, and should it be included once confirmed?" for fid in unknown_owner]

        return PlannerOutput(
            task_summary=f"[MOCK] {task}",
            assumptions=assumptions,
            unanswered_questions=unanswered,
            candidates=candidates,
            preferred_candidate_id=preferred_id,
            suggested_outcome=suggested_outcome,
            scenarios=scenarios,
        )

    def _build_red_team(self, payload: dict) -> RedTeamOutput:
        candidate_decisions: dict[str, dict] = payload["candidate_decisions"]
        context_items = [ContextItem.model_validate(c) for c in payload.get("context", [])]
        trust_findings = evaluate_context(context_items)
        injection_ids = sorted({eid for f in trust_findings for eid in f.evidence})

        assessments = [
            ActionAssessment(
                candidate_id=cid,
                suggested_outcome=dec["outcome"],
                concerns=_concerns_from_findings(cid, dec["findings"]),
            )
            for cid, dec in candidate_decisions.items()
        ]
        summary = "[MOCK] Reviewed each candidate for misuse, scope expansion, and injected instructions."
        if injection_ids:
            summary += " An untrusted instruction-override document is present but followed by no candidate."
        return RedTeamOutput(summary=summary, assessments=assessments, injection_evidence_ids=injection_ids)

    def _build_privacy(self, payload: dict) -> PrivacyOutput:
        candidate_decisions: dict[str, dict] = payload["candidate_decisions"]
        preferred_id = payload.get("preferred_candidate_id")
        candidates_by_id = {c["id"]: c for c in payload["planner_candidates"]}

        assessments = [
            ActionAssessment(
                candidate_id=cid,
                suggested_outcome=dec["outcome"],
                concerns=_concerns_from_findings(cid, dec["findings"]),
            )
            for cid, dec in candidate_decisions.items()
        ]

        risk_ratings = []
        if preferred_id and preferred_id in candidate_decisions:
            candidate = CandidateAction.model_validate(candidates_by_id[preferred_id])
            findings = [PolicyFinding.model_validate(f) for f in candidate_decisions[preferred_id]["findings"]]
            policy = RetentionPolicy.from_dict(payload["policy"])
            risk_ratings = compute_risk_ratings(candidate, findings, policy)

        summary = "[MOCK] Assessed user-data impact, ownership, retention, and recovery for each candidate."
        return PrivacyOutput(summary=summary, assessments=assessments, risk_ratings=risk_ratings)

    def _build_arbiter(self, payload: dict) -> ArbiterOutput:
        candidate_decisions: dict[str, dict] = payload["candidate_decisions"]
        allowed_ids: list[str] = payload["allowed_candidate_ids"]
        preferred_id = payload.get("preferred_candidate_id")

        selected_id = preferred_id if preferred_id in allowed_ids else (allowed_ids[0] if allowed_ids else None)
        outcome = candidate_decisions[selected_id]["outcome"] if selected_id else "blocked"

        summary = (
            f"[MOCK] Synthesized planner, red-team, and privacy assessments; recommending "
            f"candidate '{selected_id}'." if selected_id else "[MOCK] No candidate is currently permitted."
        )
        return ArbiterOutput(
            selected_candidate_id=selected_id,
            suggested_outcome=outcome,
            summary=summary,
            evidence_ids=["ctx-policy", "ctx-metadata"],
            required_facts=payload.get("unanswered_questions", []),
            required_safeguards=[],
        )


def _concerns_from_findings(candidate_id: str, findings: list[dict]) -> list[Concern]:
    concerns = []
    for finding in findings:
        if finding["status"] != "triggered" or finding["effect"] not in ("block", "clarify", "safeguard"):
            continue
        category = "injection" if finding["rule_id"] == "TRUST-001" else (
            "scope_expansion" if finding["rule_id"] in ("SCOPE-001", "HOLD-001") else "other"
        )
        severity = {"block": "critical", "clarify": "high", "safeguard": "moderate"}[finding["effect"]]
        concerns.append(
            Concern(
                id=f"concern-{candidate_id}-{finding['rule_id']}",
                candidate_id=candidate_id,
                category=category,
                severity=severity,
                evidence_ids=finding.get("evidence", []),
                explanation=finding["explanation"][:800],
                remediation=finding["remediation"][:500],
            )
        )
    return concerns
