from typing import Dict, List, Any, Optional

def rank_plans(candidate_plans: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Ranks safe eligible candidate plans according to the exact competition rules:
    1. Complete the full request by desired_completion_date.
    2. Require no spending changes.
    3. Minimize the total amount paid.
    4. Start payment earlier.
    5. Use fewer payments.
    6. Lowest payment_option_id as the final tie-breaker.
    """
    if not candidate_plans:
        return {
            'affordability_status': 'not_affordable',
            'recommended_payment_method': 'not_recommended',
            'payment_plan': 'none',
            'spending_changes_needed': 'none',
            'decision_explanation': ''
        }

    def ranking_key(p):
        # 1. Complete by deadline (True first -> 0, False -> 1)
        k1 = 0 if p.get('completes_by_deadline', False) else 1
        
        # 2. Require no spending changes (0 changes first -> 0, >0 -> 1)
        num_changes = len(p.get('spending_changes', []))
        k2 = 0 if num_changes == 0 else 1
        
        # 3. Minimize total amount paid
        k3 = float(p.get('total_amount_paid', 1e12))
        
        # 4. Start payment earlier
        k4 = str(p.get('first_payment_date', '9999-12-31'))
        
        # 5. Use fewer payments
        k5 = int(p.get('number_of_payments', 999))
        
        # 6. Lowest payment_option_id
        # Convert e.g. 'payment_option_05' to integer 5, or 999999 if not installment
        opt_id = str(p.get('payment_option_id', ''))
        if 'payment_option_' in opt_id:
            try:
                k6 = int(opt_id.replace('payment_option_', ''))
            except:
                k6 = 999999
        else:
            k6 = 999999

        return (k1, k2, k3, k4, k5, k6)

    sorted_plans = sorted(candidate_plans, key=ranking_key)
    return sorted_plans[0]