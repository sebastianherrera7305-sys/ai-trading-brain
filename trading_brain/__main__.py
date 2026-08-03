"""`python3 -m trading_brain` runs the synthetic demos for each module."""

from .liquidity import run_demo as liquidity_demo
from .market_structure import run_demo as market_structure_demo

if __name__ == "__main__":
    print("######## MARKET STRUCTURE ########\n")
    market_structure_demo()
    print("\n\n######## LIQUIDITY ########\n")
    liquidity_demo()
