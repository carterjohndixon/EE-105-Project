# EE 105 Project: Rock-Paper-Scissors CNN

## Dataset

The image data is not stored in git. Download `data-zip.zip` from the
[data-v1 release](https://github.com/carterjohndixon/EE-105-Project/releases/tag/data-v1)
and unzip it at the repository root. That recreates `data/`:

```
data/kaggle/{train,validation,test}/{rock,paper,scissors}/
data/ours/{rock,paper,scissors,none}/
data/test/{rock,paper,scissors,none}/
```

The Kaggle images are 300x300 RGBA PNGs. The OV7675 camera gives 320x240 grayscale frames.
