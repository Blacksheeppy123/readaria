#!/usr/bin/env python3
"""
Quick smoke test for saved articles and read/unread endpoints.
Requires backend running at http://localhost:8000 and a logged-in user token.

Usage:
  source venv/bin/activate
  export BASE_URL=http://localhost:8000
  export TOKEN="<your JWT token>"
  python scripts/test_saved_and_read.py "https://example.com/article-url"
"""
import os
import sys
import json
import time
import requests

BASE = os.getenv('BASE_URL', 'http://localhost:8000')
TOKEN = os.getenv('TOKEN')

def auth_headers():
    if not TOKEN:
        print('Missing TOKEN env var. Please set a valid JWT token in TOKEN.')
        sys.exit(1)
    return {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}

def main():
    if len(sys.argv) < 2:
        print('Usage: python scripts/test_saved_and_read.py <article_url>')
        sys.exit(1)

    url = sys.argv[1]

    # Check saved status
    r = requests.get(f"{BASE}/api/saved/status", params={"url": url}, headers=auth_headers())
    print('saved/status:', r.status_code, r.text)

    # Mark read
    r = requests.post(f"{BASE}/api/articles/read", headers=auth_headers(), data=json.dumps({"url": url}))
    print('articles/read (POST):', r.status_code, r.text)

    # Save
    r = requests.post(f"{BASE}/api/saved", headers=auth_headers(), data=json.dumps({"url": url}))
    print('saved (POST):', r.status_code, r.text)

    # List saved
    r = requests.get(f"{BASE}/api/saved", headers=auth_headers())
    print('saved (GET):', r.status_code, len(r.text))

    # Unsave
    r = requests.delete(f"{BASE}/api/saved", params={"url": url}, headers=auth_headers())
    print('saved (DELETE):', r.status_code, r.text)

    # Mark unread
    r = requests.delete(f"{BASE}/api/articles/read", params={"url": url}, headers=auth_headers())
    print('articles/read (DELETE):', r.status_code, r.text)

    print('Done ✅')

if __name__ == '__main__':
    main()

