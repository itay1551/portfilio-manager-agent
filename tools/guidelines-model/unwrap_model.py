"""Extract the plain sklearn Pipeline from the project's wrapped joblib format.

The guidelines agent saves models as::

    {"model": Pipeline(...), "saved_at": "...", "sklearn_version": "...", "type": "..."}

MLServer expects ``joblib.load()`` to return the model directly.
"""

import sys
import os
import joblib


def main():
    src = sys.argv[1]
    dst = sys.argv[2]

    payload = joblib.load(src)
    model = (
        payload["model"]
        if isinstance(payload, dict) and "model" in payload
        else payload
    )

    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    joblib.dump(model, dst)
    print(f"Unwrapped model saved to {dst}")


if __name__ == "__main__":
    main()
