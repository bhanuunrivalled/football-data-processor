import * as iam from 'aws-cdk-lib/aws-iam';
import * as cdk from 'aws-cdk-lib';

/**
 * Constructs the ARN for a Kafka topic given the ARN of the Kafka cluster and the topic name.
 * @param kafkaClusterArn The ARN of the Kafka cluster
 * @param topicName The name of the Kafka topic
 * @returns The ARN of the Kafka topic
 */
export function getTopicName(kafkaClusterArn: string, topicName: string): string {
  // Use Fn.join to construct the ARN dynamically at deployment time
  return cdk.Fn.join('', [
    'arn:aws:kafka:',
    cdk.Fn.select(3, cdk.Fn.split(':', kafkaClusterArn)), // region
    ':',
    cdk.Fn.select(4, cdk.Fn.split(':', kafkaClusterArn)), // account
    ':topic/',
    cdk.Fn.select(1, cdk.Fn.split('/', kafkaClusterArn)), // cluster name
    '/*/',
    topicName
  ]);
}

/**
 * Constructs the ARN for a Kafka consumer group given the ARN of the Kafka cluster and the group name.
 * @param kafkaClusterArn The ARN of the Kafka cluster
 * @param groupName The name of the Kafka consumer group
 * @returns The ARN of the Kafka consumer group
 */
export function getGroupName(kafkaClusterArn: string, groupName: string): string {
  // Use Fn.join to construct the ARN dynamically at deployment time
  return cdk.Fn.join('', [
    'arn:aws:kafka:',
    cdk.Fn.select(3, cdk.Fn.split(':', kafkaClusterArn)), // region
    ':',
    cdk.Fn.select(4, cdk.Fn.split(':', kafkaClusterArn)), // account
    ':group/',
    cdk.Fn.select(1, cdk.Fn.split('/', kafkaClusterArn)), // cluster name
    '/*/',
    groupName
  ]);
}

/**
 * Adds permissions to an IAM role.
 * @param role The IAM role to add permissions to
 * @param permissions A map of actions to resources
 */
export function addPermissionsToPolicy(role: iam.Role, permissions: Record<string, string[]>): void {
  for (const [action, resources] of Object.entries(permissions)) {
    const resourceList = resources.length > 0 ? resources : ['*'];

    for (const resource of resourceList) {
      role.addToPolicy(new iam.PolicyStatement({
        actions: [action],
        resources: [resource],
        effect: iam.Effect.ALLOW
      }));
    }
  }
}
