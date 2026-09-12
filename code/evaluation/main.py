import os
import sys

def main():
    print("=" * 60)
    print("HackerRank Orchestrate — Evaluation & Token Usage Summary")
    print("=" * 60)
    
    report_path = os.path.join(os.path.dirname(__file__), "usage_report.md")
    if not os.path.exists(report_path):
        print(f"Error: Usage report not found at {report_path}")
        sys.exit(1)
        
    with open(report_path, "r", encoding="utf-8") as f:
        print(f.read())

if __name__ == "__main__":
    main()