import json
from typing import Any

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from app.config import Settings
from app.observability import FILTERED, before_breadcrumb, before_send, init_sentry, scrub

CANARY = "CANARY_STUDENT_CODE_8841"
STATEMENT = "CANARY_PROBLEM_TEXT_5520"


class CapturingTransport(Transport):
    def __init__(self, sink: list[Any]):
        super().__init__()
        self.sink = sink

    def capture_envelope(self, envelope: Any) -> None:
        self.sink.append(envelope)


def settings(**kw: Any) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


def test_scrub_removes_sensitive_fields_at_any_depth() -> None:
    event = {
        "extra": {"code": CANARY, "keep": 1},
        "contexts": {"hint": {"request": {"problem": {"content_text": STATEMENT, "slug": "s"}}}},
        "list": [{"student_message": CANARY}, {"ok": True}, "plain"],
        "tuple": ({"Code": CANARY},),
        "UPPER": {"CONTENT_TEXT": STATEMENT},
    }
    cleaned = scrub(event)
    dump = json.dumps(cleaned)
    assert CANARY not in dump and STATEMENT not in dump
    assert cleaned["extra"] == {"code": FILTERED, "keep": 1}
    assert cleaned["contexts"]["hint"]["request"]["problem"] == {
        "content_text": FILTERED, "slug": "s",
    }  # fmt: skip
    assert cleaned["list"][1:] == [{"ok": True}, "plain"]
    assert cleaned["tuple"] == ({"Code": FILTERED},)
    assert event["extra"]["code"] == CANARY  # the input is not mutated


def test_before_send_drops_request_bodies_and_identifying_headers() -> None:
    event = {
        "message": "boom",
        "request": {
            "url": "http://x/v1/hint",
            "method": "POST",
            "data": {"code": CANARY, "problem": {"content_text": STATEMENT}},
            "cookies": {"s": "1"},
            "query_string": "a=b",
            "headers": {"X-Aporia-Device": "dev-uuid", "content-type": "application/json"},
        },
        "extra": {"student_message": CANARY},
    }
    cleaned = before_send(event)
    assert cleaned is not None
    dump = json.dumps(cleaned)
    assert CANARY not in dump and STATEMENT not in dump and "dev-uuid" not in dump
    request = cleaned["request"]
    assert "data" not in request and "cookies" not in request and "query_string" not in request
    assert request["url"] == "http://x/v1/hint" and request["method"] == "POST"
    assert request["headers"]["X-Aporia-Device"] == FILTERED
    assert request["headers"]["content-type"] == "application/json"


def test_before_send_handles_events_without_a_request() -> None:
    assert before_send({"message": "x"}) == {"message": "x"}
    assert before_breadcrumb({"data": {"code": CANARY}, "message": "m"}) == {
        "data": {"code": FILTERED}, "message": "m",
    }  # fmt: skip


def test_sentry_is_off_without_a_dsn() -> None:
    assert init_sentry(settings()) is False
    assert sentry_sdk.get_client().is_active() is False


def test_enabled_with_a_dsn_and_scrubs_what_it_would_send() -> None:
    sent: list[Any] = []
    try:
        assert init_sentry(
            settings(sentry_dsn="https://public@example.invalid/1"),
            transport=CapturingTransport(sent),
        )
        client = sentry_sdk.get_client()
        assert client.is_active()
        opts = client.options
        collection = opts["data_collection"]
        assert collection["user_info"] is False
        assert collection["http_bodies"] == []  # request bodies are never collected
        assert collection["stack_frame_variables"] is False
        assert opts["before_send"] is before_send  # our scrubber is in the pipeline
        sentry_sdk.capture_message("something broke", scope=None)
        with sentry_sdk.new_scope() as scope:
            scope.set_extra("code", CANARY)
            scope.set_context("hint", {"content_text": STATEMENT, "slug": "two-sum"})
            sentry_sdk.capture_exception(RuntimeError("boom"))
        sentry_sdk.flush(timeout=2)
        payload = " ".join(repr(item.get_event() or item.items) for item in sent)
        assert sent, "the exception should have reached the transport"
        assert CANARY not in payload and STATEMENT not in payload
    finally:
        sentry_sdk.get_global_scope().set_client(None)


@pytest.mark.parametrize("dsn", ["", None])
def test_empty_dsn_means_disabled(dsn: Any) -> None:
    assert init_sentry(settings(sentry_dsn=dsn or "")) is False
