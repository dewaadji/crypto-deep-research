from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage, get_buffer_string, filter_messages
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph
from langgraph.types import Command
import asyncio
from typing import Literal

from state import (
    # AgentState,
    ClarifyWithUser,
    InputState,
    DelegateAgent,
    SupervisorState,
    HeuristAgentState,
    FlipsideAgentState,
)
from utils import (
    configurable_model,
    max_structured_output_retries,
    allow_clarification,
    load_heurist_mcp,
    load_flipside_mcp,
)
from prompt import (
    clarify_with_user_instructions,
    supervisor_system_prompt,
    heurist_mcp_system_prompt,
    flipside_mcp_system_prompt,
    summary_system_prompt
)

async def clarify_with_user(state: SupervisorState, config: RunnableConfig) -> Command[Literal["supervisor", "__end__"]]:
    if not allow_clarification:
        return Command(goto="supervisor")
    
    messages = state["messages"]
    
    clarify_model = configurable_model.with_structured_output(ClarifyWithUser).with_retry(stop_after_attempt=max_structured_output_retries)
    
    response = await clarify_model.ainvoke([
        HumanMessage(content=clarify_with_user_instructions.format(messages=get_buffer_string(messages))),
        SystemMessage(content=supervisor_system_prompt)
        ])
    print(f"\nresponse clarify_user: \n{response}")
    if response.need_clarification:
        return Command(
            goto=END, 
            update={
                "messages": [AIMessage(content=response.question)]
                }
            )
    else:
        return Command(
            goto="supervisor", 
            update={
                # "supervisor_messages": [AIMessage(content=response.verification)],
                "messages": {
                    "type": "override",
                    "value": [
                        SystemMessage(content=supervisor_system_prompt),
                        HumanMessage(content=response.verification)
                    ]
                }
            }
        )


async def supervisor(state:SupervisorState, config: RunnableConfig) -> Command[Literal["heurist_agent", "flipside_agent", "__end__"]]:
    # human_message = state.get("supervisor_messages", [])
    human_message = state.get("messages", [])
    if isinstance(human_message, str):
        human_message = [HumanMessage(content=human_message)]
    print(f"\ninput received supervisor: \n{human_message}")
    
    supervisor_model = configurable_model.with_structured_output(DelegateAgent)

    # messages = [
    #     SystemMessage(content=supervisor_system_prompt),
    #     *human_message
    # ]

    response = await supervisor_model.ainvoke(human_message)
    print(f"\nresponse task supervisor: \n{response.heurist_queries} \n{response.flipside_queries}")
    
    #skip if all None
    if not response.heurist_queries and not response.flipside_queries:
        return Command(goto="__end__")

    # print(response)
    coros = []
    if response.heurist_queries:
        heurist_call = heurist_subgraph.ainvoke({
            "heurist_queries": [
                SystemMessage(content=heurist_mcp_system_prompt),
                HumanMessage(content=response.heurist_queries)
            ],
        }, config)
        coros.append(heurist_call)
    if response.flipside_queries:
        flipside_call = flipside_subgraph.ainvoke({
            "flipside_queries": [
                SystemMessage(content=flipside_mcp_system_prompt),
                HumanMessage(content=response.flipside_queries)
            ]
        }, config)
        coros.append(flipside_call)

    results = await asyncio.gather(*coros)
    #baru
    heurist_results = []
    flipside_results = []
    for result in results:
        if "heurist_results" in result:
            heurist_results.append(result["heurist_results"])
        if "flipside_results" in result:
            flipside_results.append(result["flipside_results"])

    return Command(
        goto="__end__",
        update={
            "heurist_queries": response.heurist_queries,
            "heurist_results": heurist_results,
            "flipside_queries": response.flipside_queries,
            "flipside_results": flipside_results
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
                    tasks.append(tool.ainvoke(call["args"]))
        
            results = await asyncio.gather(*tasks)

            tool_messages = [
                ToolMessage(
                    name=call["name"],
                    tool_call_id=call["id"],
                    content=result
                )
                for call, result in zip(tool_calls, results)
            ]
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
                    tasks.append(tool.ainvoke(call["args"]))
        
            results = await asyncio.gather(*tasks)

            tool_messages = [
                ToolMessage(
                    name=call["name"],
                    tool_call_id=call["id"],
                    content=result
                )
                for call, result in zip(tool_calls, results)
            ]
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

supervisor_builder = StateGraph(SupervisorState)
supervisor_builder.add_node("supervisor", supervisor)
supervisor_builder.add_node("heurist_agent", heurist_subgraph)
supervisor_builder.add_node("flipside_agent", flipside_subgraph)
supervisor_builder.add_edge(START, "supervisor")
supervisor_builder.add_edge("supervisor", END)
supervisor_subgraph = supervisor_builder.compile()

async def summary_agent(state: SupervisorState, config: RunnableConfig): #SupervisorState for switch without clarify_with_user
    heurist_state = state.get("heurist_results", [])
    flipside_state = state.get("flipside_results", [])
    
    heurist_results = heurist_state if isinstance(heurist_state, list) else [HumanMessage(content=heurist_state)]
    flipside_results = flipside_state if isinstance(flipside_state, list) else [HumanMessage(content=flipside_state)]
    if not heurist_results and not flipside_results:
        return Command(
            goto=END, 
            update={
                "final_answer": "No output provided or something went wrong.",
                "messages": [AIMessage(content="No output provided or something went wrong.")]
                }
            )

    summary_prompt = summary_system_prompt.format(
        heurist_results=heurist_results,
        flipside_results=flipside_results
    )
    try:
        summary = await configurable_model.ainvoke([HumanMessage(content=summary_prompt)])
        return Command(
            goto=END,
            update={"final_answer": summary.content}
        )
    except Exception as e:
        return Command(
            goto=END,
            update={"final_answer": f"Error generating final report: {e}"}
        )

ccp = StateGraph(SupervisorState, config=RunnableConfig) #SupervisorState for switch without clarify_with_user
ccp.add_node("clarify_with_user", clarify_with_user)
ccp.add_node("supervisor", supervisor_subgraph)
ccp.add_node("summary_agent", summary_agent)
ccp.add_edge(START, "clarify_with_user")

# Add conditional edge from clarify_with_user
def should_continue_after_clarify(state):
    # Check if we have supervisor_messages (meaning clarification was provided)
    if state.get("supervisor_messages"):
        return "supervisor"
    # Otherwise, end the workflow (clarification needed)
    return END

ccp.add_conditional_edges(
    "clarify_with_user",
    should_continue_after_clarify,
    {
        "supervisor": "supervisor",
        END: END
    }
)

ccp.add_edge("supervisor", "summary_agent")
# ccp.add_edge("summary_agent", END)
crypt = ccp.compile()


def print_streamed_event(event):
    kind = event.get("event")
    if kind == "on_chat_model_stream":
        content = event["data"]["chunk"].content
        if content:
            print(content, end="", flush=True)
    elif kind == "on_tool_start":
        print(f"\n[Tool Start] {event['name']} with inputs: {event['data'].get('input')}")
    elif kind == "on_tool_end":
        print(f"[Tool End] {event['name']} output: {event['data'].get('output')}")
    elif kind == "on_chain_end":
        print("\n[Chain End]")

async def main():
    print("Welcome to the Crypto-Orchestrator Agent! Type 'exit' or 'quit' to stop.")
    while True:
        user_input = input("User: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            print("Exiting.")
            break
        
        # Prepare initial state for the graph
        initial_state = {"messages": [HumanMessage(content=user_input)]}
        print("\n[Streaming response...]")
        
        # Run the workflow and collect the result
        result = await crypt.ainvoke(initial_state)
        
        # Check if we need clarification
        messages = result.get("messages", [])
        if messages and isinstance(messages[-1], AIMessage):
            ai_msg = messages[-1].content
            print(f"\nAI: {ai_msg}")
            
            # Check if this is a clarification question
            if "clarify" in ai_msg.lower() or "please provide" in ai_msg.lower() or "need more information" in ai_msg.lower():
                clarification_input = input("Your clarification: ").strip()
                if clarification_input.lower() not in {"exit", "quit"}:
                    # Continue with clarification
                    clarification_state = {
                        "messages": [HumanMessage(content=clarification_input)],
                        "supervisor_messages": [HumanMessage(content=clarification_input)]
                    }
                    print("\n[Continuing with clarification...]")
                    async for event in crypt.astream_events(clarification_state, version="v1"):
                        print_streamed_event(event)
                    print("\n---\n")
                    continue
            else:
                # Print the final result
                print(f"\nFinal Answer: {result.get('final_answer', 'No final answer provided')}")
        else:
            # Print the final result
            print(f"\nFinal Answer: {result.get('final_answer', 'No final answer provided')}")
        
        print("\n---\n")

if __name__ == "__main__":
    asyncio.run(main())

    # How has Aave performed over the last 6 hours, and what are the analysis and projections for its future development?
    # what is price performance of Hyperliquid past 12 hours, what about people say in X, and what how healthy is Hyperliquid at that time?