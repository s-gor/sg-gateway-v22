from types import SimpleNamespace

import pytest

from app.naiveproxy import integration


def test_naiveproxy_prefers_ready_tls_domain_over_connection_ip():
    settings = SimpleNamespace(
        host="74.248.185.146",
        config={"domain": ""},
    )
    credential = {"host": "74.248.185.146"}
    tls = {"https_ready": True, "domain": "itsec.opik.net"}

    assert integration._effective_naiveproxy_domain(settings, credential, tls) == "itsec.opik.net"


def test_naiveproxy_uses_valid_connection_domain_without_ready_tls():
    settings = SimpleNamespace(
        host="naive.example.com",
        config={"domain": "naive.example.com"},
    )
    credential = {"host": "naive.example.com"}
    tls = {"https_ready": False, "domain": ""}

    assert integration._effective_naiveproxy_domain(settings, credential, tls) == "naive.example.com"


def test_naiveproxy_rejects_ip_when_no_tls_domain_is_ready():
    settings = SimpleNamespace(
        host="74.248.185.146",
        config={"domain": ""},
    )
    credential = {"host": "74.248.185.146"}
    tls = {"https_ready": False, "domain": ""}

    with pytest.raises(Exception):
        integration._effective_naiveproxy_domain(settings, credential, tls)
