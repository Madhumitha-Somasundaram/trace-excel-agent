"""
Script to create the users DynamoDB table.

Run this script once to set up the users table:
    python scripts/create_users_table.py
"""
import boto3
from botocore.exceptions import ClientError


def create_users_table():
    """Create DynamoDB table for users"""

    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

    try:
        table = dynamodb.create_table(
            TableName='users',
            KeySchema=[
                {
                    'AttributeName': 'username',
                    'KeyType': 'HASH'  # Partition key (username is user_id)
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'username',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'email',
                    'AttributeType': 'S'
                }
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'email-index',
                    'KeySchema': [
                        {
                            'AttributeName': 'email',
                            'KeyType': 'HASH'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    },
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )

        # Wait for the table to be created
        print("Creating users table...")
        table.wait_until_exists()

        print("✅ Users table created successfully!")
        print(f"Table status: {table.table_status}")

    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            print("⚠️  Table already exists")
        else:
            print(f"❌ Error creating table: {e}")
            raise


if __name__ == "__main__":
    create_users_table()
