"""`python3 -m trading_brain` runs the synthetic demos for each module."""

from .backtest import run_demo as backtest_demo
from .displacement import run_demo as displacement_demo
from .fair_value_gap import run_demo as fair_value_gap_demo
from .liquidity import run_demo as liquidity_demo
from .market_structure import run_demo as market_structure_demo
from .risk import run_demo as risk_demo
from .scoring import run_demo as scoring_demo
from .sessions import run_demo as sessions_demo

if __name__ == "__main__":
    print("######## MARKET STRUCTURE ########\n")
    market_structure_demo()
    print("\n\n######## LIQUIDITY ########\n")
    liquidity_demo()
    print("\n\n######## DISPLACEMENT ########\n")
    displacement_demo()
    print("\n\n######## SESSIONS ########\n")
    sessions_demo()
    print("\n\n######## FAIR VALUE GAP ########\n")
    fair_value_gap_demo()
    print("\n\n######## RISK ########\n")
    risk_demo()
    print("\n\n######## SCORING ########\n")
    scoring_demo()
    print("\n\n######## BACKTEST ########\n")
    backtest_demo()
