#!/usr/bin/env python
"""Diagnostic script to test TinyFish API"""
import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('TINYFISH_API_KEY')

print("="*70)
print("TINYFISH API DIAGNOSTIC")
print("="*70)
print(f"\n✓ API Key loaded: {api_key[:15]}...{api_key[-8:]}\n")

# Test endpoints
endpoints = [
    "https://agent.tinyfish.ai/v1/automation/run-sse",
    "https://agent.tinyfish.ai/health",
    "https://agent.tinyfish.ai/",
]

for endpoint in endpoints:
    print(f"→ {endpoint}")
    try:
        start = time.time()
        resp = requests.get(endpoint, timeout=5, headers={'X-API-Key': api_key})
        elapsed = time.time() - start
        print(f"  ✓ Status {resp.status_code} | Response time: {elapsed:.2f}s")
    except requests.exceptions.Timeout:
        elapsed = time.time() - start
        print(f"  ✗ TIMEOUT after {elapsed:.1f}s")
        print(f"    → Connection works BUT server never sends response")
    except requests.exceptions.ConnectionError as e:
        print(f"  ✗ CONNECTION ERROR")
        print(f"    → {str(e)[:100]}")
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {str(e)[:100]}")

print("\n" + "="*70)
print("EXACT PROBLEM DIAGNOSIS:")
print("="*70)
