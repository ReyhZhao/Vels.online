"""SSRF-guarded report fetcher (module 3, issue #479).

Pure-module unit tests: the host-block logic, scheme allowlist, size cap, and redirect
handling. A fake resolver maps hostnames to IPs so nothing hits DNS or the network.
"""
import pytest

from hunts.report_fetch import (
    MAX_BYTES,
    ReportFetchError,
    assert_host_allowed,
    assert_url_allowed,
    fetch_report,
)

# hostname -> resolved IP set
_DNS = {
    "intel.example.com": {"93.184.216.34"},
    "internal.example.com": {"10.0.0.5"},
    "metadata.example.com": {"169.254.169.254"},
    "loopback.example.com": {"127.0.0.1"},
    "lan.example.com": {"192.168.1.10"},
}


def _resolver(host):
    return _DNS[host]


@pytest.mark.parametrize("host", [
    "internal.example.com", "metadata.example.com", "loopback.example.com", "lan.example.com",
])
def test_blocks_private_link_local_loopback_hosts(host):
    with pytest.raises(ReportFetchError):
        assert_host_allowed(host, resolver=_resolver)


def test_allows_public_host():
    assert_host_allowed("intel.example.com", resolver=_resolver)  # no raise


def test_rejects_non_http_scheme():
    with pytest.raises(ReportFetchError):
        assert_url_allowed("ftp://intel.example.com/x", resolver=_resolver)
    with pytest.raises(ReportFetchError):
        assert_url_allowed("file:///etc/passwd", resolver=_resolver)


def test_rejects_url_whose_host_is_internal():
    with pytest.raises(ReportFetchError):
        assert_url_allowed("https://internal.example.com/report", resolver=_resolver)


class FakeResp:
    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requested = []

    def get(self, url, **kwargs):
        self.requested.append(url)
        assert kwargs.get("allow_redirects") is False  # guard never auto-follows
        return self._responses.pop(0)


def test_fetches_public_report_text():
    sess = FakeSession([FakeResp(200, b"IOC: deadbeef")])
    text = fetch_report("https://intel.example.com/r", resolver=_resolver, session=sess)
    assert "deadbeef" in text


def test_caps_response_size():
    big = b"x" * (MAX_BYTES + 100)
    sess = FakeSession([FakeResp(200, big)])
    text = fetch_report("https://intel.example.com/r", resolver=_resolver, session=sess)
    assert len(text) <= MAX_BYTES


def test_blocks_redirect_into_internal_space():
    sess = FakeSession([
        FakeResp(302, headers={"Location": "https://internal.example.com/secret"}),
        FakeResp(200, b"should-never-reach"),
    ])
    with pytest.raises(ReportFetchError):
        fetch_report("https://intel.example.com/r", resolver=_resolver, session=sess)


def test_follows_one_safe_redirect():
    sess = FakeSession([
        FakeResp(302, headers={"Location": "https://intel.example.com/final"}),
        FakeResp(200, b"final body"),
    ])
    text = fetch_report("https://intel.example.com/r", resolver=_resolver, session=sess)
    assert "final body" in text


def test_rejects_too_many_redirects():
    sess = FakeSession([
        FakeResp(302, headers={"Location": "https://intel.example.com/a"}),
        FakeResp(302, headers={"Location": "https://intel.example.com/b"}),
    ])
    with pytest.raises(ReportFetchError):
        fetch_report("https://intel.example.com/r", resolver=_resolver, session=sess)
