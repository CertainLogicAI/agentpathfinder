"""Tests for AgentPathfinder pattern validation engine.

Every check type tested: equals, contains, excludes, empty, not_empty,
matches, lt, gt, and/or/not combinators, edge cases.
"""

import pytest
from agentpathfinder.result_validator import (
    validate,
    rules_from_step,
    ValidationReport,
)


# ---------------------------------------------------------------------------
# equals
# ---------------------------------------------------------------------------

class TestCheckEquals:
    def test_exit_code_zero(self):
        r = validate({"exit_code": 0}, {"exit_code": {"equals": 0}})
        assert r.passed is True
        assert len(r.failed_checks) == 0

    def test_exit_code_nonzero_fails(self):
        r = validate({"exit_code": 1}, {"exit_code": {"equals": 0}})
        assert r.passed is False
        assert any("exit_code" in f for f in r.failed_checks)

    def test_string_equals(self):
        r = validate({"stdout": "hello"}, {"stdout": {"equals": "hello"}})
        assert r.passed is True

    def test_bool_equals(self):
        r = validate({"result": {"ok": True}}, {"result.ok": {"equals": True}})
        assert r.passed is True


# ---------------------------------------------------------------------------
# contains
# ---------------------------------------------------------------------------

class TestCheckContains:
    def test_substring_found(self):
        r = validate({"stdout": "47 passed in 2.34s"}, {"stdout": {"contains": "passed"}})
        assert r.passed is True

    def test_substring_not_found(self):
        r = validate({"stdout": "47 passed"}, {"stdout": {"contains": "FAILED"}})
        assert r.passed is False

    def test_non_string_value_fails(self):
        r = validate({"exit_code": 0}, {"exit_code": {"contains": "0"}})
        assert r.passed is False

    def test_unicode_content(self):
        r = validate({"stdout": "✓ 3 tests passed"}, {"stdout": {"contains": "✓"}})
        assert r.passed is True


# ---------------------------------------------------------------------------
# excludes
# ---------------------------------------------------------------------------

class TestCheckExcludes:
    def test_forbidden_absent(self):
        r = validate({"stdout": "all passed"}, {"stdout": {"excludes": "ERROR"}})
        assert r.passed is True

    def test_forbidden_present(self):
        r = validate({"stdout": "ERROR: timeout"}, {"stdout": {"excludes": "ERROR"}})
        assert r.passed is False

    def test_non_string_skips(self):
        r = validate({"exit_code": 0}, {"exit_code": {"excludes": "0"}})
        assert r.passed is True  # can't exclude on non-string


# ---------------------------------------------------------------------------
# empty / not_empty
# ---------------------------------------------------------------------------

class TestCheckEmpty:
    def test_empty_string(self):
        r = validate({"stderr": ""}, {"stderr": {"empty": True}})
        assert r.passed is True

    def test_nonempty_string_fails(self):
        r = validate({"stderr": "warning: x"}, {"stderr": {"empty": True}})
        assert r.passed is False

    def test_none_value(self):
        r = validate({"stderr": None}, {"stderr": {"empty": True}})
        assert r.passed is True


class TestCheckNotEmpty:
    def test_nonempty_stdout(self):
        r = validate({"stdout": "ok"}, {"stdout": {"not_empty": True}})
        assert r.passed is True

    def test_empty_fails(self):
        r = validate({"stdout": ""}, {"stdout": {"not_empty": True}})
        assert r.passed is False


# ---------------------------------------------------------------------------
# matches (regex)
# ---------------------------------------------------------------------------

class TestCheckMatches:
    def test_regex_match(self):
        r = validate({"stdout": "3 passed, 0 failed"},
                     {"stdout": {"matches": r"\d+ passed"}})
        assert r.passed is True

    def test_regex_no_match(self):
        r = validate({"stdout": "all ok"}, {"stdout": {"matches": r"\d+ failed"}})
        assert r.passed is False

    def test_invalid_regex(self):
        r = validate({"stdout": "hi"}, {"stdout": {"matches": r"["}})
        assert r.passed is False  # invalid pattern -> fail


# ---------------------------------------------------------------------------
# lt / gt (numeric)
# ---------------------------------------------------------------------------

class TestCheckLt:
    def test_under_threshold(self):
        r = validate({"duration_ms": 420}, {"duration_ms": {"lt": 30000}})
        assert r.passed is True

    def test_at_threshold_fails(self):
        r = validate({"duration_ms": 30000}, {"duration_ms": {"lt": 30000}})
        assert r.passed is False

    def test_non_numeric_fails(self):
        r = validate({"duration_ms": "fast"}, {"duration_ms": {"lt": 30000}})
        assert r.passed is False


class TestCheckGt:
    def test_above_threshold(self):
        r = validate({"duration_ms": 500}, {"duration_ms": {"gt": 100}})
        assert r.passed is True

    def test_below_threshold_fails(self):
        r = validate({"duration_ms": 50}, {"duration_ms": {"gt": 100}})
        assert r.passed is False


# ---------------------------------------------------------------------------
# Combination: multiple checks on same field
# ---------------------------------------------------------------------------

class TestMultipleChecks:
    def test_all_pass(self):
        r = validate(
            {"exit_code": 0, "stdout": "3 passed", "stderr": ""},
            {"exit_code": {"equals": 0},
             "stdout": {"contains": "passed"},
             "stderr": {"empty": True}},
        )
        assert r.passed is True

    def test_one_fails_all_fail(self):
        r = validate(
            {"exit_code": 1, "stdout": "3 passed"},
            {"exit_code": {"equals": 0},
             "stdout": {"contains": "passed"}},
        )
        assert r.passed is False
        assert len(r.failed_checks) == 1

    def test_multiple_checks_same_field(self):
        r = validate(
            {"duration_ms": 420},
            {"duration_ms": {"gt": 0, "lt": 30000}},
        )
        assert r.passed is True

    def test_second_check_on_same_field_fails(self):
        r = validate(
            {"duration_ms": 50000},
            {"duration_ms": {"gt": 0, "lt": 30000}},
        )
        assert r.passed is False


# ---------------------------------------------------------------------------
# Nested field resolution
# ---------------------------------------------------------------------------

class TestNestedFields:
    def test_nested_result_field(self):
        r = validate(
            {"result": {"bytes_written": 1024}},
            {"result.bytes_written": {"gt": 0}},
        )
        assert r.passed is True

    def test_deep_nesting(self):
        r = validate(
            {"result": {"deploy": {"status": "success"}}},
            {"result.deploy.status": {"equals": "success"}},
        )
        assert r.passed is True

    def test_missing_nested_field(self):
        r = validate(
            {"result": {}},
            {"result.bytes_written": {"gt": 0}},
        )
        assert r.passed is False
        assert any("missing" in f.lower() for f in r.failed_checks)


# ---------------------------------------------------------------------------
# Combinators: and / or / not
# ---------------------------------------------------------------------------

class TestCombinatorAnd:
    def test_all_sub_checks_pass(self):
        r = validate(
            {"exit_code": 0},
            {"exit_code": {"and": [{"equals": 0}, {"lt": 10}]}},
        )
        assert r.passed is True

    def test_one_sub_check_fails(self):
        r = validate(
            {"exit_code": 1},
            {"exit_code": {"and": [{"equals": 0}, {"lt": 10}]}},
        )
        assert r.passed is False


class TestCombinatorOr:
    def test_first_option_passes(self):
        r = validate(
            {"exit_code": 0},
            {"exit_code": {"or": [{"equals": 0}, {"equals": 1}]}},
        )
        assert r.passed is True

    def test_second_option_passes(self):
        r = validate(
            {"exit_code": 1},
            {"exit_code": {"or": [{"equals": 0}, {"equals": 1}]}},
        )
        assert r.passed is True

    def test_neither_passes(self):
        r = validate(
            {"exit_code": 2},
            {"exit_code": {"or": [{"equals": 0}, {"equals": 1}]}},
        )
        assert r.passed is False


class TestCombinatorNot:
    def test_invert_pass(self):
        r = validate(
            {"exit_code": 1},
            {"exit_code": {"not": {"equals": 0}}},
        )
        assert r.passed is True

    def test_invert_fail(self):
        r = validate(
            {"exit_code": 0},
            {"exit_code": {"not": {"equals": 0}}},
        )
        assert r.passed is False

    def test_double_not(self):
        r = validate(
            {"exit_code": 0},
            {"exit_code": {"not": {"not": {"equals": 0}}}},
        )
        assert r.passed is True


# ---------------------------------------------------------------------------
# Empty / absent rules
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_no_rules_passes(self):
        r = validate({"exit_code": 1}, {})
        assert r.passed is True
        assert len(r.checks) == 0

    def test_unknown_field_still_checks_field(self):
        r = validate({}, {"missing_field": {"equals": 0}})
        assert r.passed is False

    def test_unknown_check_type(self):
        r = validate({"exit_code": 0}, {"exit_code": {"magic": True}})
        assert r.passed is False
        assert any("unknown check" in f for f in r.failed_checks)


# ---------------------------------------------------------------------------
# ValidationReport
# ---------------------------------------------------------------------------

class TestValidationReport:
    def test_to_dict(self):
        report = validate({"exit_code": 0}, {"exit_code": {"equals": 0}})
        d = report.to_dict()
        assert d["passed"] is True
        assert len(d["checks"]) == 1
        assert len(d["failed_checks"]) == 0

    def test_repr_pass(self):
        report = validate({"exit_code": 0}, {"exit_code": {"equals": 0}})
        assert "PASS" in repr(report)

    def test_repr_fail(self):
        report = validate({"exit_code": 1}, {"exit_code": {"equals": 0}})
        assert "FAIL" in repr(report)


# ---------------------------------------------------------------------------
# rules_from_step
# ---------------------------------------------------------------------------

class TestRulesFromStep:
    def test_extract_validation_rules(self):
        step = {"name": "test", "validation": {"exit_code": {"equals": 0}}}
        rules = rules_from_step(step)
        assert rules == {"exit_code": {"equals": 0}}

    def test_no_validation_rules(self):
        step = {"name": "test"}
        assert rules_from_step(step) is None

    def test_non_dict_validation(self):
        step = {"name": "test", "validation": "yes"}
        assert rules_from_step(step) is None


# ---------------------------------------------------------------------------
# Real-world scenarios
# ---------------------------------------------------------------------------

class TestRealWorld:
    def test_test_run_success(self):
        """pytest: 3 passed, 0 failed, exit code 0."""
        result = {
            "exit_code": 0,
            "stdout": (
                "========================= test session starts =========================\n"
                "collected 3 items\n\n"
                "tests/test_api.py ...                      [100%]\n\n"
                "========================== 3 passed in 0.42s ==========================\n"
            ),
            "stderr": "",
            "duration_ms": 420,
        }
        rules = {
            "exit_code": {"equals": 0},
            "stdout": {"contains": "passed"},
            "stdout": {"excludes": "FAILED"},
            "stdout": {"matches": r"\d+ passed in"},
            "stderr": {"empty": True},
            "duration_ms": {"lt": 30000},
        }
        r = validate(result, rules)
        assert r.passed is True

    def test_test_run_failure(self):
        """pytest: 2 passed, 1 FAILED → should catch."""
        result = {
            "exit_code": 1,
            "stdout": (
                "collected 3 items\n\n"
                "tests/test_api.py ..F                    [100%]\n\n"
                "=========== 2 passed, 1 FAILED in 1.2s ===========\n"
            ),
            "stderr": "",
            "duration_ms": 1200,
        }
        rules = {
            "exit_code": {"equals": 0},
            "stdout": {"excludes": "FAILED"},
            "stderr": {"empty": True},
        }
        r = validate(result, rules)
        assert r.passed is False
        assert any("exit_code" in f for f in r.failed_checks)
        assert any("FAILED" in f for f in r.failed_checks)

    def test_deploy_success(self):
        result = {
            "exit_code": 0,
            "stdout": "Deploy successful: version 2.3.1 pushed to production",
            "stderr": "",
            "duration_ms": 4500,
        }
        rules = {
            "exit_code": {"equals": 0},
            "stdout": {"contains": "Deploy successful"},
            "stdout": {"matches": r"version \d+\.\d+\.\d+"},
            "stderr": {"empty": True},
            "duration_ms": {"lt": 60000},
        }
        r = validate(result, rules)
        assert r.passed is True

    def test_deploy_with_warning_allowed(self):
        """stderr has warnings but non-fatal — should still pass or fail
        based on rules. Here we allow warnings."""
        result = {
            "exit_code": 0,
            "stdout": "Deploy successful",
            "stderr": "WARNING: old config format detected, auto-migrated",
            "duration_ms": 4500,
        }
        # Only check exit_code and stdout — don't enforce empty stderr
        rules = {
            "exit_code": {"equals": 0},
            "stdout": {"contains": "Deploy successful"},
            "duration_ms": {"lt": 60000},
        }
        r = validate(result, rules)
        assert r.passed is True

    def test_file_write_success(self):
        result = {
            "exit_code": 0,
            "result": {"bytes_written": 1024, "path": "/tmp/output.json"},
            "stderr": "",
            "duration_ms": 8,
        }
        rules = {
            "exit_code": {"equals": 0},
            "result.bytes_written": {"gt": 0},
            "result.bytes_written": {"lt": 10_000_000},
            "stderr": {"empty": True},
        }
        r = validate(result, rules)
        assert r.passed is True

    def test_file_write_zero_bytes_fails(self):
        result = {
            "exit_code": 0,
            "result": {"bytes_written": 0},
            "stderr": "",
        }
        rules = {
            "exit_code": {"equals": 0},
            "result.bytes_written": {"gt": 0},
        }
        r = validate(result, rules)
        assert r.passed is False


@pytest.fixture(autouse=True)
def _verify_report_structure():
    """Every test should produce a valid ValidationReport."""
    yield
    # Nothing to verify per-test — the assertion in validate() covers it