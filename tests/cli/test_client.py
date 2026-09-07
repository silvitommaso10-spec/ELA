"""The client itself: what it reads, where it points, and how it reports an answer it cannot use.

Everything here is about the CLI's own edges. That the commands work against the real API is
proved by the other modules, which drive them through it.
"""

from __future__ import annotations

import httpx
import pytest

from ela.cli import client
from ela.composition import ApiSettings, ConfigurationError
from tests.cli.support import refusing
from tests.composition.support import TOKEN


def settings_of(host: str = "127.0.0.1", port: int = 8351) -> ApiSettings:
    return ApiSettings(_env_file=None, api_token=TOKEN, api_host=host, api_port=port)  # type: ignore[call-arg]


def test_query_keeps_only_what_was_asked_for() -> None:
    assert client.query(state=None, limit=3, task_id="a") == {"limit": 3, "task_id": "a"}
    assert client.query(state=[], limit=None) == {}


def test_the_address_is_the_one_the_settings_declare() -> None:
    assert client.base_url(settings_of(port=9000)) == "http://127.0.0.1:9000"


def test_a_numeric_ipv6_address_is_bracketed() -> None:
    """``::1`` is loopback and a URL needs it in brackets, or the port is read as part of it."""
    assert client.base_url(settings_of(host="::1")) == "http://[::1]:8351"


def test_the_settings_are_the_three_a_client_needs(monkeypatch: pytest.MonkeyPatch) -> None:
    """A routing table with a typo in it does not stop ``ela health``: it is not about that."""
    monkeypatch.setenv("ELA_API_TOKEN", TOKEN)
    monkeypatch.setenv("ELA_MODEL_ROUTES", "{not json")

    assert client.api_settings().token == TOKEN


def test_a_configuration_failure_names_its_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELA_API_TOKEN", TOKEN)
    monkeypatch.setenv("ELA_API_PORT", "not a port")

    with pytest.raises(ConfigurationError, match="ELA_API_PORT"):
        client.api_settings()


def test_connect_carries_the_token_to_the_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELA_API_TOKEN", TOKEN)
    monkeypatch.setenv("ELA_API_PORT", "9000")

    with client.connect() as opened:
        request = opened._client.build_request("GET", "/health")

    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert str(request.url) == "http://127.0.0.1:9000/health"


def test_the_connection_has_a_timeout_but_the_answer_does_not() -> None:
    """``run`` walks the plan inside the request: an answer may take as long as a model call."""
    with client.open_client(settings_of()) as opened:
        timeout = opened._client.timeout

    assert timeout.connect == client.CONNECT_TIMEOUT
    assert timeout.read is None


def test_an_error_body_of_elas_own_shape_becomes_its_code_and_message() -> None:
    body = '{"error": {"code": "not_found", "message": "no such task"}}'
    with (
        client.open_client(settings_of(), refusing(404, body, "application/json")) as opened,
        pytest.raises(client.ApiRefusal) as raised,
    ):
        opened.get("/tasks/x")

    assert (raised.value.status, raised.value.code) == (404, "not_found")
    assert raised.value.message == "no such task"


@pytest.mark.parametrize(
    ("body", "content_type"),
    [("<html>gateway</html>", "text/html"), ('{"detail": "elsewhere"}', "application/json")],
    ids=["not-json", "another-shape"],
)
def test_an_answer_that_did_not_come_from_ela_is_reported_as_its_status(
    body: str, content_type: str
) -> None:
    """Never guessed at: a body ELA did not write is reported as the status code it arrived with."""
    with (
        client.open_client(settings_of(), refusing(502, body, content_type)) as opened,
        pytest.raises(client.ApiRefusal) as raised,
    ):
        opened.get("/health")

    assert raised.value.code == "http_502"
    assert body.strip() in raised.value.message


def test_a_transport_that_cannot_connect_becomes_unreachable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with (
        client.open_client(settings_of(), httpx.MockTransport(refuse)) as opened,
        pytest.raises(client.Unreachable, match="ela serve"),
    ):
        opened.post("/tasks", {"text": "x"})
