"""Simple test script for Monthly Runbook Agent components."""

import asyncio
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent))

async def test_excel_parser():
    """Test Excel configuration parser."""
    print("\n[TEST] Testing Excel Configuration Parser...")
    
    try:
        from src.config.excel_parser import ExcelConfigParser
        parser = ExcelConfigParser()
        
        # Create a sample Excel file
        sample_file = Path("test_config.xlsx")
        parser.create_sample_excel(sample_file)
        print(f"[OK] Created sample Excel file: {sample_file}")
        
        # Parse the sample file
        result = parser.parse_file(sample_file)
        
        if result.success:
            print("[OK] Excel parsing successful!")
            print(f"   Runbook ID: {result.runbook.id}")
            print(f"   Tasks: {len(result.runbook.tasks)}")
        else:
            print("[FAIL] Excel parsing failed!")
            print(f"   Errors: {result.errors}")
        
        # Clean up
        if sample_file.exists():
            sample_file.unlink()
        
        return result.success
        
    except Exception as e:
        print(f"[ERROR] Excel parser test failed: {e}")
        return False

async def test_ui_engine():
    """Test UI automation engine with Playwright."""
    print("\n[TEST] Testing Playwright UI Engine...")
    
    try:
        from src.automation.ui_engine import UIAutomationEngine
        from src.config.models import UIAutomationConfig
        
        ui_engine = UIAutomationEngine()
        await ui_engine.initialize()
        print("[OK] Playwright initialized successfully!")
        
        # Test configuration validation
        config = UIAutomationConfig(
            url="https://httpbin.org/get",
            browser="chromium",
            headless=True,
            steps=[
                {"action": "navigate", "url": "https://httpbin.org/get"},
                {"action": "wait", "timeout": 2},
                {"action": "screenshot", "description": "httpbin_page"}
            ]
        )
        
        errors = await ui_engine.validate_configuration(config)
        if not errors:
            print("[OK] UI configuration validation passed!")
        else:
            print(f"[FAIL] UI configuration errors: {errors}")
            return False
        
        # Test actual automation
        print("[RUN] Running UI automation test...")
        result = await ui_engine.execute_automation(config)
        
        if result.success:
            print("[OK] UI automation test successful!")
            print(f"   Duration: {result.duration_seconds:.2f}s")
            print(f"   Steps completed: {result.completed_steps}/{result.total_steps}")
            print(f"   Screenshots: {len(result.screenshots)}")
        else:
            print("[FAIL] UI automation test failed!")
            print(f"   Error: {result.message}")
            return False
        
        await ui_engine.cleanup()
        return True
        
    except Exception as e:
        print(f"[ERROR] UI engine test failed: {e}")
        return False

async def test_data_checker():
    """Test data availability checker."""
    print("\n[TEST] Testing Data Availability Checker...")
    
    try:
        from src.data.availability_checker import DataAvailabilityChecker
        from src.config.models import DataCheckConfig
        
        data_checker = DataAvailabilityChecker()
        
        # Register a mock HTTP connection
        await data_checker.register_connection("httpbin_api", {
            "type": "http",
            "url": "https://httpbin.org",
            "timeout": 10
        })
        print("[OK] HTTP connection registered!")
        
        # Test HTTP data check
        check_config = DataCheckConfig(
            data_source="httpbin_api",
            query="get"  # This will be used as endpoint
        )
        
        result = await data_checker.check_data_availability(check_config)
        
        if result.success:
            print("[OK] Data availability check successful!")
            print(f"   Message: {result.message}")
            print(f"   Duration: {result.query_duration_ms:.2f}ms")
        else:
            print("[FAIL] Data availability check failed!")
            print(f"   Error: {result.message}")
            return False
        
        await data_checker.close()
        return True
        
    except Exception as e:
        print(f"[ERROR] Data checker test failed: {e}")
        return False

async def test_imports():
    """Test that all components can be imported."""
    print("\n[TEST] Testing Component Imports...")
    
    try:
        from src.orchestration.workflow_engine import WorkflowOrchestrator
        from src.notifications.notification_service import NotificationService
        from src.monitoring.health_monitor import HealthMonitor
        from src.api.main import app
        
        print("[OK] All components imported successfully!")
        print(f"   FastAPI app: {app.title}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Import test failed: {e}")
        return False

async def main():
    """Run all tests."""
    print("Monthly Runbook Agent Component Tests")
    print("=" * 50)
    
    tests = [
        ("Import Test", test_imports),
        ("Excel Parser", test_excel_parser),
        ("Data Checker", test_data_checker),
        ("UI Engine", test_ui_engine),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"[ERROR] {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Results Summary:")
    
    passed = 0
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1
    
    total = len(results)
    print(f"\nOverall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("SUCCESS: All tests passed! The Monthly Runbook Agent is ready!")
        return 0
    else:
        print("WARNING: Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)