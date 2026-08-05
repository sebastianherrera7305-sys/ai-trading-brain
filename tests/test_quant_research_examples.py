"""Regression tests for the docs/examples/ research walkthroughs.

Every python code block in docs/examples/*.md is executed in order
per file (shared namespace per file, as written). This makes the
examples executable documentation: the assert statements inside them
are the regression contract.

Additionally, this test enforces that every public function of the
package appears in at least one example — the Phase 1 acceptance
criterion "each public function demonstrated in a real-world workflow".
"""

import re
from pathlib import Path

import pytest

from quant_research import core, probability, resampling, statistics, timeseries

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "docs" / "examples"
FENCE_RE = re.compile(r"```python\n(.*?)```", re.S)


def _example_files():
    return sorted(EXAMPLES_DIR.glob("*.md"))


@pytest.mark.parametrize(
    "path",
    [p for p in _example_files() if p.name != "README.md"],
    ids=lambda p: p.name,
)
def test_example_code_blocks_execute(path):
    text = path.read_text()
    blocks = FENCE_RE.findall(text)
    assert blocks, f"{path.name}: no python code blocks found"
    namespace = {}
    for i, block in enumerate(blocks):
        exec(compile(block, f"{path.name} block {i}", "exec"), namespace)


def test_every_public_function_demonstrated_in_examples():
    source = "\n".join(p.read_text() for p in _example_files())
    for module in (core, statistics, probability, resampling, timeseries):
        for name in module.__all__:
            assert re.search(rf"\b{re.escape(name)}\b", source), (
                f"{module.__name__}.{name} is not demonstrated in any "
                f"docs/examples/ walkthrough"
            )
