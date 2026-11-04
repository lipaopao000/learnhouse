"""Validate the actual SMTP wire format, including headers relays cannot guess."""
import time
from email import message_from_string, policy
from email.utils import parsedate_to_datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.services.email.utils import _send_email_smtp


def _mailing(port):
    return SimpleNamespace(system_email_address="noreply@example.com", smtp_host="smtp.example.com", smtp_port=port, smtp_use_tls=True, smtp_username=None, smtp_password=None)


@pytest.mark.parametrize("port", [465, 587])
def test_smtp_has_valid_date_and_domain_message_id(port):
    client = Mock()
    with patch("src.services.email.utils.smtplib.SMTP_SSL", return_value=client), patch("src.services.email.utils.smtplib.SMTP", return_value=client):
        _send_email_smtp("教学平台 <noreply@example.com>", "student@example.net", "邮箱验证", "<p>验证邮件</p>", _mailing(port))
    envelope_from, recipient, raw = client.sendmail.call_args.args
    message = message_from_string(raw, policy=policy.default)
    assert envelope_from == "noreply@example.com" and recipient == "student@example.net"
    assert message["Message-ID"] is not None, "Missing Message-ID makes relays invent or repair the identifier"
    assert len(message.get_all("Message-ID")) == 1
    assert not message["Message-ID"].defects
    assert str(message["Message-ID"]).startswith("<")
    assert str(message["Message-ID"]).endswith("@example.com>")
    assert message["Date"] is not None
    assert len(message.get_all("Date")) == 1
    date = parsedate_to_datetime(str(message["Date"]))
    assert date.tzinfo is not None and abs(date.timestamp() - time.time()) < 10
    assert message.get_body(preferencelist=("html",)).get_content().strip() == "<p>验证邮件</p>"


def test_each_smtp_message_has_a_distinct_id():
    client = Mock()
    with patch("src.services.email.utils.smtplib.SMTP_SSL", return_value=client):
        for _ in range(2):
            _send_email_smtp("noreply@example.com", "student@example.net", "Verification", "<p>Hi</p>", _mailing(465))
    ids = [message_from_string(call.args[2], policy=policy.default)["Message-ID"] for call in client.sendmail.call_args_list]
    assert all(ids) and ids[0] != ids[1]


def test_explicit_headers_are_preserved_without_duplicate_date_or_message_id():
    client = Mock()
    headers = {"Message-ID": "<caller-created@example.com>", "Date": "Thu, 05 Nov 2026 02:00:00 +0800", "List-Unsubscribe": "<https://example.com/unsubscribe>"}
    with patch("src.services.email.utils.smtplib.SMTP_SSL", return_value=client):
        _send_email_smtp("noreply@example.com", "student@example.net", "Verification", "<p>Hi</p>", _mailing(465), headers)
    message = message_from_string(client.sendmail.call_args.args[2], policy=policy.default)
    for name, value in headers.items():
        assert message.get_all(name) == [value]
