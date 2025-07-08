"""
MCP Server for querying biking, hiking, and walking trails using Overpass API.

This server provides:
- Resources: Access to trail data by location and type
- Tools: Query trails with various filters
- Prompts: Common trail query templates
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
import asyncio
import json
import logging
from typing import Dict, List, Optional, Any, Union
import httpx
from urllib.parse import quote
from dataclasses import dataclass
from enum import Enum
import textwrap

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
from utils.logging_colors import setup_logger, SERVER_COLOR

# Configure logging
logger = setup_logger("trail_mcp_server", SERVER_COLOR, fmt="[SERVER] %(levelname)s: %(message)s")

# Create the MCP server
mcp = FastMCP(
    "Trail Explorer",
    dependencies=["httpx"]
)

# Configuration
@dataclass
class Config:
    """Configuration settings for the trails server."""
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    timeout: float = 60.0
    max_trails_display: int = 50
    query_timeout: int = 30

config = Config()

class TrailType(Enum):
    """Enumeration of supported trail types."""
    HIKING = "hiking"
    BIKING = "biking"
    WALKING = "walking"

# Trail type mappings to OSM tags
TRAIL_TYPES = {
    TrailType.HIKING.value: {
        "route": ["hiking", "foot"],
        "highway": ["footway", "path", "track", "bridleway", "steps"],
        "foot": "yes",
        "access_exclude": ["private", "no"]
    },
    TrailType.BIKING.value: {
        "route": ["bicycle", "mtb"],
        "highway": ["cycleway", "path", "track"],
        "bicycle": "yes",
        "access_exclude": ["private", "no"]
    },
    TrailType.WALKING.value: {
        "route": ["walking", "foot"],
        "highway": ["footway", "pedestrian", "path", "steps"],
        "foot": "yes",
        "access_exclude": ["private", "no"]
    }
}


class OverpassQueryBuilder:
    """Helper class to build Overpass API queries."""

    @staticmethod
    def build_access_filters(access_exclude: List[str]) -> str:
        """Build access exclusion filters."""
        filters = []
        for access in access_exclude:
            filters.append(f'["access"!="{access}"]')
        return "".join(filters)

    @staticmethod
    def build_bbox_query(
            south: float, west: float, north: float, east: float,
            trail_types: Optional[List[str]] = None
    ) -> str:
        """Build a query for trails within a bounding box."""
        if trail_types is None:
            trail_types = list(TRAIL_TYPES.keys())

        # Validate coordinates
        if not (-90 <= south <= 90) or not (-90 <= north <= 90):
            raise ValueError("Latitude must be between -90 and 90 degrees")
        if not (-180 <= west <= 180) or not (-180 <= east <= 180):
            raise ValueError("Longitude must be between -180 and 180 degrees")
        if south >= north:
            raise ValueError("South latitude must be less than north latitude")
        if west >= east:
            raise ValueError("West longitude must be less than east longitude")

        # Build the query parts
        query_parts = [f"[out:json][timeout:{config.query_timeout}][maxsize:1073741824];", "("]

        for trail_type in trail_types:
            if trail_type in TRAIL_TYPES:
                tags = TRAIL_TYPES[trail_type]
                access_filters = OverpassQueryBuilder.build_access_filters(tags.get("access_exclude", []))

                # Add route relations
                for route_type in tags.get("route", []):
                    query_parts.append(
                        f'  relation["route"="{route_type}"]({south},{west},{north},{east});'
                    )

                # Add highway ways with access filtering
                for highway_type in tags.get("highway", []):
                    query_parts.append(
                        f'  way["highway"="{highway_type}"]{access_filters}({south},{west},{north},{east});'
                    )

        query_parts.extend([");", "out geom;"])
        return "\n".join(query_parts)

    @staticmethod
    def build_area_query(area_name: str, trail_types: Optional[List[str]] = None) -> str:
        """Build a query for trails within a named area."""
        if trail_types is None:
            trail_types = list(TRAIL_TYPES.keys())

        if not area_name or not area_name.strip():
            raise ValueError("Area name cannot be empty")

        # Sanitize area name for query
        sanitized_area = area_name.strip().replace('"', '\\"')

        # Build area search - start with most specific (parks)
        query_parts = [
            f"[out:json][timeout:{config.query_timeout}][maxsize:1073741824];",
            "(",
            f'  area["name"="{sanitized_area}"]["leisure"="park"]->.searchArea;',
            ");",
            "("
        ]

        for trail_type in trail_types:
            if trail_type in TRAIL_TYPES:
                tags = TRAIL_TYPES[trail_type]
                access_filters = OverpassQueryBuilder.build_access_filters(tags.get("access_exclude", []))

                # Add route relations
                for route_type in tags.get("route", []):
                    query_parts.append(
                        f'  relation(area.searchArea)["route"="{route_type}"];'
                    )

                # Add highway ways with access filtering
                for highway_type in tags.get("highway", []):
                    query_parts.append(
                        f'  way(area.searchArea)["highway"="{highway_type}"]{access_filters};'
                    )

        query_parts.extend([");", "out geom;"])
        return "\n".join(query_parts)


class OverpassAPIError(Exception):
    """Custom exception for Overpass API errors."""
    pass


async def query_overpass(query: str) -> Dict[str, Any]:
    """Execute an Overpass API query."""
    logger.info(f"Executing Overpass query: {query[:100]}...")
    
    async with httpx.AsyncClient(timeout=config.timeout) as client:
        try:
            response = await client.post(
                config.overpass_url,
                content=query,  # Use content instead of data for string
                headers={"Content-Type": "text/plain"}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP error during Overpass query: {e}")
            raise OverpassAPIError(f"Overpass API error: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            raise OverpassAPIError("Invalid JSON response from Overpass API")
        except Exception as e:
            logger.error(f"Unexpected error during Overpass query: {e}")
            raise OverpassAPIError(f"Unexpected error: {str(e)}")


def format_trail_data(data: Dict[str, Any]) -> str:
    """Format trail data for human-readable output."""
    elements = data.get("elements", [])
    if not elements:
        return "No trails found in the specified area."

    formatted_trails = []
    trail_count = {trail_type: 0 for trail_type in TRAIL_TYPES.keys()}

    for element in elements:
        tags = element.get("tags", {})
        name = tags.get("name", "Unnamed trail")
        trail_type = identify_trail_type(tags)

        if trail_type:
            trail_count[trail_type] += 1

            trail_info = [f"{name} ({trail_type.title()}"]

            # Add additional info if available
            if "distance" in tags:
                trail_info.append(f"Distance: {tags['distance']}")
            if "surface" in tags:
                trail_info.append(f"Surface: {tags['surface']}")
            if "difficulty" in tags:
                trail_info.append(f"Difficulty: {tags['difficulty']}")
            if "description" in tags:
                trail_info.append(f"Description: {tags['description']}")

            formatted_trails.append(" | ".join(trail_info) + ")")

    # Summary
    summary = f"Found {len(elements)} trail elements:\n"
    for trail_type, count in trail_count.items():
        if count > 0:
            summary += f"- {trail_type.title()}: {count}\n"
    summary += "\n"

    # Detailed trails
    if formatted_trails:
        summary += "Trail Details:\n" + "\n".join(formatted_trails[:config.max_trails_display])
        if len(formatted_trails) > config.max_trails_display:
            summary += f"\n... and {len(formatted_trails) - config.max_trails_display} more trails"

    return summary


def identify_trail_type(tags: Dict[str, str]) -> Optional[str]:
    """Identify the type of trail based on OSM tags."""
    route = tags.get("route", "")
    highway = tags.get("highway", "")

    # Check for specific route types
    if route in ["hiking", "foot"]:
        return TrailType.HIKING.value
    elif route in ["bicycle", "mtb"]:
        return TrailType.BIKING.value
    elif route in ["walking"]:
        return TrailType.WALKING.value

    # Check highway types
    if highway in ["cycleway"] or tags.get("bicycle") == "yes":
        return TrailType.BIKING.value
    elif highway in ["footway", "pedestrian"] or tags.get("foot") == "yes":
        return TrailType.HIKING.value
    elif highway in ["path", "track"]:
        # Path/track could be either - check additional tags
        if tags.get("bicycle") == "yes":
            return TrailType.BIKING.value
        else:
            return TrailType.HIKING.value

    return None


def validate_trail_types(trail_types: Optional[List[str]]) -> List[str]:
    """Validate and return valid trail types."""
    if trail_types is None:
        return list(TRAIL_TYPES.keys())
    
    valid_types = [t for t in trail_types if t in TRAIL_TYPES]
    if not valid_types:
        raise ValueError("No valid trail types specified. Use: hiking, biking, or walking")
    
    return valid_types


# Tools
@mcp.tool()
async def search_trails_by_coordinates(
        south: float,
        west: float,
        north: float,
        east: float,
        trail_types: Optional[List[str]] = None
) -> str:
    """
    Search for trails within specific coordinates.

    Args:
        south: Southern boundary latitude
        west: Western boundary longitude
        north: Northern boundary latitude
        east: Eastern boundary longitude
        trail_types: List of trail types to search for (hiking, biking, walking)
    """
    try:
        valid_types = validate_trail_types(trail_types)
        query = OverpassQueryBuilder.build_bbox_query(south, west, north, east, valid_types)
        data = await query_overpass(query)
        return format_trail_data(data)
    except Exception as e:
        logger.error(f"Error in search_trails_by_coordinates: {e}")
        return f"Error searching trails: {str(e)}"


@mcp.tool()
async def search_trails_by_area_name(
        area_name: str,
        trail_types: Optional[List[str]] = None
) -> str:
    """
    Search for trails in a named area (city, park, region).

    Args:
        area_name: Name of the area to search in
        trail_types: List of trail types to search for (hiking, biking, walking)
    """
    try:
        valid_types = validate_trail_types(trail_types)
        
        # Try different area search strategies in order of specificity
        sanitized_area = area_name.strip().replace('"', '\\"')
        search_strategies = [
            ("park", f'area["name"="{sanitized_area}"]["leisure"="park"]->.searchArea;'),
            ("administrative", f'area["name"="{sanitized_area}"]["boundary"="administrative"]->.searchArea;'),
            ("any", f'area["name"="{sanitized_area}"]->.searchArea;')
        ]
        
        for strategy_name, area_query in search_strategies:
            try:
                logger.info(f"Trying {strategy_name} strategy for area: {area_name}")
                
                # Build query with this strategy
                query_parts = [
                    f"[out:json][timeout:{config.query_timeout}][maxsize:1073741824];",
                    "(",
                    area_query,
                    ");",
                    "("
                ]

                for trail_type in valid_types:
                    if trail_type in TRAIL_TYPES:
                        tags = TRAIL_TYPES[trail_type]
                        access_filters = OverpassQueryBuilder.build_access_filters(tags.get("access_exclude", []))

                        # Add route relations
                        for route_type in tags.get("route", []):
                            query_parts.append(
                                f'  relation(area.searchArea)["route"="{route_type}"];'
                            )

                        # Add highway ways with access filtering
                        for highway_type in tags.get("highway", []):
                            query_parts.append(
                                f'  way(area.searchArea)["highway"="{highway_type}"]{access_filters};'
                            )

                query_parts.extend([");", "out geom;"])
                query = "\n".join(query_parts)
                
                data = await query_overpass(query)
                
                # If we get results, return them
                if data.get("elements"):
                    logger.info(f"Found results using {strategy_name} strategy")
                    return format_trail_data(data)
                    
            except Exception as e:
                logger.warning(f"Strategy {strategy_name} failed for {area_name}: {e}")
                continue
        
        # If all strategies failed, return no results
        return "No trails found in the specified area after trying multiple search strategies."
        
    except Exception as e:
        logger.error(f"Error in search_trails_by_area_name: {e}")
        return f"Error searching trails: {str(e)}"


@mcp.tool()
async def get_trail_statistics(
        area_name: Optional[str] = None,
        south: Optional[float] = None,
        west: Optional[float] = None,
        north: Optional[float] = None,
        east: Optional[float] = None
) -> str:
    """
    Get statistics about trails in a location.

    Args:
        area_name: Name of the area (alternative to coordinates)
        south: Southern boundary latitude (if using coordinates)
        west: Western boundary longitude (if using coordinates)
        north: Northern boundary latitude (if using coordinates)
        east: Eastern boundary longitude (if using coordinates)
    """
    try:
        if area_name:
            query = OverpassQueryBuilder.build_area_query(area_name)
        elif all(coord is not None for coord in [south, west, north, east]):
            # Since we've validated all coordinates are not None, we can safely cast them
            assert south is not None and west is not None and north is not None and east is not None
            query = OverpassQueryBuilder.build_bbox_query(
                south=south, west=west, north=north, east=east
            )
        else:
            return "Please provide either an area name or all four coordinates (south, west, north, east)"

        data = await query_overpass(query)
        elements = data.get("elements", [])

        if not elements:
            return "No trail data found for the specified area."

        # Count by type and collect statistics
        stats = {trail_type: 0 for trail_type in TRAIL_TYPES.keys()}
        stats["unknown"] = 0
        surfaces = {}
        difficulties = {}

        for element in elements:
            tags = element.get("tags", {})
            trail_type = identify_trail_type(tags)

            if trail_type:
                stats[trail_type] += 1
            else:
                stats["unknown"] += 1

            # Surface statistics
            surface = tags.get("surface", "unknown")
            surfaces[surface] = surfaces.get(surface, 0) + 1

            # Difficulty statistics
            difficulty = tags.get("difficulty", "unknown")
            difficulties[difficulty] = difficulties.get(difficulty, 0) + 1

        # Format results
        result = f"Trail Statistics:\n\n"
        result += f"Total elements: {len(elements)}\n\n"

        result += "By Type:\n"
        for trail_type, count in stats.items():
            if count > 0:
                result += f"- {trail_type.title()}: {count}\n"

        result += "\nBy Surface:\n"
        for surface, count in sorted(surfaces.items(), key=lambda x: x[1], reverse=True)[:10]:
            result += f"- {surface}: {count}\n"

        result += "\nBy Difficulty:\n"
        for difficulty, count in sorted(difficulties.items(), key=lambda x: x[1], reverse=True):
            if difficulty != "unknown":
                result += f"- {difficulty}: {count}\n"

        return result
    except Exception as e:
        logger.error(f"Error in get_trail_statistics: {e}")
        return f"Error getting trail statistics: {str(e)}"

# Resources
@mcp.resource("trails://bbox/{south}/{west}/{north}/{east}")
def get_trails_bbox(south: float, west: float, north: float, east: float) -> str:
    """Get trails within a bounding box (south, west, north, east coordinates)."""
    try:
        query = OverpassQueryBuilder.build_bbox_query(south, west, north, east)
        data = asyncio.run(query_overpass(query))
        return format_trail_data(data)
    except Exception as e:
        logger.error(f"Error in get_trails_bbox: {e}")
        return f"Error retrieving trail data: {str(e)}"


@mcp.resource("trails://area/{area_name}")
def get_trails_area(area_name: str) -> str:
    """Get trails within a named area (city, park, region)."""
    try:
        query = OverpassQueryBuilder.build_area_query(area_name)
        data = asyncio.run(query_overpass(query))
        return format_trail_data(data)
    except Exception as e:
        logger.error(f"Error in get_trails_area: {e}")
        return f"Error retrieving trail data: {str(e)}"


@mcp.resource("trails://types")
def get_trail_types() -> str:
    """Get information about supported trail types and their OSM mappings."""
    info = "Supported Trail Types:\n\n"

    for trail_type, tags in TRAIL_TYPES.items():
        info += f"{trail_type.title()}:\n"
        info += f"- Route types: {', '.join(tags.get('route', []))}\n"
        info += f"- Highway types: {', '.join(tags.get('highway', []))}\n"
        if 'foot' in tags:
            info += f"- Foot access: {tags['foot']}\n"
        if 'bicycle' in tags:
            info += f"- Bicycle access: {tags['bicycle']}\n"
        info += "\n"

    return info


# Prompts
@mcp.prompt()
def find_trails_near_city(city: str) -> str:
    """Generate a prompt to find trails near a specific city."""
    return textwrap.dedent(f"""
        Please help me find trails near {city}. I'm interested in:

        1. What types of trails are available (hiking, biking, walking)
        2. Popular trail names and their difficulty levels
        3. Surface types and trail conditions
        4. Any notable features or descriptions

        Use the search_trails_by_area_name tool with the city name "{city}" to get this information. 
        If there are no results for "{city}", try searching with coordinates or nearby areas.
    """)


@mcp.prompt()
def compare_trail_areas(area1: str, area2: str) -> str:
    """Generate a prompt to compare trails between two areas."""
    return textwrap.dedent(f"""
        Please compare the trail options between {area1} and {area2}. For each area, provide:

        1. Total number of trails by type (hiking, biking, walking)
        2. Variety of surfaces and difficulty levels
        3. Notable differences in trail infrastructure
        4. Which area might be better for different activities

        Use the get_trail_statistics tool for both "{area1}" and "{area2}" and then compare the results.
        Also use search_trails_by_area_name for both areas to get specific trail details.
    """)


@mcp.prompt()
def plan_trail_adventure(trail_type: str, location: str) -> str:
    """Generate a prompt to plan a trail adventure."""
    return textwrap.dedent(f"""
        I want to plan a {trail_type} adventure in {location}. Please help me by:

        1. Finding all {trail_type} trails in the area
        2. Providing details about trail surfaces and difficulty
        3. Highlighting any trails with interesting descriptions or features
        4. Summarizing the best options for a {trail_type} enthusiast
        5. Suggesting trail combinations for a full day of adventure

        Use the search_trails_by_area_name tool with location "{location}" and filter for "{trail_type}" trails.
        Also check the trail statistics to understand the variety available.
    """)


@mcp.prompt()
def trail_surface_analysis(location: str) -> str:
    """Generate a prompt for trail surface analysis."""
    return textwrap.dedent(f"""
        I'm planning to visit {location} and want to understand what types of trail surfaces I can expect.

        Please analyze the trail surfaces in {location} by:

        1. Getting trail statistics to see surface type distribution
        2. Finding specific trails and their surface descriptions
        3. Identifying which surfaces are most common
        4. Highlighting any unique or special surface types
        5. Providing recommendations based on surface preferences

        Use the get_trail_statistics tool for "{location}" and focus on the surface type breakdown.
        Then use search_trails_by_area_name to get specific trail details.
    """)


@mcp.prompt()
def beginner_trail_recommendations(location: str) -> str:
    """Generate a prompt for beginner trail recommendations."""
    return textwrap.dedent(f"""
        I'm new to outdoor activities and looking for beginner-friendly trails in {location}.

        Please help me find:

        1. Easy hiking trails suitable for beginners
        2. Well-maintained paths with good signage
        3. Trails with gentle elevation changes
        4. Popular and frequently used trails (safety in numbers)
        5. Trails with good access and parking

        Use search_trails_by_area_name with "{location}" and focus on hiking trails.
        Look for trails with descriptions mentioning "easy", "beginner", "family-friendly", or similar terms.
    """)


@mcp.prompt()
def advanced_trail_challenge(location: str, activity: str) -> str:
    """Generate a prompt for advanced trail challenges."""
    return textwrap.dedent(f"""
        I'm an experienced {activity} enthusiast looking for challenging trails in {location}.

        Please help me find:

        1. Difficult and technical {activity} trails
        2. Trails with significant elevation gain
        3. Less-maintained or backcountry options
        4. Trails with advanced features (rocky terrain, steep climbs, etc.)
        5. Trails that offer a real challenge

        Use search_trails_by_area_name with "{location}" and filter for "{activity}" trails.
        Look for trails with descriptions mentioning "difficult", "challenging", "technical", or similar terms.
    """)


@mcp.prompt()
def family_trail_outing(location: str) -> str:
    """Generate a prompt for family trail outings."""
    return textwrap.dedent(f"""
        I'm planning a family outing in {location} and need trails suitable for all ages.

        Please help me find:

        1. Family-friendly trails with easy access
        2. Trails with interesting features for children
        3. Well-maintained paths with good safety features
        4. Trails with picnic areas or rest spots
        5. Options for different family members' abilities

        Use search_trails_by_area_name with "{location}" and focus on walking and easy hiking trails.
        Look for trails near parks, playgrounds, or with family-oriented descriptions.
    """)


@mcp.prompt()
def seasonal_trail_planning(location: str, season: str) -> str:
    """Generate a prompt for seasonal trail planning."""
    return textwrap.dedent(f"""
        I'm planning a {season} visit to {location} and want to know what trails are best for this season.

        Please help me understand:

        1. Which trails are accessible during {season}
        2. Seasonal considerations (weather, conditions, closures)
        3. Best trail types for {season} activities
        4. Any seasonal highlights or features
        5. Safety considerations for {season} hiking

        Use search_trails_by_area_name with "{location}" to get current trail information.
        Consider seasonal factors like weather, accessibility, and trail conditions.
    """)


@mcp.prompt()
def trail_accessibility_analysis(location: str) -> str:
    """Generate a prompt for trail accessibility analysis."""
    return textwrap.dedent(f"""
        I'm looking for accessible trails in {location} that accommodate different mobility needs.

        Please help me find:

        1. Trails with paved or smooth surfaces
        2. Trails with minimal elevation changes
        3. Trails with good accessibility features
        4. Trails suitable for wheelchairs or mobility aids
        5. Trails with nearby parking and facilities

        Use search_trails_by_area_name with "{location}" and focus on walking trails.
        Look for trails with descriptions mentioning "accessible", "paved", "smooth", or similar terms.
    """)


@mcp.prompt()
def multi_activity_trail_planning(location: str) -> str:
    """Generate a prompt for multi-activity trail planning."""
    return textwrap.dedent(f"""
        I'm planning a trip to {location} and want to experience different types of trail activities.

        Please help me plan:

        1. A mix of hiking, biking, and walking trails
        2. Trails suitable for different skill levels
        3. Trails that showcase the area's diversity
        4. Options for both solo and group activities
        5. Trails with different scenic highlights

        Use search_trails_by_area_name with "{location}" for different trail types.
        Also use get_trail_statistics to understand the variety of trails available in the area.
    """)


if __name__ == "__main__":
    mcp.run()
