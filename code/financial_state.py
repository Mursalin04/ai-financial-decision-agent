import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any

class FinancialState:
    """
    Reconstructs user profile, active recurring commitments, pending debits,
    and scheduled income over a 90-day forecast horizon.
    """
    def __init__(self, user_id: str, request_date: str, loader, msg_proc):
        self.user_id = user_id
        self.request_date = request_date
        self.req_dt = pd.to_datetime(request_date)
        self.end_dt = self.req_dt + pd.Timedelta(days=90)
        self.loader = loader
        self.msg_proc = msg_proc

        # Profile data
        self.prof = loader.profiles_df[loader.profiles_df['user_id'] == user_id].iloc[0]
        self.home_cur = self.prof['home_currency']
        self.available_balance = float(self.prof['current_available_balance'])
        self.minimum_balance = float(self.prof['minimum_balance_to_keep'])
        self.priorities = str(self.prof['financial_priorities']).split('|')
        
        self.protected_cats = set(str(self.prof['expense_categories_to_protect']).split('|')) if pd.notna(self.prof['expense_categories_to_protect']) else set()
        self.reducible_cats = set(str(self.prof['expense_categories_user_is_willing_to_reduce']).split('|')) if pd.notna(self.prof['expense_categories_user_is_willing_to_reduce']) else set()
        self.stoppable_cats = set(str(self.prof['expense_categories_user_is_willing_to_stop']).split('|')) if pd.notna(self.prof['expense_categories_user_is_willing_to_stop']) else set()
        
        self.considered_methods = set(str(self.prof['payment_methods_user_will_consider']).split('|'))
        self.max_installment_months = float(self.prof['max_installment_months']) if pd.notna(self.prof['max_installment_months']) else None

        # Message adjustments
        self.adj = msg_proc.get_user_adjustments(user_id)

        # Reconstructed events for user with currency conversion
        self.events = self._load_and_convert_events()

        # Build baseline recurring commitments
        self.baseline_flows, self.flexible_events = self._build_baseline_flows()

    def _load_and_convert_events(self) -> pd.DataFrame:
        df = self.loader.events_df[self.loader.events_df['user_id'] == self.user_id].copy()
        c_amounts = []
        for _, r in df.iterrows():
            amt = float(r['amount']) if pd.notna(r['amount']) else 0.0
            cur = str(r['currency'])
            s_date = str(r['settlement_date'])
            c_amt = self.loader.convert_currency(amt, cur, self.home_cur, s_date)
            c_amounts.append(c_amt)
        df['home_amount'] = c_amounts
        df['settlement_dt'] = pd.to_datetime(df['settlement_date'])
        return df

    def _build_baseline_flows(self) -> Tuple[Dict[pd.Timestamp, float], List[Dict[str, Any]]]:
        flows = {self.req_dt + pd.Timedelta(days=i): 0.0 for i in range(91)}
        flexible_events = []

        # 1. Known future events in financial_events.csv (pending debits, scheduled items)
        future_events = self.events[self.events['settlement_dt'] >= self.req_dt]
        known_salary_dts = set()
        sched_salary_amt = 0.0
        sched_salary_day = 15

        for _, r in future_events.iterrows():
            st = r['status']
            direction = r['direction']
            amt = r['home_amount']
            s_dt = r['settlement_dt']
            etype = r['event_type']
            cat = r['category']
            
            if st == 'pending' and direction == 'debit' and s_dt in flows:
                flows[s_dt] -= amt
            elif st == 'scheduled':
                if direction == 'credit' and (etype == 'income' or cat == 'salary'):
                    if s_dt in flows:
                        flows[s_dt] += amt
                        known_salary_dts.add(s_dt)
                        sched_salary_amt = amt
                        sched_salary_day = s_dt.day
                elif direction == 'debit' and s_dt in flows:
                    flows[s_dt] -= amt

        # 2. Historical settled records to detect active recurring streams
        settled_hist = self.events[(self.events['settlement_dt'] < self.req_dt) & 
                                   (self.events['status'] == 'settled')]

        # Salary recurrence
        if not self.adj['salary_ended']:
            sal_events = settled_hist[(settled_hist['direction'] == 'credit') & 
                                      (settled_hist['category'] == 'salary')].sort_values('settlement_dt')
            base_salary = 0.0
            sal_day = 15

            if self.adj['salary_override_amount'] is not None:
                base_salary = self.adj['salary_override_amount']
            elif sched_salary_amt > 0:
                base_salary = sched_salary_amt
                sal_day = sched_salary_day
            elif len(sal_events) > 0:
                payroll_credits = sal_events[sal_events['description'].str.contains('Payroll credit', case=False, na=False)]
                if len(payroll_credits) > 0:
                    last_sal = payroll_credits.iloc[-1]
                else:
                    last_sal = sal_events.iloc[-1]
                if "final" not in str(last_sal['description']).lower():
                    base_salary = last_sal['home_amount']
                    sal_day = last_sal['settlement_dt'].day

            if self.adj['salary_override_date'] is not None:
                sal_day = pd.to_datetime(self.adj['salary_override_date']).day

            if base_salary > 0:
                for m_offset in range(4):
                    y = self.req_dt.year + (self.req_dt.month - 1 + m_offset) // 12
                    m = ((self.req_dt.month - 1 + m_offset) % 12) + 1
                    try:
                        dt = pd.to_datetime(f"{y}-{m:02d}-{sal_day:02d}")
                    except:
                        dt = pd.to_datetime(f"{y}-{m:02d}-28")
                    if self.req_dt <= dt <= self.end_dt and dt not in known_salary_dts:
                        flows[dt] += base_salary
                        known_salary_dts.add(dt)

        # Variable categories: groceries, transport, dining
        for cat in ['groceries', 'transport', 'dining']:
            cat_events = settled_hist[settled_hist['category'] == cat].sort_values('settlement_dt')
            if len(cat_events) >= 2:
                diffs = cat_events['settlement_dt'].diff().dt.days.dropna()
                interval = int(round(diffs.median()))
                if interval < 1:
                    interval = 7
                last_dt = cat_events.iloc[-1]['settlement_dt']
                amt = cat_events.tail(4)['home_amount'].mean()

                # Check flexible candidate
                last_event = cat_events.iloc[-1]
                flex = str(last_event['flexibility'])
                min_allowed = float(last_event['minimum_allowed_amount']) if pd.notna(last_event['minimum_allowed_amount']) else 0.0
                if flex in ['stoppable', 'reducible', 'reducible_or_stoppable'] and cat not in self.protected_cats:
                    flexible_events.append({
                        'event_id': last_event['event_id'],
                        'category': cat,
                        'description': last_event['description'],
                        'flexibility': flex,
                        'amount': last_event['home_amount'],
                        'minimum_allowed_amount': min_allowed,
                        'is_periodic': True,
                        'interval': interval,
                        'last_dt': last_dt
                    })

                curr = last_dt + pd.Timedelta(days=interval)
                while curr <= self.end_dt:
                    if curr >= self.req_dt:
                        flows[curr] -= amt
                    curr += pd.Timedelta(days=interval)

        # Monthly categories
        monthly_cats = set(settled_hist['category'].unique()) - {'groceries', 'transport', 'dining', 'salary', 'income', 'refund', 'investment'}
        for cat in monthly_cats:
            sub = settled_hist[settled_hist['category'] == cat]
            for desc, grp in sub.groupby('description'):
                if len(grp) >= 2:
                    grp_sorted = grp.sort_values('settlement_dt')
                    last_event = grp_sorted.iloc[-1]
                    last_dt = last_event['settlement_dt']
                    amt = last_event['home_amount']
                    dom = last_dt.day

                    if cat == 'rent':
                        amt *= self.adj['rent_multiplier']

                    flex = str(last_event['flexibility'])
                    min_allowed = float(last_event['minimum_allowed_amount']) if pd.notna(last_event['minimum_allowed_amount']) else 0.0
                    if flex in ['stoppable', 'reducible', 'reducible_or_stoppable'] and cat not in self.protected_cats:
                        flexible_events.append({
                            'event_id': last_event['event_id'],
                            'category': cat,
                            'description': desc,
                            'flexibility': flex,
                            'amount': amt,
                            'minimum_allowed_amount': min_allowed,
                            'is_periodic': False,
                            'dom': dom
                        })

                    for m_offset in range(4):
                        y = self.req_dt.year + (self.req_dt.month - 1 + m_offset) // 12
                        m = ((self.req_dt.month - 1 + m_offset) % 12) + 1
                        try:
                            dt = pd.to_datetime(f"{y}-{m:02d}-{dom:02d}")
                        except:
                            dt = pd.to_datetime(f"{y}-{m:02d}-28")
                        if self.req_dt <= dt <= self.end_dt:
                            flows[dt] -= amt

        return flows, flexible_events