#!/usr/bin/env python3
"""Check Apple pickup stock with curl; intended for cron every five minutes."""
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

PARTS = {
    "MK1F4LL/A": "256GB Night Sky", "MK1E4LL/A": "256GB Star White",
    "MK1H4LL/A": "512GB Night Sky", "MK1G4LL/A": "512GB Star White",
    "MK1L4LL/A": "1TB Night Sky", "MK1J4LL/A": "1TB Star White",
    "MK1R4LL/A": "2TB Night Sky", "MK1Q4LL/A": "2TB Star White",
}
DEFAULT_LOCATIONS = ("55113", "55344", "77002")


def request_stock(location):
    params = [("pl", "true"), ("mts.0", "regular"), ("location", location)]
    params += [(f"parts.{i}", part) for i, part in enumerate(PARTS)]
    url = "https://www.apple.com/shop/retail/pickup-message?" + urlencode(params)
    command = ["/usr/bin/curl", "--silent", "--show-error", "--compressed", "--max-time", "30",
               "--write-out", "\n%{http_code}", "-H", "accept: application/json", "--url", url]
    result = subprocess.run(command, capture_output=True, text=True, timeout=35)
    if result.returncode:
        raise RuntimeError(f"curl failed: {result.stderr.strip()}")
    body, sep, status = result.stdout.rpartition("\n")
    if not sep or status != "200":
        raise RuntimeError(f"Apple returned HTTP {status or 'unknown'}; stock is unknown")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Apple returned non-JSON content; stock is unknown") from exc


def pickup_available(stock):
    if stock.get("storePickEligible") is False:
        return False
    display = str(stock.get("pickupDisplay", "")).lower()
    quote = str(stock.get("pickupSearchQuote", "")).lower()
    return display == "available" or ("available" in quote and "unavailable" not in quote)


def available_options(data):
    if str(data.get("head", {}).get("status")) != "200":
        raise ValueError("Apple API did not report success")
    stores = data.get("body", {}).get("stores")
    if not stores or not isinstance(stores, list):
        raise ValueError("Apple returned no store availability data")
    found = []
    for store in stores:
        stock = store.get("partsAvailability", {})
        missing = PARTS.keys() - stock.keys()
        if missing:
            raise ValueError(f"Incomplete stock data for {store.get('storeName', 'a store')}")
        for part, model in PARTS.items():
            if pickup_available(stock[part]):
                found.append({"key": f"{store['storeNumber']}:{part}",
                              "store": store["storeName"], "model": model,
                              "quote": stock[part].get("pickupSearchQuote", "Available")})
    return stores, found


def alert(item):
    title = f"iPhone Duo available: {item['model']}"
    message = f"Pickup at Apple {item['store']}. Open Apple Store to order."
    print(f"ALERT: {title} — {message}")
    if sys.platform == "darwin":
        script = "on run argv\n display notification (item 2 of argv) with title (item 1 of argv)\nend run"
        result = subprocess.run(["osascript", "-e", script, title, message],
                                capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"macOS notification failed: {result.stderr.strip()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--location", action="append", help="ZIP code to check; repeat for multiple ZIPs")
    parser.add_argument("--state-file", type=Path,
                        default=Path.home() / ".local/state/iphone-duo-monitor/state.json")
    args = parser.parse_args()
    locations = tuple(dict.fromkeys(args.location or DEFAULT_LOCATIONS))
    stores_by_number = {}
    found_by_key = {}
    for location in locations:
        stores, found = available_options(request_stock(location))
        for store in stores:
            number = store["storeNumber"]
            if number not in stores_by_number:
                stores_by_number[number] = {**store, "searchedLocations": [location]}
            else:
                stores_by_number[number]["searchedLocations"].append(location)
        for item in found:
            found_by_key[item["key"]] = item
    stores = list(stores_by_number.values())
    found = list(found_by_key.values())
    state = args.state_file.expanduser()
    prior = set(json.loads(state.read_text())) if state.exists() else set()
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"{now}: checked {len(PARTS)} variants at {len(stores)} unique stores near {', '.join(locations)}; {len(found)} pickup options available")
    for store in stores:
        store_options = [item for item in found if item["store"] == store["storeName"]]
        searched = ", ".join(store["searchedLocations"])
        print(f"  {store['storeName']} ({store['storeNumber']}; returned for {searched}): {len(store_options)} available")
    for item in found:
        print(f"  {item['model']} — {item['store']} ({item['quote']})")
        if item["key"] not in prior:
            alert(item)
    state.parent.mkdir(parents=True, exist_ok=True)
    temp = state.with_suffix(".tmp")
    temp.write_text(json.dumps(sorted(item["key"] for item in found)))
    temp.replace(state)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"Stock check failed: {exc}", file=sys.stderr)
        sys.exit(1)
