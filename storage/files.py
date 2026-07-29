import uuid
import boto3
from botocore.config import Config
from core.config import settings


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
    )


def upload_bytes(data: bytes, filename: str, content_type: str = "application/octet-stream") -> str:
    """Upload raw bytes to S3/R2. Returns the S3 key."""
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    key = f"uploads/{uuid.uuid4().hex}.{ext}"
    _client().put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return key


def public_url(key: str) -> str:
    base = settings.s3_public_url.rstrip("/")
    return f"{base}/{key}"
