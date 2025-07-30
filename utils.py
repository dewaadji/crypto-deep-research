import os
from typing import List
from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
import traceback
from dotenv import load_dotenv

load_dotenv()

configurable_model = init_chat_model(
    model= "deepseek/deepseek-r1-distill-llama-70b",
    # model= "meta-llama/llama-3.3-70b-instruct",
    model_provider= "openai",
    api_key= os.getenv("HEURIST_API_KEY"),
    base_url= os.getenv("HEURIST_BASE_URL")
)
max_structured_output_retries = 3
allow_clarification = True

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
