import requests
import json
import time
import uuid
import boto3
import sys
import logging
from typing import Tuple
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Constants
STACK_NAME = "FootballDataApiStack"
MAX_WAIT_TIME = 120  # seconds
INITIAL_BACKOFF = 2  # seconds
MAX_BACKOFF = 10     # seconds
REGION =  os.getenv("CDK_DEFAULT_REGION")

if REGION is None:
    logger.error("CDK_DEFAULT_REGION is not set. Please set it to the region where the stack is deployed.")
    sys.exit(1)

class CloudFormationHelper:
    @staticmethod
    def get_api_endpoint(stack_name: str) -> str:
        """Retrieve API endpoint from CloudFormation stack outputs."""
        logger.info(f"Fetching API endpoint from stack: {stack_name}")
        try:
            session = boto3.Session()
            cf = session.client("cloudformation", region_name=REGION)
            response = cf.describe_stacks(StackName=stack_name)
            outputs = response["Stacks"][0]["Outputs"]

            for output in outputs:
                if output["OutputKey"] == "ApiEndpoint":
                    endpoint = output["OutputValue"]
                    logger.info(f"API endpoint: {endpoint}")
                    return endpoint

            logger.error("ApiEndpoint not found in stack outputs.")
            sys.exit(1)

        except Exception as e:
            logger.error(f"Error retrieving API endpoint: {str(e)}")
            sys.exit(1)

class FootballApiTester:
    def __init__(self, api_endpoint: str):
        self.api_endpoint = api_endpoint

    def send_event(self, match_id: str, event_type: str, player_id: str, team_id: str, timestamp: str) -> bool:
        """Send a single football event to the producer API."""
        payload = {
            "match_id": match_id,
            "event_type": event_type,
            "player_id": player_id,
            "team_id": team_id,
            "timestamp": timestamp
        }
        url = f"{self.api_endpoint}/events"
        logger.info(f"Sending {event_type} event at {timestamp}")
        response = requests.post(url, json=payload)

        if response.ok:
            logger.info(f"✅ Event sent successfully: {response.json().get('event_id')}")
            return True
        else:
            logger.error(f"❌ Failed to send event: {response.status_code}")
            logger.error(json.dumps(response.json(), indent=2))
            return False

    def test_producer(self) -> Tuple[bool, str]:
        """Test event production by sending multiple events."""
        logger.info("\n=== Testing Producer API ===")
        match_id = f"test-match-{uuid.uuid4().hex[:8]}"
        logger.info(f"Generated match ID: {match_id}")

        events = [
            {"event_type": "goal", "player_id": "player123", "team_id": "team_a", "timestamp": "2023-06-15T14:30:00Z"},
            {"event_type": "goal", "player_id": "player456", "team_id": "team_b", "timestamp": "2023-06-15T14:15:00Z"},
            {"event_type": "pass", "player_id": "player789", "team_id": "team_a", "timestamp": "2023-06-15T14:25:00Z"},
            {"event_type": "goal", "player_id": "player123", "team_id": "team_a", "timestamp": "2023-06-15T14:45:00Z"},
        ]

        all_success = True
        for event in events:
            success = self.send_event(
                match_id=match_id,
                event_type=event["event_type"],
                player_id=event["player_id"],
                team_id=event["team_id"],
                timestamp=event["timestamp"]
            )
            all_success = all_success and success

        return all_success, match_id

    def poll_for_events(self, match_id: str) -> bool:
        """Wait until the events for a match are available via query API."""
        logger.info("Polling for events...")

        start = time.time()
        backoff = INITIAL_BACKOFF

        while (elapsed := time.time() - start) < MAX_WAIT_TIME:
            url = f"{self.api_endpoint}/matches/{match_id}"
            try:
                response = requests.get(url)
                if response.ok and response.json().get("event_count", 0) > 0:
                    logger.info(f"✅ Found events after {int(elapsed)} seconds")
                    return True
            except Exception as e:
                logger.warning(f"Polling error: {str(e)}")

            logger.info(f"Waiting {backoff}s... (Elapsed: {int(elapsed)}s)")
            time.sleep(backoff)
            backoff = min(backoff * 1.5, MAX_BACKOFF)

        logger.error("❌ Timed out waiting for events.")
        return False

    def query_api(self, match_id: str, endpoint_suffix: str, label: str, table_headers: list, table_keys: list):
        """Query specific API endpoint and display data in table format."""
        url = f"{self.api_endpoint}/matches/{match_id}{endpoint_suffix}"
        logger.info(f"\n--- {label} ---\nCalling {url}")
        response = requests.get(url)

        logger.info(f"Status code: {response.status_code}")
        if response.ok:
            data = response.json()
            items = data.get(label.lower(), []) or data.get('events', [])
            logger.info(f"Found {len(items)} {label.lower()}")

            if items:
                header = "  ".join([f"{h:<20}" for h in table_headers])
                logger.info(header)
                logger.info("-" * len(header))
                for item in items:
                    row = "  ".join([f"{item.get(k, 'N/A'):<20}" for k in table_keys])
                    logger.info(row)
        else:
            logger.error(json.dumps(response.json(), indent=2))

    def test_queries(self, match_id: str):
        """Run all query tests."""
        logger.info("\n=== Testing Query APIs ===")
        if self.poll_for_events(match_id):
            self.query_api(match_id, "", "Events", ["EVENT TYPE", "TIMESTAMP", "PLAYER"], ["event_type", "timestamp", "player_id"])
            self.query_api(match_id, "/goals", "Goals", ["TIMESTAMP", "PLAYER", "TEAM"], ["timestamp", "player_id", "team_id"])
            self.query_api(match_id, "/passes", "Passes", ["TIMESTAMP", "PLAYER", "TEAM"], ["timestamp", "player_id", "team_id"])

def main():
    api_endpoint = CloudFormationHelper.get_api_endpoint(STACK_NAME)
    tester = FootballApiTester(api_endpoint)

    success, match_id = tester.test_producer()
    if success:
        tester.test_queries(match_id)
    else:
        logger.error("❌ Producer test failed. Skipping query tests.")

if __name__ == "__main__":
    main()
