import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as msk from 'aws-cdk-lib/aws-msk';
import { VpcStack } from './vpc-stack';

export class MskStack extends cdk.Stack {
  public readonly mskCluster: msk.CfnServerlessCluster;
  public readonly mskArn: string;
  public readonly kafkaTopic: string;

  constructor(scope: Construct, id: string, vpcStack: VpcStack, props?: cdk.StackProps) {
    super(scope, id, props);

    // Define the Kafka topic name
    this.kafkaTopic = 'football-events';

    // Reference the VPC and security group from the VPC stack
    const vpc = vpcStack.vpc;
    const kafkaSecurityGroup = vpcStack.kafkaSecurityGroup;

    // Get the private subnet IDs
    const privateSubnetIds = vpc.privateSubnets.map(subnet => subnet.subnetId);

    // Create the MSK Serverless Cluster
    this.mskCluster = new msk.CfnServerlessCluster(this, 'FootballDataMskCluster', {
      clusterName: 'FootballDataMskCluster',
      clientAuthentication: {
        sasl: {
          iam: {
            enabled: true,
          },
        },
      },
      vpcConfigs: [
        {
          subnetIds: privateSubnetIds,
          securityGroups: [kafkaSecurityGroup.securityGroupId],
        },
      ],
    });

    // Store the MSK ARN for reference by other stacks
    this.mskArn = this.mskCluster.attrArn;

    // Output the MSK ARN
    new cdk.CfnOutput(this, 'MskClusterArn', {
      value: this.mskArn,
      description: 'The ARN of the MSK Serverless Cluster',
      exportName: 'FootballDataMskClusterArn'
    });
  }
}
