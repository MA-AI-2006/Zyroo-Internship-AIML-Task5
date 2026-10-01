"""
train_classifier.py
Week 3 — Steps 4, 5, 6: train a small TF-IDF classifier, compare simple
models (Logistic Regression, Linear SVM, Naive Bayes), evaluate them, and
save the best-performing model + vectorizer for app.py to load.

Run: python train_classifier.py
Outputs:
  model/vectorizer.pkl
  model/classifier.pkl
  model/metrics.json          (accuracy/precision/recall/F1 per model)
  model/confusion_matrix.txt  (confusion matrix of the chosen model)
"""

import json
import os
import pickle

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.svm import LinearSVC

from text_utils import clean_text

DATA_PATH = os.path.join(os.path.dirname(__file__), "dataset", "documents.csv")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "model")


def load_dataset():
    df = pd.read_csv(DATA_PATH)
    df["clean_text"] = df["text"].apply(clean_text)
    return df


def evaluate(model, X_test, y_test, labels):
    preds = model.predict(X_test)
    metrics = {
        "accuracy": round(accuracy_score(y_test, preds), 3),
        "precision": round(precision_score(y_test, preds, average="macro", zero_division=0), 3),
        "recall": round(recall_score(y_test, preds, average="macro", zero_division=0), 3),
        "f1": round(f1_score(y_test, preds, average="macro", zero_division=0), 3),
    }
    cm = confusion_matrix(y_test, preds, labels=labels)
    return metrics, cm


def main():
    os.makedirs(MODEL_DIR, exist_ok=True)
    df = load_dataset()
    labels = sorted(df["label"].unique())

    X_train, X_test, y_train, y_test = train_test_split(
        df["clean_text"], df["label"], test_size=0.3, random_state=42, stratify=df["label"]
    )

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)

    candidates = {
        "LogisticRegression": LogisticRegression(max_iter=1000),
        "LinearSVM": LinearSVC(),
        "NaiveBayes": MultinomialNB(),
    }

    all_metrics = {}
    trained_models = {}
    for name, clf in candidates.items():
        clf.fit(X_train_vec, y_train)
        metrics, cm = evaluate(clf, X_test_vec, y_test, labels)
        all_metrics[name] = {"metrics": metrics, "confusion_matrix": cm.tolist(), "labels": labels}
        trained_models[name] = clf
        print(f"{name}: {metrics}")

    # Select best model by F1 score (ties broken by accuracy)
    best_name = max(all_metrics, key=lambda n: (all_metrics[n]["metrics"]["f1"], all_metrics[n]["metrics"]["accuracy"]))
    best_model = trained_models[best_name]
    print(f"\nSelected best model: {best_name}")

    with open(os.path.join(MODEL_DIR, "vectorizer.pkl"), "wb") as f:
        pickle.dump(vectorizer, f)
    with open(os.path.join(MODEL_DIR, "classifier.pkl"), "wb") as f:
        pickle.dump({"model": best_model, "name": best_name, "labels": labels}, f)

    with open(os.path.join(MODEL_DIR, "metrics.json"), "w") as f:
        json.dump({"best_model": best_name, "all_models": all_metrics}, f, indent=2)

    with open(os.path.join(MODEL_DIR, "confusion_matrix.txt"), "w") as f:
        f.write(f"Best model: {best_name}\nLabels order: {labels}\n\n")
        for name, data in all_metrics.items():
            f.write(f"--- {name} ---\n")
            f.write(f"Metrics: {data['metrics']}\n")
            f.write("Confusion matrix (rows=true, cols=predicted):\n")
            for row in data["confusion_matrix"]:
                f.write(f"  {row}\n")
            f.write("\n")

    print("\nSaved model artifacts to:", MODEL_DIR)


if __name__ == "__main__":
    main()
