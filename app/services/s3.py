from functools import lru_cache
from uuid import uuid4

import boto3

from app.config import get_settings


@lru_cache
def get_s3_client():
    settings = get_settings()
    client_kwargs = {
        "service_name": "s3",
        "region_name": settings.aws_region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
    }
    if settings.aws_session_token is not None:
        client_kwargs["aws_session_token"] = settings.aws_session_token
    if settings.aws_s3_endpoint_url:
        client_kwargs["endpoint_url"] = settings.aws_s3_endpoint_url

    return boto3.client(**client_kwargs)


def create_presigned_upload_url(
    *,
    file_key: str,
    content_type: str,
) -> str:
    settings = get_settings()
    return get_s3_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_bucket_name,
            "Key": file_key,
            "ContentType": content_type,
        },
        ExpiresIn=settings.s3_upload_url_expires_sec,
    )


def uses_local_multipart_backend() -> bool:
    return get_settings().s3_multipart_backend == "local"


def create_multipart_upload(*, object_key: str, content_type: str) -> str:
    settings = get_settings()
    if uses_local_multipart_backend():
        return f"local-{uuid4()}"

    response = get_s3_client().create_multipart_upload(
        Bucket=settings.s3_bucket_name,
        Key=object_key,
        ContentType=content_type,
        ChecksumAlgorithm="CRC32C",
    )
    return response["UploadId"]


def create_presigned_part_url(
    *,
    object_key: str,
    s3_upload_id: str,
    part_number: int,
    checksum_crc32c: str,
    upload_id: str,
) -> str:
    settings = get_settings()
    if uses_local_multipart_backend():
        base_url = settings.public_base_url.rstrip("/")
        return f"{base_url}/v1/local-s3/raw-uploads/{upload_id}/parts/{part_number}"

    return get_s3_client().generate_presigned_url(
        "upload_part",
        Params={
            "Bucket": settings.s3_bucket_name,
            "Key": object_key,
            "UploadId": s3_upload_id,
            "PartNumber": part_number,
            "ChecksumCRC32C": checksum_crc32c,
        },
        ExpiresIn=settings.s3_upload_url_expires_sec,
    )


def list_uploaded_parts(*, object_key: str, s3_upload_id: str) -> list[dict]:
    settings = get_settings()
    if uses_local_multipart_backend():
        return []

    response = get_s3_client().list_parts(
        Bucket=settings.s3_bucket_name,
        Key=object_key,
        UploadId=s3_upload_id,
    )
    return [
        {
            "partNumber": part["PartNumber"],
            "etag": part["ETag"],
            "checksumCrc32c": part.get("ChecksumCRC32C", ""),
            "sizeBytes": part["Size"],
        }
        for part in response.get("Parts", [])
    ]


def complete_multipart_upload(
    *,
    object_key: str,
    s3_upload_id: str,
    parts: list[dict],
) -> None:
    settings = get_settings()
    if uses_local_multipart_backend():
        return

    get_s3_client().complete_multipart_upload(
        Bucket=settings.s3_bucket_name,
        Key=object_key,
        UploadId=s3_upload_id,
        MultipartUpload={
            "Parts": [
                {
                    "PartNumber": part["partNumber"],
                    "ETag": part["etag"],
                    "ChecksumCRC32C": part["checksumCrc32c"],
                }
                for part in parts
            ]
        },
    )


def abort_multipart_upload(*, object_key: str, s3_upload_id: str) -> None:
    settings = get_settings()
    if uses_local_multipart_backend():
        return

    get_s3_client().abort_multipart_upload(
        Bucket=settings.s3_bucket_name,
        Key=object_key,
        UploadId=s3_upload_id,
    )
