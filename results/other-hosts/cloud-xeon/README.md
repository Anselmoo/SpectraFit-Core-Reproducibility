# Cloud sandbox run: not the results of record

The first run of this pipeline, kept for comparison. It is **not** the run of record:
the results of record are produced on terra and live in `results/` and `figures/`.

| | |
|---|---|
| Generated | 2026-10-03T18:29:29Z (`results/provenance.json`) |
| Command | `reproduce.py --source ../upstream` |
| Host | cloud sandbox, Linux 6.18.44 x86-64, glibc 2.39, Intel Xeon @ 2.80 GHz, 2 cores |
| Python | CPython 3.13.15 |
| Library | spectrafit-core 0.1.0 PyPI wheel, tag v0.1.0 (0c5d366e) |
| Comparators | lmfit 1.3.4, SciPy 1.18.0, NumPy 2.5.1, matplotlib 3.11.2 |

The files are as the run wrote them, moved here unchanged:

- `results/`: the regenerated NIST tables, claims and drift reports, provenance, and the
  copies the run took from the release (`archived/`, `release-archive/`)
- `figures/`: the three figures

That run's own manifests (`checksums.sha256`, `ro-crate-metadata.json`) are not kept: their
paths referred to the folder layout of the time. The repository-wide manifests written by
every later run cover these files.

The three PNG files carry a content-credentials (C2PA) chunk added by the file transfer that
first brought this folder to disk; the pixels are what matplotlib drew, the bytes are not.
