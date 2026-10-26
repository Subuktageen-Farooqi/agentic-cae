from concurrent.futures import ThreadPoolExecutor

import pytest

from schemas import WorkflowState as S
from storage import ConflictError, Store
from workflow import TRANSITIONS, Workflow


def advance(workflow, project, target, reason="Test state transition", **kwargs):
    version = workflow.store.project(project)["row_version"]
    return workflow.transition(project, target, expected_version=version, reason=reason, **kwargs)


def test_every_specified_state_has_an_explicit_transition_definition():
    assert set(TRANSITIONS) == set(S)
    assert all(target in S for targets in TRANSITIONS.values() for target in targets)


def test_intake_route_and_brief_states_persist_across_restart(store, project, brief):
    flow = Workflow(store)
    advance(flow, project, S.ROUTE_SELECTION)
    advance(flow, project, S.ADVISOR_CHAT, route="advisor")
    advance(flow, project, S.BRIEF_READY)
    advance(flow, project, S.SPEC_GENERATION)
    restored = Store(store.root).project(project)
    assert restored["state"] == S.SPEC_GENERATION and restored["route"] == "advisor"
    assert len([event for event in store.events(project) if event["kind"] == "state_transition"]) == 4


def test_automatic_route_uses_same_brief_without_extra_confirmation(store, project, brief):
    flow = Workflow(store)
    advance(flow, project, S.ROUTE_SELECTION)
    advance(flow, project, S.BRIEF_READY, route="automatic")
    assert advance(flow, project, S.SPEC_GENERATION)["state"] == S.SPEC_GENERATION
    assert store.brief(project).brief_id == brief.brief_id


def test_generation_without_brief_and_wrong_route_rejected(store, project):
    flow = Workflow(store)
    advance(flow, project, S.ROUTE_SELECTION)
    with pytest.raises(ValueError, match="match"):
        advance(flow, project, S.ADVISOR_CHAT, route="automatic")
    with pytest.raises(ValueError, match="validated brief"):
        advance(flow, project, S.BRIEF_READY, route="automatic")
    assert store.project(project)["state"] == S.ROUTE_SELECTION


def test_invalid_and_stale_transitions_do_not_change_state(store, project):
    flow = Workflow(store)
    with pytest.raises(ValueError, match="Invalid"):
        advance(flow, project, S.REPORT_READY)
    advance(flow, project, S.ROUTE_SELECTION)
    with pytest.raises(ConflictError, match="Stale"):
        flow.transition(project, S.ADVISOR_CHAT, expected_version=0, reason="Old frontend", route="advisor")
    assert store.project(project)["state"] == S.ROUTE_SELECTION


def test_concurrent_state_actions_only_commit_once(store, project):
    version = store.project(project)["row_version"]

    def act(_):
        try:
            Workflow(store).transition(project, S.ROUTE_SELECTION, expected_version=version, reason="Rerun")
            return True
        except ConflictError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(act, range(2))) == 1


@pytest.mark.parametrize("failure", [S.BLOCKED, S.ERROR])
def test_blocked_error_resume_only_to_saved_stage_and_never_run_jobs(store, project, failure):
    flow = Workflow(store)
    advance(flow, project, S.ROUTE_SELECTION)
    blocked = advance(flow, project, failure, reason="Explicit dependency/technical error")
    assert blocked["resume_state"] == S.ROUTE_SELECTION
    with pytest.raises(ValueError):
        advance(flow, project, S.CAD_GENERATION)
    assert store.jobs(project) == []
    restored = advance(flow, project, S.ROUTE_SELECTION, reason="Dependency corrected; explicit resume")
    assert restored["resume_state"] is None


def test_missing_audit_reason_rejected(store, project):
    with pytest.raises(ValueError):
        advance(Workflow(store), project, S.ROUTE_SELECTION, reason=" ")
