"""Utah snowboard-weekend flight watcher.
LAX/BUR -> SLC, nonstop, Thursday evening out, Sunday night or early Monday back.
Sends ONE phone notification (ntfy) listing any weekends under your price limit.
"""
import os
import sys
import datetime as dt
import requests

# ---- EDIT THESE ----
ORIGINS = "LAX,BUR"
DESTINATION = "SLC"
MAX_PRICE = 300            # round-trip total, USD
MONTHS = (1, 2, 3)         # Jan, Feb, Mar
OUT_AFTER_HOUR = 16        # Thursday departure at/after 4 pm
SUN_AFTER_HOUR = 19        # Sunday return departing at/after 7 pm
MON_BEFORE_HOUR = 7        # Monday return departing before 8 am (hours 0-7)
# --------------------

SERPAPI_KEY = os.environ["SERPAPI_KEY"]
NTFY_TOPIC = os.environ["NTFY_TOPIC"]


def thursdays():
    today = dt.date.today()
    year = today.year if today.month <= 3 else today.year + 1
    d = dt.date(year, MONTHS[0], 1)
    end = dt.date(year, MONTHS[-1] + 1, 1) if MONTHS[-1] < 12 else dt.date(year + 1, 1, 1)
    while d < end:
        if d.weekday() == 3 and d > today:
            yield d
        d += dt.timedelta(days=1)


def search(thu, ret_day, ret_times):
    params = {
        "engine": "google_flights",
        "departure_id": ORIGINS,
        "arrival_id": DESTINATION,
        "outbound_date": thu.isoformat(),
        "return_date": ret_day.isoformat(),
        "type": "1",
        "stops": "1",  # nonstop only
        "outbound_times": f"{OUT_AFTER_HOUR},23",
        "return_times": ret_times,
        "currency": "USD",
        "hl": "en",
        "api_key": SERPAPI_KEY,
    }
    r = requests.get("https://serpapi.com/search", params=params, timeout=90)
    r.raise_for_status()
    data = r.json()
    options = data.get("best_flights", []) + data.get("other_flights", [])
    options = [o for o in options if "price" in o and len(o.get("flights", [])) == 1]
    if not options:
        return None
    best = min(options, key=lambda o: o["price"])
    seg = best["flights"][0]
    return {
        "price": best["price"],
        "out": thu,
        "back": ret_day,
        "airport": seg["departure_airport"]["id"],
        "airline": seg.get("airline", "?"),
        "dep_time": seg["departure_airport"].get("time", "")[-5:],
        "link": data.get("search_metadata", {}).get("google_flights_url"),
    }


def notify(deals):
    deals.sort(key=lambda d: d["price"])
    lines = []
    for d in deals[:10]:
        back = "Sun night" if d["back"].weekday() == 6 else "Mon early"
        lines.append(
            f"${d['price']}  {d['out']:%a %b %d} -> {back} "
            f"({d['airport']}, {d['airline']} {d['dep_time']})"
        )
    headers = {  # headers must be plain ASCII
        "Title": f"Utah ski weekend from ${deals[0]['price']}",
        "Priority": "high",
        "Tags": "snowboarder,airplane",
    }
    if deals[0]["link"]:
        headers["Click"] = deals[0]["link"]
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data="\n".join(lines).encode("utf-8"),
        headers=headers,
        timeout=30,
    )


def main():
    deals, checked = [], 0
    for thu in thursdays():
        for ret_day, ret_times in (
            (thu + dt.timedelta(days=3), f"{SUN_AFTER_HOUR},23"),
            (thu + dt.timedelta(days=4), f"0,{MON_BEFORE_HOUR}"),
        ):
            try:
                result = search(thu, ret_day, ret_times)
            except Exception as e:
                print(f"{thu} -> {ret_day}: error {e}", file=sys.stderr)
                continue
            checked += 1
            if result:
                print(f"{thu} -> {ret_day}: ${result['price']} ({result['airport']})")
                if result["price"] < MAX_PRICE:
                    deals.append(result)
            else:
                print(f"{thu} -> {ret_day}: no matching nonstop")
    print(f"Checked {checked} date combos, {len(deals)} under ${MAX_PRICE}")
    if deals:
        notify(deals)


if __name__ == "__main__":
    main()
