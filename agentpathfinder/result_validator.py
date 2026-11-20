"""AgentPathfinder — Deterministic result validation engine.

Checks tool call results against rule-based expectations defined in the
step schema. Every check is deterministic — no AI, no model-as-judge.
Pass/fail results are logged as VALIDATION_PASS / VALIDATION_FAIL audit events.

Check types: equals, contains, excludes, empty, not_empty, matches, lt, gt.
Combinators: and, or, not.
"""

import re
from typing import Any, Dict, List, Optional, Union

_MISSING = object()


class ValidationReport:
    """Structured result of a validation run."""
    __slots__ = ("passed", "checks", "failed_checks")

    def __init__(self, passed: bool, checks: List[Dict[str, Any]],
                 failed_checks: List[str]):
        self.passed = passed
        self.checks = checks
        self.failed_checks = failed_checks

    def to_dict(self) -> Dict[str, Any]:
        return {"passed": self.passed, "checks": self.checks,
                "failed_checks": self.failed_checks}

    def __repr__(self) -> str:
        return f"<ValidationReport {'PASS' if self.passed else 'FAIL'} ({len(self.failed_checks)} failures)>"


def _resolve_field(data: Dict[str, Any], field_path: str) -> Any:
    """Resolve a dotted field path against a dict."""
    parts = field_path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part, _MISSING)
        else:
            return _MISSING
        if current is _MISSING:
            return _MISSING
    return current


# Check implementations — each returns {"passed": bool, "detail": str}

def _check_equals(value: Any, expect: Any) -> Dict[str, Any]:
    passed = value == expect
    return {"passed": passed, "detail": f"expected == {expect!r}, got {value!r}"}


def _check_contains(value: Any, substring: str) -> Dict[str, Any]:
    if not isinstance(value, str):
        return {"passed": False, "detail": f"not a string (type={type(value).__name__})"}
    passed = substring in value
    return {"passed": passed, "detail": f"expected contains {substring!r}" if not passed else f"found {substring!r}"}


def _check_excludes(value: Any, substring: str) -> Dict[str, Any]:
    if not isinstance(value, str):
        return {"passed": True, "detail": "not a string — skip"}
    passed = substring not in value
    return {"passed": passed, "detail": f"expected excludes {substring!r}" if not passed else f"excluded {substring!r}"}


def _check_empty(value: Any, _arg: Any = None) -> Dict[str, Any]:
    if isinstance(value, str):
        passed = len(value) == 0
    elif isinstance(value, (list, dict, tuple)):
        passed = len(value) == 0
    elif value is None:
        passed = True
    else:
        passed = False
    return {"passed": passed, "detail": f"expected empty, got {type(value).__name__}({value!r})" if not passed else "is empty"}


def _check_not_empty(value: Any, _arg: Any = None) -> Dict[str, Any]:
    if isinstance(value, str):
        passed = len(value) > 0
    elif isinstance(value, (list, dict, tuple)):
        passed = len(value) > 0
    elif value is None:
        passed = False
    else:
        passed = True
    return {"passed": passed, "detail": "expected non-empty, got empty" if not passed else "is non-empty"}


def _check_matches(value: Any, pattern: str) -> Dict[str, Any]:
    if not isinstance(value, str):
        return {"passed": False, "detail": f"not a string (type={type(value).__name__})"}
    try:
        compiled = re.compile(pattern)
        passed = bool(compiled.search(value))
    except re.error as e:
        return {"passed": False, "detail": f"invalid regex: {e}"}
    return {"passed": passed, "detail": f"pattern {pattern!r} {'matched' if passed else 'not matched'}"}


def _check_lt(value: Any, threshold: Union[int, float]) -> Dict[str, Any]:
    if not isinstance(value, (int, float)):
        return {"passed": False, "detail": f"not numeric (type={type(value).__name__})"}
    return {"passed": value < threshold, "detail": f"expected < {threshold}, got {value}"}


def _check_gt(value: Any, threshold: Union[int, float]) -> Dict[str, Any]:
    if not isinstance(value, (int, float)):
        return {"passed": False, "detail": f"not numeric (type={type(value).__name__})"}
    return {"passed": value > threshold, "detail": f"expected > {threshold}, got {value}"}


_CHECKERS = {
    "equals": _check_equals, "contains": _check_contains,
    "excludes": _check_excludes, "empty": _check_empty,
    "not_empty": _check_not_empty, "matches": _check_matches,
    "lt": _check_lt, "gt": _check_gt,
}


# Combinators — return single aggregated result with nested sub_checks

def _check_and(rules: List[Dict[str, Any]], resolved_value: Any,
               field_path: str) -> Dict[str, Any]:
    sub_checks = []
    any_failed = False
    for rule in rules:
        sr = _run_checks_on_field(resolved_value, rule, field_path)
        sub_checks.extend(sr)
        if any(not r.get("passed") for r in sr):
            any_failed = True
    return {"field": field_path, "check": "and", "passed": not any_failed,
            "detail": f"{len(rules)} sub-rule(s), {'all passed' if not any_failed else 'some failed'}",
            "sub_checks": sub_checks}


def _check_or(rules: List[Dict[str, Any]], resolved_value: Any,
              field_path: str) -> Dict[str, Any]:
    sub_checks = []
    any_passed = False
    for rule in rules:
        sr = _run_checks_on_field(resolved_value, rule, field_path)
        sub_checks.extend(sr)
        if sr and all(r.get("passed") for r in sr):
            any_passed = True
    return {"field": field_path, "check": "or", "passed": any_passed,
            "detail": f"{len(rules)} option(s), {'at least one passed' if any_passed else 'none passed'}",
            "sub_checks": sub_checks}


def _check_not(rule: Dict[str, Any], resolved_value: Any,
               field_path: str) -> Dict[str, Any]:
    sr = _run_checks_on_field(resolved_value, rule, field_path)
    sub_passed = all(r.get("passed") for r in sr)
    return {"field": field_path, "check": "not", "passed": not sub_passed,
            "detail": f"inverted: sub-rule {'passed' if sub_passed else 'failed'}",
            "sub_checks": sr}


_COMBINATORS = {"and": _check_and, "or": _check_or, "not": _check_not}


def _run_checks_on_field(value: Any, rules: Dict[str, Any],
                         field_path: str) -> List[Dict[str, Any]]:
    results = []
    for check_type, arg in rules.items():
        if check_type in _COMBINATORS:
            handler = _COMBINATORS[check_type]
            results.append(handler(arg, value, field_path))
            continue
        if check_type in _CHECKERS:
            cr = _CHECKERS[check_type](value, arg)
            results.append({"field": field_path, "check": check_type,
                           "passed": cr["passed"], "detail": cr["detail"]})
            continue
        results.append({"field": field_path, "check": check_type,
                       "passed": False, "detail": f"unknown check type: {check_type}"})
    return results


def validate(result: Dict[str, Any], rules: Dict[str, Any]) -> ValidationReport:
    """Validate a tool result against a set of rules.

    Parameters
    ----------
    result : dict — Flat result with exit_code, stdout, stderr, duration_ms, etc.
    rules : dict — {"exit_code": {"equals": 0}, "stdout": {"contains": "passed"}}

    Returns ValidationReport with passed (bool), checks (list), failed_checks (list).
    """
    all_checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    for field_path, field_rules in rules.items():
        value = _resolve_field(result, field_path)
        if value is _MISSING:
            all_checks.append({"field": field_path, "check": "_exists",
                              "passed": False,
                              "detail": f"field {field_path!r} not found in result"})
            failed_checks.append(f"field '{field_path}' missing from result")
            continue

        field_results = _run_checks_on_field(value, field_rules, field_path)
        all_checks.extend(field_results)
        for cr in field_results:
            if not cr["passed"]:
                failed_checks.append(f"'{field_path}' {cr['check']}: {cr['detail']}")

    return ValidationReport(passed=len(failed_checks) == 0,
                           checks=all_checks, failed_checks=failed_checks)


def rules_from_step(step: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Extract validation rules from a step dict, or None if absent."""
    if not isinstance(step, dict):
        return None
    raw = step.get("validation")
    return raw if isinstance(raw, dict) else None