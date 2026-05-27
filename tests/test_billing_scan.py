"""Unit tests for billing CSV parsing."""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ai_eng_audit.tier1.billing_scan import (
    BillingScanError,
    detect_vendor,
    scan_billing,
)


_ANTHROPIC_CSV = """\
usage_date_utc,model,workspace,api_key,usage_type,context_window,token_type,cost_usd,list_price_usd,cost_type,inference_geo,speed
2026-03-15,Claude Opus 4.6,Default,OB-1,message,≤ 200k,input_no_cache,1.50,1.50,token,global,
2026-03-15,Claude Opus 4.6,Default,OB-1,message,≤ 200k,output,0.50,0.50,token,global,
2026-03-16,Claude Sonnet 4.6,Default,OB-1,message,≤ 200k,input_no_cache,2.00,2.00,token,global,
"""


_OPENROUTER_CSV = """\
Date,Slug,Usage,BYOK Usage,Requests,Prompt Tokens,Completion Tokens,Reasoning Tokens
"2026-05-12 00:00:00","anthropic/claude-opus-4.7","430.07","0","4115","70965665","3009973","0"
"2026-05-13 00:00:00","anthropic/claude-opus-4.7","505.87","0","4254","87199493","2795119","0"
"""


_ANTHROPIC_TOKENS_ONLY_CSV = """\
usage_date_utc,model_version,api_key,workspace,usage_type,context_window,usage_input_tokens_no_cache,usage_output_tokens,web_search_count,inference_geo,speed
2026-03-15,claude-opus-4-6,OB-1,Default,standard,≤ 200k,154214,2640,0,global,
"""


_BROKEN_ANTHROPIC_CSV = """\
usage_date_utc,model,cost_usd
not-a-date,foo,not-a-number
also-bad,bar,still-bad
"""


def _write(tmp: Path, name: str, content: str) -> Path:
    path = tmp / name
    path.write_text(content, encoding="utf-8")
    return path


class DetectVendorTests(unittest.TestCase):
    def test_anthropic_cost_csv_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "anthropic.csv", _ANTHROPIC_CSV)
            self.assertEqual(detect_vendor(p), "anthropic")

    def test_openrouter_csv_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "or.csv", _OPENROUTER_CSV)
            self.assertEqual(detect_vendor(p), "openrouter")

    def test_anthropic_tokens_only_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "tokens.csv", _ANTHROPIC_TOKENS_ONLY_CSV)
            with self.assertRaises(BillingScanError) as ctx:
                detect_vendor(p)
            self.assertIn("tokens-only", str(ctx.exception))

    def test_unknown_csv_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "weird.csv", "foo,bar,baz\n1,2,3\n")
            with self.assertRaises(BillingScanError):
                detect_vendor(p)


class ScanBillingTests(unittest.TestCase):
    def test_anthropic_parses_and_sums_by_day(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "anthropic.csv", _ANTHROPIC_CSV)
            result = scan_billing([p])

            self.assertEqual(result.vendors, ("anthropic",))
            self.assertEqual(len(result.periods), 2)  # two distinct days
            self.assertEqual(result.skipped_rows, 0)

            by_date = {p.date.isoformat(): p.cost_usd for p in result.periods}
            self.assertEqual(by_date["2026-03-15"], Decimal("2.00"))  # 1.50 + 0.50
            self.assertEqual(by_date["2026-03-16"], Decimal("2.00"))

    def test_openrouter_parses_and_excludes_byok(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "or.csv", _OPENROUTER_CSV)
            result = scan_billing([p])

            self.assertEqual(result.vendors, ("openrouter",))
            self.assertEqual(len(result.periods), 2)
            total = sum((p.cost_usd for p in result.periods), Decimal("0"))
            self.assertEqual(total, Decimal("935.94"))  # 430.07 + 505.87

    def test_zero_parseable_rows_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "broken.csv", _BROKEN_ANTHROPIC_CSV)
            with self.assertRaises(BillingScanError) as ctx:
                scan_billing([p])
            self.assertIn("no parseable cost rows", str(ctx.exception))

    def test_multiple_files_merged(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            a = _write(d, "anthropic.csv", _ANTHROPIC_CSV)
            o = _write(d, "or.csv", _OPENROUTER_CSV)
            result = scan_billing([a, o])

            self.assertEqual(result.vendors, ("anthropic", "openrouter"))
            # 2 anthropic days + 2 openrouter days
            self.assertEqual(len(result.periods), 4)

    def test_scope_propagated(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "anthropic.csv", _ANTHROPIC_CSV)
            result = scan_billing([p], scope="aligned")
            self.assertEqual(result.scope, "aligned")


if __name__ == "__main__":
    unittest.main()
