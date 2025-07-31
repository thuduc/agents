#!/usr/bin/env python3
"""Quick test to verify Monthly Runbook Agent is working."""

import asyncio
import sys
from pathlib import Path

# Add src to Python path  
sys.path.insert(0, str(Path(__file__).parent))

async def quick_verification():
    """Quick verification that all components work."""
    print("QUICK VERIFICATION TEST")
    print("=" * 30)
    
    success_count = 0
    total_tests = 4
    
    # Test 1: Imports
    print("1. Testing imports...")
    try:
        from src.config.excel_parser import ExcelConfigParser
        from src.automation.ui_engine import UIAutomationEngine
        from src.data.availability_checker import DataAvailabilityChecker
        print("   ✅ All imports successful")
        success_count += 1
    except Exception as e:
        print(f"   ❌ Import failed: {e}")
    
    # Test 2: Excel parsing
    print("2. Testing Excel configuration...")
    try:
        parser = ExcelConfigParser()
        test_file = Path("verification_test.xlsx")
        parser.create_sample_excel(test_file)
        result = parser.parse_file(test_file)
        
        if result.success:
            print(f"   ✅ Excel parsing works ({len(result.runbook.tasks)} tasks found)")
            success_count += 1
        else:
            print("   ❌ Excel parsing failed")
        
        # Clean up
        if test_file.exists():
            test_file.unlink()
            
    except Exception as e:
        print(f"   ❌ Excel test failed: {e}")
    
    # Test 3: Data checker
    print("3. Testing data availability checker...")
    try:
        from src.config.models import DataCheckConfig
        
        checker = DataAvailabilityChecker()
        await checker.register_connection("test", {
            "type": "http",
            "url": "https://httpbin.org"
        })
        
        config = DataCheckConfig(data_source="test", query="get")
        result = await checker.check_data_availability(config)
        
        if result.success:
            print(f"   ✅ Data checker works ({result.query_duration_ms:.0f}ms)")
            success_count += 1
        else:
            print("   ❌ Data checker failed")
            
        await checker.close()
        
    except Exception as e:
        print(f"   ❌ Data checker test failed: {e}")
    
    # Test 4: UI Engine (basic initialization)
    print("4. Testing UI automation engine...")
    try:
        ui_engine = UIAutomationEngine()
        await ui_engine.initialize()
        print("   ✅ Playwright initialized successfully")
        await ui_engine.cleanup()
        success_count += 1
    except Exception as e:
        print(f"   ❌ UI engine test failed: {e}")
    
    # Results
    print("\n" + "=" * 30)
    print(f"RESULTS: {success_count}/{total_tests} tests passed")
    
    if success_count == total_tests:
        print("🎉 ALL SYSTEMS GO!")
        print("Your Monthly Runbook Agent is fully functional!")
    elif success_count >= 3:
        print("✅ MOSTLY WORKING!")
        print("The core system is functional with minor issues.")
    else:
        print("⚠️ SOME ISSUES FOUND")
        print("The system needs some attention before production use.")
    
    print("\nNext steps:")
    print("1. Create your Excel runbook configuration")
    print("2. Test with your Angular/NestJS application")
    print("3. Deploy to AWS for production use")
    
    return success_count == total_tests

if __name__ == "__main__":
    try:
        success = asyncio.run(quick_verification()) 
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Verification failed: {e}")
        sys.exit(1)