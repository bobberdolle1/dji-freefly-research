"""The mutation gate.

Everything in this library is read-only by default. State-changing operations
are not merely discouraged by documentation: they are refused at runtime unless
the caller has taken an explicit, auditable step.

Two independent mechanisms, because either alone has a failure mode:

``MutationGuard``
    A policy object consulted by every write-capable call site. It starts
    :attr:`MutationGuard.allowed` **False**. A caller must call
    :meth:`MutationGuard.enable` with a written justification, and the guard
    records who enabled it and why so a log shows the intent.

``DryRunTransport``
    A transport that renders frames without sending them. Useful on its own, and
    also used as the enforcement point: :class:`~flylib.transport.Session` will
    not transmit a mutating frame through a live transport unless the guard
    permits it.

The ordering matters. ``enable()`` is not enough on its own — the session still
requires the guard, and the guard still requires an explicit reason. Both are
checked, so a future refactor that wires only one of them fails closed.
"""
from __future__ import annotations

import dataclasses
import time


class MutationNotAllowed(PermissionError):
    """Raised when a state-changing operation is attempted without opt-in."""


@dataclasses.dataclass
class MutationGuard:
    """Disabled by default. Enable requires a reason that is recorded, not dropped.

    >>> guard = MutationGuard()
    >>> guard.allowed
    False
    >>> guard.require("writeParamValue2017")
    Traceback (most recent call last):
        ...
    flylib.guard.MutationNotAllowed: mutation is disabled by default ...
    """

    allowed: bool = False
    reason: str = ""
    enabled_at: float | None = None
    enabled_by: str | None = None
    dry_run: bool = True

    def enable(self, reason: str, *, actor: str | None = None,
               dry_run: bool = True) -> None:
        """Allow state-changing operations to be *considered*.

        ``reason`` is mandatory: a blank or whitespace-only justification is
        rejected, so "enable it for now" cannot become the audit record.

        ``dry_run`` defaults to **True** deliberately. Enabling the guard is
        easy and gets you a logged dry run; going all the way to a live write
        should require typing ``dry_run=False`` explicitly, so the safe mode is
        the one you land in rather than the one you have to remember to pick.
        """
        if not reason or not reason.strip():
            raise ValueError("enabling mutation requires a written reason")
        self.allowed = True
        self.reason = reason.strip()
        self.enabled_by = actor
        self.enabled_at = time.time()
        self.dry_run = dry_run

    def disable(self) -> None:
        """Return to the default state and forget the justification."""
        self.allowed = False
        self.reason = ""
        self.enabled_by = None
        self.enabled_at = None
        self.dry_run = True

    def require(self, operation: str) -> None:
        """Raise unless this operation may proceed.

        Called at the top of every state-changing code path.
        """
        if not self.allowed:
            raise MutationNotAllowed(
                f"mutation is disabled by default; refusing {operation}. "
                f"Call MutationGuard.enable(reason=...) if you really mean it, "
                f"and prefer dry_run=True while developing.")
        if self.dry_run:
            raise MutationNotAllowed(
                f"{operation} permitted by the guard but suppressed: dry_run is "
                f"enabled (reason: {self.reason!r})")

    def describe(self) -> dict:
        return {
            "allowed": self.allowed,
            "dry_run": self.dry_run,
            "reason": self.reason,
            "enabled_by": self.enabled_by,
            "enabled_at": self.enabled_at,
        }


# Operations that change aircraft state. Kept as data so the write-path tests
# and the documentation enumerate the same set.
STATE_CHANGING_COMMANDS = frozenset({
    "writeParamValue2015",   # cmdSet FC, cmdId -7
    "writeParamValue2017",   # cmdSet FC, cmdId -29
    "assistantUnlock",       # cmdSet FC, cmdId -33: alters FC assistant state
})


def is_state_changing(cmd_set: int, signed_cmd_id: int) -> bool:
    """Classify a frame without trusting the caller's intent."""
    from .commands import (CMD_SET_FC, CMD_FC_ASSISTANT_UNLOCK,
                           CMD_FC_PARAM_WRITE_2015, CMD_FC_PARAM_WRITE_2017)
    if cmd_set != CMD_SET_FC:
        return False
    return signed_cmd_id in (CMD_FC_PARAM_WRITE_2015, CMD_FC_PARAM_WRITE_2017,
                             CMD_FC_ASSISTANT_UNLOCK)