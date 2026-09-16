from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import PutResult, TimeTaggerRecord


class TimeTaggerError(RuntimeError):
    """A definite API or connectivity failure."""


class AuthenticationError(TimeTaggerError):
    """TimeTagger rejected authentication."""


class UncertainWriteError(TimeTaggerError):
    """A PUT may have reached the server and must not be retried."""


class TimeTaggerClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 10,
        session: requests.Session | None = None,
    ):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "authtoken": token,
                "User-Agent": "timetagger-scheduler/0.1",
                "Accept": "application/json",
            }
        )
        if session is None:
            retry = Retry(
                total=3,
                connect=3,
                read=3,
                status=3,
                backoff_factor=0.3,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset({"GET"}),
            )
            self.session.mount("http://", HTTPAdapter(max_retries=retry))
            self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def _get(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.session.get(self.base_url + endpoint, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise TimeTaggerError(f"TimeTagger GET failed: {type(exc).__name__}") from exc
        return self._decode(response)

    @staticmethod
    def _decode(response: requests.Response) -> dict[str, Any]:
        if response.status_code == 401:
            raise AuthenticationError("TimeTagger authentication failed (HTTP 401)")
        if not response.ok:
            raise TimeTaggerError(f"TimeTagger API returned HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise TimeTaggerError("TimeTagger returned invalid JSON") from exc
        if not isinstance(body, dict):
            raise TimeTaggerError("TimeTagger returned an unexpected response")
        return body

    def get_version(self) -> str:
        body = self._get("version")
        version = body.get("version")
        if not isinstance(version, str):
            raise TimeTaggerError("TimeTagger version response is invalid")
        return version

    def get_all_records(self) -> list[TimeTaggerRecord]:
        body = self._get("updates", params={"since": 0})
        records = body.get("records")
        if not isinstance(records, list):
            raise TimeTaggerError("TimeTagger updates response is invalid")
        result = []
        for record in records:
            try:
                result.append(
                    TimeTaggerRecord(
                        key=str(record["key"]),
                        t1=int(record["t1"]),
                        t2=int(record["t2"]),
                        ds=str(record.get("ds", "")),
                        mt=int(record["mt"]),
                        st=float(record.get("st", 0)),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise TimeTaggerError("TimeTagger returned a malformed record") from exc
        return result

    def create_records(self, records: list[TimeTaggerRecord]) -> PutResult:
        if not records:
            return PutResult((), (), ())
        try:
            response = self.session.put(
                self.base_url + "records",
                json=[record.as_api_dict() for record in records],
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise UncertainWriteError(
                f"PUT result is uncertain ({type(exc).__name__}); not retrying. "
                "The next run will perform a fresh full inventory."
            ) from exc
        body = self._decode(response)
        accepted, failed, errors = body.get("accepted"), body.get("failed"), body.get("errors")
        if not all(isinstance(value, list) for value in (accepted, failed, errors)):
            raise UncertainWriteError("PUT returned an invalid response; write state is uncertain")
        return PutResult(
            tuple(map(str, accepted)), tuple(map(str, failed)), tuple(map(str, errors))
        )
