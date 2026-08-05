from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class AgentState(BaseModel):
    """
    The shared memory container for our multi-agent collaboration loop.
    Tracks user input, historical messages, intermediate agent thoughts, 
    and any uploaded image data.
    """
    # The original text prompt sent by the user
    user_input: str
    
    # Stores the conversational history (role: user/assistant, content)
    messages: List[Dict[str, str]] = Field(default_factory=list)
    
    # Holds optional Base64 image data strings if the user uploads a picture
    image_data: Optional[str] = None
    
    # A scratchpad dictionary where specialized agents can dump their analysis
    agent_outputs: Dict[str, Any] = Field(default_factory=dict)
    
    # Tracks which agent should speak next ('supervisor', 'writer', 'vision', or 'end')
    next_step: str = "supervisor"
    
    # The final consolidated text response that will be streamed back to the user
    final_response: str = ""