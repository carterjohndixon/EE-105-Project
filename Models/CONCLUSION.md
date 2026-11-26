## Conclusion

We will use **MobileNetV2 (transfer learning)** for the game.

- **Works on both cameras:** trained on Kaggle plus about 3,200 of our own pictures from the OV7675 board camera
  and a laptop webcam (several rooms, outdoors, day and night, many hand angles, and a "none" class for an empty
  scene or a hand holding an object), MobileNetV2 scores **95.6% on 551 camera pictures it never trained on**,
  **96.5% validation** and **96.2% on Kaggle**. Its train and validation accuracy stay close, so it is not
  overfitting.
- **Transfer learning is what makes it work:** trained on exactly the same data, the small CNN (94k parameters
  learned from scratch) reaches only **67.5%** on the camera test and **57.0%** validation. It cannot even learn
  its training pictures (71% after 30 epochs): it underfits, because it would have to learn what a hand looks
  like in all these scenes from about 3,200 pictures. MobileNetV2 reuses shape features learned from 1.2 million
  ImageNet photos and only learns how to combine them.
- **The gap grows with the variety of the data:** with pictures from one room the two models were close on our
  camera (small CNN 92.7%, MobileNetV2 95.3%). Each new place widened the gap (60% vs 82% validation after adding
  outdoor and lounge pictures, 57% vs 96.5% now).
- **Where they go wrong:** MobileNetV2's 24 camera mistakes are spread out; the largest group is 8 rocks called
  paper (fists with the palm side toward the camera). The small CNN mostly confuses paper and scissors (89
  mistakes between them) and calls 36 paper or rock pictures "none".
- **Balanced data matters:** when we first added webcam pictures only for rock, MobileNetV2 learned that "looks
  like a webcam picture" means rock and called most webcam paper, scissors and empty scenes rock (80.9% camera
  test). Recording every class in the same places and lighting removed that shortcut.
- **Our own pictures were necessary:** trained on Kaggle alone, the model guessed "paper" for almost
  everything the camera showed, including an empty scene. Kaggle's pictures are rendered hands on white
  backgrounds and have no "none" class.
- **Lighting and sessions matter:** with pictures from only one session per room, the model learned each
  session's lighting and called 41 of 60 empty-room pictures from a different time of day "rock". Pictures from
  more places and times, plus random changes of brightness, contrast and blur, made it robust.
- **Fast enough:** a prediction takes about 7 ms on a T4 GPU and about 28 ms on a laptop CPU, small next to
  the board camera (a new picture every 400 ms) and fine for a webcam with predictions limited to 10 per second.

**Limitations:** all pictures come from one person's hand, and many test pictures were recorded in the same
sessions as training pictures, so accuracy in a new room or with other people is likely lower; a test set
recorded in new places and with other people's hands would give a more honest number. The model has never seen
a face, so a face inside the box (likely with a laptop webcam) can be mistaken for a gesture.
