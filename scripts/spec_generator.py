#!/usr/bin/env python3
"""
Spec Generator — Auto-write build specs from GBrain product knowledge.

This tool queries GBrain for product info and generates a build spec
automatically. It ensures every build aligns with CertainLogic's
business requirements and brand voice.

USAGE:
    # Generate a spec for a new feature
    python3 spec_generator.py --feature "SSO Integration" --type auth
    
    # Generate spec with business constraints from GBrain
    python3 spec_generator.py --feature "Webhook Notifications" --type integration
    
    # Output to file
    python3 spec_generator.py --feature "Team Dashboard" --team --output dashboard_spec.md

Types: auth | integration | ui | api | security | performance
"""

import argparse
import json
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

BRAIN_API = "http://127.0.0.1:8000"


class SpecGenerator:
    """Generates build specs using GBrain as source of truth."""
    
    def __init__(self, brain_url: str = BRAIN_API):
        self.brain_url = brain_url
    
    def query_brain(self, query: str, top_k: int = 5) -> List[Dict]:
        """Query GBrain for facts."""
        try:
            r = requests.post(
                f"{self.brain_url}/query",
                json={"query": query, "top_k": top_k},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("results", [])
        except Exception:
            pass
        return []
    
    def get_product_info(self) -> Dict[str, str]:
        """Extract product context from GBrain."""
        info = {
            "name": "AgentPathfinder",
            "tagline": "",
            "pricing_free": "",
            "pricing_pro": "",
            "pricing_business": "",
            "security_model": "",
            "brand_voice": "",
        }
        
        # Query each fact
        queries = {
            "name": "AgentPathfinder name",
            "tagline": "AgentPathfinder tagline",
            "pricing_free": "free tier features pricing",
            "pricing_pro": "pro tier pricing",
            "pricing_business": "business tier pricing",
            "security_model": "security model tamper",
            "brand_voice": "X voice brand tone",
        }
        
        for key, query in queries.items():
            results = self.query_brain(query, top_k=1)
            if results:
                val = results[0].get("value", "")
                if isinstance(val, dict):
                    val = val.get("value", "")
                info[key] = str(val)[:200]
        
        return info
    
    def generate(self, feature: str, feature_type: str, team_needs: bool = False) -> str:
        """Generate a complete build spec."""
        ctx = self.get_product_info()
        
        # Template based on feature type
        templates = {
            "auth": self._auth_spec,
            "integration": self._integration_spec,
            "ui": self._ui_spec,
            "api": self._api_spec,
            "security": self._security_spec,
            "performance": self._performance_spec,
        }
        
        template_fn = templates.get(feature_type, self._generic_spec)
        return template_fn(feature, ctx, team_needs)
    
    def _header(self, feature: str, ctx: Dict) -> str:
        return f"""# Build Spec: {feature}

## Product Context
- **Product**: {ctx.get('name', 'AgentPathfinder')}
- **Tagline**: {ctx.get('tagline', 'Deterministic AI you can trust')}
- **Brand Voice**: {ctx.get('brand_voice', 'Direct, conversational, indie builder')}

## Pricing Impact
"""

    def _pricing_section(self, ctx: Dict, team: bool = False) -> str:
        lines = ["- **Free tier**: " + ctx.get('pricing_free', 'Unlimited tasks, CLI, audit trails')[:80]]
        if team:
            lines.append("- **Business tier**: " + ctx.get('pricing_business', 'Team features $79/mo')[:80])
        else:
            lines.append("- **Pro tier**: " + ctx.get('pricing_pro', 'Dashboard $29/mo')[:80])
        lines.append("")
        return "\n".join(lines)
    
    def _security_section(self, ctx: Dict) -> str:
        return f"""## Security Requirements
- **Model**: {ctx.get('security_model', 'Tamper-evident, local-first')[:120]}
- All changes must be HMAC-SHA256 auditable
- Never store API keys in repository
- Follow principle: feature-gate, don't usage-gate

"""
    
    def _testing_section(self, feature: str) -> str:
        return f"""## Testing Criteria
- [ ] Feature works in Free tier (unlimited usage)
- [ ] Feature unlocks in correct paid tier
- [ ] Audit trail captures every state change
- [ ] No token key leakage in code or logs
- [ ] Responsive design if UI component
- [ ] Error handling for all edge cases

## Build Steps
1. Design the feature architecture
2. Implement core functionality
3. Add audit trail integration
4. Write unit tests (pytest)
5. Write integration tests
6. Verify token-safe (no secrets leaked)
7. Manual QA checklist

## Notes
- **Auto-generated** by CertainLogic Spec Generator
- **GBrain context** ensures alignment with business requirements
- **DO NOT push to GitHub** without Anton's explicit approval
- Date: {datetime.now().strftime("%Y-%m-%d %H:%M UTC")}
"""
    
    def _generic_spec(self, feature: str, ctx: Dict, team: bool) -> str:
        return self._header(feature, ctx) + self._pricing_section(ctx, team) + self._security_section(ctx) + f"""
## Feature: {feature}
### Goal
Implement {feature} for AgentPathfinder.

### Requirements
- Must work in local-first mode (no SaaS dependency for free tier)
- Must have clear upgrade path to paid tiers
- Must integrate with existing audit trail system

### Key Questions
1. What tier should this feature live in?
2. Does it require remote vault (Business tier) or local only?
3. How does this feature differentiate from competitors?

{self._testing_section(feature)}"""
    
    def _auth_spec(self, feature: str, ctx: Dict, team: bool) -> str:
        return self._header(feature, ctx) + self._pricing_section(ctx, team) + self._security_section(ctx) + f"""
## Feature: {feature} (Authentication)
### Goal
Secure authentication system for AgentPathfinder.

### Requirements
- Password hashing: bcrypt (never plaintext)
- Session tokens: JWT with expiration
- Role-based access: Free=single user, Pro=multi-agent, Business=team admin
- SSO integration: OAuth2 for Enterprise tier

### Tier Logic
- Free: Local auth only, single user
- Pro: Basic auth + API keys
- Business: Team invites + user management
- Enterprise: SSO/SAML integration

### Security
- Password minimum: 12 characters
- Rate limiting: 5 attempts per minute
- Audit log: Every login, logout, permission change
- **NEVER commit auth secrets to git**

{self._testing_section(feature)}"""
    
    def _integration_spec(self, feature: str, ctx: Dict, team: bool) -> str:
        return self._header(feature, ctx) + self._pricing_section(ctx, team) + self._security_section(ctx) + f"""
## Feature: {feature} (Integration)
### Goal
External service integration for AgentPathfinder.

### Requirements
- Webhook support: Inbound + outbound
- API rate limiting: Respect third-party limits
- Retry logic: Exponential backoff with max retries
- Error isolation: One failing webhook doesn't break others

### Tier Logic
- Free: Manual webhook config (1 active)
- Pro: Dashboard + 10 active webhooks
- Business: 50 webhooks + shared team configs
- Enterprise: Unlimited + custom integrations

### Security
- Webhook signatures: HMAC-SHA256 verification
- API keys: Stored in remote vault (Business+) or local keychain
- **Never log webhook payloads containing PII**

{self._testing_section(feature)}"""
    
    def _ui_spec(self, feature: str, ctx: Dict, team: bool) -> str:
        return self._header(feature, ctx) + self._pricing_section(ctx, team) + self._security_section(ctx) + f"""
## Feature: {feature} (UI Component)
### Goal
User interface component for AgentPathfinder.

### Requirements
- Responsive design: Mobile-first CSS
- Navy #0F1724 + Electric Blue #2563EB color scheme
- Accessible: WCAG 2.1 AA compliance
- Performance: Load time < 2s on 3G

### Components
- Dashboard tab: Real-time task/agent status
- Settings: Tier management + billing info
- Audit view: Blockchain-style verification UI

### Tier Logic
- Free: CLI only (no web UI)
- Pro: Dashboard with localhost binding
- Business: Team-specific views + shared workspace
- Enterprise: Custom branding + white-label

{self._testing_section(feature)}"""
    
    def _api_spec(self, feature: str, ctx: Dict, team: bool) -> str:
        return self._header(feature, ctx) + self._pricing_section(ctx, team) + self._security_section(ctx) + f"""
## Feature: {feature} (API Extension)
### Goal
REST/JSON API extension for AgentPathfinder.

### Requirements
- OpenAPI 3.0 spec
- Versioning: /v1/ prefix
- Authentication: API key (Pro+) or token-based
- Rate limiting: 100 req/min Free, 1000/mo Pro, custom Business

### Endpoints
- GET /v1/tasks — List tasks (paginated)
- POST /v1/tasks — Create task
- GET /v1/tasks/{id}/audit — Full audit trail
- POST /v1/tasks/{id}/verify — Verify cryptographically

### Tier Logic
- Free: Read-only API, 100 req/min
- Pro: Full CRUD + exports
- Business: Team-scoped endpoints
- Enterprise: Custom endpoints + SLA

{self._testing_section(feature)}"""
    
    def _security_spec(self, feature: str, ctx: Dict, team: bool) -> str:
        return self._header(feature, ctx) + self._pricing_section(ctx, team) + self._security_section(ctx) + f"""
## Feature: {feature} (Security Hardening)
### Goal
Enhance security of AgentPathfinder.

### Requirements
- HMAC-SHA256 on all state transitions
- Audit log integrity: Chain of hashes
- Token rotation: Automatic key refresh
- Vulnerability scanning: Automated dependency checks

### Deliverables
- Security audit report
- Updated SAFETY.md
- Threat model documentation
- Penetration test results (if applicable)

### Tier Logic
- All tiers: Same security level (non-negotiable)
- Pro+: Signed audit certificates
- Enterprise: SOC-2 compliance documentation

{self._testing_section(feature)}"""
    
    def _performance_spec(self, feature: str, ctx: Dict, team: bool) -> str:
        return self._header(feature, ctx) + self._pricing_section(ctx, team) + self._security_section(ctx) + f"""
## Feature: {feature} (Performance Optimization)
### Goal
Optimize AgentPathfinder for speed and scale.

### Requirements
- Task creation: < 10ms
- Audit verification: < 50ms
- Concurrent agents: 1000+ simultaneous
- Memory footprint: < 50MB baseline

### Benchmarks
- Baseline: Current performance metrics
- Target: 10x improvement on hot paths
- Stress test: 10K tasks, 100 agents, 1hr run

### Deliverables
- Performance regression test suite
- Flame graphs of hot paths
- Optimization PR with before/after numbers

{self._testing_section(feature)}"""


def main():
    parser = argparse.ArgumentParser(description="Spec Generator — GBrain-powered build specs")
    parser.add_argument("--feature", required=True, help="Feature name")
    parser.add_argument("--type", required=True, 
                       choices=["auth", "integration", "ui", "api", "security", "performance"],
                       help="Feature type")
    parser.add_argument("--team", action="store_true", help="Team/Business tier context")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    parser.add_argument("--brain-url", default=BRAIN_API, help="Brain API URL")
    args = parser.parse_args()
    
    gen = SpecGenerator(brain_url=args.brain_url)
    spec = gen.generate(args.feature, args.type, args.team)
    
    if args.output:
        Path(args.output).write_text(spec)
        print(f"✅ Spec written: {args.output}")
        print(f"   Type: {args.type}")
        print(f"   Feature: {args.feature}")
        print(f"   Tiers: {'Team/Business' if args.team else 'Individual/Pro'}")
    else:
        print(spec)


if __name__ == "__main__":
    main()
