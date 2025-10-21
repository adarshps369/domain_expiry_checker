#!/usr/bin/env python3
import argparse
import requests
import sys
import os
import time
from datetime import datetime

CACHE_DIR = "/tmp/check_domain_cache"
CACHE_AGE = 8 * 3600  # 8 hours in seconds

STATE_OK = 0
STATE_WARNING = 1
STATE_CRITICAL = 2
STATE_UNKNOWN = 3


def die(state, message):
    print(message)
    sys.exit(state)


def get_cache_file(domain):
    return os.path.join(CACHE_DIR, f"{domain}.cache")


def load_cached_data(domain):
    cache_file = get_cache_file(domain)
    if os.path.exists(cache_file):
        if time.time() - os.path.getmtime(cache_file) < CACHE_AGE:
            with open(cache_file, "r") as f:
                return f.read().strip()
    return None


def save_to_cache(domain, data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(get_cache_file(domain), "w") as f:
        f.write(data)


def parse_rdap_date(date_str):
    """Parse RDAP date string into a timestamp, handling milliseconds if present."""
    try:
        return int(datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp())
    except ValueError:
        try:
            return int(datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").timestamp())
        except ValueError:
            die(STATE_UNKNOWN, f"UNKNOWN - Invalid expiration date format: {date_str}")


def get_domain_expiration(domain):
    cached = load_cached_data(domain)
    if cached:
        return cached

    rdap_url = f"https://rdap.org/domain/{domain}"
    try:
        response = requests.get(rdap_url, timeout=10)
        data = response.json()
        events = data.get("events", [])
        for event in events:
            if event.get("eventAction") == "expiration":
                expiration = event.get("eventDate")
                if expiration:
                    save_to_cache(domain, expiration)
                    return expiration
        die(STATE_UNKNOWN, f"UNKNOWN - Expiry date not found for {domain}")
    except Exception as e:
        die(STATE_UNKNOWN, f"UNKNOWN - Error fetching RDAP data: {e}")


def main():
    parser = argparse.ArgumentParser(description="Check domain expiration via RDAP")
    parser.add_argument("-d", "--domain", required=True, help="Domain name to check")
    parser.add_argument("-w", "--warning", type=int, default=30, help="Warning threshold (days)")
    parser.add_argument("-c", "--critical", type=int, default=10, help="Critical threshold (days)")
    args = parser.parse_args()

    expiration_date = get_domain_expiration(args.domain)

    exp_seconds = parse_rdap_date(expiration_date)
    now_seconds = int(time.time())
    days_left = (exp_seconds - now_seconds) // 86400

    if days_left < 0:
        die(STATE_CRITICAL, f"CRITICAL - Domain {args.domain} expired {-days_left} days ago ({expiration_date}).")
    elif days_left < args.critical:
        die(STATE_CRITICAL, f"CRITICAL - Domain {args.domain} will expire in {days_left} days ({expiration_date}).")
    elif days_left < args.warning:
        die(STATE_WARNING, f"WARNING - Domain {args.domain} will expire in {days_left} days ({expiration_date}).")
    else:
        die(STATE_OK, f"OK - Domain {args.domain} will expire in {days_left} days ({expiration_date}).")


if __name__ == "__main__":
    main()
