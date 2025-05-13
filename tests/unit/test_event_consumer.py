import base64
import json
import os
import unittest
from unittest.mock import patch, MagicMock

import boto3
from moto import mock_aws

# Set environment variables
os.environ['DYNAMODB_TABLE'] = 'football-events-test'
os.environ['MSK_TOPIC'] = 'football-events'

# Import the Lambda function
from lambdas.event_consumer import app

# Helper function to create a mock Lambda context
def create_mock_lambda_context():
    context = MagicMock()
    context.function_name = "test-function"
    context.memory_limit_in_mb = 128
    context.invoked_function_arn = "arn:aws:lambda:eu-central-1:123456789012:function:test-function"
    context.aws_request_id = "test-request-id"
    return context

# Sample Kafka event data
SAMPLE_KAFKA_EVENT = {
    "records": {
        "football-events-0": [
            {
                "topic": "football-events",
                "partition": 0,
                "offset": 0,
                "timestamp": 1630000000000,
                "timestampType": "CREATE_TIME",
                "value": base64.b64encode(json.dumps({
                    "match_id": "match-123",
                    "event_type": "goal",
                    "player_id": "player-456",
                    "team_id": "team-789",
                    "timestamp": "2023-08-15T14:30:00Z",
                    "details": {
                        "minute": 42,
                        "assist_player_id": "player-789"
                    }
                }).encode('utf-8')).decode('utf-8')
            },
            {
                "topic": "football-events",
                "partition": 0,
                "offset": 1,
                "timestamp": 1630000001000,
                "timestampType": "CREATE_TIME",
                "value": base64.b64encode(json.dumps({
                    "match_id": "match-123",
                    "event_type": "card",
                    "player_id": "player-456",
                    "team_id": "team-789",
                    "timestamp": "2023-08-15T14:35:00Z",
                    "details": {
                        "minute": 47,
                        "card_type": "yellow"
                    }
                }).encode('utf-8')).decode('utf-8')
            }
        ]
    }
}

# Sample event for January (different season calculation)
SAMPLE_JANUARY_EVENT = {
    "records": {
        "football-events-0": [
            {
                "topic": "football-events",
                "partition": 0,
                "offset": 0,
                "timestamp": 1630000000000,
                "timestampType": "CREATE_TIME",
                "value": base64.b64encode(json.dumps({
                    "match_id": "match-123",
                    "event_type": "goal",
                    "player_id": "player-456",
                    "team_id": "team-789",
                    "timestamp": "2023-01-15T14:30:00Z",
                    "details": {
                        "minute": 42,
                        "assist_player_id": "player-789"
                    }
                }).encode('utf-8')).decode('utf-8')
            }
        ]
    }
}

# Test class for the event consumer Lambda
@mock_aws
class TestEventConsumer(unittest.TestCase):

    def setUp(self):
        """Set up test environment"""
        # Create the mock DynamoDB table
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.create_table(
            TableName='football-events-test',
            KeySchema=[
                {'AttributeName': 'match_id', 'KeyType': 'HASH'},
                {'AttributeName': 'event_timestamp', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'match_id', 'AttributeType': 'S'},
                {'AttributeName': 'event_timestamp', 'AttributeType': 'S'},
                {'AttributeName': 'event_type_timestamp', 'AttributeType': 'S'}
            ],
            LocalSecondaryIndexes=[
                {
                    'IndexName': 'EventTypeIndex',
                    'KeySchema': [
                        {'AttributeName': 'match_id', 'KeyType': 'HASH'},
                        {'AttributeName': 'event_type_timestamp', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'}
                }
            ],
            BillingMode='PAY_PER_REQUEST'
        )

        # Reset the table reference in the app
        app.table = None



    def tearDown(self):
        """Clean up after tests"""
        # Delete the table
        self.table.delete()

        # Remove environment variables
        os.environ.pop('DYNAMODB_TABLE', None)
        os.environ.pop('MSK_TOPIC', None)



    def test_derive_season(self):
        """Test the derive_season function"""
        # Test August (start of season)
        self.assertEqual(app.derive_season("2023-08-15T14:30:00Z"), "2023/2024")

        # Test January (middle of season)
        self.assertEqual(app.derive_season("2023-01-15T14:30:00Z"), "2022/2023")

        # Test July (end of season)
        self.assertEqual(app.derive_season("2023-07-31T23:59:59Z"), "2022/2023")

        # Test August 1st (start of new season)
        self.assertEqual(app.derive_season("2023-08-01T00:00:00Z"), "2023/2024")

    def test_process_record(self):
        """Test the process_record function"""
        # Create a sample record
        record = {
            "value": base64.b64encode(json.dumps({
                "match_id": "match-123",
                "event_type": "goal",
                "player_id": "player-456",
                "team_id": "team-789",
                "timestamp": "2023-08-15T14:30:00Z"
            }).encode('utf-8')).decode('utf-8')
        }

        # Process the record
        result = app.process_record(record)

        # Verify the result
        self.assertEqual(result["match_id"], "match-123")
        self.assertEqual(result["event_type"], "goal")
        self.assertEqual(result["season"], "2023/2024")
        self.assertEqual(result["event_timestamp"], "2023-08-15T14:30:00Z")
        self.assertEqual(result["event_type_timestamp"], "goal#2023-08-15T14:30:00Z")

    def test_lambda_handler_success(self):
        """Test the lambda_handler function with successful processing"""
        # Create a mock context
        context = create_mock_lambda_context()

        # Call the lambda handler
        response = app.lambda_handler(SAMPLE_KAFKA_EVENT, context)

        # Verify the response
        self.assertEqual(response["statusCode"], 200)
        self.assertIn("2 records processed successfully", response["body"])

        # Verify data was written to DynamoDB
        items = list(self.table.scan()["Items"])
        self.assertEqual(len(items), 2)

        # Verify the first item
        goal_event = next(item for item in items if item["event_type"] == "goal")
        self.assertEqual(goal_event["match_id"], "match-123")
        self.assertEqual(goal_event["season"], "2023/2024")
        self.assertEqual(goal_event["event_type_timestamp"], "goal#2023-08-15T14:30:00Z")

        # Verify the second item
        card_event = next(item for item in items if item["event_type"] == "card")
        self.assertEqual(card_event["match_id"], "match-123")
        self.assertEqual(card_event["season"], "2023/2024")
        self.assertEqual(card_event["event_type_timestamp"], "card#2023-08-15T14:35:00Z")

    def test_lambda_handler_january_event(self):
        """Test the lambda_handler function with January event (different season)"""
        # Create a mock context
        context = create_mock_lambda_context()

        # Call the lambda handler
        response = app.lambda_handler(SAMPLE_JANUARY_EVENT, context)

        # Verify the response
        self.assertEqual(response["statusCode"], 200)
        self.assertIn("1 records processed successfully", response["body"])

        # Verify data was written to DynamoDB
        items = list(self.table.scan()["Items"])
        self.assertEqual(len(items), 1)

        # Verify the season calculation
        self.assertEqual(items[0]["season"], "2022/2023")

    @patch('lambdas.event_consumer.app.process_record')
    def test_lambda_handler_with_processing_error(self, mock_process_record):
        """Test the lambda_handler function with processing errors"""
        # Make process_record return None to simulate an error
        mock_process_record.return_value = None

        # Create a mock context
        lambda_context = create_mock_lambda_context()

        # Call the lambda handler and expect an exception
        with self.assertRaises(Exception) as context:
            app.lambda_handler(SAMPLE_KAFKA_EVENT, lambda_context)

        # Verify the exception message
        self.assertIn("Processed 0 out of 2 records successfully", str(context.exception))

        # Verify no data was written to DynamoDB
        items = list(self.table.scan()["Items"])
        self.assertEqual(len(items), 0)

if __name__ == '__main__':
    unittest.main()
