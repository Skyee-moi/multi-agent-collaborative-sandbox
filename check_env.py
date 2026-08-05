import os
from pathlib import Path
from dotenv import load_dotenv

# Force reload from .env ignoring cached session variables
env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

token = os.getenv("GITHUB_TOKEN", "")

has_single_quote = "'" in token
has_double_quote = '"' in token

print("\n--------------------------------------------------")
print("Token Length      :", len(token))
print("Starts With       :", repr(token[:7]))
print("Has Single Quotes :", has_single_quote)
print("Has Double Quotes :", has_double_quote)
print("--------------------------------------------------\n")