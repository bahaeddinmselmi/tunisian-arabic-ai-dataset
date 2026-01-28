# TunAI Consolidated Datasets 🇹🇳

This repository contains a comprehensive collection of datasets for **Tunisian Arabic (Derja)** AI training and development.

## 📦 Content

The repository hosts a single compressed archive: **`tunisian_datasets.zip`** (~334 MB).

When likely unzipped, this archive contains **170+ data files**, including:
*   **Social Media Data**: Scraped comments and posts from **Reddit** (r/Tunisia), **Facebook**, and **Twitter**.
*   **YouTube**: Transcripts and comments from Tunisian channels.
*   **E-commerce**: Product catalogs and mock conversations for RAG.
*   **Processed Data**:
    *   `cleaned.jsonl`: Cleaned and normalized text.
    *   `dedup.jsonl`: Deduplicated dataset (large).
    *   `train.jsonl` / `val.jsonl` / `test.jsonl`: Pre-split datasets for training LLMs (e.g., QLoRA SFT).
*   **Lexicons**: Word lists and sentiment/classification datasets (`TuniziDataset.csv`).

## 🚀 Usage

1.  **Clone the repository** (ensure you have Git LFS installed):
    ```bash
    git lfs install
    git clone https://github.com/bahaeddinmselmi/tunai-consolidated-datasets.git
    ```

2.  **Unzip the dataset**:
    ```bash
    unzip tunisian_datasets.zip -d datasets
    ```

3.  **Explore**:
    The data is formatted primarily in `.jsonl` (JSON Lines), suitable for most modern NLP libraries (HuggingFace Datasets, Pandas, etc.).

## ⚠️ Notes
*   **Git LFS**: The main zip file is stored using Git Large File Storage. You must have Git LFS installed to pull the actual file content.
*   **Privacy**: This dataset contains public social media data. Please use responsibly and respect privacy regulations.

## License
MIT
