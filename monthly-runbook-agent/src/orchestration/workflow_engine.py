"""Workflow orchestration engine for runbook execution."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Any, Callable
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict, deque

from ..config.models import (
    RunbookConfig, TaskConfig, RunbookExecution, TaskStatus, TaskType
)
from ..data.availability_checker import DataAvailabilityChecker, DataCheckConfig
from ..automation.ui_engine import UIAutomationEngine, UIAutomationConfig

logger = logging.getLogger(__name__)


class ExecutionState(str, Enum):
    """Workflow execution states."""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskExecution:
    """Tracks execution of a single task."""
    task_id: str
    task_config: TaskConfig
    status: TaskStatus = TaskStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    error_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate task duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    @property
    def is_finished(self) -> bool:
        """Check if task is in a finished state."""
        return self.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.SKIPPED]


@dataclass 
class WorkflowExecution:
    """Tracks execution of an entire workflow."""
    execution_id: str
    runbook_config: RunbookConfig
    state: ExecutionState = ExecutionState.INITIALIZING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    triggered_by: str = "manual"
    
    # Task tracking
    tasks: Dict[str, TaskExecution] = field(default_factory=dict)
    task_dependencies: Dict[str, Set[str]] = field(default_factory=dict)
    
    # Execution context
    variables: Dict[str, str] = field(default_factory=dict)
    global_timeout_at: Optional[datetime] = None
    
    # Statistics
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0
    
    def __post_init__(self):
        """Initialize task executions from runbook config."""
        self.total_tasks = len(self.runbook_config.tasks)
        
        for task_config in self.runbook_config.tasks:
            task_exec = TaskExecution(
                task_id=task_config.id,
                task_config=task_config
            )
            self.tasks[task_config.id] = task_exec
            
            # Build dependency graph
            self.task_dependencies[task_config.id] = set(task_config.depends_on)
        
        # Set global timeout
        if self.runbook_config.global_timeout_minutes > 0:
            self.global_timeout_at = datetime.utcnow() + timedelta(
                minutes=self.runbook_config.global_timeout_minutes
            )
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate workflow duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    @property
    def progress_percentage(self) -> float:
        """Calculate execution progress percentage."""
        if self.total_tasks == 0:
            return 100.0
        return (self.completed_tasks + self.failed_tasks + self.skipped_tasks) / self.total_tasks * 100


class WorkflowOrchestrator:
    """Orchestrates workflow execution with dependency management."""
    
    def __init__(
        self,
        data_checker: Optional[DataAvailabilityChecker] = None,
        ui_engine: Optional[UIAutomationEngine] = None,
        notification_callback: Optional[Callable] = None
    ):
        self.data_checker = data_checker or DataAvailabilityChecker()
        self.ui_engine = ui_engine or UIAutomationEngine()
        self.notification_callback = notification_callback
        
        # Active executions
        self.active_executions: Dict[str, WorkflowExecution] = {}
        
        # Task executors
        self.task_executors = {
            TaskType.DATA_CHECK: self._execute_data_check,
            TaskType.UI_AUTOMATION: self._execute_ui_automation,
            TaskType.API_CALL: self._execute_api_call,
            TaskType.DATABASE_QUERY: self._execute_database_query,
            TaskType.NOTIFICATION: self._execute_notification,
            TaskType.WAIT: self._execute_wait,
            TaskType.CONDITIONAL: self._execute_conditional,
        }
    
    async def start_workflow(
        self,
        runbook_config: RunbookConfig,
        execution_id: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
        triggered_by: str = "manual"
    ) -> WorkflowExecution:
        """
        Start workflow execution.
        
        Args:
            runbook_config: Runbook configuration
            execution_id: Unique execution ID (generated if not provided)
            variables: Variable substitutions
            triggered_by: What triggered this execution
            
        Returns:
            WorkflowExecution instance
        """
        if execution_id is None:
            execution_id = f"{runbook_config.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        # Validate runbook configuration
        validation_errors = await self._validate_runbook(runbook_config)
        if validation_errors:
            raise ValueError(f"Runbook validation failed: {'; '.join(validation_errors)}")
        
        # Create workflow execution
        workflow = WorkflowExecution(
            execution_id=execution_id,
            runbook_config=runbook_config,
            started_at=datetime.utcnow(),
            triggered_by=triggered_by,
            variables=variables or {}
        )
        
        # Register active execution
        self.active_executions[execution_id] = workflow
        
        logger.info(f"Starting workflow execution: {execution_id}")
        
        # Start execution in background
        asyncio.create_task(self._execute_workflow(workflow))
        
        return workflow
    
    async def _execute_workflow(self, workflow: WorkflowExecution):
        """Execute workflow tasks according to dependency order."""
        try:
            workflow.state = ExecutionState.RUNNING
            logger.info(f"Workflow {workflow.execution_id} started execution")
            
            # Get execution order
            execution_order = self._calculate_execution_order(workflow)
            if not execution_order:
                workflow.state = ExecutionState.FAILED
                logger.error(f"Workflow {workflow.execution_id} has circular dependencies")
                return
            
            # Execute tasks in batches (respecting dependencies and parallelism)
            max_parallel = workflow.runbook_config.max_parallel_tasks
            
            for batch in execution_order:
                # Check global timeout
                if workflow.global_timeout_at and datetime.utcnow() > workflow.global_timeout_at:
                    workflow.state = ExecutionState.FAILED
                    logger.error(f"Workflow {workflow.execution_id} exceeded global timeout")
                    break
                
                # Execute batch with parallelism limit
                semaphore = asyncio.Semaphore(max_parallel)
                batch_tasks = []
                
                for task_id in batch:
                    if self._should_execute_task(workflow, task_id):
                        task = asyncio.create_task(
                            self._execute_single_task(workflow, task_id, semaphore)
                        )
                        batch_tasks.append(task)
                
                # Wait for batch completion
                if batch_tasks:
                    await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                # Check if workflow should continue
                if not self._should_continue_workflow(workflow):
                    break
            
            # Determine final state
            if workflow.failed_tasks > 0:
                workflow.state = ExecutionState.FAILED
            else:
                workflow.state = ExecutionState.COMPLETED
            
            workflow.completed_at = datetime.utcnow()
            
            logger.info(
                f"Workflow {workflow.execution_id} finished: {workflow.state} "
                f"({workflow.completed_tasks}/{workflow.total_tasks} completed)"
            )
            
            # Send completion notification
            if self.notification_callback:
                await self.notification_callback(workflow, "workflow_completed")
                
        except Exception as e:
            logger.exception(f"Workflow {workflow.execution_id} failed with exception")
            workflow.state = ExecutionState.FAILED
            workflow.completed_at = datetime.utcnow()
            
            if self.notification_callback:
                await self.notification_callback(workflow, "workflow_failed", str(e))
        
        finally:
            # Clean up
            if workflow.execution_id in self.active_executions:
                del self.active_executions[workflow.execution_id]
    
    async def _execute_single_task(
        self,
        workflow: WorkflowExecution,
        task_id: str,
        semaphore: asyncio.Semaphore
    ):
        """Execute a single task with semaphore for concurrency control."""
        async with semaphore:
            task_exec = workflow.tasks[task_id]
            task_config = task_exec.task_config
            
            logger.info(f"Starting task {task_id} in workflow {workflow.execution_id}")
            
            task_exec.status = TaskStatus.RUNNING
            task_exec.started_at = datetime.utcnow()
            
            # Send start notification if requested
            if task_config.notify_on_start and self.notification_callback:
                await self.notification_callback(workflow, "task_started", task_id)
            
            max_retries = task_config.retry_count
            retry_delay = task_config.retry_delay_seconds
            
            for attempt in range(max_retries + 1):
                try:
                    task_exec.retry_count = attempt
                    
                    # Get task executor
                    executor = self.task_executors.get(task_config.task_type)
                    if not executor:
                        raise ValueError(f"No executor for task type: {task_config.task_type}")
                    
                    # Execute task with timeout
                    timeout_seconds = task_config.timeout_minutes * 60
                    result = await asyncio.wait_for(
                        executor(workflow, task_exec),
                        timeout=timeout_seconds
                    )
                    
                    # Task succeeded
                    task_exec.status = TaskStatus.COMPLETED
                    task_exec.result = result
                    task_exec.completed_at = datetime.utcnow()
                    workflow.completed_tasks += 1
                    
                    logger.info(f"Task {task_id} completed successfully")
                    
                    # Send success notification if requested
                    if task_config.notify_on_success and self.notification_callback:
                        await self.notification_callback(workflow, "task_completed", task_id)
                    
                    return
                    
                except asyncio.TimeoutError:
                    error_msg = f"Task {task_id} timed out after {timeout_seconds} seconds"
                    logger.error(error_msg)
                    task_exec.error_message = error_msg
                    
                except Exception as e:
                    error_msg = f"Task {task_id} failed: {str(e)}"
                    logger.error(error_msg)
                    task_exec.error_message = error_msg
                
                # Retry logic
                if attempt < max_retries:
                    logger.info(f"Retrying task {task_id} in {retry_delay} seconds (attempt {attempt + 2})")
                    await asyncio.sleep(retry_delay)
                else:
                    # All retries exhausted
                    task_exec.status = TaskStatus.FAILED
                    task_exec.completed_at = datetime.utcnow()
                    workflow.failed_tasks += 1
                    
                    logger.error(f"Task {task_id} failed after {max_retries + 1} attempts")
                    
                    # Send failure notification if requested
                    if task_config.notify_on_failure and self.notification_callback:
                        await self.notification_callback(workflow, "task_failed", task_id)
    
    async def _execute_data_check(
        self,
        workflow: WorkflowExecution,
        task_exec: TaskExecution
    ) -> Dict[str, Any]:
        """Execute data availability check task."""
        config_dict = task_exec.task_config.config
        
        # Create DataCheckConfig from task config
        check_config = DataCheckConfig(
            data_source=config_dict['data_source'],
            query=config_dict.get('query'),
            expected_count_min=config_dict.get('expected_count_min'),
            expected_count_max=config_dict.get('expected_count_max'),
            freshness_hours=config_dict.get('freshness_hours'),
            validation_rules=config_dict.get('validation_rules', [])
        )
        
        # Execute data check
        result = await self.data_checker.check_data_availability(check_config)
        
        if not result.success:
            raise RuntimeError(f"Data check failed: {result.message}")
        
        return {
            'success': result.success,
            'message': result.message,
            'record_count': result.record_count,
            'freshness_minutes': result.freshness_minutes,
            'details': result.details
        }
    
    async def _execute_ui_automation(
        self,
        workflow: WorkflowExecution,
        task_exec: TaskExecution
    ) -> Dict[str, Any]:
        """Execute UI automation task."""
        config_dict = task_exec.task_config.config
        
        # Create UIAutomationConfig from task config
        ui_config = UIAutomationConfig(
            url=config_dict['url'],
            browser=config_dict.get('browser', 'chromium'),
            headless=config_dict.get('headless', True),
            timeout_seconds=config_dict.get('timeout_seconds', 30),
            screenshot_on_failure=config_dict.get('screenshot_on_failure', True),
            steps=config_dict.get('steps', [])
        )
        
        # Execute UI automation
        result = await self.ui_engine.execute_automation(ui_config, workflow.variables)
        
        if not result.success:
            raise RuntimeError(f"UI automation failed: {result.message}")
        
        return {
            'success': result.success,
            'message': result.message,
            'duration_seconds': result.duration_seconds,
            'completed_steps': result.completed_steps,
            'total_steps': result.total_steps,
            'screenshots': result.screenshots,
            'console_logs': result.console_logs
        }
    
    async def _execute_api_call(
        self,
        workflow: WorkflowExecution,
        task_exec: TaskExecution
    ) -> Dict[str, Any]:
        """Execute API call task."""
        import httpx
        
        config_dict = task_exec.task_config.config
        
        method = config_dict.get('method', 'GET').upper()
        url = config_dict['url']
        headers = config_dict.get('headers', {})
        params = config_dict.get('params', {})
        body = config_dict.get('body')
        expected_status = config_dict.get('expected_status', 200)
        timeout = config_dict.get('timeout_seconds', 30)
        
        # Substitute variables
        url = self._substitute_variables(url, workflow.variables)
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=body
            )
            
            if response.status_code != expected_status:
                raise RuntimeError(
                    f"API call failed: expected status {expected_status}, got {response.status_code}"
                )
            
            try:
                response_data = response.json()
            except:
                response_data = response.text
            
            return {
                'success': True,
                'status_code': response.status_code,
                'response_data': response_data,
                'response_headers': dict(response.headers)
            }
    
    async def _execute_database_query(
        self,
        workflow: WorkflowExecution,
        task_exec: TaskExecution
    ) -> Dict[str, Any]:
        """Execute database query task."""
        config_dict = task_exec.task_config.config
        
        connection_name = config_dict['connection_name']
        query = config_dict['query']
        parameters = config_dict.get('parameters', {})
        
        # This would integrate with your database connection manager
        # For now, we'll use a placeholder
        raise NotImplementedError("Database query execution not implemented yet")
    
    async def _execute_notification(
        self,
        workflow: WorkflowExecution,
        task_exec: TaskExecution
    ) -> Dict[str, Any]:
        """Execute notification task."""
        if self.notification_callback:
            await self.notification_callback(workflow, "custom_notification", task_exec.task_id)
        
        return {'success': True, 'message': 'Notification sent'}
    
    async def _execute_wait(
        self,
        workflow: WorkflowExecution,
        task_exec: TaskExecution
    ) -> Dict[str, Any]:
        """Execute wait task."""
        config_dict = task_exec.task_config.config
        wait_seconds = config_dict.get('seconds', 60)
        
        await asyncio.sleep(wait_seconds)
        
        return {'success': True, 'waited_seconds': wait_seconds}
    
    async def _execute_conditional(
        self,
        workflow: WorkflowExecution,
        task_exec: TaskExecution
    ) -> Dict[str, Any]:
        """Execute conditional task."""
        # This would evaluate conditions and potentially skip/modify subsequent tasks
        raise NotImplementedError("Conditional execution not implemented yet")
    
    def _calculate_execution_order(
        self,
        workflow: WorkflowExecution
    ) -> List[List[str]]:
        """Calculate task execution order using topological sort."""
        # Build dependency graph
        in_degree = defaultdict(int)
        graph = defaultdict(list)
        
        all_tasks = set(workflow.tasks.keys())
        
        for task_id, dependencies in workflow.task_dependencies.items():
            in_degree[task_id] = len(dependencies)
            for dep in dependencies:
                if dep in all_tasks:
                    graph[dep].append(task_id)
        
        # Topological sort with batching
        execution_order = []
        queue = deque([task for task in all_tasks if in_degree[task] == 0])
        
        while queue:
            # Current batch - all tasks with no remaining dependencies
            current_batch = list(queue)
            queue.clear()
            
            if not current_batch:
                # Circular dependency detected
                return []
            
            execution_order.append(current_batch)
            
            # Process current batch
            for task_id in current_batch:
                for dependent in graph[task_id]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
        
        return execution_order
    
    def _should_execute_task(self, workflow: WorkflowExecution, task_id: str) -> bool:
        """Check if task should be executed based on dependencies and conditions."""
        task_exec = workflow.tasks[task_id]
        
        # Check if task is already finished
        if task_exec.is_finished:
            return False
        
        # Check dependencies
        for dep_id in workflow.task_dependencies[task_id]:
            dep_exec = workflow.tasks.get(dep_id)
            if not dep_exec or dep_exec.status != TaskStatus.COMPLETED:
                # Check if we should skip on dependency failure
                if dep_exec and dep_exec.status == TaskStatus.FAILED and task_exec.task_config.skip_on_failure:
                    task_exec.status = TaskStatus.SKIPPED
                    workflow.skipped_tasks += 1
                    return False
                # Dependency not satisfied
                return False
        
        return True
    
    def _should_continue_workflow(self, workflow: WorkflowExecution) -> bool:
        """Check if workflow should continue execution."""
        # Check global timeout
        if workflow.global_timeout_at and datetime.utcnow() > workflow.global_timeout_at:
            return False
        
        # Check if there are any pending tasks that can be executed
        pending_tasks = [
            task_id for task_id, task_exec in workflow.tasks.items()
            if task_exec.status == TaskStatus.PENDING
        ]
        
        return len(pending_tasks) > 0
    
    def _substitute_variables(self, text: str, variables: Dict[str, str]) -> str:
        """Substitute variables in text."""
        result = text
        for key, value in variables.items():
            placeholder = f"${{{key}}}"
            result = result.replace(placeholder, value)
        return result
    
    async def _validate_runbook(self, runbook_config: RunbookConfig) -> List[str]:
        """Validate runbook configuration."""
        errors = []
        
        # Check for task ID uniqueness
        task_ids = [task.id for task in runbook_config.tasks]
        if len(task_ids) != len(set(task_ids)):
            errors.append("Task IDs must be unique")
        
        # Check dependencies exist
        all_task_ids = set(task_ids)
        for task in runbook_config.tasks:
            for dep in task.depends_on:
                if dep not in all_task_ids:
                    errors.append(f"Task {task.id} depends on non-existent task {dep}")
        
        # Validate individual task configurations
        for task in runbook_config.tasks:
            if task.task_type == TaskType.UI_AUTOMATION:
                ui_config = UIAutomationConfig(**task.config)
                ui_errors = await self.ui_engine.validate_configuration(ui_config)
                errors.extend([f"Task {task.id}: {error}" for error in ui_errors])
        
        return errors
    
    async def pause_workflow(self, execution_id: str) -> bool:
        """Pause workflow execution."""
        if execution_id in self.active_executions:
            workflow = self.active_executions[execution_id]
            workflow.state = ExecutionState.PAUSED
            logger.info(f"Workflow {execution_id} paused")
            return True
        return False
    
    async def cancel_workflow(self, execution_id: str) -> bool:
        """Cancel workflow execution."""
        if execution_id in self.active_executions:
            workflow = self.active_executions[execution_id]
            workflow.state = ExecutionState.CANCELLED
            workflow.completed_at = datetime.utcnow()
            logger.info(f"Workflow {execution_id} cancelled")
            return True
        return False
    
    def get_workflow_status(self, execution_id: str) -> Optional[WorkflowExecution]:
        """Get current workflow status."""
        return self.active_executions.get(execution_id)
    
    async def cleanup(self):
        """Clean up resources."""
        await self.data_checker.close()
        await self.ui_engine.cleanup()