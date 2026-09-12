import pandas as pd
from typing import Dict, List, Tuple, Optional

class Simulator:
    """
    Deterministic 90-day daily cash-flow simulator.
    Tracks starting balance, scheduled income, essential and recurring expenses,
    pending transactions, and recommended payment schedules.
    """
    def __init__(self, req_dt: pd.Timestamp, initial_balance: float, minimum_balance: float, baseline_flows: Dict[pd.Timestamp, float]):
        self.req_dt = req_dt
        self.end_dt = req_dt + pd.Timedelta(days=90)
        self.initial_balance = initial_balance
        self.minimum_balance = minimum_balance
        self.baseline_flows = baseline_flows

    def simulate(self, extra_payments: Optional[Dict[pd.Timestamp, float]] = None, flow_adjustments: Optional[Dict[pd.Timestamp, float]] = None) -> Tuple[bool, float, Dict[pd.Timestamp, float]]:
        """
        Simulates cash flow over 90 days.
        extra_payments: date -> payment amount (e.g. laptop purchase)
        flow_adjustments: date -> positive adjustment from spending reductions/stops
        Returns: (is_safe, min_balance_observed, balance_trajectory)
        """
        curr_balance = self.initial_balance
        min_balance_observed = curr_balance
        is_safe = True
        trajectory = {}

        for day_offset in range(91):
            dt = self.req_dt + pd.Timedelta(days=day_offset)
            
            # Baseline net cash flow on this day
            net_flow = self.baseline_flows.get(dt, 0.0)
            
            # Add flow adjustments (e.g. saved money from stopped/reduced subscriptions)
            if flow_adjustments and dt in flow_adjustments:
                net_flow += flow_adjustments[dt]
                
            # Apply extra payment (debit)
            if extra_payments and dt in extra_payments:
                net_flow -= extra_payments[dt]
                
            curr_balance += net_flow
            trajectory[dt] = curr_balance
            
            if curr_balance < min_balance_observed:
                min_balance_observed = curr_balance
                
            if curr_balance < self.minimum_balance:
                is_safe = False

        return is_safe, min_balance_observed, trajectory

    def compute_amount_safe_to_pay(self, requested_amount: float) -> float:
        """
        Computes maximum amount user can safely pay today before optional spending changes.
        amount_safe_to_pay is bounded between 0 and requested_amount.
        """
        # Baseline simulation with 0 extra payment
        _, min_observed, _ = self.simulate()
        
        # Max amount safe today is the minimum surplus above minimum_balance across the 90 days
        max_safe = min_observed - self.minimum_balance
        max_safe = max(0.0, min(requested_amount, max_safe))
        return round(max_safe, 2)

    def compute_earliest_date_for_full_payment(self, requested_amount: float) -> str:
        """
        Finds the first date on which the full requested amount can safely be paid
        as a single payment without optional spending changes.
        Returns YYYY-MM-DD, or empty string if not safe within 90 days.
        """
        for day_offset in range(91):
            cand_dt = self.req_dt + pd.Timedelta(days=day_offset)
            is_safe, _, _ = self.simulate(extra_payments={cand_dt: requested_amount})
            if is_safe:
                return cand_dt.strftime('%Y-%m-%d')
        return ""