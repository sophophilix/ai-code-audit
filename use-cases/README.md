# Use cases

Worked instructions for running the kit on a specific system.

**Convention:** a use case that names a real organisation's systems,
infrastructure or known issues is saved as `<name>.local.md`. The repo's
`.gitignore` excludes `*.local.*`, so those files never leave your machine.
Keep them somewhere backed up, under your organisation's records rules.

Never copy `use-cases/` into an audit workspace. Agents must not see answer
keys or the tech lead's notes.

A use case usually covers:
1. The two sessions: a helper session in the kit repo for setup, and the
   audit session started in the workspace
2. Track A, a shake-down and evaluation on a history-free copy with seeded
   issues and in-repo issue lists removed
3. Track B, the real audit, only after Track A passes
4. The project-specific `project.md` and `models.yaml`
5. Facts the tech lead can check discovery against at Checkpoint 1
6. Where the answer keys live (outside the kit repo and the workspace)
7. A notes file for kit improvements found during the run

Before pushing the kit: `git status --ignored` should show your `.local.md`
files as ignored, and `git grep -niE '<org names, hostnames>'` should find nothing.
