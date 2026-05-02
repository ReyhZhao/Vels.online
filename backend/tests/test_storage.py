import io
from unittest.mock import MagicMock, patch

import pytest

from security.storage import StorageClient


@pytest.fixture
def mock_boto3_client():
    with patch("security.storage.boto3.client") as mock_client:
        mock_s3 = MagicMock()
        mock_client.return_value = mock_s3
        yield mock_s3


@pytest.fixture
def client(mock_boto3_client, monkeypatch):
    monkeypatch.setenv("WASABI_ENDPOINT", "https://s3.eu-west-1.wasabisys.com")
    monkeypatch.setenv("WASABI_BUCKET", "test-bucket")
    monkeypatch.setenv("WASABI_ACCESS_KEY", "test-access-key")
    monkeypatch.setenv("WASABI_SECRET_KEY", "test-secret-key")
    return StorageClient()


def test_generate_presigned_url_calls_s3_with_correct_params(client, mock_boto3_client):
    mock_boto3_client.generate_presigned_url.return_value = "https://presigned.url/file"

    url = client.generate_presigned_url("downloads/agent.exe")

    mock_boto3_client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "test-bucket", "Key": "downloads/agent.exe"},
        ExpiresIn=300,
    )
    assert url == "https://presigned.url/file"


def test_generate_presigned_url_respects_custom_expiry(client, mock_boto3_client):
    mock_boto3_client.generate_presigned_url.return_value = "https://presigned.url/file"

    client.generate_presigned_url("downloads/agent.exe", expiry_seconds=60)

    mock_boto3_client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "test-bucket", "Key": "downloads/agent.exe"},
        ExpiresIn=60,
    )


def test_upload_file_streams_to_correct_bucket_and_key(client, mock_boto3_client):
    file_obj = io.BytesIO(b"file contents")

    client.upload_file(file_obj, "downloads/sysmon.zip")

    mock_boto3_client.upload_fileobj.assert_called_once_with(
        file_obj, "test-bucket", "downloads/sysmon.zip"
    )


def test_boto3_client_initialised_with_credentials(monkeypatch):
    monkeypatch.setenv("WASABI_ENDPOINT", "https://s3.eu-west-1.wasabisys.com")
    monkeypatch.setenv("WASABI_BUCKET", "my-bucket")
    monkeypatch.setenv("WASABI_ACCESS_KEY", "AKIAIOSFODNN7EXAMPLE")
    monkeypatch.setenv("WASABI_SECRET_KEY", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")

    with patch("security.storage.boto3.client") as mock_client:
        mock_client.return_value = MagicMock()
        StorageClient()

        mock_client.assert_called_once_with(
            "s3",
            endpoint_url="https://s3.eu-west-1.wasabisys.com",
            aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
            aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )
