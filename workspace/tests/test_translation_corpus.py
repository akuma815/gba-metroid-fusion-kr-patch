from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "workspace" / "scripts"))

import translation_corpus as corpus


class TranslationCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = corpus.build_report(corpus.DEFAULT_CSV)

    def test_complete_csv_identity_and_counts(self):
        self.assertEqual(
            cls_sha := self.report["source"]["csv_sha256"],
            "1A688D4874B24713C4921C05404CD85B383B3B6371F11EBA1FCD3A245138F1CB",
        )
        self.assertEqual(len(cls_sha), 64)
        self.assertEqual(self.report["corpus"]["entry_count"], 349)
        self.assertEqual(self.report["corpus"]["unique_hangul_syllables"], 546)
        self.assertEqual(self.report["corpus"]["hangul_occurrences"], 14360)

    def test_encoding_and_storage_boundaries(self):
        self.assertEqual(self.report["unsupported_literals"], [])
        self.assertEqual(
            self.report["literal_alias_sequences"],
            {},
        )
        self.assertEqual(self.report["corpus"]["source_logical_bytes"], 54324)
        self.assertEqual(self.report["corpus"]["target_logical_bytes"], 45328)
        self.assertEqual(self.report["corpus"]["individual_overflow_count"], 86)

    def test_hangul_nominally_fits_but_is_not_safe(self):
        first = self.report["hangul_allocation"][0]
        self.assertEqual(first["candidate_count"], 581)
        self.assertEqual(first["nominal_spare_cells"], 35)
        self.assertEqual(first["count_result"], "fits")
        self.assertEqual(first["inventory_status"], "provisional_not_globally_safe")
        second = self.report["hangul_allocation"][1]
        self.assertEqual(second["nominal_spare_cells"], 178)
        self.assertEqual(second["count_result"], "fits")

    def test_file_select_alias_and_repack_constraints(self):
        aliases = self.report["file_select_internal_suffix_aliases"]
        self.assertEqual(aliases["count"], 13)
        self.assertEqual(aliases["preserved_count"], 7)
        populations = {item["population_id"]: item for item in self.report["storage_by_population"]}
        self.assertTrue(populations["navigation"]["fits_source_occupied_span_if_independently_repacked"])
        self.assertFalse(populations["file_select"]["fits_source_occupied_span_if_independently_repacked"])
        self.assertTrue(populations["file_select_shared"]["fits_source_occupied_span_if_independently_repacked"])

    def test_malformed_tokens_are_rejected(self):
        with self.assertRaises(corpus.TranslationCorpusError):
            corpus.split_units("테스트{br")


if __name__ == "__main__":
    unittest.main()
