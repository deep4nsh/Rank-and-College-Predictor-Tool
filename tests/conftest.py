import pytest
from starlette.testclient import TestClient

# Ensure existing end-to-end integration test suites pass with default counsellor passcode
_orig_init = TestClient.__init__


def _patched_init(self, *args, **kwargs):
    headers = kwargs.get("headers")
    if headers is None:
        headers = {}
    else:
        headers = dict(headers)
    headers.setdefault("X-Counsellor-Passcode", "Councellor@123")
    kwargs["headers"] = headers
    _orig_init(self, *args, **kwargs)


TestClient.__init__ = _patched_init
