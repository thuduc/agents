"""Example: Angular/NestJS Monthly Process Automation with Playwright"""

async def automate_monthly_angular_process():
    """Example of automating an Angular/NestJS monthly process"""
    
    # This would be defined in your Excel configuration
    angular_steps = [
        # Step 1: Login
        {
            "action": "navigate",
            "url": "https://admin.yourcompany.com/login",
            "description": "Navigate to admin login"
        },
        {
            "action": "fill",
            "selector": "input[formControlName='username']",  # Angular reactive form
            "value": "${SERVICE_ACCOUNT_USERNAME}",
            "description": "Enter username"
        },
        {
            "action": "fill", 
            "selector": "input[formControlName='password']",
            "value": "${SERVICE_ACCOUNT_PASSWORD}",
            "description": "Enter password"
        },
        {
            "action": "click",
            "selector": "button[type='submit']",
            "description": "Click login button"
        },
        
        # Step 2: Wait for Angular routing
        {
            "action": "wait",
            "selector": "app-dashboard",  # Angular component
            "timeout": 10,
            "description": "Wait for dashboard to load"
        },
        {
            "action": "screenshot",
            "description": "dashboard_loaded"
        },
        
        # Step 3: Navigate to monthly reports
        {
            "action": "click",
            "selector": "[routerLink='/reports']",  # Angular router link
            "description": "Navigate to reports section"
        },
        {
            "action": "wait",
            "selector": "app-reports",
            "timeout": 5
        },
        
        # Step 4: Start monthly process
        {
            "action": "click",
            "selector": "[data-testid='generate-monthly-report']",
            "description": "Start monthly report generation"
        },
        
        # Step 5: Wait for NestJS API call to complete
        {
            "action": "wait_for_text",
            "selector": ".process-status",
            "expected_text": "Generation Started",
            "timeout": 10,
            "description": "Confirm process started"
        },
        {
            "action": "screenshot",
            "description": "process_started"
        },
        
        # Step 6: Wait for long-running process (your NestJS background job)
        {
            "action": "wait_for_text",
            "selector": ".process-status",
            "expected_text": "Report Ready",
            "timeout": 1800,  # 30 minutes max
            "description": "Wait for report generation to complete"
        },
        
        # Step 7: Download the report
        {
            "action": "click",
            "selector": "[data-testid='download-report']",
            "description": "Download generated report"
        },
        {
            "action": "wait",
            "timeout": 5,
            "description": "Wait for download to start"
        },
        
        # Step 8: Verify success
        {
            "action": "assert_visible",
            "selector": ".success-message",
            "description": "Verify success message appears"
        },
        {
            "action": "screenshot",
            "description": "final_success"
        }
    ]
    
    return angular_steps


# Example of handling Angular-specific challenges
async def handle_angular_challenges(page):
    """Handle common Angular automation challenges"""
    
    # 1. Wait for Angular to bootstrap
    await page.wait_for_function("window.ng && window.ng.probe")
    
    # 2. Wait for HTTP requests to complete
    await page.wait_for_load_state("networkidle")
    
    # 3. Handle Angular Material components
    await page.click("mat-select")  # Opens dropdown
    await page.click("mat-option[value='monthly']")  # Selects option
    
    # 4. Handle Angular forms validation
    await page.fill("input[formControlName='reportType']", "monthly")
    await page.wait_for_selector(".mat-form-field:not(.mat-form-field-invalid)")
    
    # 5. Handle Angular routing
    await page.click("[routerLink='/reports']")
    await page.wait_for_url("**/reports")
    
    # 6. Handle lazy-loaded modules
    await page.wait_for_selector("app-reports", state="attached")


# Example of NestJS API integration monitoring
async def monitor_nestjs_api_calls(page):
    """Monitor NestJS API calls during UI automation"""
    
    api_calls = []
    
    # Intercept network requests
    async def handle_request(request):
        if "/api/" in request.url:
            api_calls.append({
                "url": request.url,
                "method": request.method,
                "timestamp": datetime.now()
            })
    
    async def handle_response(response):
        if "/api/" in response.url:
            print(f"API Response: {response.status} - {response.url}")
            
            # Log specific monthly process API
            if "/api/reports/monthly" in response.url:
                if response.status == 200:
                    print("✅ Monthly report API call successful")
                else:
                    print(f"❌ Monthly report API failed: {response.status}")
    
    page.on("request", handle_request)
    page.on("response", handle_response)
    
    return api_calls


# Example error handling for Angular/NestJS automation
async def handle_automation_errors(page, step, error):
    """Handle common Angular/NestJS automation errors"""
    
    error_data = {
        "step": step,
        "error": str(error),
        "timestamp": datetime.now(),
        "url": page.url,
        "screenshot": None,
        "console_logs": [],
        "network_errors": []
    }
    
    try:
        # Take failure screenshot
        screenshot_path = f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        error_data["screenshot"] = screenshot_path
        
        # Capture console errors
        console_logs = await page.evaluate("""
            () => {
                const logs = [];
                const originalLog = console.log;
                const originalError = console.error;
                
                // Get any stored console messages
                if (window.__console_logs) {
                    return window.__console_logs;
                }
                return [];
            }
        """)
        error_data["console_logs"] = console_logs
        
        # Check for Angular errors
        angular_errors = await page.evaluate("""
            () => {
                // Check for Angular error handler
                if (window.ng && window.ng.probe) {
                    const debugElement = window.ng.probe(document.body);
                    // Get any Angular-specific error info
                    return debugElement ? "Angular is running" : "Angular not detected";
                }
                return "Angular not loaded";
            }
        """)
        error_data["angular_status"] = angular_errors
        
        # Check for failed network requests
        # This would be collected from the network monitoring above
        
    except Exception as capture_error:
        error_data["capture_error"] = str(capture_error)
    
    return error_data