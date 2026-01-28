# 🇹🇳 Tunisian Arabic (Derja) AI Dataset

> The largest open-source collection of Tunisian Arabic text for NLP, LLM training, and sentiment analysis.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Dataset](https://img.shields.io/badge/Dataset-Tunisian_Derja-blue.svg)](https://github.com/bahaeddinmselmi/tunisian-arabic-ai-dataset)
[![Language](https://img.shields.io/badge/Language-Tunisian_Arabic-green.svg)]()

## 📖 Overview

The **Tunisian Arabic AI Dataset** is a comprehensive corpus aggregated from multiple social media platforms and online sources. It is designed to facilitate the development of Large Language Models (LLMs), chatbots, and translation systems for the **Tunisian dialect (Derja/Tounsi)**, which is a low-resource language variety often mixing Arabic script and "Arabizi" (Latin script).

This repository hosts a consolidated **334 MB+** archive containing over **170 data files**, ready for machine learning pipelines.

## 📦 Dataset Contents

The data is provided in a single Git LFS-tracked archive: **`tunisian_datasets.zip`**.

### 1. Social Media Corpus
Extensive scrapes from major social platforms, capturing authentic, informal, and code-switched communication:
*   **Reddit (r/Tunisia)**:
    *   `reddit_posts_all.jsonl`: Full historical post data.
    *   `reddit_comments_all.jsonl`: Deep comment threads, rich in Arabizi and English-Derja mixing.
*   **Facebook & Twitter/X**:
    *   Scraped posts and comments from public Tunisian communities.
    *   High density of native Arabic script Derja.
*   **YouTube**:
    *   Transcripts and comment sections from popular Tunisian channels.

### 2. Pre-Processing & Training Splits
Ready-to-use splits for Supervised Fine-Tuning (SFT) and Evaluation:
*   **`cleaned.jsonl`**: Text normalized to remove PII, excessive noise, and non-text artifacts.
*   **`dedup.jsonl`**: Determining deduplicated content to ensure model quality.
*   **Train/Test/Val Splits**:
    *   `train.jsonl` (~80%)
    *   `val.jsonl` (~10%)
    *   `test.jsonl` (~10%)

### 3. Specialized Sub-Datasets
*   **Lexicons**: `TuniziDataset.csv` for sentiment analysis and dialect classification.
*   **E-Commerce**: `products.json` and mock conversations for building commercial RAG (Retrieval-Augmented Generation) agents.

## 🚀 Getting Started

### Prerequisites
You strictly need **Git LFS** (Large File Storage) to download this dataset.

```bash
# Install Git LFS
git lfs install
```

### Installation
Clone the repository:

```bash
git clone https://github.com/bahaeddinmselmi/tunisian-arabic-ai-dataset.git
cd tunisian-arabic-ai-dataset
```

Unzip the main archive:

```bash
# Linux / Mac
unzip tunisian_datasets.zip -d data

# Windows
Expand-Archive tunisian_datasets.zip -DestinationPath data
```

## 🛠 Usage Example (Python)

Load the data easily using standard libraries:

```python
import pandas as pd

# Load the training split
df = pd.read_json('data/train.jsonl', lines=True)

print(f"Loaded {len(df)} samples")
print(df.head())
```

## 📊 Statistics
*   **Total Compressed Size**: ~334 MB
*   **Files**: 170+
*   **Languages**: Tunisian Arabic (Arabic script), Arabizi (Latin script), Code-switched (French/English/Derja).

## 🤝 Contribution
Contributions are welcome! If you have additional Tunisian datasets, please open a PR or an issue.

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.

---
**Keywords**: Tunisian Arabic, Derja, Tounsi, Arabizi, Low-resource NLP, Maghrebi Dialect, LLM Dataset, North Africa, AI Training Data.
