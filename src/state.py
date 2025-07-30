from typing import Annotated, Optional
from langgraph.graph import MessagesState
from langchain_core.messages import MessageLikeRepresentation
from pydantic import BaseModel, Field
from typing import List
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict
import operator

#state
class DelegateAgent(BaseModel):
    # queries: Optional[WorkerQueries] = None
    heurist_queries: str = Field(
        description="The input for MCP call, must be described in high detail."
    )
    flipside_queries: str = Field(
        description="The input for db call, must be described in high detail following SQL rule query."
    )

class ClarifyWithUser(BaseModel):
    need_clarification: bool = Field(
        description="Whether the user needs to be asked a clarifying question.",
    )
    question: str = Field(
        description="A question to ask the user to clarify the report scope",
    )
    verification: str = Field(
        description="Verify message that we will start research after the user has provided the necessary information.",
    )

#agent state
def override_reducer(current_value, new_value):
    if isinstance(new_value, dict) and new_value.get("type") == "override":
        return new_value.get("value", new_value)
    else:
        return operator.add(current_value, new_value)

class InputState(MessagesState):
    """InputState is only 'messages'"""

class SupervisorState(MessagesState):
    # supervisor_messages: Annotated[list[MessageLikeRepresentation], operator.add]
    supervisor_messages: Annotated[list[MessageLikeRepresentation], override_reducer]
    heurist_queries: Optional[str]       
    heurist_results: Optional[str]
    flipside_queries: Optional[str]       
    flipside_results: Optional[str]
    # Meta
    final_answer: Annotated[Optional[str], override_reducer]

class HeuristAgentState(TypedDict):
    heurist_queries: Optional[str]
    heurist_results: Optional[str]

class FlipsideAgentState(TypedDict):
    flipside_queries: Optional[str]
    flipside_results: Optional[str]