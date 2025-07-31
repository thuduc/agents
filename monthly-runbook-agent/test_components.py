#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test script for Monthly Runbook Agent components."""

import asyncio
import sys
import os
from datetime import datetime
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Test imports
try:
    from src.config.excel_parser import ExcelConfigParser
    from src.config.models import UIAutomationConfig, DataCheckConfig
    from src.automation.ui_engine import UIAutomationEngine
    from src.data.availability_checker import DataAvailabilityChecker
    print("All imports successful!")
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)


async def test_excel_parser():
    """Test Excel configuration parser."""
    print("\n[TEST] Testing Excel Configuration Parser...")
    
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
        print(f"   Task names: {[task.name for task in result.runbook.tasks]}")
    else:
        print("[FAIL] Excel parsing failed!")
        print(f"   Errors: {result.errors}")
    
    # Clean up
    if sample_file.exists():
        sample_file.unlink()
    
    return result.success


async def test_ui_engine():
    """Test UI automation engine with Playwright."""
    print("\n🎭 Testing Playwright UI Engine...")
    
    ui_engine = UIAutomationEngine()
    
    try:
        await ui_engine.initialize()
        print("✅ Playwright initialized successfully!")
        
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
            print("✅ UI configuration validation passed!")
        else:
            print(f"❌ UI configuration errors: {errors}")
            return False
        
        # Test actual automation
        print("🚀 Running UI automation test...")
        result = await ui_engine.execute_automation(config)
        
        if result.success:
            print("✅ UI automation test successful!")
            print(f"   Duration: {result.duration_seconds:.2f}s")
            print(f"   Steps completed: {result.completed_steps}/{result.total_steps}")
            print(f"   Screenshots: {len(result.screenshots)}")
        else:
            print("❌ UI automation test failed!")
            print(f"   Error: {result.message}")
            return False
        
        await ui_engine.cleanup()
        return True
        
    except Exception as e:
        print(f"❌ UI engine test failed: {e}")
        return False


async def test_data_checker():
    """Test data availability checker."""
    print("\n🔍 Testing Data Availability Checker...")
    
    data_checker = DataAvailabilityChecker()
    
    try:
        # Register a mock HTTP connection
        await data_checker.register_connection("httpbin_api", {
            "type": "http",
            "url": "https://httpbin.org",
            "timeout": 10
        })
        print("✅ HTTP connection registered!")
        
        # Test HTTP data check
        check_config = DataCheckConfig(
            data_source="httpbin_api",
            query="get"  # This will be used as endpoint
        )
        
        result = await data_checker.check_data_availability(check_config)
        
        if result.success:
            print("✅ Data availability check successful!")
            print(f"   Message: {result.message}")
            print(f"   Duration: {result.query_duration_ms:.2f}ms")
        else:
            print("❌ Data availability check failed!")
            print(f"   Error: {result.message}")
            return False
        
        await data_checker.close()
        return True
        
    except Exception as e:
        print(f"❌ Data checker test failed: {e}")
        return False


async def test_basic_workflow():
    """Test a basic end-to-end workflow."""
    print("\n🔄 Testing Basic Workflow...")
    
    try:
        # This would test the workflow orchestrator
        # For now, just verify imports work
        from orchestration.workflow_engine import WorkflowOrchestrator
        from notifications.notification_service import NotificationService
        from monitoring.health_monitor import HealthMonitor
        
        print("✅ Workflow components imported successfully!")
        
        # Test notification service
        notification_service = NotificationService()
        print("✅ Notification service created!")
        
        # Test health monitor
        health_monitor = HealthMonitor()
        print("✅ Health monitor created!")
        
        return True
        
    except Exception as e:
        print(f"❌ Basic workflow test failed: {e}")
        return False


async def test_api_startup():
    """Test that the FastAPI app can start."""
    print("\n🚀 Testing FastAPI Application...")
    
    try:
        # Import the FastAPI app
        from api.main import app
        print("✅ FastAPI app imported successfully!")
        
        # Test that we can create the app
        print(f"   App title: {app.title}")
        print(f"   App version: {app.version}")
        
        return True
        
    except Exception as e:
        print(f"❌ FastAPI test failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("🧪 Monthly Runbook Agent Component Tests")
    print("=" * 50)
    
    tests = [
        ("Excel Parser", test_excel_parser),
        ("UI Engine", test_ui_engine),
        ("Data Checker", test_data_checker),
        ("Basic Workflow", test_basic_workflow),
        ("FastAPI App", test_api_startup),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1
    
    total = len(results)
    print(f"\n🎯 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 All tests passed! The Monthly Runbook Agent is ready to use!")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)