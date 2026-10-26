"""Deterministic workflow skeleton. Stage adapters/business gates follow in M2–M8.

Transitions are persisted atomically with optimistic concurrency. Merely moving
state is not proof that a stage executed: only its verified artifacts can be.
"""

from schemas import WorkflowState as S
from storage import ConflictError, Store


TRANSITIONS: dict[S, frozenset[S]] = {
    S.INTAKE: frozenset({S.ROUTE_SELECTION}),
    S.ROUTE_SELECTION: frozenset({S.ADVISOR_CHAT, S.BRIEF_READY}),
    S.ADVISOR_CHAT: frozenset({S.BRIEF_READY}),
    S.BRIEF_READY: frozenset({S.ADVISOR_CHAT, S.SPEC_GENERATION}),
    S.SPEC_GENERATION: frozenset({S.CAD_GENERATION}),
    S.CAD_GENERATION: frozenset({S.CAD_EXECUTION}),
    S.CAD_EXECUTION: frozenset({S.FREECAD_VALIDATION, S.CAD_GENERATION}),
    S.FREECAD_VALIDATION: frozenset({S.RULE_CHECKS, S.CAD_GENERATION}),
    S.RULE_CHECKS: frozenset({S.DESIGN_REVIEW, S.CAD_GENERATION}),
    S.DESIGN_REVIEW: frozenset({S.SPEC_GENERATION, S.RESTART_OFFER, S.ANALYSIS_INTAKE}),
    S.RESTART_OFFER: frozenset({S.ADVISOR_CHAT, S.BRIEF_READY, S.ROUTE_SELECTION}),
    S.ANALYSIS_INTAKE: frozenset({S.ANALYSIS_SPEC_REVIEW}),
    S.ANALYSIS_SPEC_REVIEW: frozenset({S.ANALYSIS_INTAKE, S.ANALYSIS_EXECUTION}),
    S.ANALYSIS_EXECUTION: frozenset({S.REPORT_READY}),
    S.REPORT_READY: frozenset({S.ANALYSIS_INTAKE}),
    S.BLOCKED: frozenset(),
    S.ERROR: frozenset(),
}


class Workflow:
    def __init__(self, store: Store):
        self.store = store

    def transition(self, project_id: str, target: S, *, expected_version: int,
                   reason: str, route: str | None = None) -> dict:
        target = S(target)
        if not reason.strip():
            raise ValueError("State transitions require an audit reason")
        if route not in (None, "advisor", "automatic"):
            raise ValueError("Unknown route")
        with self.store._connection(write=True) as db:
            project = self.store._project_row(db, project_id)
            current = S(project["state"])
            if project["row_version"] != expected_version:
                raise ConflictError("Stale workflow action; reload project state")
            recovery = current in (S.BLOCKED, S.ERROR) and target.value == project["resume_state"]
            failure = current not in (S.BLOCKED, S.ERROR) and target in (S.BLOCKED, S.ERROR)
            if target not in TRANSITIONS[current] and not recovery and not failure:
                raise ValueError(f"Invalid workflow transition {current} → {target}")
            if route is not None and current != S.ROUTE_SELECTION:
                raise ValueError("Route selection is only allowed at route selection")
            if current == S.ROUTE_SELECTION and target not in (S.BLOCKED, S.ERROR):
                expected_route = "advisor" if target == S.ADVISOR_CHAT else "automatic"
                if route != expected_route:
                    raise ValueError("Route choice must match its target state")
            if target in (S.BRIEF_READY, S.SPEC_GENERATION) and project["brief_version"] == 0:
                raise ValueError("Create a validated brief before generation")
            # These transitions need business gates not yet available in M1.
            if (current, target) in {(S.DESIGN_REVIEW, S.ANALYSIS_INTAKE),
                                      (S.ANALYSIS_SPEC_REVIEW, S.ANALYSIS_EXECUTION)}:
                raise ValueError("Acceptance/analysis confirmation gate is not implemented yet")
            resume_state = current.value if failure else None
            db.execute("UPDATE projects SET state=?,row_version=row_version+1,route=COALESCE(?,route),resume_state=? WHERE project_id=?",
                       (target.value, route, resume_state, project_id))
            self.store._event(db, project_id, "state_transition", {
                "from": current.value, "to": target.value, "reason": reason,
                "row_version": expected_version + 1, "route": route,
            })
        return self.store.project(project_id)
