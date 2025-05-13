import json
import base64
import os
import boto3
from datetime import datetime
from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

# Initialize powertools
logger = Logger(service="FootballDataConsumer")
metrics = Metrics(namespace="FootballDataProcessor", service="Consumer")

# Get environment variables
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE')
MSK_TOPIC = os.environ.get('MSK_TOPIC', 'football-events')

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table = None

def init_dynamodb():
    """Initialize DynamoDB table resource"""
    global table
    if table is None:
        table = dynamodb.Table(DYNAMODB_TABLE)
    return table

def derive_season(timestamp_str):
    """Derive the season from the timestamp"""
    try:
        # Parse the timestamp
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

        # Get the year
        year = timestamp.year

        # If the month is before August, it's the previous season
        if timestamp.month < 8:
            return f"{year-1}/{year}"
        else:
            return f"{year}/{year+1}"
    except Exception as e:
        logger.error(f"Error deriving season: {str(e)}")
        return "unknown"

def process_record(record):
    """Process a single Kafka record"""
    try:
        # Extract the value from the record
        if 'value' in record:
            value_bytes = base64.b64decode(record["value"])
            event = json.loads(value_bytes.decode('utf-8'))

            # Log the received event
            logger.info(f"Received event: {json.dumps(event)}")

            # Get the event type
            event_type = event.get('event_type', 'unknown')

            # Derive the season from the timestamp
            timestamp = event.get('timestamp', '')
            season = derive_season(timestamp)

            # Add the season to the event
            event['season'] = season

            # Make sure we have event_timestamp for DynamoDB sort key
            if 'timestamp' in event and 'event_timestamp' not in event:
                event['event_timestamp'] = event['timestamp']

            # Create the composite sort key for LSI (event_type#event_timestamp)
            event_timestamp = event.get('event_timestamp', '')
            event['event_type_timestamp'] = f"{event_type}#{event_timestamp}"

            logger.info(f"Created composite key: {event['event_type_timestamp']}")

            return event
    except Exception as e:
        logger.exception(f"Error processing record: {str(e)}")

    return None

def batch_write_to_dynamodb(items):
    """Write a batch of items to DynamoDB using batch_writer"""
    if not items:
        return 0

    # Use the table resource which handles the type conversion automatically
    table = init_dynamodb()
    success_count = 0

    try:
        # Use the batch_writer context manager which handles batching automatically
        # It will automatically split into batches of 25 items and handle retries
        with table.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)

        # If we get here, all items were successfully written
        success_count = len(items)
        logger.info(f"Successfully wrote {len(items)} items to DynamoDB using batch_writer")

    except Exception as e:
        logger.exception(f"Error in batch_write_to_dynamodb: {str(e)}")

    return success_count

@logger.inject_lambda_context(log_event=True)
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event, context: LambdaContext):
    """Lambda handler for processing Kafka events"""
    logger.info("Consumer Lambda invoked")

    # Log the entire event for debugging
    logger.info(f"Event structure: {json.dumps(event)}")

    # Log context information
    logger.info(f"Function name: {context.function_name}")
    logger.info(f"Request ID: {context.aws_request_id}")

    # Process each record
    success_count = 0
    total_records = 0
    processed_items = []

    # The event structure from the MSK event source mapping is different
    if 'records' in event:
        for partition_key, records in event['records'].items():
            total_records += len(records)
            logger.info(f"Processing {len(records)} records from partition {partition_key}")
            metrics.add_metric(name="RecordsReceived", unit=MetricUnit.Count, value=len(records))

            for record in records:
                item = process_record(record)
                if item:
                    processed_items.append(item)

        # Batch write to DynamoDB
        if processed_items:
            success_count = batch_write_to_dynamodb(processed_items)
            metrics.add_metric(name="RecordsProcessed", unit=MetricUnit.Count, value=success_count)
    else:
        logger.warning("Unexpected event structure - 'records' field not found")

    logger.info(f"Processed {success_count} out of {total_records} records successfully")

    # Add success rate metric
    if total_records > 0:
        success_rate = (success_count / total_records) * 100
        metrics.add_metric(name="ProcessingSuccessRate", unit=MetricUnit.Percent, value=success_rate)

    if success_count != total_records:
        ## if we are not able to process all records, raise an exception
        # lambda is Idempotent, so we can safely raise an exception
        # for kinesis stream and sqs here we can use partial batch or bisect feature
        logger.warning(f"Processed {success_count} out of {total_records} records successfully")
        metrics.add_metric(name="ProcessingFailures", unit=MetricUnit.Count, value=total_records - success_count)
        raise Exception(f"Processed {success_count} out of {total_records} records successfully")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": f"{success_count} records processed successfully"
        })
    }
