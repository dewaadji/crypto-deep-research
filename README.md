# Crypto Person 🤖

A sophisticated crypto research agent built with LangGraph that combines multiple data sources to provide comprehensive cryptocurrency analysis. The agent uses a supervisor pattern to coordinate between different specialized agents for market data, social sentiment, and on-chain analytics.

## 🚀 Features

- **Multi-Agent Architecture**: Supervisor coordinates between Heurist (market data) and Flipside (on-chain analytics) agents
- **Clarification System**: Intelligent clarification requests to ensure accurate research scope
- **MCP Integration**: Model Context Protocol support for external data sources
- **Real-time Analysis**: Live cryptocurrency data and sentiment analysis
- **Structured Outputs**: Reliable structured responses for consistent results

## 🏗️ Architecture

```
User Input → Clarify Agent → Supervisor → [Heurist Agent | Flipside Agent] → Summary Agent → Final Report
```

- **Clarify Agent**: Asks clarifying questions to understand user requirements
- **Supervisor**: Delegates tasks to specialized agents based on input analysis
- **Heurist Agent**: Handles market data, social sentiment, and general crypto research
- **Flipside Agent**: Processes on-chain data and SQL-based analytics
- **Summary Agent**: Combines results into comprehensive final report

## 📋 Prerequisites

- Python 3.10 or higher
- API keys for your chosen model provider
- MCP server configurations (optional)

## 🛠️ Installation

### 1. Clone and Setup

```bash
# Navigate to your project directory
cd crypto-project

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
# Install the package in editable mode
pip install -e .
```

### 3. Environment Configuration

Create a `.env` file in the project root:

```bash
# Model Configuration
HEURIST_API_KEY=your_api_key_here
HEURIST_BASE_URL=your_base_url_here

# MCP Server URLs (optional)
HEURIST_MCP_URL=your_heurist_mcp_url
FLIPSIDE_MCP_URL=your_flipside_mcp_url
```

## 🚀 Quick Start

### Option 1: LangGraph Studio (Recommended)

1. **Start the LangGraph server**:
   ```bash
   langgraph dev
   ```

2. **Access the Studio UI**:
   - Open your browser to: `http://localhost:8123`
   - Or use the Studio UI: `https://smith.langchain.com/studio/?baseUrl=http://localhost:8123`

3. **Test your graph**:
   - Select the "Crypto Person" graph
   - Enter your crypto research question
   - Click "Submit" to run the analysis

### Option 2: Command Line Testing

```bash
# Test the graph directly
langgraph dev --test
```

## 📝 Usage Examples

### Basic Crypto Research
```
"Which 3 cryptocurrencies had the highest gains today?"
```

### Detailed Analysis
```
"What is the price performance of Hyperliquid over the past 12 hours, what are people saying on X, and how healthy is Hyperliquid at this time?"
```

### Market Analysis
```
"How has Aave performed over the last 6 hours, and what are the analysis and projections for its future development?"
```

## ⚙️ Configuration

### Model Settings

The agent uses configurable models for different tasks. Update `src/utils.py` to change model providers:

```python
configurable_model = init_chat_model(
    model="deepseek/deepseek-r1-distill-llama-70b",
    model_provider="openai",
    api_key=os.getenv("HEURIST_API_KEY"),
    base_url=os.getenv("HEURIST_BASE_URL")
)
```

### MCP Server Configuration

Configure MCP servers in your `.env` file:

```bash
# Heurist MCP for market data
HEURIST_MCP_URL=your_heurist_mcp_server_url

# Flipside MCP for on-chain data
FLIPSIDE_MCP_URL=your_flipside_mcp_server_url
```

## 🔧 Development

### Project Structure

```
crypto-project/
├── src/
│   ├── __init__.py
│   ├── orchestrator_agent.py  # Main graph implementation
│   ├── state.py              # State definitions
│   ├── utils.py              # Utility functions and model config
│   └── prompt.py             # System prompts
├── langgraph.json            # LangGraph configuration
├── pyproject.toml           # Project dependencies
└── README.md               # This file
```

### Making Changes

1. **Edit source files** in the `src/` directory
2. **Restart LangGraph Studio** to see changes immediately
3. **No reinstallation needed** for code changes

### Adding New Agents

1. Create new state classes in `state.py`
2. Add agent functions in `orchestrator_agent.py`
3. Update the supervisor to delegate to new agents
4. Add MCP tools in `utils.py` if needed

## 🐛 Troubleshooting

### Common Issues

1. **Import Errors**: Ensure you're using relative imports (`.state`, `.utils`, `.prompt`)
2. **API Key Issues**: Check your `.env` file and API key validity
3. **MCP Connection**: Verify MCP server URLs are accessible
4. **Model Compatibility**: Ensure your model supports structured outputs

### Debug Mode

Enable debug logging by adding to your `.env`:

```bash
LOG_LEVEL=DEBUG
```

## 📊 State Management

The agent uses sophisticated state management with:

- **MessagesState**: Handles conversation history
- **Override Reducer**: Manages state updates with override capability
- **TypedDict States**: Type-safe state for different agents

### State Flow

1. **InputState**: Initial user input
2. **SupervisorState**: Main coordination state
3. **HeuristAgentState**: Market data processing
4. **FlipsideAgentState**: On-chain data processing

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🙏 Acknowledgments

- Built with [LangGraph](https://github.com/langchain-ai/langgraph)
- Uses [LangChain](https://github.com/langchain-ai/langchain) for LLM orchestration
- MCP integration for extensible tool support

---

**Happy Crypto Researching! 🚀**
