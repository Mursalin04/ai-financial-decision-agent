import itertools
import pandas as pd
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from financial_state import FinancialState
from simulator import Simulator
from plan_ranker import rank_plans
from explanation_generator import generate_explanation

def fmt_amt(val: float) -> str:
    if abs(val - round(val)) < 1e-5:
        return str(int(round(val)))
    return f"{val:.2f}"

class Solver:
    def __init__(self, loader, msg_proc):
        self.loader = loader
        self.msg_proc = msg_proc

    def solve_request(self, request_row: pd.Series) -> Dict[str, Any]:
        req_id = str(request_row['request_id'])
        user_id = str(request_row['user_id'])
        req_date = str(request_row['request_date'])
        req_type = str(request_row['request_type'])
        req_amt = float(request_row['requested_amount'])
        desired_date = str(request_row['desired_completion_date'])
        allows_partial = bool(request_row['allows_partial_payment']) if pd.notna(request_row['allows_partial_payment']) else False
        req_text = str(request_row['request_text'])

        # 1. Build financial state
        state = FinancialState(user_id, req_date, self.loader, self.msg_proc)
        sim = Simulator(state.req_dt, state.available_balance, state.minimum_balance, state.baseline_flows)

        # 2. Baseline safe amount and earliest full date
        amount_safe_to_pay = sim.compute_amount_safe_to_pay(req_amt)
        earliest_date = sim.compute_earliest_date_for_full_payment(req_amt)

        # 3. Generate candidate plans
        req_dt = state.req_dt
        end_dt = state.end_dt
        desired_dt = pd.to_datetime(desired_date)
        user_methods = state.considered_methods

        def evaluate_plan_candidates(active_sim, active_flows, changes_str, changes_list):
            candidates = []

            # Option A: full_payment today
            if 'full_payment' in user_methods:
                is_safe, _, _ = active_sim.simulate(extra_payments={req_dt: req_amt})
                if is_safe:
                    status = 'affordable_now' if not changes_list else 'affordable_with_plan'
                    candidates.append({
                        'affordability_status': status,
                        'recommended_payment_method': 'full_payment',
                        'payment_plan': f"{req_date}:{fmt_amt(req_amt)}",
                        'earliest_date_for_full_payment': req_date if not changes_list else (earliest_date if earliest_date else ''),
                        'spending_changes_needed': changes_str,
                        'spending_changes': changes_list,
                        'completes_by_deadline': req_dt <= desired_dt,
                        'total_amount_paid': req_amt,
                        'first_payment_date': req_date,
                        'number_of_payments': 1,
                        'payment_option_id': None
                    })

            # Option B: partial_payment
            if allows_partial and 'partial_payment' in user_methods and not changes_list:
                if 0 < amount_safe_to_pay < req_amt and earliest_date:
                    earliest_dt = pd.to_datetime(earliest_date)
                    rem_amt = req_amt - amount_safe_to_pay
                    is_safe, _, _ = active_sim.simulate(extra_payments={req_dt: amount_safe_to_pay, earliest_dt: rem_amt})
                    if is_safe:
                        candidates.append({
                            'affordability_status': 'affordable_with_plan',
                            'recommended_payment_method': 'partial_payment',
                            'payment_plan': f"{req_date}:{fmt_amt(amount_safe_to_pay)}|{earliest_date}:{fmt_amt(rem_amt)}",
                            'earliest_date_for_full_payment': earliest_date,
                            'spending_changes_needed': 'none',
                            'spending_changes': [],
                            'completes_by_deadline': earliest_dt <= desired_dt,
                            'total_amount_paid': req_amt,
                            'first_payment_date': req_date,
                            'number_of_payments': 2,
                            'payment_option_id': None
                        })

            # Option C: installments from request_payment_options.csv
            if 'installments' in user_methods:
                req_options = self.loader.options_df[
                    (self.loader.options_df['request_id'] == req_id) & 
                    (self.loader.options_df['payment_method'] == 'installments')
                ]
                for _, opt in req_options.iterrows():
                    opt_id = str(opt['payment_option_id'])
                    p_amt = float(opt['payment_amount'])
                    num_p = int(opt['number_of_payments'])
                    f_date = str(opt['first_payment_date'])
                    f_dt = pd.to_datetime(f_date)
                    freq = int(opt['payment_frequency_days'])
                    tot_amt = float(opt['total_payable_amount'])

                    dur_days = (num_p - 1) * freq
                    dur_months = dur_days / 30.0
                    if state.max_installment_months is not None and dur_months > state.max_installment_months:
                        continue

                    sched = {}
                    sched_parts = []
                    for i in range(num_p):
                        p_dt = f_dt + pd.Timedelta(days=i * freq)
                        p_dt_str = p_dt.strftime('%Y-%m-%d')
                        sched[p_dt] = p_amt
                        sched_parts.append(f"{p_dt_str}:{fmt_amt(p_amt)}")

                    completion_dt = f_dt + pd.Timedelta(days=(num_p - 1) * freq)
                    is_safe, _, _ = active_sim.simulate(extra_payments=sched)
                    if is_safe:
                        candidates.append({
                            'affordability_status': 'affordable_with_plan',
                            'recommended_payment_method': 'installments',
                            'payment_plan': "|".join(sched_parts),
                            'earliest_date_for_full_payment': earliest_date if earliest_date else '',
                            'spending_changes_needed': changes_str,
                            'spending_changes': changes_list,
                            'completes_by_deadline': completion_dt <= desired_dt,
                            'total_amount_paid': tot_amt,
                            'first_payment_date': f_date,
                            'number_of_payments': num_p,
                            'payment_option_id': opt_id
                        })

            # Option D: wait
            if 'full_payment' in user_methods and earliest_date and not changes_list:
                earliest_dt = pd.to_datetime(earliest_date)
                candidates.append({
                    'affordability_status': 'affordable_later',
                    'recommended_payment_method': 'wait',
                    'payment_plan': f"{earliest_date}:{fmt_amt(req_amt)}",
                    'earliest_date_for_full_payment': earliest_date,
                    'spending_changes_needed': 'none',
                    'spending_changes': [],
                    'completes_by_deadline': earliest_dt <= desired_dt,
                    'total_amount_paid': req_amt,
                    'first_payment_date': earliest_date,
                    'number_of_payments': 1,
                    'payment_option_id': None
                })

            return candidates

        # Evaluate candidates without spending changes
        candidates = evaluate_plan_candidates(sim, state.baseline_flows, 'none', [])
        candidates_by_deadline = [c for c in candidates if c['completes_by_deadline']]

        # Option E: Spending Changes (if needed)
        if not candidates_by_deadline and state.flexible_events:
            possible_actions = []
            for fe in state.flexible_events:
                eid = fe['event_id']
                cat = fe['category']
                flex = fe['flexibility']
                e_amt = fe['amount']
                min_a = fe['minimum_allowed_amount']

                if (flex in ['stoppable', 'reducible_or_stoppable']) and (cat in state.stoppable_cats):
                    possible_actions.append(('stop', eid, cat, e_amt, f"stop:{eid}", fe))
                if (flex in ['reducible', 'reducible_or_stoppable']) and (cat in state.reducible_cats):
                    saved = e_amt - min_a
                    if saved > 0:
                        possible_actions.append(('reduce', eid, cat, saved, f"reduce_to:{eid}:{fmt_amt(min_a)}", fe))

            best_change_candidates = []
            for k in range(1, min(4, len(possible_actions) + 1)):
                for combo in itertools.combinations(possible_actions, k):
                    used_eids = [act[1] for act in combo]
                    if len(set(used_eids)) < len(used_eids):
                        continue

                    adj_flows = {}
                    for act in combo:
                        action_type, eid, cat, saved_val, ch_str, fe = act
                        if fe.get('is_periodic', False):
                            curr = fe['last_dt'] + pd.Timedelta(days=fe['interval'])
                            while curr <= end_dt:
                                if curr >= req_dt:
                                    adj_flows[curr] = adj_flows.get(curr, 0.0) + saved_val
                                curr += pd.Timedelta(days=fe['interval'])
                        else:
                            dom = fe['dom']
                            for m_offset in range(4):
                                y = req_dt.year + (req_dt.month - 1 + m_offset) // 12
                                m = ((req_dt.month - 1 + m_offset) % 12) + 1
                                try:
                                    dt = pd.to_datetime(f"{y}-{m:02d}-{dom:02d}")
                                except:
                                    dt = pd.to_datetime(f"{y}-{m:02d}-28")
                                if req_dt <= dt <= end_dt:
                                    adj_flows[dt] = adj_flows.get(dt, 0.0) + saved_val

                    combo_flows = {dt: state.baseline_flows[dt] + adj_flows.get(dt, 0.0) for dt in state.baseline_flows}
                    combo_sim = Simulator(req_dt, state.available_balance, state.minimum_balance, combo_flows)
                    combo_str = "|".join([act[4] for act in combo])
                    combo_list = [act[4] for act in combo]

                    c_plans = evaluate_plan_candidates(combo_sim, combo_flows, combo_str, combo_list)
                    deadline_plans = [cp for cp in c_plans if cp['completes_by_deadline']]
                    if deadline_plans:
                        best_change_candidates.extend(deadline_plans)
                if best_change_candidates:
                    break
            candidates.extend(best_change_candidates)

        # Rank all valid candidate plans
        if candidates:
            best_plan = rank_plans(candidates)
        else:
            best_plan = {
                'affordability_status': 'not_affordable',
                'recommended_payment_method': 'not_recommended',
                'payment_plan': 'none',
                'earliest_date_for_full_payment': earliest_date if earliest_date else '',
                'spending_changes_needed': 'none',
                'spending_changes': [],
                'completes_by_deadline': False,
                'total_amount_paid': 0.0,
                'first_payment_date': None,
                'number_of_payments': 0,
                'payment_option_id': None
            }

        # Populate amount_safe_to_pay in plan result
        best_plan['amount_safe_to_pay'] = amount_safe_to_pay
        best_plan['request_id'] = req_id

        # Generate decision explanation
        user_prof_dict = state.prof.to_dict()
        user_prof_dict['minimum_balance_to_keep'] = state.minimum_balance
        user_prof_dict['home_currency'] = state.home_cur
        req_info_dict = {
            'requested_amount': req_amt,
            'desired_completion_date': desired_date
        }
        best_plan['decision_explanation'] = generate_explanation(best_plan, user_prof_dict, req_info_dict)

        # Return exact required schema
        return {
            'request_id': req_id,
            'amount_safe_to_pay': best_plan['amount_safe_to_pay'],
            'affordability_status': best_plan['affordability_status'],
            'recommended_payment_method': best_plan['recommended_payment_method'],
            'payment_plan': best_plan['payment_plan'],
            'earliest_date_for_full_payment': best_plan['earliest_date_for_full_payment'],
            'spending_changes_needed': best_plan['spending_changes_needed'],
            'decision_explanation': best_plan['decision_explanation']
        }