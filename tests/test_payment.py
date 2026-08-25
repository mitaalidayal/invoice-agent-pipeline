from agents.payment import mock_payment


def test_mock_payment_returns_success():
    assert mock_payment("Widgets Inc.", 5000.0) == {"status": "success"}
