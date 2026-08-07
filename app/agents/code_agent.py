import sys
import io
import re
import traceback
from typing import Dict, Any

class CodeAgent:
    """Helper for extracting and safely executing Python code snippets."""

    @staticmethod
    def extract_code(text: str) -> str:
        """Extract Python code inside markdown blocks."""
        pattern = r"```python\s*(.*?)\s*```"
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            return "\n\n".join(matches)
        
        generic_pattern = r"```\s*(.*?)\s*```"
        matches = re.findall(generic_pattern, text, re.DOTALL)
        if matches:
            return "\n\n".join(matches)
            
        return text

    @classmethod
    def execute_python(cls, code: str, timeout_seconds: int = 5) -> Dict[str, Any]:
        """Execute python code in isolated environment and capture stdout/stderr."""
        clean_code = cls.extract_code(code)
        
        buffer = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        
        executed_successfully = False
        output = ""
        error = ""
        
        try:
            sys.stdout = buffer
            sys.stderr = buffer
            
            # Isolated namespace
            local_scope: Dict[str, Any] = {}
            global_scope = {"__builtins__": __builtins__}
            
            exec(clean_code, global_scope, local_scope)
            output = buffer.getvalue()
            executed_successfully = True
        except Exception as e:
            output = buffer.getvalue()
            error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        return {
            "success": executed_successfully,
            "code": clean_code,
            "output": output.strip(),
            "error": error.strip()
        }
