"""Excel configuration parser for runbooks."""

import json
import logging
from datetime import datetime, time
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

import pandas as pd
from pydantic import ValidationError

from .models import (
    RunbookConfig, TaskConfig, RunbookSchedule, NotificationConfig,
    TaskType, NotificationChannel, ConfigParsingResult
)

logger = logging.getLogger(__name__)


class ExcelConfigParser:
    """Parser for Excel-based runbook configurations."""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def parse_file(self, file_path: Union[str, Path]) -> ConfigParsingResult:
        """
        Parse runbook configuration from Excel file.
        
        Expected Excel structure:
        - Sheet 'Runbook': Basic runbook information
        - Sheet 'Tasks': Task definitions
        - Sheet 'Schedule': Scheduling configuration
        - Sheet 'Connections': Database/API connections
        - Sheet 'Notifications': Notification settings
        """
        file_path = Path(file_path)
        self.errors = []
        self.warnings = []
        
        if not file_path.exists():
            return ConfigParsingResult(
                success=False,
                source_file=str(file_path),
                errors=[f"File not found: {file_path}"]
            )
        
        try:
            # Load all sheets
            excel_data = pd.read_excel(file_path, sheet_name=None, dtype=str)
            sheets_processed = list(excel_data.keys())
            
            logger.info(f"Found sheets: {sheets_processed}")
            
            # Parse each section
            runbook_info = self._parse_runbook_info(excel_data.get('Runbook'))
            tasks = self._parse_tasks(excel_data.get('Tasks'))
            schedule = self._parse_schedule(excel_data.get('Schedule'))
            connections = self._parse_connections(excel_data.get('Connections'))
            notifications = self._parse_notifications(excel_data.get('Notifications'))
            
            # Build runbook configuration
            if runbook_info and tasks:
                runbook_config = RunbookConfig(
                    **runbook_info,
                    tasks=tasks,
                    schedule=schedule,
                    connections=connections,
                    default_notifications=notifications
                )
                
                return ConfigParsingResult(
                    success=True,
                    runbook=runbook_config,
                    source_file=str(file_path),
                    sheets_processed=sheets_processed,
                    errors=self.errors,
                    warnings=self.warnings
                )
            else:
                return ConfigParsingResult(
                    success=False,
                    source_file=str(file_path),
                    sheets_processed=sheets_processed,
                    errors=self.errors + ["Failed to parse required runbook information or tasks"],
                    warnings=self.warnings
                )
                
        except Exception as e:
            logger.exception(f"Error parsing Excel file: {e}")
            return ConfigParsingResult(
                success=False,
                source_file=str(file_path),
                errors=[f"Failed to parse Excel file: {str(e)}"]
            )
    
    def _parse_runbook_info(self, df: Optional[pd.DataFrame]) -> Optional[Dict[str, Any]]:
        """Parse basic runbook information."""
        if df is None:
            self.errors.append("Missing 'Runbook' sheet")
            return None
        
        try:
            # Convert DataFrame to key-value pairs
            info = {}
            for _, row in df.iterrows():
                if pd.notna(row.get('Property')) and pd.notna(row.get('Value')):
                    key = str(row['Property']).strip().lower()
                    value = str(row['Value']).strip()
                    
                    # Map Excel properties to model fields
                    field_mapping = {
                        'id': 'id',
                        'name': 'name',
                        'description': 'description',
                        'version': 'version',
                        'owner': 'owner',
                        'team': 'team',
                        'environment': 'environment',
                        'global_timeout_minutes': 'global_timeout_minutes',
                        'max_parallel_tasks': 'max_parallel_tasks'
                    }
                    
                    if key in field_mapping:
                        field_name = field_mapping[key]
                        
                        # Type conversion
                        if field_name in ['global_timeout_minutes', 'max_parallel_tasks']:
                            try:
                                info[field_name] = int(value)
                            except ValueError:
                                self.warnings.append(f"Invalid integer value for {field_name}: {value}")
                        else:
                            info[field_name] = value
                    
                    # Handle tags as comma-separated values
                    elif key == 'tags':
                        info['tags'] = [tag.strip() for tag in value.split(',') if tag.strip()]
            
            # Validate required fields
            required_fields = ['id', 'name', 'owner']
            for field in required_fields:
                if field not in info:
                    self.errors.append(f"Missing required field in Runbook sheet: {field}")
            
            return info if not any(field not in info for field in required_fields) else None
            
        except Exception as e:
            self.errors.append(f"Error parsing Runbook sheet: {str(e)}")
            return None
    
    def _parse_tasks(self, df: Optional[pd.DataFrame]) -> Optional[List[TaskConfig]]:
        """Parse task definitions."""
        if df is None:
            self.errors.append("Missing 'Tasks' sheet")
            return None
        
        tasks = []
        
        try:
            for idx, row in df.iterrows():
                if pd.isna(row.get('ID')) or pd.isna(row.get('Name')):
                    continue  # Skip empty rows
                
                task_data = {
                    'id': str(row['ID']).strip(),
                    'name': str(row['Name']).strip(),
                    'description': str(row.get('Description', '')).strip() or None,
                    'task_type': str(row.get('Type', 'ui_automation')).lower(),
                }
                
                # Parse dependencies
                if pd.notna(row.get('Dependencies')):
                    deps = str(row['Dependencies']).strip()
                    task_data['depends_on'] = [dep.strip() for dep in deps.split(',') if dep.strip()]
                
                # Parse numeric fields
                numeric_fields = {
                    'timeout_minutes': 'Timeout_Minutes',
                    'retry_count': 'Retry_Count',
                    'retry_delay_seconds': 'Retry_Delay_Seconds'
                }
                
                for field, col in numeric_fields.items():
                    if pd.notna(row.get(col)):
                        try:
                            task_data[field] = int(row[col])
                        except ValueError:
                            self.warnings.append(f"Invalid {field} for task {task_data['id']}: {row[col]}")
                
                # Parse boolean fields
                boolean_fields = {
                    'skip_on_failure': 'Skip_On_Failure',
                    'notify_on_start': 'Notify_On_Start',
                    'notify_on_success': 'Notify_On_Success',
                    'notify_on_failure': 'Notify_On_Failure'
                }
                
                for field, col in boolean_fields.items():
                    if pd.notna(row.get(col)):
                        val = str(row[col]).lower()
                        task_data[field] = val in ['true', 'yes', '1', 'on']
                
                # Parse task-specific configuration
                config = self._parse_task_config(row, task_data['task_type'])
                task_data['config'] = config
                
                # Parse conditions if present
                if pd.notna(row.get('Conditions')):
                    try:
                        conditions_str = str(row['Conditions']).strip()
                        if conditions_str:
                            task_data['conditions'] = json.loads(conditions_str)
                    except json.JSONDecodeError:
                        self.warnings.append(f"Invalid JSON in conditions for task {task_data['id']}")
                
                try:
                    task = TaskConfig(**task_data)
                    tasks.append(task)
                except ValidationError as e:
                    self.errors.append(f"Invalid task configuration for {task_data.get('id', 'unknown')}: {e}")
            
            return tasks if tasks else None
            
        except Exception as e:
            self.errors.append(f"Error parsing Tasks sheet: {str(e)}")
            return None
    
    def _parse_task_config(self, row: pd.Series, task_type: str) -> Dict[str, Any]:
        """Parse task-specific configuration from Excel row."""
        config = {}
        
        try:
            if task_type == TaskType.DATA_CHECK:
                config = {
                    'data_source': str(row.get('Data_Source', '')),
                    'query': str(row.get('Query', '')) if pd.notna(row.get('Query')) else None,
                    'expected_count_min': int(row['Expected_Count_Min']) if pd.notna(row.get('Expected_Count_Min')) else None,
                    'expected_count_max': int(row['Expected_Count_Max']) if pd.notna(row.get('Expected_Count_Max')) else None,
                    'freshness_hours': int(row['Freshness_Hours']) if pd.notna(row.get('Freshness_Hours')) else None,
                }
                
            elif task_type == TaskType.UI_AUTOMATION:
                config = {
                    'url': str(row.get('URL', '')),
                    'browser': str(row.get('Browser', 'chromium')),
                    'headless': str(row.get('Headless', 'true')).lower() in ['true', 'yes', '1'],
                    'timeout_seconds': int(row.get('UI_Timeout_Seconds', 30)),
                    'screenshot_on_failure': str(row.get('Screenshot_On_Failure', 'true')).lower() in ['true', 'yes', '1'],
                }
                
                # Parse UI steps if present
                if pd.notna(row.get('UI_Steps')):
                    try:
                        steps_str = str(row['UI_Steps']).strip()
                        config['steps'] = json.loads(steps_str)
                    except json.JSONDecodeError:
                        self.warnings.append(f"Invalid JSON in UI_Steps for task {row.get('ID', 'unknown')}")
                        config['steps'] = []
                
            elif task_type == TaskType.API_CALL:
                config = {
                    'method': str(row.get('HTTP_Method', 'GET')).upper(),
                    'url': str(row.get('API_URL', '')),
                    'timeout_seconds': int(row.get('API_Timeout_Seconds', 30)),
                    'expected_status': int(row.get('Expected_Status', 200)),
                }
                
                # Parse headers, params, body as JSON
                for json_field in ['Headers', 'Params', 'Body']:
                    if pd.notna(row.get(json_field)):
                        try:
                            config[json_field.lower()] = json.loads(str(row[json_field]))
                        except json.JSONDecodeError:
                            self.warnings.append(f"Invalid JSON in {json_field} for task {row.get('ID', 'unknown')}")
                
            elif task_type == TaskType.DATABASE_QUERY:
                config = {
                    'connection_name': str(row.get('Connection_Name', '')),
                    'query': str(row.get('DB_Query', '')),
                    'timeout_seconds': int(row.get('DB_Timeout_Seconds', 60)),
                }
                
                if pd.notna(row.get('Query_Parameters')):
                    try:
                        config['parameters'] = json.loads(str(row['Query_Parameters']))
                    except json.JSONDecodeError:
                        self.warnings.append(f"Invalid JSON in Query_Parameters for task {row.get('ID', 'unknown')}")
            
            # Add any additional configuration from Config_JSON column
            if pd.notna(row.get('Config_JSON')):
                try:
                    additional_config = json.loads(str(row['Config_JSON']))
                    config.update(additional_config)
                except json.JSONDecodeError:
                    self.warnings.append(f"Invalid JSON in Config_JSON for task {row.get('ID', 'unknown')}")
        
        except Exception as e:
            self.warnings.append(f"Error parsing config for task {row.get('ID', 'unknown')}: {str(e)}")
        
        return config
    
    def _parse_schedule(self, df: Optional[pd.DataFrame]) -> Optional[RunbookSchedule]:
        """Parse scheduling configuration."""
        if df is None:
            return None
        
        try:
            schedule_data = {}
            
            for _, row in df.iterrows():
                if pd.notna(row.get('Property')) and pd.notna(row.get('Value')):
                    key = str(row['Property']).strip().lower()
                    value = str(row['Value']).strip()
                    
                    if key == 'enabled':
                        schedule_data['enabled'] = value.lower() in ['true', 'yes', '1']
                    elif key == 'cron_expression':
                        schedule_data['cron_expression'] = value
                    elif key == 'timezone':
                        schedule_data['timezone'] = value
                    elif key == 'day_of_month':
                        try:
                            schedule_data['day_of_month'] = int(value)
                        except ValueError:
                            self.warnings.append(f"Invalid day_of_month: {value}")
                    elif key in ['time_of_day', 'earliest_start', 'latest_start']:
                        try:
                            # Parse time (HH:MM or HH:MM:SS format)
                            time_parts = value.split(':')
                            if len(time_parts) >= 2:
                                hour = int(time_parts[0])
                                minute = int(time_parts[1])
                                second = int(time_parts[2]) if len(time_parts) > 2 else 0
                                schedule_data[key] = time(hour, minute, second)
                        except ValueError:
                            self.warnings.append(f"Invalid time format for {key}: {value}")
                    elif key == 'skip_holidays':
                        schedule_data['skip_holidays'] = value.lower() in ['true', 'yes', '1']
                    elif key == 'holiday_calendar':
                        schedule_data['holiday_calendar'] = value
            
            return RunbookSchedule(**schedule_data) if schedule_data else None
            
        except Exception as e:
            self.warnings.append(f"Error parsing Schedule sheet: {str(e)}")
            return None
    
    def _parse_connections(self, df: Optional[pd.DataFrame]) -> Dict[str, Dict[str, Any]]:
        """Parse connection configurations."""
        if df is None:
            return {}
        
        connections = {}
        
        try:
            for _, row in df.iterrows():
                if pd.notna(row.get('Name')):
                    name = str(row['Name']).strip()
                    conn_config = {}
                    
                    # Standard connection fields
                    fields = ['Type', 'Host', 'Port', 'Database', 'Username', 'Password', 'URL']
                    for field in fields:
                        if pd.notna(row.get(field)):
                            conn_config[field.lower()] = str(row[field]).strip()
                    
                    # Parse additional config as JSON
                    if pd.notna(row.get('Config_JSON')):
                        try:
                            additional_config = json.loads(str(row['Config_JSON']))
                            conn_config.update(additional_config)
                        except json.JSONDecodeError:
                            self.warnings.append(f"Invalid JSON in connection config for {name}")
                    
                    connections[name] = conn_config
            
        except Exception as e:
            self.warnings.append(f"Error parsing Connections sheet: {str(e)}")
        
        return connections
    
    def _parse_notifications(self, df: Optional[pd.DataFrame]) -> Optional[NotificationConfig]:
        """Parse default notification configuration."""
        if df is None:
            return None
        
        try:
            notification_data = {}
            
            for _, row in df.iterrows():
                if pd.notna(row.get('Property')) and pd.notna(row.get('Value')):
                    key = str(row['Property']).strip().lower()
                    value = str(row['Value']).strip()
                    
                    if key == 'channels':
                        # Parse comma-separated channels
                        channels = [ch.strip().lower() for ch in value.split(',') if ch.strip()]
                        valid_channels = []
                        for ch in channels:
                            try:
                                valid_channels.append(NotificationChannel(ch))
                            except ValueError:
                                self.warnings.append(f"Invalid notification channel: {ch}")
                        notification_data['channels'] = valid_channels
                    elif key == 'message_template':
                        notification_data['message_template'] = value
                    elif key == 'recipients':
                        notification_data['recipients'] = [r.strip() for r in value.split(',') if r.strip()]
                    elif key == 'priority':
                        notification_data['priority'] = value
                    elif key == 'include_details':
                        notification_data['include_details'] = value.lower() in ['true', 'yes', '1']
            
            return NotificationConfig(**notification_data) if notification_data else None
            
        except Exception as e:
            self.warnings.append(f"Error parsing Notifications sheet: {str(e)}")
            return None
    
    def create_sample_excel(self, output_path: Union[str, Path]) -> None:
        """Create a sample Excel configuration file."""
        output_path = Path(output_path)
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Runbook sheet
            runbook_data = pd.DataFrame([
                ['ID', 'monthly_prod_runbook'],
                ['Name', 'Monthly Production Runbook'],
                ['Description', 'Automated monthly production tasks'],
                ['Version', '1.0.0'],
                ['Owner', 'ops-team@company.com'],
                ['Team', 'Operations'],
                ['Environment', 'production'],
                ['Global_Timeout_Minutes', '240'],
                ['Max_Parallel_Tasks', '3'],
                ['Tags', 'monthly,production,automation']
            ], columns=['Property', 'Value'])
            runbook_data.to_excel(writer, sheet_name='Runbook', index=False)
            
            # Tasks sheet
            tasks_data = pd.DataFrame([
                {
                    'ID': 'check_data_availability',
                    'Name': 'Check Data Availability',
                    'Description': 'Verify monthly data is available',
                    'Type': 'data_check',
                    'Dependencies': '',
                    'Timeout_Minutes': 15,
                    'Retry_Count': 3,
                    'Data_Source': 'prod_database',
                    'Query': 'SELECT COUNT(*) FROM monthly_data WHERE date >= date_trunc(\'month\', current_date)',
                    'Expected_Count_Min': 1000,
                    'Freshness_Hours': 24
                },
                {
                    'ID': 'run_monthly_ui_task',
                    'Name': 'Execute Monthly UI Process',
                    'Description': 'Run the monthly UI automation',
                    'Type': 'ui_automation',
                    'Dependencies': 'check_data_availability',
                    'Timeout_Minutes': 60,
                    'Retry_Count': 2,
                    'URL': 'https://internal-app.company.com/monthly-process',
                    'Browser': 'chromium',
                    'Headless': 'true',
                    'UI_Steps': json.dumps([
                        {'action': 'navigate', 'url': 'https://internal-app.company.com/login'},
                        {'action': 'fill', 'selector': '#username', 'value': '${USERNAME}'},
                        {'action': 'fill', 'selector': '#password', 'value': '${PASSWORD}'},
                        {'action': 'click', 'selector': '#login-button'},
                        {'action': 'wait', 'selector': '#dashboard'},
                        {'action': 'click', 'selector': '#monthly-process-link'},
                        {'action': 'click', 'selector': '#start-process-button'},
                        {'action': 'wait', 'selector': '.process-complete', 'timeout': 1800000}
                    ])
                },
                {
                    'ID': 'send_completion_report',
                    'Name': 'Send Completion Report',
                    'Description': 'Send summary report to stakeholders',
                    'Type': 'notification',
                    'Dependencies': 'run_monthly_ui_task',
                    'Timeout_Minutes': 5,
                    'Config_JSON': json.dumps({
                        'template': 'monthly_completion_report',
                        'include_screenshots': True,
                        'include_logs': True
                    })
                }
            ])
            tasks_data.to_excel(writer, sheet_name='Tasks', index=False)
            
            # Schedule sheet
            schedule_data = pd.DataFrame([
                ['Enabled', 'true'],
                ['Day_Of_Month', '1'],
                ['Time_Of_Day', '02:00:00'],
                ['Timezone', 'UTC'],
                ['Skip_Holidays', 'true'],
                ['Holiday_Calendar', 'US']
            ], columns=['Property', 'Value'])
            schedule_data.to_excel(writer, sheet_name='Schedule', index=False)
            
            # Connections sheet
            connections_data = pd.DataFrame([
                {
                    'Name': 'prod_database',
                    'Type': 'postgresql',
                    'Host': 'prod-db.company.com',
                    'Port': '5432',
                    'Database': 'production',
                    'Username': '${DB_USERNAME}',
                    'Password': '${DB_PASSWORD}'
                },
                {
                    'Name': 'api_service',
                    'Type': 'http',
                    'URL': 'https://api.company.com',
                    'Config_JSON': json.dumps({
                        'timeout': 30,
                        'headers': {'Authorization': 'Bearer ${API_TOKEN}'}
                    })
                }
            ])
            connections_data.to_excel(writer, sheet_name='Connections', index=False)
            
            # Notifications sheet
            notifications_data = pd.DataFrame([
                ['Channels', 'slack,email'],
                ['Message_Template', 'Monthly runbook execution: {status} | Duration: {duration} | Tasks: {completed}/{total}'],
                ['Recipients', 'ops-team@company.com,#ops-alerts'],
                ['Priority', 'normal'],
                ['Include_Details', 'true']
            ], columns=['Property', 'Value'])
            notifications_data.to_excel(writer, sheet_name='Notifications', index=False)
        
        logger.info(f"Sample Excel configuration created at: {output_path}")