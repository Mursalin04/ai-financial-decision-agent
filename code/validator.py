import pandas as pd
import numpy as np
import sys
import os
from typing import List, Tuple

REQUIRED_COLUMNS = [
    'request_id',
    'amount_safe_to_pay',
    'affordability_status',
    'recommended_payment_method',
    'payment_plan',
    'earliest_date_for_full_payment',
    'spending_changes_needed',
    'decision_explanation'
]

VALID_STATUSES = {'affordable_now', 'affordable_with_plan', 'affordable_later', 'not_affordable'}
VALID_METHODS = {'full_payment', 'partial_payment', 'installments', 'wait', 'not_recommended'}

def validate_dataframe(output_df: pd.DataFrame, requests_df: pd.DataFrame, profiles_df: pd.DataFrame, options_df: pd.DataFrame) -> Tuple[bool, List[str]]:
    errors = []
    
    # 1. Columns check
    if list(output_df.columns) != REQUIRED_COLUMNS:
        errors.append(f"Columns mismatch. Expected {REQUIRED_COLUMNS}, got {list(output_df.columns)}")
        return False, errors

    # 2. Row count and request_id check
    if len(output_df) != len(requests_df):
        errors.append(f"Row count mismatch: expected {len(requests_df)}, got {len(output_df)}")
        
    expected_ids = set(requests_df['request_id'])
    actual_ids = set(output_df['request_id'])
    if expected_ids != actual_ids:
        errors.append(f"Missing request_ids: {expected_ids - actual_ids}, Extra request_ids: {actual_ids - expected_ids}")

    req_map = requests_df.set_index('request_id').to_dict(orient='index')
    prof_map = profiles_df.set_index('user_id').to_dict(orient='index')

    for idx, row in output_df.iterrows():
        req_id = row['request_id']
        if req_id not in req_map:
            continue
        req = req_map[req_id]
        user_id = req['user_id']
        prof = prof_map.get(user_id, {})
        
        req_amt = float(req['requested_amount'])
        safe_amt = float(row['amount_safe_to_pay'])
        status = str(row['affordability_status'])
        method = str(row['recommended_payment_method'])
        plan = str(row['payment_plan'])
        earliest = str(row['earliest_date_for_full_payment']) if pd.notna(row['earliest_date_for_full_payment']) else ""
        changes = str(row['spending_changes_needed'])
        expl = str(row['decision_explanation'])

        # 3. Safe amount bounds
        if safe_amt < -1e-4 or safe_amt > req_amt + 1e-4:
            errors.append(f"Row {req_id}: safe amount {safe_amt} out of bounds [0, {req_amt}]")

        # 4. Status and Method validity
        if status not in VALID_STATUSES:
            errors.append(f"Row {req_id}: invalid status {status}")
        if method not in VALID_METHODS:
            errors.append(f"Row {req_id}: invalid method {method}")

        # 5. affordable_now rules
        if status == 'affordable_now':
            if method != 'full_payment':
                errors.append(f"Row {req_id}: affordable_now must use full_payment, got {method}")
            if earliest != str(req['request_date']):
                errors.append(f"Row {req_id}: affordable_now earliest_date must equal request_date {req['request_date']}, got {earliest}")
            if abs(safe_amt - req_amt) > 1e-2:
                errors.append(f"Row {req_id}: affordable_now safe_amt {safe_amt} must equal req_amt {req_amt}")

        # 6. partial_payment rules
        if method == 'partial_payment':
            if status != 'affordable_with_plan':
                errors.append(f"Row {req_id}: partial_payment must have status affordable_with_plan, got {status}")
            if not bool(req.get('allows_partial_payment', False)):
                errors.append(f"Row {req_id}: partial_payment chosen but request does not allow partial payment")
            if safe_amt <= 0 or safe_amt >= req_amt:
                errors.append(f"Row {req_id}: partial_payment requires 0 < safe_amt < req_amt, got {safe_amt}")
            if not earliest:
                errors.append(f"Row {req_id}: partial_payment requires non-empty earliest_date")
            else:
                if pd.to_datetime(earliest) > pd.to_datetime(req['desired_completion_date']):
                    errors.append(f"Row {req_id}: partial_payment second payment date {earliest} exceeds desired completion date {req['desired_completion_date']}")
            
            # Plan format check
            parts = plan.split('|')
            if len(parts) != 2:
                errors.append(f"Row {req_id}: partial_payment plan must have exactly 2 payments, got {len(parts)}")
            else:
                try:
                    d1, a1 = parts[0].split(':')
                    d2, a2 = parts[1].split(':')
                    if d1 != str(req['request_date']):
                        errors.append(f"Row {req_id}: partial_payment first date {d1} != request_date {req['request_date']}")
                    if d2 != earliest:
                        errors.append(f"Row {req_id}: partial_payment second date {d2} != earliest_date {earliest}")
                    if abs(float(a1) + float(a2) - req_amt) > 1e-2:
                        errors.append(f"Row {req_id}: partial payments {a1} + {a2} != req_amt {req_amt}")
                except Exception as e:
                    errors.append(f"Row {req_id}: malformed partial_payment plan syntax {plan}: {e}")

        # 7. not_recommended rules
        if method == 'not_recommended':
            if status != 'not_affordable':
                errors.append(f"Row {req_id}: not_recommended must have status not_affordable, got {status}")
            if plan != 'none':
                errors.append(f"Row {req_id}: not_recommended plan must be 'none', got {plan}")

        # 8. wait rules
        if method == 'wait':
            if status != 'affordable_later':
                errors.append(f"Row {req_id}: wait must have status affordable_later, got {status}")
            if not earliest:
                errors.append(f"Row {req_id}: wait requires non-empty earliest_date")

        # 9. Spending changes syntax
        if changes != 'none':
            c_items = changes.split('|')
            if len(c_items) > 3:
                errors.append(f"Row {req_id}: maximum 3 spending changes allowed, got {len(c_items)}")
            seen_events = set()
            for c in c_items:
                if c.startswith('stop:'):
                    eid = c.replace('stop:', '')
                elif c.startswith('reduce_to:'):
                    parts = c.split(':')
                    eid = parts[1]
                else:
                    errors.append(f"Row {req_id}: invalid spending change syntax {c}")
                    continue
                if eid in seen_events:
                    errors.append(f"Row {req_id}: duplicate event {eid} in spending changes")
                seen_events.add(eid)

        # 10. Explanation presence
        if not expl or len(expl.strip()) < 5:
            errors.append(f"Row {req_id}: missing or too short decision explanation")

    return len(errors) == 0, errors

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='output.csv', help='Path to output.csv to validate')
    args = parser.parse_args()

    out_path = args.input
    if not os.path.exists(out_path):
        print(f"Error: {out_path} does not exist.")
        sys.exit(1)

    out_df = pd.read_csv(out_path)
    reqs_df = pd.read_csv('dataset/requests.csv')
    profs_df = pd.read_csv('dataset/financial_profiles.csv')
    opts_df = pd.read_csv('dataset/request_payment_options.csv')

    is_valid, errors = validate_dataframe(out_df, reqs_df, profs_df, opts_df)
    if is_valid:
        print(f"VALIDATION PASSED: All {len(out_df)} rows in {out_path} strictly conform to all rules!")
        sys.exit(0)
    else:
        print(f"VALIDATION FAILED with {len(errors)} error(s):")
        for err in errors[:25]:
            print("  -", err)
        if len(errors) > 25:
            print(f"  ... and {len(errors) - 25} more errors.")
        sys.exit(1)