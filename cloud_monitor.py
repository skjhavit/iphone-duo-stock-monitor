#!/usr/bin/env python3
"""Run iPhone Duo stock checks on GitHub Actions and notify on new pickup stock."""

import json
import os
import urllib.error
import urllib.request

from iphone_duo_check import DEFAULT_LOCATIONS, available_options, request_stock

ISSUE_TITLE = "iPhone Duo stock monitor state"
SHOP_URL = "https://www.apple.com/shop/buy-iphone/iphone-duo"


def github(method, path, payload=None):
    url = "https://api.github.com/repos/" + os.environ["GITHUB_REPOSITORY"] + path
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=body, method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "iphone-duo-stock-monitor",
        **({"Content-Type": "application/json"} if body is not None else {}),
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"GitHub API {method} {path} returned HTTP {error.code}") from error


def state_issue():
    issues = github("GET", "/issues?state=all&per_page=100")
    for issue in issues:
        if issue.get("title") == ISSUE_TITLE and "pull_request" not in issue:
            return issue
    return github("POST", "/issues", {
        "title": ISSUE_TITLE,
        "body": json.dumps({"available": []}, indent=2),
    })


def current_stock():
    stores_by_number = {}
    found_by_key = {}
    for location in DEFAULT_LOCATIONS:
        stores, found = available_options(request_stock(location))
        stores_by_number.update({store["storeNumber"]: store for store in stores})
        found_by_key.update({item["key"]: item for item in found})
    print(f"Checked {len(stores_by_number)} unique stores; {len(found_by_key)} pickup options available")
    return found_by_key


def send_ntfy(items):
    topic = os.environ["NTFY_TOPIC"]
    if not topic or not all(char.isalnum() or char in "-_" for char in topic):
        raise RuntimeError("NTFY_TOPIC is missing or invalid")
    lines = [f"{item['model']} at Apple {item['store']} ({item['quote']})" for item in items]
    message = "iPhone Duo pickup available:\n" + "\n".join(lines) + f"\n{SHOP_URL}"
    request = urllib.request.Request(
        "https://ntfy.sh/" + topic,
        data=message.encode(),
        method="POST",
        headers={
            "Title": "iPhone Duo pickup available",
            "Priority": "high",
            "Click": SHOP_URL,
            "Content-Type": "text/plain; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise RuntimeError(f"ntfy returned HTTP {response.status}")
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"ntfy returned HTTP {error.code}") from error


def main():
    found = current_stock()  # On any failed Apple request, leave saved state untouched.
    issue = state_issue()
    try:
        previous = set(json.loads(issue.get("body") or "{}").get("available", []))
    except (ValueError, TypeError) as error:
        raise RuntimeError("State issue has invalid JSON") from error
    fresh = [item for key, item in found.items() if key not in previous]

    if fresh:
        send_ntfy(fresh)
        print("Sent ntfy stock alert for", ", ".join(item["key"] for item in fresh))

    keys = sorted(found)
    if keys != sorted(previous):
        github("PATCH", f"/issues/{issue['number']}", {
            "body": json.dumps({"available": keys}, indent=2),
        })
        print("Updated saved stock state")


if __name__ == "__main__":
    main()
