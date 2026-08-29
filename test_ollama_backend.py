#!/usr/bin/env python3
"""Test the backend with free Ollama model"""
import json
import urllib.request

url = "http://127.0.0.1:8001/api/chat"
req_data = {
    "message": "how to reset pin",
    "request_human": False
}

print("Testing backend with Ollama gemma4:31b...")
print(f"Request: {req_data['message']}\n")

try:
    req = urllib.request.Request(
        url,
        data=json.dumps(req_data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        
        print(f"Status: HTTP {resp.status}")
        print(f"Decision: {data.get('decision')}")
        print(f"Reply: {data.get('reply', '')[:200]}...")
        print(f"Steps: {len(data.get('steps', []))}")
        print(f"Error: {data.get('error')}")
        print("\n--- Success! ---")
        
except Exception as e:
    print(f"Failed: {e}")
