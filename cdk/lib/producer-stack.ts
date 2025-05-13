import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as path from 'path';
import { VpcStack } from './vpc-stack';
import { MskStack } from './msk-stack';
import { getTopicName, addPermissionsToPolicy } from './helpers';
import { EnvironmentConfig, getConfig } from '../config/config';

export class ProducerStack extends cdk.Stack {
  public readonly producerFunction: lambda.Function;

  constructor(scope: Construct, id: string, vpcStack: VpcStack, mskStack: MskStack, props?: cdk.StackProps) {
    super(scope, id, props);

    // Get environment from context or default to 'dev'
    const environment = this.node.tryGetContext('environment') || 'dev';
    const config = getConfig(environment);

    // Reference the VPC and security group from the VPC stack
    const vpc = vpcStack.vpc;
    const kafkaSecurityGroup = vpcStack.kafkaSecurityGroup;

    // Reference the MSK cluster ARN and topic from the MSK stack
    const mskClusterArn = mskStack.mskArn;
    const kafkaTopic = mskStack.kafkaTopic;

    // Create a role for the producer Lambda function
    const producerRole = new iam.Role(this, 'ProducerRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaVPCAccessExecutionRole'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('AWSXrayWriteOnlyAccess') // Add X-Ray permissions
      ]
    });

    // Add MSK permissions to the role using the helper function
    addPermissionsToPolicy(producerRole, {
      'kafka:DescribeCluster': [mskClusterArn],
      'kafka:GetBootstrapBrokers': [mskClusterArn],
      'kafka-cluster:Connect': [mskClusterArn],
      'kafka-cluster:DescribeCluster': [mskClusterArn],
      'kafka-cluster:CreateTopic': [getTopicName(mskClusterArn, kafkaTopic)],
      'kafka-cluster:WriteData': [getTopicName(mskClusterArn, kafkaTopic)],
      'kafka-cluster:ReadData': [getTopicName(mskClusterArn, kafkaTopic)],
      'kafka-cluster:DescribeTopic': [getTopicName(mskClusterArn, kafkaTopic)],
      'kafka-cluster:AlterTopic': [getTopicName(mskClusterArn, kafkaTopic)]
    });

    // Create the producer Lambda function
    this.producerFunction = new lambda.Function(this, 'ProducerFunction', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'app.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../lambdas/event_ingest'), {
        bundling: {
          image: lambda.Runtime.PYTHON_3_11.bundlingImage,
          command: [
            'bash', '-c', [
              'pip install --no-cache-dir -r requirements.txt -t /tmp/asset-output',
              'cp -r . /tmp/asset-output',
              'cp -r /tmp/asset-output/* /asset-output/'
            ].join(' && ')
          ]
        }
      }),
      timeout: cdk.Duration.minutes(5),
      memorySize: 256,
      vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS
      },
      securityGroups: [kafkaSecurityGroup],
      environment: {
        "LOG_LEVEL": environment === 'prod' ? "INFO" : "DEBUG",
        "MSK_CLUSTER_ARN": mskClusterArn,
        "MSK_TOPIC": kafkaTopic
      },
      role: producerRole
    });

    // Output the producer Lambda function name
    new cdk.CfnOutput(this, 'ProducerFunctionName', {
      value: this.producerFunction.functionName,
      description: 'The name of the producer Lambda function',
      exportName: 'FootballDataProducerFunctionName'
    });
  }
}
