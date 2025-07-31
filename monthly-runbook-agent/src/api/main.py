"""Main FastAPI application for Monthly Runbook Agent."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
from starlette.responses import Response
from pydantic import BaseModel

from ..config.excel_parser import ExcelConfigParser
from ..config.models import RunbookConfig, ConfigParsingResult
from ..data.availability_checker import DataAvailabilityChecker
from ..automation.ui_engine import UIAutomationEngine
from ..orchestration.workflow_engine import WorkflowOrchestrator, WorkflowExecution
from ..notifications.notification_service import NotificationService
from ..monitoring.health_monitor import HealthMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
data_checker: Optional[DataAvailabilityChecker] = None
ui_engine: Optional[UIAutomationEngine] = None
orchestrator: Optional[WorkflowOrchestrator] = None
notification_service: Optional[NotificationService] = None
health_monitor: Optional[HealthMonitor] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    global data_checker, ui_engine, orchestrator, notification_service, health_monitor
    
    logger.info("Starting Monthly Runbook Agent")
    
    # Initialize services
    data_checker = DataAvailabilityChecker()
    ui_engine = UIAutomationEngine()
    notification_service = NotificationService()
    health_monitor = HealthMonitor(notification_callback=notification_callback)
    
    # Initialize orchestrator with dependencies
    orchestrator = WorkflowOrchestrator(
        data_checker=data_checker,
        ui_engine=ui_engine,
        notification_callback=workflow_notification_callback
    )
    
    # Start health monitoring
    await health_monitor.start_monitoring()
    
    logger.info("Monthly Runbook Agent started successfully")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Monthly Runbook Agent")
    
    if health_monitor:
        await health_monitor.stop_monitoring()
    
    if orchestrator:
        await orchestrator.cleanup()
    
    if ui_engine:
        await ui_engine.cleanup()
    
    if data_checker:
        await data_checker.close()
    
    logger.info("Monthly Runbook Agent shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Monthly Runbook Agent",
    description="Automated agent system for executing monthly production runbooks",
    version="1.0.0",
    lifespan=lifespan
)


# Request/Response models
class RunbookUploadResponse(BaseModel):
    success: bool
    message: str
    runbook_id: Optional[str] = None
    parsing_result: Optional[ConfigParsingResult] = None


class WorkflowStartRequest(BaseModel):
    runbook_id: str
    variables: Optional[Dict[str, str]] = None
    triggered_by: str = "api"


class WorkflowStartResponse(BaseModel):
    success: bool
    message: str
    execution_id: Optional[str] = None
    workflow: Optional[Dict] = None


# Callback functions
async def notification_callback(event_type: str, message: str, priority: str = "normal"):
    """Callback for system notifications."""
    if notification_service:
        from ..notifications.notification_service import NotificationMessage, NotificationChannel
        
        notification = NotificationMessage(
            title=f"System Alert: {event_type}",
            message=message,
            priority=priority,
            channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
            recipients=["ops-team@company.com", "#ops-alerts"]
        )
        
        await notification_service.send_notification(notification)


async def workflow_notification_callback(workflow: WorkflowExecution, event_type: str, additional_info: str = None):
    """Callback for workflow notifications."""
    if notification_service:
        await notification_service.send_workflow_notification(workflow, event_type, additional_info)


# Health check endpoints
@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    if health_monitor:
        status = health_monitor.get_health_status()
        return JSONResponse(
            status_code=200 if status['overall_status'] == 'healthy' else 503,
            content=status
        )
    
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check with all components."""
    if not health_monitor:
        raise HTTPException(status_code=503, detail="Health monitor not available")
    
    return health_monitor.get_health_status()


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics endpoint."""
    if not health_monitor:
        raise HTTPException(status_code=503, detail="Health monitor not available")
    
    metrics = health_monitor.get_prometheus_metrics()
    return Response(content=metrics, media_type="text/plain")


# Configuration management endpoints
@app.post("/runbooks/upload", response_model=RunbookUploadResponse)
async def upload_runbook_config(file: UploadFile = File(...)):
    """Upload and parse Excel runbook configuration."""
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="File must be an Excel file (.xlsx or .xls)")
    
    try:
        # Save uploaded file temporarily
        temp_file = Path(f"/tmp/{file.filename}")
        temp_file.parent.mkdir(exist_ok=True)
        
        with open(temp_file, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Parse configuration
        parser = ExcelConfigParser()
        parsing_result = parser.parse_file(temp_file)
        
        # Clean up temp file
        temp_file.unlink()
        
        if parsing_result.success:
            # Store runbook configuration (in production, this would go to database)
            runbook_id = parsing_result.runbook.id
            
            # Register data connections
            if orchestrator and parsing_result.runbook.connections:
                for name, config in parsing_result.runbook.connections.items():
                    await data_checker.register_connection(name, config)
            
            return RunbookUploadResponse(
                success=True,
                message="Runbook configuration uploaded and parsed successfully",
                runbook_id=runbook_id,
                parsing_result=parsing_result
            )
        else:
            return RunbookUploadResponse(
                success=False,
                message="Failed to parse runbook configuration",
                parsing_result=parsing_result
            )
    
    except Exception as e:
        logger.exception("Error uploading runbook configuration")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get("/runbooks/example")
async def download_example_config():
    """Download example Excel configuration file."""
    example_file = Path("/tmp/example_runbook_config.xlsx")
    
    # Generate example file
    parser = ExcelConfigParser()
    parser.create_sample_excel(example_file)
    
    return FileResponse(
        path=str(example_file),
        filename="example_runbook_config.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# Workflow execution endpoints
@app.post("/workflows/start", response_model=WorkflowStartResponse)
async def start_workflow(request: WorkflowStartRequest, background_tasks: BackgroundTasks):
    """Start workflow execution."""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    
    try:
        # In production, load runbook from database
        # For now, we'll assume it's already loaded
        
        # This is a placeholder - in real implementation, load from storage
        raise HTTPException(status_code=501, detail="Workflow start not fully implemented - need to load runbook from storage")
        
    except Exception as e:
        logger.exception("Error starting workflow")
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {str(e)}")


@app.get("/workflows/{execution_id}")
async def get_workflow_status(execution_id: str):
    """Get workflow execution status."""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    
    workflow = orchestrator.get_workflow_status(execution_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow execution not found")
    
    return {
        "execution_id": workflow.execution_id,
        "runbook_name": workflow.runbook_config.name,
        "state": workflow.state,
        "progress_percentage": workflow.progress_percentage,
        "started_at": workflow.started_at.isoformat() if workflow.started_at else None,
        "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
        "duration_seconds": workflow.duration_seconds,
        "total_tasks": workflow.total_tasks,
        "completed_tasks": workflow.completed_tasks,
        "failed_tasks": workflow.failed_tasks,
        "skipped_tasks": workflow.skipped_tasks,
        "task_status": {
            task_id: {
                "status": task_exec.status,
                "started_at": task_exec.started_at.isoformat() if task_exec.started_at else None,
                "completed_at": task_exec.completed_at.isoformat() if task_exec.completed_at else None,
                "duration_seconds": task_exec.duration_seconds,
                "retry_count": task_exec.retry_count,
                "error_message": task_exec.error_message
            }
            for task_id, task_exec in workflow.tasks.items()
        }
    }


@app.post("/workflows/{execution_id}/cancel")
async def cancel_workflow(execution_id: str):
    """Cancel workflow execution."""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    
    success = await orchestrator.cancel_workflow(execution_id)
    if not success:
        raise HTTPException(status_code=404, detail="Workflow execution not found")
    
    return {"message": f"Workflow {execution_id} cancelled successfully"}


@app.post("/workflows/{execution_id}/pause")
async def pause_workflow(execution_id: str):
    """Pause workflow execution."""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    
    success = await orchestrator.pause_workflow(execution_id)
    if not success:
        raise HTTPException(status_code=404, detail="Workflow execution not found")
    
    return {"message": f"Workflow {execution_id} paused successfully"}


# Data availability endpoints
@app.post("/data/check")
async def check_data_availability(
    data_source: str,
    query: Optional[str] = None,
    expected_count_min: Optional[int] = None,
    expected_count_max: Optional[int] = None,
    freshness_hours: Optional[int] = None
):
    """Check data availability for a specific source."""
    if not data_checker:
        raise HTTPException(status_code=503, detail="Data checker not available")
    
    from ..config.models import DataCheckConfig
    
    check_config = DataCheckConfig(
        data_source=data_source,
        query=query,
        expected_count_min=expected_count_min,
        expected_count_max=expected_count_max,
        freshness_hours=freshness_hours
    )
    
    result = await data_checker.check_data_availability(check_config)
    
    return {
        "success": result.success,
        "message": result.message,
        "data_source": result.data_source,
        "record_count": result.record_count,
        "freshness_minutes": result.freshness_minutes,
        "checked_at": result.checked_at.isoformat(),
        "details": result.details
    }


# UI automation endpoints
@app.post("/ui/test")
async def test_ui_automation(
    url: str,
    browser: str = "chromium",
    headless: bool = True,
    steps: Optional[List[Dict]] = None
):
    """Test UI automation steps."""
    if not ui_engine:
        raise HTTPException(status_code=503, detail="UI engine not available")
    
    from ..config.models import UIAutomationConfig
    
    config = UIAutomationConfig(
        url=url,
        browser=browser,
        headless=headless,
        steps=steps or []
    )
    
    result = await ui_engine.execute_automation(config)
    
    return {
        "success": result.success,
        "message": result.message,
        "duration_seconds": result.duration_seconds,
        "completed_steps": result.completed_steps,
        "total_steps": result.total_steps,
        "screenshots": result.screenshots,
        "console_logs": result.console_logs[-10:] if result.console_logs else []  # Last 10 logs
    }


# Notification endpoints
@app.post("/notifications/test")
async def test_notification(
    title: str,
    message: str,
    channels: List[str],
    recipients: List[str],
    priority: str = "normal"
):
    """Send test notification."""
    if not notification_service:
        raise HTTPException(status_code=503, detail="Notification service not available")
    
    from ..notifications.notification_service import NotificationMessage, NotificationChannel
    
    # Convert string channels to enum
    try:
        channel_enums = [NotificationChannel(ch.lower()) for ch in channels]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid channel: {str(e)}")
    
    notification = NotificationMessage(
        title=title,
        message=message,
        priority=priority,
        channels=channel_enums,
        recipients=recipients
    )
    
    results = await notification_service.send_notification(notification)
    
    return {
        "message": "Test notification sent",
        "results": [
            {
                "success": result.success,
                "channel": result.channel,
                "recipient": result.recipient,
                "message": result.message,
                "error": result.error
            }
            for result in results
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)