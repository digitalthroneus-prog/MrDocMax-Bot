"""
Tests for the refactored JARVIS Corporate Document Bot.
Covers: detail parsing, ZIP assembly, document specs, watermark clause.
"""
import io
import zipfile
import sys
import os

# Ensure the module can be imported without a running bot or live .env
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "fake-token-for-tests")
os.environ.setdefault("EMERGENT_API_KEY", "fake-key-for-tests")

sys.path.insert(0, os.path.dirname(__file__))

import main as bot


# ---------------------------------------------------------------------------
# _parse_details
# ---------------------------------------------------------------------------
class TestParseDetails:
    def test_full_input(self):
        raw = (
            "Company Name: Acme Ltd\n"
            "Entity Type: LLC\n"
            "Jurisdiction: Cayman Islands\n"
            "Formation Date: 01 Jan 2019\n"
            "Director Name: Bob Jones\n"
            "Shareholder Name: Alice Smith\n"
        )
        d = bot._parse_details(raw)
        assert d["company_name"] == "Acme Ltd"
        assert d["entity_type"] == "LLC"
        assert d["jurisdiction"] == "Cayman Islands"
        assert d["formation_date"] == "01 Jan 2019"
        assert d["director_name"] == "Bob Jones"
        assert d["shareholder_name"] == "Alice Smith"

    def test_missing_fields_get_defaults(self):
        d = bot._parse_details("")
        assert d["company_name"] == "Nexus Global Holdings Ltd"
        assert d["entity_type"] == "Private Limited Company"
        assert d["jurisdiction"] == "British Virgin Islands"
        assert "company_number" in d
        assert d["company_number"].startswith("BVI-")

    def test_partial_input_uses_defaults_for_rest(self):
        raw = "Company Name: Delta Corp\n"
        d = bot._parse_details(raw)
        assert d["company_name"] == "Delta Corp"
        assert d["director_name"] == "Alexander J. Morrison"

    def test_company_number_is_unique(self):
        d1 = bot._parse_details("")
        d2 = bot._parse_details("")
        assert d1["company_number"] != d2["company_number"]

    def test_unknown_key_goes_to_extra(self):
        raw = "Custom Field: Some Value\n"
        d = bot._parse_details(raw)
        assert "custom_field" in d["extra"].lower()


# ---------------------------------------------------------------------------
# build_zip
# ---------------------------------------------------------------------------
class TestBuildZip:
    def _make_details(self):
        return bot._parse_details("Company Name: TestCo Ltd")

    def test_zip_contains_readme(self):
        details = self._make_details()
        data = bot.build_zip("ALL TEXT HERE", {}, details)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert "README.txt" in zf.namelist()

    def test_zip_contains_all_documents_text(self):
        details = self._make_details()
        data = bot.build_zip("ALL TEXT HERE", {}, details)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert "ALL_DOCUMENTS.txt" in zf.namelist()
            content = zf.read("ALL_DOCUMENTS.txt").decode()
            assert "ALL TEXT HERE" in content

    def test_zip_contains_images(self):
        details = self._make_details()
        images = {
            "02_Share_Certificate_Mockup.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
            "04_Certificate_Good_Standing_Mockup.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
        }
        data = bot.build_zip("DOC TEXT", images, details)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            assert "02_Share_Certificate_Mockup.png" in names
            assert "04_Certificate_Good_Standing_Mockup.png" in names

    def test_readme_contains_company_name(self):
        details = self._make_details()
        data = bot.build_zip("text", {}, details)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            readme = zf.read("README.txt").decode()
            assert "TestCo Ltd" in readme

    def test_readme_contains_not_official_notice(self):
        details = self._make_details()
        data = bot.build_zip("text", {}, details)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            readme = zf.read("README.txt").decode()
            assert "NOT OFFICIAL" in readme or "NON-OFFICIAL" in readme

    def test_zip_is_valid_zip(self):
        details = self._make_details()
        data = bot.build_zip("text", {}, details)
        assert zipfile.is_zipfile(io.BytesIO(data))


# ---------------------------------------------------------------------------
# DOCUMENT_SPECS structure
# ---------------------------------------------------------------------------
class TestDocumentSpecs:
    def test_twelve_documents_defined(self):
        assert len(bot.DOCUMENT_SPECS) == 12

    def test_filenames_have_png_extension(self):
        for fname, _ in bot.DOCUMENT_SPECS:
            assert fname.endswith(".png"), f"{fname} must end with .png"

    def test_filenames_are_numbered(self):
        for i, (fname, _) in enumerate(bot.DOCUMENT_SPECS, start=1):
            prefix = f"{i:02d}_"
            assert fname.startswith(prefix), f"{fname} must start with {prefix}"

    def test_image_docs_are_subset_of_specs(self):
        spec_filenames = {fname for fname, _ in bot.DOCUMENT_SPECS}
        for fname in bot.IMAGE_DOCS:
            assert fname in spec_filenames, f"{fname} in IMAGE_DOCS not in DOCUMENT_SPECS"

    def test_five_image_docs(self):
        assert len(bot.IMAGE_DOCS) == 5


# ---------------------------------------------------------------------------
# Watermark clause
# ---------------------------------------------------------------------------
class TestWatermarkClause:
    def test_watermark_contains_sample(self):
        assert "SAMPLE" in bot.WATERMARK_CLAUSE

    def test_watermark_contains_not_official(self):
        assert "NOT OFFICIAL" in bot.WATERMARK_CLAUSE

    def test_watermark_contains_for_review(self):
        assert "FOR REVIEW" in bot.WATERMARK_CLAUSE


# ---------------------------------------------------------------------------
# Constants / config
# ---------------------------------------------------------------------------
class TestConfig:
    def test_conversation_states_are_distinct(self):
        assert bot.AWAITING_DETAILS != bot.AWAITING_PHOTO

    def test_greet_text_mentions_jarvis(self):
        assert "JARVIS" in bot.GREET_TEXT

    def test_greet_text_lists_key_documents(self):
        assert "Share Certificate" in bot.GREET_TEXT
        assert "Board Resolution" in bot.GREET_TEXT
        assert "AML" in bot.GREET_TEXT
