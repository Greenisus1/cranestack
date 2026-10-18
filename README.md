# Cranestack

A fullscreen, offline 3D block-stacking tower game for Raspberry Pi and Linux terminals. A block sweeps side to side over your tower; drop it so it lands on the block below. Whatever hangs past the edge gets sliced off and falls away, and your next block is that much smaller. Miss the tower outright and the run ends. Speed climbs every level. Chain perfect drops for combo points.

Original name, art, and code, in the spirit of timing-based stacking games. This is a simplified terminal tribute: it shares no assets or code with any commercial game and does not claim to be a port.

Rendered in real 3D with an analytic ray tracer (truecolor half-block frames, delta writes, frame skip) - rainbow tower, sliced debris, camera that follows your tower up.

## Run

```
python3 cranestack.py
```

Python 3. No dependencies, no network, no install. Saves your best score to `~/.cranestack-best.json`.

## Controls

- **Space / Enter** - drop the sweeping block (restart after a miss)
- **[ / ]** - field of view
- **F** - cycle fps cap
- **P** - pause
- **Q** - quit

## Tests

```
python3 -m unittest test_cranestack
```

Built with AI assistance from my design. MIT License - Copyright (c) 2026 Greenisus1.
