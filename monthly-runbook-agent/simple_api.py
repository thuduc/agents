"""Simple API demo for Monthly Runbook Agent."""

from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from datetime import datetime
from pathlib import Path
import sys

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent))

app = FastAPI(
    title="Monthly Runbook Agent",
    description="Automated agent system for executing monthly production runbooks",
    version="1.0.0"
)

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    message: str
    version: str

class RunbookUploadResponse(BaseModel):
    success: bool
    message: str
    filename: str = None
    tasks: int = None

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        message="Monthly Runbook Agent is running",
        version="1.0.0"
    )

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Monthly Runbook Agent API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

@app.post("/runbooks/upload", response_model=RunbookUploadResponse)
async def upload_runbook_config(file: UploadFile = File(...)):
    """Upload and parse Excel runbook configuration."""
    if not file.filename.endswith(('.xlsx', '.xls')):
        return RunbookUploadResponse(
            success=False,
            message="File must be an Excel file (.xlsx or .xls)"
        )
    
    try:
        from src.config.excel_parser import ExcelConfigParser
        
        # Save uploaded file temporarily
        temp_file = Path(f"temp_{file.filename}")
        
        with open(temp_file, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Parse configuration
        parser = ExcelConfigParser()
        result = parser.parse_file(temp_file)
        
        # Clean up temp file
        if temp_file.exists():
            temp_file.unlink()
        
        if result.success:
            return RunbookUploadResponse(
                success=True,
                message=f"Runbook '{result.runbook.name}' uploaded successfully",
                filename=file.filename,
                tasks=len(result.runbook.tasks)
            )
        else:
            return RunbookUploadResponse(
                success=False,
                message=f"Parsing failed: {'; '.join(result.errors)}",
                filename=file.filename
            )
    
    except Exception as e:
        return RunbookUploadResponse(
            success=False,
            message=f"Upload failed: {str(e)}",
            filename=file.filename
        )

@app.get("/runbooks/example")
async def download_example_config():
    """Download example Excel configuration file."""
    from src.config.excel_parser import ExcelConfigParser
    from fastapi.responses import FileResponse
    
    example_file = Path("example_runbook_config.xlsx")
    
    # Generate example file
    parser = ExcelConfigParser()
    parser.create_sample_excel(example_file)
    
    return FileResponse(
        path=str(example_file),
        filename="example_runbook_config.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.post("/ui/test")
async def test_ui_automation(
    url: str,
    browser: str = "chromium",
    headless: bool = True
):
    """Test UI automation with a simple navigation."""
    try:
        from src.automation.ui_engine import UIAutomationEngine
        from src.config.models import UIAutomationConfig
        
        ui_engine = UIAutomationEngine()
        await ui_engine.initialize()
        
        config = UIAutomationConfig(
            url=url,
            browser=browser,
            headless=headless,
            steps=[
                {"action": "navigate", "url": url},
                {"action": "wait", "timeout": 2},
                {"action": "screenshot", "description": "test_page"}
            ]
        )
        
        result = await ui_engine.execute_automation(config)
        await ui_engine.cleanup()
        
        return {
            "success": result.success,
            "message": result.message,
            "duration_seconds": result.duration_seconds,
            "screenshots": result.screenshots
        }
    
    except Exception as e:
        return {
            "success": False,
            "message": f"UI test failed: {str(e)}"
        }

if __name__ == "__main__":
    import uvicorn
    print("Starting Monthly Runbook Agent API Server...")
    print("Access the API at: http://localhost:8000")
    print("API Documentation: http://localhost:8000/docs")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")