"""AWS deployment utilities and ECS integration."""

import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


@dataclass
class ECSServiceConfig:
    """ECS service configuration."""
    cluster_name: str
    service_name: str
    task_definition_arn: str
    desired_count: int = 1
    subnets: List[str] = None
    security_groups: List[str] = None
    public_ip: bool = True
    
    def __post_init__(self):
        if self.subnets is None:
            self.subnets = []
        if self.security_groups is None:
            self.security_groups = []


@dataclass
class TaskDefinitionConfig:
    """ECS task definition configuration."""
    family: str
    cpu: str = "256"
    memory: str = "512"
    execution_role_arn: str = ""
    task_role_arn: str = ""
    network_mode: str = "awsvpc"
    requires_compatibility: List[str] = None
    
    def __post_init__(self):
        if self.requires_compatibility is None:
            self.requires_compatibility = ["FARGATE"]


class AWSDeploymentManager:
    """Manages AWS deployment for the Monthly Runbook Agent."""
    
    def __init__(self, region_name: str = "us-east-1"):
        self.region_name = region_name
        
        # AWS clients
        self.ecs_client = boto3.client('ecs', region_name=region_name)
        self.ec2_client = boto3.client('ec2', region_name=region_name)
        self.logs_client = boto3.client('logs', region_name=region_name)
        self.ssm_client = boto3.client('ssm', region_name=region_name)
        self.secretsmanager_client = boto3.client('secretsmanager', region_name=region_name)
        
        logger.info(f"AWS Deployment Manager initialized for region: {region_name}")
    
    async def create_task_definition(
        self,
        config: TaskDefinitionConfig,
        container_image: str,
        environment_variables: Optional[Dict[str, str]] = None,
        secrets: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Create ECS task definition for the runbook agent.
        
        Args:
            config: Task definition configuration
            container_image: Docker image URI
            environment_variables: Environment variables for the container
            secrets: Secret references (key: secret ARN or parameter name)
            
        Returns:
            Task definition ARN
        """
        try:
            # Prepare container definition
            container_def = {
                "name": "runbook-agent",
                "image": container_image,
                "portMappings": [
                    {
                        "containerPort": 8000,
                        "protocol": "tcp"
                    }
                ],
                "essential": True,
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": f"/ecs/{config.family}",
                        "awslogs-region": self.region_name,
                        "awslogs-stream-prefix": "ecs"
                    }
                },
                "healthCheck": {
                    "command": [
                        "CMD-SHELL",
                        "curl -f http://localhost:8000/health || exit 1"
                    ],
                    "interval": 30,
                    "timeout": 5,
                    "retries": 3,
                    "startPeriod": 60
                }
            }
            
            # Add environment variables
            if environment_variables:
                container_def["environment"] = [
                    {"name": key, "value": value}
                    for key, value in environment_variables.items()
                ]
            
            # Add secrets
            if secrets:
                container_def["secrets"] = [
                    {"name": key, "valueFrom": value}
                    for key, value in secrets.items()
                ]
            
            # Create CloudWatch log group if it doesn't exist
            await self._ensure_log_group(f"/ecs/{config.family}")
            
            # Register task definition
            response = self.ecs_client.register_task_definition(
                family=config.family,
                networkMode=config.network_mode,
                requiresCompatibility=config.requires_compatibility,
                cpu=config.cpu,
                memory=config.memory,
                executionRoleArn=config.execution_role_arn,
                taskRoleArn=config.task_role_arn,
                containerDefinitions=[container_def]
            )
            
            task_def_arn = response['taskDefinition']['taskDefinitionArn']
            logger.info(f"Created task definition: {task_def_arn}")
            
            return task_def_arn
            
        except ClientError as e:
            logger.error(f"Failed to create task definition: {e}")
            raise
    
    async def create_ecs_service(
        self,
        service_config: ECSServiceConfig,
        load_balancer_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create ECS service for the runbook agent.
        
        Args:
            service_config: ECS service configuration
            load_balancer_config: Optional load balancer configuration
            
        Returns:
            Service ARN
        """
        try:
            # Ensure cluster exists
            await self._ensure_cluster(service_config.cluster_name)
            
            # Prepare service definition
            service_def = {
                "serviceName": service_config.service_name,
                "cluster": service_config.cluster_name,
                "taskDefinition": service_config.task_definition_arn,
                "desiredCount": service_config.desired_count,
                "launchType": "FARGATE",
                "networkConfiguration": {
                    "awsvpcConfiguration": {
                        "subnets": service_config.subnets,
                        "securityGroups": service_config.security_groups,
                        "assignPublicIp": "ENABLED" if service_config.public_ip else "DISABLED"
                    }
                },
                "enableExecuteCommand": True,  # For debugging
                "propagateTags": "SERVICE"
            }
            
            # Add load balancer configuration if provided
            if load_balancer_config:
                service_def["loadBalancers"] = [load_balancer_config]
                service_def["healthCheckGracePeriodSeconds"] = 300
            
            # Create service
            response = self.ecs_client.create_service(**service_def)
            
            service_arn = response['service']['serviceArn']
            logger.info(f"Created ECS service: {service_arn}")
            
            return service_arn
            
        except ClientError as e:
            logger.error(f"Failed to create ECS service: {e}")
            raise
    
    async def update_service(
        self,
        cluster_name: str,
        service_name: str,
        task_definition_arn: str,
        desired_count: Optional[int] = None
    ) -> bool:
        """
        Update existing ECS service.
        
        Args:
            cluster_name: ECS cluster name
            service_name: ECS service name
            task_definition_arn: New task definition ARN
            desired_count: Optional new desired count
            
        Returns:
            True if successful
        """
        try:
            update_params = {
                "cluster": cluster_name,
                "service": service_name,
                "taskDefinition": task_definition_arn
            }
            
            if desired_count is not None:
                update_params["desiredCount"] = desired_count
            
            response = self.ecs_client.update_service(**update_params)
            
            logger.info(f"Updated ECS service: {service_name}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to update ECS service: {e}")
            return False
    
    async def get_service_status(
        self,
        cluster_name: str,
        service_name: str
    ) -> Dict[str, Any]:
        """
        Get ECS service status and metrics.
        
        Args:
            cluster_name: ECS cluster name
            service_name: ECS service name
            
        Returns:
            Service status information
        """
        try:
            response = self.ecs_client.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            if not response['services']:
                return {"error": "Service not found"}
            
            service = response['services'][0]
            
            # Get task details
            tasks_response = self.ecs_client.list_tasks(
                cluster=cluster_name,
                serviceName=service_name
            )
            
            task_details = []
            if tasks_response['taskArns']:
                tasks_desc = self.ecs_client.describe_tasks(
                    cluster=cluster_name,
                    tasks=tasks_response['taskArns']
                )
                
                task_details = [
                    {
                        "taskArn": task['taskArn'],
                        "lastStatus": task['lastStatus'],
                        "desiredStatus": task['desiredStatus'],
                        "healthStatus": task.get('healthStatus', 'UNKNOWN'),
                        "createdAt": task['createdAt'].isoformat(),
                        "cpu": task['cpu'],
                        "memory": task['memory']
                    }
                    for task in tasks_desc['tasks']
                ]
            
            return {
                "serviceName": service['serviceName'],
                "status": service['status'],
                "runningCount": service['runningCount'],
                "pendingCount": service['pendingCount'],
                "desiredCount": service['desiredCount'],
                "taskDefinition": service['taskDefinition'],
                "launchType": service['launchType'],
                "createdAt": service['createdAt'].isoformat(),
                "tasks": task_details
            }
            
        except ClientError as e:
            logger.error(f"Failed to get service status: {e}")
            return {"error": str(e)}
    
    async def setup_secrets(
        self,
        secrets: Dict[str, str],
        secret_prefix: str = "/runbook-agent/"
    ) -> Dict[str, str]:
        """
        Store configuration secrets in AWS Systems Manager Parameter Store.
        
        Args:
            secrets: Dictionary of secret key-value pairs
            secret_prefix: Prefix for parameter names
            
        Returns:
            Dictionary mapping secret names to parameter ARNs
        """
        parameter_arns = {}
        
        try:
            for key, value in secrets.items():
                parameter_name = f"{secret_prefix}{key}"
                
                # Store as SecureString parameter
                self.ssm_client.put_parameter(
                    Name=parameter_name,
                    Value=value,
                    Type='SecureString',
                    Overwrite=True,
                    Description=f"Secret for Monthly Runbook Agent: {key}"
                )
                
                # Build parameter ARN
                account_id = boto3.client('sts').get_caller_identity()['Account']
                parameter_arn = f"arn:aws:ssm:{self.region_name}:{account_id}:parameter{parameter_name}"
                parameter_arns[key] = parameter_arn
                
                logger.info(f"Stored secret parameter: {parameter_name}")
            
            return parameter_arns
            
        except ClientError as e:
            logger.error(f"Failed to setup secrets: {e}")
            raise
    
    async def create_deployment_resources(
        self,
        project_name: str = "monthly-runbook-agent",
        vpc_id: Optional[str] = None,
        subnet_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create all necessary AWS resources for deployment.
        
        Args:
            project_name: Project name for resource naming
            vpc_id: VPC ID (uses default if not provided)
            subnet_ids: Subnet IDs (uses default subnets if not provided)
            
        Returns:
            Dictionary with created resource details
        """
        resources = {}
        
        try:
            # Get default VPC and subnets if not provided
            if not vpc_id or not subnet_ids:
                vpc_info = await self._get_default_vpc_info()
                vpc_id = vpc_id or vpc_info['vpc_id']
                subnet_ids = subnet_ids or vpc_info['subnet_ids']
            
            # Create security group
            security_group_id = await self._create_security_group(
                f"{project_name}-sg",
                vpc_id
            )
            resources['security_group_id'] = security_group_id
            
            # Create ECS cluster
            cluster_arn = await self._ensure_cluster(f"{project_name}-cluster")
            resources['cluster_arn'] = cluster_arn
            
            # Create IAM roles
            execution_role_arn = await self._create_execution_role(f"{project_name}-execution-role")
            task_role_arn = await self._create_task_role(f"{project_name}-task-role")
            
            resources['execution_role_arn'] = execution_role_arn
            resources['task_role_arn'] = task_role_arn
            resources['vpc_id'] = vpc_id
            resources['subnet_ids'] = subnet_ids
            
            logger.info(f"Created deployment resources for {project_name}")
            return resources
            
        except Exception as e:
            logger.error(f"Failed to create deployment resources: {e}")
            raise
    
    async def _ensure_log_group(self, log_group_name: str):
        """Ensure CloudWatch log group exists."""
        try:
            self.logs_client.describe_log_groups(logGroupNamePrefix=log_group_name)
        except self.logs_client.exceptions.ResourceNotFoundException:
            self.logs_client.create_log_group(
                logGroupName=log_group_name,
                retentionInDays=30
            )
            logger.info(f"Created log group: {log_group_name}")
    
    async def _ensure_cluster(self, cluster_name: str) -> str:
        """Ensure ECS cluster exists."""
        try:
            response = self.ecs_client.describe_clusters(clusters=[cluster_name])
            if response['clusters']:
                return response['clusters'][0]['clusterArn']
        except ClientError:
            pass
        
        # Create cluster
        response = self.ecs_client.create_cluster(
            clusterName=cluster_name,
            capacityProviders=['FARGATE'],
            defaultCapacityProviderStrategy=[
                {
                    'capacityProvider': 'FARGATE',
                    'weight': 1
                }
            ]
        )
        
        cluster_arn = response['cluster']['clusterArn']
        logger.info(f"Created ECS cluster: {cluster_arn}")
        return cluster_arn
    
    async def _get_default_vpc_info(self) -> Dict[str, Any]:
        """Get default VPC and subnet information."""
        # Get default VPC
        vpcs = self.ec2_client.describe_vpcs(
            Filters=[{'Name': 'is-default', 'Values': ['true']}]
        )
        
        if not vpcs['Vpcs']:
            raise ValueError("No default VPC found")
        
        vpc_id = vpcs['Vpcs'][0]['VpcId']
        
        # Get subnets in default VPC
        subnets = self.ec2_client.describe_subnets(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )
        
        subnet_ids = [subnet['SubnetId'] for subnet in subnets['Subnets']]
        
        return {
            'vpc_id': vpc_id,
            'subnet_ids': subnet_ids
        }
    
    async def _create_security_group(self, group_name: str, vpc_id: str) -> str:
        """Create security group for the application."""
        try:
            response = self.ec2_client.create_security_group(
                GroupName=group_name,
                Description="Security group for Monthly Runbook Agent",
                VpcId=vpc_id
            )
            
            security_group_id = response['GroupId']
            
            # Add inbound rules
            self.ec2_client.authorize_security_group_ingress(
                GroupId=security_group_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 8000,
                        'ToPort': 8000,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'HTTP API'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 443,
                        'ToPort': 443,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'HTTPS'}]
                    }
                ]
            )
            
            logger.info(f"Created security group: {security_group_id}")
            return security_group_id
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidGroup.Duplicate':
                # Get existing security group
                response = self.ec2_client.describe_security_groups(
                    Filters=[
                        {'Name': 'group-name', 'Values': [group_name]},
                        {'Name': 'vpc-id', 'Values': [vpc_id]}
                    ]
                )
                return response['SecurityGroups'][0]['GroupId']
            raise
    
    async def _create_execution_role(self, role_name: str) -> str:
        """Create ECS task execution role."""
        iam_client = boto3.client('iam')
        
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        try:
            response = iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description="ECS task execution role for Monthly Runbook Agent"
            )
            
            role_arn = response['Role']['Arn']
            
            # Attach managed policy
            iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn='arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy'
            )
            
            logger.info(f"Created execution role: {role_arn}")
            return role_arn
            
        except iam_client.exceptions.EntityAlreadyExistsException:
            response = iam_client.get_role(RoleName=role_name)
            return response['Role']['Arn']
    
    async def _create_task_role(self, role_name: str) -> str:
        """Create ECS task role with necessary permissions."""
        iam_client = boto3.client('iam')
        
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        task_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "ssm:GetParameter",
                        "ssm:GetParameters",
                        "ssm:GetParametersByPath",
                        "secretsmanager:GetSecretValue",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents"
                    ],
                    "Resource": "*"
                }
            ]
        }
        
        try:
            response = iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description="ECS task role for Monthly Runbook Agent"
            )
            
            role_arn = response['Role']['Arn']
            
            # Create and attach inline policy
            iam_client.put_role_policy(
                RoleName=role_name,
                PolicyName=f"{role_name}-policy",
                PolicyDocument=json.dumps(task_policy)
            )
            
            logger.info(f"Created task role: {role_arn}")
            return role_arn
            
        except iam_client.exceptions.EntityAlreadyExistsException:
            response = iam_client.get_role(RoleName=role_name)
            return response['Role']['Arn']