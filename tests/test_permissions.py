"""An approval cannot be reused or applied to changed action details."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest

from alicia_core.execution import ExecutionStatus, TaskExecutor
from alicia_core.permissions import ActionRequest, PermissionEngine, Risk
from alicia_core.tool_args import OpenAppArgs
from alicia_core.tools import ToolRegistry, TypedTool


def request(risk: Risk = Risk.REVERSIBLE) -> ActionRequest:
    return ActionRequest(
        request_id=str(uuid4()),
        actor_id="owner",
        device_id="pc-main",
        capability="windows.open_app.v1",
        arguments={"app_id": "editor"},
        risk=risk,
    )


def test_approval_is_single_use_and_bound_to_full_request() -> None:
    policy = PermissionEngine()
    action = request()
    token = policy.issue(action, "owner")
    assert not policy.authorize(replace(action, device_id="phone"), token)
    assert not policy.authorize(replace(action, actor_id="stranger"), token)
    assert not policy.authorize(replace(action, capability="windows.delete.v1"), token)
    assert not policy.authorize(replace(action, arguments={"app_id": "other"}), token)
    assert not policy.authorize(replace(action, request_id=str(uuid4())), token)
    assert policy.authorize(action, token)
    assert not policy.authorize(action, token)


def test_expired_approval_and_unknown_token_are_rejected() -> None:
    now = [100.0]
    policy = PermissionEngine(clock=lambda: now[0])
    action = request()
    token = policy.issue(action, "owner", ttl_sec=3)
    now[0] = 103.0
    assert not policy.authorize(action, token)
    assert not policy.authorize(action, "different")


def test_risk_policy_and_issuer_identity() -> None:
    policy = PermissionEngine()
    assert policy.authorize(request(Risk.READ))
    assert not policy.authorize(request(Risk.EXTERNAL))
    with pytest.raises(ValueError):
        policy.issue(request(Risk.EXTERNAL), "owner")
    with pytest.raises(ValueError):
        policy.issue(request(), "another-user")
    with pytest.raises(ValueError):
        policy.issue(request(), "owner", ttl_sec=301)


def test_concurrent_approval_can_only_be_consumed_once() -> None:
    policy = PermissionEngine()
    action = request()
    token = policy.issue(action, "owner")
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: policy.authorize(action, token), range(30)))
    assert results.count(True) == 1


def test_invalid_arguments_do_not_create_approval() -> None:
    action = request()
    with pytest.raises(ValueError):
        replace(action, arguments={"value": float("nan")})
    with pytest.raises(ValueError):
        replace(action, arguments={"value": object()})
    with pytest.raises(ValueError):
        replace(action, arguments={"value": "x" * 20000})
    with pytest.raises(ValueError):
        replace(action, request_id="not-a-uuid")


def test_authorized_execution_validates_before_consuming_approval() -> None:
    policy = PermissionEngine()
    action = request()
    effects: list[str] = []
    tool = TypedTool(
        action.capability,
        "Abrir aplicación",
        OpenAppArgs,
        lambda args: effects.append(args.app_name) or "iniciado",
        authorize=lambda args: True,
        requires_confirmation=True,
        choices={"app_name": ("editor",)},
        risk=Risk.REVERSIBLE,
    )
    registry = ToolRegistry((tool,))
    action = replace(action, arguments={"app_name": "editor"})
    token = policy.issue(action, "owner")
    assert "distintos" in registry.execute_authorized(
        action.capability, {"app_name": "other"}, action, policy, token
    )
    assert "inválidos" in registry.execute_authorized(
        action.capability,
        {"app_name": "editor", "extra": "x"},
        replace(action, arguments={"app_name": "editor", "extra": "x"}),
        policy,
        token,
    )
    assert "incompatible" in registry.execute_authorized(
        action.capability, {"app_name": "editor"}, replace(action, risk=Risk.READ), policy, token
    )
    assert not effects
    assert (
        registry.execute_authorized(action.capability, {"app_name": "editor"}, action, policy, token)
        == "iniciado"
    )
    assert "denegada" in registry.execute_authorized(
        action.capability, {"app_name": "editor"}, action, policy, token
    )
    assert effects == ["editor"]


def test_bad_local_policy_does_not_consume_remote_approval() -> None:
    policy = PermissionEngine()
    action = replace(request(), arguments={"app_name": "editor"})
    denied = TypedTool(
        action.capability,
        "Abrir",
        OpenAppArgs,
        lambda args: "never",
        authorize=lambda args: False,
        requires_confirmation=True,
        risk=Risk.REVERSIBLE,
    )
    accepted = TypedTool(
        action.capability,
        "Abrir",
        OpenAppArgs,
        lambda args: "ok",
        authorize=lambda args: True,
        requires_confirmation=True,
        risk=Risk.REVERSIBLE,
    )
    token = policy.issue(action, "owner")
    assert "local" in ToolRegistry((denied,)).execute_authorized(
        action.capability, action.arguments, action, policy, token
    )
    assert (
        ToolRegistry((accepted,)).execute_authorized(
            action.capability, action.arguments, action, policy, token
        )
        == "ok"
    )


def test_executor_marks_failed_handler_as_unknown_and_blocks_replay() -> None:
    policy = PermissionEngine()
    action = request()
    token = policy.issue(action, "owner")
    effects: list[str] = []

    def may_have_actuated() -> str:
        effects.append("launched")
        raise OSError("private filesystem detail")

    executor = TaskExecutor()
    result = executor.run(action, policy, may_have_actuated, token)
    assert result.status is ExecutionStatus.UNKNOWN
    assert "private filesystem detail" not in result.message
    again = executor.run(action, policy, may_have_actuated, token)
    assert again.status is ExecutionStatus.DENIED
    assert effects == ["launched"]
