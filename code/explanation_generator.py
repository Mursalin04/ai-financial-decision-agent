import pandas as pd
from typing import Dict, Any, List

def format_curr(amount: float, currency: str) -> str:
    # Format with comma separators and appropriate decimals
    # If integer-like, no decimals; else 2 decimals
    if abs(amount - round(amount)) < 1e-4:
        return f"{currency} {int(round(amount)):,}"
    else:
        return f"{currency} {amount:,.2f}"

def format_date_natural(date_str: str) -> str:
    # Converts '2024-03-03' to '3 March 2024' or '15 November 2019'
    dt = pd.to_datetime(date_str)
    month_name = dt.strftime('%B')
    return f"{dt.day} {month_name} {dt.year}"

def generate_explanation(plan_result: Dict[str, Any], user_profile: Dict[str, Any], request_info: Dict[str, Any]) -> str:
    status = plan_result['affordability_status']
    method = plan_result['recommended_payment_method']
    cur = user_profile['home_currency']
    min_bal = user_profile['minimum_balance_to_keep']
    min_bal_str = format_curr(min_bal, cur)
    req_amt = request_info['requested_amount']
    req_amt_str = format_curr(req_amt, cur)
    desired_date_str = format_date_natural(request_info['desired_completion_date'])
    safe_amt = plan_result['amount_safe_to_pay']
    safe_amt_str = format_curr(safe_amt, cur)
    
    if status == 'affordable_now' and method == 'full_payment':
        return f"Pay {req_amt_str} today. This leaves at least {min_bal_str} available over the next 90 days."
        
    elif method == 'installments':
        parts = plan_result['payment_plan'].split('|')
        num_inst = len(parts)
        first_date_str = format_date_natural(parts[0].split(':')[0])
        inst_amt = float(parts[0].split(':')[1])
        inst_amt_str = format_curr(inst_amt, cur)
        return f"Use {num_inst} installments of {inst_amt_str}, starting {first_date_str}. This leaves at least {min_bal_str} available."
        
    elif method == 'partial_payment':
        rem_amt = req_amt - safe_amt
        rem_amt_str = format_curr(rem_amt, cur)
        earliest_date_str = format_date_natural(plan_result['earliest_date_for_full_payment'])
        return f"Pay {safe_amt_str} today and the remaining {rem_amt_str} on {earliest_date_str}. This completes the full request and keeps the {min_bal_str} minimum protected."
        
    elif status == 'affordable_with_plan' and method == 'full_payment':
        # Handled with spending changes
        changes_desc = plan_result.get('changes_description', '')
        if changes_desc:
            return f"{changes_desc}, then pay {req_amt_str} today. This leaves at least {min_bal_str} available."
        return f"Pay {req_amt_str} today. This leaves at least {min_bal_str} available."
        
    elif method == 'wait':
        earliest_date_str = format_date_natural(plan_result['earliest_date_for_full_payment'])
        return f"Pay {req_amt_str} in full on {earliest_date_str}. Paying earlier would take the balance below the {min_bal_str} minimum."
        
    else: # not_recommended / not_affordable
        if safe_amt > 0:
            return f"Do not proceed with the {req_amt_str} request. Although {safe_amt_str} is available today, the full amount cannot be completed safely within 90 days."
        else:
            return f"Do not make this payment by {desired_date_str}. None of the available options keeps the {min_bal_str} minimum protected."