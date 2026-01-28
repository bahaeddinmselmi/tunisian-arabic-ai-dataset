import os
import subprocess
from prefect import flow, task


@task
def ingest():
    # X
    if os.getenv("X_BEARER_TOKEN"):
        subprocess.run(["python", "collectors/collect_x.py", "--limit", "2000", "--out", "data/raw/x_tn.jsonl"], check=True)
    else:
        print("[ingest] Skip X: missing X_BEARER_TOKEN")

    # Reddit
    if os.getenv("REDDIT_CLIENT_ID") and os.getenv("REDDIT_CLIENT_SECRET"):
        subprocess.run(["python", "collectors/collect_reddit.py", "--sub", "Tunisia", "--limit", "2000", "--out", "data/raw/reddit_tn.jsonl"], check=True)
    else:
        print("[ingest] Skip Reddit: missing credentials")

    # YouTube
    if os.getenv("YOUTUBE_API_KEY") and os.getenv("YT_CHANNEL_ID"):
        subprocess.run(["python", "collectors/collect_youtube.py", "--channel", os.getenv("YT_CHANNEL_ID"), "--out", "data/raw/youtube_tn.jsonl"], check=True)
    else:
        print("[ingest] Skip YouTube: missing YOUTUBE_API_KEY or YT_CHANNEL_ID")


@task
def preprocess():
    subprocess.run(["python", "processors/clean.py", "--raw_dir", "data/raw", "--out", "data/processed/cleaned.jsonl"], check=True)
    subprocess.run(["python", "processors/dedup.py", "--in", "data/processed/cleaned.jsonl", "--out", "data/processed/dedup.jsonl"], check=True)
    subprocess.run(["python", "processors/build_sft.py", "--in", "data/processed/dedup.jsonl", "--out", "data/processed/sft.jsonl"], check=True)
    subprocess.run(["python", "processors/split.py", "--in", "data/processed/sft.jsonl", "--out_dir", "data/splits"], check=True)


@task
def train_and_merge():
    subprocess.run(["python", "training/train_sft.py"], check=True)
    subprocess.run(["python", "training/merge_lora.py"], check=True)


@flow
def nightly():
    ingest()
    preprocess()
    train_and_merge()
    print("[flow] Nightly pipeline completed.")


if __name__ == "__main__":
    nightly()
