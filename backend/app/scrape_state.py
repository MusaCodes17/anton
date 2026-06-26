"""
In-memory state + pub/sub for the background scrape job's SSE stream.

Transient by design (per the feature spec) — resets on server restart, which
is fine since it only describes "what's happening with the current/last
scrape run," not anything that needs to survive a restart.
"""
import asyncio
from datetime import datetime
from typing import List, Optional


class ScrapeStateManager:
    def __init__(self):
        self.is_running: bool = False
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        # Full ordered event log for the current/last job. New SSE
        # subscribers get this replayed (see subscribe()) before any live
        # events, so connecting slightly late — or after the job already
        # finished — never misses anything or hangs forever.
        self.history: List[dict] = []
        self._subscribers: List[asyncio.Queue] = []

    def start(self) -> None:
        self.is_running = True
        self.started_at = datetime.utcnow().isoformat()
        self.completed_at = None
        self.history = []

    def finish(self, completed_at: Optional[str] = None) -> None:
        self.is_running = False
        self.completed_at = completed_at or datetime.utcnow().isoformat()

    def subscribe(self) -> asyncio.Queue:
        """
        Synchronous on purpose (no `await` in this method body) — that makes
        the "copy current history into the new queue, then register it" pair
        atomic with respect to publish() (which is async and can only ever
        run between awaits), so a publish can never land in the gap between
        the copy and the registration and get lost or double-delivered.
        """
        q: asyncio.Queue = asyncio.Queue()
        for event in self.history:
            q.put_nowait(event)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def publish(self, event: dict) -> None:
        self.history.append(event)
        for q in list(self._subscribers):
            await q.put(event)


# Single shared instance — this module is the one source of truth for
# "what's the current scrape job doing," imported by the scrape runner (which
# writes to it) and the /api/scrape/stream endpoint (which reads it).
scrape_state = ScrapeStateManager()
