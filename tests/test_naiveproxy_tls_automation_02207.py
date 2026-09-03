from app.naiveproxy.runtime import NaiveProxySettings, render_caddyfile


def test_naiveproxy_uses_explicit_sg_gateway_certificate_without_caddy_automation():
    rendered = render_caddyfile(
        NaiveProxySettings(
            domain="itsec.opik.net",
            port=8447,
            certificate_path="/etc/letsencrypt/live/itsec.opik.net/fullchain.pem",
            private_key_path="/etc/letsencrypt/live/itsec.opik.net/privkey.pem",
        ),
        [],
    )

    assert "auto_https off" in rendered
    assert "auto_https disable_redirects" not in rendered
    assert (
        "tls /etc/letsencrypt/live/itsec.opik.net/fullchain.pem "
        "/etc/letsencrypt/live/itsec.opik.net/privkey.pem"
    ) in rendered
