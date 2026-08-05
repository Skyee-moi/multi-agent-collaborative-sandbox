import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY")
)

try:
    models = client.models.list()
    print("\n--------------------------------------------------")
    print("✅ Active Groq Model IDs on your account:")
    for m in models.data:
        print(f"  • {m.id}")
    print("--------------------------------------------------\n")
except Exception as e:
    print("❌ Error fetching models:", e)