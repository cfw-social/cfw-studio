# Preview

Variation `default`. A 4 second sample of `card-orbit` on the procedural mannequin (`../examples/assets/synthetic_mannequin.mp4`, a drawn figure, no real person), 540 by 960.

[Sample](../examples/samples/camera_motion.mp4)

The clip floats as a rounded card with a shadow and rocks slowly around its vertical axis.

Rebuild it from `effects/`:

```bash
python3 e-camera-motion/scripts/camera_motion.py examples/assets/synthetic_mannequin.mp4 \
  --motion card-orbit --canvas 540x960 --card-scale 0.8 --crf 26 --out examples/samples/camera_motion.mp4
```

The other motions have no separate sample. Each one is rendered on a small test clip by the tests.
