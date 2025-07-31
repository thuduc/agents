"""Data models for runbook configuration."""

from typing import List, Dict, Any, Optional, Union
from datetime import datetime, time
from enum import Enum
from pydantic import BaseModel, Field, validator
from dataclasses import dataclass


class TaskType(str, Enum):
    """Types of runbook tasks."""
    DATA_CHECK = "data_check"
    UI_AUTOMATION = "ui_automation"
    API_CALL = "api_call"
    DATABASE_QUERY = "database_query"
    FILE_OPERATION = "file_operation"
    NOTIFICATION = "notification"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"
    WAIT = "wait"


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class NotificationChannel(str, Enum):
    """Notification channels."""
    EMAIL = "email"
    SLACK = "slack"
    TEAMS = "teams"
    SMS = "sms"
    WEBHOOK = "webhook"


@dataclass
class DataCheckConfig:
    """Configuration for data availability checks."""
    data_source: str
    query: Optional[str] = None
    expected_count_min: Optional[int] = None
    expected_count_max: Optional[int] = None
    freshness_hours: Optional[int] = None
    validation_rules: List[str] = None


@dataclass
class UIAutomationConfig:
    """Configuration for UI automation tasks."""
    url: str
    browser: str = "chromium"
    headless: bool = True
    timeout_seconds: int = 30
    screenshot_on_failure: bool = True
    steps: List[Dict[str, Any]] = None


@dataclass
class APICallConfig:
    """Configuration for API calls."""
    method: str
    url: str
    headers: Optional[Dict[str, str]] = None
    params: Optional[Dict[str, Any]] = None
    body: Optional[Dict[str, Any]] = None
    expected_status: int = 200
    timeout_seconds: int = 30


@dataclass
class DatabaseQueryConfig:
    """Configuration for database queries."""
    connection_name: str
    query: str
    parameters: Optional[Dict[str, Any]] = None
    expected_result_count: Optional[int] = None
    timeout_seconds: int = 60


@dataclass
class NotificationConfig:
    """Configuration for notifications."""
    channels: List[NotificationChannel]
    message_template: str
    recipients: List[str]
    priority: str = "normal"
    include_details: bool = True


class TaskConfig(BaseModel):
    """Configuration for a single runbook task."""
    
    id: str = Field(..., description="Unique task identifier")
    name: str = Field(..., description="Human-readable task name")
    description: Optional[str] = Field(None, description="Task description")
    
    # Task execution
    task_type: TaskType = Field(..., description="Type of task")
    config: Dict[str, Any] = Field(..., description="Task-specific configuration")
    
    # Dependencies and scheduling
    depends_on: List[str] = Field(default=[], description="Task dependencies")
    timeout_minutes: int = Field(default=30, description="Task timeout in minutes")
    retry_count: int = Field(default=3, description="Number of retry attempts")
    retry_delay_seconds: int = Field(default=60, description="Delay between retries")
    
    # Conditional execution
    conditions: Optional[Dict[str, Any]] = Field(None, description="Execution conditions")
    skip_on_failure: bool = Field(default=False, description="Skip if dependencies fail")
    
    # Notifications
    notify_on_start: bool = Field(default=False, description="Notify when task starts")
    notify_on_success: bool = Field(default=False, description="Notify on success")
    notify_on_failure: bool = Field(default=True, description="Notify on failure")
    
    @validator('id')
    def validate_task_id(cls, v):
        """Ensure task ID is valid."""
        if not v or not v.strip():
            raise ValueError("Task ID cannot be empty")
        return v.strip()


class RunbookSchedule(BaseModel):
    """Schedule configuration for runbook execution."""
    
    enabled: bool = Field(default=True, description="Whether scheduling is enabled")
    cron_expression: Optional[str] = Field(None, description="Cron expression for scheduling")
    timezone: str = Field(default="UTC", description="Timezone for scheduling")
    
    # Monthly schedule specifics
    day_of_month: Optional[int] = Field(None, ge=1, le=31, description="Day of month to run")
    time_of_day: Optional[time] = Field(None, description="Time of day to run")
    
    # Execution windows
    earliest_start: Optional[time] = Field(None, description="Earliest start time")
    latest_start: Optional[time] = Field(None, description="Latest start time")
    
    # Holiday handling
    skip_holidays: bool = Field(default=True, description="Skip execution on holidays")
    holiday_calendar: str = Field(default="US", description="Holiday calendar to use")


class RunbookConfig(BaseModel):
    """Complete runbook configuration."""
    
    # Basic information
    id: str = Field(..., description="Unique runbook identifier")
    name: str = Field(..., description="Human-readable runbook name")
    description: Optional[str] = Field(None, description="Runbook description")
    version: str = Field(default="1.0.0", description="Runbook version")
    
    # Ownership and metadata
    owner: str = Field(..., description="Runbook owner")
    team: Optional[str] = Field(None, description="Owning team")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    tags: List[str] = Field(default=[], description="Searchable tags")
    
    # Tasks and execution
    tasks: List[TaskConfig] = Field(..., description="List of tasks")
    schedule: Optional[RunbookSchedule] = Field(None, description="Execution schedule")
    
    # Global settings
    global_timeout_minutes: int = Field(default=240, description="Global timeout in minutes")
    max_parallel_tasks: int = Field(default=5, description="Maximum parallel tasks")
    
    # Environment and connections
    environment: str = Field(default="production", description="Target environment")
    connections: Dict[str, Dict[str, Any]] = Field(default=dict, description="Connection configurations")
    
    # Notifications
    default_notifications: Optional[NotificationConfig] = Field(None, description="Default notification settings")
    
    @validator('tasks')
    def validate_task_dependencies(cls, v):
        """Validate task dependencies form a valid DAG."""
        task_ids = {task.id for task in v}
        
        for task in v:
            for dep in task.depends_on:
                if dep not in task_ids:
                    raise ValueError(f"Task {task.id} depends on non-existent task {dep}")
        
        # TODO: Add cycle detection
        return v


class RunbookExecution(BaseModel):
    """Runbook execution instance."""
    
    id: str = Field(..., description="Unique execution identifier")
    runbook_id: str = Field(..., description="Associated runbook ID")
    
    # Execution metadata
    started_at: Optional[datetime] = Field(None, description="Execution start time")
    completed_at: Optional[datetime] = Field(None, description="Execution end time")
    triggered_by: str = Field(..., description="What triggered this execution")
    
    # Status tracking
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Overall execution status")
    current_task: Optional[str] = Field(None, description="Currently executing task")
    
    # Task status
    task_status: Dict[str, TaskStatus] = Field(default=dict, description="Status of each task")
    task_results: Dict[str, Dict[str, Any]] = Field(default=dict, description="Results from each task")
    task_errors: Dict[str, str] = Field(default=dict, description="Error messages from failed tasks")
    
    # Metrics
    total_tasks: int = Field(default=0, description="Total number of tasks")
    completed_tasks: int = Field(default=0, description="Number of completed tasks")
    failed_tasks: int = Field(default=0, description="Number of failed tasks")
    
    # Configuration snapshot
    config_snapshot: Optional[RunbookConfig] = Field(None, description="Runbook config at execution time")


class ConfigParsingResult(BaseModel):
    """Result of parsing configuration from Excel."""
    
    success: bool = Field(..., description="Whether parsing was successful")
    runbook: Optional[RunbookConfig] = Field(None, description="Parsed runbook configuration")
    errors: List[str] = Field(default=[], description="Parsing errors")
    warnings: List[str] = Field(default=[], description="Parsing warnings")
    
    # Parsing metadata
    source_file: str = Field(..., description="Source Excel file path")
    parsed_at: datetime = Field(default_factory=datetime.utcnow, description="When parsing occurred")
    sheets_processed: List[str] = Field(default=[], description="Excel sheets that were processed")