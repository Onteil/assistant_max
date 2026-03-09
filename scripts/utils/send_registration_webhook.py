"""
Test script to send registration approval webhook
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import aiohttp
import json


async def send_webhook():
    url = "https://3f3a-77-238-231-29.ngrok-free.app/bot/api/webhooks/registration_status"
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": "test-key-123"
    }
    
    payload = {
        "user_id": 23,
        "phone": "+79956877974",
        "status": "approved"
    }
    
    print(f"Sending webhook to: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                print(f"\nResponse Status: {response.status}")
                print(f"Response Headers: {dict(response.headers)}")
                
                try:
                    response_data = await response.json()
                    print(f"Response Body: {json.dumps(response_data, indent=2)}")
                except:
                    response_text = await response.text()
                    print(f"Response Text: {response_text}")
                    
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(send_webhook())
