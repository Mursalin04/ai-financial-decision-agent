import os
import sys
import pandas as pd
import numpy as np

# Add code/ to path
sys.path.append(os.path.abspath('code'))

from data_loader import DataLoader
from message_processor import MessageProcessor
from solver import Solver
from validator import validate_dataframe

def test_samples():
    print("Running Sample Validation Test...")
    loader = DataLoader('dataset')
    msg_proc = MessageProcessor(loader.messages_df)
    solver = Solver(loader, msg_proc)

    samples_df = pd.read_csv('dataset/sample_requests.csv')
    predictions = []

    for _, row in samples_df.iterrows():
        pred = solver.solve_request(row)
        predictions.append(pred)

    pred_df = pd.DataFrame(predictions)
    
    # Check validator
    is_valid, errors = validate_dataframe(pred_df, samples_df, loader.profiles_df, loader.options_df)
    print(f"Sample Validation Result: Valid={is_valid}, Errors={len(errors)}")
    if errors:
        for err in errors[:10]:
            print("  -", err)

    # Compare against ground truth in sample_requests.csv
    status_matches = 0
    method_matches = 0
    plan_matches = 0
    total = len(samples_df)

    for i in range(total):
        r_id = samples_df.iloc[i]['request_id']
        exp_status = samples_df.iloc[i]['affordability_status']
        act_status = pred_df.iloc[i]['affordability_status']
        exp_method = samples_df.iloc[i]['recommended_payment_method']
        act_method = pred_df.iloc[i]['recommended_payment_method']
        exp_plan = samples_df.iloc[i]['payment_plan']
        act_plan = pred_df.iloc[i]['payment_plan']
        exp_safe = samples_df.iloc[i]['amount_safe_to_pay']
        act_safe = pred_df.iloc[i]['amount_safe_to_pay']

        if exp_status == act_status:
            status_matches += 1
        if exp_method == act_method:
            method_matches += 1
        if exp_plan == act_plan:
            plan_matches += 1
        else:
            print(f"Mismatch in {r_id}:")
            print(f"  Expected: status={exp_status}, method={exp_method}, plan={exp_plan}, safe={exp_safe}")
            print(f"  Actual:   status={act_status}, method={act_method}, plan={act_plan}, safe={act_safe}")

    print(f"\nAccuracy on 25 Samples:")
    print(f"Status Match: {status_matches}/{total} ({status_matches/total*100:.1f}%)")
    print(f"Method Match: {method_matches}/{total} ({method_matches/total*100:.1f}%)")
    print(f"Plan Match:   {plan_matches}/{total} ({plan_matches/total*100:.1f}%)")

if __name__ == '__main__':
    test_samples()