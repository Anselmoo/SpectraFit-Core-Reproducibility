# Timing measurement on the host of record

Procedure for one timing measurement of a spectrafit-core release on terra (KVM guest,
16 vCPU, Ubuntu 22.04). The release is `SPECTRAFIT_VERSION` (default `0.1.3`, archive
release 1.3.0; release 1.2.0 measured `0.1.2`); `bench/preflight.sh` resolves it to the tag
`v$SPECTRAFIT_VERSION` of the SpectraFit-Core checkout and writes version, tag and commit to
`<run root>/source.env`, which the chain and `bench/assemble.py` read. The chain runs about
26 to 48 hours with library-default threading and needs the host to itself. In a full archive
run, `run-archive.sh` starts it as its first target (`timing`).

The procedure has two parts because the reboot ends every session on the host,
including an agent session that runs this list. Part 1 ends with the reboot; part 2
starts in a new session.

Paths used below:

| | |
|---|---|
| this repository on terra | `~/projects/SpectraFit-Core-Reproducibility` |
| SpectraFit-Core checkout (only read) | `~/projects/SpectraFit-Core` |
| run root (fresh for every run) | `~/timing-<version>-<YYYY-MM-DD>` |
| smoke root | `~/timing-smoke-<YYYY-MM-DD>` |

## 0. Get the commit to terra

Release 1.3.0 is prepared on the GitLab branch `release/1.3.0` (release 1.2.0 came through a
bare repository on terra, branch `run-2026-10`). On terra:

```bash
cd ~/projects/SpectraFit-Core-Reproducibility
git fetch origin release/1.3.0
git checkout --detach FETCH_HEAD
git rev-parse HEAD            # write this commit down; the run records it
git status --porcelain        # must print nothing
```

## Part 1: update and reboot

1. Save the CPU counters of the previous boot, then update:

   ```bash
   mkdir -p ~/host-records
   { date -u +%FT%TZ; uptime; head -1 /proc/stat; uname -r; } > ~/host-records/proc-stat-before-reboot-$(date -u +%Y%m%dT%H%M%SZ).txt
   sudo apt update && sudo apt full-upgrade -y
   ```

2. Reboot:

   ```bash
   sudo reboot
   ```

## Part 2: after the reboot

3. Freeze the host for the run. Note what you stop, so you can restore it in step 10:

   ```bash
   sudo systemctl stop apt-daily.timer apt-daily-upgrade.timer unattended-upgrades
   sudo systemctl mask apt-daily.timer apt-daily-upgrade.timer
   sudo apt-mark hold $(dpkg-query -W -f='${Package}\n' 'linux-image-*' 'linux-modules-*' libc6 libc-bin 2>/dev/null)
   docker ps -q | xargs -r docker stop
   ```

   Close VS Code remote sessions and any other agent session except the one running
   this list.

4. Check that the numbers of Table 1 are unchanged by the update (minutes):

   ```bash
   cd ~/projects/SpectraFit-Core-Reproducibility
   uv run --locked reproduce.py --check --source ~/projects/SpectraFit-Core
   ```

   `--check` must report "stored results are current" for the files it compares (a
   result this repository did not store before, such as the Figure 4 fit, is listed as
   not stored yet). If it reports a difference, stop here: the update changed the last
   digits of a fit, which goes into the README before anything is measured.

5. Smoke test: the whole chain on the smallest inputs, including the assembly (about 45
   minutes). It catches a failure of the drivers before the 26 hours start.

   ```bash
   S=~/timing-smoke-$(date -u +%F)
   bash bench/preflight.sh "$S" ~/projects/SpectraFit-Core --allow-sessions
   tmux new -d -s smoke "bash bench/run_timing.sh $S --smoke"
   # wait until cat $S/STATUS prints DONE; FAILED means: read the log it names
   ```

6. Preflight of the measurement. It exports the pinned commit into a fresh run root and
   checks the repository, the export, the six backends and the host:

   ```bash
   V=${SPECTRAFIT_VERSION:-0.1.3}; T=~/timing-$V-$(date -u +%F)
   bash bench/preflight.sh "$T" ~/projects/SpectraFit-Core --allow-sessions
   ```

   Every line must read PASS, except a WARN for the session that runs this list.

7. Start the chain with a delay, so that this session can end before the first rung:

   ```bash
   tmux new -d -s timing "sleep 300; bash bench/run_timing.sh $T"
   ```

8. **End this session now** (an agent session: exit it; an SSH session: log out). Nothing
   else runs on terra until the chain is done.

9. Progress, from a short login only:

   ```bash
   cat ~/timing-$V-*/STATUS; tail -3 ~/timing-$V-*/chain.log
   ```

   A chain that stopped at step K resumes with
   `bash bench/run_timing.sh $T --from-step K`; the seed sweep keeps finished seeds.

10. After `DONE`, restore the host:

    ```bash
    sudo systemctl unmask apt-daily.timer apt-daily-upgrade.timer
    sudo systemctl start apt-daily.timer apt-daily-upgrade.timer unattended-upgrades
    sudo apt-mark unhold $(apt-mark showhold)
    ```

## After the run

11. Keep the previous timing of record next to the new one, then assemble (release 1.3.0:
    the 0.1.2 timing of 16 to 17 October 2026 becomes `results/timing-0.1.2-2026-10-16`):

    ```bash
    git mv results/timing results/timing-0.1.2-2026-10-16
    uv run --locked python bench/assemble.py build "$T" results/timing
    ```

    `assemble.py` must report `0 problem(s)`.

12. Update `pins.toml` (`[timing]`, `[timing_inputs]` with the SHA-256 of the new files) and
    run `uv run --locked reproduce.py` on terra. The bench, agree and bias claims are then
    computed from the new timing; a claim whose expected value or text no longer fits is
    reported to the author of the article, never changed by the harness. Release 1.2.0 was
    then pushed to GitHub, tagged `v1.2.0` and archived on Zenodo.
