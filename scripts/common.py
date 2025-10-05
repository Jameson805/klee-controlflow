import json
import pandas as pd

def load_combined_json(input_json: str) -> pd.DataFrame:
    """Load the JSON produced by compare_with_ctchecker.py into a DataFrame.

    Support two forms:
      - A dict with keys {"data": [...], "dtypes": {...}}
      - A plain records-orient JSON array
    """
    with open(input_json, "r") as f:
        obj = json.load(f)

    if isinstance(obj, dict) and "data" in obj:
        df = pd.DataFrame(obj["data"])
        dtypes = obj.get("dtypes", {})
        for col, dtype in dtypes.items():
            if col in df.columns:
                try:
                    df[col] = df[col].astype(dtype)
                except Exception:
                    logging.debug("failed to cast column %s to %s", col, dtype)
    else:
        df = pd.read_json(input_json, orient="records")

    return df

def save_combined_json(df: pd.DataFrame, output_json: str) -> None:
    """Save both data and dtypes so consumers can restore original pandas dtypes"""
    data_json = df.to_json(orient="records")
    dtypes = df.dtypes.astype(str).to_dict()

    out_obj = {
        "data": json.loads(data_json),
        "dtypes": dtypes
    }

    with open(output_json, "w") as f:
        json.dump(out_obj, f, indent=2)
