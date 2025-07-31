"""Notification service for runbook execution alerts."""

import asyncio
import logging
import smtplib
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
import json

import httpx
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from ..config.models import NotificationChannel, NotificationConfig
from ..orchestration.workflow_engine import WorkflowExecution

logger = logging.getLogger(__name__)


@dataclass
class NotificationMessage:
    """Represents a notification message."""
    title: str
    message: str
    priority: str = "normal"
    channels: List[NotificationChannel] = None
    recipients: List[str] = None
    attachments: List[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.channels is None:
            self.channels = []
        if self.recipients is None:
            self.recipients = []
        if self.attachments is None:
            self.attachments = []
        if self.metadata is None:
            self.metadata = {}


@dataclass
class NotificationResult:
    """Result of sending a notification."""
    success: bool
    channel: NotificationChannel
    message: str
    recipient: Optional[str] = None
    sent_at: Optional[datetime] = None
    error: Optional[str] = None


class NotificationService:
    """Multi-channel notification service."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        # Channel clients
        self._slack_client: Optional[AsyncWebClient] = None
        self._smtp_config: Optional[Dict[str, str]] = None
        
        # Initialize channels
        self._initialize_channels()
    
    def _initialize_channels(self):
        """Initialize notification channel clients."""
        # Slack
        if self.config.get('slack', {}).get('token'):
            self._slack_client = AsyncWebClient(token=self.config['slack']['token'])
            logger.info("Slack client initialized")
        
        # Email SMTP
        if self.config.get('email', {}).get('smtp_server'):
            self._smtp_config = self.config['email']
            logger.info("Email SMTP configuration loaded")
    
    async def send_notification(
        self,
        notification: NotificationMessage
    ) -> List[NotificationResult]:
        """
        Send notification through configured channels.
        
        Args:
            notification: Notification message to send
            
        Returns:
            List of NotificationResult for each channel/recipient
        """
        results = []
        
        for channel in notification.channels:
            if channel == NotificationChannel.SLACK:
                channel_results = await self._send_slack_notification(notification)
                results.extend(channel_results)
            
            elif channel == NotificationChannel.EMAIL:
                channel_results = await self._send_email_notification(notification)
                results.extend(channel_results)
            
            elif channel == NotificationChannel.TEAMS:
                channel_results = await self._send_teams_notification(notification)
                results.extend(channel_results)
            
            elif channel == NotificationChannel.WEBHOOK:
                channel_results = await self._send_webhook_notification(notification)
                results.extend(channel_results)
            
            else:
                logger.warning(f"Unsupported notification channel: {channel}")
                results.append(NotificationResult(
                    success=False,
                    channel=channel,
                    message=f"Unsupported channel: {channel}",
                    error="Channel not implemented"
                ))
        
        return results
    
    async def _send_slack_notification(
        self,
        notification: NotificationMessage
    ) -> List[NotificationResult]:
        """Send notification via Slack."""
        results = []
        
        if not self._slack_client:
            return [NotificationResult(
                success=False,
                channel=NotificationChannel.SLACK,
                message="Slack client not configured",
                error="Missing Slack token"
            )]
        
        # Prepare Slack message
        slack_message = self._format_slack_message(notification)
        
        for recipient in notification.recipients:
            try:
                # Determine if recipient is a channel or user
                if recipient.startswith('#'):
                    # Channel
                    response = await self._slack_client.chat_postMessage(
                        channel=recipient,
                        **slack_message
                    )
                elif recipient.startswith('@'):
                    # User (DM)
                    # First get user ID
                    user_response = await self._slack_client.users_lookupByEmail(
                        email=recipient[1:]  # Remove @ prefix
                    )
                    user_id = user_response['user']['id']
                    
                    # Open DM conversation
                    dm_response = await self._slack_client.conversations_open(
                        users=[user_id]
                    )
                    channel_id = dm_response['channel']['id']
                    
                    # Send message
                    response = await self._slack_client.chat_postMessage(
                        channel=channel_id,
                        **slack_message
                    )
                else:
                    # Assume it's a channel ID
                    response = await self._slack_client.chat_postMessage(
                        channel=recipient,
                        **slack_message
                    )
                
                results.append(NotificationResult(
                    success=True,
                    channel=NotificationChannel.SLACK,
                    message="Slack message sent successfully",
                    recipient=recipient,
                    sent_at=datetime.utcnow()
                ))
                
            except SlackApiError as e:
                logger.error(f"Slack API error for {recipient}: {e}")
                results.append(NotificationResult(
                    success=False,
                    channel=NotificationChannel.SLACK,
                    message=f"Slack API error: {e.response['error']}",
                    recipient=recipient,
                    error=str(e)
                ))
            except Exception as e:
                logger.exception(f"Error sending Slack notification to {recipient}")
                results.append(NotificationResult(
                    success=False,
                    channel=NotificationChannel.SLACK,
                    message=f"Unexpected error: {str(e)}",
                    recipient=recipient,
                    error=str(e)
                ))
        
        return results
    
    def _format_slack_message(self, notification: NotificationMessage) -> Dict[str, Any]:
        """Format notification as Slack message."""
        # Priority emoji mapping
        priority_emojis = {
            'low': ':information_source:',
            'normal': ':bell:',
            'high': ':warning:',
            'critical': ':rotating_light:'
        }
        
        emoji = priority_emojis.get(notification.priority, ':bell:')
        
        # Create blocks for rich formatting
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {notification.title}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": notification.message
                }
            }
        ]
        
        # Add metadata if present
        if notification.metadata:
            metadata_text = "\n".join([
                f"*{key}:* {value}" 
                for key, value in notification.metadata.items()
            ])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": metadata_text
                }
            })
        
        # Add divider
        blocks.append({"type": "divider"})
        
        # Add timestamp
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Sent at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                }
            ]
        })
        
        return {
            "blocks": blocks,
            "text": f"{notification.title}: {notification.message}"  # Fallback text
        }
    
    async def _send_email_notification(
        self,
        notification: NotificationMessage
    ) -> List[NotificationResult]:
        """Send notification via email."""
        results = []
        
        if not self._smtp_config:
            return [NotificationResult(
                success=False,
                channel=NotificationChannel.EMAIL,
                message="Email SMTP not configured",
                error="Missing SMTP configuration"
            )]
        
        for recipient in notification.recipients:
            try:
                # Create email message
                msg = MIMEMultipart()
                msg['From'] = self._smtp_config['from_email']
                msg['To'] = recipient
                msg['Subject'] = f"[{notification.priority.upper()}] {notification.title}"
                
                # Create HTML body
                html_body = self._format_email_html(notification)
                msg.attach(MIMEText(html_body, 'html'))
                
                # Add attachments
                for attachment_path in notification.attachments:
                    if Path(attachment_path).exists():
                        with open(attachment_path, 'rb') as f:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(f.read())
                            encoders.encode_base64(part)
                            part.add_header(
                                'Content-Disposition',
                                f'attachment; filename= {Path(attachment_path).name}'
                            )
                            msg.attach(part)
                
                # Send email
                with smtplib.SMTP(
                    self._smtp_config['smtp_server'],
                    self._smtp_config.get('smtp_port', 587)
                ) as server:
                    if self._smtp_config.get('use_tls', True):
                        server.starttls()
                    
                    if self._smtp_config.get('username'):
                        server.login(
                            self._smtp_config['username'],
                            self._smtp_config['password']
                        )
                    
                    server.send_message(msg)
                
                results.append(NotificationResult(
                    success=True,
                    channel=NotificationChannel.EMAIL,
                    message="Email sent successfully",
                    recipient=recipient,
                    sent_at=datetime.utcnow()
                ))
                
            except Exception as e:
                logger.exception(f"Error sending email to {recipient}")
                results.append(NotificationResult(
                    success=False,
                    channel=NotificationChannel.EMAIL,
                    message=f"Email send failed: {str(e)}",
                    recipient=recipient,
                    error=str(e)
                ))
        
        return results
    
    def _format_email_html(self, notification: NotificationMessage) -> str:
        """Format notification as HTML email."""
        priority_colors = {
            'low': '#17a2b8',      # info blue
            'normal': '#28a745',   # success green  
            'high': '#ffc107',     # warning yellow
            'critical': '#dc3545'  # danger red
        }
        
        color = priority_colors.get(notification.priority, '#28a745')
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: {color}; color: white; padding: 15px; border-radius: 5px; }}
                .content {{ margin: 20px 0; line-height: 1.6; }}
                .metadata {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .footer {{ color: #6c757d; font-size: 12px; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>{notification.title}</h2>
                <p>Priority: {notification.priority.upper()}</p>
            </div>
            
            <div class="content">
                <p>{notification.message.replace(chr(10), '<br>')}</p>
            </div>
        """
        
        if notification.metadata:
            html += '<div class="metadata"><h4>Details:</h4><ul>'
            for key, value in notification.metadata.items():
                html += f'<li><strong>{key}:</strong> {value}</li>'
            html += '</ul></div>'
        
        html += f"""
            <div class="footer">
                <p>Sent by Monthly Runbook Agent at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            </div>
        </body>
        </html>
        """
        
        return html
    
    async def _send_teams_notification(
        self,
        notification: NotificationMessage
    ) -> List[NotificationResult]:
        """Send notification via Microsoft Teams."""
        results = []
        
        webhook_url = self.config.get('teams', {}).get('webhook_url')
        if not webhook_url:
            return [NotificationResult(
                success=False,
                channel=NotificationChannel.TEAMS,
                message="Teams webhook URL not configured",
                error="Missing webhook URL"
            )]
        
        # Create Teams adaptive card
        teams_payload = self._format_teams_message(notification)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json=teams_payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    results.append(NotificationResult(
                        success=True,
                        channel=NotificationChannel.TEAMS,
                        message="Teams message sent successfully",
                        sent_at=datetime.utcnow()
                    ))
                else:
                    results.append(NotificationResult(
                        success=False,
                        channel=NotificationChannel.TEAMS,
                        message=f"Teams webhook failed: {response.status_code}",
                        error=f"HTTP {response.status_code}: {response.text}"
                    ))
                    
        except Exception as e:
            logger.exception("Error sending Teams notification")
            results.append(NotificationResult(
                success=False,
                channel=NotificationChannel.TEAMS,
                message=f"Teams notification failed: {str(e)}",
                error=str(e)
            ))
        
        return results
    
    def _format_teams_message(self, notification: NotificationMessage) -> Dict[str, Any]:
        """Format notification as Teams adaptive card."""
        priority_colors = {
            'low': 'accent',
            'normal': 'good',
            'high': 'warning',
            'critical': 'attention'
        }
        
        color = priority_colors.get(notification.priority, 'good')
        
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary": notification.title,
            "sections": [
                {
                    "activityTitle": notification.title,
                    "activitySubtitle": f"Priority: {notification.priority.upper()}",
                    "text": notification.message,
                    "markdown": True
                }
            ]
        }
        
        # Add metadata as facts
        if notification.metadata:
            facts = [
                {"name": key, "value": str(value)}
                for key, value in notification.metadata.items()
            ]
            card["sections"][0]["facts"] = facts
        
        return card
    
    async def _send_webhook_notification(
        self,
        notification: NotificationMessage
    ) -> List[NotificationResult]:
        """Send notification via generic webhook."""
        results = []
        
        webhook_urls = self.config.get('webhook', {}).get('urls', [])
        if not webhook_urls:
            return [NotificationResult(
                success=False,
                channel=NotificationChannel.WEBHOOK,
                message="No webhook URLs configured",
                error="Missing webhook configuration"
            )]
        
        # Create webhook payload
        payload = {
            "title": notification.title,
            "message": notification.message,
            "priority": notification.priority,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": notification.metadata
        }
        
        for webhook_url in webhook_urls:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        webhook_url,
                        json=payload,
                        timeout=30
                    )
                    
                    if response.status_code in [200, 201, 202]:
                        results.append(NotificationResult(
                            success=True,
                            channel=NotificationChannel.WEBHOOK,
                            message="Webhook notification sent successfully",
                            recipient=webhook_url,
                            sent_at=datetime.utcnow()
                        ))
                    else:
                        results.append(NotificationResult(
                            success=False,
                            channel=NotificationChannel.WEBHOOK,
                            message=f"Webhook failed: {response.status_code}",
                            recipient=webhook_url,
                            error=f"HTTP {response.status_code}: {response.text}"
                        ))
                        
            except Exception as e:
                logger.exception(f"Error sending webhook notification to {webhook_url}")
                results.append(NotificationResult(
                    success=False,
                    channel=NotificationChannel.WEBHOOK,
                    message=f"Webhook notification failed: {str(e)}",
                    recipient=webhook_url,
                    error=str(e)
                ))
        
        return results
    
    def create_workflow_notification(
        self,
        workflow: WorkflowExecution,
        event_type: str,
        additional_info: Optional[str] = None
    ) -> NotificationMessage:
        """Create notification message for workflow events."""
        event_templates = {
            'workflow_started': {
                'title': f'Runbook Started: {workflow.runbook_config.name}',
                'message': f'Runbook execution {workflow.execution_id} has started.',
                'priority': 'normal'
            },
            'workflow_completed': {
                'title': f'Runbook Completed: {workflow.runbook_config.name}',
                'message': f'Runbook execution {workflow.execution_id} completed successfully.',
                'priority': 'normal'
            },
            'workflow_failed': {
                'title': f'Runbook Failed: {workflow.runbook_config.name}',
                'message': f'Runbook execution {workflow.execution_id} failed.',
                'priority': 'high'
            },
            'task_failed': {
                'title': f'Task Failed: {workflow.runbook_config.name}',
                'message': f'Task {additional_info} failed in runbook {workflow.execution_id}.',
                'priority': 'high'
            }
        }
        
        template = event_templates.get(event_type, {
            'title': f'Runbook Event: {workflow.runbook_config.name}',
            'message': f'Event {event_type} occurred in runbook {workflow.execution_id}.',
            'priority': 'normal'
        })
        
        # Add additional info to message if provided
        if additional_info and event_type not in ['task_failed']:
            template['message'] += f' {additional_info}'
        
        # Prepare metadata
        metadata = {
            'Execution ID': workflow.execution_id,
            'Runbook': workflow.runbook_config.name,
            'State': workflow.state.value,
            'Progress': f'{workflow.progress_percentage:.1f}%',
            'Completed Tasks': f'{workflow.completed_tasks}/{workflow.total_tasks}',
            'Failed Tasks': str(workflow.failed_tasks),
            'Duration': f'{workflow.duration_seconds:.1f}s' if workflow.duration_seconds else 'N/A'
        }
        
        # Use default notification config from runbook
        default_config = workflow.runbook_config.default_notifications
        channels = default_config.channels if default_config else [NotificationChannel.EMAIL]
        recipients = default_config.recipients if default_config else []
        
        return NotificationMessage(
            title=template['title'],
            message=template['message'],
            priority=template['priority'],
            channels=channels,
            recipients=recipients,
            metadata=metadata
        )
    
    async def send_workflow_notification(
        self,
        workflow: WorkflowExecution,
        event_type: str,
        additional_info: Optional[str] = None
    ) -> List[NotificationResult]:
        """Send notification for workflow events."""
        notification = self.create_workflow_notification(workflow, event_type, additional_info)
        return await self.send_notification(notification)