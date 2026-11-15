from scripts.sync_nbu import parse_currency_item

def test_parse_currency_valid_item():
    item = {"cc": "USD", "txt": "Долар США", "rate": 41.2}
    result = parse_currency_item(item)

    assert result is not None
    assert result["code"] == "USD"
    assert result["rate"] == 41.2
    assert result["symbol"] == "$"

def test_parse_currency_blocked_and_invalid():
    blocked_item = {"cc": "RUB", "txt": "Рубль", "rate": 0.4}
    assert parse_currency_item(blocked_item) is None

    invalid_item = {"cc": "US", "txt": "Невідомо", "rate": 10.0}
    assert parse_currency_item(invalid_item) is None