import os
import sys
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI

from app.memory.redis_store import RedisMemoryStore
from app.memory.chroma_store import ChromaMemoryStore
from app.agents.personas import (
    SUPERVISOR_PROMPT, WRITER_PROMPT, VISION_PROMPT,
    VIZ_PROMPT, CODE_PROMPT, IMAGE_GEN_PROMPT, DOC_AGENT_PROMPT
)
from app.agents.viz_agent import VizAgent
from app.agents.code_agent import CodeAgent
from app.agents.image_gen_agent import ImageGenAgent
from app.agents.doc_agent import FileExtractor

# Ensure UTF-8 output encoding for Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Load .env file from root directory
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

app = FastAPI(title="Multi-Agent Collaborative Sandbox API")

# Mount static files directory
static_dir = Path(__file__).resolve().parent.parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

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

PRIMARY_MODEL = "qwen/qwen3.6-27b"
FAST_MODEL = "openai/gpt-oss-20b"

# Initialize Memory Stores
redis_store = RedisMemoryStore()
chroma_store = ChromaMemoryStore()

@app.get("/")
async def serve_frontend():
    html_file = Path(__file__).resolve().parent.parent / "test.html"
    return FileResponse(html_file)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("[WS] Client connected to WebSocket")
    
    try:
        while True:
            raw_data = await websocket.receive_text()
            print(f"[WS] Received payload: {raw_data[:100]}...")
            
            prompt = ""
            image_data = None
            file_data = None
            file_name = None
            session_id = "default_session"
            
            try:
                parsed = json.loads(raw_data)
                if isinstance(parsed, dict):
                    prompt = parsed.get("prompt", parsed.get("message", ""))
                    image_data = parsed.get("image", None)
                    file_data = parsed.get("file_data", None)
                    file_name = parsed.get("file_name", None)
                    session_id = parsed.get("session_id", "default_session")
            except json.JSONDecodeError:
                prompt = raw_data

            if not prompt and not image_data and not file_data:
                continue

            prompt_lower = prompt.lower().strip()

            # 1. Document Extraction & Vector Indexing if a file was uploaded
            extracted_doc_text = ""
            file_metadata = {}
            if file_data and file_name:
                doc_event = {
                    "type": "agent_start",
                    "agent": "Document Analyst Agent",
                    "role": "Extractor",
                    "content": f"📄 Parsing and indexing `{file_name}`..."
                }
                await websocket.send_text(json.dumps(doc_event))
                await asyncio.sleep(0.2)

                doc_res = FileExtractor.extract_text(file_name, file_data)
                extracted_doc_text = doc_res.get("content", "")
                file_metadata = doc_res.get("metadata", {})

                if extracted_doc_text:
                    chroma_store.add_memory(
                        text=f"Document File: {file_name}\nContent:\n{extracted_doc_text[:2000]}",
                        metadata={"filename": file_name, "type": "uploaded_document"}
                    )
                    idx_event = {
                        "type": "memory_retrieved",
                        "agent": "ChromaDB Document Indexer",
                        "content": f"✅ Indexed `{file_name}` ({file_metadata.get('character_count', 0)} chars) into vector memory."
                    }
                    await websocket.send_text(json.dumps(idx_event))

            # 2. Check Redis Cache for short-term hit
            cache_key = f"{prompt}_{file_name}"
            cached_response = redis_store.get_cached_response(cache_key) if prompt and not image_data and not file_data else None
            if cached_response:
                print("[WS] Short-term Redis cache hit!")
                await websocket.send_text(json.dumps({
                    "type": "agent_start",
                    "agent": "Supervisor",
                    "role": "Cache Manager",
                    "content": "⚡ Retrieved response from short-term Redis cache."
                }))
                await asyncio.sleep(0.2)

                await websocket.send_text(json.dumps({
                    "type": "stream_chunk",
                    "agent": "Writer Agent",
                    "content": cached_response
                }))
                await websocket.send_text(json.dumps({
                    "type": "agent_complete",
                    "agent": "Writer Agent",
                    "status": "done"
                }))
                continue

            # 3. Retrieve Long-Term Memory Context from ChromaDB
            memory_context = ""
            if prompt:
                historic_docs = chroma_store.search_memory(prompt, limit=2)
                if historic_docs:
                    memory_context = "\n[Relevant Historic Context]:\n" + "\n".join(f"- {d}" for d in historic_docs) + "\n"
                    await websocket.send_text(json.dumps({
                        "type": "memory_retrieved",
                        "agent": "ChromaDB Memory",
                        "content": f"Retrieved {len(historic_docs)} relevant context snippet(s) from vector memory."
                    }))

            # 4. Intelligent Supervisor Routing
            target_agent = "writer"
            reasoning = "General text reasoning task."

            img_triggers = ["image", "picture", "photo", "draw", "render", "paint", "artwork", "illustration", "wallpaper", "cat", "dog", "piano", "scene"]
            img_actions = ["generate", "create", "make", "draw", "render", "paint", "show", "give", "produce", "an image", "a picture", "a photo"]
            
            is_image_request = any(act in prompt_lower for act in ["generate", "create", "draw", "make", "render", "paint"]) and any(tr in prompt_lower for tr in ["image", "picture", "photo", "art", "drawing", "illustration", "cat", "dog", "scene", "piano"])

            if file_data or (prompt and any(w in prompt_lower for w in ["document", "pdf", "docx", "file", "csv", "summary of file", "read file"])):
                target_agent = "doc_agent"
                reasoning = "Document analysis request detected."
            elif image_data:
                target_agent = "vision"
                reasoning = "Image uploaded; routing to Vision Analyst."
            elif is_image_request:
                target_agent = "image_generator"
                reasoning = "Image generation request detected."
            elif any(w in prompt_lower for w in ["chart", "graph", "plot", "bar chart", "pie chart", "line chart", "sales", "metrics", "visualize"]):
                target_agent = "visualization"
                reasoning = "Data visualization request detected."
            elif any(w in prompt_lower for w in ["code", "python", "script", "function", "run code", "calculate", "fibonacci", "algorithm"]):
                target_agent = "code_executor"
                reasoning = "Code execution request detected."
            else:
                # LLM Router fallback check
                try:
                    router_res = await client.chat.completions.create(
                        model=FAST_MODEL,
                        messages=[
                            {"role": "system", "content": SUPERVISOR_PROMPT},
                            {"role": "user", "content": prompt}
                        ],
                        response_format={"type": "json_object"}
                    )
                    route_json = json.loads(router_res.choices[0].message.content)
                    target_agent = route_json.get("target_agent", "writer")
                    reasoning = route_json.get("reasoning", reasoning)
                except Exception as e:
                    print(f"[Router Fallback Warning] {e}")

            agent_names = {
                "writer": "Writer Agent",
                "doc_agent": "Document Analyst Agent",
                "visualization": "Data Visualization Agent",
                "code_executor": "Code Execution Agent",
                "vision": "Vision Analyst Agent",
                "image_generator": "Image Generator Agent"
            }
            assigned_worker = agent_names.get(target_agent, "Writer Agent")

            # Supervisor Event
            await websocket.send_text(json.dumps({
                "type": "agent_start",
                "agent": "Supervisor",
                "role": "Orchestrator",
                "content": f"Task analyzed: {reasoning} Assigning to **{assigned_worker}**."
            }))
            await asyncio.sleep(0.3)

            # Worker Execution
            await websocket.send_text(json.dumps({
                "type": "agent_start",
                "agent": assigned_worker,
                "role": "Executor",
                "content": ""
            }))

            full_response_text = ""

            # EXECUTION BRANCHES
            if target_agent == "image_generator":
                sys_prompt = IMAGE_GEN_PROMPT
                clean_p = ImageGenAgent.clean_user_prompt(prompt)
                user_msg = f"Refine into an artistic detailed image prompt for FLUX: {clean_p}"
                
                try:
                    res = await client.chat.completions.create(
                        model=FAST_MODEL,
                        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}],
                        response_format={"type": "json_object"}
                    )
                    raw_out = res.choices[0].message.content
                    img_data = ImageGenAgent.parse_and_build(raw_out, clean_p)
                except Exception as e:
                    img_data = ImageGenAgent.parse_and_build(clean_p, clean_p)
                
                full_response_text = f"Generated image for: '{img_data['prompt']}'"
                
                await websocket.send_text(json.dumps({
                    "type": "stream_chunk",
                    "agent": assigned_worker,
                    "content": f"🎨 **Generating custom AI Image...**\n*{img_data['prompt']}*"
                }))
                
                await websocket.send_text(json.dumps({
                    "type": "image_render",
                    "agent": assigned_worker,
                    "image_url": img_data["image_url"],
                    "caption": img_data["caption"]
                }))

            elif target_agent == "doc_agent":
                user_msg = f"{memory_context}\nFile: `{file_name or 'Uploaded Document'}`\nDocument Content:\n{extracted_doc_text[:4000]}\n\nUser Question/Instruction: {prompt if prompt else 'Summarize key findings and outline takeaways from this document.'}"
                response = await client.chat.completions.create(
                    model=PRIMARY_MODEL,
                    messages=[{"role": "system", "content": DOC_AGENT_PROMPT}, {"role": "user", "content": user_msg}],
                    stream=True
                )
                async for chunk in response:
                    c = chunk.choices[0].delta.content
                    if c:
                        full_response_text += c
                        await websocket.send_text(json.dumps({
                            "type": "stream_chunk",
                            "agent": assigned_worker,
                            "content": c
                        }))

            elif target_agent == "visualization":
                sys_prompt = VIZ_PROMPT
                doc_ctx = f"\nData Source: {extracted_doc_text[:2000]}" if extracted_doc_text else ""
                user_msg = f"{memory_context}{doc_ctx}\nConstruct chart for prompt: {prompt}"
                res = await client.chat.completions.create(
                    model=PRIMARY_MODEL,
                    messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}]
                )
                raw_out = res.choices[0].message.content
                chart_config = VizAgent.parse_chart_json(raw_out)
                
                explanation = chart_config.get("explanation", "Data visualization generated.")
                full_response_text = explanation
                await websocket.send_text(json.dumps({
                    "type": "stream_chunk",
                    "agent": assigned_worker,
                    "content": explanation
                }))
                await websocket.send_text(json.dumps({
                    "type": "chart_render",
                    "agent": assigned_worker,
                    "chart": chart_config
                }))

            elif target_agent == "code_executor":
                sys_prompt = CODE_PROMPT
                user_msg = f"{memory_context}Write python code for: {prompt}"
                res = await client.chat.completions.create(
                    model=PRIMARY_MODEL,
                    messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}]
                )
                code_text = res.choices[0].message.content
                full_response_text = code_text
                
                await websocket.send_text(json.dumps({
                    "type": "stream_chunk",
                    "agent": assigned_worker,
                    "content": code_text
                }))
                
                exec_result = CodeAgent.execute_python(code_text)
                await websocket.send_text(json.dumps({
                    "type": "code_execution_result",
                    "agent": assigned_worker,
                    "result": exec_result
                }))

            elif target_agent == "vision":
                user_msg = f"{prompt if prompt else 'Describe the contents of this uploaded image.'}"
                response = await client.chat.completions.create(
                    model=PRIMARY_MODEL,
                    messages=[{"role": "system", "content": VISION_PROMPT}, {"role": "user", "content": user_msg}],
                    stream=True
                )
                async for chunk in response:
                    c = chunk.choices[0].delta.content
                    if c:
                        full_response_text += c
                        await websocket.send_text(json.dumps({
                            "type": "stream_chunk",
                            "agent": assigned_worker,
                            "content": c
                        }))

            else:  # Writer / General Agent
                user_msg = f"{memory_context}User Query: {prompt}"
                response = await client.chat.completions.create(
                    model=PRIMARY_MODEL,
                    messages=[{"role": "system", "content": WRITER_PROMPT}, {"role": "user", "content": user_msg}],
                    stream=True
                )
                async for chunk in response:
                    c = chunk.choices[0].delta.content
                    if c:
                        full_response_text += c
                        await websocket.send_text(json.dumps({
                            "type": "stream_chunk",
                            "agent": assigned_worker,
                            "content": c
                        }))

            # Complete Event
            await websocket.send_text(json.dumps({
                "type": "agent_complete",
                "agent": assigned_worker,
                "status": "done"
            }))

            # Save to Memory Stores
            if prompt and full_response_text:
                redis_store.cache_response(cache_key, full_response_text)
                chroma_store.add_memory(
                    text=f"User Query: {prompt}\nAgent ({assigned_worker}): {full_response_text[:300]}",
                    metadata={"agent": assigned_worker, "session_id": session_id}
                )

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        print(f"[WS Error] {e}")
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "content": f"Agent Execution Error: {str(e)}"
            }))
        except Exception:
            pass