#!/usr/bin/env python3
"""
MCP Client for Trail Explorer Server

This client implements the official MCP client pattern to interact with the
Trail Explorer MCP server, including fetching tools, resources, and prompts.
"""

import asyncio
import json
import logging
import sys
from typing import Dict, List, Optional, Any, Union
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import (
    TextContent,
    Tool, Resource, Prompt
)
from pydantic import AnyUrl
from pydantic import TypeAdapter
from utils.logging_colors import setup_logger, CLIENT_COLOR

# Configure logging
logger = setup_logger("trail_mcp_client", CLIENT_COLOR, fmt="[CLIENT] %(levelname)s: %(message)s")

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))


@dataclass
class TrailSearchResult:
    """Container for trail search results."""
    location: str
    trail_count: int
    trail_types: Dict[str, int]
    trails: List[Dict[str, Any]]
    raw_data: str


@dataclass
class ServerCapabilities:
    """Container for server capabilities."""
    tools: List[Tool]
    resources: List[Resource]
    prompts: List[Prompt]


class TrailMcpClient:
    """MCP client for Trail Explorer server with comprehensive capabilities."""
    
    def __init__(self, server_path: str = "server/trail_mcp_server.py"):
        """Initialize the MCP client."""
        self.server_path = server_path
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.capabilities: Optional[ServerCapabilities] = None
        
    async def connect(self) -> bool:
        """Connect to the Trail Explorer MCP server."""
        try:
            logger.info(f"Connecting to server at {self.server_path}")
            
            # Create server parameters
            server_params = StdioServerParameters(
                command="python",
                args=[self.server_path],
                env=None
            )
            
            # Connect to the server
            stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
            self.stdio, self.write = stdio_transport
            self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
            
            # Initialize the session
            await self.session.initialize()
            
            # Fetch server capabilities
            await self._fetch_capabilities()
            
            logger.info("Connected to Trail Explorer MCP server")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to server: {e}")
            raise
    
    async def _fetch_capabilities(self):
        """Fetch server capabilities (tools, resources, prompts)."""
        if not self.session:
            raise RuntimeError("Not connected to server")
            
        try:
            # List tools
            tools_response = await self.session.list_tools()
            
            # List resources
            resources_response = await self.session.list_resources()
            
            # List prompts
            prompts_response = await self.session.list_prompts()
            
            self.capabilities = ServerCapabilities(
                tools=tools_response.tools,
                resources=resources_response.resources,
                prompts=prompts_response.prompts
            )
            
            logger.info(f"Server capabilities loaded:")
            logger.info(f"  - Tools: {len(self.capabilities.tools)}")
            logger.info(f"  - Resources: {len(self.capabilities.resources)}")
            logger.info(f"  - Prompts: {len(self.capabilities.prompts)}")
            
        except Exception as e:
            logger.error(f"Failed to fetch capabilities: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from the server."""
        if self.session:
            await self.exit_stack.aclose()
            logger.info("Disconnected from Trail Explorer MCP server")
    
    # Tool-related methods
    async def list_tools(self) -> List[Tool]:
        """Get list of available tools."""
        if not self.session:
            raise RuntimeError("Not connected to server")
        
        if self.capabilities:
            return self.capabilities.tools
        else:
            response = await self.session.list_tools()
            return response.tools
    
    async def get_tool_info(self, tool_name: str) -> Optional[Tool]:
        """Get information about a specific tool."""
        tools = await self.list_tools()
        for tool in tools:
            if tool.name == tool_name:
                return tool
        return None
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool on the server."""
        if not self.session:
            raise RuntimeError("Not connected to server")
        
        try:
            result = await self.session.call_tool(tool_name, arguments)
            
            # Extract text content from result
            if result.content:
                text_parts = []
                for content_item in result.content:
                    if isinstance(content_item, TextContent):
                        text_parts.append(content_item.text)
                    elif isinstance(content_item, dict) and 'text' in content_item:
                        text_parts.append(str(content_item['text']))
                
                return "\n".join(text_parts)
            else:
                return "No content returned from tool"
                
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            raise
    
    # Resource-related methods
    async def list_resources(self) -> List[Resource]:
        """Get list of available resources."""
        if not self.session:
            raise RuntimeError("Not connected to server")
        
        if self.capabilities:
            return self.capabilities.resources
        else:
            response = await self.session.list_resources()
            return response.resources
    
    async def get_resource_info(self, uri: str) -> Optional[Resource]:
        """Get information about a specific resource."""
        resources = await self.list_resources()
        for resource in resources:
            if resource.uri == uri:
                return resource
        return None
    
    async def read_resource(self, uri: str) -> str:
        """Read a resource from the server."""
        if not self.session:
            raise RuntimeError("Not connected to server")
        
        try:
            # Validate URI format
            validated_uri = TypeAdapter(AnyUrl).validate_python(uri)
            result = await self.session.read_resource(validated_uri)
            
            # Extract text content from result
            if result.contents:
                text_parts = []
                for content_item in result.contents:
                    if isinstance(content_item, TextContent):
                        text_parts.append(content_item.text)
                    elif isinstance(content_item, dict) and 'text' in content_item:
                        text_parts.append(str(content_item['text']))
                
                return "\n".join(text_parts)
            else:
                return "No content returned from resource"
                
        except Exception as e:
            logger.error(f"Error reading resource {uri}: {e}")
            raise
    
    # Prompt-related methods
    async def list_prompts(self) -> List[Prompt]:
        """Get list of available prompts."""
        if not self.session:
            raise RuntimeError("Not connected to server")
        
        if self.capabilities:
            return self.capabilities.prompts
        else:
            response = await self.session.list_prompts()
            return response.prompts
    
    async def get_prompt_info(self, prompt_name: str) -> Optional[Prompt]:
        """Get information about a specific prompt."""
        prompts = await self.list_prompts()
        for prompt in prompts:
            if prompt.name == prompt_name:
                return prompt
        return None
    
    async def get_prompt(self, prompt_name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        """Get a prompt from the server."""
        if not self.session:
            raise RuntimeError("Not connected to server")
        
        try:
            result = await self.session.get_prompt(prompt_name, arguments)
            
            if result.description:
                return result.description
            else:
                return f"Prompt: {prompt_name}"
                
        except Exception as e:
            logger.error(f"Error getting prompt {prompt_name}: {e}")
            raise
    
    # Convenience methods for trail-specific operations
    async def search_trails_by_area_name(
        self, 
        area_name: str, 
        trail_types: Optional[List[str]] = None
    ) -> TrailSearchResult:
        """Search for trails in a specific area."""
        arguments = {
            "area_name": area_name,
            "trail_types": trail_types or ["hiking", "biking", "walking"]
        }
        
        result = await self.call_tool("search_trails_by_area_name", arguments)
        
        return TrailSearchResult(
            location=area_name,
            trail_count=0,  # Will be parsed from response
            trail_types={},
            trails=[],
            raw_data=result
        )
    
    async def search_trails_by_coordinates(
        self,
        south: float,
        west: float,
        north: float,
        east: float,
        trail_types: Optional[List[str]] = None
    ) -> TrailSearchResult:
        """Search for trails within specific coordinates."""
        arguments = {
            "south": south,
            "west": west,
            "north": north,
            "east": east,
            "trail_types": trail_types or ["hiking", "biking", "walking"]
        }
        
        result = await self.call_tool("search_trails_by_coordinates", arguments)
        
        return TrailSearchResult(
            location=f"bbox({south},{west},{north},{east})",
            trail_count=0,
            trail_types={},
            trails=[],
            raw_data=result
        )
    
    async def get_trail_statistics(
        self,
        location: Optional[str] = None,
        south: Optional[float] = None,
        west: Optional[float] = None,
        north: Optional[float] = None,
        east: Optional[float] = None
    ) -> str:
        """Get trail statistics."""
        arguments = {}
        if location:
            arguments["location"] = location
        if all(coord is not None for coord in [south, west, north, east]):
            arguments.update({
                "south": south,
                "west": west,
                "north": north,
                "east": east
            })
        
        if not arguments:
            return "Error: Must provide either location or all coordinates"
        
        return await self.call_tool("get_trail_statistics", arguments)
    
    async def get_trail_types(self) -> str:
        """Get information about supported trail types."""
        return await self.read_resource("trails://types")
    
    async def get_trails_bbox_resource(
        self,
        south: float,
        west: float,
        north: float,
        east: float
    ) -> str:
        """Get trails using the bbox resource."""
        uri = f"trails://bbox/{south}/{west}/{north}/{east}"
        return await self.read_resource(uri)
    
    async def get_trails_area_resource(self, area_name: str) -> str:
        """Get trails using the area resource."""
        uri = f"trails://area/{area_name}"
        return await self.read_resource(uri)
    
    # Utility methods
    async def get_server_info(self) -> Dict[str, Any]:
        """Get comprehensive server information."""
        if not self.capabilities:
            await self._fetch_capabilities()
        
        if not self.capabilities:
            return {"tools": [], "resources": [], "prompts": []}
        
        return {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema
                }
                for tool in self.capabilities.tools
            ],
            "resources": [
                {
                    "uri": str(resource.uri),
                    "name": resource.name,
                    "description": resource.description,
                    "mime_type": resource.mimeType
                }
                for resource in self.capabilities.resources
            ],
            "prompts": [
                {
                    "name": prompt.name,
                    "description": prompt.description,
                    "arguments": [
                        {
                            "name": arg.name,
                            "description": arg.description,
                            "required": arg.required
                        }
                        for arg in prompt.arguments
                    ] if prompt.arguments else []
                }
                for prompt in self.capabilities.prompts
            ]
        }
