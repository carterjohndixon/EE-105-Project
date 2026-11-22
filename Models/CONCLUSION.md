## Conclusion

We will use **MobileNetV2 (transfer learning)** for the game.

- **More accurate:** 94.9% on the Kaggle test set (19 of 372 wrong), compared with 88.4% (43 wrong)
  for the small CNN trained from scratch.
- **Fewer systematic mistakes:** the small CNN over-predicts rock (precision 0.76, so about 1 in 4
  of its "rock" answers is wrong). MobileNetV2's weakest class is scissors (recall 0.91), and it never
  calls another gesture scissors (precision 1.00).
- **Learns faster:** pretrained ImageNet features let MobileNetV2 reach about 94% validation accuracy within
  2 epochs; the small CNN needed about 16 epochs to level off around 88%. Its training and validation
  accuracy stay close, so it is limited by its small size rather than overfitting.
- **Fast enough:** a prediction takes 7.7 ms on a T4 GPU (3.4 ms for the small CNN). Both are negligible
  next to the camera, which delivers a new frame every 400 ms (2.5 frames per second), so the larger model
  costs nothing noticeable in the game.

**Limitation:** both models were tested on Kaggle's computer-rendered hands on white backgrounds,
converted to grayscale. The next step is to test MobileNetV2 on our own OV7675 camera pictures
(`data/test/`) and, if needed, fine-tune it on pictures we capture ourselves (`data/ours/`),
including a "none" class for when no hand is shown.
