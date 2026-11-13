"""Which recalled corrections a rationale cites, and which cited IDs were never recalled."""
from app.workspace.citations import citations

A = 'correction-021bdf864a92418abe76c5e026cef585'
B = 'correction-021bdf86ffffffffffffffffffffffff'
C = 'correction-9c0ffee0000000000000000000000000'


def recalled(*ids):
    return [{'source_id': id, 'text': 'Reject ink.'} for id in ids]


def test_a_full_id_that_was_sent_is_cited():
    got = citations(f'Sharp white characters are ink, as in {A}.', recalled(A, C))
    assert got == {'cited_ids': [A], 'uncited_ids': [C], 'unknown_citations': []}


def test_a_unique_shortened_id_resolves_to_the_full_id():
    got = citations('Applied correction-9c0ffee0.', recalled(A, C))
    assert got['cited_ids'] == [C]
    assert got['unknown_citations'] == []


def test_a_prefix_shared_by_two_sent_ids_is_not_guessed():
    got = citations('Applied correction-021bdf86.', recalled(A, B))
    assert got['cited_ids'] == []
    assert got['unknown_citations'] == ['correction-021bdf86']


def test_an_id_that_was_not_sent_is_reported():
    got = citations('Applied correction-deadbeefdeadbeef.', recalled(A))
    assert got == {'cited_ids': [], 'uncited_ids': [A], 'unknown_citations': ['correction-deadbeefdeadbeef']}


def test_a_rationale_without_ids_cites_nothing():
    got = citations('The bright area is natural gloss.', recalled(A, C))
    assert got == {'cited_ids': [], 'uncited_ids': [A, C], 'unknown_citations': []}


def test_two_facts_from_one_correction_count_as_one_citation():
    got = citations(f'Applied {A}.', recalled(A, A))
    assert got == {'cited_ids': [A], 'uncited_ids': [], 'unknown_citations': []}


def test_an_uppercase_id_is_matched():
    got = citations(f'Applied {A.upper()}.', recalled(A))
    assert got['cited_ids'] == [A]


def test_with_memory_off_any_cited_id_is_unknown():
    got = citations(f'Applied {A}.', [])
    assert got == {'cited_ids': [], 'uncited_ids': [], 'unknown_citations': [A]}


def test_ordinary_words_after_correction_are_not_read_as_ids():
    got = citations('A correction-based standard and correction-deadbeefxyz are not IDs.', recalled(A))
    assert got['cited_ids'] == [] and got['unknown_citations'] == []
