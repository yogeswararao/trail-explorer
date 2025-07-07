# Trail Explorer

Trail Explorer is an AI assistant that uses Model Context Protocol (MCP) implementation to provide intelligent trail discovery capabilities. Built on the MCP standard, it enables seamless integration between Large Language Models (LLMs) and OpenStreetMap (OSM) trail data through the Overpass API. The system demonstrates how MCP can bridge AI models with real-world geographic data, allowing users to discover hiking, biking, and walking trails through natural language queries. The system features:

## Features

- **MCP Server**: Implements tools, resources, and prompts based on MCP standard for trail discovery using OSM data
- **MCP Client**: Implements client for interacting with the MCP server. 
- **LLM-Powered CLI Chat App**: An interactive chat application that demonstrates MCP integration by automatically calling appropriate tools based on natural language queries

## Quick Start

### 1. Create and Activate a Virtual Environment
```bash
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
```

### 2. Install All Project Dependencies
```bash
uv sync
```
- This will install all dependencies exactly as specified in `uv.lock` (reproducible installs).
- If `uv.lock` is missing, it will resolve dependencies from `pyproject.toml` and create a new `uv.lock` file.


### 3. Set Up Environment Variables
Create a `.env` file in the project root:
```env
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

### 4. Run the CLI Chat App
```bash
python -m app.chat_app
```
*You do NOT need to run the server manually; the chat app will start it automatically. Uses ``stdio`` transport mechanism*

## Usage Examples

### CLI Chat App
The chat app provides an interactive interface with the following commands:
- `help` - Show help and example queries
- `tools` - List available tools and their descriptions
- `info` - Show server information
- `clear` - Clear the screen
- `quit/exit/q` - Exit the application

**Example Queries:**
- "Find hiking trails in Central Park"
- "What biking trails are available in San Francisco?"
- "Show me walking trails near coordinates 40.7, -74.0, 40.8, -73.9"
- "Get trail statistics for Golden Gate Park"
- "What types of trails are supported?"

The LLM will automatically use the appropriate tools to search for trails and provide comprehensive responses.


## Configuration
- Edit `.env` for API keys
- Change server path in `app/llm_mcp_connector.py` or client code if needed
- Modify logging colors in `utils/logging_colors.py` if desired

## Development & Testing

### Running Tests
```bash
# Run server tests
python -m tests.test_trail_mcp_server

# Run client tests
python -m tests.test_trail_mcp_client
```
## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request 

## License

MIT License

Copyright (c) 2025 Yogeswara Rao

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
