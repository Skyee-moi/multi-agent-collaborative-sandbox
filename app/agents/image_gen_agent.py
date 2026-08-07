import urllib.parse
import json
import re
import random
from typing import Dict, Any

class ImageGenAgent:
    """Helper for generating image URLs using FLUX / Pollinations engine."""

    @staticmethod
    def clean_user_prompt(prompt: str) -> str:
        """Strip conversational filler words from prompt."""
        text = prompt.strip()
        fillers = [
            r"^can you (?:please )?(?:generate|create|draw|make|render|show me|paint)\s+(?:an?|the)?\s*",
            r"^(?:please )?(?:generate|create|draw|make|render|show me|paint)\s+(?:an?|the)?\s*",
            r"^image of\s*",
            r"^picture of\s*",
            r"^photo of\s*"
        ]
        for f in fillers:
            text = re.sub(f, "", text, flags=re.IGNORECASE)
        return text.strip() if text.strip() else prompt.strip()

    @classmethod
    def generate_image_url(cls, prompt: str, width: int = 1024, height: int = 768, seed: int = None) -> str:
        """Encode prompt into Pollinations FLUX image generator URL with dynamic seed."""
        if seed is None:
            seed = random.randint(100, 999999)
        clean_p = cls.clean_user_prompt(prompt)
        encoded_prompt = urllib.parse.quote(clean_p)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&seed={seed}&nologo=true&model=flux"
        return url

    @classmethod
    def parse_and_build(cls, raw_text: str, user_prompt: str) -> Dict[str, Any]:
        """Extract refined prompt JSON or construct image generator parameters."""
        clean_prompt = cls.clean_user_prompt(user_prompt)
        final_prompt = clean_prompt
        caption = f"AI generated image: '{clean_prompt}'"

        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict):
                final_prompt = parsed.get("prompt", clean_prompt)
                caption = parsed.get("caption", caption)
        except Exception:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(1))
                    final_prompt = parsed.get("prompt", clean_prompt)
                    caption = parsed.get("caption", caption)
                except Exception:
                    pass

        # If model returned non-JSON text explanation, use cleaned text
        if final_prompt == clean_prompt and len(raw_text.strip()) > 5 and not raw_text.strip().startswith("{"):
            # Clean markdown formatting from raw text
            cleaned_raw = re.sub(r"`|\*|#", "", raw_text).strip()
            if len(cleaned_raw) < 200:
                final_prompt = cleaned_raw

        seed = random.randint(100, 999999)
        image_url = cls.generate_image_url(final_prompt, seed=seed)
        
        return {
            "prompt": final_prompt,
            "caption": caption,
            "image_url": image_url,
            "seed": seed
        }
