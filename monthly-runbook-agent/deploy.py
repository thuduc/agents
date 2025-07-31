#!/usr/bin/env python3
"""Deployment script for Monthly Runbook Agent to AWS ECS Fargate."""

import asyncio
import logging
import argparse
from pathlib import Path
import json

from src.aws.deployment import AWSDeploymentManager, ECSServiceConfig, TaskDefinitionConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def deploy_to_aws(
    image_uri: str,
    project_name: str = "monthly-runbook-agent",
    region: str = "us-east-1",
    environment: str = "production"
):
    """Deploy the Monthly Runbook Agent to AWS ECS Fargate."""
    
    logger.info(f"Starting deployment to AWS region: {region}")
    
    # Initialize deployment manager
    deployment_manager = AWSDeploymentManager(region_name=region)
    
    try:
        # Step 1: Create base AWS resources
        logger.info("Creating base AWS resources...")
        resources = await deployment_manager.create_deployment_resources(project_name)
        
        # Step 2: Setup secrets in Parameter Store
        logger.info("Setting up secrets...")
        secrets = {
            "DATABASE_PASSWORD": "your-db-password-here",
            "SLACK_TOKEN": "xoxb-your-slack-token-here",
            "SMTP_PASSWORD": "your-smtp-password-here",
            "API_SECRET_KEY": "your-api-secret-key-here"
        }
        
        secret_arns = await deployment_manager.setup_secrets(secrets, f"/{project_name}/")
        
        # Step 3: Create task definition
        logger.info("Creating ECS task definition...")
        
        task_config = TaskDefinitionConfig(
            family=f"{project_name}-task",
            cpu="512",  # 0.5 vCPU
            memory="1024",  # 1 GB
            execution_role_arn=resources['execution_role_arn'],
            task_role_arn=resources['task_role_arn']
        )
        
        environment_variables = {
            "ENVIRONMENT": environment,
            "LOG_LEVEL": "INFO",
            "PROMETHEUS_PORT": "9090"
        }
        
        # Map secrets to environment variable names
        secrets_mapping = {
            "DATABASE_PASSWORD": secret_arns["DATABASE_PASSWORD"],
            "SLACK_TOKEN": secret_arns["SLACK_TOKEN"],
            "SMTP_PASSWORD": secret_arns["SMTP_PASSWORD"],
            "API_SECRET_KEY": secret_arns["API_SECRET_KEY"]
        }
        
        task_definition_arn = await deployment_manager.create_task_definition(
            config=task_config,
            container_image=image_uri,
            environment_variables=environment_variables,
            secrets=secrets_mapping
        )
        
        # Step 4: Create ECS service
        logger.info("Creating ECS service...")
        
        service_config = ECSServiceConfig(
            cluster_name=f"{project_name}-cluster",
            service_name=f"{project_name}-service",
            task_definition_arn=task_definition_arn,
            desired_count=1,
            subnets=resources['subnet_ids'],
            security_groups=[resources['security_group_id']],
            public_ip=True
        )
        
        service_arn = await deployment_manager.create_ecs_service(service_config)
        
        # Step 5: Output deployment information
        deployment_info = {
            "deployment_timestamp": asyncio.get_event_loop().time(),
            "project_name": project_name,
            "region": region,
            "environment": environment,
            "image_uri": image_uri,
            "resources": {
                "cluster_arn": resources['cluster_arn'],
                "service_arn": service_arn,
                "task_definition_arn": task_definition_arn,
                "security_group_id": resources['security_group_id'],
                "execution_role_arn": resources['execution_role_arn'],
                "task_role_arn": resources['task_role_arn']
            }
        }
        
        # Save deployment info
        deployment_file = Path(f"deployment-{environment}.json")
        with open(deployment_file, 'w') as f:
            json.dump(deployment_info, f, indent=2)
        
        logger.info(f"Deployment completed successfully!")
        logger.info(f"Deployment info saved to: {deployment_file}")
        logger.info(f"Service ARN: {service_arn}")
        
        # Check service status
        logger.info("Checking service status...")
        status = await deployment_manager.get_service_status(
            service_config.cluster_name,
            service_config.service_name
        )
        
        logger.info(f"Service status: {status.get('status', 'Unknown')}")
        logger.info(f"Running tasks: {status.get('runningCount', 0)}")
        logger.info(f"Desired tasks: {status.get('desiredCount', 0)}")
        
        return deployment_info
        
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        raise


async def update_service(
    image_uri: str,
    project_name: str = "monthly-runbook-agent",
    region: str = "us-east-1",
    environment: str = "production"
):
    """Update existing ECS service with new image."""
    
    logger.info(f"Updating service in AWS region: {region}")
    
    deployment_manager = AWSDeploymentManager(region_name=region)
    
    try:
        # Load existing deployment info
        deployment_file = Path(f"deployment-{environment}.json")
        if not deployment_file.exists():
            logger.error(f"Deployment file not found: {deployment_file}")
            logger.error("Run initial deployment first with --deploy flag")
            return
        
        with open(deployment_file) as f:
            deployment_info = json.load(f)
        
        # Create new task definition with updated image
        task_config = TaskDefinitionConfig(
            family=f"{project_name}-task",
            cpu="512",
            memory="1024",
            execution_role_arn=deployment_info['resources']['execution_role_arn'],
            task_role_arn=deployment_info['resources']['task_role_arn']
        )
        
        environment_variables = {
            "ENVIRONMENT": environment,
            "LOG_LEVEL": "INFO",
            "PROMETHEUS_PORT": "9090"
        }
        
        # Recreate secrets mapping (in practice, these would be loaded from existing config)
        secret_arns = {
            "DATABASE_PASSWORD": f"arn:aws:ssm:{region}:*:parameter/{project_name}/DATABASE_PASSWORD",
            "SLACK_TOKEN": f"arn:aws:ssm:{region}:*:parameter/{project_name}/SLACK_TOKEN",
            "SMTP_PASSWORD": f"arn:aws:ssm:{region}:*:parameter/{project_name}/SMTP_PASSWORD",
            "API_SECRET_KEY": f"arn:aws:ssm:{region}:*:parameter/{project_name}/API_SECRET_KEY"
        }
        
        new_task_definition_arn = await deployment_manager.create_task_definition(
            config=task_config,
            container_image=image_uri,
            environment_variables=environment_variables,
            secrets=secret_arns
        )
        
        # Update service
        success = await deployment_manager.update_service(
            cluster_name=f"{project_name}-cluster",
            service_name=f"{project_name}-service",
            task_definition_arn=new_task_definition_arn
        )
        
        if success:
            # Update deployment info
            deployment_info['resources']['task_definition_arn'] = new_task_definition_arn
            deployment_info['image_uri'] = image_uri
            deployment_info['last_update'] = asyncio.get_event_loop().time()
            
            with open(deployment_file, 'w') as f:
                json.dump(deployment_info, f, indent=2)
            
            logger.info("Service updated successfully!")
            logger.info(f"New task definition: {new_task_definition_arn}")
        else:
            logger.error("Service update failed")
            
    except Exception as e:
        logger.error(f"Service update failed: {e}")
        raise


async def check_status(
    project_name: str = "monthly-runbook-agent",
    region: str = "us-east-1",
    environment: str = "production"
):
    """Check status of deployed service."""
    
    deployment_manager = AWSDeploymentManager(region_name=region)
    
    status = await deployment_manager.get_service_status(
        cluster_name=f"{project_name}-cluster",
        service_name=f"{project_name}-service"
    )
    
    if "error" in status:
        logger.error(f"Error getting service status: {status['error']}")
        return
    
    logger.info("=== Service Status ===")
    logger.info(f"Service: {status['serviceName']}")
    logger.info(f"Status: {status['status']}")
    logger.info(f"Launch Type: {status['launchType']}")
    logger.info(f"Running Tasks: {status['runningCount']}")
    logger.info(f"Pending Tasks: {status['pendingCount']}")
    logger.info(f"Desired Tasks: {status['desiredCount']}")
    logger.info(f"Task Definition: {status['taskDefinition']}")
    logger.info(f"Created: {status['createdAt']}")
    
    if status['tasks']:
        logger.info("\n=== Task Details ===")
        for i, task in enumerate(status['tasks'], 1):
            logger.info(f"Task {i}:")
            logger.info(f"  Status: {task['lastStatus']} -> {task['desiredStatus']}")
            logger.info(f"  Health: {task['healthStatus']}")
            logger.info(f"  Created: {task['createdAt']}")
            logger.info(f"  CPU: {task['cpu']}, Memory: {task['memory']}")


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(description='Deploy Monthly Runbook Agent to AWS')
    
    parser.add_argument('--deploy', action='store_true', help='Deploy new service')
    parser.add_argument('--update', action='store_true', help='Update existing service')
    parser.add_argument('--status', action='store_true', help='Check service status')
    
    parser.add_argument('--image', required=False, help='Docker image URI')
    parser.add_argument('--project', default='monthly-runbook-agent', help='Project name')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--environment', default='production', help='Environment name')
    
    args = parser.parse_args()
    
    if not any([args.deploy, args.update, args.status]):
        parser.error('Must specify one of: --deploy, --update, --status')
    
    if (args.deploy or args.update) and not args.image:
        parser.error('--image is required for deploy and update operations')
    
    # Run async function
    if args.deploy:
        asyncio.run(deploy_to_aws(
            image_uri=args.image,
            project_name=args.project,
            region=args.region,
            environment=args.environment
        ))
    elif args.update:
        asyncio.run(update_service(
            image_uri=args.image,
            project_name=args.project,
            region=args.region,
            environment=args.environment
        ))
    elif args.status:
        asyncio.run(check_status(
            project_name=args.project,
            region=args.region,
            environment=args.environment
        ))


if __name__ == '__main__':
    main()