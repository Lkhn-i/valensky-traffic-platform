from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .models import NotificationJob
    from .templates import RenderedNotification


@dataclass(frozen=True, slots=True)
class ProviderDispatchReceipt:
    provider_message_id: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


class NotificationDispatchError(Exception):
    """Base notification dispatch failure."""


class RetryableNotificationError(NotificationDispatchError):
    """A dispatch failure that can be retried later."""


class PermanentNotificationError(NotificationDispatchError):
    """A dispatch failure that should be sent to dead letter immediately."""


class NotificationProvider(Protocol):
    channel: str

    def send(
        self,
        *,
        job: NotificationJob,
        message: RenderedNotification,
    ) -> ProviderDispatchReceipt: ...


class NotificationProviderRegistry:
    def __init__(self, providers: Iterable[NotificationProvider] | None = None) -> None:
        self._providers = {provider.channel: provider for provider in providers or []}

    def resolve(self, channel: str) -> NotificationProvider:
        provider = self._providers.get(channel)
        if provider is None:
            raise PermanentNotificationError(
                f"No notification provider configured for channel {channel!r}."
            )
        return provider


class StubNotificationProvider:
    """In-memory provider for tests and local dispatch wiring."""

    def __init__(
        self,
        *,
        channel: str,
        outcomes: Iterable[ProviderDispatchReceipt | Exception | None] | None = None,
    ) -> None:
        self.channel = channel
        self._outcomes = deque(outcomes or [])
        self.deliveries: list[tuple[int, str]] = []

    def send(
        self,
        *,
        job: NotificationJob,
        message: RenderedNotification,
    ) -> ProviderDispatchReceipt:
        self.deliveries.append((job.id, message.template_key))
        if self._outcomes:
            outcome = self._outcomes.popleft()
            if isinstance(outcome, Exception):
                raise outcome
            if outcome is not None:
                return outcome
        return ProviderDispatchReceipt(
            provider_message_id=f"stub:{self.channel}:{job.id}",
            metadata={"template_key": message.template_key},
        )
