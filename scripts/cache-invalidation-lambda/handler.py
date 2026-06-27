"""Cache invalidation Lambda.

Triggered by a WordPress `save_post` webhook (wired to this function's Lambda Function
URL) whenever a post is published or updated. Invalidates just the specific path(s) in
CloudFront rather than the whole distribution, since a full-distribution invalidation
on every edit would cause a cache-miss storm against the origin right after every
single publish, exactly the problem this architecture is built to avoid.

Expected request body (JSON):
    {
        "shared_secret": "...",
        "paths": ["/2026/06/some-post-slug/", "/"]
    }

The shared secret is a basic webhook authentication mechanism appropriate for this use
case (a WordPress plugin calling a public Function URL); it is not a substitute for
IAM auth in contexts where that's available, but WordPress webhooks calling a public
HTTPS endpoint can't easily do SigV4 signing, so a shared secret checked here is the
pragmatic real-world choice.

On failure capture: Lambda Function URLs invoke synchronously (RequestResponse), and
Lambda's automatic async failure handling (Destinations, the built-in DLQ config) only
fires for asynchronous invocations, never for synchronous ones. Wiring up an async DLQ
on this function the way you would for an EventBridge-triggered Lambda would be
configured but would simply never fire here. Instead, a CloudFront API failure is
caught explicitly and pushed to an SQS queue from inside the handler itself, before
returning the error response, so a failed invalidation has somewhere durable to land
instead of being lost to whatever the WordPress webhook plugin does (or doesn't do)
with a 500 response.
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3

MAX_PATHS_PER_REQUEST = 15  # keep invalidation requests small and frequent, not large and rare


class InvalidRequest(Exception):
    pass


def _validate_request(body: dict[str, Any]) -> list[str]:
    expected_secret = os.environ.get("WEBHOOK_SHARED_SECRET")
    if not expected_secret:
        raise InvalidRequest("WEBHOOK_SHARED_SECRET is not configured on the function.")

    if body.get("shared_secret") != expected_secret:
        raise InvalidRequest("Invalid shared secret.")

    paths = body.get("paths")
    if not paths or not isinstance(paths, list):
        raise InvalidRequest("'paths' must be a non-empty list of strings.")

    if len(paths) > MAX_PATHS_PER_REQUEST:
        raise InvalidRequest(
            f"Too many paths in one request ({len(paths)}); "
            f"max is {MAX_PATHS_PER_REQUEST}. Send multiple smaller requests instead."
        )

    for path in paths:
        if not isinstance(path, str) or not path.startswith("/"):
            raise InvalidRequest(f"Invalid path '{path}': paths must start with '/'.")

    return paths


def create_invalidation(cloudfront_client, distribution_id: str, paths: list[str]) -> str:
    response = cloudfront_client.create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={
            "Paths": {"Quantity": len(paths), "Items": paths},
            # CallerReference must be unique per request; using the sorted path list
            # keeps repeated identical requests idempotent-ish rather than always
            # generating a fresh, billable invalidation for the exact same paths.
            "CallerReference": "|".join(sorted(paths)),
        },
    )
    return response["Invalidation"]["Id"]


def record_failed_invalidation(
    sqs_client, queue_url: str, distribution_id: str, paths: list[str], error_message: str
) -> None:
    """Pushes a failed invalidation attempt to SQS for later inspection or manual
    replay. Called instead of relying on Lambda's async Destinations/DLQ, which don't
    apply to this function's synchronous Function URL invocation; see module docstring.
    """
    sqs_client.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(
            {
                "distribution_id": distribution_id,
                "paths": paths,
                "error": error_message,
            }
        ),
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        raw_body = event.get("body", "{}")
        body = json.loads(raw_body) if isinstance(raw_body, str) else raw_body
        paths = _validate_request(body)
    except (InvalidRequest, json.JSONDecodeError, TypeError) as exc:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": str(exc)}),
        }

    distribution_id = os.environ["CLOUDFRONT_DISTRIBUTION_ID"]
    cloudfront_client = boto3.client("cloudfront")

    try:
        invalidation_id = create_invalidation(cloudfront_client, distribution_id, paths)
    except Exception as exc:  # noqa: BLE001, intentional broad catch to guarantee SQS capture before returning
        queue_url = os.environ.get("FAILED_INVALIDATIONS_QUEUE_URL")
        if queue_url:
            sqs_client = boto3.client("sqs")
            record_failed_invalidation(sqs_client, queue_url, distribution_id, paths, str(exc))
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"CloudFront invalidation failed: {exc}"}),
        }

    return {
        "statusCode": 200,
        "body": json.dumps({"invalidation_id": invalidation_id, "paths": paths}),
    }
