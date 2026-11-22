import torch
import torch.nn as nn
import torch.optim as optim
import matplotlib.pyplot as plt
from torch.utils.data import DataLoader

from torchvision import datasets, transforms, models

CLASSES = ["none", "paper", "rock", "scissors"]

class smallCNN(nn.Module):
    def __init__(self, num_classes=len(CLASSES)):
        super().__init__()

        def block(c_in, c_out):
            return nn.Sequential(
                nn.Conv2d(c_in, c_out, 3, padding=1),
                nn.BatchNorm2d(c_out),
                nn.ReLU(),
                nn.MaxPool2d(2),
            )

        self.features = nn.Sequential(block(1,32), block(32, 64), block(64, 128))
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(0.5),
            nn.Linear(128, num_classes),
        )

    def forward( self, x):
        return self.classifier(self.pool(self.features(x)))

def build_mobilenet(num_classes=len(CLASSES), freeze=True):
    m = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.DEFAULT)
    if freeze:
        for p in m.parameters():
            p.requires_grad = False
    n = m.classifier[1].in_features
    m.classifier = nn.Sequential(
        nn.Dropout(0.3),
        nn.Linear(n, 128),
        nn.ReLU(),
        nn.Dropout(0.3),
        nn.Linear(128, num_classes),
    )
    return m

def unfreeze_last_blocks(m, n_blocks=2):
    params = list(m.features[-n_blocks:].parameters())
    for p in params:
        p.requires_grad = True
    return params

def save(model, path):
    torch.save(model.state_dict(), path)

def load(kind, path, device="cpu"):
    m = smallCNN() if kind == "cnn" else build_mobilenet(freeze=False)
    m.load_state_dict(torch.load(path, map_location=device))
    return m.eval().to(device)

# =====================================================================
#  Data, training and evaluation helpers (used by results.ipynb)
#  Paste this below load(). Nothing here runs on import.
# =====================================================================
import time
from pathlib import Path

import numpy as np
from PIL import Image
from torch.utils.data import DataLoader

KAGGLE = Path(__file__).resolve().parent / "data" / "kaggle"
IMAGENET_MEAN, IMAGENET_STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]

# input size and channels per model: the CNN sees 1-channel gray, MobileNet 3 copies of gray
SETTINGS = {"cnn": {"size": 96, "channels": 1},
            "mobilenet": {"size": 224, "channels": 3}}


def make_transform(kind, train):
    """Grayscale (like the camera), resized; random changes only when training."""
    size, ch = SETTINGS[kind]["size"], SETTINGS[kind]["channels"]
    steps = [transforms.Grayscale(num_output_channels=ch)]
    if train:
        steps += [transforms.RandomResizedCrop(size, scale=(0.8, 1.0)),
                  transforms.RandomRotation(30, fill=255),   # white corners, like the backgrounds
                  transforms.RandomHorizontalFlip(),
                  transforms.ColorJitter(brightness=0.4, contrast=0.4)]
    else:
        steps += [transforms.Resize((size, size))]
    steps.append(transforms.ToTensor())
    if ch == 3:
        steps.append(transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD))
    else:
        steps.append(transforms.Normalize([0.5], [0.5]))
    return transforms.Compose(steps)


class _ToClasses:
    """Maps an ImageFolder label (folder index) to its index in CLASSES.
    The Kaggle folders have no 'none', so paper/rock/scissors become 1/2/3, not 0/1/2."""

    def __init__(self, folder_classes):
        self.lookup = [CLASSES.index(c) for c in folder_classes]

    def __call__(self, i):
        return self.lookup[i]


def make_dataset(kind, split, root=KAGGLE):
    """split: 'train', 'validation' or 'test' (a folder of class subfolders)."""
    train = split == "train"
    ds = datasets.ImageFolder(Path(root) / split, transform=make_transform(kind, train))
    ds.target_transform = _ToClasses(ds.classes)
    return ds


def make_loaders(kind, root=KAGGLE, batch_size=32):
    """{'train', 'validation', 'test'} DataLoaders."""
    return {split: DataLoader(make_dataset(kind, split, root), batch_size=batch_size,
                              shuffle=(split == "train"), num_workers=0)
            for split in ("train", "validation", "test")}


def run_epoch(model, loader, criterion, device, optimizer=None):
    """One pass over loader; trains if an optimizer is given. Returns (loss, accuracy)."""
    training = optimizer is not None
    model.train(training)
    total_loss, correct, n = 0.0, 0, 0
    with torch.set_grad_enabled(training):
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            out = model(x)
            loss = criterion(out, y)
            if training:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
            total_loss += loss.item() * len(y)
            correct += (out.argmax(1) == y).sum().item()
            n += len(y)
    return total_loss / n, correct / n


def train(model, loaders, epochs=10, lr=1e-3, device="cpu", unfreeze_at=None, weights_path=None):
    """Train on loaders['train'], check loaders['validation'] after each epoch.

    unfreeze_at: epoch (0-based) at which MobileNet's last blocks start training too.
    Keeps the weights of the best validation epoch (and saves them if weights_path is given).
    Returns a history dict of lists: train_loss, train_acc, val_loss, val_acc, seconds.
    """
    model.to(device)
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                                  lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max", factor=0.5, patience=2)
    hist = {k: [] for k in ("train_loss", "train_acc", "val_loss", "val_acc", "seconds")}
    best_acc, best_state = -1.0, None

    for epoch in range(epochs):
        if unfreeze_at is not None and epoch == unfreeze_at:
            # add to the SAME optimizer so the scheduler keeps controlling it
            optimizer.add_param_group({"params": unfreeze_last_blocks(model), "lr": lr / 10})
            print("unfroze the last MobileNet blocks")
        t0 = time.time()
        tr_loss, tr_acc = run_epoch(model, loaders["train"], criterion, device, optimizer)
        va_loss, va_acc = run_epoch(model, loaders["validation"], criterion, device)
        scheduler.step(va_acc)
        for k, v in zip(hist, (tr_loss, tr_acc, va_loss, va_acc, time.time() - t0)):
            hist[k].append(v)
        print(f"epoch {epoch + 1:2d}/{epochs}  train {tr_acc:.3f} (loss {tr_loss:.3f})  "
              f"val {va_acc:.3f} (loss {va_loss:.3f})  {hist['seconds'][-1]:.0f} s")
        if va_acc > best_acc:
            best_acc = va_acc
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    if weights_path:
        Path(weights_path).parent.mkdir(parents=True, exist_ok=True)
        save(model, weights_path)
    return hist


def predict_loader(model, loader, device="cpu"):
    """(true labels, predicted labels, probabilities) over a whole loader."""
    model.eval().to(device)
    ys, ps = [], []
    with torch.no_grad():
        for x, y in loader:
            ps.append(torch.softmax(model(x.to(device)), 1).cpu())
            ys.append(y)
    probs = torch.cat(ps).numpy()
    return torch.cat(ys).numpy(), probs.argmax(1), probs


def confusion(y_true, y_pred, n=len(CLASSES)):
    """n x n counts: rows = true class, columns = predicted class."""
    cm = np.zeros((n, n), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[t, p] += 1
    return cm


def predict_frame(model, kind, img, crop=0.8, device="cpu"):
    """Predict one camera picture (2-D uint8 array). Returns (class name, probabilities)."""
    h, w = img.shape
    s = int(round(min(h, w) * crop))
    y0, x0 = (h - s) // 2, (w - s) // 2
    pil = Image.fromarray(img[y0:y0 + s, x0:x0 + s])
    x = make_transform(kind, train=False)(pil).unsqueeze(0).to(device)
    model.eval().to(device)
    with torch.no_grad():
        p = torch.softmax(model(x), 1)[0].cpu().numpy()
    return CLASSES[int(p.argmax())], p


if __name__ == "__main__":
    # python model.py: train the small CNN on the Kaggle pictures and plot the curves
    TRAIN_DATA_PATH = './data/kaggle/train'
    TEST_DATA_PATH = './data/kaggle/test'

    train_transform = transforms.Compose([
        transforms.Grayscale(num_output_channels=1),
        transforms.RandomResizedCrop(96, scale=(0.8, 1.0)),
        transforms.RandomRotation(30, fill=255),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(brightness=0.4, contrast=0.4),
        transforms.ToTensor(),
        transforms.Normalize([0.5], [0.5]),
    ])

    test_transform = transforms.Compose([
        transforms.Grayscale(num_output_channels=1),
        transforms.Resize((96, 96)),
        transforms.ToTensor(),
        transforms.Normalize([0.5], [0.5]),
    ])

    train_dataset = datasets.ImageFolder(TRAIN_DATA_PATH, transform=train_transform,
                                         target_transform=lambda i: i + 1)
    test_dataset = datasets.ImageFolder(TEST_DATA_PATH, transform=test_transform,
                                        target_transform=lambda i: i + 1)

    trainloader = DataLoader(train_dataset, batch_size=64, shuffle=True)
    testloader = DataLoader(test_dataset, batch_size=64, shuffle=False)

    # Create an instance of the model
    model_CNN = smallCNN()  # Use the smallCNN model defined earlier
    # Define the loss function and optimizer
    criterion = nn.CrossEntropyLoss()  # Used for multi-class classification
    optimizer = optim.Adam(model_CNN.parameters(), lr=0.001)  # Adam optimizer for adaptive learning
    # Lists to store accuracy and loss values for plotting
    train_accuracies = []
    test_accuracies = []
    train_losses = []

    epochs = 10
    for epoch in range(epochs):
        running_loss = 0.0
        correct = 0
        total = 0

        model_CNN.train()  # Set the model to training mode
        for images, labels in trainloader:
            optimizer.zero_grad()  # Clear previous gradients

            # Forward pass
            outputs = model_CNN(images)

            # Compute the loss
            loss = criterion(outputs, labels)

            # Backward pass and optimization
            loss.backward()
            optimizer.step()

            running_loss += loss.item()

            # Calculate training accuracy
            _, predicted = torch.max(outputs, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()

        # Calculate average training loss and accuracy for the epoch
        avg_loss = running_loss / len(trainloader)
        train_accuracy = 100 * correct / total

        # Store the loss and accuracy
        train_losses.append(avg_loss)
        train_accuracies.append(train_accuracy)

        # Calculate test accuracy
        model_CNN.eval()  # Set the model to evaluation mode
        test_correct = 0
        test_total = 0
        with torch.no_grad():  # No gradient computation during testing
            for images, labels in testloader:
                outputs = model_CNN(images)
                _, predicted = torch.max(outputs, 1)
                test_total += labels.size(0)
                test_correct += (predicted == labels).sum().item()

        test_accuracy = 100 * test_correct / test_total
        test_accuracies.append(test_accuracy)

        # Print training loss, training accuracy, and test accuracy for the epoch
        print(f'Epoch [{epoch + 1}/{epochs}], Loss: {avg_loss:.4f}, Training Accuracy: {train_accuracy:.2f}%, Test Accuracy: {test_accuracy:.2f}%')

    # Plot the training and test accuracy curves
    plt.figure(figsize=(10, 5))
    plt.plot(range(1, epochs + 1), train_accuracies, label='Training Accuracy')
    plt.plot(range(1, epochs + 1), test_accuracies, label='Test Accuracy')
    plt.xlabel('Epochs')
    plt.ylabel('Accuracy (%)')
    plt.title('Training and Test Accuracy Over Epochs')
    plt.legend()
    plt.grid(True)
    plt.show()

    # Plot the training loss curve
    plt.figure(figsize=(10, 5))
    plt.plot(range(1, epochs + 1), train_losses, label='Training Loss', color='orange')
    plt.xlabel('Epochs')
    plt.ylabel('Loss')
    plt.title('Training Loss Over Epochs')
    plt.legend()
    plt.grid(True)
    plt.show()