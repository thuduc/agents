"""Create Excel runbook for local end-to-end testing."""

import json
from pathlib import Path
import pandas as pd
import sys

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent))

def create_local_test_runbook():
    """Create a comprehensive test runbook for local testing."""
    print("Creating local test runbook...")
    
    runbook_file = Path("local_test_runbook.xlsx")
    
    with pd.ExcelWriter(runbook_file, engine='openpyxl') as writer:
        # Runbook sheet - Basic information
        runbook_data = pd.DataFrame([
            ['ID', 'local_test_runbook'],
            ['Name', 'Local End-to-End Test Runbook'],
            ['Description', 'Complete test of Monthly Runbook Agent with local HTML app'],
            ['Version', '1.0.0'],
            ['Owner', 'test-user@local.dev'],
            ['Team', 'Testing Team'],
            ['Environment', 'local'],
            ['Global_Timeout_Minutes', '30'],
            ['Max_Parallel_Tasks', '2'],
            ['Tags', 'test,local,demo,end-to-end']
        ], columns=['Property', 'Value'])
        runbook_data.to_excel(writer, sheet_name='Runbook', index=False)
        
        # Tasks sheet - Define the complete workflow
        tasks_data = pd.DataFrame([
            {
                'ID': 'check_test_server',
                'Name': 'Check Test Server Availability', 
                'Description': 'Verify the local test server is running',
                'Type': 'data_check',
                'Dependencies': '',
                'Timeout_Minutes': 5,
                'Retry_Count': 2,
                'Data_Source': 'test_server',
                'Query': 'index.html',
                'Expected_Count_Min': '',
                'Notify_On_Failure': 'true'
            },
            {
                'ID': 'login_to_dashboard',
                'Name': 'Login to Monthly Process Dashboard',
                'Description': 'Authenticate to the test application',
                'Type': 'ui_automation',
                'Dependencies': 'check_test_server',
                'Timeout_Minutes': 10,
                'Retry_Count': 3,
                'URL': 'http://localhost:8080/index.html',
                'Browser': 'chromium',
                'Headless': 'false',  # Show browser for demo
                'Screenshot_On_Failure': 'true',
                'UI_Steps': json.dumps([
                    {'action': 'navigate', 'url': 'http://localhost:8080/index.html', 'description': 'Navigate to test app'},
                    {'action': 'screenshot', 'description': 'initial_page'},
                    {'action': 'fill', 'selector': '#username', 'value': 'testuser', 'description': 'Enter username'},
                    {'action': 'fill', 'selector': '#password', 'value': 'testpass', 'description': 'Enter password'},
                    {'action': 'screenshot', 'description': 'credentials_entered'},
                    {'action': 'click', 'selector': 'button[onclick="login()"]', 'description': 'Click login button'},
                    {'action': 'wait', 'selector': '#dashboard', 'timeout': 5, 'description': 'Wait for dashboard to load'},
                    {'action': 'screenshot', 'description': 'dashboard_loaded'}
                ])
            },
            {
                'ID': 'validate_data_sources',
                'Name': 'Execute Data Validation',
                'Description': 'Validate monthly data sources in the dashboard',
                'Type': 'ui_automation',
                'Dependencies': 'login_to_dashboard',
                'Timeout_Minutes': 10,
                'Retry_Count': 2,
                'URL': '',
                'Browser': 'chromium',
                'Headless': 'false',
                'Screenshot_On_Failure': 'true',
                'UI_Steps': json.dumps([
                    {'action': 'click', 'selector': '#validate-btn', 'description': 'Click validate data button'},
                    {'action': 'wait_for_text', 'selector': '#data-status', 'expected_text': 'All data sources validated', 'timeout': 10, 'description': 'Wait for validation to complete'},
                    {'action': 'screenshot', 'description': 'data_validated'},
                    {'action': 'assert_text', 'selector': '#transaction-status', 'expected_text': 'Valid', 'description': 'Verify transaction data is valid'},
                    {'action': 'assert_text', 'selector': '#customer-status', 'expected_text': 'Valid', 'description': 'Verify customer data is valid'}
                ])
            },
            {
                'ID': 'execute_monthly_process',
                'Name': 'Start Monthly Process Execution',
                'Description': 'Execute the main monthly process workflow',
                'Type': 'ui_automation',
                'Dependencies': 'validate_data_sources',
                'Timeout_Minutes': 15,
                'Retry_Count': 1,
                'URL': '',
                'Browser': 'chromium',
                'Headless': 'false',
                'Screenshot_On_Failure': 'true',
                'UI_Steps': json.dumps([
                    {'action': 'select', 'selector': '#report-type', 'value': 'detailed', 'description': 'Select detailed report type'},
                    {'action': 'fill', 'selector': '#notification-email', 'value': 'test-results@local.dev', 'description': 'Enter notification email'},
                    {'action': 'screenshot', 'description': 'process_configured'},
                    {'action': 'click', 'selector': '[data-testid="start-monthly-process"]', 'description': 'Start monthly process'},
                    {'action': 'wait_for_text', 'selector': '#process-status', 'expected_text': 'completed successfully', 'timeout': 15, 'description': 'Wait for process completion'},
                    {'action': 'screenshot', 'description': 'process_completed'}
                ])
            },
            {
                'ID': 'verify_results_and_download',
                'Name': 'Verify Results and Download Report',
                'Description': 'Verify the process completed and download the report',
                'Type': 'ui_automation',
                'Dependencies': 'execute_monthly_process',
                'Timeout_Minutes': 5,
                'Retry_Count': 2,
                'URL': '',
                'Browser': 'chromium',
                'Headless': 'false',
                'Screenshot_On_Failure': 'true',
                'UI_Steps': json.dumps([
                    {'action': 'assert_visible', 'selector': '.success-message.show', 'description': 'Verify success message is visible'},
                    {'action': 'assert_text', 'selector': '#results-status', 'expected_text': 'ready for download', 'description': 'Verify results are ready'},
                    {'action': 'screenshot', 'description': 'results_ready'},
                    {'action': 'click', 'selector': '#download-btn', 'description': 'Click download report button'},
                    {'action': 'wait', 'timeout': 2, 'description': 'Wait for download dialog'},
                    {'action': 'screenshot', 'description': 'download_initiated'}
                ])
            },
            {
                'ID': 'send_completion_notification',
                'Name': 'Send Process Completion Notification',
                'Description': 'Send notification about successful completion',
                'Type': 'ui_automation',
                'Dependencies': 'verify_results_and_download',
                'Timeout_Minutes': 5,
                'Retry_Count': 1,
                'URL': '',
                'Browser': 'chromium',
                'Headless': 'false',
                'Screenshot_On_Failure': 'true',
                'UI_Steps': json.dumps([
                    {'action': 'click', 'selector': '#send-notification-btn', 'description': 'Send completion notification'},
                    {'action': 'wait', 'timeout': 2, 'description': 'Wait for notification confirmation'},
                    {'action': 'screenshot', 'description': 'notification_sent'},
                    {'action': 'click', 'selector': 'button[onclick="logout()"]', 'description': 'Logout from application'},
                    {'action': 'wait', 'selector': '#login-form', 'timeout': 3, 'description': 'Wait for login form to appear'},
                    {'action': 'screenshot', 'description': 'logged_out'}
                ])
            }
        ])
        tasks_data.to_excel(writer, sheet_name='Tasks', index=False)
        
        # Schedule sheet - Run immediately for testing
        schedule_data = pd.DataFrame([
            ['Enabled', 'false'],  # Disabled for manual testing
            ['Timezone', 'UTC'],
            ['Skip_Holidays', 'false']
        ], columns=['Property', 'Value'])
        schedule_data.to_excel(writer, sheet_name='Schedule', index=False)
        
        # Connections sheet - Define the test server connection
        connections_data = pd.DataFrame([
            {
                'Name': 'test_server',
                'Type': 'http',
                'Host': 'localhost',
                'Port': '8080',
                'URL': 'http://localhost:8080',
                'Config_JSON': json.dumps({
                    'timeout': 10,
                    'headers': {'User-Agent': 'Monthly-Runbook-Agent/1.0'}
                })
            }
        ])
        connections_data.to_excel(writer, sheet_name='Connections', index=False)
        
        # Notifications sheet - Local testing notifications
        notifications_data = pd.DataFrame([
            ['Channels', 'email'],
            ['Message_Template', 'Local Test Runbook: {status} | Duration: {duration} | Tasks: {completed}/{total}'],
            ['Recipients', 'test@local.dev'],
            ['Priority', 'normal'],
            ['Include_Details', 'true']
        ], columns=['Property', 'Value'])
        notifications_data.to_excel(writer, sheet_name='Notifications', index=False)
    
    print(f"✅ Created test runbook: {runbook_file}")
    return runbook_file

if __name__ == "__main__":
    create_local_test_runbook()