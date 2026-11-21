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
