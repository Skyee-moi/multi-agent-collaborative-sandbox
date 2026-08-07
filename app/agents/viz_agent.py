import json
import re
from typing import Dict, Any

class VizAgent:
    """Helper for generating structured Chart.js options from text or model responses."""

    @staticmethod
    def parse_chart_json(raw_text: str) -> Dict[str, Any]:
        """Extract and clean JSON payload from model response."""
        try:
            # Try direct JSON parsing
            return json.loads(raw_text)
        except Exception:
            pass

        # Try regex extract within ```json ... ```
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        # Fallback JSON structure if extraction failed
        return {
            "type": "bar",
            "title": "Data Overview",
            "labels": ["Item A", "Item B", "Item C"],
            "datasets": [
                {
                    "label": "Values",
                    "data": [15, 30, 45]
                }
            ],
            "explanation": raw_text
        }
