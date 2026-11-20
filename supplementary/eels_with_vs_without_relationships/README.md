# Fe L2,3 fit with and without the four tied relationships

Supplementary material of the archive; no claim of `results/claims-report.json` rests on it.

The Fe L2,3 edge of Fe2O3 (700 to 735 eV, `scripts/fig_eels.py`) fitted from the same 500
seeded start vectors in two arms: **with relationships** (the four tied relationships of
`fig_eels.TIES`: the L2 step is half the L3 step, both steps share one width, each step sits at
the centre of its main white-line component; 30 free parameters) and **without relationships**
(34 free parameters). Both arms use the same solver (`FitOptions(solver="lm")` of
spectrafit-core 0.1.3), the same bounds and the same settings; the starts are drawn by
`fig_eels.sample_start` from `numpy.random.default_rng([20261110, 0])`.

No fit is run here. `eels_with_vs_without_relationships.py` reads the spectrafit fits of the
`eels-far` target (`results/eels-far/eels_far.json`) and the reference points of
`results/eels_fe2o3.json`, both from the run of record, and writes:

| file | content |
|---|---|
| `eels_with_vs_without_relationships.json` | one record per fit: arm, start, all fitted parameters, reported success, termination message, RSS, Gauss-Newton stationarity flag, L3 and L2 step amplitudes and their sum, L3 white-line branching ratio; the reference points; SHA-256 of every input |
| `eels_with_vs_without_relationships.{pdf,png}` | the figure below |

Run from the repository root:

```bash
uv run --locked python supplementary/eels_with_vs_without_relationships/eels_with_vs_without_relationships.py
```

**Figure.** (a) Histogram of the fitted L3 + L2 step amplitude of all 500 fits per arm (60
bins); the grey band marks L3 + L2 from 2550 to 2700 counts. (b) Fitted L3 step amplitude
against fitted L2 step amplitude, one point per fit, coloured by arm; filled markers are fits
that report success, open markers fits that do not; the grey band marks the same region of
L3 + L2. Two reference points of the fit without relationships, from `results/eels_fe2o3.json`:
the fit from the default start (cross) and the lowest point of the profile of the L3 step
amplitude (diamond). Points of every RSS are shown; the RSS of each fit is in the JSON file.
