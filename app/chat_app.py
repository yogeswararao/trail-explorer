#!/usr/bin/env python3
"""
Trail Explorer Chat App

A command-line chat application that uses LLM-MCP integration to provide
intelligent trail search capabilities. The LLM automatically calls appropriate
tools based on user queries and provides comprehensive responses.
"""

import asyncio
import sys
import os
from pathlib import Path
import textwrap
import logging

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).parent.parent))
from utils.logging_colors import setup_logger, APP_COLOR
from colorama import Fore

from app.llm_mcp_connector import process_user_query, get_available_tools, get_available_resources, get_available_prompts, get_server_info, cleanup_integration

# Configure logging
logger = setup_logger("chat_app", APP_COLOR, fmt="[APP] %(levelname)s: %(message)s")

# Configure response logger
response_logger = setup_logger("chat_app_response", Fore.LIGHTBLUE_EX, fmt="%(message)s")

class TrailExplorerChat:
    """Interactive chat interface for Trail Explorer."""
    
    def __init__(self):
        """Initialize the chat application."""
        self.running = False
        self.commands = {
            'help': self.show_help,
            'tools': self.show_tools,
            'resources': self.show_resources,
            'prompts': self.show_prompts,
            'info': self.show_server_info,
            'clear': self.clear_screen,
        }
        
    async def start(self):
        """Start the interactive chat session."""
        logger.info("Trail Explorer Chat App")
        logger.info("=" * 50)
        logger.info("Welcome! I can help you find hiking, biking, and walking trails.")
        logger.info("Type 'help' for available commands, 'quit' to exit.")
        print()
        
        self.running = True
        
        while self.running:
            try:
                # Get user input
                user_input = input("You: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ['quit', 'exit', 'q']:
                    await self.quit()
                    break
                if user_input in self.commands:
                    await self.commands[user_input]()
                    continue
                
                # Process the query
                logger.info("Assistant: Thinking...")
                response = await process_user_query(user_input)
                
                # Display the response
                response_logger.info(f"Assistant: {response}")
                print()
                
            except KeyboardInterrupt:
                logger.info("Interrupted by user.")
                await self.quit()
                break
            except Exception as e:
                logger.error(f"Error: {e}")
                print("Please try again or type 'quit' to exit.")
    
    async def show_help(self):
        """Show help information."""
        help_text = textwrap.dedent("""
            Available Commands:
              help           Show this help message
              tools          Show available tools and their descriptions
              resources      Show available resources and their descriptions
              prompts        Show available prompts and their descriptions
              info           Show server information
              clear          Clear the screen
              quit/exit/q    Exit the application

            Example Queries:
              "Find hiking trails in Central Park"
              "What biking trails are available in San Francisco?"
              "Show me walking trails near coordinates 40.7, -74.0, 40.8, -73.9"
              "Get trail statistics for Golden Gate Park"
              "What types of trails are supported?"
              "Compare trails between Central Park and Prospect Park"
              "Plan a hiking adventure in Yosemite"
              "Analyze trail surfaces in Boulder"

            I'll automatically use the appropriate tools, resources, and prompts to search for trails and provide comprehensive responses.
        """)
        response_logger.info(help_text)

    async def show_tools(self):
        await self._display_section("Available Tools", get_available_tools)

    async def show_resources(self):
        await self._display_section("Available Resources", get_available_resources)

    async def show_prompts(self):
        await self._display_section("Available Prompts", get_available_prompts)

    async def show_server_info(self):
        await self._display_section("Server Information", get_server_info)

    def clear_screen(self):
        os.system("cls" if os.name == "nt" else "clear")

    async def _display_section(self, title, fetch_fn):
        logger.info(f"{title}\n" + "-" * 30)
        data = await fetch_fn()
        response_logger.info(data + "\n")
        print()

    async def quit(self):
        """Quit the application."""
        logger.info("Goodbye! Thanks for using Trail Explorer Chat.")
        self.running = False


async def main():
    """Main function to run the chat application."""
    chat = TrailExplorerChat()
    
    try:
        await chat.start()
    except Exception as e:
        print(f"Fatal error: {e}")
        return 1
    finally:
        # Clean up resources
        await cleanup_integration()
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main())) 