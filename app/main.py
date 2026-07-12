import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Load environmental configurations from our root .env file
load_dotenv()

app = FastAPI(title="Multi-Agent AI Collaborative Sandbox - Phase 2")

# Allow local frontend testing scripts to securely connect to our server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize client using GitHub's free endpoint matrix
ai_client = AsyncOpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=os.environ.get("GITHUB_TOKEN")
)

async def stream_gpt_response(prompt: str, websocket: WebSocket):
    """
    Calls the free model marketplace asynchronously and streams
    the raw text data over the persistent open connection.
    """
    try:
        response_stream = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are the Supervisor Agent of a multi-agent sandbox. Keep answers structured."},
                {"role": "user", "content": prompt}
            ],
            stream=True
        )

        # Iterate through response frames as they drop in real time
        async for chunk in response_stream:
            # Safety Check: Verify the chunk lists choice arrays before indexing
            if chunk.choices and len(chunk.choices) > 0:
                token = chunk.choices[0].delta.content
                if token:
                    # Instantly dispatch text token down the WebSocket pipe
                    await websocket.send_text(token)
                    
    except Exception as e:
        await websocket.send_text(f"\n[Backend Error]: {str(e)}")

@app.websocket("/ws/sandbox")
async def websocket_endpoint(websocket: WebSocket):
    """
    Monitors incoming real-time socket handshakes from user dashboards.
    """
    await websocket.accept()
    print("🚀 Connected: Client channel opened securely.")
    
    try:
        while True:
            # Await incoming string prompts from the interface canvas
            user_prompt = await websocket.receive_text()
            print(f"📥 Prompt Received: '{user_prompt}'")
            
            # Fire up our safe streaming transmission loop
            await stream_gpt_response(user_prompt, websocket)
            
            # Send End of File confirmation flag to let client close stream graphics
            await websocket.send_text(" [EOF]")
            
    except WebSocketDisconnect:
        print("❌ Disconnected: Client channel terminated safely.")