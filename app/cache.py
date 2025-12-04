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
            Dictionary with 'devices', 'readings_by_device', 'analysis_history', 'cached_at' if cache hit,
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
                'analysis_history': meta.get('analysis_history', []),  # Last 3 analyses
                'cached_at': meta['cached_at']
            }
    
    def set(self, user_id: str, devices: List[Dict], readings_by_device: Dict[str, Any], analysis_history: Optional[List[Dict]] = None):
        """
        Cache data for a user.
        
        Args:
            user_id: Firebase user ID
            devices: List of device metadata dictionaries
            readings_by_device: Dictionary mapping device_id to list of readings OR dict with recent/historic
            analysis_history: Optional list of previous analyses (last 3) for this user
        """
        with self._lock:
            # Limit readings per device to prevent memory bloat
            limited_readings = {}
            for device_id, readings in readings_by_device.items():
                if isinstance(readings, dict):
                    # Handle new structure {recent: [], historic: []}
                    rec = readings.get('recent', [])[:self.max_readings_per_device]
                    hist = readings.get('historic', [])[:self.max_readings_per_device]
                    limited_readings[device_id] = {'recent': rec, 'historic': hist}
                else:
                    # Legacy list structure
                    limited_readings[device_id] = readings[:self.max_readings_per_device]
            
            self._cache[user_id] = limited_readings
            self._metadata[user_id] = {
                'devices': devices,
                'analysis_history': analysis_history or [],  # Store last 3 analyses
                'cached_at': datetime.utcnow(),
                'ttl_expires': datetime.utcnow() + timedelta(seconds=self.ttl_seconds)
            }
    
    def update_reading(self, user_id: str, device_id: str, reading: Dict):
        """
        Add a single new reading to cache (called on device upload).
        This keeps the cache fresh as new data arrives.
        Initializes cache if it doesn't exist yet.
        
        Args:
            user_id: Firebase user ID
            device_id: Device identifier
            reading: Reading data dictionary
        """
        with self._lock:
            # Initialize cache structure if it doesn't exist
            if user_id not in self._cache:
                self._cache[user_id] = {}
            
            # Initialize metadata if it doesn't exist
            if user_id not in self._metadata:
                self._metadata[user_id] = {
                    'devices': [],  # Will be populated when device metadata is available
                    'analysis_history': [],  # Will be populated when advice is generated
                    'cached_at': datetime.utcnow(),
                    'ttl_expires': datetime.utcnow() + timedelta(seconds=self.ttl_seconds)
                }
            
            # Initialize device readings structure if not present
            if device_id not in self._cache[user_id]:
                # Use new structure: {recent: [], historic: []}
                self._cache[user_id][device_id] = {'recent': [], 'historic': []}
            
            cached_data = self._cache[user_id][device_id]
            
            if isinstance(cached_data, dict):
                # New structure: add to 'recent'
                if 'recent' not in cached_data:
                    cached_data['recent'] = []
                
                cached_data['recent'].insert(0, reading)
                cached_data['recent'] = cached_data['recent'][:self.max_readings_per_device]
            else:
                # Legacy list structure - convert to new structure
                legacy_readings = cached_data[:self.max_readings_per_device]
                self._cache[user_id][device_id] = {'recent': legacy_readings, 'historic': []}
                # Add new reading
                self._cache[user_id][device_id]['recent'].insert(0, reading)
                self._cache[user_id][device_id]['recent'] = self._cache[user_id][device_id]['recent'][:self.max_readings_per_device]
            
            # Don't update cached_at timestamp - we want TTL to expire based on full refresh
    
    def update_device_metadata(self, user_id: str, device_id: str, device_data: Dict):
        """
        Update device metadata in cache (called when device uploads data).
        This ensures device descriptions and other metadata are available for Gemini prompts.
        
        Args:
            user_id: Firebase user ID
            device_id: Device identifier
            device_data: Device metadata dictionary (from Firestore device document)
        """
        with self._lock:
            # Initialize metadata if it doesn't exist
            if user_id not in self._metadata:
                self._metadata[user_id] = {
                    'devices': [],
                    'analysis_history': [],
                    'cached_at': datetime.utcnow(),
                    'ttl_expires': datetime.utcnow() + timedelta(seconds=self.ttl_seconds)
                }
            
            # Add device_id to device_data if not present
            device_with_id = device_data.copy()
            device_with_id['device_id'] = device_id
            
            # Update or add device in devices list
            devices = self._metadata[user_id].get('devices', [])
            # Check if device already exists
            device_index = None
            for i, dev in enumerate(devices):
                if dev.get('device_id') == device_id:
                    device_index = i
                    break
            
            if device_index is not None:
                # Update existing device
                devices[device_index] = device_with_id
            else:
                # Add new device
                devices.append(device_with_id)
            
            self._metadata[user_id]['devices'] = devices
    
    def update_analysis_history(self, user_id: str, analysis_history: List[Dict]):
        """
        Update analysis history for a user in cache.
        This allows analysis history to be added/updated without repopulating entire cache.
        
        Args:
            user_id: Firebase user ID
            analysis_history: List of analysis dictionaries (last 3)
        """
        with self._lock:
            if user_id not in self._metadata:
                # Cache doesn't exist for this user yet - can't update history
                return
            
            # Update analysis history in metadata
            self._metadata[user_id]['analysis_history'] = analysis_history[:3]  # Only store last 3
    
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
# Very long TTL since client-side localStorage is the primary cache
# Server cache is only for Gemini AI and device upload updates
# IMPORTANT: 24 hour TTL must be maintained to minimize database operations - do not shorten this
readings_cache = ReadingsCache(ttl_seconds=86400, max_readings_per_device=200)  # 24 hours - DO NOT SHORTEN

