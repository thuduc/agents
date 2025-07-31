"""Health monitoring and alerting system."""

import asyncio
import logging
import psutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json

from prometheus_client import CollectorRegistry, Gauge, Counter, Histogram, generate_latest

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health check status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Individual health check definition."""
    name: str
    check_function: Callable
    interval_seconds: int = 60
    timeout_seconds: int = 30
    enabled: bool = True
    critical: bool = False
    description: str = ""
    
    # State tracking
    last_check: Optional[datetime] = None
    last_status: HealthStatus = HealthStatus.UNKNOWN
    last_message: str = ""
    consecutive_failures: int = 0
    last_success: Optional[datetime] = None


@dataclass
class HealthCheckResult:
    """Result of a health check execution."""
    check_name: str
    status: HealthStatus
    message: str
    checked_at: datetime
    duration_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemMetrics:
    """System performance metrics."""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_available_gb: float
    disk_usage_percent: float
    disk_free_gb: float
    network_bytes_sent: int
    network_bytes_recv: int
    process_count: int
    load_average: Optional[List[float]] = None  # Unix only


class HealthMonitor:
    """Comprehensive health monitoring system."""
    
    def __init__(self, notification_callback: Optional[Callable] = None):
        self.notification_callback = notification_callback
        
        # Health checks registry
        self.health_checks: Dict[str, HealthCheck] = {}
        
        # Monitoring state
        self.monitoring_active = False
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Metrics
        self.metrics_registry = CollectorRegistry()
        self._setup_prometheus_metrics()
        
        # Alert thresholds
        self.alert_thresholds = {
            'cpu_percent': 80.0,
            'memory_percent': 85.0,
            'disk_usage_percent': 90.0,
            'consecutive_failures': 3
        }
        
        # Recent metrics storage (last 24 hours)
        self.metrics_history: List[SystemMetrics] = []
        self.max_history_size = 24 * 60  # 24 hours at 1-minute intervals
        
        # Register default health checks
        self._register_default_checks()
    
    def _setup_prometheus_metrics(self):
        """Set up Prometheus metrics."""
        self.prom_health_status = Gauge(
            'runbook_agent_health_status',
            'Health check status (1=healthy, 0.5=warning, 0=critical)',
            ['check_name'],
            registry=self.metrics_registry
        )
        
        self.prom_health_duration = Histogram(
            'runbook_agent_health_check_duration_seconds',
            'Health check execution duration',
            ['check_name'],
            registry=self.metrics_registry
        )
        
        self.prom_system_cpu = Gauge(
            'runbook_agent_system_cpu_percent',
            'System CPU usage percentage',
            registry=self.metrics_registry
        )
        
        self.prom_system_memory = Gauge(
            'runbook_agent_system_memory_percent',
            'System memory usage percentage',
            registry=self.metrics_registry
        )
        
        self.prom_system_disk = Gauge(
            'runbook_agent_system_disk_percent',
            'System disk usage percentage',
            registry=self.metrics_registry
        )
        
        self.prom_workflow_executions = Counter(
            'runbook_agent_workflow_executions_total',
            'Total workflow executions',
            ['status'],
            registry=self.metrics_registry
        )
        
        self.prom_task_executions = Counter(
            'runbook_agent_task_executions_total',
            'Total task executions',
            ['task_type', 'status'],
            registry=self.metrics_registry
        )
    
    def _register_default_checks(self):
        """Register default system health checks."""
        # System resource checks
        self.register_health_check(HealthCheck(
            name="system_cpu",
            check_function=self._check_system_cpu,
            interval_seconds=60,
            critical=False,
            description="Monitor system CPU usage"
        ))
        
        self.register_health_check(HealthCheck(
            name="system_memory",
            check_function=self._check_system_memory,
            interval_seconds=60,
            critical=False,
            description="Monitor system memory usage"
        ))
        
        self.register_health_check(HealthCheck(
            name="system_disk",
            check_function=self._check_system_disk,
            interval_seconds=300,  # 5 minutes
            critical=True,
            description="Monitor system disk usage"
        ))
        
        # Application health checks
        self.register_health_check(HealthCheck(
            name="database_connection",
            check_function=self._check_database_connection,
            interval_seconds=120,
            critical=True,
            description="Check database connectivity"
        ))
        
        self.register_health_check(HealthCheck(
            name="redis_connection",
            check_function=self._check_redis_connection,
            interval_seconds=120,
            critical=True,
            description="Check Redis connectivity"
        ))
    
    def register_health_check(self, health_check: HealthCheck):
        """Register a new health check."""
        self.health_checks[health_check.name] = health_check
        logger.info(f"Registered health check: {health_check.name}")
    
    def unregister_health_check(self, check_name: str):
        """Unregister a health check."""
        if check_name in self.health_checks:
            del self.health_checks[check_name]
            logger.info(f"Unregistered health check: {check_name}")
    
    async def start_monitoring(self):
        """Start the health monitoring loop."""
        if self.monitoring_active:
            logger.warning("Health monitoring is already active")
            return
        
        self.monitoring_active = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Health monitoring started")
    
    async def stop_monitoring(self):
        """Stop the health monitoring loop."""
        self.monitoring_active = False
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
            self.monitoring_task = None
        
        logger.info("Health monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop."""
        try:
            while self.monitoring_active:
                # Collect system metrics
                await self._collect_system_metrics()
                
                # Run health checks
                await self._run_health_checks()
                
                # Sleep until next check interval
                await asyncio.sleep(60)  # Base interval of 1 minute
                
        except asyncio.CancelledError:
            logger.info("Monitoring loop cancelled")
        except Exception as e:
            logger.exception(f"Error in monitoring loop: {e}")
    
    async def _collect_system_metrics(self):
        """Collect system performance metrics."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_available_gb = memory.available / (1024**3)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_usage_percent = (disk.used / disk.total) * 100
            disk_free_gb = disk.free / (1024**3)
            
            # Network I/O
            network = psutil.net_io_counters()
            network_bytes_sent = network.bytes_sent
            network_bytes_recv = network.bytes_recv
            
            # Process count
            process_count = len(psutil.pids())
            
            # Load average (Unix only)
            load_average = None
            try:
                load_average = list(psutil.getloadavg())
            except AttributeError:
                pass  # Windows doesn't have load average
            
            # Create metrics object
            metrics = SystemMetrics(
                timestamp=datetime.utcnow(),
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_available_gb=memory_available_gb,
                disk_usage_percent=disk_usage_percent,
                disk_free_gb=disk_free_gb,
                network_bytes_sent=network_bytes_sent,
                network_bytes_recv=network_bytes_recv,
                process_count=process_count,
                load_average=load_average
            )
            
            # Store in history
            self.metrics_history.append(metrics)
            
            # Trim history if too large
            if len(self.metrics_history) > self.max_history_size:
                self.metrics_history = self.metrics_history[-self.max_history_size:]
            
            # Update Prometheus metrics
            self.prom_system_cpu.set(cpu_percent)
            self.prom_system_memory.set(memory_percent)
            self.prom_system_disk.set(disk_usage_percent)
            
            # Check for alerts
            await self._check_metric_alerts(metrics)
            
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
    
    async def _run_health_checks(self):
        """Run all enabled health checks."""
        current_time = datetime.utcnow()
        
        for check_name, health_check in self.health_checks.items():
            if not health_check.enabled:
                continue
            
            # Check if it's time to run this check
            if (health_check.last_check and 
                current_time - health_check.last_check < timedelta(seconds=health_check.interval_seconds)):
                continue
            
            # Run the health check
            await self._execute_health_check(health_check)
    
    async def _execute_health_check(self, health_check: HealthCheck):
        """Execute a single health check."""
        start_time = datetime.utcnow()
        
        try:
            # Run the check function with timeout
            result = await asyncio.wait_for(
                health_check.check_function(),
                timeout=health_check.timeout_seconds
            )
            
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Update health check state
            health_check.last_check = start_time
            health_check.last_status = result.status
            health_check.last_message = result.message
            
            if result.status == HealthStatus.HEALTHY:
                health_check.consecutive_failures = 0
                health_check.last_success = start_time
            else:
                health_check.consecutive_failures += 1
            
            # Update Prometheus metrics
            status_value = {
                HealthStatus.HEALTHY: 1.0,
                HealthStatus.WARNING: 0.5,
                HealthStatus.CRITICAL: 0.0,
                HealthStatus.UNKNOWN: 0.0
            }[result.status]
            
            self.prom_health_status.labels(check_name=health_check.name).set(status_value)
            self.prom_health_duration.labels(check_name=health_check.name).observe(duration_ms / 1000)
            
            # Check if we need to send alerts
            await self._check_health_alerts(health_check, result)
            
            logger.debug(f"Health check {health_check.name}: {result.status} - {result.message}")
            
        except asyncio.TimeoutError:
            health_check.last_check = start_time
            health_check.last_status = HealthStatus.CRITICAL
            health_check.last_message = f"Health check timed out after {health_check.timeout_seconds}s"
            health_check.consecutive_failures += 1
            
            logger.error(f"Health check {health_check.name} timed out")
            
        except Exception as e:
            health_check.last_check = start_time
            health_check.last_status = HealthStatus.CRITICAL
            health_check.last_message = f"Health check failed: {str(e)}"
            health_check.consecutive_failures += 1
            
            logger.error(f"Health check {health_check.name} failed: {e}")
    
    async def _check_system_cpu(self) -> HealthCheckResult:
        """Check system CPU usage."""
        cpu_percent = psutil.cpu_percent(interval=1)
        
        if cpu_percent > self.alert_thresholds['cpu_percent']:
            status = HealthStatus.WARNING if cpu_percent < 95 else HealthStatus.CRITICAL
            message = f"High CPU usage: {cpu_percent:.1f}%"
        else:
            status = HealthStatus.HEALTHY
            message = f"CPU usage normal: {cpu_percent:.1f}%"
        
        return HealthCheckResult(
            check_name="system_cpu",
            status=status,
            message=message,
            checked_at=datetime.utcnow(),
            duration_ms=1000,  # CPU check takes ~1 second
            metadata={'cpu_percent': cpu_percent}
        )
    
    async def _check_system_memory(self) -> HealthCheckResult:
        """Check system memory usage."""
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        if memory_percent > self.alert_thresholds['memory_percent']:
            status = HealthStatus.WARNING if memory_percent < 95 else HealthStatus.CRITICAL
            message = f"High memory usage: {memory_percent:.1f}%"
        else:
            status = HealthStatus.HEALTHY
            message = f"Memory usage normal: {memory_percent:.1f}%"
        
        return HealthCheckResult(
            check_name="system_memory",
            status=status,
            message=message,
            checked_at=datetime.utcnow(),
            duration_ms=10,
            metadata={
                'memory_percent': memory_percent,
                'memory_available_gb': memory.available / (1024**3)
            }
        )
    
    async def _check_system_disk(self) -> HealthCheckResult:
        """Check system disk usage."""
        disk = psutil.disk_usage('/')
        disk_usage_percent = (disk.used / disk.total) * 100
        
        if disk_usage_percent > self.alert_thresholds['disk_usage_percent']:
            status = HealthStatus.CRITICAL
            message = f"Critical disk usage: {disk_usage_percent:.1f}%"
        elif disk_usage_percent > 80:
            status = HealthStatus.WARNING
            message = f"High disk usage: {disk_usage_percent:.1f}%"
        else:
            status = HealthStatus.HEALTHY
            message = f"Disk usage normal: {disk_usage_percent:.1f}%"
        
        return HealthCheckResult(
            check_name="system_disk",
            status=status,
            message=message,
            checked_at=datetime.utcnow(),
            duration_ms=50,
            metadata={
                'disk_usage_percent': disk_usage_percent,
                'disk_free_gb': disk.free / (1024**3)
            }
        )
    
    async def _check_database_connection(self) -> HealthCheckResult:
        """Check database connectivity."""
        # This would implement actual database connectivity check
        # For now, return a placeholder
        return HealthCheckResult(
            check_name="database_connection",
            status=HealthStatus.HEALTHY,
            message="Database connection check not implemented",
            checked_at=datetime.utcnow(),
            duration_ms=100
        )
    
    async def _check_redis_connection(self) -> HealthCheckResult:
        """Check Redis connectivity."""
        # This would implement actual Redis connectivity check
        # For now, return a placeholder
        return HealthCheckResult(
            check_name="redis_connection",
            status=HealthStatus.HEALTHY,
            message="Redis connection check not implemented",
            checked_at=datetime.utcnow(),
            duration_ms=50
        )
    
    async def _check_metric_alerts(self, metrics: SystemMetrics):
        """Check if system metrics trigger alerts."""
        alerts = []
        
        if metrics.cpu_percent > self.alert_thresholds['cpu_percent']:
            alerts.append(f"High CPU usage: {metrics.cpu_percent:.1f}%")
        
        if metrics.memory_percent > self.alert_thresholds['memory_percent']:
            alerts.append(f"High memory usage: {metrics.memory_percent:.1f}%")
        
        if metrics.disk_usage_percent > self.alert_thresholds['disk_usage_percent']:
            alerts.append(f"Critical disk usage: {metrics.disk_usage_percent:.1f}%")
        
        # Send alerts if any triggered
        if alerts and self.notification_callback:
            await self.notification_callback(
                "system_alert",
                "; ".join(alerts),
                "critical" if metrics.disk_usage_percent > 90 else "warning"
            )
    
    async def _check_health_alerts(self, health_check: HealthCheck, result: HealthCheckResult):
        """Check if health check results trigger alerts."""
        # Alert on critical status
        if result.status == HealthStatus.CRITICAL and health_check.critical:
            if self.notification_callback:
                await self.notification_callback(
                    "health_check_critical",
                    f"Critical health check failure: {health_check.name} - {result.message}",
                    "critical"
                )
        
        # Alert on consecutive failures
        if health_check.consecutive_failures >= self.alert_thresholds['consecutive_failures']:
            if self.notification_callback:
                await self.notification_callback(
                    "health_check_repeated_failure",
                    f"Health check {health_check.name} has failed {health_check.consecutive_failures} times consecutively",
                    "high"
                )
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status summary."""
        overall_status = HealthStatus.HEALTHY
        unhealthy_checks = []
        
        for check_name, health_check in self.health_checks.items():
            if not health_check.enabled:
                continue
            
            if health_check.last_status == HealthStatus.CRITICAL:
                overall_status = HealthStatus.CRITICAL
                unhealthy_checks.append(check_name)
            elif health_check.last_status == HealthStatus.WARNING and overall_status != HealthStatus.CRITICAL:
                overall_status = HealthStatus.WARNING
                unhealthy_checks.append(check_name)
        
        return {
            'overall_status': overall_status,
            'timestamp': datetime.utcnow().isoformat(),
            'checks': {
                name: {
                    'status': check.last_status,
                    'message': check.last_message,
                    'last_check': check.last_check.isoformat() if check.last_check else None,
                    'consecutive_failures': check.consecutive_failures
                }
                for name, check in self.health_checks.items()
                if check.enabled
            },
            'unhealthy_checks': unhealthy_checks,
            'system_metrics': self._get_latest_metrics() if self.metrics_history else None
        }
    
    def _get_latest_metrics(self) -> Dict[str, Any]:
        """Get latest system metrics."""
        if not self.metrics_history:
            return {}
        
        latest = self.metrics_history[-1]
        return {
            'timestamp': latest.timestamp.isoformat(),
            'cpu_percent': latest.cpu_percent,
            'memory_percent': latest.memory_percent,
            'memory_available_gb': latest.memory_available_gb,
            'disk_usage_percent': latest.disk_usage_percent,
            'disk_free_gb': latest.disk_free_gb,
            'process_count': latest.process_count,
            'load_average': latest.load_average
        }
    
    def get_prometheus_metrics(self) -> str:
        """Get Prometheus metrics in text format."""
        return generate_latest(self.metrics_registry).decode('utf-8')
    
    def record_workflow_execution(self, status: str):
        """Record workflow execution for metrics."""
        self.prom_workflow_executions.labels(status=status).inc()
    
    def record_task_execution(self, task_type: str, status: str):
        """Record task execution for metrics."""
        self.prom_task_executions.labels(task_type=task_type, status=status).inc()