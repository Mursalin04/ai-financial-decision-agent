# Buy or Wait? — AI Financial Decision Agent
## HackerRank Orchestrate (September 2026)

This repository contains the winning autonomous financial decision agent for the **Buy or Wait?** challenge.

---

## 1. System Architecture

The agent evaluates financial purchase and payment requests across 250 evaluation cases. For each request, the agent decides whether the user should:
- Pay in full (`full_payment`, `affordable_now` or `affordable_with_plan`)
- Pay partially today and remaining balance on payday (`partial_payment`, `affordable_with_plan`)
- Use an eligible seller installment plan (`installments`, `affordable_with_plan`)
- Wait until safe full payment is projected (`wait`, `affordable_later`)
- Not proceed (`not_recommended`, `not_affordable`)

### Key Components
1. **Multimodal Invoice Resolution (`image_processor.py`)**: Automatically resolves blank event amounts by reading invoice media in `dataset/media/images/`.
2. **Message Understanding (`message_processor.py`)**: Parses natural language messages for salary adjustments, contract terminations, and lease updates.
3. **Data Loader (`data_loader.py`)**: Ingests structured profiles, dated foreign exchange rates, and financial transactions.
4. **90-Day Cash-Flow Simulator (`simulator.py`)**: Simulates daily cash flow over 90 days ensuring the balance never breaches `minimum_balance_to_keep`.
5. **Plan Generator & Ranker (`solver.py`, `plan_ranker.py`)**: Generates candidate payment plans and evaluates spending changes (`stop:<event_id>`, `reduce_to:<event_id>:<amount>`), strictly obeying the 6-tier ranking hierarchy.
6. **Decision Explainer (`explanation_generator.py`)**: Produces grounded, concise explanations adhering to challenge standards.
7. **Deterministic Validator (`validator.py`)**: Enforces column structure, mathematical bounds, date formats, and financial invariants.

---

## 2. Requirements & Installation

Python 3.10+ is recommended.

```bash
pip install -r code/requirements.txt
```

Dependencies:
- `pandas>=2.2.0`
- `numpy>=1.26.0`
- `pillow>=10.0.0`

---

## 3. Running the Pipeline

To run the complete pipeline and produce the submission `output.csv`:

```bash
python code/main.py
```

Optional arguments:
- `--dataset_dir`: Path to dataset directory (default: `dataset`)
- `--output_path`: Path for generated output CSV (default: `output.csv`)

Example:
```bash
python code/main.py --dataset_dir dataset --output_path output.csv
```

---

## 4. Validating the Output

The output file is automatically validated upon completion. You can also run the validator independently:

```bash
python code/validator.py --input output.csv
```

---

## 5. Token Usage & Performance Report

See `evaluation/usage_report.md` for full breakdown of model calls, tokens, latency, and cost estimates.
