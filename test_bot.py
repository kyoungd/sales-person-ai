import asyncio
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from bot import build_system_instruction, make_request_callback


def run_tool(tool, **kwargs):
    """Invoke an async direct-function tool with a fake FunctionCallParams,
    returning what it passed to result_callback."""
    results = []

    async def result_callback(result):
        results.append(result)

    params = SimpleNamespace(result_callback=result_callback)
    asyncio.run(tool(params, **kwargs))
    return results[0]


class RequestCallbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.leads_path = Path(self.tmp.name) / "leads.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_records_lead_with_caller_number(self):
        tool = make_request_callback("+13105551212", self.leads_path)
        result = run_tool(
            tool,
            callback_time="tomorrow afternoon",
            interest_note="asked about the LS3 engine and warranty",
            language="English",
        )
        self.assertEqual(result["status"], "recorded")

        leads = json.loads(self.leads_path.read_text())
        self.assertEqual(len(leads), 1)
        lead = leads[0]
        self.assertEqual(lead["caller_number"], "+13105551212")
        self.assertEqual(lead["callback_time"], "tomorrow afternoon")
        self.assertEqual(lead["interest_note"], "asked about the LS3 engine and warranty")
        self.assertEqual(lead["language"], "English")
        datetime.fromisoformat(lead["timestamp"])  # valid ISO timestamp

    def test_appends_second_lead(self):
        tool = make_request_callback("+13105551212", self.leads_path)
        run_tool(tool, callback_time="tonight", interest_note="price", language="English")
        tool2 = make_request_callback("+818012345678", self.leads_path)
        run_tool(tool2, callback_time="mañana", interest_note="precio", language="Spanish")

        leads = json.loads(self.leads_path.read_text())
        self.assertEqual(len(leads), 2)
        self.assertEqual(leads[1]["caller_number"], "+818012345678")
        self.assertEqual(leads[1]["language"], "Spanish")

    def test_missing_caller_number_fails_and_writes_nothing(self):
        tool = make_request_callback(None, self.leads_path)
        result = run_tool(
            tool, callback_time="tomorrow", interest_note="specs", language="English"
        )
        self.assertEqual(result["status"], "failed")
        self.assertFalse(self.leads_path.exists())


class SystemInstructionTest(unittest.TestCase):
    def test_contains_data_persona_and_multilingual_rule(self):
        car = "UNIQUE-CAR-MARKER 1969 Corvette Stingray $119,950"
        company = "UNIQUE-COMPANY-MARKER Ironwood Custom Classics"
        instruction = build_system_instruction(car, company)

        self.assertIn(car, instruction)          # listing data verbatim
        self.assertIn(company, instruction)      # company data verbatim
        self.assertIn("Ava", instruction)        # persona name
        self.assertIn("language", instruction)   # multilingual rule present


if __name__ == "__main__":
    unittest.main()
