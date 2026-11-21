
import torch
import torch.nn as nn

from torchvision import datasets, transforms

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
        self.classsifier = nn.Sequential(
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

TRAIN_DATA_PATH = './data'
TEST_DATA_PATH = './data'

# Create DataLoaders
trainloader = DataLoader(train_dataset, batch_size=128, shuffle=True)
testloader = DataLoader(test_dataset, batch_size=10000, shuffle=False)

# Define a simple CNN model
class SimpleCNN(nn.Module):
    def __init__(self):
        super(SimpleCNN, self).__init__()
        # First convolutional layer
        self.conv1 = nn.Conv2d(in_channels=1, out_channels=16, kernel_size=3, stride=1, padding=1)
        self.relu = nn.ReLU()  # ReLU activation function
        self.pool = nn.MaxPool2d(kernel_size=2, stride=2, padding=0)  # Max pooling layer
        
        # Second convolutional layer
        self.conv2 = nn.Conv2d(in_channels=16, out_channels=32, kernel_size=3, stride=1, padding=1)
        
        # Fully connected layers
        self.fc1 = nn.Linear(32 * 7 * 7, 128)  # Fully connected layer
        self.fc2 = nn.Linear(128, 10)  # Output layer (10 classes for digits 0-9)

    def forward(self, x):
        x = self.relu(self.conv1(x))  # Apply first convolution + ReLU
        x = self.pool(x)  # Apply max pooling
        x = self.relu(self.conv2(x))  # Apply second convolution + ReLU
        x = self.pool(x)  # Apply max pooling again
        x = x.view(-1, 32 * 7 * 7)  # Flatten the output for the fully connected layer
        x = self.relu(self.fc1(x))  # Apply first fully connected layer + ReLU
        x = self.fc2(x)  # Apply output layer
        return x

# Create an instance of the model
model_CNN = SimpleCNN()
# Define the loss function and optimizer
criterion = nn.CrossEntropyLoss()  # Used for multi-class classification
optimizer = optim.Adam(model_CNN.parameters(), lr=0.02)  # Adam optimizer for adaptive learning
epochs = 5
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