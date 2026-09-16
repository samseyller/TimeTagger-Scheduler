from unittest.mock import Mock

import pytest
import requests

from timetagger_scheduler.client import (
    AuthenticationError,
    TimeTaggerClient,
    TimeTaggerError,
    UncertainWriteError,
)
from timetagger_scheduler.models import TimeTaggerRecord


def response(status, body):
    result = Mock(status_code=status, ok=status < 400)
    result.json.return_value = body
    return result


def test_headers_url_gets_and_timeout():
    session = Mock()
    session.headers = {}
    session.get.side_effect = [response(200, {"version": "26.1.3"}), response(200, {"records": []})]
    client = TimeTaggerClient("https://example/api/v2///", "SECRET", 7, session)
    assert client.base_url == "https://example/api/v2/"
    assert client.get_version() == "26.1.3"
    assert client.get_all_records() == []
    assert session.headers["authtoken"] == "SECRET"
    session.get.assert_called_with("https://example/api/v2/updates", timeout=7, params={"since": 0})


def test_put_array_and_parse_result():
    session = Mock()
    session.headers = {}
    session.put.return_value = response(200, {"accepted": ["k"], "failed": [], "errors": []})
    result = TimeTaggerClient("https://x", "t", session=session).create_records(
        [TimeTaggerRecord("k", 1, 2, "d", 3)]
    )
    assert result.accepted == ("k",)
    assert isinstance(session.put.call_args.kwargs["json"], list)


@pytest.mark.parametrize(
    "status,error", [(401, AuthenticationError), (400, TimeTaggerError), (500, TimeTaggerError)]
)
def test_http_errors_do_not_leak_token(status, error):
    session = Mock()
    session.headers = {}
    session.get.return_value = response(status, {})
    with pytest.raises(error) as caught:
        TimeTaggerClient("https://x", "SUPERSECRET", session=session).get_version()
    assert "SUPERSECRET" not in str(caught.value)


def test_put_timeout_is_not_retried():
    session = Mock()
    session.headers = {}
    session.put.side_effect = requests.Timeout("SUPERSECRET")
    client = TimeTaggerClient("https://x", "SUPERSECRET", session=session)
    with pytest.raises(UncertainWriteError) as caught:
        client.create_records([TimeTaggerRecord("k", 1, 2, "d", 3)])
    assert session.put.call_count == 1
    assert "SUPERSECRET" not in str(caught.value)
