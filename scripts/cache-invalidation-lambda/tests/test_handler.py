import json
import os
from unittest.mock import MagicMock

import pytest

os.environ["WEBHOOK_SHARED_SECRET"] = "test-secret"
os.environ["CLOUDFRONT_DISTRIBUTION_ID"] = "EDFDVBD6EXAMPLE"

from handler import (  # noqa: E402
    InvalidRequest,
    _validate_request,
    create_invalidation,
    handler,
    record_failed_invalidation,
)


def test_validate_request_accepts_valid_body():
    body = {"shared_secret": "test-secret", "paths": ["/", "/2026/06/some-post/"]}
    paths = _validate_request(body)
    assert paths == ["/", "/2026/06/some-post/"]


def test_validate_request_rejects_wrong_secret():
    body = {"shared_secret": "wrong", "paths": ["/"]}
    with pytest.raises(InvalidRequest, match="Invalid shared secret"):
        _validate_request(body)


def test_validate_request_rejects_missing_paths():
    body = {"shared_secret": "test-secret", "paths": []}
    with pytest.raises(InvalidRequest, match="non-empty list"):
        _validate_request(body)


def test_validate_request_rejects_path_without_leading_slash():
    body = {"shared_secret": "test-secret", "paths": ["no-leading-slash"]}
    with pytest.raises(InvalidRequest, match="must start with"):
        _validate_request(body)


def test_validate_request_rejects_too_many_paths():
    body = {"shared_secret": "test-secret", "paths": [f"/post-{i}/" for i in range(20)]}
    with pytest.raises(InvalidRequest, match="Too many paths"):
        _validate_request(body)


def test_create_invalidation_calls_cloudfront_with_expected_args():
    mock_client = MagicMock()
    mock_client.create_invalidation.return_value = {
        "Invalidation": {"Id": "I2EXAMPLE"}
    }

    invalidation_id = create_invalidation(mock_client, "EDFDVBD6EXAMPLE", ["/", "/about/"])

    assert invalidation_id == "I2EXAMPLE"
    mock_client.create_invalidation.assert_called_once()
    call_kwargs = mock_client.create_invalidation.call_args.kwargs
    assert call_kwargs["DistributionId"] == "EDFDVBD6EXAMPLE"
    assert call_kwargs["InvalidationBatch"]["Paths"]["Items"] == ["/", "/about/"]


def test_handler_returns_400_on_bad_secret(monkeypatch):
    event = {
        "body": json.dumps({"shared_secret": "wrong", "paths": ["/"]})
    }
    result = handler(event, None)
    assert result["statusCode"] == 400


def test_handler_returns_200_on_success(monkeypatch):
    mock_client = MagicMock()
    mock_client.create_invalidation.return_value = {
        "Invalidation": {"Id": "I3EXAMPLE"}
    }
    monkeypatch.setattr("handler.boto3.client", lambda service: mock_client)

    event = {
        "body": json.dumps({"shared_secret": "test-secret", "paths": ["/", "/blog/"]})
    }
    result = handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["invalidation_id"] == "I3EXAMPLE"
    assert body["paths"] == ["/", "/blog/"]


def test_record_failed_invalidation_sends_to_sqs():
    mock_sqs = MagicMock()
    record_failed_invalidation(mock_sqs, "https://sqs.example/queue", "DISTRIBUTION123", ["/"], "boom")

    mock_sqs.send_message.assert_called_once()
    call_kwargs = mock_sqs.send_message.call_args.kwargs
    assert call_kwargs["QueueUrl"] == "https://sqs.example/queue"
    body = json.loads(call_kwargs["MessageBody"])
    assert body["distribution_id"] == "DISTRIBUTION123"
    assert body["paths"] == ["/"]
    assert body["error"] == "boom"


def test_handler_returns_500_and_captures_to_sqs_on_cloudfront_failure(monkeypatch):
    mock_cloudfront = MagicMock()
    mock_cloudfront.create_invalidation.side_effect = Exception("Throttling: Rate exceeded")
    mock_sqs = MagicMock()

    def fake_client(service):
        return {"cloudfront": mock_cloudfront, "sqs": mock_sqs}[service]

    monkeypatch.setattr("handler.boto3.client", fake_client)
    monkeypatch.setenv("FAILED_INVALIDATIONS_QUEUE_URL", "https://sqs.example/failed-queue")

    event = {
        "body": json.dumps({"shared_secret": "test-secret", "paths": ["/", "/blog/"]})
    }
    result = handler(event, None)

    assert result["statusCode"] == 500
    assert "Throttling" in result["body"]
    mock_sqs.send_message.assert_called_once()
    sent_body = json.loads(mock_sqs.send_message.call_args.kwargs["MessageBody"])
    assert sent_body["paths"] == ["/", "/blog/"]
    assert "Throttling" in sent_body["error"]


def test_handler_returns_500_without_crashing_when_queue_url_not_configured(monkeypatch):
    # If FAILED_INVALIDATIONS_QUEUE_URL isn't set (e.g. an older deployment that
    # hasn't picked up this Terraform change yet), the handler must still degrade
    # gracefully, returning the error response instead of raising a KeyError trying
    # to look up a queue that was never configured.
    mock_cloudfront = MagicMock()
    mock_cloudfront.create_invalidation.side_effect = Exception("boom")
    monkeypatch.setattr("handler.boto3.client", lambda service: mock_cloudfront)
    monkeypatch.delenv("FAILED_INVALIDATIONS_QUEUE_URL", raising=False)

    event = {
        "body": json.dumps({"shared_secret": "test-secret", "paths": ["/"]})
    }
    result = handler(event, None)

    assert result["statusCode"] == 500
