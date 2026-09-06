"""
Rate-limiting gate (Law 10 — Operational Boundaries).

Unlike InvariantMonitor, which evaluates after actions have already run (detection),
RateLimitGate evaluates BEFORE execution (prevention). It enforces sliding-window
frequency ceilings per adapter, action, or globally, stopping burst floods, runaway loops,
and resource exhaustion before any physical effect can occur.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from orrery.core.types import ActionPayload

logger = logging.getLogger(__name__)

RATELIMIT_POLICY = "LAW10-RATELIMIT"


class RateLimitRule(BaseModel):
    """
    Configuration for a single rate-limiting rule.
    Empty adapter or action fields act as wildcards.
    """

    name: str
    adapter: Optional[str] = None
    action: Optional[str] = None
    max_calls: int = Field(gt=0, description="Maximum permitted calls within the window.")
    window_seconds: float = Field(gt=0.0, description="Sliding window duration in seconds.")

    def matches(self, action_payload: ActionPayload) -> bool:
        if self.adapter and self.adapter != action_payload.target_adapter:
            return False
        if self.action and self.action != action_payload.action_name:
            return False
        return True


class RateLimitDecision(BaseModel):
    """
    Verdict returned by RateLimitGate.
    """

    allowed: bool
    policy_id: Optional[str] = None
    reason: Optional[str] = None
    rule_name: Optional[str] = None
    observed_count: int = 0
    limit: int = 0
    window_seconds: float = 0.0


class RateLimitGate:
    """
    Sliding-window rate limiter evaluated in the pre-dispatch gate ladder.
    Thread-safe and deterministic.
    """

    def __init__(
        self,
        rules: Optional[List[RateLimitRule]] = None,
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        self.rules = list(rules) if rules else []
        self._history: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def add_rule(self, rule: RateLimitRule) -> None:
        with self._lock:
            self.rules.append(rule)

    def reset(self) -> None:
        """Clears all call history (useful between test runs or cycles)."""
        with self._lock:
            self._history.clear()

    def evaluate(
        self, action: ActionPayload, now: Optional[float] = None
    ) -> RateLimitDecision:
        """
        Evaluates whether an action is within allowed rate limits.
        If all matching rules are within bounds, records the invocation and allows it.
        If any matching rule's threshold is met or exceeded, denies execution.
        """
        if not self.enabled or not self.rules:
            return RateLimitDecision(allowed=True)

        current_time = time.time() if now is None else now

        with self._lock:
            matching_rules = [r for r in self.rules if r.matches(action)]
            if not matching_rules:
                return RateLimitDecision(allowed=True)

            # First pass: check limits for all matching rules
            for rule in matching_rules:
                history = self._history.setdefault(rule.name, [])
                # Prune calls outside the sliding window
                cutoff = current_time - rule.window_seconds
                active_calls = [t for t in history if t > cutoff]
                self._history[rule.name] = active_calls

                if len(active_calls) >= rule.max_calls:
                    reason = (
                        f"Rate limit '{rule.name}' exceeded: {len(active_calls)} calls "
                        f"in past {rule.window_seconds:.1f}s (ceiling is {rule.max_calls})."
                    )
                    logger.warning("[RateLimitGate] Refused action %r: %s", action.action_name, reason)
                    return RateLimitDecision(
                        allowed=False,
                        policy_id=RATELIMIT_POLICY,
                        reason=reason,
                        rule_name=rule.name,
                        observed_count=len(active_calls),
                        limit=rule.max_calls,
                        window_seconds=rule.window_seconds,
                    )

            # Second pass: all matching rules passed, record this call in all matching histories
            for rule in matching_rules:
                self._history[rule.name].append(current_time)

            return RateLimitDecision(
                allowed=True,
                policy_id=RATELIMIT_POLICY,
            )
