import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as path from 'path';
import { ConsumerStack } from './consumer-stack';
import { EnvironmentConfig, getConfig } from '../config/config';

export class QueryStack extends cdk.Stack {
  public readonly queryFunction: lambda.Function;

  constructor(scope: Construct, id: string, consumerStack: ConsumerStack, props?: cdk.StackProps) {
    super(scope, id, props);

    // Get environment from context or default to 'dev'
    const environment = this.node.tryGetContext('environment') || 'dev';
    const config = getConfig(environment);

    // Reference the DynamoDB table from the consumer stack
    const dynamoTable = consumerStack.dynamoTable;

    // Create a role for the query handler Lambda function
    const queryHandlerRole = new iam.Role(this, 'QueryHandlerRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('AWSXrayWriteOnlyAccess') // Add X-Ray permissions
      ]
    });

    // Add DynamoDB permissions to the query handler role
    queryHandlerRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'dynamodb:GetItem',
        'dynamodb:Query',
        'dynamodb:Scan'
      ],
      resources: [
        dynamoTable.tableArn,
        `${dynamoTable.tableArn}/index/*`
      ]
    }));

    // Create the query handler Lambda function
    this.queryFunction = new lambda.Function(this, 'QueryHandlerFunction', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'app.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../lambdas/query_handler'), {
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
      timeout: cdk.Duration.seconds(30),
      memorySize: 256,
      environment: {
        "LOG_LEVEL": "INFO",
        "DYNAMODB_TABLE": dynamoTable.tableName,
        "ENVIRONMENT": environment
      },
      role: queryHandlerRole,
      tracing: lambda.Tracing.ACTIVE // Enable X-Ray tracing
    });

    // Output the query handler Lambda function name
    new cdk.CfnOutput(this, 'QueryHandlerFunctionName', {
      value: this.queryFunction.functionName,
      description: 'The name of the query handler Lambda function',
      exportName: 'FootballDataQueryHandlerFunctionName'
    });
  }
}
