import os
import asyncio
from typing import List
from datetime import datetime
from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
import traceback
from dotenv import load_dotenv

load_dotenv()

configurable_model = init_chat_model(
    model= "deepseek/deepseek-r1-distill-llama-70b",
    model_provider= "openai",
    api_key= os.getenv("HEURIST_API_KEY"),
    base_url= os.getenv("HEURIST_BASE_URL"),
    temperature=0
)
max_structured_output_retries = 3
allow_clarification = True

def get_current_date_time():
    """
    Get the current date and time in a formatted string.
    
    Returns:
        str: Current date and time in format "YYYY-MM-DD HH:MM:SS"
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_current_date():
    """
    Get the current date in a formatted string.
    
    Returns:
        str: Current date in format "YYYY-MM-DD"
    """
    return datetime.now().strftime("%Y-%m-%d")

def get_current_time():
    """
    Get the current time in a formatted string.
    
    Returns:
        str: Current time in format "HH:MM:SS"
    """
    return datetime.now().strftime("%H:%M:%S")

async def retry_mcp_tool_call(tool, args, max_retries=1, delay=3):
    """
    Retry MCP tool calls with delay on 400 errors.
    
    Args:
        tool: The MCP tool to invoke
        args: Arguments for the tool call
        max_retries: Maximum number of retries (default: 1)
        delay: Delay in seconds between retries (default: 3)
    
    Returns:
        The tool result or raises the last exception
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await tool.ainvoke(args)
        except Exception as e:
            last_exception = e
            error_str = str(e).lower()
            
            # Check if it's a 400 error or bad request
            if ("400" in error_str or "bad request" in error_str or 
                "client error" in error_str or "invalid request" in error_str):
                
                if attempt < max_retries:
                    print(f"MCP tool call failed with 400 error (attempt {attempt + 1}/{max_retries + 1}). Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    print(f"MCP tool call failed after {max_retries + 1} attempts. Returning error.")
                    raise last_exception
            else:
                # For non-400 errors, don't retry
                print(f"MCP tool call failed with non-400 error: {e}")
                raise e
    
    # This should never be reached, but just in case
    raise last_exception

#tools heurist
async def load_heurist_mcp(config: RunnableConfig) -> List[BaseTool]:
    mcp_sse_url = os.getenv("HEURIST_MCP_URL")
    mcp_server_config = {
        "heurist_mcp": {
            "transport": "sse",
            "url": mcp_sse_url
        }
    }

    try:
        client = MultiServerMCPClient(mcp_server_config)
        mcp_tools = await client.get_tools()
    except Exception as e:
        print(f"Error loading MCP tools: {e}")
        traceback.print_exception(type(e), e, e.__traceback__)
        return []
    return mcp_tools
#tools flipside
async def load_flipside_mcp(config: RunnableConfig) -> List[BaseTool]:
    mcp_sse_url = os.getenv("FLIPSIDE_MCP_URL")
    mcp_server_config = {
        "flipside_mcp": {
            "transport": "sse",
            "url": mcp_sse_url
        }
    }

    try:
        client = MultiServerMCPClient(mcp_server_config)
        mcp_tools = await client.get_tools()
    except Exception as e:
        print(f"Error loading MCP tools: {e}")
        traceback.print_exception(type(e), e, e.__traceback__)
        return []
    return mcp_tools
