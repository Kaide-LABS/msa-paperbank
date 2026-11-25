"""Cutover step 06 — side-by-side comparison of the old (GCP) and new (local) deploys.

Queries two running HTTP deployments over ``/tool/retrieve`` for the fixed query set
and reports per-query top-k agreement plus a summary. It compares two HTTP services
only: it imports NO ``app.providers.gcp.*`` and NO ``google.*`` symbol, so it keeps
working after the in-repo GCP code is deleted in Part B.

Credentials/endpoints come from env/flags; no secret literal is embedded. The core
``compare`` function is pure — it takes two fetch callables and never touches the
network itself, so it is unit-testable with injected fakes (AC 2: no network in
tests).

Operator usage (NOT run during the build)::

    OLD_BASE_URL=https://old-gcp-deploy.example \
    NEW_BASE_URL=https://new-local-deploy.example \
    TOOL_API_TOKEN=... \
    python cutover/06_side_by_side.py --k 5
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from collections.abc import Callable, Sequence

# Default fixed query set; overridable via --queries.
DEFAULT_QUERIES_FILE = "data/parity_queries.json"


def _result_key(response: dict) -> object:
    """Identity of a /tool/retrieve response for agreement purposes.

    Uses the matched paper id when a paper was found, else a ``(found, course)``
    marker so "both found nothing for X" still counts as agreement.
    """
    if response.get("found") and isinstance(response.get("paper"), dict):
        return ("paper", response["paper"].get("id"))
    return ("none", response.get("course_code") or response.get("intent"))


def compare(
    queries: Sequence[str],
    fetch_old: Callable[[str], dict],
    fetch_new: Callable[[str], dict],
) -> dict:
    """Pure comparison of two endpoints over a query set.

    ``fetch_old``/``fetch_new`` map a query string to a parsed ``/tool/retrieve``
    response dict. Returns per-query agreement rows and the overall agreement rate. No
    network, no GCP import — just the two injected callables.
    """
    rows = []
    agree = 0
    for query in queries:
        old = fetch_old(query)
        new = fetch_new(query)
        old_key = _result_key(old)
        new_key = _result_key(new)
        match = old_key == new_key
        if match:
            agree += 1
        rows.append({"query": query, "old": old_key, "new": new_key, "agree": match})
    rate = agree / len(queries) if queries else 1.0
    return {"total": len(queries), "agreed": agree, "agreement_rate": rate, "queries": rows}


def _http_fetcher(base_url: str, token: str | None, k: int) -> Callable[[str], dict]:
    """Build a fetcher that POSTs a query to ``{base_url}/tool/retrieve``."""
    endpoint = base_url.rstrip("/") + "/tool/retrieve"

    def fetch(query: str) -> dict:
        payload = json.dumps({"query": query}).encode("utf-8")
        req = urllib.request.Request(endpoint, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (operator tool)
            return json.loads(resp.read().decode("utf-8"))

    return fetch

    # (k is accepted for interface symmetry; /tool/retrieve returns a single match.)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Side-by-side old-vs-new /tool/retrieve comparison")
    parser.add_argument("--queries", default=DEFAULT_QUERIES_FILE)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--old-base-url", default=os.environ.get("OLD_BASE_URL"))
    parser.add_argument("--new-base-url", default=os.environ.get("NEW_BASE_URL"))
    args = parser.parse_args(argv)

    if not args.old_base_url or not args.new_base_url:
        parser.error("OLD_BASE_URL and NEW_BASE_URL must be set (env or flags)")

    token = os.environ.get("TOOL_API_TOKEN")
    with open(args.queries, encoding="utf-8") as fh:
        queries = json.load(fh)

    report = compare(
        queries,
        _http_fetcher(args.old_base_url, token, args.k),
        _http_fetcher(args.new_base_url, token, args.k),
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
