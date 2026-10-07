"""Candidate 9 - SetFit (experimental; only if it passes the feasibility gate).

SetFit first fine-tunes the MiniLM encoder with contrastive learning (pairs of training
complaints: "same class" should get closer vectors, "different class" further apart),
then trains a Logistic Regression head on the new vectors. Designed for small datasets.
Fixed settings (config.SETFIT): 20 pair iterations, 1 epoch, batch size 16, seed per fit.
Explanation: as candidate 8, only similar-training-complaint evidence, no word weights.
"""
import numpy as np

from safespeak_ml import config
from safespeak_ml.features import embeddings  # noqa: F401  (sets offline mode)
from safespeak_ml.models.base import Candidate


class SetFitClassifier(Candidate):
    number, name, title, kind = 9, "setfit_classifier", "SetFit (contrastive MiniLM fine-tuning + LR head)", "setfit"

    def fit(self, texts, labels):
        import torch
        from datasets import Dataset
        from setfit import SetFitModel, Trainer, TrainingArguments

        torch.manual_seed(self.seed)
        self.classes_ = sorted(set(labels))
        index = {c: i for i, c in enumerate(self.classes_)}
        self.model = SetFitModel.from_pretrained(
            str(config.ENCODER_DIR), head_params={"class_weight": "balanced", "max_iter": 5000}
        )
        args = TrainingArguments(
            batch_size=config.SETFIT["batch_size"],
            num_epochs=config.SETFIT["num_epochs"],
            num_iterations=config.SETFIT["num_iterations"],
            seed=self.seed,
            report_to="none",
            show_progress_bar=False,
        )
        dataset = Dataset.from_dict({"text": list(texts), "label": [index[y] for y in labels]})
        Trainer(model=self.model, args=args, train_dataset=dataset).train()
        return self

    def _proba(self, texts):
        proba = self.model.predict_proba(list(texts))
        return np.asarray(proba.cpu().numpy() if hasattr(proba, "cpu") else proba, dtype=float)

    def scores(self, texts):
        return np.log(np.clip(self._proba(texts), 1e-12, 1.0))

    def predict(self, texts):
        return [self.classes_[i] for i in self._proba(texts).argmax(axis=1)]

    def describe(self):
        return {
            **super().describe(),
            "features": f"{config.ENCODER_REPO}@{config.ENCODER_REVISION}, contrastively fine-tuned",
            "algorithm": "SetFit (sentence-transformers fine-tuning + LogisticRegression head)",
            "hyperparameters": config.SETFIT,
            "seed": self.seed,
        }

    def save(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        self.model.save_pretrained(str(directory / "setfit_body"))
        return ["setfit_body/"]
