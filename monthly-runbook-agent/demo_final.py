#!/usr/bin/env python3
"""Final demonstration of Monthly Runbook Agent."""

import asyncio
import subprocess
import sys
import webbrowser
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent))

async def run_live_demo():
    """Run a live demonstration of the Monthly Runbook Agent."""
    print("Monthly Runbook Agent - Live Demo")
    print("=" * 50)
    print("This demo will show you the complete workflow:")
    print("1. Start a local test web application")
    print("2. Run browser automation to interact with it")
    print("3. Show you exactly how it works with your Angular/NestJS app")
    print()
    
    # Start the test server
    print("Starting local test server...")
    server_process = subprocess.Popen(
        [sys.executable, "test-app/server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    try:
        # Wait for server to start
        await asyncio.sleep(3)
        
        # Open browser to show the test app
        print("Opening test application in browser...")
        webbrowser.open('http://localhost:8080/index.html')
        
        print("\nYou should see a 'Monthly Process Dashboard' webpage.")
        print("This simulates your Angular/NestJS application.")
        print()
        print("Now, let's run automation to interact with it...")
        print("WATCH THE BROWSER - you'll see it working automatically!")
        
        await asyncio.sleep(3)
        
        # Run the automation
        from src.automation.ui_engine import UIAutomationEngine
        from src.config.models import UIAutomationConfig
        
        ui_engine = UIAutomationEngine()
        await ui_engine.initialize()
        
        print("\nStarting automation (browser will open)...")
        
        config = UIAutomationConfig(
            url="http://localhost:8080/index.html",
            browser="chromium",
            headless=False,  # Show browser for demo
            steps=[
                {"action": "navigate", "url": "http://localhost:8080/index.html", "description": "Open the application"},
                {"action": "screenshot", "description": "initial_page"},
                {"action": "wait", "timeout": 2, "description": "Wait for page to fully load"},
                
                # Login process
                {"action": "fill", "selector": "#username", "value": "demo-user", "description": "Enter username"},
                {"action": "wait", "timeout": 1},
                {"action": "fill", "selector": "#password", "value": "demo-pass", "description": "Enter password"},
                {"action": "screenshot", "description": "credentials_entered"},
                {"action": "click", "selector": 'button[onclick="login()"]', "description": "Click login button"},
                {"action": "wait", "selector": "#dashboard", "timeout": 5, "description": "Wait for dashboard"},
                {"action": "screenshot", "description": "logged_in"},
                
                # Data validation step
                {"action": "wait", "timeout": 2, "description": "Pause to show dashboard"},
                {"action": "click", "selector": "#validate-btn", "description": "Start data validation"},
                {"action": "wait", "timeout": 4, "description": "Wait for validation to complete"},
                {"action": "screenshot", "description": "data_validated"},
                
                # Monthly process
                {"action": "select", "selector": "#report-type", "value": "detailed", "description": "Select report type"},
                {"action": "fill", "selector": "#notification-email", "value": "demo@company.com", "description": "Set notification email"},
                {"action": "screenshot", "description": "process_configured"},
                {"action": "click", "selector": '[data-testid="start-monthly-process"]', "description": "Start monthly process"},
                {"action": "wait", "timeout": 12, "description": "Wait for process to complete"},
                {"action": "screenshot", "description": "process_completed"},
                
                # Verify results
                {"action": "assert_visible", "selector": ".success-message.show", "description": "Check success message"},
                {"action": "click", "selector": "#download-btn", "description": "Download report"},
                {"action": "wait", "timeout": 2},
                {"action": "screenshot", "description": "report_downloaded"},
                
                # Final step
                {"action": "click", "selector": 'button[onclick="logout()"]', "description": "Logout"},
                {"action": "wait", "selector": "#login-form", "timeout": 3, "description": "Confirm logout"},
                {"action": "screenshot", "description": "logged_out"}
            ]
        )
        
        result = await ui_engine.execute_automation(config)
        
        if result.success:
            print(f"\nSUCCESS! Automation completed in {result.duration_seconds:.1f} seconds")
            print(f"Steps completed: {result.completed_steps}/{result.total_steps}")
            print(f"Screenshots saved: {len(result.screenshots)}")
            print("\nScreenshots saved:")
            for screenshot in result.screenshots:
                print(f"  - {screenshot}")
            
            print("\n" + "=" * 60)
            print("WHAT YOU JUST SAW:")
            print("1. Automated login to web application")
            print("2. Automated data validation process")
            print("3. Automated monthly process execution")
            print("4. Automated report download")
            print("5. Automated logout")
            print()
            print("THIS IS EXACTLY HOW IT WILL WORK WITH YOUR ANGULAR/NESTJS APP!")
            print()
            print("Next steps for your production setup:")
            print("1. Replace the test URL with your Angular app URL")
            print("2. Update the selectors for your specific UI elements")
            print("3. Add your authentication credentials")
            print("4. Configure the monthly process steps")
            print("5. Set up email/Slack notifications")
            print("6. Deploy to AWS for automatic scheduling")
            
        else:
            print(f"Automation failed: {result.message}")
            if result.failed_step is not None:
                print(f"Failed at step: {result.failed_step + 1}")
        
        await ui_engine.cleanup()
        
    except Exception as e:
        print(f"Demo failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up server
        try:
            server_process.terminate()
            server_process.wait(timeout=5)
            print("\nTest server stopped")
        except:
            server_process.kill()
            print("\nTest server force stopped")

if __name__ == "__main__":
    print("MONTHLY RUNBOOK AGENT - LIVE DEMONSTRATION")
    print("This will show you browser automation in action!")
    print()
    print("Make sure to watch the browser window that opens.")
    print("You'll see the automation working step by step.")
    print()
    
    try:
        asyncio.run(run_live_demo())
    except KeyboardInterrupt:
        print("\nDemo interrupted by user")
    
    print("\nDemo complete! The Monthly Runbook Agent is ready for your use.")