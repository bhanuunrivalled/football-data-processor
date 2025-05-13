# Football Match Data Processor

A serverless application that processes and analyzes football match data in real-time using AWS services.

## Architecture

This application uses a serverless architecture with the following components:

- **API Gateway**: Exposes REST APIs for data ingestion and querying
- **Lambda Functions**: Process and query match event data
- **Amazon MSK (Kafka)**: Streams match events in real-time
- **DynamoDB**: Stores processed match event data
- **AWS CDK**: Defines the infrastructure as code

## Architecture Diagram

https://github.com/aws-samples/apigateway-lambda-msk-serverless-integration I followed this architecture Exactly

- The only difference is the consumer lambda uses a Dynamo DB
- Imp **FIXME** is the producer lambda that creates the topic also but this can be easily added to the topic handler using cloudformation custom resource

```plaintext
Client → API Gateway → Lambda (Producer) → Kafka (MSK) → Lambda Consumer → DynamoDB → Query Lambda → API Gateway
```

## Features

- Ingest live football match events (goals, passes, fouls, etc.)
- Process and enrich events in real-time
- Store events in DynamoDB with efficient querying capabilities
- Query match statistics through REST APIs
- Chronological ordering of events within each event type

## API Endpoints

### Producer API

- **POST /events**: Submit a new match event

Example payload:
```json
{
  "match_id": "match123",
  "event_type": "goal",
  "player_id": "player456",
  "team_id": "team789",
  "timestamp": "2023-06-15T14:30:00Z"
}
```

### Query API

- **GET /matches/{match_id}**: Get all events for a specific match in chronological order
- **GET /matches/{match_id}/goals**: Get all goals for a specific match in chronological order
- **GET /matches/{match_id}/passes**: Get all passes for a specific match in chronological order

## Lambda Functions

1. **Event Ingest (event_ingest)**
   - Validates the incoming event
   - Publishes the event to Amazon MSK (Kafka) using the match_id as the partition key
   - **Also creates the topic a better approach is to USE CDK custom resource to create the topic**

2. **Event Consumer (event_consumer)**
   - Consumes events from Kafka
   - Creates a composite sort key for efficient querying
   - Writes the event to DynamoDB

3. **Query Handler (query_handler)**
   - Provides an API to query DynamoDB for match events and statistics
   - Returns events in chronological order

## DynamoDB Design

| Partition Key | Sort Key         | LSI Sort Key           | Additional Attributes |
|--------------|------------------|------------------------|----------------------|
| match_id      | event_timestamp  | event_type_timestamp   | event_type, player_id, team_id |

- **Primary Key**: (match_id, event_timestamp)
  - Allows efficient retrieval of all events for a match in chronological order

- **Local Secondary Index**: (match_id, event_type_timestamp)
  - Composite key format: `event_type#event_timestamp`
  - Allows efficient retrieval of specific event types (e.g., goals) in chronological order

## Deployment

Ensure that you have appropriate [AWS credentials](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html) for interacting with resources in your AWS account

### Prerequisites

- AWS Account
- Node.js 18+
- AWS CDK CLI 2.x
- Python 3.9+
- DOCKER or PODMAN

### Steps

1. Clone the repository
2. Install dependencies:
   ```bash
   cd cdk
   npm install
   ```

3. Configure environment variables

    ```bash
    # For default region deployment
    export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query 'Account' --output text)
    export CDK_DEFAULT_REGION=$(aws configure get region)
    ```

4. Deploy the stacks:
   ```bash
   npm run bootstrap
   npm run build
   npm run synth
   npm run deploy:all
   ```

### Deploying to a Different Region

To deploy the application to a different AWS region:

1. Set the environment variables for the target region:
   ```bash
   export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query 'Account' --output text)
   export CDK_DEFAULT_REGION=eu-west-2  # Replace with your target region
   export AWS_REGION=eu-west-2          # Important: This overrides the profile's default region
   export CDK_DOCKER=podman             # If using Podman instead of Docker
   ```

2. Bootstrap the CDK environment in the new region:
   ```bash
   npm run bootstrap
   ```

3. Deploy the stacks to the new region:
   ```bash
   npm run build
   npm run synth
   npm run deploy:all
   ```

4. After deployment, the API Gateway endpoint will be available in the new region. You can get the endpoint URL from the CloudFormation stack outputs.

## Testing

### Using the Python Test Script

install the required dependencies:


Create a python virtual environment
Go to the root directory of the project
```
python3 -m venv .venv
```

After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
source .venv/bin/activate
```

Install test requirements

```
pip3 install -r requirements-dev.txt
```


```bash
python test_api.py
```

This script helps like an end-to-end integration test:
1. Send multiple test events to the producer API
2. Wait for the events to be processed
3. Query the events using the query API
4. Verify that events are returned in the correct order
5. ***NOTE,*** As the producer is creating the topic the first time, it will take a bit longer to process the events
6. This can be fixed by having a handler for the topic creation in the CDK stack
7. We can set up a provisioned concurrency for the producer and consumer lambdas to reduce the cold start time

### Using Postman

Import the provided Postman collection please change the api end point url:
```
football-data-processor.postman_collection.json
```

## Project Structure

```
football-data-processor/
├── cdk/                   # CDK infrastructure code
│   ├── bin/               # CDK app entry point
│   ├── lib/               # CDK stack definitions
│   └── config/            # Environment-specific configuration
├── lambdas/               # Lambda function code
│   ├── event_ingest/      # Producer Lambda
│   ├── event_consumer/    # Consumer Lambda
│   └── query_handler/     # Query Lambda
├── scripts/               # Utility scripts
├── test_api.py            # End-to-end test script
└── README.md              # This file
```

## API Endpoint

API Endpoint: Get the API Gateway URL from the CDK output after deployment check [test_api.py](test_api.py)

Example curl command:
```bash
curl -X POST https://ueeun1qp59.execute-api.eu-central-1.amazonaws.com/prod/events -H "Content-Type: application/json" -d '{"match_id": "match123", "event_type": "goal", "player_id": "player456", "team_id": "team789", "timestamp": "2023-06-15T14:30:00Z"}'
```

## NICE TO IMPLEMENT

- Monitoring
- Use CloudWatch to monitor the lag of the Kafka consumer
- Set up CloudWatch Alarms to notify when lag exceeds a certain threshold
- Error Destination for Kafka Consumer
- Producer and consumer can be a websocket API
- CDK tests
- Unit tests for Lambda for prodcuer lambda
- use pydantic for event validation
- Load Testing
