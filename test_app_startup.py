#!/usr/bin/env python3
"""
Test that the Flask app can start successfully with new caching code.
"""

import sys
import os

def test_app_imports():
    """Test that all modules can be imported without errors."""
    try:
        # Test cache module
        from app.cache import ReadingsCache, readings_cache
        print("✓ Cache module imported successfully")
        
        # Test firebase_client with new function
        from app.firebase_client import get_user_device_readings_since
        print("✓ Firebase client with incremental fetch imported successfully")
        
        # Test routes with cache integration
        from app.routes import flatten_cached_readings, organize_readings_by_device
        print("✓ Route helper functions imported successfully")
        
        # Test that cache singleton exists
        assert readings_cache is not None
        assert isinstance(readings_cache, ReadingsCache)
        print("✓ Cache singleton initialized correctly")
        
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_flask_app_creation():
    """Test that Flask app can be created with all blueprints."""
    try:
        from app import create_app
        app = create_app()
        
        # Check that routes are registered
        rules = [str(rule) for rule in app.url_map.iter_rules()]
        
        required_routes = [
            '/user_data',
            '/upload_data',
            '/devices/register'
        ]
        
        for route in required_routes:
            if route in rules:
                print(f"✓ Route {route} registered")
            else:
                print(f"✗ Route {route} NOT found")
                return False
        
        print("✓ Flask app created successfully with all routes")
        return True
        
    except Exception as e:
        print(f"✗ Flask app creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all startup tests."""
    print("=" * 60)
    print("GrowSense App Startup Tests")
    print("=" * 60)
    
    all_passed = True
    
    print("\n[Test 1] Module Imports")
    print("-" * 60)
    if not test_app_imports():
        all_passed = False
    
    print("\n[Test 2] Flask App Creation")
    print("-" * 60)
    if not test_flask_app_creation():
        all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL TESTS PASSED - App is ready for deployment!")
        print("=" * 60)
        return 0
    else:
        print("✗ SOME TESTS FAILED - Fix issues before deploying")
        print("=" * 60)
        return 1


if __name__ == '__main__':
    sys.exit(main())

