"""
Server-side caching module for GrowSense API.

Provides in-memory caching of user device readings to reduce Firestore reads.
The cache is populated when devices upload data and served when users request data.
"""

from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, List, Optional, Any


class ReadingsCache:
    """
    Thread-safe in-memory cache for user device readings.
    
    Structure:
        _cache = {
            user_id: {
                device_id: [reading1, reading2, ...],  # Most recent readings
                ...
            }
        }
        _metadata = {
            user_id: {
                'devices': [...],  # Device metadata
                'cached_at': datetime,
                'ttl_expires': datetime
            }
        }
    """
    
    def __init__(self, ttl_seconds=300, max_readings_per_device=200):
        """
        Initialize the cache.
        
        Args:
            ttl_seconds: Time-to-live for cache entries (default: 300 = 5 minutes)
            max_readings_per_device: Maximum number of readings to cache per device
        """
        self._cache: Dict[str, Dict[str, List[Dict]]] = {}
        self._metadata: Dict[str, Dict] = {}
        self._lock = Lock()
        self.ttl_seconds = ttl_seconds
        self.max_readings_per_device = max_readings_per_device
    
    def get(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached data for a user.
        
        Args:
            user_id: Firebase user ID
            
        Returns:
            Dictionary with 'devices', 'readings', 'cached_at' if cache hit,
            None if cache miss or expired
        """
        with self._lock:
            if user_id not in self._metadata:
                return None
            
            meta = self._metadata[user_id]
            age = datetime.utcnow() - meta['cached_at']
            
            if age.total_seconds() > self.ttl_seconds:
                # Cache expired
                self._invalidate(user_id)
                return None
            
            return {
                'devices': meta.get('devices', []),
                'readings_by_device': self._cache.get(user_id, {}),
                'cached_at': meta['cached_at']
            }
    
    def set(self, user_id: str, devices: List[Dict], readings_by_device: Dict[str, List[Dict]]):
        """
        Cache data for a user.
        
        Args:
            user_id: Firebase user ID
            devices: List of device metadata dictionaries
            readings_by_device: Dictionary mapping device_id to list of readings
        """
        with self._lock:
            # Limit readings per device to prevent memory bloat
            limited_readings = {}
            for device_id, readings in readings_by_device.items():
                limited_readings[device_id] = readings[:self.max_readings_per_device]
            
            self._cache[user_id] = limited_readings
            self._metadata[user_id] = {
                'devices': devices,
                'cached_at': datetime.utcnow(),
                'ttl_expires': datetime.utcnow() + timedelta(seconds=self.ttl_seconds)
            }
    
    def update_reading(self, user_id: str, device_id: str, reading: Dict):
        """
        Add a single new reading to cache (called on device upload).
        This keeps the cache fresh as new data arrives.
        
        Args:
            user_id: Firebase user ID
            device_id: Device identifier
            reading: Reading data dictionary
        """
        with self._lock:
            if user_id not in self._cache:
                # No cache for this user yet - will be populated on first request
                return
            
            if device_id not in self._cache[user_id]:
                self._cache[user_id][device_id] = []
            
            # Add to front (newest first)
            self._cache[user_id][device_id].insert(0, reading)
            
            # Keep only recent N readings
            self._cache[user_id][device_id] = self._cache[user_id][device_id][:self.max_readings_per_device]
            
            # Don't update cached_at timestamp - we want TTL to expire based on full refresh
    
    def invalidate(self, user_id: str):
        """
        Public method to invalidate cache for a user.
        
        Args:
            user_id: Firebase user ID
        """
        with self._lock:
            self._invalidate(user_id)
    
    def _invalidate(self, user_id: str):
        """
        Remove user from cache (internal method, assumes lock is held).
        
        Args:
            user_id: Firebase user ID
        """
        self._cache.pop(user_id, None)
        self._metadata.pop(user_id, None)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics for monitoring.
        
        Returns:
            Dictionary with cache statistics
        """
        with self._lock:
            total_readings = 0
            for user_cache in self._cache.values():
                for device_readings in user_cache.values():
                    total_readings += len(device_readings)
            
            return {
                'cached_users': len(self._cache),
                'total_readings': total_readings,
                'ttl_seconds': self.ttl_seconds,
                'max_readings_per_device': self.max_readings_per_device
            }


# Global singleton instance
readings_cache = ReadingsCache(ttl_seconds=300, max_readings_per_device=200)

