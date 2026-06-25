"""Shared DRF renderers.

The SSE endpoints (incident presence/assistant roster streams, the attack-map
tail) return a raw ``StreamingHttpResponse``, but DRF still runs content
negotiation in ``initial()`` against the view's ``renderer_classes`` *before*
the handler ever runs. A client that sends the semantically-correct
``Accept: text/event-stream`` (the incident presence roster stream does) is
otherwise rejected with ``406 Not Acceptable``
("Could not satisfy the request Accept header.") because the default renderers
only advertise ``application/json``.

Listing this passthrough renderer in a view's ``renderer_classes`` lets content
negotiation honour that Accept header. Keep ``JSONRenderer`` first in the list so
non-streaming responses on the same view (errors, the presence activity POST)
still serialise as JSON — for ``Accept: */*`` negotiation picks the first
renderer, while ``Accept: text/event-stream`` matches this one.
"""
from rest_framework.renderers import BaseRenderer


class ServerSentEventRenderer(BaseRenderer):
    """No-op renderer advertising ``text/event-stream`` for SSE views.

    Streaming views return a ``StreamingHttpResponse`` directly, so ``render`` is
    never actually invoked; this class exists purely so content negotiation will
    accept an ``Accept: text/event-stream`` request.
    """

    media_type = "text/event-stream"
    format = "event-stream"
    charset = None

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data
