"""Exports the trained classifier to ONNX, quantizes it (dynamic int8) and checks parity.

    cd ml && uv run python export/export_onnx.py --model-dir artifacts/classifier \
        --data data/leak_dataset.jsonl --out artifacts/onnx

Output directory (what the API loads from APORIA_CLASSIFIER_DIR):
    model.onnx        int8, dynamically quantized (served)
    model_fp32.onnx   full precision (kept for the parity check)
    tokenizer.json    fast tokenizer
    model_card.json  thresholds and metrics from training

Parity (200 test records by default) is checked three ways and the script exits non-zero if any
fails:
  1. fp32 ONNX vs the PyTorch model: max |logit difference| <= FP32_TOLERANCE. Same weights and
     math, different runtime, so only float rounding is allowed.
  2. int8 ONNX vs the PyTorch model: max |logit difference| <= INT8_TOLERANCE.
  3. The text the API builds (tokenizers library) equals the text training built (transformers),
     and so do the token ids: guards against train/serve drift.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from ml.train.data import format_records, load_problem_texts, read_jsonl  # noqa: E402

# Same weights and operators in another runtime: differences are float rounding, around 1e-5.
# 1e-3 leaves headroom for different kernel orderings on other CPUs.
FP32_TOLERANCE = 1e-3
# Dynamic int8 quantization rounds the weights of every linear layer, which perturbs logits by a
# small fraction of their range. Logits of a trained classifier span roughly +-6; 0.25 moves a
# probability by at most 0.0625 where it is least certain (p = 0.5) and by under 0.01 beyond
# |logit| = 3, where t_low and t_high sit. A larger gap means the quantized model is not
# trustworthy for the cascade: re-train or serve the fp32 model (use --no-quantize).
INT8_TOLERANCE = 0.25


def max_abs_diff(a: Any, b: Any) -> float:
    import numpy as np

    return float(np.max(np.abs(np.asarray(a, dtype="float64") - np.asarray(b, dtype="float64"))))


def torch_logits(model_dir: Path, texts: list[str], tokenizer: Any, max_length: int) -> Any:
    import numpy as np
    import torch
    from transformers import AutoModelForSequenceClassification

    model = AutoModelForSequenceClassification.from_pretrained(str(model_dir)).eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), 16):
            enc = tokenizer(
                texts[i : i + 16], truncation=True, max_length=max_length, padding=True,
                return_tensors="pt",
            )  # fmt: skip
            out.append(model(**enc).logits.numpy())
    return np.concatenate(out)


def onnx_logits(path: Path, texts: list[str], tokenizer: Any, max_length: int) -> Any:
    import numpy as np
    import onnxruntime as ort

    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    wanted = {i.name for i in session.get_inputs()}
    out = []
    for i in range(0, len(texts), 16):
        enc = tokenizer(
            texts[i : i + 16], truncation=True, max_length=max_length, padding=True,
            return_tensors="np",
        )  # fmt: skip
        feeds = {k: v.astype("int64") for k, v in enc.items() if k in wanted}
        out.append(session.run(None, feeds)[0])
    return np.concatenate(out)


def export_fp32(model_dir: Path, out: Path) -> Path:
    """fp32 ONNX via optimum (it handles the DeBERTa graph and dynamic axes)."""
    from optimum.onnxruntime import ORTModelForSequenceClassification

    tmp = out / "fp32_tmp"
    ORTModelForSequenceClassification.from_pretrained(str(model_dir), export=True).save_pretrained(
        str(tmp)
    )
    target = out / "model_fp32.onnx"
    shutil.move(str(tmp / "model.onnx"), str(target))
    shutil.rmtree(tmp, ignore_errors=True)
    return target


def quantize(fp32: Path, int8: Path) -> None:
    from onnxruntime.quantization import QuantType, quantize_dynamic

    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)


def check_tokenizer_parity(
    model_dir: Path, tokenizer: Any, records: list[dict], problems: dict, max_length: int
) -> list[str]:
    """The API's tokenizers-library path must build the same text and ids as training."""
    from app.guard.classifier_format import format_input, reference_text
    from tokenizers import Tokenizer

    fast = Tokenizer.from_file(str(model_dir / "tokenizer.json"))

    class Adapter:
        def encode(self, text: str) -> list[int]:
            return fast.encode(text, add_special_tokens=False).ids

        def decode(self, ids: list[int]) -> str:
            return fast.decode(ids)

    train_texts = format_records(records, problems, tokenizer, max_length)
    problems_found = []
    for r, train_text in zip(records, train_texts, strict=True):
        p = problems[r["problem_slug"]]
        api_text = format_input(
            r["level"],
            p["summary"],
            reference_text(p["reference"]),
            r["reply"],
            Adapter(),
            max_length,
        )
        if api_text != train_text:
            problems_found.append(f"{r['id']}: formatted text differs")
            continue
        ids_train = tokenizer(train_text, truncation=True, max_length=max_length)["input_ids"]
        fast.enable_truncation(max_length)
        if fast.encode(api_text).ids != ids_train:
            problems_found.append(f"{r['id']}: token ids differ")
    return problems_found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--model-dir", required=True, help="trained model directory (HF format)")
    ap.add_argument("--data", required=True, help="leak_dataset.jsonl (or a smoke dataset)")
    ap.add_argument("--references", nargs="*", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=200, help="test records for the parity check")
    ap.add_argument("--no-quantize", action="store_true", help="serve fp32 (no int8 file)")
    args = ap.parse_args()

    from transformers import AutoTokenizer

    model_dir, out = Path(args.model_dir), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    card_path = model_dir.parent / "model_card.json"
    card = json.loads(card_path.read_text()) if card_path.exists() else {}
    max_length = int(card.get("max_length", 512))

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    tokenizer.backend_tokenizer.save(str(out / "tokenizer.json"))
    (out / "model_card.json").write_text(json.dumps(card, indent=2) + "\n")

    records = [r for r in read_jsonl(Path(args.data)) if r["split"] == "test"][: args.n]
    problems = load_problem_texts([Path(d) for d in args.references] if args.references else None)
    texts = format_records(records, problems, tokenizer, max_length)
    print(f"parity set: {len(texts)} test records, max_length {max_length}")

    fp32 = export_fp32(model_dir, out)
    failures: list[str] = []
    reference = torch_logits(model_dir, texts, tokenizer, max_length)
    d32 = max_abs_diff(reference, onnx_logits(fp32, texts, tokenizer, max_length))
    print(f"fp32 ONNX vs PyTorch: max |logit diff| = {d32:.6f} (tolerance {FP32_TOLERANCE})")
    if d32 > FP32_TOLERANCE:
        failures.append("fp32 parity")

    served = out / "model.onnx"
    if args.no_quantize:
        shutil.copy(fp32, served)
    else:
        quantize(fp32, served)
        d8 = max_abs_diff(reference, onnx_logits(served, texts, tokenizer, max_length))
        print(f"int8 ONNX vs PyTorch: max |logit diff| = {d8:.6f} (tolerance {INT8_TOLERANCE})")
        if d8 > INT8_TOLERANCE:
            failures.append("int8 parity")

    # tokenizer.json written above is the one the API uses: compare train and serve paths
    shutil.copy(out / "tokenizer.json", model_dir / "tokenizer.json")
    mismatches = check_tokenizer_parity(model_dir, tokenizer, records, problems, max_length)
    print(f"train/serve formatting parity: {len(mismatches)} mismatches of {len(records)}")
    for m in mismatches[:5]:
        print("  ", m)
    if mismatches:
        failures.append("formatter/tokenizer parity")

    sizes = {p.name: f"{p.stat().st_size / 1e6:.1f} MB" for p in out.glob("*.onnx")}
    print("artifacts:", sizes)
    if failures:
        print("FAILED:", ", ".join(failures))
        return 1
    print("export OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
