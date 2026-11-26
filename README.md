# EE 105 Project: Rock-Paper-Scissors CNN

## Dataset

The full image data is not stored in this repo. Download `data-zip.zip` from the
[data-v1 release](https://github.com/carterjohndixon/EE-105-Project/releases/tag/data-v1)
and unzip it at the repository root. That recreates `data/`:

Data is from [here](https://www.kaggle.com/datasets/sanikamal/rock-paper-scissors-dataset?resource=download)

## How it works
The user is prompted to do a gesture following: scissors, rock, paper. While being prompted for the gesture via camera, the computer runs a random number generator to pick a random gesture and then comapres it to the user to determine who wins.

```
data/kaggle/{train,validation,test}/{rock,paper,scissors}/
data/ours/{rock,paper,scissors,none}/
data/test/{rock,paper,scissors,none}/
```

## Model

The game recognizes gestures with **MobileNetV2**, a convolutional neural network pretrained on ImageNet
(1.2 million everyday photos) and adapted to rock-paper-scissors with **transfer learning**. We compared it
with a small CNN trained from scratch and chose MobileNetV2: see the **[model comparison results](Models/RESULTS.md)**
for accuracy tables, training curves, confusion matrices and the conclusion.

**From camera picture to prediction**

1. The camera on the the provided board sends a 160×120 grayscale picture.
2. The center square (the yellow box in the game window, 96×96 pixels) is cropped out.
3. It is resized to 224×224, the gray channel is copied 3 times (MobileNetV2 expects color input),
   and it is normalized with ImageNet's mean and standard deviation.
4. MobileNetV2's convolutional layers turn the picture into 1,280 features (edges, shapes, finger outlines).
5. A small classifier we added turns those into probabilities for 4 classes: **none** (no hand), **paper**,
   **rock** and **scissors**. Its layers: Dropout 0.3 → Linear 1280→128 → ReLU → Dropout 0.3 → Linear 128→4.

**Training** (in [`Models/MobileNet-model.ipynb`](Models/MobileNet-model.ipynb), on a Google Colab T4 GPU)

- **Data:** 2,520 Kaggle training pictures plus about 3,200 of our own pictures from the board camera and a
  laptop webcam (taken with `capture.py` in several rooms, outdoors, day and night), all converted to grayscale. Our pictures are used 3 times per epoch
  because there are fewer of them, and they include the "none" class, which Kaggle does not have.
- **Transfer learning:** the pretrained layers are frozen at first, so only the new classifier learns
  (about 164,000 of the model's 2.4 million parameters). After 4 epochs the last 2 blocks of MobileNetV2 are
  unfrozen and fine-tuned at a 10× lower learning rate.
- **Augmentation:** every training picture is randomly cropped, rotated up to 30°, mirrored, and changed in
  brightness and contrast. Our camera pictures also get stronger brightness/contrast changes and some blur, so the
  model learns the hand shape rather than the lighting of the session in which a picture was taken.
- **Settings:** 12 epochs, AdamW optimizer (learning rate 3e-4, weight decay 1e-4), cross-entropy loss with label
  smoothing 0.1, learning rate halved when validation accuracy stops improving. The epoch with the best
  validation accuracy is kept.

**Results:** 95.6% on 551 of our own board and webcam pictures that were never used for training, and 96.2% on
Kaggle's test set. A small CNN trained from scratch on the same data reaches only 67.5% on our pictures, which is
why the game uses transfer learning. Details and the full comparison: [Models/RESULTS.md](Models/RESULTS.md).

**In the game**, each round takes 3 camera pictures (about 1.2 s). A picture counts only if the model is at
least 45% sure it shows a gesture, and at least 2 of the 3 pictures must agree; otherwise the player is asked to
try again. `model.best_kind()` automatically picks the trained model with the best accuracy on our camera
pictures. The trained weights (`weights/mobilenet.pt`) are not stored in git.

**Code:** the models, data loading and training are in [`model.py`](model.py); the training notebooks are in
[`Models/`](Models/).
