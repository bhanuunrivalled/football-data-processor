import json
import os
import uuid
import socket
import logging
import boto3
import jsonschema
from kafka import KafkaProducer, KafkaAdminClient
from kafka.admin import NewTopic
from kafka.errors import TopicAlreadyExistsError
from kafka.sasl.oauth import AbstractTokenProvider
from aws_msk_iam_sasl_signer import MSKAuthTokenProvider

logger = logging.getLogger()
logger.setLevel("INFO")


# Load the JSON schema for validation
with open('schema.json', 'r') as f:
    EVENT_SCHEMA = json.load(f)

# Get environment variables
MSK_CLUSTER_ARN = os.environ.get('MSK_CLUSTER_ARN')
MSK_TOPIC = os.environ.get('MSK_TOPIC', 'football-events')
AWS_REGION = os.environ.get('AWS_REGION')

# Get bootstrap servers from MSK cluster
def get_bootstrap_servers():
    try:
        logger.info(f"Getting bootstrap servers for cluster ARN: {MSK_CLUSTER_ARN}")
        kafka_client = boto3.client('kafka', region_name=AWS_REGION)
        response = kafka_client.get_bootstrap_brokers(ClusterArn=MSK_CLUSTER_ARN)
        bootstrap_servers = response.get('BootstrapBrokerStringSaslIam')

        if not bootstrap_servers:
            logger.error("Failed to get bootstrap servers. Response: " + json.dumps(response))
            raise ValueError("Failed to get bootstrap servers. Check the cluster ARN and your permissions.")

        logger.info(f"Successfully retrieved bootstrap servers: {bootstrap_servers}")
        return bootstrap_servers
    except Exception as e:
        logger.exception(f"Error getting bootstrap servers: {str(e)}")
        raise

# Create a custom token provider class
class MSKTokenProvider(AbstractTokenProvider):
    def token(self):
        token, _ = MSKAuthTokenProvider.generate_auth_token(AWS_REGION)
        return token

# Ensure Kafka topic exists
def ensure_topic_exists(bootstrap_servers, topic_name, num_partitions=3, replication_factor=2):
    try:
        # Create MSK token provider
        token_provider = MSKTokenProvider()

        # Create Kafka admin client with IAM authentication
        admin_client = KafkaAdminClient(
            bootstrap_servers=bootstrap_servers,
            security_protocol='SASL_SSL',
            sasl_mechanism='OAUTHBEARER',
            sasl_oauth_token_provider=token_provider,
            client_id=socket.gethostname(),
            api_version=(2, 6)  # Use a more recent API version compatible with MSK Serverless
        )

        try:
            # List existing topics
            topics = admin_client.list_topics()
            logger.info(f"Existing topics: {topics}")

            # Check if our topic exists
            if topic_name not in topics:
                logger.info(f"Topic {topic_name} does not exist. Creating it...")

                # Create the topic
                admin_client.create_topics([
                    NewTopic(
                        name=topic_name,
                        num_partitions=num_partitions,
                        replication_factor=replication_factor
                    )
                ])
                logger.info(f"Successfully created topic: {topic_name}")
            else:
                logger.info(f"Topic {topic_name} already exists")

        except TopicAlreadyExistsError:
            logger.info(f"Topic {topic_name} already exists (race condition)")
        except Exception as e:
            logger.error(f"Error creating/checking topic: {str(e)}")
            raise
        finally:
            admin_client.close()

    except Exception as e:
        logger.exception(f"Error ensuring topic exists: {str(e)}")
        raise

# Initialize Kafka producer
def get_kafka_producer():
    try:
        logger.info("Starting to create Kafka producer")

        # Get bootstrap servers
        bootstrap_servers = get_bootstrap_servers()
        logger.info(f"Got bootstrap servers: {bootstrap_servers}")

        # Ensure the topic exists
        logger.info(f"Ensuring topic {MSK_TOPIC} exists")
        ensure_topic_exists(bootstrap_servers, MSK_TOPIC)

        # Create MSK token provider
        logger.info("Creating MSK token provider")
        token_provider = MSKTokenProvider()

        # Create Kafka producer with IAM authentication
        logger.info("Creating Kafka producer with IAM authentication")
        producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            security_protocol='SASL_SSL',
            sasl_mechanism='OAUTHBEARER',
            sasl_oauth_token_provider=token_provider,
            client_id=socket.gethostname(),
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            api_version=(2, 6)  # Fixed API version to match what Kafka supports
        )

        logger.info("Kafka producer created successfully")
        return producer
    except Exception as e:
        logger.exception(f"Failed to create Kafka producer: {str(e)}")
        raise

# Validate event against JSON schema
def validate_event(event):
    try:
        jsonschema.validate(instance=event, schema=EVENT_SCHEMA)
        return True
    except jsonschema.exceptions.ValidationError as e:
        logger.error(f"Event validation failed: {str(e)}")
        return False

# Process the API Gateway event
def process_event(body):
    try:
        logger.info(f"Processing event: {json.dumps(body)}")

        # Validate the event
        logger.info("Validating event against schema")
        if not validate_event(body):
            logger.warning("Event validation failed")
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "message": "Invalid event format"
                })
            }

        # Get the match_id to use as partition key
        match_id = body.get('match_id')
        if not match_id:
            logger.warning("match_id is missing in the event")
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "message": "match_id is required"
                })
            }

        # Initialize Kafka producer
        logger.info("Getting Kafka producer")
        producer = get_kafka_producer()

        # Add a unique event_id if not present
        if 'event_id' not in body:
            body['event_id'] = str(uuid.uuid4())
            logger.info(f"Generated event_id: {body['event_id']}")

        # Send the event to Kafka
        logger.info(f"Sending event to Kafka topic {MSK_TOPIC} with key {match_id}")
        future = producer.send(
            topic=MSK_TOPIC,
            key=match_id,
            value=body
        )

        # Wait for the result
        logger.info("Waiting for send confirmation")
        record_metadata = future.get(timeout=10)

        # Log the result
        logger.info(f"Event published to {record_metadata.topic} partition {record_metadata.partition} offset {record_metadata.offset}")

        # Return success response
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Event published successfully",
                "event_id": body['event_id']
            })
        }
    except Exception as e:
        logger.exception(f"Error publishing event: {str(e)}")

        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": f"Error publishing event: {str(e)}"
            })
        }

# Main Lambda handler
def lambda_handler(event, context):  # Using context instead of _ for better logging
    logger.info("Lambda handler started")
    logger.info(f"Received event: {json.dumps(event)}")
    logger.info(f"Lambda context: RequestId={context.aws_request_id}, Function={context.function_name}, Remaining Time={context.get_remaining_time_in_millis()}ms")

    try:
        # Parse the request body from API Gateway event
        if 'body' in event:
            logger.info("Parsing request body")
            body = json.loads(event['body'])
            logger.info(f"Parsed body: {json.dumps(body)}")
        else:
            logger.warning("Missing request body in the event")
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "message": "Missing request body"
                })
            }

        # Process the event
        logger.info("Processing the event")
        result = process_event(body)
        logger.info(f"Process result: {json.dumps(result)}")
        return result
    except Exception as e:
        logger.exception(f"Error processing request: {str(e)}")

        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": f"Error processing request: {str(e)}"
            })
        }
