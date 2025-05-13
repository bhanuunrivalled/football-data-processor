import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';

export class VpcStack extends cdk.Stack {
  public readonly vpc: ec2.Vpc;
  public readonly kafkaSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Create a VPC with public and private subnets across 3 availability zones
    this.vpc = new ec2.Vpc(this, 'FootballDataVpc', {
      maxAzs: 3,
      natGateways: 1, // Use 1 NAT Gateway to reduce costs
      subnetConfiguration: [
        {
          cidrMask: 24,
          name: 'Public',
          subnetType: ec2.SubnetType.PUBLIC,
        },
        {
          cidrMask: 24,
          name: 'Private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        }
      ]
    });

    // Create a security group for Kafka
    this.kafkaSecurityGroup = new ec2.SecurityGroup(this, 'KafkaSecurityGroup', {
      vpc: this.vpc,
      description: 'Security group for Kafka cluster',
      allowAllOutbound: true
    });

    // Allow Kafka traffic within the security group
    this.kafkaSecurityGroup.addIngressRule(
      this.kafkaSecurityGroup,
      ec2.Port.allTraffic(),
      'Allow all traffic within the security group'
    );

    // Output the VPC ID
    new cdk.CfnOutput(this, 'VpcId', {
      value: this.vpc.vpcId,
      description: 'The ID of the VPC',
      exportName: 'FootballDataVpcId'
    });
  }
}
