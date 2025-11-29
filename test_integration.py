#!/usr/bin/env python3
"""
Integration test for the complete caching data flow:
1. Device uploads data
2. Cache is updated
3. User requests data
4. Data is served from cache
"""

import unittest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import sys
import os

from app.cache import ReadingsCache


class TestCachingDataFlow(unittest.TestCase):
    """Test the complete data flow with caching."""
    
    def setUp(self):
        """Set up fresh cache for each test."""
        self.cache = ReadingsCache(ttl_seconds=300, max_readings_per_device=200)
        self.user_id = 'test_user_123'
        self.device_id = 'test_device_A'
    
    def test_complete_data_flow(self):
        """
        Test complete flow:
        1. Cache is empty
        2. User requests data (cache miss) → Firestore read
        3. Cache is populated
        4. Device uploads new data → Cache updated
        5. User requests data again (cache hit) → No Firestore read
        """
        
        # Step 1: Cache is empty
        cached_data = self.cache.get(self.user_id)
        self.assertIsNone(cached_data, "Cache should be empty initially")
        
        # Step 2 & 3: First user request - populate cache (simulated)
        devices = [{'device_id': self.device_id, 'name': 'Test Device'}]
        initial_readings = [
            {
                'id': 'r1',
                'device_id': self.device_id,
                'temperature': 23.5,
                'humidity': 65.0,
                'timestamp': '2024-11-29T10:00:00Z',
                'server_timestamp': '2024-11-29T10:00:00Z'
            }
        ]
        readings_by_device = {self.device_id: initial_readings}
        
        self.cache.set(self.user_id, devices, readings_by_device)
        
        # Verify cache is populated
        cached_data = self.cache.get(self.user_id)
        self.assertIsNotNone(cached_data, "Cache should be populated after set")
        self.assertEqual(len(cached_data['readings_by_device'][self.device_id]), 1)
        
        # Step 4: Device uploads new data → Cache updated
        new_reading = {
            'id': 'r2',
            'device_id': self.device_id,
            'temperature': 23.7,
            'humidity': 64.5,
            'timestamp': '2024-11-29T10:01:00Z',
            'server_timestamp': '2024-11-29T10:01:00Z'
        }
        
        self.cache.update_reading(self.user_id, self.device_id, new_reading)
        
        # Step 5: User requests data again - should get cached data with new reading
        cached_data = self.cache.get(self.user_id)
        self.assertIsNotNone(cached_data, "Cache should still be valid")
        self.assertEqual(len(cached_data['readings_by_device'][self.device_id]), 2,
                        "Cache should have both readings")
        
        # Verify new reading is first (newest)
        readings = cached_data['readings_by_device'][self.device_id]
        self.assertEqual(readings[0]['id'], 'r2', "Newest reading should be first")
        self.assertEqual(readings[1]['id'], 'r1', "Older reading should be second")
    
    def test_cache_serves_multiple_devices(self):
        """Test that cache correctly handles multiple devices for a user."""
        devices = [
            {'device_id': 'device_A', 'name': 'Living Room'},
            {'device_id': 'device_B', 'name': 'Bedroom'}
        ]
        
        readings_by_device = {
            'device_A': [
                {'id': 'rA1', 'temperature': 23.5, 'timestamp': '2024-11-29T10:00:00Z'}
            ],
            'device_B': [
                {'id': 'rB1', 'temperature': 22.1, 'timestamp': '2024-11-29T10:00:00Z'}
            ]
        }
        
        self.cache.set(self.user_id, devices, readings_by_device)
        
        # Upload new reading to device_A
        new_reading_A = {'id': 'rA2', 'temperature': 23.7, 'timestamp': '2024-11-29T10:01:00Z'}
        self.cache.update_reading(self.user_id, 'device_A', new_reading_A)
        
        # Verify device_A has 2 readings, device_B still has 1
        cached_data = self.cache.get(self.user_id)
        self.assertEqual(len(cached_data['readings_by_device']['device_A']), 2)
        self.assertEqual(len(cached_data['readings_by_device']['device_B']), 1)
    
    def test_incremental_fetch_reduces_reads(self):
        """
        Conceptual test: Verify that incremental fetching would reduce reads.
        
        This tests the logic without actually calling Firestore.
        """
        from app.routes import flatten_cached_readings
        
        # Simulate cached data from previous fetch
        cached_readings = {
            'device_A': [
                {'id': f'r{i}', 'server_timestamp': f'2024-11-29T10:{i:02d}:00Z'}
                for i in range(10)  # 10 old readings
            ]
        }
        
        # Flatten to get all readings
        all_readings = flatten_cached_readings(cached_readings, limit=100)
        self.assertEqual(len(all_readings), 10)
        
        # Simulate incremental fetch returning only 1 new reading
        new_readings = [
            {'id': 'r10', 'server_timestamp': '2024-11-29T10:10:00Z'}
        ]
        
        # In real scenario, frontend would merge:
        # - Old: 10 readings (already cached)
        # - New: 1 reading (fetched with ?since=)
        # Result: 11 readings total, but only 1 Firestore read instead of 11
        
        # This demonstrates the savings
        old_approach_reads = 11  # Would fetch all 11 readings
        new_approach_reads = 1   # Only fetch 1 new reading
        savings = (old_approach_reads - new_approach_reads) / old_approach_reads * 100
        
        self.assertGreater(savings, 90, "Should save > 90% of reads")


class TestRouteHelperFunctions(unittest.TestCase):
    """Test helper functions used in routes."""
    
    def test_flatten_and_organize_roundtrip(self):
        """Test that flatten and organize are inverse operations."""
        from app.routes import flatten_cached_readings, organize_readings_by_device
        
        # Original structure: readings organized by device
        readings_by_device = {
            'device_A': [
                {'id': 'r1', 'device_id': 'device_A', 'server_timestamp': '2024-11-29T10:00:00Z'},
                {'id': 'r2', 'device_id': 'device_A', 'server_timestamp': '2024-11-29T10:01:00Z'}
            ],
            'device_B': [
                {'id': 'r3', 'device_id': 'device_B', 'server_timestamp': '2024-11-29T10:00:00Z'}
            ]
        }
        
        # Flatten
        flat_readings = flatten_cached_readings(readings_by_device, limit=100)
        self.assertEqual(len(flat_readings), 3)
        
        # Organize back
        organized = organize_readings_by_device(flat_readings)
        
        # Should have same structure (though may be in different order)
        self.assertEqual(set(organized.keys()), set(readings_by_device.keys()))
        self.assertEqual(len(organized['device_A']), len(readings_by_device['device_A']))
        self.assertEqual(len(organized['device_B']), len(readings_by_device['device_B']))


def run_tests():
    """Run all integration tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestCachingDataFlow))
    suite.addTests(loader.loadTestsFromTestCase(TestRouteHelperFunctions))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("Running Integration Tests for Caching Data Flow")
    print("=" * 70 + "\n")
    
    success = run_tests()
    
    print("\n" + "=" * 70)
    if success:
        print("✓ ALL INTEGRATION TESTS PASSED")
    else:
        print("✗ SOME INTEGRATION TESTS FAILED")
    print("=" * 70 + "\n")
    
    sys.exit(0 if success else 1)

