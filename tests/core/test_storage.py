
import pytest
import boto3
from moto import mock_aws
import io
from uuid import uuid4

# テスト対象のモジュール（まだ存在しない）
from app.core import storage
from app.core.config import settings

# pytestを非同期で実行するためのマーク
pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="function")
def aws_credentials():
    """Mock AWS Credentials for moto."""
    import os
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

@pytest.fixture(scope="function")
def s3_client(aws_credentials):
    """S3 client fixture wrapped in mock_aws context manager."""
    with mock_aws():
        conn = boto3.client("s3", region_name="us-east-1")
        yield conn

@pytest.fixture(scope="function")
def s3_bucket(s3_client):
    """Create a mock S3 bucket."""
    bucket_name = "test-bucket"
    settings.S3_BUCKET_NAME = bucket_name
    s3_client.create_bucket(Bucket=bucket_name)
    return bucket_name

@pytest.mark.asyncio
async def test_upload_file(s3_client, s3_bucket):
    """
    Test that upload_file function uploads a file to a mock S3 bucket
    and returns the correct S3 URL.
    """
    # 1. Setup
    file_content = b"Hello, S3!"
    file_like_object = io.BytesIO(file_content)
    object_name = f"test-folder/{uuid4()}.txt"

    # 2. Execute the function to be tested
    s3_url = await storage.upload_file(
        file=file_like_object,
        object_name=object_name,
    )

    # 3. Assert the result
    expected_url = f"s3://{s3_bucket}/{object_name}"
    assert s3_url == expected_url

    # 4. Verify the file was actually uploaded to the mock S3
    response = s3_client.get_object(Bucket=s3_bucket, Key=object_name)
    data = response["Body"].read()
    assert data == file_content

@pytest.mark.asyncio
async def test_create_presigned_url(s3_client, s3_bucket):
    """
    Test that create_presigned_url generates a valid presigned URL for a given object.
    """
    # 1. Setup: Upload a dummy file to the mock S3
    object_name = f"test-folder/{uuid4()}.txt"
    s3_client.put_object(Bucket=s3_bucket, Key=object_name, Body=b"dummy content")

    # 2. Execute the function to be tested
    presigned_url = await storage.create_presigned_url(object_name=object_name)

    # 3. Assert the result
    assert presigned_url is not None
    assert isinstance(presigned_url, str)
    assert f"https://{s3_bucket}.s3.amazonaws.com/{object_name}" in presigned_url
    # Check for Signature Version 4 parameters
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in presigned_url
    assert "X-Amz-Credential=" in presigned_url
    assert "X-Amz-Signature=" in presigned_url
    assert "X-Amz-Expires=" in presigned_url

