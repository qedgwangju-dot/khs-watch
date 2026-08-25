# Treasury alert rollout verification

The two new production watchers are considered fully verified only after:
1. architecture CI succeeds;
2. each workflow completes an initial baseline without Telegram spam;
3. a later genuine source change produces exactly one Telegram alert;
4. state advances only after confirmed Telegram delivery.

Until those checks are observed, code creation is complete but production delivery is not yet claimed as verified.
