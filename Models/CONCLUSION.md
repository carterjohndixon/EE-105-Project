## Conclusion

We will use **MobileNetV2 (transfer learning)** for the game.

- **Works on our camera:** trained on Kaggle plus 1,421 of our own OV7675 pictures from several rooms and
  sessions (including a "none" class for when no hand is shown), MobileNetV2 scores **95.3% on 232 camera
  pictures it never trained on**. Every "no hand" and paper picture was right; the mistakes were 9
  scissors called paper and 2 rocks called "none".
- **Our own pictures were necessary:** trained on Kaggle alone, the model guessed "paper" for almost
  everything the camera showed, including an empty scene. Kaggle's pictures are rendered hands on white
  backgrounds and have no "none" class.
- **Lighting and sessions matter:** with pictures from only one session per room, the model learned each
  session's lighting. It called 41 of 60 empty-room pictures from a different time of day "rock". Adding
  those pictures to training and randomly varying brightness, contrast and blur made it more robust.
- **Trade-off on Kaggle:** focusing on our camera lowered accuracy on Kaggle's rendered hands from 94.9%
  to 86.6% (it now often calls Kaggle's paper "scissors"). The game only sees our camera, so we accept this.
- **Versus the small CNN:** trained on the same data, the small CNN (trained from scratch, 94k parameters)
  scores **92.7% on our camera pictures**, compared with MobileNetV2's 95.3%. It confuses scissors with paper
  more often (14 vs 9 times) and calls 3 "no hand" pictures paper. MobileNetV2 also learns much faster thanks
  to pretrained ImageNet features (about 90% validation accuracy after 2 epochs; the CNN needed 30 epochs).
- **The small CNN improved most from the extra data:** with our pictures, stronger augmentation and 30 epochs,
  its Kaggle accuracy rose from 88.4% to 96.2%, now above MobileNetV2's 86.6% there. The game only sees our
  camera, where MobileNetV2 is better, so the game uses MobileNetV2.
- **Both models confuse scissors with paper:** since both make the same mistake, it comes from the data rather
  than the model; more varied scissors pictures are the most useful next step.
- **Fast enough:** a prediction takes about 6 ms on a T4 GPU and 28 ms on a laptop CPU, small next to the
  camera, which delivers a new picture about every 400 ms (2.5 per second).

**Limitations:** the camera test set is small (232 pictures), comes from one person's hand, and partly
from the same sessions as training pictures, so accuracy in a new room or with other people is likely
lower. A fresh test set recorded in a separate session would give a more honest number.
