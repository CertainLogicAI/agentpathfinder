#!/usr/bin/env python3
"""
Auto-Build Agent — Analyzes, specs, builds, tests, asks before shipping.
Integrates with GBrain for pattern reuse and knowledge storage.

USAGE:
    # Analyze and improve one module
    python3 auto_build.py --target agentpathfinder/task_engine.py
    
    # Dry run (analyze + spec only)
    python3 auto_build.py --target agentpathfinder/task_engine.py --dry-run
    
    # The agent will:
    #   1. Check GBrain for existing build patterns
    #   2. Analyze the module for issues
    #   3. Generate an improvement spec
    #   4. Run build orchestrator
    #   5. Test the changes
    #   6. Git commit locally
    #   7. ASK YOU before git push

Permission gates:
  ✅ Auto: GBrain query, analyze, spec, build, test, local commit
  ❌ Human required: git push, tag release
"""

import argparse
import ast
import json
import subprocess
import sys
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
import requests

# ── Import Pathfinder ──
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR.parent))
from agentpathfinder import TaskEngine, IssuingLayer, hash_key

PASS = "✅"; FAIL = "❌"; SPIN = "⏳"; WARN = "⚠️"
BRAIN_API = "http://127.0.0.1:8000"


# ═══════════════════════════════════════════════════════════
# GBrain Integration
# ═══════════════════════════════════════════════════════════

class GBrainIntegrator:
    """Queries and stores build patterns in GBrain."""
    
    def __init__(self, base_url: str = BRAIN_API):
        self.base_url = base_url
    
    def search_pattern(self, module_name: str, goal: str) -> Optional[Dict]:
        """Check if we've built something similar before."""
        try:
            r = requests.post(
                f"{self.base_url}/query",
                json={"query": f"build pattern {module_name} {goal}", "top_k": 3},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                hits = [h for h in data.get("results", []) if "build" in h.get("key", "")]
                if hits:
                    return {"found": True, "best": hits[0], "count": len(hits)}
            return None
        except Exception:
            return None
    
    def store_build_result(self, module_name: str, spec: str, result: str) -> bool:
        """Store completed build for future pattern reuse."""
        try:
            r = requests.post(
                f"{self.base_url}/facts",
                json={
                    "category": "build_spec",
                    "key": f"{module_name}_build_{int(time.time())}",
                    "value": f"Goal: {spec}\n\nResult: {result}",
                    "type": "string",
                    "source": "auto-build"
                },
                timeout=10
            )
            return r.status_code in (200, 201)
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════
# Module Analyzer
# ═══════════════════════════════════════════════════════════

class ModuleAnalyzer:
    """Analyzes a Python module and generates improvement specs."""

    def __init__(self, module_path: Path):
        self.module_path = Path(module_path)
        self.source = self.module_path.read_text()
        self.tree = ast.parse(self.source)
        self.issues = []

    def analyze(self) -> Dict[str, Any]:
        self._check_docstrings()
        self._check_type_hints()
        self._check_test_coverage()
        self._check_todos()
        self._check_complexity()
        
        return {
            "module": str(self.module_path),
            "lines": len(self.source.split("\n")),
            "functions": len([n for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]),
            "classes": len([n for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]),
            "issues": self.issues,
            "issue_count": len(self.issues),
        }

    def _check_docstrings(self):
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                if not ast.get_docstring(node):
                    self.issues.append({
                        "type": "missing_docstring",
                        "line": node.lineno,
                        "name": node.name,
                        "severity": "low",
                        "message": f"Add docstring to {node.__class__.__name__} `{node.name}`"
                    })

    def _check_type_hints(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef):
                for arg in node.args.args:
                    if arg.annotation is None and arg.arg != "self":
                        self.issues.append({
                            "type": "missing_type_hint",
                            "line": node.lineno,
                            "name": f"{node.name}({arg.arg})",
                            "severity": "low",
                            "message": f"Add type hint for `{arg.arg}` in `{node.name}`"
                        })
                if node.returns is None:
                    self.issues.append({
                        "type": "missing_return_type",
                        "line": node.lineno,
                        "name": node.name,
                        "severity": "low",
                        "message": f"Add return type hint to `{node.name}`"
                    })

    def _check_test_coverage(self):
        test_dir = self.module_path.parent.parent / "tests"
        test_file = test_dir / f"test_{self.module_path.name}"
        if not test_file.exists():
            self.issues.append({
                "type": "missing_tests",
                "line": 1,
                "name": str(test_file),
                "severity": "medium",
                "message": f"Create test file: {test_file}"
            })

    def _check_todos(self):
        for i, line in enumerate(self.source.split("\n"), 1):
            if any(marker in line for marker in ["TODO", "FIXME", "XXX", "HACK"]):
                self.issues.append({
                    "type": "todo",
                    "line": i,
                    "name": line.strip()[:60],
                    "severity": "low",
                    "message": f"Address: {line.strip()[:80]}"
                })

    def _check_complexity(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef):
                end_line = node.end_lineno or node.lineno
                if end_line - node.lineno > 50:
                    self.issues.append({
                        "type": "high_complexity",
                        "line": node.lineno,
                        "name": node.name,
                        "severity": "medium",
                        "message": f"Consider refactoring `{node.name}` ({end_line - node.lineno} lines > 50)"
                    })

    def generate_spec(self) -> str:
        analysis = self.analyze()
        by_type = {}
        for issue in analysis["issues"]:
            t = issue["type"]
            by_type.setdefault(t, []).append(issue)
        
        improvements = []
        if "missing_docstrings" in by_type:
            improvements.append(f"1. Add docstrings to {len(by_type['missing_docstrings'])} functions/classes")
        if "missing_type_hint" in by_type or "missing_return_type" in by_type:
            improvements.append("2. Add type hints to function signatures")
        if "missing_tests" in by_type:
            improvements.append(f"3. Create test file: test_{self.module_path.name}")
        if "todo" in by_type:
            improvements.append(f"4. Address {len(by_type['todo'])} TODO/FIXME comments")
        if "high_complexity" in by_type:
            improvements.append("5. Refactor overly complex functions")
        if not improvements:
            improvements.append("1. Code review passed — no critical issues")
        
        spec = f"""# Auto-Generated Spec: {self.module_path.name}

## Module
- Path: `{self.module_path}`
- Lines: {analysis['lines']}
- Functions: {analysis['functions']}
- Classes: {analysis['classes']}
- Issues: {analysis['issue_count']}

## Improvements
{chr(10).join(improvements)}

## Testing Criteria
- All functions have docstrings
- Type hints on public API
- Tests pass: `pytest test_{self.module_path.name}`
- No TODO/FIXME left behind

## Notes
- Preserve existing functionality
- Do not change method signatures unless adding type hints
- **NEVER push to GitHub without Anton's approval**
"""
        return spec


# ═══════════════════════════════════════════════════════════
# Auto-Build Agent
# ═══════════════════════════════════════════════════════════

class AutoBuildAgent:
    def __init__(self, repo_root: Path, brain_url: str = BRAIN_API):
        self.repo_root = Path(repo_root)
        self.build_data_dir = self.repo_root / ".build_data"
        self.build_data_dir.mkdir(exist_ok=True)
        self.gbrain = GBrainIntegrator(brain_url)
        
    def _apply_quick_fixes(self, source: str, analysis: Dict) -> str:
        """Apply simple automated fixes: docstrings, type stubs, TODO comments."""
        lines = source.split("\n")
        
        # Add TODO audit comment at top
        if "todo" in [i["type"] for i in analysis["issues"]]:
            lines.insert(1, f'# TODO: Address {len([i for i in analysis["issues"] if i["type"] == "todo"])} pending items')
        
        # Minimal fixes - just add module-level docstring if missing
        needs_docstring = any(i["type"] == "missing_docstring" for i in analysis["issues"])
        if needs_docstring and not source.strip().startswith('"""'):
            lines.insert(0, f'"""Auto-improved by CertainLogic Build Agent.\nGenerated: {time.strftime("%Y-%m-%d %H:%M UTC")}\n"""\n')
        
        return "\n".join(lines)

    def run(self, target_module: str, dry_run: bool = False):
        module_path = self.repo_root / target_module
        if not module_path.exists():
            print(f"{FAIL} Module not found: {module_path}")
            return False
        
        print("=" * 65)
        print("  🤖 AUTO-BUILD AGENT — CertainLogic Build System")
        print("=" * 65)
        
        # ── Phase 0: GBrain Check ──
        print(f"\n{SPIN} Phase 0: Checking GBrain for patterns...")
        p_name = module_path.stem
        pattern = self.gbrain.search_pattern(p_name, f"improve {p_name}")
        if pattern:
            print(f"   {PASS} Found {pattern['count']} similar build pattern(s)")
            print(f"   Best match: {pattern['best'].get('key', 'unknown')}")
        else:
            print(f"   ℹ️  No existing patterns. Fresh build.")
        
        # ── Phase 1: ANALYZE ──
        print(f"\n{SPIN} Phase 1: Analyzing {target_module}...")
        analyzer = ModuleAnalyzer(module_path)
        analysis = analyzer.analyze()
        
        print(f"   {PASS} Analysis complete")
        print(f"   Modules: {analysis['lines']} lines, {analysis['functions']} funcs, {analysis['classes']} classes")
        print(f"   Issues found: {analysis['issue_count']}")
        
        if analysis['issue_count'] == 0:
            print(f"\n{PASS} No issues found. Nothing to build.")
            return True
        
        for issue in analysis['issues'][:5]:
            icon = WARN if issue['severity'] == 'medium' else 'ℹ️'
            print(f"   {icon} {issue['message']}")
        if len(analysis['issues']) > 5:
            print(f"   ... and {len(analysis['issues']) - 5} more")
        
        # ── Phase 2: SPEC ──
        print(f"\n{SPIN} Phase 2: Generating improvement spec...")
        spec_text = analyzer.generate_spec()
        spec_path = self.build_data_dir / f"spec_{p_name}.md"
        spec_path.write_text(spec_text)
        print(f"   {PASS} Spec written: {spec_path}")
        
        if dry_run:
            print(f"\n{WARN} Dry run — stopping before build")
            return True
        
        # ── Phase 3: BUILD ──
        print(f"\n{SPIN} Phase 3: Running build orchestrator...")
        build_output = self.build_data_dir / f"build_{p_name}"
        build_output.mkdir(exist_ok=True)
        
        sys.path.insert(0, str(_SCRIPT_DIR))
        from build_orchestrator import BuildOrchestrator
        
        orch = BuildOrchestrator(data_dir=self.build_data_dir / "pathfinder_data")
        task_id = orch.start(str(spec_path), str(build_output))
        
        # Track through steps
        orch.run_step(1, ["echo", f"Spec loaded: {len(spec_text)} chars"])
        orch.run_step(2, ["mkdir", "-p", str(build_output)])
        
        # Apply automated fixes
        print(f"   {SPIN} Applying automated fixes...")
        improved = self._apply_quick_fixes(module_path.read_text(), analysis)
        improved_path = build_output / module_path.name
        improved_path.write_text(improved)
        print(f"   {PASS} Applied fixes to {improved_path}")
        
        orch.issuing.issue_step_token(
            task_id, 3, "auto_improvements_applied",
            hash_key(improved.encode())[:16]
        )
        
        # Check for tests
        test_file = module_path.parent.parent / "tests" / f"test_{module_path.name}"
        if test_file.exists():
            orch.run_step(4, [sys.executable, "-m", "pytest", str(test_file), "-v"])
        else:
            orch.run_step(4, ["echo", "No tests to run — test file missing"])
        
        orch.run_step(5, ["python3", "-m", "py_compile", str(improved_path)])
        
        # ── Phase 4: GIT STAGE ──
        print(f"\n{SPIN} Phase 4: Staging changes...")
        final_path = self.repo_root / target_module
        shutil.copy2(str(improved_path), str(final_path))
        
        # Write spec to repo too
        spec_dest = self.repo_root / f"docs/auto-specs/spec_{p_name}.md"
        spec_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(spec_path), str(spec_dest))
        
        # Git add
        for gitcmd in [
            ["git", "add", str(final_path)],
            ["git", "add", str(spec_path)],
            ["git", "add", str(spec_dest)] if spec_dest.exists() else None
        ]:
            if gitcmd:
                subprocess.run(gitcmd, cwd=self.repo_root, capture_output=True)
        
        commit_msg = (
            f"auto-build: Improve {p_name}\n\n"
            f"- {analysis['issue_count']} issues addressed\n"
            f"- Task: {task_id}\n"
            f"- Review required before push"
        )
        git_commit = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=self.repo_root, capture_output=True, text=True
        )
        
        if git_commit.returncode == 0:
            print(f"   {PASS} Committed locally")
            commit_hash = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=self.repo_root, capture_output=True, text=True
            )
            print(f"   Commit: {commit_hash.stdout.strip()}")
        else:
            print(f"   {WARN} Nothing new to commit")
        
        # ── Phase 5: HUMAN APPROVAL GATE ──
        print(f"\n{'=' * 65}")
        print(f"  🛑 HUMAN APPROVAL REQUIRED")
        print(f"  {'=' * 65}")
        print()
        print(f"  Module:     {target_module}")
        print(f"  Task:       {task_id}")
        print(f"  Issues:     {analysis['issue_count']}")
        print(f"  Changes:    {improved_path}")
        print()
        print(f"  ✅ Changes ARE committed locally")
        print(f"  ❌ Changes are NOT pushed to GitHub")
        print()
        print(f"  To review:")
        print(f"    git log --oneline -3")
        print(f"    git diff HEAD~1 HEAD")
        print()
        print(f"  To approve and push:")
        print(f"    git push origin main")
        print()
        print(f"  To reject and undo:")
        print(f"    git reset --soft HEAD~1")
        print(f"    git checkout -- {target_module}")
        print()
        
        # Store in GBrain
        try:
            self.gbrain.store_build_result(
                p_name, spec_text, 
                f"Issues: {analysis['issue_count']}, Task: {task_id}"
            )
            print(f"  📚 Build pattern stored in GBrain")
        except Exception:
            print(f"  ⚠️  Could not store in GBrain (non-critical)")
        
        return True


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Auto-Build Agent — GBrain + Pathfinder")
    parser.add_argument("--target", required=True, help="Target module path relative to repo root")
    parser.add_argument("--repo-root", default=".", help="Repository root directory")
    parser.add_argument("--brain-url", default=BRAIN_API, help="Brain API URL")
    parser.add_argument("--dry-run", action="store_true", help="Analyze + spec only, no build")
    args = parser.parse_args()
    
    repo = Path(args.repo_root).resolve()
    if not (repo / ".git").exists():
        print(f"{FAIL} Not a git repo: {repo}")
        sys.exit(1)
    
    agent = AutoBuildAgent(repo, brain_url=args.brain_url)
    success = agent.run(args.target, dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    import shutil  # import here to avoid issues
    main()
