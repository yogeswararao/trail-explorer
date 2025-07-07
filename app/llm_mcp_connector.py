#!/usr/bin/env python3
"""
LLM-MCP Connector for the Chat App

This module integrates the Trail Explorer MCP client claude LLM.
The LLM uses the available tools, resources and prompts to search 
for trails and provide comprehensive responses.
"""

import json
import os
import sys
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from client.trail_mcp_client import TrailMcpClient
from anthropic import Anthropic
from dotenv import load_dotenv
import textwrap
from utils.logging_colors import APP_COLOR, setup_logger

# Add the project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv()

# Configure logging
logger = setup_logger("llm_mcp_connector", APP_COLOR, fmt="[APP] %(levelname)s: %(message)s")


class LlmMcpConnector:
    """Bridge between LLM and MCP client for automatic tool calling."""
    
    _instance: Optional["LlmMcpConnector"] = None

    @classmethod
    async def get_connector(cls) -> "LlmMcpConnector":
        if cls._instance is None:
            cls._instance = cls()
            await cls._instance.connect()
        return cls._instance

    @classmethod
    async def cleanup(cls):
        if cls._instance:
            await cls._instance.disconnect()
            cls._instance = None

    def __init__(self, server_path: str = "server/trail_mcp_server.py"):
        """Initialize the LLM-MCP integration."""
        self.server_path = server_path
        self.mcp_client = TrailMcpClient(server_path)
        self.anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.available_tools: List[Dict[str, Any]] = []
        self.available_resources: List[Dict[str, Any]] = []
        self.available_prompts: List[Dict[str, Any]] = []
        self.is_connected = False
        
    async def connect(self) -> bool:
        """Connect to the MCP server and prepare tools, resources, and prompts for LLM."""
        try:
            # Connect to MCP server
            await self.mcp_client.connect()
            self.is_connected = True
            
            # Get available tools and convert to LLM format
            tools = await self.mcp_client.list_tools()
            self.available_tools = []
            
            for tool in tools:
                tool_dict = {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema
                }
                self.available_tools.append(tool_dict)
            
            # Get available resources
            resources = await self.mcp_client.list_resources()
            self.available_resources = []
            
            for resource in resources:
                resource_dict = {
                    "uri": resource.uri,
                    "name": resource.name,
                    "description": resource.description,
                    "mime_type": resource.mimeType
                }
                self.available_resources.append(resource_dict)
            
            # Get available prompts
            prompts = await self.mcp_client.list_prompts()
            self.available_prompts = []
            
            for prompt in prompts:
                # Convert PromptArgument objects to dictionaries
                arguments_list = []
                if prompt.arguments:
                    for arg in prompt.arguments:
                        arg_dict = {
                            "name": arg.name,
                            "description": arg.description,
                            "required": arg.required
                        }
                        arguments_list.append(arg_dict)
                
                prompt_dict = {
                    "name": prompt.name,
                    "description": prompt.description,
                    "arguments": arguments_list
                }
                self.available_prompts.append(prompt_dict)
            
            logger.info(f"Connected to MCP server with {len(self.available_tools)} tools, {len(self.available_resources)} resources, and {len(self.available_prompts)} prompts")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from the MCP server."""
        if self.is_connected:
            await self.mcp_client.disconnect()
            self.is_connected = False
            logger.info("Disconnected from MCP server")
    
    async def process_query(self, query: str) -> str:
        """Process a user query using the LLM with automatic tool calling (multi-step)."""
        if not self.is_connected:
            raise RuntimeError("Not connected to MCP server")
        
        messages = [
            {
                "role": "user",
                "content": self._create_system_prompt() + f"\n\nUser Query: {query}"
            }
        ]
        
        conversation_history: List[Dict[str, Any]] = messages.copy()
        final_response: List[str] = []
        
        while True:
            # LLM call with tools
            response = self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=conversation_history,  # type: ignore
                tools=self.available_tools  # type: ignore
            )
            
            # Add assistant response to history
            conversation_history.append({
                "role": "assistant",
                "content": response.content
            })
            
            # Track if any tool calls are present
            tool_calls = []
            text_chunks = []
            for content in response.content:
                if content.type == 'text':
                    text_chunks.append(content.text)
                elif content.type == 'tool_use':
                    tool_calls.append(content)
            
            # If there are tool calls, execute them and add results to history
            if tool_calls:
                for tool_call in tool_calls:
                    tool_name = tool_call.name
                    tool_args = tool_call.input
                    try:
                        logger.info(f"Calling tool: {tool_name} with args: {tool_args}")
                        tool_result = await self.mcp_client.call_tool(tool_name, tool_args)  # type: ignore
                        logger.info(f"Tool result: {tool_result[:100]}...")
                        # Add tool result to conversation
                        tool_result_message: Dict[str, Any] = {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tool_call.id,
                                    "content": tool_result
                                }
                            ]
                        }
                        conversation_history.append(tool_result_message)
                    except Exception as e:
                        error_msg = f"Error calling tool {tool_name}: {str(e)}"
                        logger.error(error_msg)
                        text_chunks.append(f"\n{error_msg}")
                # Continue the loop for another LLM round
                continue
            else:
                # No more tool calls, return the accumulated text
                final_response.extend(text_chunks)
                break
        return "\n".join(final_response)
    
    async def get_resource_data(self, uri: str) -> str:
        """Get data from a specific resource."""
        if not self.is_connected:
            raise RuntimeError("Not connected to MCP server")
        
        try:
            result = await self.mcp_client.read_resource(uri)
            return result
        except Exception as e:
            logger.error(f"Error reading resource {uri}: {e}")
            return f"Error reading resource: {str(e)}"
    
    async def get_prompt_data(self, prompt_name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        """Get data from a specific prompt."""
        if not self.is_connected:
            raise RuntimeError("Not connected to MCP server")
        
        try:
            result = await self.mcp_client.get_prompt(prompt_name, arguments)
            return result
        except Exception as e:
            logger.error(f"Error getting prompt {prompt_name}: {e}")
            return f"Error getting prompt: {str(e)}"
    
    def _create_system_prompt(self) -> str:
        """Create a system prompt that explains the available tools, resources, and prompts."""
        return textwrap.dedent(f"""
            You are a helpful assistant that can search for hiking, biking, and walking trails using the Trail Explorer system.

            You have access to three types of capabilities:

            1. TOOLS (for executing actions):
            {self._format_tools_for_prompt()}

            2. RESOURCES (for reading data):
            {self._format_resources_for_prompt()}

            3. PROMPTS (for predefined workflows):
            {self._format_prompts_for_prompt()}

            When a user asks about trails, you should:
              1. Use the appropriate tools to search for trails based on their query
              2. If they mention a location, use search_trails_by_area_name
              3. If they mention coordinates or want to search a specific area, use search_trails_by_coordinates
              4. If they want statistics, use get_trail_statistics
              5. If they want information about trail types, use the trails://types resource
              6. If they want to compare areas, use the compare_trail_areas prompt
              7. If they want to plan an adventure, use the plan_trail_adventure prompt
              8. If they want surface analysis, use the trail_surface_analysis prompt

            Always provide comprehensive, well-formatted responses that include:
              - Summary of what you found
              - Number of trails found
              - Types of trails available
              - Key details about the trails
              - Any relevant statistics

            Response format: Plain text only. No asterisks, backticks, hashes, or other markdown syntax. No bold, italic, or code formatting. Terminal-friendly output only.
        """)
    
    def _format_tools_for_prompt(self) -> str:
        """Format the available tools for inclusion in the system prompt."""
        if not self.available_tools:
            return "No tools available"
        
        tool_descriptions = []
        for tool in self.available_tools:
            desc = f"• {tool['name']}: {tool['description']}"
            if tool.get('input_schema'):
                desc += f"\n  Input: {json.dumps(tool['input_schema'], indent=2)}"
            tool_descriptions.append(desc)
        
        return "\n".join(tool_descriptions)
    
    def _format_resources_for_prompt(self) -> str:
        """Format the available resources for inclusion in the system prompt."""
        if not self.available_resources:
            return "No resources available"
        
        resource_descriptions = []
        for resource in self.available_resources:
            desc = f"• {resource['uri']}: {resource['description']}"
            resource_descriptions.append(desc)
        
        return "\n".join(resource_descriptions)
    
    def _format_prompts_for_prompt(self) -> str:
        """Format the available prompts for inclusion in the system prompt."""
        if not self.available_prompts:
            return "No prompts available"
        
        prompt_descriptions = []
        for prompt in self.available_prompts:
            desc = f"• {prompt['name']}: {prompt['description']}"
            if prompt.get('arguments'):
                desc += f"\n  Arguments: {json.dumps(prompt['arguments'], indent=2)}"
            prompt_descriptions.append(desc)
        
        return "\n".join(prompt_descriptions)
    
    async def get_tool_descriptions(self) -> str:
        """Get descriptions of available tools for display."""
        if not self.available_tools:
            return "No tools available"
        
        descriptions = []
        for tool in self.available_tools:
            desc = f"{tool['name']}: {tool['description']}"
            if tool.get('input_schema'):
                desc += f"\n  Input schema: {json.dumps(tool['input_schema'], indent=2)}"
            descriptions.append(desc)
        
        return "\n\n".join(descriptions)
    
    async def get_resource_descriptions(self) -> str:
        """Get descriptions of available resources for display."""
        if not self.available_resources:
            return "No resources available"
        
        descriptions = []
        for resource in self.available_resources:
            desc = f"{resource['uri']}: {resource['description']}"
            descriptions.append(desc)
        
        return "\n\n".join(descriptions)
    
    async def get_prompt_descriptions(self) -> str:
        """Get descriptions of available prompts for display."""
        if not self.available_prompts:
            return "No prompts available"
        
        descriptions = []
        for prompt in self.available_prompts:
            desc = f"{prompt['name']}: {prompt['description']}"
            if prompt.get('arguments'):
                desc += f"\n  Arguments: {json.dumps(prompt['arguments'], indent=2)}"
            descriptions.append(desc)
        
        return "\n\n".join(descriptions)
    
    async def get_server_info(self) -> str:
        """Get server information for display."""
        if not self.is_connected:
            return "Not connected to server"
        
        try:
            info = await self.mcp_client.get_server_info()
            
            # Format the info as a readable string
            result = []
            result.append(f"Server Information:")
            result.append(f"Tools: {len(self.available_tools)}")
            result.append(f"Resources: {len(self.available_resources)}")
            result.append(f"Prompts: {len(self.available_prompts)}")
            
            if self.available_tools:
                result.append("\nTools:")
                for tool in self.available_tools:
                    result.append(f"  - {tool['name']}: {tool['description']}")
            
            if self.available_resources:
                result.append("\nResources:")
                for resource in self.available_resources:
                    result.append(f"  - {resource['uri']}: {resource['description']}")
            
            if self.available_prompts:
                result.append("\nPrompts:")
                for prompt in self.available_prompts:
                    result.append(f"  - {prompt['name']}: {prompt['description']}")
            
            return "\n".join(result)
            
        except Exception as e:
            logger.error(f"Error getting server info: {e}")
            return f"Error getting server info: {str(e)}"


async def process_user_query(query: str) -> str:
    """Process a user query using the LLM-MCP integration."""
    try:
        connector = await LlmMcpConnector.get_connector()
        result = await connector.process_query(query)
        return result
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        return f"Sorry, I encountered an error while processing your query: {str(e)}"


async def get_available_tools() -> str:
    """Get descriptions of available tools."""
    try:
        connector = await LlmMcpConnector.get_connector()
        return await connector.get_tool_descriptions()
    except Exception as e:
        logger.error(f"Error getting tools: {e}")
        return f"Error getting available tools: {str(e)}"


async def get_available_resources() -> str:
    """Get descriptions of available resources."""
    try:
        connector = await LlmMcpConnector.get_connector()
        return await connector.get_resource_descriptions()
    except Exception as e:
        logger.error(f"Error getting resources: {e}")
        return f"Error getting available resources: {str(e)}"


async def get_available_prompts() -> str:
    """Get descriptions of available prompts."""
    try:
        connector = await LlmMcpConnector.get_connector()
        return await connector.get_prompt_descriptions()
    except Exception as e:
        logger.error(f"Error getting prompts: {e}")
        return f"Error getting available prompts: {str(e)}"


async def get_server_info() -> str:
    """Get server information."""
    try:
        connector = await LlmMcpConnector.get_connector()
        return await connector.get_server_info()
    except Exception as e:
        logger.error(f"Error getting server info: {e}")
        return f"Error getting server info: {str(e)}"


async def cleanup_integration():
    """Clean up the global connector instance."""
    await LlmMcpConnector.cleanup() 