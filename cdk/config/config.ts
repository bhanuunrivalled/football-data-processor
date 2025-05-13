/**
 * Configuration for different environments
 */

export interface EnvironmentConfig {
  // VPC Configuration
  vpc: {
    maxAzs: number;
  };

  // MSK Configuration
  msk: {
    kafkaTopic: string;
  };

  // Producer Configuration
  producer: {
    lambdaMemorySize: number;
    lambdaTimeout: number;
  };

  // Consumer Configuration
  consumer: {
    lambdaMemorySize: number;
    lambdaTimeout: number;
    batchSize: number;
    maxBatchingWindow: number; // in seconds
  };

  // DynamoDB Configuration
  dynamodb: {
    billingMode: string;
    pointInTimeRecovery: boolean;
  };
}

// Development environment configuration
export const devConfig: EnvironmentConfig = {
  vpc: {
    maxAzs: 2
  },
  msk: {
    kafkaTopic: 'football-events'
  },
  producer: {
    lambdaMemorySize: 256,
    lambdaTimeout: 30
  },
  consumer: {
    lambdaMemorySize: 256,
    lambdaTimeout: 300,
    batchSize: 30,
    maxBatchingWindow: 5
  },
  dynamodb: {
    billingMode: 'PAY_PER_REQUEST',
    pointInTimeRecovery: true
  }
};

// Production environment configuration
export const prodConfig: EnvironmentConfig = {
  vpc: {
    maxAzs: 3
  },
  msk: {
    kafkaTopic: 'football-events'
  },
  producer: {
    lambdaMemorySize: 512,
    lambdaTimeout: 60
  },
  consumer: {
    lambdaMemorySize: 512,
    lambdaTimeout: 300,
    batchSize: 25,
    maxBatchingWindow: 30
  },
  dynamodb: {
    billingMode: 'PROVISIONED',
    pointInTimeRecovery: true
  }
};

// Get configuration based on environment
export function getConfig(environment: string): EnvironmentConfig {
  switch (environment.toLowerCase()) {
    case 'prod':
    case 'production':
      return prodConfig;
    case 'dev':
    case 'development':
    default:
      return devConfig;
  }
}
