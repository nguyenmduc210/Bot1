from __future__ import annotations

from handlers.callbacks import parse_callback_data, resolve_callback_route


def test_callback_action_routing_single() -> None:
    action, job_id = parse_callback_data("ytv:job123")
    route = resolve_callback_route(action)
    assert action == "ytv"
    assert job_id == "job123"
    assert route.is_playlist is False
    assert route.is_album is False


def test_callback_action_routing_playlist() -> None:
    action, job_id = parse_callback_data("ytpldoc:job999")
    route = resolve_callback_route(action)
    assert action == "ytpldoc"
    assert job_id == "job999"
    assert route.is_playlist is True
    assert route.is_album is False


def test_callback_action_routing_soundcloud_playlist() -> None:
    action, job_id = parse_callback_data("scplmus:job777")
    route = resolve_callback_route(action)
    assert action == "scplmus"
    assert job_id == "job777"
    assert route.is_playlist is True
    assert route.is_album is False


def test_callback_action_routing_album() -> None:
    action, job_id = parse_callback_data("img:job555")
    route = resolve_callback_route(action)
    assert route.is_album is True
    assert route.is_playlist is False
