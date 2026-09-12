import os
import sys
import argparse
import pandas as pd
from typing import Optional

# Ensure code directory is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_loader import DataLoader
from message_processor import MessageProcessor
from solver import Solver
from validator import validate_dataframe

def run_pipeline(dataset_dir: str = "dataset", output_path: str = "output.csv"):
    print("=" * 60)
    print("HackerRank Orchestrate — Buy or Wait?")
    print("AI Financial Decision Agent Pipeline")
    print("=" * 60)
    
    # 1. Load datasets
    print(f"Loading datasets from '{dataset_dir}'...")
    loader = DataLoader(dataset_dir)
    print(f"Loaded {len(loader.requests_df)} evaluation requests.")
    print(f"Loaded {len(loader.profiles_df)} user profiles.")
    print(f"Loaded {len(loader.events_df)} financial events.")
    print(f"Loaded {len(loader.options_df)} payment options.")
    print(f"Loaded {len(loader.messages_df)} messages.")

    # 2. Initialize processors and solver
    print("Initializing MessageProcessor and Solver...")
    msg_proc = MessageProcessor(loader.messages_df)
    solver = Solver(loader, msg_proc)

    # 3. Solve each request
    print("Generating financial recommendations for all requests...")
    results = []
    total_reqs = len(loader.requests_df)
    
    for idx, (_, req_row) in enumerate(loader.requests_df.iterrows()):
        req_id = req_row['request_id']
        pred = solver.solve_request(req_row)
        results.append(pred)
        if (idx + 1) % 25 == 0 or (idx + 1) == total_reqs:
            print(f"  Processed {idx + 1}/{total_reqs} requests ({(idx + 1)/total_reqs*100:.1f}%)")

    # 4. Create DataFrame with exact column order
    required_cols = [
        'request_id',
        'amount_safe_to_pay',
        'affordability_status',
        'recommended_payment_method',
        'payment_plan',
        'earliest_date_for_full_payment',
        'spending_changes_needed',
        'decision_explanation'
    ]
    output_df = pd.DataFrame(results)[required_cols]

    # 5. Validate output against contest requirements
    print("\nValidating output schema and business constraints...")
    is_valid, errors = validate_dataframe(output_df, loader.requests_df, loader.profiles_df, loader.options_df)
    if not is_valid:
        print(f"Validation FAILED with {len(errors)} errors:")
        for err in errors[:10]:
            print(f"  - {err}")
        raise ValueError("Generated output failed validation constraints.")
    else:
        print("Validation PASSED successfully! 0 errors detected.")

    # 6. Save output files
    # Save to specified output path (root output.csv)
    output_df.to_csv(output_path, index=False)
    print(f"Saved predictions to '{output_path}'.")

    # Also save to dataset/output.csv as requested in problem statement
    dataset_output_path = os.path.join(dataset_dir, "output.csv")
    if os.path.abspath(output_path) != os.path.abspath(dataset_output_path):
        output_df.to_csv(dataset_output_path, index=False)
        print(f"Saved copy to '{dataset_output_path}'.")

    # 7. Print summary statistics
    print("\nDecision Summary Breakdown:")
    print(output_df['affordability_status'].value_counts().to_string())
    print("\nRecommended Payment Methods:")
    print(output_df['recommended_payment_method'].value_counts().to_string())
    print("\nPipeline execution complete.")
    return output_df

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Buy or Wait? financial decision pipeline")
    parser.add_argument("--dataset_dir", type=str, default="dataset", help="Path to dataset directory")
    parser.add_argument("--output_path", type=str, default="output.csv", help="Path to write output.csv")
    args = parser.parse_args()

    run_pipeline(args.dataset_dir, args.output_path)