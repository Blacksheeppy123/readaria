#!/usr/bin/env python3
"""
Auth flow smoke test for Jasmine (Week 3 JWT)

Pre-reqs:
  - Backend server running on http://localhost:8000
  - Postgres/Elasticsearch configured and reachable

What it tests:
  1) Register -> Login -> Me
  2) Add a feed -> List feeds
  3) Get paginated articles for the current user

Usage:
  python scripts/test_auth_flow.py --base http://localhost:8000 --user alice
"""
import argparse
import time
import sys
import requests


def json_or_text(resp):
    try:
        return resp.json()
    except Exception:
        return resp.text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://localhost:8000', help='Backend base URL')
    parser.add_argument('--user', default='alice', help='Username prefix')
    args = parser.parse_args()

    base = args.base.rstrip('/')
    username = f"{args.user}-{int(time.time())}"
    email = f"{username}@example.com"
    password = 'Passw0rd!'

    print(f"[1/6] Register {username} ...")
    r = requests.post(f"{base}/api/auth/register", json={
        'username': username,
        'email': email,
        'password': password,
        'full_name': 'Test User'
    }, timeout=15)

    if r.status_code == 200:
        data = r.json()
        token = data['access_token']
        print("  ✔ Registered")
    elif r.status_code in (400, 409):
        print("  ℹ️  User exists, trying login ...")
        r = requests.post(f"{base}/api/auth/login", json={
            'username': username,
            'password': password
        }, timeout=15)
        if r.status_code != 200:
            print("  ✖ Login failed: ", r.status_code, json_or_text(r))
            sys.exit(1)
        token = r.json()['access_token']
    else:
        print("  ✖ Register failed:", r.status_code, json_or_text(r))
        sys.exit(1)

    headers = {'Authorization': f'Bearer {token}'}

    print("[2/6] Get current user /api/auth/me ...")
    r = requests.get(f"{base}/api/auth/me", headers=headers, timeout=10)
    if r.status_code != 200:
        print("  ✖ /me failed:", r.status_code, json_or_text(r))
        sys.exit(1)
    me = r.json()
    user_id = me['id']
    print(f"  ✔ Hello, {me['username']} ({user_id})")

    print("[3/6] Add a feed ...")
    feed_url = "https://rsshub.app/v2ex/topics/hot"
    r = requests.post(f"{base}/user/{user_id}/feeds", json={
        'feed_name': 'V2EX热门',
        'feed_url': feed_url
    }, headers=headers, timeout=15)
    if r.status_code != 200:
        print("  ✖ Add feed failed:", r.status_code, json_or_text(r))
        # continue but mark warning
    else:
        print("  ✔ Feed added")

    print("[4/6] List feeds ...")
    r = requests.get(f"{base}/user/{user_id}/feeds", headers=headers, timeout=15)
    if r.status_code != 200:
        print("  ✖ List feeds failed:", r.status_code, json_or_text(r))
        sys.exit(1)
    feeds_data = r.json()
    # unwrap if wrapped
    if isinstance(feeds_data, dict) and 'feeds' in feeds_data:
        feeds = feeds_data['feeds']
    else:
        feeds = feeds_data
    print(f"  ✔ Feeds count: {len(feeds)}")

    print("[5/6] Get paged articles (user isolated) ...")
    r = requests.get(f"{base}/api/user/{user_id}/feeds/articles", params={'page': 1, 'size': 10}, headers=headers, timeout=20)
    if r.status_code != 200:
        print("  ✖ Get articles failed:", r.status_code, json_or_text(r))
        sys.exit(1)
    articles_payload = r.json()
    if isinstance(articles_payload, dict) and 'articles' in articles_payload:
        articles = articles_payload['articles']
    else:
        articles = articles_payload
    print(f"  ✔ Articles: {len(articles)}")

    print("[6/6] Logout ...")
    r = requests.post(f"{base}/api/auth/logout", headers=headers, timeout=10)
    if r.status_code == 200:
        print("  ✔ Logged out")
    else:
        print("  ℹ️  Logout non-200:", r.status_code, json_or_text(r))

    print("\nAll done. ✅")


if __name__ == '__main__':
    main()

