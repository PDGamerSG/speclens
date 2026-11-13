"""Which recalled corrections did the model cite? Read from the rationale, checked against what was sent."""
from __future__ import annotations

import re

# A correction ID is 'correction-' and 32 hex characters. A shortened ID needs at least 8 of them.
CITED = re.compile(r'\bcorrection-[0-9a-f]{8,}(?![0-9a-z])', re.IGNORECASE)


def citations(rationale: str | None, memories: list[dict] | None) -> dict:
    """Split the recalled corrections into cited and uncited, and list cited IDs that were never recalled.

    A shortened ID counts only when it matches exactly one recalled correction. Anything else, including an
    ID cited when memory was off, goes to unknown_citations so it can be shown as a warning.
    """
    sent = sorted({str(m['source_id']) for m in memories or [] if m.get('source_id')})
    cited, unknown = set(), []
    for token in sorted({t.lower() for t in CITED.findall(rationale or '')}):
        matches = [s for s in sent if s.lower().startswith(token)]
        if len(matches) == 1:
            cited.add(matches[0])
        else:
            unknown.append(token)
    return {'cited_ids': sorted(cited),
            'uncited_ids': [s for s in sent if s not in cited],
            'unknown_citations': unknown}
