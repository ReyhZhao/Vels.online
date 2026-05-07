import os

import boto3


class StorageClient:
    def __init__(self):
        self._bucket = os.environ.get("WASABI_BUCKET", "")
        self._s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("WASABI_ENDPOINT", ""),
            aws_access_key_id=os.environ.get("WASABI_ACCESS_KEY", ""),
            aws_secret_access_key=os.environ.get("WASABI_SECRET_KEY", ""),
        )

    def upload_file(self, file_obj, key):
        self._s3.upload_fileobj(file_obj, self._bucket, key)

    def generate_presigned_url(self, key, expiry_seconds=300):
        return self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expiry_seconds,
        )

    def generate_presigned_put_url(self, key, content_type, expiry_seconds=300):
        return self._s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expiry_seconds,
        )

    def head_object(self, key):
        return self._s3.head_object(Bucket=self._bucket, Key=key)

    def list_objects(self, prefix):
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            yield from page.get("Contents", [])

    def delete_file(self, key):
        self._s3.delete_object(Bucket=self._bucket, Key=key)
