from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage, get_buffer_string, filter_messages
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph
from langgraph.types import Command
import asyncio
from typing import Literal

from src.state import (
    ClarifyWithUser,
    InputState,
    DelegateAgent,
    SupervisorState,
    HeuristAgentState,
    FlipsideAgentState,
    TavilyAgentState,
)
from src.utils import (
    configurable_model,
    summary_model,
    max_structured_output_retries,
    allow_clarification,
    load_heurist_mcp,
    load_flipside_mcp,
    retry_mcp_tool_call,
    get_current_date_time,
    load_tavily_search,
)
from src.prompt import (
    clarify_with_user_instructions,
    supervisor_system_prompt,
    heurist_mcp_system_prompt,
    flipside_mcp_system_prompt,
    tavily_mcp_system_prompt,
    summary_system_prompt
)

current_datetime = get_current_date_time()

async def clarify_with_user(state: SupervisorState, config: RunnableConfig) -> Command[Literal["supervisor", "__end__"]]:
    if not allow_clarification:
        return Command(
            goto="supervisor", 
            update={"supervisor_messages": {"type": "override",
                    "value": [
                        SystemMessage(content=supervisor_system_prompt.format(current_datetime=current_datetime)),
                        HumanMessage(content=response.verification)
                    ]
                }})
    
    messages = state["messages"]
    
    clarify_model = configurable_model.with_structured_output(ClarifyWithUser).with_retry(stop_after_attempt=max_structured_output_retries)
    response = await clarify_model.ainvoke([HumanMessage(content=clarify_with_user_instructions.format(messages=get_buffer_string(messages), current_datetime=current_datetime))])
    
    print(f"\nresponse clarify_user: \n{response}")
    if response.need_clarification:
        return Command(
            goto=END, 
            update={"messages": [AIMessage(content=response.question)]})
    else:
        return Command(
            goto="supervisor", 
            update={
                "supervisor_messages": {
                    "type": "override",
                    "value": [
                        SystemMessage(content=supervisor_system_prompt.format(current_datetime=current_datetime)),
                        HumanMessage(content=response.verification)
                    ]
                }
            }
        )


async def supervisor(state:SupervisorState, config: RunnableConfig) -> Command[Literal["heurist_agent", "flipside_agent", "tavily_agent", "__end__"]]:
    supervisor_message = state.get("supervisor_messages", [])
    if isinstance(supervisor_message, str):
        supervisor_message = [HumanMessage(content=supervisor_message)]
    print(f"\ninput received supervisor: \n{supervisor_message}")
    
    supervisor_model = configurable_model.with_structured_output(DelegateAgent)

    response = await supervisor_model.ainvoke(supervisor_message)
    print(f"\nresponse task supervisor: \n{response.heurist_queries} \n{response.flipside_queries} \n{response.tavily_queries}")
    
    #skip if all None
    if not response.heurist_queries and not response.flipside_queries and not response.tavily_queries:
        return Command(goto="__end__")

    # print(response)
    coros = []
    if response.heurist_queries:
        heurist_call = heurist_subgraph.ainvoke({
            "heurist_queries": [
                SystemMessage(content=heurist_mcp_system_prompt.format(current_datetime=current_datetime)),
                HumanMessage(content=response.heurist_queries)
            ],
        }, config)
        coros.append(heurist_call)
    if response.flipside_queries:
        flipside_call = flipside_subgraph.ainvoke({
            "flipside_queries": [
                SystemMessage(content=flipside_mcp_system_prompt.format(current_datetime=current_datetime)),
                HumanMessage(content=response.flipside_queries)
            ]
        }, config)
        coros.append(flipside_call)
    if response.tavily_queries:
        tavily_call = tavily_subgraph.ainvoke({
            "tavily_queries": [
                SystemMessage(content=tavily_mcp_system_prompt.format(current_datetime=current_datetime)),
                HumanMessage(content=response.tavily_queries)
            ]
        }, config)
        coros.append(tavily_call)

    results = await asyncio.gather(*coros)
    
    heurist_results = []
    flipside_results = []
    tavily_results = []
    for result in results:
        if "heurist_results" in result:
            heurist_results.append(result["heurist_results"])
        if "flipside_results" in result:
            flipside_results.append(result["flipside_results"])
        if "tavily_results" in result:
            tavily_results.append(result["tavily_results"])

    return Command(
        goto="__end__",
        update={
            "heurist_queries": response.heurist_queries,
            "heurist_results": heurist_results,
            "flipside_queries": response.flipside_queries,
            "flipside_results": flipside_results,
            "tavily_queries": response.tavily_queries,
            "tavily_results": tavily_results
        }
    )

async def heurist_agent(state: HeuristAgentState, config: RunnableConfig) -> Command[Literal["__end__"]]:
    query = state.get("heurist_queries", [])
    messages = query if isinstance(query, list) else [HumanMessage(content=query)]
    
    # Load only heurist MCP tools
    tools = await load_heurist_mcp(config)
    # print("MCP QUERY IN FUNCTION:", query)
    if not query:
        return Command(
            goto="__end__", 
            update={
                "heurist_queries": [HumanMessage(content="No MCP messages provided")],
                "heurist_results": ["No MCP messages provided"]
                }
            )
    
    HeuristAgent_model = configurable_model.bind_tools(tools)
    while True:
        response = await HeuristAgent_model.ainvoke(messages, config)
        
        if response.tool_calls:
            tool_calls = response.tool_calls
            tasks = []
            for call in tool_calls:
                tool = next((t for t in tools if t.name==call['name']), None)
                if tool:
                    tasks.append(retry_mcp_tool_call(tool, call["args"]))
        
            results = await asyncio.gather(*tasks, return_exceptions=True)

            tool_messages = []
            for call, result in zip(tool_calls, results):
                if isinstance(result, Exception):
                    # If the tool call failed after retries, create an error message
                    error_content = f"Tool call failed after retries: {str(result)}"
                    tool_messages.append(ToolMessage(
                        name=call["name"],
                        tool_call_id=call["id"],
                        content=error_content
                    ))
                else:
                    tool_messages.append(ToolMessage(
                        name=call["name"],
                        tool_call_id=call["id"],
                        content=result
                    ))
            messages.append(response)
            messages.extend(tool_messages)
        else:
            break
    
    return Command(
        goto="__end__",
        update={
            "heurist_queries": query,
            "heurist_results": response.content
        }
    )
heurist_builder = StateGraph(HeuristAgentState)
heurist_builder.add_node("heurist_agent", heurist_agent)
heurist_builder.set_entry_point("heurist_agent")
heurist_builder.add_edge("heurist_agent", END)
heurist_subgraph = heurist_builder.compile()

async def flipside_agent(state: FlipsideAgentState, config: RunnableConfig) -> Command[Literal["__end__"]]:
    query = state.get("flipside_queries", [])
    messages = query if isinstance(query, list) else [HumanMessage(content=query)]
    
    # Load only flipside MCP tools
    tools = await load_flipside_mcp(config)
    # print("MCP QUERY IN FUNCTION:", query)
    if not query:
        return Command(
            goto="__end__", 
            update={
                "flipside_queries": [HumanMessage(content="No MCP messages provided")],
                "flipside_results": ["No MCP messages provided"]
                }
            )
    
    FlipsideAgent_model = configurable_model.bind_tools(tools)
    while True:
        response = await FlipsideAgent_model.ainvoke(messages, config)
        
        if response.tool_calls:
            tool_calls = response.tool_calls
            tasks = []
            for call in tool_calls:
                tool = next((t for t in tools if t.name==call['name']), None)
                if tool:
                    tasks.append(retry_mcp_tool_call(tool, call["args"]))
        
            results = await asyncio.gather(*tasks, return_exceptions=True)

            tool_messages = []
            for call, result in zip(tool_calls, results):
                if isinstance(result, Exception):
                    # If the tool call failed after retries, create an error message
                    error_content = f"Tool call failed after retries: {str(result)}"
                    tool_messages.append(ToolMessage(
                        name=call["name"],
                        tool_call_id=call["id"],
                        content=error_content
                    ))
                else:
                    tool_messages.append(ToolMessage(
                        name=call["name"],
                        tool_call_id=call["id"],
                        content=result
                    ))
            messages.append(response)
            messages.extend(tool_messages)
        else:
            break
    
    return Command(
        goto="__end__",
        update={
            "flipside_queries": query,
            "flipside_results": response.content
        }
    )
flipside_builder = StateGraph(FlipsideAgentState)
flipside_builder.add_node("flipside_agent", flipside_agent)
flipside_builder.set_entry_point("flipside_agent")
flipside_subgraph = flipside_builder.compile()

async def tavily_agent(state: TavilyAgentState, config: RunnableConfig) -> Command[Literal["__end__"]]:
    query = state.get("tavily_queries", [])
    messages = query if isinstance(query, list) else [HumanMessage(content=query)]
    
    # Load Tavily search tool
    tools = await load_tavily_search(config)
    if not query:
        return Command(
            goto="__end__", 
            update={
                "tavily_queries": [HumanMessage(content="No messages provided")],
                "tavily_results": ["No messages provided"]
                }
            )
    
    tavily_model = configurable_model.bind_tools(tools)
    while True:
        response = await tavily_model.ainvoke(messages, config)
        
        if response.tool_calls:
            tool_calls = response.tool_calls
            tasks = []
            for call in tool_calls:
                tool = next((t for t in tools if t.name==call['name']), None)
                if tool:
                    tasks.append(tool.ainvoke(call["args"]))
        
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            tool_messages = []
            for call, result in zip(tool_calls, results):
                if isinstance(result, Exception):
                    # If the tool call failed, create an error message
                    error_content = f"Search failed: {str(result)}"
                    tool_messages.append(ToolMessage(
                        name=call["name"],
                        tool_call_id=call["id"],
                        content=error_content
                    ))
                else:
                    tool_messages.append(ToolMessage(
                        name=call["name"],
                        tool_call_id=call["id"],
                        content=result
                    ))
            messages.append(response)
            messages.extend(tool_messages)
        else:
            break
    
    return Command(
        goto="__end__",
        update={
            "tavily_queries": query,
            "tavily_results": response.content
        }
    )

tavily_builder = StateGraph(TavilyAgentState)
tavily_builder.add_node("tavily_agent", tavily_agent)
tavily_builder.set_entry_point("tavily_agent")
tavily_subgraph = tavily_builder.compile()

supervisor_builder = StateGraph(SupervisorState)
supervisor_builder.add_node("supervisor", supervisor)
supervisor_builder.add_node("heurist_agent", heurist_agent)
supervisor_builder.add_node("flipside_agent", flipside_agent)
supervisor_builder.add_node("tavily_agent", tavily_agent)
supervisor_builder.add_edge(START, "supervisor")
supervisor_builder.add_edge("supervisor", END)
supervisor_subgraph = supervisor_builder.compile()

async def summary_agent(state: SupervisorState, config: RunnableConfig): 
    heurist_state = state.get("heurist_results", [])
    flipside_state = state.get("flipside_results", [])
    tavily_state = state.get("tavily_results", [])
    cleared_state = {
        "heurist_results": {"type": "override", "value": []}, 
        "flipside_results": {"type": "override", "value": []},
        "tavily_results": {"type": "override", "value": []}
    }
    
    heurist_results = heurist_state if isinstance(heurist_state, list) else [HumanMessage(content=heurist_state)]
    flipside_results = flipside_state if isinstance(flipside_state, list) else [HumanMessage(content=flipside_state)]
    tavily_results = tavily_state if isinstance(tavily_state, list) else [HumanMessage(content=tavily_state)]
    
    if not heurist_results and not flipside_results and not tavily_results:
        return Command(
            goto=END, 
            update={
                "final_answer": "No output provided or something went wrong.",
                "messages": [AIMessage(content="No output provided or something went wrong.")]
                }
            )

    summary_prompt = summary_system_prompt.format(
        heurist_results=heurist_results,
        flipside_results=flipside_results,
        tavily_results=tavily_results
    )
    try:
        summary = await summary_model.ainvoke([HumanMessage(content=summary_prompt)])
        return {
            "final_answer": summary.content,
            "messages": [summary],
            **cleared_state
        }
    except Exception as e:
        return {
            "final_answer": "Error generating final report: Maximum retries exceeded",
            "messages": [AIMessage(content=f"Error generating final report: {e}")],
            **cleared_state
        }


ccp = StateGraph(SupervisorState, input_schema=InputState, config=RunnableConfig) 
ccp.add_node("clarify_with_user", clarify_with_user)
ccp.add_node("supervisor", supervisor_subgraph)
ccp.add_node("summary_agent", summary_agent)
ccp.add_edge(START, "clarify_with_user")
ccp.add_edge("supervisor", "summary_agent")
ccp.add_edge("summary_agent", END)
crypt = ccp.compile()