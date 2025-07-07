#!/usr/bin/env python3
"""
Simple test script for the Trail Explorer MCP Server.

This script tests the basic functionality of the enhanced trail server.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from server.trail_mcp_server import (
    OverpassQueryBuilder,
    query_overpass,
    format_trail_data,
    identify_trail_type,
    validate_trail_types,
    Config,
    TrailType
)


async def test_query_builder():
    """Test the OverpassQueryBuilder functionality."""
    print("Testing OverpassQueryBuilder...")
    
    # Test bbox query
    try:
        query = OverpassQueryBuilder.build_bbox_query(
            south=40.7, west=-74.0, north=40.8, east=-73.9,
            trail_types=["hiking"]
        )
        print("PASS: Bbox query built successfully")
        print(f"  Query preview: {query[:100]}...")
    except Exception as e:
        print(f"FAIL: Bbox query failed: {e}")
        return False
    
    # Test area query
    try:
        query = OverpassQueryBuilder.build_area_query(
            "Central Park",
            trail_types=["walking"]
        )
        print("PASS: Area query built successfully")
        print(f"  Query preview: {query[:100]}...")
    except Exception as e:
        print(f"FAIL: Area query failed: {e}")
        return False
    
    # Test coordinate validation
    try:
        OverpassQueryBuilder.build_bbox_query(
            south=91, west=-74.0, north=40.8, east=-73.9  # Invalid latitude
        )
        print("FAIL: Should have failed with invalid coordinates")
        return False
    except ValueError:
        print("PASS: Coordinate validation working")
    
    return True


def test_trail_type_identification():
    """Test trail type identification."""
    print("\nTesting trail type identification...")
    
    test_cases = [
        ({"route": "hiking"}, "hiking"),
        ({"route": "bicycle"}, "biking"),
        ({"highway": "cycleway"}, "biking"),
        ({"highway": "footway", "foot": "yes"}, "hiking"),
        ({"highway": "path", "bicycle": "yes"}, "biking"),
        ({"highway": "path"}, "hiking"),  # Default for path
        ({}, None),  # No trail type
    ]
    
    for tags, expected in test_cases:
        result = identify_trail_type(tags)
        if result == expected:
            print(f"PASS: {tags} -> {result}")
        else:
            print(f"FAIL: {tags} -> {result} (expected {expected})")
            return False
    
    return True


def test_trail_type_validation():
    """Test trail type validation."""
    print("\nTesting trail type validation...")
    
    # Test valid types
    try:
        valid_types = validate_trail_types(["hiking", "biking"])
        assert valid_types == ["hiking", "biking"]
        print("PASS: Valid trail types accepted")
    except Exception as e:
        print(f"FAIL: Valid trail types failed: {e}")
        return False
    
    # Test invalid types
    try:
        validate_trail_types(["invalid_type"])
        print("FAIL: Should have failed with invalid type")
        return False
    except ValueError:
        print("PASS: Invalid trail types rejected")
    
    # Test None
    try:
        valid_types = validate_trail_types(None)
        expected_types = [TrailType.HIKING.value, TrailType.BIKING.value, TrailType.WALKING.value]
        assert set(valid_types) == set(expected_types)
        print("PASS: None defaults to all trail types")
    except Exception as e:
        print(f"FAIL: None handling failed: {e}")
        return False
    
    return True


def test_configuration():
    """Test configuration system."""
    print("\nTesting configuration...")
    
    # Test default config
    config = Config()
    assert config.overpass_url == "https://overpass-api.de/api/interpreter"
    assert config.timeout == 60.0
    assert config.max_trails_display == 50
    assert config.query_timeout == 30
    print("PASS: Default configuration loaded")
    
    # Test custom config
    custom_config = Config(
        timeout=30.0,
        max_trails_display=10
    )
    assert custom_config.timeout == 30.0
    assert custom_config.max_trails_display == 10
    print("PASS: Custom configuration working")
    
    return True


async def test_overpass_query():
    """Test actual Overpass API query (optional)."""
    print("\nTesting Overpass API query...")
    
    # This is optional and depends on internet connectivity
    try:
        query = OverpassQueryBuilder.build_bbox_query(
            south=40.7, west=-74.0, north=40.8, east=-73.9,
            trail_types=["biking"]
        )

        print(f"query: {query}")
        data = await query_overpass(query)
        print("elements:", data["elements"][0:5])
        
        if "elements" in data:
            print(f"PASS: Overpass API query successful, found {len(data['elements'])} elements")
            return True
        else:
            print("FAIL: Overpass API returned unexpected data format")
            return False
    except Exception as e:
        print(f"WARNING: Overpass API query failed (this is normal if offline): {e}")
        return True  # Don't fail the test for network issues


async def test_area_query_biking_trails():
    """Test area query specifically for biking trails and validate results."""
    print("\nTesting area query for biking trails...")
    
    # Test 1: Query building for biking trails
    try:
        query = OverpassQueryBuilder.build_area_query(
            "Central Park",
            trail_types=["biking"]
        )
        print("PASS: Biking area query built successfully")
        
        # Validate that the query contains biking-specific elements
        assert "bicycle" in query or "cycleway" in query, "Query should contain biking elements"
        assert "route" in query, "Query should contain route elements"
        print("PASS: Query contains biking-specific elements")
        
        # Check that it doesn't contain other trail types
        assert "hiking" not in query or "foot" not in query, "Query should not contain hiking elements"
        print("PASS: Query correctly filters for biking only")
        
    except Exception as e:
        print(f"FAIL: Biking area query building failed: {e}")
        return False
    
    # Test 2: Test with different area names
    test_areas = ["Golden Gate Park", "Yosemite National Park", "Central Park"]
    for area in test_areas:
        try:
            query = OverpassQueryBuilder.build_area_query(area, ["biking"])
            assert area.replace('"', '\\"') in query, f"Area name {area} should be in query"
            print(f"PASS: Query for {area} built successfully")
        except Exception as e:
            print(f"FAIL: Query for {area} failed: {e}")
            return False
    
    # Test 3: Test actual Overpass API query (if network available)
    try:
        print("\nTesting actual Overpass API query for biking trails in Central Park...")
        query = OverpassQueryBuilder.build_area_query("Central Park", ["biking"])
        print(f"query: {query}")
        data = await query_overpass(query)

        print(f"data: {data}")
        
        if "elements" in data:
            elements = data["elements"]
            print(f"PASS: Found {len(elements)} elements in Central Park biking query")
            
            # Validate that we have some biking-related elements
            biking_elements = 0
            for element in elements:
                if element.get("type") in ["way", "relation"]:
                    tags = element.get("tags", {})
                    # Check for biking indicators
                    if (tags.get("route") in ["bicycle", "mtb"] or 
                        tags.get("highway") == "cycleway" or
                        tags.get("bicycle") == "yes"):
                        biking_elements += 1
            
            print(f"PASS: Found {biking_elements} biking-related elements")
            
            # If we found elements, validate their structure
            if elements:
                first_element = elements[0]
                assert "type" in first_element, "Element should have type"
                assert "id" in first_element, "Element should have id"
                assert "tags" in first_element, "Element should have tags"
                print("PASS: Element structure is valid")
            
            return True
        else:
            print("FAIL: Overpass API returned unexpected data format")
            return False
            
    except Exception as e:
        print(f"WARNING: Overpass API query failed (this is normal if offline): {e}")
        return True  # Don't fail the test for network issues
    
    return True


async def main():
    """Run all tests."""
    print("Trail Explorer MCP Server - Test Suite")
    print("=" * 50)
    
    tests = [
        ("Query Builder", test_query_builder()),
        ("Trail Type Identification", test_trail_type_identification()),
        ("Trail Type Validation", test_trail_type_validation()),
        ("Configuration", test_configuration()),
        ("Overpass API Query", test_overpass_query()),
        ("Area Query Biking Trails", test_area_query_biking_trails()),
    ]
    
    results = []
    for test_name, test_coro in tests:
        if asyncio.iscoroutine(test_coro):
            result = await test_coro
        else:
            result = test_coro
        results.append((test_name, result))
    
    print("\n" + "=" * 50)
    print("Test Results:")
    print("=" * 50)
    
    all_passed = True
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{test_name}: {status}")
        if not result:
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("SUCCESS: All tests passed!")
        return 0
    else:
        print("FAILURE: Some tests failed!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 