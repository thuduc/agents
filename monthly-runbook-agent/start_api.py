"""Start the Monthly Runbook Agent API server."""

import uvicorn
from pathlib import Path
import sys

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent))

def main():
    """Start the FastAPI server."""
    print("Starting Monthly Runbook Agent API Server...")
    print("Access the API at: http://localhost:8000")
    print("API Documentation: http://localhost:8000/docs")
    print("Health Check: http://localhost:8000/health")
    print("\nPress Ctrl+C to stop the server")
    
    try:
        uvicorn.run(
            "src.api.main:app",
            host="0.0.0.0",
            port=8000,
            log_level="info",
            reload=False
        )
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Error starting server: {e}")

if __name__ == "__main__":
    main()