import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as path from 'path';
import { ManagedKafkaEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';
import { VpcStack } from './vpc-stack';
import { MskStack } from './msk-stack';
import { EnvironmentConfig, getConfig } from '../config/config';
import { getTopicName, getGroupName, addPermissionsToPolicy } from './helpers';

export class ConsumerStack extends cdk.Stack {
  public readonly dynamoTable: dynamodb.Table;

  constructor(scope: Construct, id: string, vpcStack: VpcStack, mskStack: MskStack, props?: cdk.StackProps) {
    super(scope, id, props);

    // Get environment from context or default to 'dev'
    const environment = this.node.tryGetContext('environment') || 'dev';
    const config = getConfig(environment);

    // Generate a unique timestamp for this deployment
    const deploymentTimestamp = new Date().getTime();

    // Log the environment and configuration
    console.log(`Deploying ConsumerStack with environment: ${environment}`);
    console.log(`Consumer config: ${JSON.stringify(config.consumer, null, 2)}`);
    console.log(`Deployment timestamp: ${deploymentTimestamp}`);

    // Reference the VPC and security group from the VPC stack
    const vpc = vpcStack.vpc;
    const kafkaSecurityGroup = vpcStack.kafkaSecurityGroup;

    // Reference the MSK cluster ARN and topic from the MSK stack
    const mskClusterArn = mskStack.mskArn;
    const kafkaTopic = mskStack.kafkaTopic;

    // Create DynamoDB table
    this.dynamoTable = new dynamodb.Table(this, 'FootballEventsTable', {
      partitionKey: { name: 'match_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'event_timestamp', type: dynamodb.AttributeType.STRING },
      billingMode: config.dynamodb.billingMode === 'PROVISIONED'
        ? dynamodb.BillingMode.PROVISIONED
        : dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: environment === 'prod'
        ? cdk.RemovalPolicy.RETAIN
        : cdk.RemovalPolicy.DESTROY,
      pointInTimeRecovery: config.dynamodb.pointInTimeRecovery,
    });

    // Add LSI with composite sort key for time-ordered event type queries
    this.dynamoTable.addLocalSecondaryIndex({
      indexName: 'EventTypeTimestampIndex',
      sortKey: { name: 'event_type_timestamp', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL
    });

    // Create a role for the consumer Lambda function
    const consumerRole = new iam.Role(this, 'ConsumerRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaVPCAccessExecutionRole'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaMSKExecutionRole'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('AWSXrayWriteOnlyAccess') // Add X-Ray permissions
      ]
    });

    // Define consumer group ID
    const consumerGroupId = 'FootballDataConsumerGroup';

    // Add MSK permissions to the role using the helper function
    addPermissionsToPolicy(consumerRole, {
        "kafka-cluster:Connect": [mskClusterArn],
            "kafka-cluster:DescribeGroup": [getGroupName(mskClusterArn, consumerGroupId)],
            "kafka-cluster:AlterGroup": [getGroupName(mskClusterArn, consumerGroupId)],
            "kafka-cluster:DescribeTopic": [getTopicName(mskClusterArn, kafkaTopic)],
            "kafka-cluster:ReadData": [getTopicName(mskClusterArn, kafkaTopic)],
            "kafka-cluster:ReadGroup": [getGroupName(mskClusterArn, consumerGroupId)],
            "kafka-cluster:DescribeClusterDynamicConfiguration": [mskClusterArn]
    });

    // Add DynamoDB permissions to the role
    consumerRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'dynamodb:PutItem',
        'dynamodb:GetItem',
        'dynamodb:UpdateItem',
        'dynamodb:DeleteItem',
        'dynamodb:BatchWriteItem',
        'dynamodb:BatchGetItem',
        'dynamodb:Query',
        'dynamodb:Scan'
      ],
      resources: [
        this.dynamoTable.tableArn,
        `${this.dynamoTable.tableArn}/index/*`
      ]
    }));

    // Create the consumer Lambda function
    const consumerFunction = new lambda.Function(this, 'ConsumerFunction', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'app.lambda_handler',

      code: lambda.Code.fromAsset(path.join(__dirname, '../../lambdas/event_consumer'), {
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
      timeout: cdk.Duration.seconds(config.consumer.lambdaTimeout),
      memorySize: config.consumer.lambdaMemorySize,
      vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS
      },
      securityGroups: [kafkaSecurityGroup],
      environment: {
        "LOG_LEVEL": environment === 'prod' ? "INFO" : "DEBUG",
        "MSK_CLUSTER_ARN": mskClusterArn,
        "MSK_TOPIC": kafkaTopic,
        "DYNAMODB_TABLE": this.dynamoTable.tableName,
        "ENVIRONMENT": environment
      },
      role: consumerRole,
      tracing: lambda.Tracing.ACTIVE // Enable X-Ray tracing
    });

    // Output the DynamoDB table name
    new cdk.CfnOutput(this, 'DynamoDBTableName', {
      value: this.dynamoTable.tableName,
      description: 'The name of the DynamoDB table',
      exportName: 'FootballDataDynamoDBTableName'
    });

    // Add Kafka event source mapping to the consumer Lambda
    const eventSource = new ManagedKafkaEventSource({
      clusterArn: mskClusterArn,
      topic: kafkaTopic,
      batchSize: config.consumer.batchSize,
      startingPosition: lambda.StartingPosition.TRIM_HORIZON,
      consumerGroupId: consumerGroupId,
      maxBatchingWindow: cdk.Duration.seconds(config.consumer.maxBatchingWindow)
    });

    // Add the event source to the Lambda function
    consumerFunction.addEventSource(eventSource);

    // Output the consumer Lambda function name
    new cdk.CfnOutput(this, 'ConsumerFunctionName', {
      value: consumerFunction.functionName,
      description: 'The name of the consumer Lambda function',
      exportName: 'FootballDataConsumerFunctionName'
    });
  }
}
