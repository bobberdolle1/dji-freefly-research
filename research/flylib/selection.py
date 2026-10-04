"""Parameter-protocol selection.

This models the structure recovered from ``DroneRepository.readAllParameters``
and ``readAll2017``. Only behaviour that was pinned from bytecode is modelled.

**The app is 2017-only in practice, and this module now reflects that.**

The APK contains a complete 2015 implementation — ``readAll2015`` calls
``getParamInfoByIndex2015`` and ``readParamValue2015`` — and ``readAll2017``
even logs ``"Table N empty or no response, falling back to 2015"``. But that
log string is all there is. Verified across the whole decoded tree:

* ``readAll2017`` is invoked directly at ``DroneRepository.smali:10001``,
  inside ``readAllParameters``. It is the only live bulk-read path.
* the only ``invoke-direct`` to ``readAll2015`` is line 751, which sits inside
  the synthetic accessor ``access$readAll2015`` (lines 745-755);
* ``access$readAll2015`` is referenced exactly once in the entire tree —
  ``DroneRepository$readAll2015$1.smali:145``, its own coroutine
  continuation, which is the normal Kotlin self-resume pattern and not a caller;
* ``readByIndexMap``, the fast path, calls ``readParamValue2017`` only.

So ``readAll2015`` is **unreachable dead code**, the fallback message has no
fallback behind it, and an aircraft whose tables all report zero parameters
gets an empty result and a log line rather than a 2015 scan.

Confirmed structure that *is* modelled
-------------------------------------

1. The AC's model **codename** selects the index-map cache file
   ``<codename>_index_map.json``.
2. If a map exists for that codename and a full scan is not forced, the app
   takes a **fast path**: read exactly those pairs via ``readByIndexMap``.
   Diagnostics: ``"Cache hit for <codename>: N known indices — fast read"``,
   then ``"Fast read done: N"``.
3. Otherwise a **full 2017 scan**: for each table, ``getTableAttribs2017`` for
   its declared count, then ``getParamInfo2017`` / ``readParamValue2017`` per
   parameter. Diagnostics: ``"Full scan for <codename> (first time)"``, then
   ``"Scan done: N"``.
4. A table reporting zero parameters, or not answering, logs
   ``"Table N empty or no response, falling back to 2015"`` and is **skipped**.
   It does not change the protocol, and it is not counted as a fallback.
5. After a full scan the index map is saved for the codename.

Unpinned, and therefore not modelled
------------------------------------

* The set of table numbers the app iterates. It is an explicit argument rather
  than a swept default, because inventing a bound (say 256) would manufacture
  skipped tables — and a spurious "falling back to 2015" line — for every
  aircraft that does not fill the space.
* The interaction of the ``force`` flag with the empty-result test at the end
  of ``readAllParameters``. The coroutine state object moves the candidate
  register ambiguously.

Both are recorded in ``docs/ARCHITECTURE.md`` rather than filled in.
"""
from __future__ import annotations

import dataclasses
from typing import Callable, Iterable, Protocol, Sequence

INDEX_MAP_SUFFIX = "_index_map.json"
PROTOCOL_2017 = "2017"

#: The protocol the app actually uses for bulk reads. 2015 exists in the APK but
#: is unreachable; see the module docstring for the call-site evidence.
ACTIVE_PROTOCOL = PROTOCOL_2017


#: Behaviour deliberately absent from this model, with why.
UNPINNED = (
    "the bound on the number of parameter tables the app iterates",
    "the interaction of readAllParameters' force flag with the empty-result test",
)


#: The message the app logs when a table yields nothing. It is a diagnostic
#: string, not evidence of a fallback: no 2015 code runs behind it.
EMPTY_TABLE_DIAGNOSTIC = "empty or no response, falling back to 2015"


class ParameterSource(Protocol):
    """The 2017 aircraft-facing operations the policy needs."""

    def table_attribs_2017(self, table_no: int) -> int | None:
        """Declared parameter count for a table, or ``None`` if unanswered."""

    def read_2017(self, table_no: int, param_index: int) -> object | None: ...


@dataclasses.dataclass
class TablePlan:
    table_no: int
    declared_count: int
    used: bool
    reason: str


@dataclasses.dataclass
class ScanResult:
    protocol: str
    values: list
    tables: list[TablePlan]
    index_map: list[tuple[int, int]]
    diagnostics: list[str]
    used_cache: bool = False

    @property
    def skipped_tables(self) -> list[TablePlan]:
        """Tables that yielded nothing. Not a protocol fallback."""
        return [t for t in self.tables if not t.used]


class IndexMapStore:
    """Index-map persistence, matching the app's file naming."""

    def __init__(self,
                 load: Callable[[str], Sequence[tuple[int, int]] | None],
                 save: Callable[[str, Sequence[tuple[int, int]]], None]) -> None:
        self._load = load
        self._save = save

    @staticmethod
    def filename(codename: str) -> str:
        return f"{codename}{INDEX_MAP_SUFFIX}"

    def load(self, codename: str) -> list[tuple[int, int]] | None:
        return self._load(self.filename(codename))

    def save(self, codename: str, pairs: Sequence[tuple[int, int]]) -> None:
        self._save(self.filename(codename), list(pairs))


def select_parameters(source: ParameterSource, codename: str,
                      index_maps: IndexMapStore | None = None,
                      force_full_scan: bool = False,
                      tables: Iterable[int] = (0,),
                      on_diagnostic: Callable[[str], None] | None = None,
                      ) -> ScanResult:
    """Run the 2017 scan, or the index-map fast path.

    ``force_full_scan`` skips the fast path. Its interaction with an empty
    result is *not* modelled — see the module docstring. ``tables`` is an
    explicit input for the reason given there.
    """
    diag: list[str] = []
    emit = on_diagnostic or (lambda _m: None)

    def note(message: str) -> None:
        diag.append(message)
        emit(message)

    if index_maps is not None and not force_full_scan:
        cached = index_maps.load(codename)
        if cached:
            note(f"Cache hit for {codename}: {len(cached)} known indices — fast read")
            values = [v for v in (source.read_2017(t, i) for t, i in cached)
                      if v is not None]
            note(f"Fast read done: {len(values)}")
            return ScanResult(PROTOCOL_2017, values, [], list(cached), diag,
                              used_cache=True)

    note(f"Full scan for {codename} (first time)")
    plans: list[TablePlan] = []
    index_map: list[tuple[int, int]] = []
    for table_no in tables:
        declared = source.table_attribs_2017(table_no)
        if not declared:
            note(f"Table {table_no} {EMPTY_TABLE_DIAGNOSTIC}")
            plans.append(TablePlan(table_no, declared or 0, False, EMPTY_TABLE_DIAGNOSTIC))
            continue
        plans.append(TablePlan(table_no, declared, True, "declared non-zero"))
        index_map.extend((table_no, index) for index in range(declared))

    values = [v for v in (source.read_2017(t, i) for t, i in index_map)
              if v is not None]
    note(f"Scan done: {len(values)}")
    if index_map and index_maps is not None:
        index_maps.save(codename, index_map)
    return ScanResult(PROTOCOL_2017, values, plans, index_map, diag)