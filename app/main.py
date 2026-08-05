import os
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from openai import AsyncOpenAI

# Load .env file from root directory
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

app = FastAPI(title="Multi-Agent Collaborative Sandbox API")

# Allow CORS so WebSockets connect cleanly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

groq_key = os.getenv("GROQ_API_KEY")
if not groq_key:
    raise ValueError("GROQ_API_KEY is missing from your .env file!")

client = AsyncOpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=groq_key
)

TEXT_MODEL = "llama-3.3-70b-versatile"
VISION_MODEL = "llama-3.3-70b-versatile"

@app.get("/")
async def serve_frontend():
    html_file = Path(__file__).resolve().parent.parent / "test.html"
    return FileResponse(html_file)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🔌 Client connected to WebSocket")
    
    try:
        while True:
            raw_data = await websocket.receive_text()
            print(f"📩 Received from browser: {raw_data[:100]}...")
            
            prompt = raw_data
            image_data = None
            
            try:
                parsed = json.loads(raw_data)
                if isinstance(parsed, dict):
                    prompt = parsed.get("prompt", parsed.get("message", ""))
                    image_data = parsed.get("image", None)
            except json.JSONDecodeError:
                pass

            active_model = VISION_MODEL if image_data else TEXT_MODEL
            worker_name = "Vision Agent" if image_data else "Primary Agent"

            # Calculate approximate image size from base64 string so text models can process it
            image_context = ""
            if image_data:
                try:
                    base64_str = image_data.split(",")[1] if "," in image_data else image_data
                    approx_bytes = len(base64_str) * 3 / 4
                    approx_kb = round(approx_bytes / 1024, 2)
                    image_context = f"[Attached Image Metadata: Approximate File Size ~{approx_kb} KB]. "
                except Exception:
                    image_context = "[Attached Image Received]. "

            try:
                # 1. Supervisor Orchestration Event
                supervisor_event = {
                    "type": "agent_start",
                    "agent": "Supervisor",
                    "role": "Orchestrator",
                    "content": f"Analyzing task... Assigning {worker_name} ({active_model})."
                }
                await websocket.send_text(json.dumps(supervisor_event))
                await asyncio.sleep(0.3)

                # 2. Worker Agent Execution
                agent_start = {
                    "type": "agent_start",
                    "agent": worker_name,
                    "role": "Executor",
                    "content": ""
                }
                await websocket.send_text(json.dumps(agent_start))

                user_content = f"{image_context}User prompt: {prompt if prompt else 'Describe the uploaded image details.'}"
                messages = [{"role": "user", "content": user_content}]

                response = await client.chat.completions.create(
                    model=active_model,
                    messages=messages,
                    stream=True
                )
                
                async for chunk in response:
                    content = chunk.choices[0].delta.content
                    if content:
                        chunk_event = {
                            "type": "stream_chunk",
                            "agent": worker_name,
                            "content": content
                        }
                        await websocket.send_text(json.dumps(chunk_event))
                
                complete_event = {
                    "type": "agent_complete",
                    "agent": worker_name,
                    "status": "done"
                }
                await websocket.send_text(json.dumps(complete_event))

            except Exception as api_err:
                print(f"❌ API Error: {api_err}")
                error_event = {
                    "type": "error",
                    "agent": "System",
                    "content": f"Error: {str(api_err)}"
                }
                await websocket.send_text(json.dumps(error_event))

    except WebSocketDisconnect:
        print("🔌 Client disconnected")
    except Exception as e:
        print(f"❌ WebSocket error: {e}")