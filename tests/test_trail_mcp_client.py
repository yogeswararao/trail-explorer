#!/usr/bin/env python3
"""
Demo script for the Trail MCP Client.
This script demonstrates how to use the TrailMcpClient to interact with the Trail MCP Server.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the project root to sys.path
sys.path.append(str(Path(__file__).parent))

from client.trail_mcp_client import TrailMcpClient


async def demo_client():
    """Demonstrate the Trail MCP client functionality."""
    print("Trail MCP Client Demo")
    print("=" * 50)
    
    client = TrailMcpClient()
    
    try:
        # Test connection
        print("\n1. Testing connection...")
        success = await client.connect()
        if success:
            print("PASS: Connected successfully")
        else:
            print("FAIL: Connection failed")
            return
        
        # Test server info
        print("\n2. Testing server info...")
        server_info = await client.get_server_info()
        print(f"Server info: {server_info}")
        
        # Test tools
        print("\n3. Testing tools...")
        tools = await client.list_tools()
        print(f"Found {len(tools)} tools:")
        for tool in tools:
            print(f"  - {tool.name}: {tool.description}")
        
        # Test resources
        print("\n4. Testing resources...")
        resources = await client.list_resources()
        print(f"Found {len(resources)} resources:")
        for resource in resources:
            print(f"  - {resource.uri}: {resource.description}")
        
        # Test prompts
        print("\n5. Testing prompts...")
        prompts = await client.list_prompts()
        print(f"Found {len(prompts)} prompts:")
        for prompt in prompts:
            print(f"  - {prompt.name}: {prompt.description}")
        
        # Test trail types resource
        print("\n6. Testing trail types resource...")
        trail_types = await client.get_trail_types()
        print(f"Trail types info: {trail_types[:200]}...")
        
        # Test area search
        print("\n7. Testing area search...")
        result = await client.search_trails_by_area_name("Central Park", ["hiking"])
        print(f"Search result: {result.raw_data[:200]}...")
        
        print("\nSUCCESS: All demonstrations completed successfully!")
        
    except Exception as e:
        print(f"FAIL: Demo failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(demo_client()) 