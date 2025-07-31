# Monthly Runbook Agent

Automated agent system for executing monthly production runbooks with UI automation, data validation, and intelligent monitoring.

## Architecture

The Monthly Runbook Agent consists of several key components:

- **Config Parser**: Reads Excel-based runbook configurations
- **Data Availability Checker**: Validates data prerequisites before execution
- **UI Automation Engine**: Executes UI interactions using Playwright
- **Workflow Orchestrator**: Coordinates task execution and dependencies
- **Notification System**: Sends alerts and status updates
- **Monitoring Service**: Tracks execution health and performance

## Technology Stack

- **Backend**: FastAPI, Python 3.11+
- **UI Automation**: Playwright
- **Database**: PostgreSQL with async support
- **Message Queue**: Redis
- **Monitoring**: Prometheus + Grafana
- **Deployment**: Docker, AWS ECS Fargate
- **Configuration**: Excel files + YAML

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start local development
docker-compose up -d

# Run the orchestrator
python -m src.orchestration.main
```

## Directory Structure

```
monthly-runbook-agent/
├── src/
│   ├── config/          # Configuration parsing and management
│   ├── automation/      # UI automation engines
│   ├── orchestration/   # Workflow orchestration
│   ├── monitoring/      # Health checks and metrics
│   ├── data/           # Data validation and checks
│   └── notifications/  # Alert and notification systems
├── tests/              # Test suites
├── docs/              # Documentation
├── configs/           # Sample configurations
└── docker/           # Docker configurations
```

## Features

- 📊 Excel-based runbook configuration
- 🔍 Pre-execution data validation
- 🤖 Headless browser automation
- 📈 Real-time monitoring and alerts
- 🔄 Retry logic with exponential backoff
- 📱 Multi-channel notifications (Slack, email, Teams)
- 🛡️ Error handling and recovery
- 📝 Detailed execution logging
- 🎯 AWS-native deployment