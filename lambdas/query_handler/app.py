import json
import os
import logging
import boto3
from boto3.dynamodb.conditions import Key, Attr
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.metrics import MetricUnit

SERVICE_NAME = "FootballDataQueryHandler"

logger = Logger(service=SERVICE_NAME)
tracer = Tracer(service=SERVICE_NAME)
metrics = Metrics(namespace="FootballDataProcessor", service=SERVICE_NAME)


# Initialize API Gateway resolver
app = APIGatewayRestResolver()

# Get environment variables
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table = None

def init_dynamodb():
    """Initialize DynamoDB table resource"""
    global table
    if table is None:
        table = dynamodb.Table(DYNAMODB_TABLE)
    return table

@app.get("/matches/<match_id>")
@tracer.capture_method
def get_match_events(match_id):
    """Get all events for a specific match in chronological order"""
    try:
        logger.info(f"Getting events for match: {match_id}")
        metrics.add_metric(name="GetMatchEventsRequests", unit=MetricUnit.Count, value=1)

        # Query DynamoDB for all events with the given match_id
        # Results will be sorted by event_timestamp (sort key)
        response = init_dynamodb().query(
            KeyConditionExpression=Key('match_id').eq(match_id)
        )

        # Extract items from the response
        items = response.get('Items', [])

        # Log the number of events found
        logger.info(f"Found {len(items)} events for match {match_id}")

        # Return the events
        return {
            "match_id": match_id,
            "event_count": len(items),
            "events": items
        }
    except Exception as e:
        logger.exception(f"Error getting match events: {str(e)}")
        return {"error": str(e)}, 500

@app.get("/matches/<match_id>/goals")
@tracer.capture_method
def get_match_goals(match_id):
    """Get all goals for a specific match in chronological order"""
    try:
        logger.info(f"Getting goals for match: {match_id}")
        metrics.add_metric(name="GetMatchGoalsRequests", unit=MetricUnit.Count, value=1)

        # Query DynamoDB using the LSI with composite sort key
        response = init_dynamodb().query(
            KeyConditionExpression=Key('match_id').eq(match_id) &
                                  Key('event_type_timestamp').begins_with('goal#'),
            IndexName='EventTypeTimestampIndex'
        )

        # Extract items from the response
        items = response.get('Items', [])

        # Log the number of goals found
        logger.info(f"Found {len(items)} goals for match {match_id}")

        # Return the goals
        return {
            "match_id": match_id,
            "total_goals": len(items),
            "goals": items
        }
    except Exception as e:
        logger.exception(f"Error getting match goals: {str(e)}")
        return {"error": str(e)}, 500

@app.get("/matches/<match_id>/passes")
@tracer.capture_method
def get_match_passes(match_id):
    """Get all passes for a specific match in chronological order"""
    try:
        logger.info(f"Getting passes for match: {match_id}")
        metrics.add_metric(name="GetMatchPassesRequests", unit=MetricUnit.Count, value=1)

        # Query DynamoDB using the LSI with composite sort key
        response = init_dynamodb().query(
            KeyConditionExpression=Key('match_id').eq(match_id) &
                                  Key('event_type_timestamp').begins_with('pass#'),
            IndexName='EventTypeTimestampIndex'
        )

        # Extract items from the response
        items = response.get('Items', [])

        # Log the number of passes found
        logger.info(f"Found {len(items)} passes for match {match_id}")

        # Return the passes
        return {
            "match_id": match_id,
            "total_passes": len(items),
            "passes": items
        }
    except Exception as e:
        logger.exception(f"Error getting match passes: {str(e)}")
        return {"error": str(e)}, 500

@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event, context):
    """Main Lambda handler function"""
    logger.info("Query handler invoked")

    # Process the event with the API Gateway resolver
    return app.resolve(event, context)
