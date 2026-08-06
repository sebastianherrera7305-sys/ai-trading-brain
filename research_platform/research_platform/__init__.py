"""research_platform — independent quantitative research framework.

A zero-platform, numpy-only framework for reproducible quantitative
experiments: immutable dataset registry, experiment registry, a
config-driven deterministic runner, durable result storage, a comparison
engine, and a reproducibility engine (`research run UUID`).

The framework is deliberately independent of the AI Trading Brain
production platform. Integration, if any, happens later through ADRs.

Runtime dependencies: numpy only. Everything else is the Python standard
library.
"""

__version__ = "0.1.0"
