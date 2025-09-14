import argparse
import math
import sys
import numpy as np
import pandas as pd

#!/usr/bin/env python3


# Definície funkcií pre výpočet ukazovateľov
def annualized_return_from_returns(returns, trading_days=252):
    if returns.empty:
        return np.nan
    cumulative = (1 + returns).prod()
    periods = len(returns)
    return cumulative ** (trading_days / periods) - 1

def sharpe_ratio_from_returns(returns, risk_free_annual=0.0, trading_days=252):
    if returns.empty or returns.std() == 0:
        return np.nan
    rf_daily = risk_free_annual / trading_days
    excess_mean = returns.mean() - rf_daily
    # Annualize numerator and denominator
    return (excess_mean / returns.std()) * math.sqrt(trading_days)

def percentualny_drawdown_from_equity(equity):
    if equity.empty:
        return np.nan
    running_max = equity.cummax()
    drawdowns = (equity - running_max) / running_max
    return drawdowns.min()

def load_series(path, column):
    df = pd.read_csv(path)
    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found in {path}. Available columns: {list(df.columns)}")
    return df[column].astype(float)

def main():
    p = argparse.ArgumentParser(description="Vypočíta Annualizované zhodnotenie, Sharpe Ratio a Percentuálny drawdown z CSV.")
    p.add_argument("csv", nargs="?", default="data.csv", help="Cesta k CSV súboru (default: data.csv)")
    p.add_argument("--col", default="zisk", help="Názov stĺpca v CSV so sériou (default: zisk)")
    p.add_argument("--rf", type=float, default=0.0, help="Ročný bezrizikový výnos ako desatinné číslo (default: 0.0)")
    p.add_argument("--days", type=int, default=252, help="Počet obchodných dní v roku (default: 252)")
    args = p.parse_args()

    try:
        series = load_series(args.csv, args.col)
    except Exception as e:
        print("Chyba pri načítaní CSV:", e, file=sys.stderr)
        sys.exit(2)

    # Predpoklad: vstupná séria predstavuje hodnoty portfólia / equity v čase.
    returns = series.pct_change().dropna()

    ann_ret = annualized_return_from_returns(returns, trading_days=args.days)
    sharpe = sharpe_ratio_from_returns(returns, risk_free_annual=args.rf, trading_days=args.days)

    # Použijeme equity krivku vypočítanú z returns na drawdown
    equity = (1 + returns).cumprod()
    drawdown = percentualny_drawdown_from_equity(equity)

    # Výstup (percentá formátované)
    def fmt_pct(x):
        return "NaN" if (x is None or (isinstance(x, float) and np.isnan(x))) else f"{x * 100:.2f}%"

    print(f"Annualizované zhodnotenie: {fmt_pct(ann_ret)}")
    print(f"Sharpe Ratio: {sharpe:.4f}" if not (isinstance(sharpe, float) and np.isnan(sharpe)) else "Sharpe Ratio: NaN")
    print(f"Percentuálny Drawdown (najhorší): {fmt_pct(drawdown)}")

if __name__ == "__main__":
    main()