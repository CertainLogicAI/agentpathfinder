# Build Spec: Email Validator Module

## Goal
Create a Python module `email_validator.py` that validates email addresses.

## Requirements
1. Function `validate_email(email: str) -> bool`
2. Check format using regex (RFC 5322 simplified)
3. Check domain has MX record (optional, with timeout)
4. Type hints and docstrings
5. Unit tests in `test_email_validator.py`

## Files to Create
- `email_validator.py` — main module
- `test_email_validator.py` — pytest tests

## Testing Criteria
- `validate_email("user@example.com")` → True
- `validate_email("invalid")` → False
- `validate_email("@example.com")` → False
- All pytest tests pass

## Implementation Notes
- Use `re` module for regex
- Use `dns.resolver` for MX lookup (optional)
- Handle exceptions gracefully
