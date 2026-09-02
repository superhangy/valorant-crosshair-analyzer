"""
Train a small good-vs-gun-viewmodel-as-head classifier on the box crops from
extract_gunmodel_classifier_dataset.py (dataset_gunmodel_classifier/{good,gunmodel}/).

Same architecture as train_ally_classifier.py (frozen ResNet18 backbone with
layer4 unfrozen at a lower LR, class-weighted loss for the imbalanced
good/gunmodel split, heavy augmentation).

Usage:
    python train_gunmodel_classifier.py
"""

import random
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent
DATASET_DIR = REPO_ROOT / "dataset_gunmodel_classifier"
WEIGHTS_OUT = REPO_ROOT / "gunmodel_classifier_head.pt"

VAL_FRACTION = 0.2
SEED = 42
BATCH_SIZE = 16
EPOCHS = 30
LR = 1e-3
BACKBONE_LR = 1e-5
UNFREEZE_LAYERS = ["layer4"]
WEIGHT_DECAY = 1e-4

CLASSES = ["good", "gunmodel"]  # index 0 / 1


class CropDataset(Dataset):
    def __init__(self, items, train: bool):
        self.items = items
        if train:
            self.tf = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.RandomHorizontalFlip(),
                transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.05),
                transforms.RandomAffine(degrees=5, translate=(0.05, 0.05), scale=(0.9, 1.1)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])
        else:
            self.tf = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        path, label = self.items[idx]
        img = Image.open(path).convert("RGB")
        return self.tf(img), label


def load_items():
    items = []
    for cls_idx, cls_name in enumerate(CLASSES):
        cls_dir = DATASET_DIR / cls_name
        for path in sorted(cls_dir.glob("*.jpg")):
            items.append((path, cls_idx))
    return items


def stratified_split(items):
    rng = random.Random(SEED)
    by_class = {0: [], 1: []}
    for path, label in items:
        by_class[label].append((path, label))
    train, val = [], []
    for label, group in by_class.items():
        rng.shuffle(group)
        n_val = max(1, int(len(group) * VAL_FRACTION))
        val.extend(group[:n_val])
        train.extend(group[n_val:])
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def build_model():
    backbone = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    for p in backbone.parameters():
        p.requires_grad = False
    for name in UNFREEZE_LAYERS:
        for p in getattr(backbone, name).parameters():
            p.requires_grad = True
    in_features = backbone.fc.in_features
    backbone.fc = nn.Sequential(
        nn.Linear(in_features, 64),
        nn.ReLU(),
        nn.Dropout(0.4),
        nn.Linear(64, 2),
    )
    return backbone


def evaluate(model, loader, device):
    model.eval()
    tp = fp = fn = tn = 0  # positive class = "gunmodel" (index 1)
    correct = total = 0
    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            logits = model(x)
            preds = logits.argmax(dim=1)
            correct += (preds == y).sum().item()
            total += y.size(0)
            for p, t in zip(preds.tolist(), y.tolist()):
                if p == 1 and t == 1:
                    tp += 1
                elif p == 1 and t == 0:
                    fp += 1
                elif p == 0 and t == 1:
                    fn += 1
                else:
                    tn += 1
    acc = correct / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return acc, precision, recall, (tp, fp, fn, tn)


def main():
    items = load_items()
    n_good = sum(1 for _, l in items if l == 0)
    n_gunmodel = sum(1 for _, l in items if l == 1)
    print(f"dataset: good={n_good} gunmodel={n_gunmodel} total={len(items)}")
    if len(items) < 20:
        raise SystemExit("Too few images -- run extract_gunmodel_classifier_dataset.py first")

    train_items, val_items = stratified_split(items)
    print(f"train={len(train_items)} val={len(val_items)}")

    train_ds = CropDataset(train_items, train=True)
    val_ds = CropDataset(val_items, train=False)
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model().to(device)

    n_train_good = sum(1 for _, l in train_items if l == 0)
    n_train_gunmodel = sum(1 for _, l in train_items if l == 1)
    weights = torch.tensor(
        [len(train_items) / (2 * n_train_good), len(train_items) / (2 * n_train_gunmodel)],
        dtype=torch.float32,
    ).to(device)
    criterion = nn.CrossEntropyLoss(weight=weights)
    backbone_params = [p for name in UNFREEZE_LAYERS for p in getattr(model, name).parameters()]
    optimizer = torch.optim.Adam(
        [
            {"params": model.fc.parameters(), "lr": LR},
            {"params": backbone_params, "lr": BACKBONE_LR},
        ],
        weight_decay=WEIGHT_DECAY,
    )

    best_val_acc = 0.0
    for epoch in range(1, EPOCHS + 1):
        model.train()
        total_loss = 0.0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            loss = criterion(model(x), y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * x.size(0)

        val_acc, val_prec, val_rec, _ = evaluate(model, val_loader, device)
        print(f"epoch {epoch:2d}  train_loss={total_loss/len(train_items):.4f}  "
              f"val_acc={val_acc:.3f}  val_precision(gunmodel)={val_prec:.3f}  "
              f"val_recall(gunmodel)={val_rec:.3f}")

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), WEIGHTS_OUT)

    print(f"\nbest val_acc={best_val_acc:.3f} -> head weights saved to {WEIGHTS_OUT}")
    final_acc, final_prec, final_rec, confusion = evaluate(model, val_loader, device)
    tp, fp, fn, tn = confusion
    print(f"final epoch confusion (val, n={len(val_items)}): "
          f"tp={tp} fp={fp} fn={fn} tn={tn}")


if __name__ == "__main__":
    main()
