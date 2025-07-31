"""Data availability checker service."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass

import asyncpg
import httpx
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import text

from ..config.models import DataCheckConfig, TaskStatus

logger = logging.getLogger(__name__)


@dataclass
class DataCheckResult:
    """Result of a data availability check."""
    success: bool
    message: str
    details: Dict[str, Any]
    checked_at: datetime
    data_source: str
    
    # Metrics
    record_count: Optional[int] = None
    freshness_minutes: Optional[int] = None  
    query_duration_ms: Optional[float] = None
    
    # Validation results
    count_validation_passed: Optional[bool] = None
    freshness_validation_passed: Optional[bool] = None
    
    @property
    def validation_passed(self) -> bool:
        """Overall validation status."""
        validations = [
            self.count_validation_passed,
            self.freshness_validation_passed
        ]
        # All non-None validations must pass
        return all(v for v in validations if v is not None)


class DataAvailabilityChecker:
    """Service for checking data availability and freshness."""
    
    def __init__(self):
        self.connections: Dict[str, Any] = {}
        self.connection_pools: Dict[str, Any] = {}
    
    async def register_connection(
        self,
        name: str,
        connection_config: Dict[str, Any]
    ) -> None:
        """Register a data source connection."""
        self.connections[name] = connection_config
        
        # Pre-create connection pools for database connections
        if connection_config.get('type') == 'postgresql':
            try:
                pool = await asyncpg.create_pool(
                    host=connection_config['host'],
                    port=connection_config.get('port', 5432),
                    database=connection_config['database'],
                    user=connection_config['username'],
                    password=connection_config['password'],
                    min_size=1,
                    max_size=5
                )
                self.connection_pools[name] = pool
                logger.info(f"Created connection pool for {name}")
            except Exception as e:
                logger.error(f"Failed to create connection pool for {name}: {e}")
    
    async def check_data_availability(
        self,
        config: DataCheckConfig
    ) -> DataCheckResult:
        """
        Check if data is available and meets requirements.
        
        Args:
            config: Data check configuration
            
        Returns:
            DataCheckResult with validation results
        """
        start_time = datetime.utcnow()
        
        try:
            if config.data_source not in self.connections:
                return DataCheckResult(
                    success=False,
                    message=f"Unknown data source: {config.data_source}",
                    details={'error': 'Data source not registered'},
                    checked_at=start_time,
                    data_source=config.data_source
                )
            
            connection_config = self.connections[config.data_source]
            connection_type = connection_config.get('type', 'unknown')
            
            if connection_type == 'postgresql':
                return await self._check_postgresql_data(config, connection_config, start_time)
            elif connection_type == 'http':
                return await self._check_http_data(config, connection_config, start_time)
            elif connection_type == 'file':
                return await self._check_file_data(config, connection_config, start_time)
            else:
                return DataCheckResult(
                    success=False,
                    message=f"Unsupported connection type: {connection_type}",
                    details={'connection_type': connection_type},
                    checked_at=start_time,
                    data_source=config.data_source
                )
                
        except Exception as e:
            logger.exception(f"Error checking data availability for {config.data_source}")
            return DataCheckResult(
                success=False,
                message=f"Data check failed: {str(e)}",
                details={'error': str(e), 'error_type': type(e).__name__},
                checked_at=start_time,
                data_source=config.data_source
            )
    
    async def _check_postgresql_data(
        self,
        config: DataCheckConfig,
        connection_config: Dict[str, Any],
        start_time: datetime
    ) -> DataCheckResult:
        """Check PostgreSQL data availability."""
        pool = self.connection_pools.get(config.data_source)
        if not pool:
            return DataCheckResult(
                success=False,
                message="No connection pool available for PostgreSQL source",
                details={'error': 'Connection pool not found'},
                checked_at=start_time,
                data_source=config.data_source
            )
        
        query_start = datetime.utcnow()
        
        try:
            async with pool.acquire() as conn:
                # Execute the query
                if config.query:
                    query = config.query
                else:
                    # Default query to check table existence and count
                    table_name = connection_config.get('default_table', 'data')
                    query = f"SELECT COUNT(*) FROM {table_name}"
                
                result = await conn.fetchrow(query)
                query_duration = (datetime.utcnow() - query_start).total_seconds() * 1000
                
                # Extract count (assume first column is count)
                record_count = int(result[0]) if result else 0
                
                # Check freshness if required
                freshness_minutes = None
                freshness_passed = True
                
                if config.freshness_hours:
                    freshness_query = config.query or f"""
                        SELECT EXTRACT(EPOCH FROM (NOW() - MAX(updated_at)))/60 as minutes_old
                        FROM {connection_config.get('default_table', 'data')}
                    """
                    
                    freshness_result = await conn.fetchrow(freshness_query.replace('COUNT(*)', 'MAX(updated_at)'))
                    if freshness_result and freshness_result[0]:
                        freshness_minutes = float(freshness_result[0])
                        freshness_passed = freshness_minutes <= (config.freshness_hours * 60)
                
                # Validate count requirements
                count_passed = True
                if config.expected_count_min is not None:
                    count_passed = count_passed and record_count >= config.expected_count_min
                if config.expected_count_max is not None:
                    count_passed = count_passed and record_count <= config.expected_count_max
                
                success = count_passed and freshness_passed
                
                details = {
                    'query': query,
                    'record_count': record_count,
                    'expected_count_min': config.expected_count_min,
                    'expected_count_max': config.expected_count_max,
                    'freshness_hours_limit': config.freshness_hours,
                    'freshness_minutes_actual': freshness_minutes,
                    'validations': {
                        'count_validation': count_passed,
                        'freshness_validation': freshness_passed
                    }
                }
                
                message_parts = []
                if not count_passed:
                    message_parts.append(f"Count {record_count} outside expected range")
                if not freshness_passed:
                    message_parts.append(f"Data too old: {freshness_minutes:.1f} minutes")
                
                message = (
                    "Data availability check passed" if success 
                    else f"Data availability check failed: {'; '.join(message_parts)}"
                )
                
                return DataCheckResult(
                    success=success,
                    message=message,
                    details=details,
                    checked_at=start_time,
                    data_source=config.data_source,
                    record_count=record_count,
                    freshness_minutes=freshness_minutes,
                    query_duration_ms=query_duration,
                    count_validation_passed=count_passed,
                    freshness_validation_passed=freshness_passed
                )
                
        except Exception as e:
            logger.exception(f"PostgreSQL data check failed for {config.data_source}")
            return DataCheckResult(
                success=False,
                message=f"PostgreSQL query failed: {str(e)}",
                details={
                    'error': str(e),
                    'query': config.query,
                    'connection': config.data_source
                },
                checked_at=start_time,
                data_source=config.data_source
            )
    
    async def _check_http_data(
        self,
        config: DataCheckConfig,
        connection_config: Dict[str, Any],
        start_time: datetime
    ) -> DataCheckResult:
        """Check HTTP API data availability."""
        base_url = connection_config['url']
        timeout = connection_config.get('timeout', 30)
        headers = connection_config.get('headers', {})
        
        # Use query as endpoint if provided
        endpoint = config.query or connection_config.get('default_endpoint', '/health')
        url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        query_start = datetime.utcnow()
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, headers=headers)
                query_duration = (datetime.utcnow() - query_start).total_seconds() * 1000
                
                # Check if response is successful
                success = response.status_code == 200
                
                # Try to extract record count from response
                record_count = None
                try:
                    json_data = response.json()
                    if isinstance(json_data, dict):
                        # Look for common count fields
                        for field in ['count', 'total', 'records', 'size']:
                            if field in json_data:
                                record_count = int(json_data[field])
                                break
                    elif isinstance(json_data, list):
                        record_count = len(json_data)
                except:
                    pass  # Not JSON or no count info
                
                # Validate count if we have it
                count_passed = True
                if record_count is not None:
                    if config.expected_count_min is not None:
                        count_passed = count_passed and record_count >= config.expected_count_min
                    if config.expected_count_max is not None:
                        count_passed = count_passed and record_count <= config.expected_count_max
                
                success = success and count_passed
                
                details = {
                    'url': url,
                    'status_code': response.status_code,
                    'response_size': len(response.content),
                    'record_count': record_count,
                    'headers': dict(response.headers),
                    'validations': {
                        'http_status': response.status_code == 200,
                        'count_validation': count_passed
                    }
                }
                
                message = (
                    f"HTTP check passed (status: {response.status_code})" if success
                    else f"HTTP check failed (status: {response.status_code})"
                )
                
                return DataCheckResult(
                    success=success,
                    message=message,
                    details=details,
                    checked_at=start_time,
                    data_source=config.data_source,
                    record_count=record_count,
                    query_duration_ms=query_duration,
                    count_validation_passed=count_passed
                )
                
        except httpx.TimeoutException:
            return DataCheckResult(
                success=False,
                message=f"HTTP request timed out after {timeout}s",
                details={'url': url, 'timeout': timeout},
                checked_at=start_time,
                data_source=config.data_source
            )
        except Exception as e:
            logger.exception(f"HTTP data check failed for {config.data_source}")
            return DataCheckResult(
                success=False,
                message=f"HTTP request failed: {str(e)}",
                details={'url': url, 'error': str(e)},
                checked_at=start_time,
                data_source=config.data_source
            )
    
    async def _check_file_data(
        self,
        config: DataCheckConfig,
        connection_config: Dict[str, Any],
        start_time: datetime
    ) -> DataCheckResult:
        """Check file-based data availability."""
        from pathlib import Path
        import os
        
        file_path = Path(connection_config.get('path', config.query or ''))
        
        try:
            # Check if file exists
            if not file_path.exists():
                return DataCheckResult(
                    success=False,
                    message=f"File not found: {file_path}",
                    details={'file_path': str(file_path)},
                    checked_at=start_time,
                    data_source=config.data_source
                )
            
            # Get file info
            stat_info = file_path.stat()
            file_size = stat_info.st_size
            modified_time = datetime.fromtimestamp(stat_info.st_mtime)
            
            # Check freshness
            file_age_minutes = (datetime.utcnow() - modified_time).total_seconds() / 60
            freshness_passed = True
            if config.freshness_hours:
                freshness_passed = file_age_minutes <= (config.freshness_hours * 60)
            
            # For certain file types, try to count records
            record_count = None
            if file_path.suffix.lower() in ['.csv', '.txt']:
                try:
                    with open(file_path, 'r') as f:
                        record_count = sum(1 for line in f) - 1  # Subtract header
                except:
                    pass
            
            # Validate count
            count_passed = True
            if record_count is not None:
                if config.expected_count_min is not None:
                    count_passed = count_passed and record_count >= config.expected_count_min
                if config.expected_count_max is not None:
                    count_passed = count_passed and record_count <= config.expected_count_max
            
            success = freshness_passed and count_passed
            
            details = {
                'file_path': str(file_path),
                'file_size_bytes': file_size,
                'modified_time': modified_time.isoformat(),
                'age_minutes': file_age_minutes,
                'record_count': record_count,
                'validations': {
                    'file_exists': True,
                    'freshness_validation': freshness_passed,
                    'count_validation': count_passed
                }
            }
            
            message_parts = []
            if not freshness_passed:
                message_parts.append(f"File too old: {file_age_minutes:.1f} minutes")
            if not count_passed:
                message_parts.append(f"Record count {record_count} outside expected range")
            
            message = (
                "File check passed" if success
                else f"File check failed: {'; '.join(message_parts)}"
            )
            
            return DataCheckResult(
                success=success,
                message=message,
                details=details,
                checked_at=start_time,
                data_source=config.data_source,
                record_count=record_count,
                freshness_minutes=file_age_minutes,
                count_validation_passed=count_passed,
                freshness_validation_passed=freshness_passed
            )
            
        except Exception as e:
            logger.exception(f"File data check failed for {config.data_source}")
            return DataCheckResult(
                success=False,
                message=f"File check failed: {str(e)}",
                details={'file_path': str(file_path), 'error': str(e)},
                checked_at=start_time,
                data_source=config.data_source
            )
    
    async def batch_check(
        self,
        checks: List[DataCheckConfig]
    ) -> List[DataCheckResult]:
        """Run multiple data availability checks concurrently."""
        tasks = [self.check_data_availability(config) for config in checks]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to failed results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(DataCheckResult(
                    success=False,
                    message=f"Check failed with exception: {str(result)}",
                    details={'error': str(result)},
                    checked_at=datetime.utcnow(),
                    data_source=checks[i].data_source
                ))
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def close(self):
        """Clean up connections and pools."""
        for name, pool in self.connection_pools.items():
            try:
                await pool.close()
                logger.info(f"Closed connection pool for {name}")
            except Exception as e:
                logger.error(f"Error closing connection pool {name}: {e}")
        
        self.connection_pools.clear()
        self.connections.clear()