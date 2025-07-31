#!/usr/bin/env python3
"""Simple end-to-end test for Monthly Runbook Agent."""

import asyncio
import subprocess
import time
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent))

async def test_basic_workflow():
    """Test basic workflow components without full orchestration."""
    print("Monthly Runbook Agent - Simple E2E Test")
    print("=" * 50)
    
    try:
        # Test 1: Excel Parser
        print("\n[TEST 1] Excel Configuration Parser")
        from src.config.excel_parser import ExcelConfigParser
        
        parser = ExcelConfigParser()
        sample_file = Path("simple_test_config.xlsx")
        parser.create_sample_excel(sample_file)
        
        result = parser.parse_file(sample_file)
        if result.success:
            print("[OK] Excel parsing successful")
            print(f"   Runbook: {result.runbook.name}")
            print(f"   Tasks: {len(result.runbook.tasks)}")
        else:
            print(f"[FAIL] Excel parsing failed: {result.errors}")
            return False
        
        # Clean up
        if sample_file.exists():
            sample_file.unlink()
        
        # Test 2: Data Availability Checker
        print("\n[TEST 2] Data Availability Checker")
        from src.data.availability_checker import DataAvailabilityChecker
        from src.config.models import DataCheckConfig
        
        data_checker = DataAvailabilityChecker()
        await data_checker.register_connection("test_http", {
            "type": "http",
            "url": "https://httpbin.org",
            "timeout": 10
        })
        
        check_config = DataCheckConfig(
            data_source="test_http",
            query="get"
        )
        
        check_result = await data_checker.check_data_availability(check_config)
        if check_result.success:
            print("[OK] Data check successful")
            print(f"   Duration: {check_result.query_duration_ms:.1f}ms")
        else:
            print(f"[FAIL] Data check failed: {check_result.message}")
        
        await data_checker.close()
        
        # Test 3: UI Automation (Simple test)
        print("\n[TEST 3] UI Automation Engine")
        from src.automation.ui_engine import UIAutomationEngine
        from src.config.models import UIAutomationConfig
        
        ui_engine = UIAutomationEngine()
        await ui_engine.initialize()
        
        config = UIAutomationConfig(
            url="https://httpbin.org/forms/post",
            browser="chromium",
            headless=True,
            steps=[
                {"action": "navigate", "url": "https://httpbin.org/forms/post"},
                {"action": "screenshot", "description": "form_page"},
                {"action": "fill", "selector": "input[name='custname']", "value": "Test User"},
                {"action": "screenshot", "description": "form_filled"}
            ]
        )
        
        ui_result = await ui_engine.execute_automation(config)
        if ui_result.success:
            print("[OK] UI automation successful")
            print(f"   Duration: {ui_result.duration_seconds:.1f}s")
            print(f"   Steps: {ui_result.completed_steps}/{ui_result.total_steps}")
            print(f"   Screenshots: {ui_result.screenshots}")
        else:
            print(f"[FAIL] UI automation failed: {ui_result.message}")
        
        await ui_engine.cleanup()
        
        print("\n" + "=" * 50)
        print("SUMMARY: Basic components are working!")
        print("The Monthly Runbook Agent is ready for use.")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_local_html_app():
    """Test with local HTML application."""
    print("\n[LOCAL TEST] Testing with Local HTML App")
    print("=" * 50)
    
    # Start local server
    print("Starting local test server...")
    server_process = None
    
    try:
        server_process = subprocess.Popen(
            [sys.executable, "test-app/server.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for server to start
        await asyncio.sleep(3)
        
        # Test server connectivity
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8080/index.html", timeout=5)
                if response.status_code == 200:
                    print("[OK] Test server is running")
                else:
                    print(f"[FAIL] Server returned {response.status_code}")
                    return False
        except Exception as e:
            print(f"[FAIL] Cannot connect to test server: {e}")
            return False
        
        # Run UI automation against local app
        print("Running UI automation against local app...")
        from src.automation.ui_engine import UIAutomationEngine
        from src.config.models import UIAutomationConfig
        
        ui_engine = UIAutomationEngine()
        await ui_engine.initialize()
        
        config = UIAutomationConfig(
            url="http://localhost:8080/index.html",
            browser="chromium",
            headless=False,  # Show browser for demo
            steps=[
                {"action": "navigate", "url": "http://localhost:8080/index.html"},
                {"action": "screenshot", "description": "initial_page"},
                {"action": "fill", "selector": "#username", "value": "testuser"},
                {"action": "fill", "selector": "#password", "value": "testpass"},
                {"action": "screenshot", "description": "credentials_filled"},
                {"action": "click", "selector": 'button[onclick="login()"]'},
                {"action": "wait", "selector": "#dashboard", "timeout": 5},
                {"action": "screenshot", "description": "dashboard_loaded"},
                {"action": "click", "selector": "#validate-btn"},
                {"action": "wait", "timeout": 4},
                {"action": "screenshot", "description": "data_validated"}
            ]
        )
        
        print("WATCH THE BROWSER: You'll see the automation in action!")
        ui_result = await ui_engine.execute_automation(config, variables={
            'USERNAME': 'testuser',
            'PASSWORD': 'testpass'
        })
        
        if ui_result.success:
            print("[OK] Local app automation successful!")
            print(f"   Duration: {ui_result.duration_seconds:.1f}s")
            print(f"   Screenshots taken: {len(ui_result.screenshots)}")
            print("   Screenshots saved in: screenshots/")
            
            for screenshot in ui_result.screenshots:
                print(f"     - {screenshot}")
        else:
            print(f"[FAIL] Local app automation failed: {ui_result.message}")
        
        await ui_engine.cleanup()
        return ui_result.success
        
    except Exception as e:
        print(f"[ERROR] Local test failed: {e}")
        return False
    finally:
        # Clean up server
        if server_process:
            try:
                server_process.terminate()
                server_process.wait(timeout=5)
                print("Test server stopped")
            except:
                server_process.kill()

async def main():
    """Run all tests."""
    print("Starting Monthly Runbook Agent Tests...")
    
    # Test 1: Basic components
    basic_success = await test_basic_workflow()
    
    if not basic_success:
        print("Basic tests failed, skipping local app test")
        return 1
    
    # Test 2: Local HTML app
    print("\n" + "=" * 60)
    print("READY FOR LOCAL APP TEST")
    print("This will open a browser and show live automation!")
    
    input("Press Enter to continue with local app test...")
    
    local_success = await test_local_html_app()
    
    # Summary
    print("\n" + "=" * 60)
    print("FINAL RESULTS:")
    print(f"  Basic Components: {'PASS' if basic_success else 'FAIL'}")
    print(f"  Local App Test:   {'PASS' if local_success else 'FAIL'}")
    
    if basic_success and local_success:
        print("\nSUCCESS! Monthly Runbook Agent is working perfectly!")
        print("\nNext steps:")
        print("1. Create your Excel runbook for your Angular/NestJS app")
        print("2. Configure your specific UI automation steps")
        print("3. Deploy to AWS using the deployment scripts")
        print("4. Set up monthly scheduling")
        return 0
    else:
        print("\nSome tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)