from app.security.auth import PUBLIC_ENDPOINTS, should_skip_auth


def test_only_public_subscription_feed_skips_panel_auth() -> None:
    assert "sg_subscription_v1" in PUBLIC_ENDPOINTS
    assert should_skip_auth("sg_subscription_v1") is True
    assert should_skip_auth("sg_subscription_v1_info") is False
    assert should_skip_auth("sg_subscription_v1_qr") is False
    assert "sg_subscription_v1_info" not in PUBLIC_ENDPOINTS
    assert "sg_subscription_v1_qr" not in PUBLIC_ENDPOINTS
