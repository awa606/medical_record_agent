from __future__ import annotations

import importlib
import sys
import traceback


def check_import(module_name: str):
    try:
        module = importlib.import_module(module_name)
        print(f"{module_name} importable: True")
        return module
    except Exception:
        print(f"{module_name} importable: False")
        traceback.print_exc()
        return None


def main() -> int:
    print(f"sys.executable: {sys.executable}")

    torch = check_import("torch")
    if torch is not None:
        print(f"torch.__version__: {getattr(torch, '__version__', '<unknown>')}")
        try:
            print(f"torch.cuda.is_available(): {torch.cuda.is_available()}")
        except Exception:
            print("torch.cuda.is_available(): <failed>")
            traceback.print_exc()
    else:
        print("torch.__version__: <not importable>")
        print("torch.cuda.is_available(): <not importable>")

    funasr = check_import("funasr")
    if funasr is not None:
        try:
            from funasr import AutoModel  # noqa: F401

            print("from funasr import AutoModel: True")
        except Exception:
            print("from funasr import AutoModel: False")
            traceback.print_exc()
    else:
        print("from funasr import AutoModel: False")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
