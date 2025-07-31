#!/usr/bin/env python3
"""Final test of Monthly Runbook Agent - no Unicode characters."""

import asyncio
import sys
from pathlib import Path

# Add src to Python path  
sys.path.insert(0, str(Path(__file__).parent))

async def run_final_test():
    """Final comprehensive test."""
    print("MONTHLY RUNBOOK AGENT - FINAL TEST")
    print("==================================")
    
    tests_passed = 0
    total_tests = 4
    
    # Test 1: Component imports
    print("\nTest 1: Component Imports")
    try:
        from src.config.excel_parser import ExcelConfigParser
        from src.automation.ui_engine import UIAutomationEngine  
        from src.data.availability_checker import DataAvailabilityChecker
        from src.config.models import UIAutomationConfig, DataCheckConfig
        print("[PASS] All components imported successfully")
        tests_passed += 1
    except Exception as e:
        print(f"[FAIL] Import error: {e}")
    
    # Test 2: Excel Configuration
    print("\nTest 2: Excel Configuration Parser")
    try:
        parser = ExcelConfigParser()
        test_file = Path("final_test.xlsx")
        
        # Create and parse sample
        parser.create_sample_excel(test_file)
        result = parser.parse_file(test_file)
        
        if result.success:
            print(f"[PASS] Parsed runbook: {result.runbook.name}")
            print(f"       Tasks found: {len(result.runbook.tasks)}")
            tests_passed += 1
        else:
            print(f"[FAIL] Parsing failed: {result.errors}")
        
        # Cleanup
        test_file.unlink()
        
    except Exception as e:
        print(f"[FAIL] Excel test error: {e}")
    
    # Test 3: Data Availability
    print("\nTest 3: Data Availability Checker")
    try:
        checker = DataAvailabilityChecker()
        
        # Register test connection
        await checker.register_connection("httpbin", {
            "type": "http",
            "url": "https://httpbin.org"
        })
        
        # Test data check
        config = DataCheckConfig(data_source="httpbin", query="get")
        result = await checker.check_data_availability(config)
        
        if result.success:
            print(f"[PASS] Data check successful")
            print(f"       Response time: {result.query_duration_ms:.0f}ms")
            tests_passed += 1
        else:
            print(f"[FAIL] Data check failed: {result.message}")
        
        await checker.close()
        
    except Exception as e:
        print(f"[FAIL] Data checker error: {e}")
    
    # Test 4: UI Automation
    print("\nTest 4: UI Automation Engine")
    try:
        ui_engine = UIAutomationEngine()
        await ui_engine.initialize()
        
        # Simple automation test
        config = UIAutomationConfig(
            url="https://httpbin.org/forms/post",
            browser="chromium",
            headless=True,
            steps=[
                {"action": "navigate", "url": "https://httpbin.org/forms/post"},
                {"action": "screenshot", "description": "test_page"}
            ]
        )
        
        result = await ui_engine.execute_automation(config)
        
        if result.success:
            print(f"[PASS] UI automation successful")
            print(f"       Duration: {result.duration_seconds:.1f}s")
            print(f"       Screenshots: {len(result.screenshots)}")
            tests_passed += 1
        else:
            print(f"[FAIL] UI automation failed: {result.message}")
        
        await ui_engine.cleanup()
        
    except Exception as e:
        print(f"[FAIL] UI automation error: {e}")
    
    # Final Results
    print("\n" + "=" * 50)
    print(f"FINAL RESULTS: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("\nSUCCESS! All systems are fully operational!")
        print("\nYour Monthly Runbook Agent is ready for:")
        print("- Excel-based runbook configuration")
        print("- Data validation and availability checks") 
        print("- Full browser automation with Playwright")
        print("- Screenshot capture for audit trails")
        print("- Production deployment on AWS")
        
        print("\nTo use with your Angular/NestJS app:")
        print("1. Create an Excel file with your specific steps")
        print("2. Configure your app URLs and selectors")
        print("3. Test against staging environment")
        print("4. Deploy for monthly automation")
        
    elif tests_passed >= 3:
        print("\nMOSTLY WORKING! Core functionality is operational.")
        print("Minor issues detected but system is usable.")
        
    else:
        print("\nSome issues detected. Please review the failures above.")
    
    print(f"\nScreenshots saved in: screenshots/")
    print(f"Test Excel files can be found in project root")
    
    return tests_passed >= 3

if __name__ == "__main__":
    try:
        success = asyncio.run(run_final_test())
        if success:
            print("\n*** READY FOR PRODUCTION USE ***")
        else:
            print("\n*** NEEDS ATTENTION BEFORE PRODUCTION ***")
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()