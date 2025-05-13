import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import { ProducerStack } from './producer-stack';
import { QueryStack } from './query-stack';

export class ApiStack extends cdk.Stack {
  public readonly apiEndpoint: string;

  constructor(scope: Construct, id: string, producerStack: ProducerStack, queryStack: QueryStack, props?: cdk.StackProps) {
    super(scope, id, props);

    // Get environment from context or default to 'dev'
    const environment = this.node.tryGetContext('environment') || 'dev';

    // Reference the Lambda functions from other stacks
    const producerFunction = producerStack.producerFunction;
    const queryFunction = queryStack.queryFunction;

    // Create API Gateway
    const api = new apigateway.RestApi(this, 'FootballDataApi', {
      restApiName: 'Football Data API',
      description: 'API for football data processing',
      cloudWatchRole: true,
      deployOptions: {
        stageName: 'prod',
        metricsEnabled: true,
        loggingLevel: apigateway.MethodLoggingLevel.INFO,
        dataTraceEnabled: true,
        tracingEnabled: true // Enable X-Ray tracing
      }
    });

    // Create events resource for producer
    const events = api.root.addResource('events');

    // Add POST method to events resource
    events.addMethod('POST', new apigateway.LambdaIntegration(producerFunction, {
      proxy: true
    }));

    // Create matches resource for query handler
    const matches = api.root.addResource('matches');

    // Create match resource for specific match queries
    const match = matches.addResource('{match_id}');

    // Add GET method to match resource (get all events for a match)
    match.addMethod('GET', new apigateway.LambdaIntegration(queryFunction, {
      proxy: true
    }));

    // Create goals resource for match goals
    const goals = match.addResource('goals');

    // Add GET method to goals resource (get all goals for a match)
    goals.addMethod('GET', new apigateway.LambdaIntegration(queryFunction, {
      proxy: true
    }));

    // Create passes resource for match passes
    const passes = match.addResource('passes');

    // Add GET method to passes resource (get all passes for a match)
    passes.addMethod('GET', new apigateway.LambdaIntegration(queryFunction, {
      proxy: true
    }));

    // Store the API endpoint for reference by other stacks
    this.apiEndpoint = api.url;

    // Output the API endpoint
    new cdk.CfnOutput(this, 'ApiEndpoint', {
      value: api.url,
      description: 'The URL of the API Gateway endpoint',
      exportName: 'FootballDataApiEndpoint'
    });
  }
}
