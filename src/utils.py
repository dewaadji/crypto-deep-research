import os
import asyncio
from typing import List, Literal, Annotated
from datetime import datetime
from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool, InjectedToolArg
from langchain_mcp_adapters.client import MultiServerMCPClient
from tavily import AsyncTavilyClient
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

# Summary agent model with higher temperature for more creative output
summary_model = init_chat_model(
    model= "deepseek/deepseek-r1-distill-llama-70b",
    model_provider= "openai",
    api_key= os.getenv("HEURIST_API_KEY"),
    base_url= os.getenv("HEURIST_BASE_URL"),
    temperature=0.5
)

max_structured_output_retries = 3
allow_clarification = True

##########################
# Tavily Search Tool Utils
##########################
TAVILY_SEARCH_DESCRIPTION = (
    "A search engine optimized for comprehensive, accurate, and trusted results. "
    "Useful for when you need to answer questions about current events."
)

@tool(description=TAVILY_SEARCH_DESCRIPTION)
async def tavily_search(
    queries: List[str],
    max_results: Annotated[int, InjectedToolArg] = 5,
    topic: Annotated[Literal["general", "news", "finance"], InjectedToolArg] = "general",
    config: RunnableConfig = None
) -> str:
    """
    Fetches results from Tavily search API.

    Args:
        queries (List[str]): List of search queries, you can pass in as many queries as you need.
        max_results (int): Maximum number of results to return
        topic (Literal['general', 'news', 'finance']): Topic to filter results by

    Returns:
        str: A formatted string of search results
    """
    search_results = await tavily_search_async(
        queries,
        max_results=max_results,
        topic=topic,
        include_raw_content=True,
        config=config
    )
    
    # Format the search results and deduplicate results by URL
    formatted_output = f"Search results: \n\n"
    unique_results = {}
    for response in search_results:
        for result in response['results']:
            url = result['url']
            if url not in unique_results:
                unique_results[url] = {**result, "query": response['query']}
    
    for i, (url, result) in enumerate(unique_results.items()):
        formatted_output += f"\n\n--- SOURCE {i+1}: {result['title']} ---\n"
        formatted_output += f"URL: {url}\n\n"
        formatted_output += f"CONTENT:\n{result['content']}\n\n"
        if result.get('raw_content'):
            formatted_output += f"RAW CONTENT:\n{result['raw_content'][:1000]}...\n\n"
        formatted_output += "\n\n" + "-" * 80 + "\n"
    
    if unique_results:
        return formatted_output
    else:
        return "No valid search results found. Please try different search queries or use a different search API."

async def tavily_search_async(search_queries, max_results: int = 5, topic: Literal["general", "news", "finance"] = "general", include_raw_content: bool = True, config: RunnableConfig = None):
    """
    Performs concurrent web searches with the Tavily API
    
    Args:
        search_queries: List of search queries to execute
        max_results: Maximum number of results per query
        topic: Topic filter for search results
        include_raw_content: Whether to include raw content in results
        config: RunnableConfig for API key access
    
    Returns:
        List[dict]: List of search responses from Tavily API
    """
    tavily_async_client = AsyncTavilyClient(api_key=get_tavily_api_key(config))
    search_tasks = []
    for query in search_queries:
        search_tasks.append(
            tavily_async_client.search(
                query,
                max_results=max_results,
                include_raw_content=include_raw_content,
                topic=topic
            )
        )
    search_docs = await asyncio.gather(*search_tasks)
    return search_docs

def get_tavily_api_key(config: RunnableConfig):
    """
    Get Tavily API key from config or environment variables
    
    Args:
        config: RunnableConfig containing API keys
    
    Returns:
        str: Tavily API key
    """
    should_get_from_config = os.getenv("GET_API_KEYS_FROM_CONFIG", "false")
    if should_get_from_config.lower() == "true":
        api_keys = config.get("configurable", {}).get("apiKeys", {})
        if not api_keys:
            return None
        return api_keys.get("TAVILY_API_KEY")
    else:
        return os.getenv("TAVILY_API_KEY")

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
    mcp_sse_url = os.getenv("FLIPSIDE_MCP_URLV2")
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

# Tavily search tool
async def load_tavily_search(config: RunnableConfig) -> List[BaseTool]:
    """
    Load Tavily search tool
    
    Args:
        config: RunnableConfig for API key access
    
    Returns:
        List[BaseTool]: List containing the Tavily search tool
    """
    try:
        # Check if Tavily API key is available
        api_key = get_tavily_api_key(config)
        if not api_key:
            print("Warning: TAVILY_API_KEY not found in environment variables or config")
            return []
        
        # Return the tavily_search tool
        return [tavily_search]
    except Exception as e:
        print(f"Error loading Tavily search tool: {e}")
        traceback.print_exception(type(e), e, e.__traceback__)
        return []
