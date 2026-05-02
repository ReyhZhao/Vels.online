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
