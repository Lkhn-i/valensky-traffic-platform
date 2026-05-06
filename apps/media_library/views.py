from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from .services import (
    ConsumedPlaybackTicketError,
    ExpiredPlaybackTicketError,
    PlaybackService,
    PlaybackTicketNotFoundError,
)


@require_GET
def local_playback_stream(request: HttpRequest, ticket_id: int) -> JsonResponse:
    raw_token = request.headers.get("X-Playback-Token") or request.GET.get("token", "")
    if not raw_token:
        return JsonResponse(
            {"status": "locked", "reason": "playback_token_required"},
            status=401,
        )

    try:
        ticket = PlaybackService().get_valid_ticket(raw_token=raw_token)
    except ExpiredPlaybackTicketError:
        return JsonResponse(
            {"status": "token_expired", "reason": "playback_ticket_expired"},
            status=410,
        )
    except PlaybackTicketNotFoundError:
        return JsonResponse(
            {"status": "missing", "reason": "playback_ticket_missing"},
            status=404,
        )
    except ConsumedPlaybackTicketError:
        return JsonResponse(
            {"status": "failed", "reason": "playback_ticket_consumed"},
            status=409,
        )

    if ticket.id != ticket_id:
        return JsonResponse(
            {"status": "locked", "reason": "playback_ticket_mismatch"},
            status=403,
        )

    asset = ticket.attachment.media_asset
    return JsonResponse(
        {
            "status": "ready",
            "stream": "local_provider_placeholder",
            "ticket_id": ticket.id,
            "content_type": asset.mime_type or "video/mp4",
            "expires_at": ticket.expires_at.isoformat(),
        }
    )
