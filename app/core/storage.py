import boto3
from botocore.exceptions import ClientError
import logging
from typing import BinaryIO

from app.core.config import settings

logger = logging.getLogger(__name__)

async def upload_file(file: BinaryIO, object_name: str) -> str | None:
    """
    Upload a file to an S3 bucket.

    :param file: File-like object to upload.
    :param object_name: S3 object name.
    :return: S3 URL of the uploaded file, or None if upload fails.
    """
    # S3シークレットキーの取得
    secret_key = None
    if settings.S3_SECRET_KEY:
        secret_key = settings.S3_SECRET_KEY.get_secret_value()

    s3_client = boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=secret_key,
        region_name=settings.S3_REGION
    )
    try:
        # PDFファイルとして正しく認識されるよう、Content-Typeを明示的に設定
        s3_client.upload_fileobj(
            file,
            settings.S3_BUCKET_NAME,
            object_name,
            ExtraArgs={
                'ContentType': 'application/pdf',
                'ContentDisposition': 'inline'
            }
        )
        s3_url = f"s3://{settings.S3_BUCKET_NAME}/{object_name}"
        logger.info(f"File {object_name} uploaded to {s3_url}")
        return s3_url
    except ClientError as e:
        logger.error(f"Failed to upload {object_name} to S3: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during S3 upload: {e}")
        return None

async def create_presigned_url(object_name: str, expiration: int = 3600, inline: bool = True) -> str | None:
    """
    Generate a presigned URL to share an S3 object.

    :param object_name: string
    :param expiration: Time in seconds for the presigned URL to remain valid.
    :param inline: If True, sets Content-Disposition to 'inline' for browser preview. If False, uses 'attachment' for download.
    :return: Presigned URL as string. If error, returns None.
    """
    # S3シークレットキーの取得
    secret_key = None
    if settings.S3_SECRET_KEY:
        secret_key = settings.S3_SECRET_KEY.get_secret_value()

    s3_client = boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=secret_key,
        region_name=settings.S3_REGION,
        config=boto3.session.Config(signature_version='s3v4')
    )
    try:
        params = {
            'Bucket': settings.S3_BUCKET_NAME,
            'Key': object_name
        }

        # Content-Dispositionを設定（ブラウザでプレビュー表示するか、ダウンロードするか）
        if inline:
            params['ResponseContentDisposition'] = 'inline'
        else:
            # ファイル名を抽出してダウンロード時に使用
            filename = object_name.split('/')[-1]
            params['ResponseContentDisposition'] = f'attachment; filename="{filename}"'

        response = s3_client.generate_presigned_url(
            'get_object',
            Params=params,
            ExpiresIn=expiration
        )
        return response
    except ClientError as e:
        logger.error(f"Failed to generate presigned URL for {object_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during presigned URL generation: {e}")
        return None
