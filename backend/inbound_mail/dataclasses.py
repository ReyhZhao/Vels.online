from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NormalisedMessage:
    from_address: str
    to_address: str
    reply_to: Optional[str]
    subject: str
    body_text: str
    body_html: str
    attachments: list = field(default_factory=list)
