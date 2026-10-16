# Timing measurement on the host of record

Procedure for one timing measurement of spectrafit-core 0.1.2 on terra (KVM guest,
16 vCPU, Ubuntu 22.04), as release 1.2.0 of this repository records it. The chain runs
about 26 hours and needs the host to itself.

The procedure has two parts because the reboot ends every session on the host,
including an agent session that runs this list. Part 1 ends with the reboot; part 2
starts in a new session.

Paths used below:

| | |
|---|---|
| this repository on terra | `~/projects/SpectraFit-Core-Reproducibility` |
| SpectraFit-Core checkout (only read) | `~/projects/SpectraFit-Core` |
| run root (fresh for every run) | `~/timing-0.1.2-<YYYY-MM-DD>` |
| smoke root | `~/timing-smoke-<YYYY-MM-DD>` |

## 0. Get the commit to terra

On the workstation, push the branch straight to terra, without a public remote:

```bash
# once, on terra
git init --bare ~/repos/SpectraFit-Core-Reproducibility.git
# once, on the workstation
git remote add terra ssh://terra/~/repos/SpectraFit-Core-Reproducibility.git
# every time
git push terra run-2026-10
```

On terra:

```bash
cd ~/projects/SpectraFit-Core-Reproducibility
git fetch ~/repos/SpectraFit-Core-Reproducibility.git run-2026-10
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
   T=~/timing-0.1.2-$(date -u +%F)
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
   cat ~/timing-0.1.2-*/STATUS; tail -3 ~/timing-0.1.2-*/chain.log
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

11. Keep the timing of record of release 1.1.0 next to the new one, then assemble:

    ```bash
    git switch -c results-2026-10
    git mv results/timing results/timing-2026-10-06
    uv run --locked python bench/assemble.py build "$T" results/timing
    ```

    `assemble.py` must report `0 problem(s)`.

12. Update `pins.toml` (`[timing]`, `[timing_inputs]` with the SHA-256 of the new files),
    update the expected values of the bench, agree and bias claims in `reproduce.py` to
    the new numbers, then run `uv run --locked reproduce.py` on terra. Every claim must
    hold. Commit, push to terra and to GitHub, tag `v1.2.0`, and archive on Zenodo.
