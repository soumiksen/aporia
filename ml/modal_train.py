"""Trains the leak classifier on a Modal GPU (A10G). YOU run this; nothing here runs locally.

One-time setup (needs a Modal account: `pip install modal && modal setup`):
    modal volume create aporia-leak-classifier
    modal volume put aporia-leak-classifier ml/data/leak_dataset.jsonl /data/leak_dataset.jsonl
    modal volume put aporia-leak-classifier ml/data/references /data/references
    modal volume put aporia-leak-classifier evals/redteam/problems /data/redteam_problems

Train (from the repository root):

    modal run ml/modal_train.py

Optional Weights & Biases logging: create a Modal secret `aporia-wandb` holding WANDB_API_KEY, then
run `APORIA_MODAL_WANDB=1 modal run ml/modal_train.py`.

Download the result (model, tokenizer, model_card.json) and export it:
    modal volume get aporia-leak-classifier /artifacts/classifier ml/artifacts/classifier
    cd ml && uv run python export/export_onnx.py --model-dir artifacts/classifier \\
        --data ../ml/data/leak_dataset.jsonl --out artifacts/onnx

The image installs `ml/requirements.txt`, which is generated from `ml/requirements.in`:
    cd ml && uv pip compile requirements.in -o requirements.txt --python-version 3.12
"""

import os
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
VOLUME_NAME = "aporia-leak-classifier"
REMOTE = "/root/aporia"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(ROOT / "ml" / "requirements.txt"))
    .add_local_dir(
        ROOT / "ml", f"{REMOTE}/ml", ignore=["artifacts", ".venv", "__pycache__", "*.pyc", "tests"]
    )
    .add_local_dir(  # the formatter and the guard package are shared with the API
        ROOT / "apps" / "api" / "app", f"{REMOTE}/apps/api/app", ignore=["__pycache__", "*.pyc"]
    )
)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
app = modal.App("aporia-leak-classifier")
secrets = [modal.Secret.from_name("aporia-wandb")] if os.environ.get("APORIA_MODAL_WANDB") else []


@app.function(
    image=image,
    gpu="A10G",
    volumes={"/vol": volume},
    secrets=secrets,
    timeout=3 * 60 * 60,
)
def train(epochs: int = 3, base_model: str = "microsoft/deberta-v3-base") -> str:
    import argparse
    import sys

    sys.path.insert(0, REMOTE)
    sys.path.insert(0, f"{REMOTE}/apps/api")
    from ml.train.train_classifier import run

    args = argparse.Namespace(
        smoke=False,
        data="/vol/data/leak_dataset.jsonl",
        references=["/vol/data/references", "/vol/data/redteam_problems"],
        out="/vol/artifacts/classifier",
        base_model=base_model,
        epochs=epochs,
        batch_size=16,
        lr=2e-5,
        patience=1,
        seed=42,
    )
    card = run(args)
    volume.commit()
    return f"done: t_low={card['t_low']:.3f} t_high={card['t_high']:.3f} (see model_card.json)"


@app.local_entrypoint()
def main(epochs: int = 3) -> None:
    print(train.remote(epochs=epochs))
    print(
        "Download with: modal volume get aporia-leak-classifier /artifacts/classifier "
        "ml/artifacts/classifier"
    )
