
import pytest
import boto3
from botocore.exceptions import ClientError
import io
import os
from uuid import uuid4
import logging

from app.core import storage
from app.core.config import settings

# pytestを非同期で実行するためのマーク
pytestmark = pytest.mark.asyncio

# 環境変数が設定されていない場合、このモジュールのテストをスキップする
# CI/CD環境やローカルで意図的に実行する場合にのみ `RUN_S3_INTEGRATION_TESTS=true` を設定
skip_if_not_configured = pytest.mark.skipif(
    os.getenv("RUN_S3_INTEGRATION_TESTS") != "true",
    reason="S3 integration tests are disabled. Set RUN_S3_INTEGRATION_TESTS=true to run them."
)

logger = logging.getLogger(__name__)

@pytest.fixture(scope="module")
def s3_integration_client():
    """実際のAWS S3に接続するboto3クライアントを提供するフィクスチャ"""
    secret_key = settings.S3_SECRET_KEY.get_secret_value() if settings.S3_SECRET_KEY else None
    
    if not all([settings.S3_ACCESS_KEY, secret_key, settings.S3_REGION, settings.S3_BUCKET_NAME]):
        pytest.fail("S3 integration test requires S3_ACCESS_KEY, S3_SECRET_KEY, S3_REGION, and S3_BUCKET_NAME.")

    client = boto3.client(
        "s3",
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=secret_key,
        region_name=settings.S3_REGION
    )
    return client

@skip_if_not_configured
@pytest.mark.asyncio
async def test_s3_integration_upload_and_delete(s3_integration_client):
    """
    実際のS3バケットに対して、ファイルのアップロード、存在確認、削除をテストする。
    """
    # 1. Setup
    file_content = b"This is a test file for S3 integration."
    file_like_object = io.BytesIO(file_content)
    # テスト実行ごとにユニークなオブジェクト名を使う
    object_name = f"integration-tests/{uuid4()}.txt"
    bucket_name = settings.S3_BUCKET_NAME
    
    uploaded_url = None
    
    try:
        # 2. Execute upload
        logger.info(f"Uploading {object_name} to bucket {bucket_name}...")
        uploaded_url = await storage.upload_file(
            file=file_like_object,
            object_name=object_name,
        )
        logger.info(f"Upload returned URL: {uploaded_url}")

        # 3. Assert upload result
        assert uploaded_url is not None
        assert uploaded_url == f"s3://{bucket_name}/{object_name}"

        # 4. Verify object existence in S3
        logger.info(f"Verifying object {object_name} in bucket {bucket_name}...")
        response = s3_integration_client.get_object(Bucket=bucket_name, Key=object_name)
        data = response["Body"].read()
        assert data == file_content
        logger.info("Object verification successful.")

        # 5. Execute presigned URL generation
        logger.info(f"Generating presigned URL for {object_name}...")
        presigned_url = await storage.create_presigned_url(object_name=object_name)
        logger.info(f"Generated presigned URL: {presigned_url}")
        
        # 6. Assert presigned URL result
        assert presigned_url is not None
        assert isinstance(presigned_url, str)
        assert f"https://{bucket_name}.s3" in presigned_url
        assert f"amazonaws.com/{object_name}" in presigned_url
        assert "X-Amz-Signature=" in presigned_url

    finally:
        # 7. Cleanup: Delete the object from S3 if it was created
        if uploaded_url:
            logger.info(f"Cleaning up: deleting object {object_name} from bucket {bucket_name}...")
            try:
                s3_integration_client.delete_object(Bucket=bucket_name, Key=object_name)
                logger.info("Cleanup successful.")
            except ClientError as e:
                logger.error(f"Failed to delete object {object_name} during cleanup: {e}")
                # We don't re-raise here to not obscure the original test failure
