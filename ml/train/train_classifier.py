"""Fine-tunes DeBERTa-v3 as a binary leak classifier (leak = 1, safe = 0).

Full training needs a GPU: run it on Modal (`ml/modal_train.py`). Locally only the smoke test:

    cd ml && uv run python train/train_classifier.py --smoke

Defaults follow the stage plan: max_length 512, lr 2e-5, 3 epochs, batch 16, weight decay 0.01,
warmup 10%, fp16 on a GPU, early stopping on validation recall at FPR <= 5%, class weights when the
classes are imbalanced, Weights & Biases when WANDB_API_KEY is set.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from ml.common import ML_DIR  # noqa: E402
from ml.train.data import file_hash, format_records, load_problem_texts, read_jsonl  # noqa: E402
from ml.train.metrics import recall_at_fpr, roc_auc, summary  # noqa: E402
from ml.train.thresholds import choose_thresholds, routing_shares, write_model_card  # noqa: E402

BASE_MODEL = "microsoft/deberta-v3-base"
SMOKE_MODEL = "microsoft/deberta-v3-xsmall"
DATASET = ML_DIR / "data" / "leak_dataset.jsonl"
SMOKE_MAX_LENGTH = 256
SMOKE_BATCH_SIZE = 4
IMBALANCE_TRIGGER = 0.1  # use class weights when the classes differ by more than 10 points


def class_weights(labels: list[int]) -> list[float] | None:
    """Inverse-frequency weights for [safe, leak], or None when the classes are balanced."""
    n = len(labels)
    pos = sum(labels)
    if n == 0 or pos in (0, n) or abs(pos / n - 0.5) <= IMBALANCE_TRIGGER:
        return None
    return [n / (2 * (n - pos)), n / (2 * pos)]


def softmax_leak(logits: Any) -> list[float]:
    import numpy as np

    z = np.asarray(logits, dtype="float64")
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return (e[:, 1] / e.sum(axis=1)).tolist()


def build_trainer(
    args: argparse.Namespace, train_ds: Any, val_ds: Any, model: Any, weights: Any
) -> Any:
    import torch
    from transformers import EarlyStoppingCallback, Trainer, TrainingArguments

    gpu = torch.cuda.is_available()

    class WeightedTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
            labels = inputs.pop("labels")
            outputs = model(**inputs)
            w = torch.tensor(weights, device=outputs.logits.device, dtype=outputs.logits.dtype)
            loss = torch.nn.functional.cross_entropy(outputs.logits, labels, weight=w)
            return (loss, outputs) if return_outputs else loss

    def compute_metrics(eval_pred: Any) -> dict[str, float]:
        logits, labels = eval_pred
        scores = softmax_leak(logits)
        y = [int(v) for v in labels]
        return {"recall_at_fpr": recall_at_fpr(y, scores)[0], "roc_auc": roc_auc(y, scores)}

    smoke = args.smoke
    kwargs: dict[str, Any] = dict(
        output_dir=str(Path(args.out) / "checkpoints"),
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size * 2,
        weight_decay=0.01,
        warmup_ratio=0.1,
        fp16=gpu,
        use_cpu=not gpu,
        report_to=["wandb"] if os.environ.get("WANDB_API_KEY") else "none",
        save_total_limit=1,
        logging_steps=10,
        seed=args.seed,
        load_best_model_at_end=True,
        metric_for_best_model="recall_at_fpr",
        greater_is_better=True,
    )
    if smoke:
        kwargs.update(per_device_train_batch_size=SMOKE_BATCH_SIZE, per_device_eval_batch_size=8)
        kwargs.update(max_steps=50, eval_strategy="steps", eval_steps=25, save_strategy="steps",
                      save_steps=25)  # fmt: skip
    else:
        kwargs.update(num_train_epochs=args.epochs, eval_strategy="epoch", save_strategy="epoch")
    trainer_cls = WeightedTrainer if weights else Trainer
    return trainer_cls(
        model=model,
        args=TrainingArguments(**kwargs),
        train_dataset=train_ds,
        eval_dataset=val_ds,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=args.patience)],
    )


class TextDataset:
    """Tokenized records as a torch dataset."""

    def __init__(self, encodings: dict[str, list[list[int]]], labels: list[int]) -> None:
        self.encodings, self.labels = encodings, labels

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, i: int) -> dict[str, Any]:
        import torch

        item = {k: torch.tensor(v[i]) for k, v in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[i])
        return item


def predict(trainer: Any, ds: Any) -> list[float]:
    return softmax_leak(trainer.predict(ds).predictions)


def run(args: argparse.Namespace) -> dict[str, Any]:
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        DataCollatorWithPadding,
    )

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.smoke:
        from ml.data.smoke_dataset import build

        records, problems = build(200)
        data_path = out / "smoke_dataset.jsonl"
        data_path.write_text("".join(json.dumps(r) + "\n" for r in records))
        base = args.base_model or SMOKE_MODEL
    else:
        data_path = Path(args.data)
        records = read_jsonl(data_path)
        problems = load_problem_texts(
            [Path(d) for d in args.references] if args.references else None
        )
        base = args.base_model or BASE_MODEL
    splits = {s: [r for r in records if r["split"] == s] for s in ("train", "val", "test")}
    missing = {r["problem_slug"] for r in records} - set(problems)
    if missing:
        raise SystemExit(f"no reference/summary for problems: {sorted(missing)[:5]}")
    print({s: len(v) for s, v in splits.items()}, "base model:", base)

    tokenizer = AutoTokenizer.from_pretrained(base)
    max_length = SMOKE_MAX_LENGTH if args.smoke else 512  # the smoke run only checks plumbing
    encoded = {}
    for name, recs in splits.items():
        texts = format_records(recs, problems, tokenizer, max_length)
        enc = tokenizer(texts, truncation=True, max_length=max_length)
        encoded[name] = (
            TextDataset(dict(enc), [r["label"] for r in recs]),
            [r["label"] for r in recs],
        )
    model = AutoModelForSequenceClassification.from_pretrained(base, num_labels=2)
    weights = class_weights(encoded["train"][1])
    trainer = build_trainer(args, encoded["train"][0], encoded["val"][0], model, weights)
    trainer.data_collator = DataCollatorWithPadding(tokenizer)
    trainer.train()

    val_scores = predict(trainer, encoded["val"][0])
    test_scores = predict(trainer, encoded["test"][0])
    thresholds = choose_thresholds(encoded["val"][1], val_scores)
    operating = thresholds["t_high"]
    card = write_model_card(
        out / "model_card.json",
        thresholds=thresholds,
        val_metrics=summary(encoded["val"][1], val_scores, operating),
        test_metrics=summary(encoded["test"][1], test_scores, operating),
        dataset_hash=file_hash(data_path),
        base_model=base,
        extra={
            "smoke": bool(args.smoke),
            "max_length": max_length,
            "class_weights": weights,
            "routing_share_test": routing_shares(
                test_scores, thresholds["t_low"], thresholds["t_high"]
            ),
            "n": {s: len(v) for s, v in splits.items()},
        },
    )  # fmt: skip
    model_dir = out / "model"
    trainer.save_model(str(model_dir))
    tokenizer.save_pretrained(str(model_dir))
    (out / "scores_test.json").write_text(
        json.dumps(
            {
                "y": encoded["test"][1],
                "scores": test_scores,
                "ids": [r["id"] for r in splits["test"]],
            }
        )
    )
    if args.smoke:
        print("SMOKE RUN: templated plumbing data; these numbers mean nothing.")
    print(json.dumps(card, indent=2))
    return card


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "--smoke", action="store_true", help="50 steps, xsmall model, 200 templated records"
    )
    ap.add_argument("--data", default=str(DATASET))
    ap.add_argument("--references", nargs="*", default=None, help="dirs of verified problem JSON")
    ap.add_argument("--out", default=None, help="artifact directory (default ml/artifacts/<run>)")
    ap.add_argument("--base-model", default=None)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--patience", type=int, default=1)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    args.out = args.out or str(ML_DIR / "artifacts" / ("smoke" if args.smoke else "classifier"))
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
