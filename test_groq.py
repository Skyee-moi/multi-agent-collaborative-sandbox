import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI

env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

async def test():
    key = os.getenv("GROQ_API_KEY")
    print(f"🔑 Key Loaded: {key[:8]}..." if key else "❌ KEY MISSING!")
    
    client = AsyncOpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=key
    )
    
    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "hi"}],
            stream=True
        )
        print("🤖 Response: ", end="", flush=True)
        async for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                print(content, end="", flush=True)
        print("\n✅ STREAM SUCCESSFUL!")
    except Exception as e:
        print(f"\n❌ API ERROR: {e}")

asyncio.run(test())