#!/usr/bin/env python
"""Test TinyFish API with POST request"""
import requests
import time
import os
import json
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('TINYFISH_API_KEY')

print("="*70)
print("TINYFISH POST REQUEST TEST")
print("="*70)
print(f"\nAPI Key: {api_key[:15]}...{api_key[-8:]}\n")

endpoint = "https://agent.tinyfish.ai/v1/automation/run-sse"
headers = {
    'X-API-Key': api_key,
    'Content-Type': 'application/json'
}
payload = {
    'url': 'https://www.google.com',
    'goal': 'Quick test',
    'screenshot': False
}

print(f"Endpoint: {endpoint}")
print(f"Headers: {headers}")
print(f"Payload: {json.dumps(payload, indent=2)}")
print(f"\nSending POST request with 10 second timeout...\n")

try:
    start = time.time()
    resp = requests.post(endpoint, headers=headers, json=payload, timeout=10)
    elapsed = time.time() - start
    
    print(f"✓ RESPONSE RECEIVED IN {elapsed:.2f}s")
    print(f"Status Code: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('content-type', 'N/A')}")
    print(f"Body (first 300 chars):")
    print(resp.text[:300])
    print(f"\n{'='*70}")
    if resp.status_code == 200:
        print("✓ TINYFISH IS WORKING!")
    elif resp.status_code == 401:
        print("✗ 401 Unauthorized - API Key invalid or expired")
    elif resp.status_code == 403:
        print("✗ 403 Forbidden - API Key not allowed/account issue")
    elif resp.status_code == 429:
        print("✗ 429 Too Many Requests - Rate limited")
    else:
        print(f"? Status {resp.status_code} - Check response body above")
        
except requests.exceptions.Timeout:
    elapsed = time.time() - start
    print(f"✗ TIMEOUT after {elapsed:.1f}s")
    print("Server accepted connection but never sent response")
    print("→ Server is hung or completely overloaded")
    
except requests.exceptions.ConnectionError as e:
    print(f"✗ CONNECTION ERROR")
    print(f"{type(e).__name__}: {str(e)[:200]}")
    
except Exception as e:
    print(f"✗ ERROR: {type(e).__name__}")
    print(str(e)[:200])
