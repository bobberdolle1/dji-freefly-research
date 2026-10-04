"""Parameter-protocol selection.

This models the structure recovered from ``DroneRepository.readAllParameters``
and ``readAll2017``. Only behaviour that was pinned from bytecode is modelled;
the parts that were not are left out rather than guessed, and are named in
:data:`UNPINNED`.

Confirmed structure
-------------------

1. The AC's model **codename** selects the index-map cache file
   ``<codename>_index_map.json``.
2. If an index map exists for that codename and a full scan was not forced, the
   app takes a **fast path**: read exactly those ``(table, index)`` pairs via
   ``readByIndexMap`` and return. Diagnostic: ``"Cache hit for <codename>: N
   known indices — fast read"``, then ``"Fast read done: N"``.
3. Otherwise a **full 2017 scan**: for each parameter table, ask
   ``getTableAttribs2017(tableNo)`` for its declared parameter count. Diagnostic:
   ``"Full scan for <codename> (first time)"``, then ``"Scan done: N"``.
4. A table reporting **zero** parameters, or not answering, is logged as
   ``"Table N empty or no response, falling back to 2015"``. This is the
   **per-table fallback trigger**.
5. The 2015 protocol is walked to an explicit end-of-list marker, not a known
   count: ``"2015 EOL at index "``.
6. After a full scan the index map is saved for the codename.

Unpinned, and therefore not modelled
------------------------------------

* The set of table numbers the app iterates. It is exposed as the ``tables``
  argument instead of a swept default, because inventing a bound (say 256)
  would manufacture a fallback for every aircraft that does not fill the space.
* The interaction of the ``force`` flag with the empty-result test at the end of
  ``readAllParameters``. The coroutine state object moves the candidate register
  in a way that admits more than one reading, so guessing would put a fabricated
  rule into the component that decides which protocol talks to the aircraft.

Both are recorded as open in ``docs/ARCHITECTURE.md`` rather than filled in.
"""
from __future__ import annotations

import dataclasses
from typing import Callable, Iterable, Protocol, Sequence

INDEX_MAP_SUFFIX = "_index_map.json"
PROTOCOL_2015 = "2015"
PROTOCOL_2017 = "2017"

#: Behaviour deliberately absent from this model, with why.
UNPINNED = (
    "the bound on the number of parameter tables the app iterates",
    "the interaction of readAllParameters' force flag with the empty-result test",
)


class ParameterSource(Protocol):
    """The aircraft-facing operations the policy needs."""

    def table_attribs_2017(self, table_no: int) -> int | None:
        """Declared parameter count for a table, or ``None`` if unanswered."""

    def read_2017(self, table_no: int, param_index: int) -> object | None: ...

    def read_by_hash_2015(self, index: int) -> object | None: ...

    def eol_2015(self, index: int) -> bool:
        """Is this 2015 index the end-of-list marker?"""


@dataclasses.dataclass
class TablePlan:
    table_no: int
    declared_count: int
    used_2017: bool
    reason: str


@dataclasses.dataclass
class ScanResult:
    protocol: str
    values: list
    tables: list[TablePlan]
    index_map: list[tuple[int, int]]
    diagnostics: list[str]

    @property
    def used_fallback(self) -> bool:
        """Did any table fail the 2017 route?"""
        return any(not t.used_2017 for t in self.tables)

    @property
    def protocol_forced(self) -> bool:
        """Did the 2015 walk produce every value?"""
        return self.protocol == PROTOCOL_2015


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
                      max_2015_indices: int = 1_000_000) -> ScanResult:
    """Choose a protocol and return the parameters.

    ``tables`` is an explicit input for the reason given in the module
    docstring. ``max_2015_indices`` is a runaway guard this project adds; the
    app has no equivalent, which is itself worth knowing before walking a live
    link.
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
            return ScanResult(PROTOCOL_2017, values, [], list(cached), diag)

    note(f"Full scan for {codename} (first time)")

    plans: list[TablePlan] = []
    index_map: list[tuple[int, int]] = []
    for table_no in tables:
        declared = source.table_attribs_2017(table_no)
        if not declared:
            note(f"Table {table_no} empty or no response, falling back to 2015")
            plans.append(TablePlan(table_no, declared or 0, False,
                                   "empty or no response"))
            continue
        plans.append(TablePlan(table_no, declared, True, "declared non-zero"))
        index_map.extend((table_no, index) for index in range(declared))

    if index_map:
        values = [v for v in (source.read_2017(t, i) for t, i in index_map)
                  if v is not None]
        note(f"Scan done: {len(values)}")
        if index_maps is not None:
            index_maps.save(codename, index_map)
        return ScanResult(PROTOCOL_2017, values, plans, index_map, diag)

    note("falling back to the 2015 name-hash protocol")
    values = []
    index = 0
    while index < max_2015_indices:
        if source.eol_2015(index):
            note(f"2015 EOL at index {index}")
            break
        value = source.read_by_hash_2015(index)
        if value is not None:
            values.append(value)
        index += 1
    else:
        note(f"2015 walk exceeded {max_2015_indices} indices, aborting")
    note(f"Scan done: {len(values)}")
    return ScanResult(PROTOCOL_2015, values, plans, [], diag)