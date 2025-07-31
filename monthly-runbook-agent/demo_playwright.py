"""Demonstrate Playwright automation for Monthly Runbook Agent."""

import asyncio
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent))

async def demo_ui_automation():
    """Demonstrate UI automation capabilities."""
    print("Monthly Runbook Agent - Playwright Demo")
    print("=" * 50)
    
    try:
        from src.automation.ui_engine import UIAutomationEngine
        from src.config.models import UIAutomationConfig
        
        # Initialize UI engine
        ui_engine = UIAutomationEngine()
        await ui_engine.initialize()
        print("[OK] Playwright initialized")
        
        # Demo 1: Simple web page automation
        print("\n[DEMO 1] Basic Web Automation")
        config1 = UIAutomationConfig(
            url="https://httpbin.org/forms/post",
            browser="chromium",
            headless=True,
            steps=[
                {"action": "navigate", "url": "https://httpbin.org/forms/post"},
                {"action": "screenshot", "description": "initial_page"},
                {"action": "fill", "selector": "input[name='custname']", "value": "Monthly Runbook Agent"},
                {"action": "fill", "selector": "input[name='custtel']", "value": "555-1234"},
                {"action": "fill", "selector": "input[name='custemail']", "value": "agent@company.com"},
                {"action": "select", "selector": "select[name='size']", "value": "large"},
                {"action": "screenshot", "description": "form_filled"},
                {"action": "wait", "timeout": 1}
            ]
        )
        
        result1 = await ui_engine.execute_automation(config1)
        if result1.success:
            print(f"[OK] Form automation completed in {result1.duration_seconds:.2f}s")
            print(f"[OK] Steps: {result1.completed_steps}/{result1.total_steps}")
            print(f"[OK] Screenshots: {result1.screenshots}")
        else:
            print(f"[FAIL] Automation failed: {result1.message}")
        
        # Demo 2: Wait for dynamic content
        print("\n[DEMO 2] Dynamic Content Handling")
        config2 = UIAutomationConfig(
            url="https://httpbin.org/delay/2",
            browser="chromium", 
            headless=True,
            steps=[
                {"action": "navigate", "url": "https://httpbin.org/delay/2"},
                {"action": "wait", "timeout": 3},
                {"action": "screenshot", "description": "delayed_content"},
            ]
        )
        
        result2 = await ui_engine.execute_automation(config2)
        if result2.success:
            print(f"[OK] Dynamic content handling completed in {result2.duration_seconds:.2f}s")
        else:
            print(f"[FAIL] Dynamic content failed: {result2.message}")
        
        # Demo 3: Error handling
        print("\n[DEMO 3] Error Handling")
        config3 = UIAutomationConfig(
            url="https://httpbin.org/status/404",
            browser="chromium",
            headless=True,
            screenshot_on_failure=True,
            steps=[
                {"action": "navigate", "url": "https://httpbin.org/status/404"},
                {"action": "wait_for_text", "selector": "body", "expected_text": "This will not exist", "timeout": 2}
            ]
        )
        
        result3 = await ui_engine.execute_automation(config3)
        if not result3.success:
            print(f"[OK] Error handling worked as expected")
            print(f"[OK] Failed at step: {result3.failed_step + 1 if result3.failed_step is not None else 'Unknown'}")
            print(f"[OK] Error screenshots: {result3.screenshots}")
        else:
            print(f"[UNEXPECTED] Should have failed but didn't")
        
        await ui_engine.cleanup()
        
        # Summary
        print("\n" + "=" * 50)
        print("Playwright Demo Summary:")
        print(f"✓ Basic form automation: {'PASS' if result1.success else 'FAIL'}")
        print(f"✓ Dynamic content: {'PASS' if result2.success else 'FAIL'}")
        print(f"✓ Error handling: {'PASS' if not result3.success else 'FAIL'}")
        print("\nPlaywright is ready for your Angular/NestJS automation!")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Demo failed: {e}")
        return False

async def demo_excel_config():
    """Demonstrate Excel configuration parsing."""
    print("\n" + "=" * 50)
    print("Excel Configuration Demo")
    print("=" * 50)
    
    try:
        from src.config.excel_parser import ExcelConfigParser
        
        parser = ExcelConfigParser()
        
        # Create sample Excel file
        sample_file = Path("monthly_runbook_demo.xlsx")
        parser.create_sample_excel(sample_file)
        print(f"[OK] Created sample runbook: {sample_file}")
        
        # Parse it
        result = parser.parse_file(sample_file)
        
        if result.success:
            runbook = result.runbook
            print(f"[OK] Parsed runbook: {runbook.name}")
            print(f"[OK] Owner: {runbook.owner}")
            print(f"[OK] Tasks: {len(runbook.tasks)}")
            
            print("\nTask Details:")
            for i, task in enumerate(runbook.tasks, 1):
                print(f"  {i}. {task.name} ({task.task_type})")
                if task.depends_on:
                    print(f"     Depends on: {', '.join(task.depends_on)}")
                print(f"     Timeout: {task.timeout_minutes} minutes")
            
            if runbook.schedule:
                print(f"\nScheduling:")
                print(f"  Enabled: {runbook.schedule.enabled}")
                if runbook.schedule.day_of_month:
                    print(f"  Day of month: {runbook.schedule.day_of_month}")
                if runbook.schedule.time_of_day:
                    print(f"  Time: {runbook.schedule.time_of_day}")
            
        else:
            print(f"[FAIL] Parsing failed: {result.errors}")
        
        # Clean up
        if sample_file.exists():
            sample_file.unlink()
        
        return result.success
        
    except Exception as e:
        print(f"[ERROR] Excel demo failed: {e}")
        return False

async def main():
    """Run the demo."""
    success = True
    
    # Demo Excel configuration
    excel_success = await demo_excel_config()
    success = success and excel_success
    
    # Demo Playwright automation
    playwright_success = await demo_ui_automation()
    success = success and playwright_success
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 SUCCESS! Monthly Runbook Agent is working!")
        print("\nNext steps:")
        print("1. Create your Excel runbook configuration")
        print("2. Define your Angular/NestJS UI automation steps")
        print("3. Start the FastAPI service: python -m uvicorn src.api.main:app")
        print("4. Upload your runbook and start automation!")
    else:
        print("❌ Some demos failed. Check the output above.")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)