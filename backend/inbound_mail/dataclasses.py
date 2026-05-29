from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NormalisedAttachment:
    filename: str
    content_type: str
    payload: bytes


@dataclass
class NormalisedMessage:
    from_address: str
    to_address: str
    reply_to: Optional[str]
    subject: str
    body_text: str
    body_html: str
    raw_bytes: bytes = field(default=b"")
    attachments: list = field(default_factory=list)
