# Request to integrator: ignore legacy/backup/

**What:** add one line to the root `.gitignore`:
```
legacy/backup/
```
**Why:** `legacy/scripts/migrate-volumes.ps1` writes full DASD backups there
(`dasd.tgz` is 206 MB, plus manifests). They must never be committed: they are
large, and a DASD image holds the whole mainframe, including RAKF user data.
`.gitignore` is yours, so for now I excluded the folder locally in
`.git/info/exclude`. That covers only my machine, so another clone running the
script would see the files as untracked.

Filed 2026-11-06 by Agent A.
