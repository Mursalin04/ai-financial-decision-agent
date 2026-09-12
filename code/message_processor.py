import re
import pandas as pd
from typing import Dict, Any, Optional

class MessageProcessor:
    """
    Parses untrusted natural language messages from messages.csv into
    structured, verified financial adjustments.
    
    Security: Embedded prompt injections are completely ignored; only strictly
    matched financial parameters (amounts, dates, percentages) are extracted.
    """
    def __init__(self, messages_df: pd.DataFrame):
        self.messages_df = messages_df

    def get_user_adjustments(self, user_id: str, request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Extracts verified updates for a specific user.
        Returns:
            salary_override_amount: Optional[float]
            salary_override_date: Optional[str] (YYYY-MM-DD)
            salary_ended: bool
            rent_multiplier: float (e.g. 1.12 for 12% increase)
            new_recurring_expenses: list of dicts
        """
        adj = {
            'salary_override_amount': None,
            'salary_override_date': None,
            'salary_ended': False,
            'rent_multiplier': 1.0,
            'new_recurring_expenses': []
        }
        
        user_msgs = self.messages_df[self.messages_df['user_id'] == user_id]
        for _, row in user_msgs.iterrows():
            text = str(row['message_text'])
            stype = str(row['source_type'])
            
            # 1. Salary termination / contract ended
            if re.search(r'(employment has ended|contract has ended|kontrak musiman saat ini telah berakhir)', text, re.IGNORECASE):
                adj['salary_ended'] = True
                continue
                
            # 2. Household employment ended with remaining salary specified
            rem_match = re.search(r'(?:remaining confirmed monthly salary is|sisa gaji bulanan yang dikonfirmasi adalah)\s+[A-Z]{3}\s+([\d,\.]+)', text, re.IGNORECASE)
            if rem_match:
                amt_str = rem_match.group(1).replace(',', '').rstrip('.')
                try:
                    adj['salary_override_amount'] = float(amt_str)
                except ValueError:
                    pass
                continue
                
            # 3. Rent increase percentage
            rent_inc_match = re.search(r'increases monthly rent by (\d+)%', text, re.IGNORECASE)
            if rent_inc_match:
                pct = float(rent_inc_match.group(1))
                adj['rent_multiplier'] = 1.0 + (pct / 100.0)
                
            # 4. Salary date update
            date_match = re.search(r'(?:expected on|confirmed credit date is|tanggal kredit yang dikonfirmasi adalah|confirmed for|dijadwalkan pada)\s+(\d{4}-\d{2}-\d{2})', text, re.IGNORECASE)
            if date_match:
                adj['salary_override_date'] = date_match.group(1)
                
            # 5. Salary amount updates
            amt_match = re.search(r'(?:naik menjadi|reduced to|monthly pay is|first salary will be|first salary of|first salary from the new employer is|regular salary for the next payroll is|salary of|gaji pokok yang dikonfirmasi adalah|gaji pertama anda sebesar)\s+[A-Z]{3}\s+([\d,\.]+)', text, re.IGNORECASE)
            if amt_match:
                amt_str = amt_match.group(1).replace(',', '').rstrip('.')
                try:
                    adj['salary_override_amount'] = float(amt_str)
                except ValueError:
                    pass

        return adj