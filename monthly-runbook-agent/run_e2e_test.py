#!/usr/bin/env python3
"""End-to-end test runner for Monthly Runbook Agent."""

import asyncio
import subprocess
import time
import sys
import signal
from pathlib import Path
import webbrowser
from datetime import datetime

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent))

class E2ETestRunner:
    def __init__(self):
        self.test_server_process = None
        self.base_path = Path(__file__).parent
        
    async def setup_test_environment(self):
        """Set up the test environment."""
        print("🚀 Setting up End-to-End Test Environment")
        print("=" * 60)
        
        # 1. Create the test runbook
        print("📊 Creating test runbook...")
        subprocess.run([sys.executable, "create_test_runbook.py"], 
                      cwd=self.base_path, check=True)
        
        # 2. Start the test server
        print("🌐 Starting test web server...")
        self.test_server_process = subprocess.Popen(
            [sys.executable, "test-app/server.py"],
            cwd=self.base_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for server to start
        print("⏳ Waiting for test server to start...")
        await asyncio.sleep(3)
        
        # 3. Verify server is running
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8080/index.html", timeout=5)
                if response.status_code == 200:
                    print("✅ Test server is running at http://localhost:8080")
                else:
                    raise Exception(f"Server returned status {response.status_code}")
        except Exception as e:
            print(f"❌ Failed to verify test server: {e}")
            return False
        
        return True
    
    async def run_runbook_automation(self):
        """Execute the runbook automation."""
        print("\n🤖 Starting Runbook Automation")
        print("=" * 60)
        
        try:
            # Import our components
            from src.config.excel_parser import ExcelConfigParser
            from src.orchestration.workflow_engine import WorkflowOrchestrator
            from src.data.availability_checker import DataAvailabilityChecker
            from src.automation.ui_engine import UIAutomationEngine
            from src.notifications.notification_service import NotificationService
            
            # Parse the runbook
            print("📋 Parsing runbook configuration...")
            parser = ExcelConfigParser()
            runbook_file = self.base_path / "local_test_runbook.xlsx"
            
            if not runbook_file.exists():
                raise FileNotFoundError(f"Runbook file not found: {runbook_file}")
            
            result = parser.parse_file(runbook_file)
            
            if not result.success:
                print(f"❌ Failed to parse runbook: {result.errors}")
                return False
            
            runbook = result.runbook
            print(f"✅ Parsed runbook: {runbook.name}")
            print(f"   📝 Tasks: {len(runbook.tasks)}")
            print(f"   👤 Owner: {runbook.owner}")
            
            # Initialize services
            print("\n🔧 Initializing services...")
            data_checker = DataAvailabilityChecker()
            ui_engine = UIAutomationEngine()
            notification_service = NotificationService()
            
            # Register connections
            print("🔌 Registering data connections...")
            for name, config in runbook.connections.items():
                await data_checker.register_connection(name, config)
                print(f"   ✅ Registered connection: {name}")
            
            # Create orchestrator
            orchestrator = WorkflowOrchestrator(
                data_checker=data_checker,
                ui_engine=ui_engine,
                notification_callback=self.notification_callback
            )
            
            # Start workflow execution
            print(f"\n🚀 Starting workflow execution...")
            print(f"📅 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            workflow = await orchestrator.start_workflow(
                runbook_config=runbook,
                execution_id=f"e2e_test_{int(time.time())}",
                variables={
                    'USERNAME': 'testuser',
                    'PASSWORD': 'testpass',
                },
                triggered_by="e2e_test"
            )
            
            print(f"✅ Workflow started: {workflow.execution_id}")
            
            # Monitor execution
            print("\n📊 Monitoring workflow execution...")
            return await self.monitor_workflow_execution(orchestrator, workflow.execution_id)
            
        except Exception as e:
            print(f"❌ Automation failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def monitor_workflow_execution(self, orchestrator, execution_id):
        """Monitor the workflow execution and provide status updates."""
        start_time = time.time()
        last_status = None
        
        while True:
            workflow = orchestrator.get_workflow_status(execution_id)
            
            if not workflow:
                print("❌ Workflow not found")
                return False
            
            # Show progress if changed
            current_status = (workflow.state, workflow.progress_percentage, workflow.completed_tasks)
            if current_status != last_status:
                duration = time.time() - start_time
                print(f"📈 Status: {workflow.state} | "
                      f"Progress: {workflow.progress_percentage:.1f}% | "
                      f"Tasks: {workflow.completed_tasks}/{workflow.total_tasks} | "
                      f"Duration: {duration:.1f}s")
                
                # Show current task details
                current_task = None
                for task_id, task_exec in workflow.tasks.items():
                    if task_exec.status.value == "running":
                        current_task = task_exec.task_config.name
                        break
                
                if current_task:
                    print(f"   🔄 Currently executing: {current_task}")
                
                last_status = current_status
            
            # Check if finished
            if workflow.state.value in ["completed", "failed", "cancelled"]:
                duration = time.time() - start_time
                
                if workflow.state.value == "completed":
                    print(f"\n🎉 Workflow completed successfully!")
                    print(f"   ⏱️  Total duration: {duration:.1f} seconds")
                    print(f"   ✅ Completed tasks: {workflow.completed_tasks}/{workflow.total_tasks}")
                    print(f"   ❌ Failed tasks: {workflow.failed_tasks}")
                    
                    # Show task summary
                    print(f"\n📋 Task Summary:")
                    for task_id, task_exec in workflow.tasks.items():
                        status_icon = "✅" if task_exec.status.value == "completed" else "❌"
                        duration_str = f"{task_exec.duration_seconds:.1f}s" if task_exec.duration_seconds else "N/A"
                        print(f"   {status_icon} {task_exec.task_config.name} ({duration_str})")
                    
                    return True
                else:
                    print(f"\n❌ Workflow {workflow.state.value}")
                    print(f"   ⏱️  Duration: {duration:.1f} seconds")
                    print(f"   ✅ Completed: {workflow.completed_tasks}/{workflow.total_tasks}")
                    print(f"   ❌ Failed: {workflow.failed_tasks}")
                    
                    # Show failed tasks
                    if workflow.failed_tasks > 0:
                        print(f"\n💥 Failed Tasks:")
                        for task_id, task_exec in workflow.tasks.items():
                            if task_exec.status.value == "failed":
                                print(f"   ❌ {task_exec.task_config.name}: {task_exec.error_message}")
                    
                    return False
            
            await asyncio.sleep(2)  # Check every 2 seconds
    
    async def notification_callback(self, workflow, event_type, additional_info=None):
        """Handle workflow notifications."""
        print(f"📢 Notification: {event_type} - {workflow.runbook_config.name}")
        if additional_info:
            print(f"   ℹ️  {additional_info}")
    
    async def cleanup_test_environment(self):
        """Clean up the test environment."""
        print("\n🧹 Cleaning up test environment...")
        
        # Stop test server
        if self.test_server_process:
            try:
                self.test_server_process.terminate()
                self.test_server_process.wait(timeout=5)
                print("✅ Test server stopped")
            except subprocess.TimeoutExpired:
                self.test_server_process.kill()
                print("🔪 Test server force killed")
            except Exception as e:
                print(f"⚠️  Error stopping test server: {e}")
        
        # Clean up temp files (optional)
        temp_files = [
            "local_test_runbook.xlsx",
            "example_runbook_config.xlsx"
        ]
        
        for temp_file in temp_files:
            file_path = self.base_path / temp_file
            if file_path.exists():
                try:
                    file_path.unlink()
                    print(f"🗑️  Removed: {temp_file}")
                except Exception as e:
                    print(f"⚠️  Could not remove {temp_file}: {e}")
    
    async def run_complete_test(self):
        """Run the complete end-to-end test."""
        try:
            print("🎯 Monthly Runbook Agent - End-to-End Test")
            print("=" * 60)
            print("This test will:")
            print("1. 🌐 Start a local web server with a test application")
            print("2. 📊 Create an Excel runbook configuration")
            print("3. 🤖 Execute the complete automation workflow")
            print("4. ✅ Verify all steps complete successfully")
            print()
            
            # Setup
            if not await self.setup_test_environment():
                print("❌ Failed to setup test environment")
                return False
            
            print(f"\n🎭 Opening test application in browser...")
            try:
                webbrowser.open('http://localhost:8080/index.html')
                print("   You can watch the automation in the browser!")
            except:
                print("   Could not open browser automatically")
            
            print(f"\n⏳ Starting automation in 5 seconds...")
            print(f"   (This gives you time to see the initial page)")
            await asyncio.sleep(5)
            
            # Run automation
            success = await self.run_runbook_automation()
            
            if success:
                print(f"\n🎉 END-TO-END TEST PASSED!")
                print(f"✅ The Monthly Runbook Agent successfully automated:")
                print(f"   • Web application login")
                print(f"   • Data validation workflow")
                print(f"   • Monthly process execution")
                print(f"   • Results verification and download")
                print(f"   • Completion notifications")
                print(f"\n🚀 Your Monthly Runbook Agent is ready for production!")
            else:
                print(f"\n❌ END-TO-END TEST FAILED")
                print(f"   Please check the error messages above")
            
            return success
            
        except KeyboardInterrupt:
            print(f"\n⚠️  Test interrupted by user")
            return False
        except Exception as e:
            print(f"\n💥 Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await self.cleanup_test_environment()

async def main():
    """Main function."""
    runner = E2ETestRunner()
    
    # Handle Ctrl+C gracefully
    def signal_handler(signum, frame):
        print(f"\n⚠️  Received interrupt signal, cleaning up...")
        asyncio.create_task(runner.cleanup_test_environment())
        sys.exit(1)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    success = await runner.run_complete_test()
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)