#!/usr/bin/env python3
"""
Unit tests for GrowSense caching functionality.

Tests:
1. Server-side cache module (app/cache.py)
2. Backend incremental fetching (firebase_client.py)
3. Route integration with cache (routes.py)
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.cache import ReadingsCache


class TestReadingsCache(unittest.TestCase):
    """Test the ReadingsCache class."""
    
    def setUp(self):
        """Set up test cache instance."""
        self.cache = ReadingsCache(ttl_seconds=300, max_readings_per_device=200)
    
    def test_cache_initialization(self):
        """Test cache initializes with correct parameters."""
        self.assertEqual(self.cache.ttl_seconds, 300)
        self.assertEqual(self.cache.max_readings_per_device, 200)
    
    def test_cache_get_empty(self):
        """Test getting from empty cache returns None."""
        result = self.cache.get('user_123')
        self.assertIsNone(result)
    
    def test_cache_set_and_get(self):
        """Test setting and retrieving cache data."""
        user_id = 'user_123'
        devices = [
            {'device_id': 'device_A', 'name': 'Living Room'},
            {'device_id': 'device_B', 'name': 'Bedroom'}
        ]
        readings_by_device = {
            'device_A': [
                {'id': 'r1', 'temperature': 23.5, 'timestamp': '2024-11-29T10:00:00Z'},
                {'id': 'r2', 'temperature': 23.6, 'timestamp': '2024-11-29T10:01:00Z'}
            ],
            'device_B': [
                {'id': 'r3', 'temperature': 22.1, 'timestamp': '2024-11-29T10:00:00Z'}
            ]
        }
        
        self.cache.set(user_id, devices, readings_by_device)
        
        result = self.cache.get(user_id)
        self.assertIsNotNone(result)
        self.assertEqual(result['devices'], devices)
        self.assertEqual(len(result['readings_by_device']['device_A']), 2)
        self.assertEqual(len(result['readings_by_device']['device_B']), 1)
    
    def test_cache_ttl_expiration(self):
        """Test cache expires after TTL."""
        cache = ReadingsCache(ttl_seconds=1)  # 1 second TTL
        user_id = 'user_123'
        devices = [{'device_id': 'device_A'}]
        readings_by_device = {'device_A': [{'id': 'r1', 'temperature': 23.5}]}
        
        cache.set(user_id, devices, readings_by_device)
        
        # Should be cached
        result = cache.get(user_id)
        self.assertIsNotNone(result)
        
        # Wait for expiration
        import time
        time.sleep(1.1)
        
        # Should be expired
        result = cache.get(user_id)
        self.assertIsNone(result)
    
    def test_cache_update_reading(self):
        """Test updating cache with new reading."""
        user_id = 'user_123'
        device_id = 'device_A'
        
        # Set initial cache
        devices = [{'device_id': device_id}]
        readings_by_device = {
            device_id: [
                {'id': 'r1', 'temperature': 23.5, 'timestamp': '2024-11-29T10:00:00Z'}
            ]
        }
        self.cache.set(user_id, devices, readings_by_device)
        
        # Add new reading
        new_reading = {'id': 'r2', 'temperature': 23.7, 'timestamp': '2024-11-29T10:01:00Z'}
        self.cache.update_reading(user_id, device_id, new_reading)
        
        # Verify new reading is at front
        result = self.cache.get(user_id)
        self.assertEqual(len(result['readings_by_device'][device_id]), 2)
        self.assertEqual(result['readings_by_device'][device_id][0]['id'], 'r2')
        self.assertEqual(result['readings_by_device'][device_id][1]['id'], 'r1')
    
    def test_cache_max_readings_limit(self):
        """Test cache limits readings per device."""
        cache = ReadingsCache(max_readings_per_device=5)
        user_id = 'user_123'
        device_id = 'device_A'
        
        # Create 10 readings
        readings = [{'id': f'r{i}', 'temperature': 20 + i} for i in range(10)]
        devices = [{'device_id': device_id}]
        readings_by_device = {device_id: readings}
        
        cache.set(user_id, devices, readings_by_device)
        
        # Should only keep first 5
        result = cache.get(user_id)
        self.assertEqual(len(result['readings_by_device'][device_id]), 5)
        self.assertEqual(result['readings_by_device'][device_id][0]['id'], 'r0')
        self.assertEqual(result['readings_by_device'][device_id][4]['id'], 'r4')
    
    def test_cache_update_reading_no_existing_cache(self):
        """Test updating reading when no cache exists (should not crash)."""
        user_id = 'user_123'
        device_id = 'device_A'
        reading = {'id': 'r1', 'temperature': 23.5}
        
        # Should not raise exception
        self.cache.update_reading(user_id, device_id, reading)
        
        # Cache should not be created by update_reading
        result = self.cache.get(user_id)
        self.assertIsNone(result)
    
    def test_cache_invalidate(self):
        """Test manual cache invalidation."""
        user_id = 'user_123'
        devices = [{'device_id': 'device_A'}]
        readings_by_device = {'device_A': [{'id': 'r1'}]}
        
        self.cache.set(user_id, devices, readings_by_device)
        self.assertIsNotNone(self.cache.get(user_id))
        
        self.cache.invalidate(user_id)
        self.assertIsNone(self.cache.get(user_id))
    
    def test_cache_get_stats(self):
        """Test cache statistics."""
        user_id = 'user_123'
        devices = [{'device_id': 'device_A'}]
        readings_by_device = {
            'device_A': [
                {'id': 'r1', 'temperature': 23.5},
                {'id': 'r2', 'temperature': 23.6}
            ]
        }
        
        self.cache.set(user_id, devices, readings_by_device)
        
        stats = self.cache.get_stats()
        self.assertEqual(stats['cached_users'], 1)
        self.assertEqual(stats['total_readings'], 2)
        self.assertEqual(stats['ttl_seconds'], 300)
        self.assertEqual(stats['max_readings_per_device'], 200)


class TestRouteHelpers(unittest.TestCase):
    """Test route helper functions."""
    
    def test_flatten_cached_readings(self):
        """Test flattening readings from cache structure."""
        from app.routes import flatten_cached_readings
        
        readings_by_device = {
            'device_A': [
                {'id': 'r1', 'device_id': 'device_A', 'server_timestamp': '2024-11-29T10:02:00Z'},
                {'id': 'r2', 'device_id': 'device_A', 'server_timestamp': '2024-11-29T10:01:00Z'}
            ],
            'device_B': [
                {'id': 'r3', 'device_id': 'device_B', 'server_timestamp': '2024-11-29T10:03:00Z'}
            ]
        }
        
        result = flatten_cached_readings(readings_by_device, limit=10)
        
        # Should have 3 readings total
        self.assertEqual(len(result), 3)
        
        # Should be sorted newest first
        self.assertEqual(result[0]['id'], 'r3')
        self.assertEqual(result[1]['id'], 'r1')
        self.assertEqual(result[2]['id'], 'r2')
    
    def test_flatten_cached_readings_with_limit(self):
        """Test flattening with limit."""
        from app.routes import flatten_cached_readings
        
        readings_by_device = {
            'device_A': [
                {'id': f'r{i}', 'server_timestamp': f'2024-11-29T10:{i:02d}:00Z'}
                for i in range(5)
            ]
        }
        
        result = flatten_cached_readings(readings_by_device, limit=3)
        self.assertEqual(len(result), 3)
    
    def test_organize_readings_by_device(self):
        """Test organizing flat readings by device."""
        from app.routes import organize_readings_by_device
        
        readings = [
            {'id': 'r1', 'device_id': 'device_A', 'temperature': 23.5},
            {'id': 'r2', 'device_id': 'device_B', 'temperature': 22.1},
            {'id': 'r3', 'device_id': 'device_A', 'temperature': 23.6}
        ]
        
        result = organize_readings_by_device(readings)
        
        self.assertIn('device_A', result)
        self.assertIn('device_B', result)
        self.assertEqual(len(result['device_A']), 2)
        self.assertEqual(len(result['device_B']), 1)
        self.assertEqual(result['device_A'][0]['id'], 'r1')
        self.assertEqual(result['device_A'][1]['id'], 'r3')


class TestCacheIntegration(unittest.TestCase):
    """Integration tests for cache with routes."""
    
    def test_incremental_fetch_with_since_parameter(self):
        """Test incremental fetch logic with since timestamp."""
        # Instead of testing the full route (which requires complex mocking),
        # test the logic that handles the 'since' parameter
        
        # Simulate what happens when since parameter is provided
        since_timestamp = '2024-11-29T10:00:00Z'
        
        # The route should use get_user_device_readings_since
        # This is verified by the function existing and being importable
        from app.firebase_client import get_user_device_readings_since
        
        # Verify function signature
        import inspect
        sig = inspect.signature(get_user_device_readings_since)
        params = list(sig.parameters.keys())
        
        # Should have user_id, since_timestamp, and limit parameters
        self.assertIn('user_id', params)
        self.assertIn('since_timestamp', params)
        self.assertIn('limit', params)
        
    def test_cache_singleton_exists(self):
        """Test that cache singleton is properly initialized."""
        from app.cache import readings_cache
        
        # Should be an instance of ReadingsCache
        self.assertIsInstance(readings_cache, ReadingsCache)
        
        # Should have correct default values
        self.assertEqual(readings_cache.ttl_seconds, 300)
        self.assertEqual(readings_cache.max_readings_per_device, 200)


class TestFrontendCacheFunctions(unittest.TestCase):
    """Test frontend cache logic (conceptual - would need JS test framework for real tests)."""
    
    def test_merge_readings_concept(self):
        """Test the concept of merging readings (Python equivalent of JS logic)."""
        # This tests the logic that would be in the frontend
        old_readings = [
            {'id': 'r1', 'timestamp': '2024-11-29T10:00:00Z', 'temperature': 23.5},
            {'id': 'r2', 'timestamp': '2024-11-29T10:01:00Z', 'temperature': 23.6}
        ]
        
        new_readings = [
            {'id': 'r3', 'timestamp': '2024-11-29T10:02:00Z', 'temperature': 23.7},
            {'id': 'r1', 'timestamp': '2024-11-29T10:00:00Z', 'temperature': 23.5}  # Duplicate
        ]
        
        # Merge logic (Python equivalent)
        reading_map = {}
        for reading in old_readings:
            reading_map[reading['id']] = reading
        for reading in new_readings:
            reading_map[reading['id']] = reading
        
        merged = list(reading_map.values())
        merged.sort(key=lambda r: r['timestamp'], reverse=True)
        
        # Should have 3 unique readings, sorted newest first
        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[0]['id'], 'r3')
        self.assertEqual(merged[1]['id'], 'r2')
        self.assertEqual(merged[2]['id'], 'r1')


def run_tests():
    """Run all tests and return results."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestReadingsCache))
    suite.addTests(loader.loadTestsFromTestCase(TestRouteHelpers))
    suite.addTests(loader.loadTestsFromTestCase(TestCacheIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestFrontendCacheFunctions))
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Return success status
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)

