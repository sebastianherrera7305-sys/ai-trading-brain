"""Make the research_platform package importable when running pytest from
the research_platform/ directory without installation."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
