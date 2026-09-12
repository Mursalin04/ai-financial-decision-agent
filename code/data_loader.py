import os
import pandas as pd
from image_processor import resolve_blank_event_amounts

class DataLoader:
    def __init__(self, data_dir: str = "dataset"):
        self.data_dir = data_dir
        self.requests_df = pd.read_csv(os.path.join(data_dir, "requests.csv"))
        self.profiles_df = pd.read_csv(os.path.join(data_dir, "financial_profiles.csv"))
        self.events_raw = pd.read_csv(os.path.join(data_dir, "financial_events.csv"))
        self.images_df = pd.read_csv(os.path.join(data_dir, "images.csv"))
        self.messages_df = pd.read_csv(os.path.join(data_dir, "messages.csv"))
        self.options_df = pd.read_csv(os.path.join(data_dir, "request_payment_options.csv"))
        self.rates_df = pd.read_csv(os.path.join(data_dir, "exchange_rates.csv"))

        # Resolve blank amounts from images
        self.events_df = resolve_blank_event_amounts(
            self.events_raw, 
            self.images_df, 
            os.path.join(data_dir, "media", "images")
        )

        # Build rate lookup table: (date, from_cur, to_cur) -> rate
        self.rates_map = {}
        for _, row in self.rates_df.iterrows():
            key = (str(row['rate_date']), str(row['from_currency']), str(row['to_currency']))
            self.rates_map[key] = float(row['rate'])

    def convert_currency(self, amount: float, from_cur: str, to_cur: str, date_str: str) -> float:
        if from_cur == to_cur or amount == 0:
            return amount
        key = (str(date_str), str(from_cur), str(to_cur))
        if key in self.rates_map:
            return amount * self.rates_map[key]
        # Fallback to nearest date if exact date not found
        matching_rates = [
            (k[0], v) for k, v in self.rates_map.items() 
            if k[1] == from_cur and k[2] == to_cur
        ]
        if matching_rates:
            # Sort by date proximity
            matching_rates.sort(key=lambda x: abs(pd.to_datetime(x[0]) - pd.to_datetime(date_str)))
            return amount * matching_rates[0][1]
        raise ValueError(f"No exchange rate found from {from_cur} to {to_cur} on or near {date_str}")