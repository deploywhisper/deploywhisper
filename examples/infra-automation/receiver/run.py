"""HTTPS reference client. Run from a provisioned, protected local receiver host."""

from __future__ import annotations

import argparse
import json
import os
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, HTTPSHandler
import ssl

from infra_automation.receiver_custody import canonical
from infra_automation.receiver_runtime import ReferenceReceiver


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Receiver redirects are forbidden")


class HTTPSReceiverServer:
    def __init__(self, origin, receiver_id, secret):
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("An HTTPS origin without credentials or path is required")
        if (
            not receiver_id
            or not secret
            or any(char in receiver_id + secret for char in "\r\n")
        ):
            raise ValueError("Receiver credentials required")
        self.origin = origin.rstrip("/")
        self._headers = {
            "Authorization": "Bearer " + secret,
            "X-Receiver-Id": receiver_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._http = build_opener(
            NoRedirect(), HTTPSHandler(context=ssl.create_default_context())
        )

    def _request(self, operation_id, action, body=None):
        if type(operation_id) is not str or not operation_id or len(operation_id) > 128:
            raise ValueError("Bounded operation identity required")
        url = (
            self.origin
            + "/api/v1/infra-automation/handoffs/"
            + quote(operation_id, safe="")
            + "/"
            + action
        )
        request = Request(
            url,
            data=canonical(body) if body is not None else None,
            headers=self._headers,
            method="POST" if body is not None else "GET",
        )
        with self._http.open(request, timeout=30) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("Receiver response exceeds bound")
        envelope = json.loads(raw)
        if type(envelope) is not dict or type(envelope.get("data")) is not dict:
            raise ValueError("Invalid authenticated receiver response")
        return envelope["data"]

    def bootstrap(self, operation_id, binding_digest):
        return self._request(
            operation_id, "receipt", {"version": 1, "binding_digest": binding_digest}
        )

    def consume(self, message, grant_token):
        return self._request(
            message.operation_id,
            "consume",
            {
                "version": 1,
                "message": message.model_dump(mode="json"),
                "grant_token": grant_token,
            },
        )

    def status(self, operation_id):
        return self._request(operation_id, "status")

    def authorize_action(self, operation_id):
        return self._request(operation_id, "authorize-action", {"version": 1})

    def callback(self, envelope):
        return self._request(envelope["operation_id"], "outcome", envelope)


def main():
    parser = argparse.ArgumentParser(
        description="Run one protected synthetic receiver operation"
    )
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--binding-digest", required=True)
    args = parser.parse_args()
    # Provision these locally. Never put secrets, payloads, plans, or grants in
    # GitHub dispatch inputs or command-line arguments.
    secret = os.environ["DEPLOYWHISPER_RECEIVER_SECRET"]
    server = HTTPSReceiverServer(
        os.environ["DEPLOYWHISPER_SERVER_ORIGIN"],
        os.environ["DEPLOYWHISPER_RECEIVER_ID"],
        secret,
    )
    receiver = ReferenceReceiver(
        os.environ["DEPLOYWHISPER_RECEIVER_ROOT"], server, secret.encode()
    )
    result = receiver.run(args.operation_id, args.binding_digest)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "operation_id",
                    "phase",
                    "counted_actions",
                    "callback_delivered",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
