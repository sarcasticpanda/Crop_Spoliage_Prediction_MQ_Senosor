# Edition 2 demo: run results

**These are results on a rule-based simulator only. They are not measured crop
accuracy, spoilage validation, or evidence of remaining shelf life.**

Command run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m crop_prototype.edition2_simulation
```

The run generated 600 independent one-time cases for each crop and trained one
Random Forest per crop. It used a stratified 75/25 row split; since rows were
generated independently, there are no lots or trajectories in this dataset.
The target is a synthetic `good`/`bad` label from the documented latent rule.

| Crop | Synthetic good / bad | Accuracy | Macro F1 | Bad recall |
|---|---:|---:|---:|---:|
| Tomato | 548 / 52 | 0.9533 | 0.8208 | 0.5385 |
| Table potato | 563 / 37 | 0.9667 | 0.8595 | 0.7778 |
| Banana | 561 / 39 | 0.9467 | 0.7003 | 0.3000 |

The classes are imbalanced, so accuracy alone hides missed `bad` cases. For
example, the banana model missed most simulated `bad` cases. These scores only
measure how closely Random Forest reproduces this generator's patterns on a
held-out set of simulated rows. They do not estimate performance on real crop
samples.

Saved models and machine-readable metrics are in `artifacts/edition2_simulation/`.
CSV files are under each crop's `simulated_v2/` folder. Source downloads remain
in the separate `original/` folders.
