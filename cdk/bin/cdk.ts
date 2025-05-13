#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { VpcStack } from '../lib/vpc-stack';
import { MskStack } from '../lib/msk-stack';
import { ProducerStack } from '../lib/producer-stack';
import { ConsumerStack } from '../lib/consumer-stack';
import { QueryStack } from '../lib/query-stack';
import { ApiStack } from '../lib/api-stack';
import * as dotenv from 'dotenv'


const app = new cdk.App();

// Define environment
const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION
};

console.log(`Environment: ${env.account}/${env.region}`);

// Create VPC stack
const vpcStack = new VpcStack(app, 'FootballDataVpcStack', { env });

// Create MSK stack
const mskStack = new MskStack(app, 'FootballDataMskStack', vpcStack,{ env });

// Add dependency to ensure VPC stack is created first
mskStack.addDependency(vpcStack);

// Create producer stack
const producerStack = new ProducerStack(app, 'FootballDataProducerStack', vpcStack, mskStack, { env });

// Add dependencies to ensure VPC and MSK stacks are created first
producerStack.addDependency(vpcStack);
producerStack.addDependency(mskStack);

// Create consumer stack
const consumerStack = new ConsumerStack(app, 'FootballDataConsumerStack', vpcStack, mskStack, { env });

// Add dependencies to ensure VPC and MSK stacks are created first
consumerStack.addDependency(vpcStack);
consumerStack.addDependency(mskStack);

// Create query stack
const queryStack = new QueryStack(app, 'FootballDataQueryStack', consumerStack, { env });

// Add dependencies to ensure consumer stack is created first
queryStack.addDependency(consumerStack);

// Create API stack (consolidating all API Gateway resources)
const apiStack = new ApiStack(app, 'FootballDataApiStack', producerStack, queryStack, { env });

// Add dependencies to ensure other stacks are created first
apiStack.addDependency(producerStack);
apiStack.addDependency(queryStack);
