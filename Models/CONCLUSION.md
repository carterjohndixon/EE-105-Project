## Conclusion

We will use **MobileNetV2 (transfer learning)** for the game.

- **Works on our camera:** trained on Kaggle plus about 2,200 of our own OV7675 pictures from several rooms,
  outdoors and at different times of day (including a "none" class for when no hand is shown), MobileNetV2
  scores **99.1% on 232 camera pictures it never trained on**: only 2 scissors were called paper.
- **It handles new places much better than the small CNN:** our validation pictures are the newest 15% of each
  class, mostly from the newest places (outdoors and a lounge, with paper also shown edge-on). There MobileNetV2
  reaches **82.5%** and was still improving after 8 epochs, while the small CNN reaches only **60.1%**. The CNN
  even struggles to learn the training pictures (77% after 30 epochs): with 94k parameters learned from scratch it
  cannot cover this many different scenes, while MobileNetV2 reuses shape features learned from ImageNet.
- **Versus the small CNN on the camera test:** the small CNN scores **92.7%** (17 mistakes: 10 scissors called
  paper, 6 paper called "none"), against MobileNetV2's 99.1% (2 mistakes).
- **Our own pictures were necessary:** trained on Kaggle alone, the model guessed "paper" for almost
  everything the camera showed, including an empty scene. Kaggle's pictures are rendered hands on white
  backgrounds and have no "none" class.
- **Lighting and sessions matter:** with pictures from only one session per room, the model learned each
  session's lighting. It called 41 of 60 empty-room pictures from a different time of day "rock". Pictures from
  more places and times, plus random changes of brightness, contrast and blur, made it more robust.
- **Trade-off on Kaggle:** focusing on our camera keeps Kaggle accuracy lower than a Kaggle-only model
  (MobileNetV2 87.6% now, 94.9% trained on Kaggle alone; the small CNN dropped from 96.2% to 83.1% with the new
  pictures). The game only sees our camera, so we accept this.
- **Scissors vs paper is the hardest pair:** both models' remaining camera mistakes are mostly scissors called
  paper, so more varied scissors pictures are the most useful next step.
- **Fast enough:** a prediction takes about 6 ms on a T4 GPU and 28 ms on a laptop CPU, small next to the
  camera, which delivers a new picture about every 400 ms (2.5 per second).

**Limitations:** the camera test set (232 pictures) comes from one person's hand and only from the earliest
recording sessions, so the 99.1% does not cover the newer places; the 82.5% validation accuracy on the newest
pictures is a more realistic estimate for a new room. A test set recorded in new places, and with other people's
hands, would give a more honest number. The model has also never seen a face, so a face in the box (likely with a
laptop webcam) can be mistaken for "rock".
