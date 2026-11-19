# iPhone Duo pickup monitor

This monitor checks all eight unlocked iPhone Duo storage and color combinations at Apple stores returned for ZIP codes **55113**, **55344**, and **77002**. It calls Apple's pickup API with `curl`; no browser session or cookies are needed.

## Cloud schedule and alerts

A Cloudflare Worker checks stock automatically every five minutes. For a separate manual check, use **Actions → Check iPhone Duo pickup → Run workflow** in this repository.

The workflow sends an ntfy alert only when a store and model combination becomes available after being unavailable. Its current availability state is stored in the repository issue named **iPhone Duo stock monitor state**. A failed Apple request leaves that state unchanged so a transient API error cannot cause a false alert.

The ntfy topic is set through the repository Actions secret `NTFY_TOPIC`. Subscribe to that topic on the `ntfy.sh` server in the ntfy app. The topic name is an address, not an authenticated inbox; anyone who knows it can read or publish messages there.

## Run from a terminal

```sh
python3 iphone_duo_check.py
```

To check a different ZIP code, use `--location 10001`; repeat `--location` to check several. The local script stores prior available combinations in `~/.local/state/iphone-duo-monitor/state.json` and sends a macOS notification only when a new one appears. Run it with cron or another scheduler if you want a separate local monitor.
