# GitHub publication record

Status: documentation prepared; remote repository/bundle not created; `upload=false`.

Authorized target for this single upload: `https://github.com/wenqizheng26/CommPlan-Agent-A-Multi-Agent-Collaborative-System-for-Communication-Planning`.

Current publication attempt stopped per user instruction after one inspection pass; no remote commit was created.

Fresh verification: `2026-09-17T08:16:43+01:00`.

The accepted local H0 baseline is committed as `2121d137ea5831d323cb1b46895e1756a4dfc835`; no remote repository has been created and no push has occurred.

## Scope

- Publisher: PUB-01.
- Intended owner: `wenqizheng26` (user-specified authoritative target).
- Connected account now observed: `wenqizheng26`; this matches the intended owner.
- Proposed new repository name: private `signal-formula-rag-takeover` (a proposal only; not user-selected).
- No existing repository was overwritten or repointed.
- The source repository origin was not changed.
- No publication bundle exists yet. Its proposed scope excludes source business files, binaries, original WBS and VSDX files.

## Channel results

- Previous origin `https://github.com/wenqizheng26/signal-formula-rag.git` is retired for this publication attempt; no further network or publication action targets it.
- Git CLI access to `github.com:443` timed out with `Failed to connect to github.com:443 after 21117 ms`.
- `gh` CLI is not installed and was not installed.
- The refreshed authenticated GitHub connector still returns login `WenqiZheng2004` (profile id `293001755`), which is not the intended owner `wenqizheng26`; the candidate repository lookup returns API `404 Not Found`, and the connector lists no repositories for the intended owner.
- The callable connector had no repository-creation operation.
- Visible Chrome recovery was attempted once after CUA reset with `https://github.com/new`; it failed with `nodeRepl.fetch request failed` and exposed no usable browser or tab.
- One bounded read-only check against the correct owner succeeded at the public API level (`https://api.github.com/users/wenqizheng26`, HTTP 200); the candidate `https://github.com/wenqizheng26/signal-formula-rag-takeover.git` returned `Repository not found` from `git ls-remote`. No creation or upload was attempted.
- Fresh connector profile/login both report `wenqizheng26` (profile id `316311030`); the public profile shows one repository, `local-agentic-rag`. The connector's accessible-repository list returned empty and the candidate repository lookup returned API 404, so the candidate does not currently exist or is not accessible through this connection.
- Read-only inspection confirms `wenqizheng26/local-agentic-rag` is an existing public repository (created `2026-06-23T10:20:02Z`), description `Fully-local agentic RAG (LangGraph + Qwen2.5 + BGE reranker) that runs on a single 8GB GPU. Multi-turn, source-cited, self-correcting.`, default branch `main`, size 53 KB, and non-empty. Top level includes `LICENSE`, `README.md`, `README.zh-CN.md`, `app.py`, `config.py`, `data/`, `eval/`, `requirements-dev.txt`, `requirements.txt`, `scripts/`, `src/`, `tests/`, and `一键打开RAG.bat`. It is a separate existing project and has not been selected as the publication target.
- The user's newly created project was not safely identifiable from the available public profile page; do not guess `local-agentic-rag` or another slug. The active snapshot contains unfinished single-agent planning WIP and therefore was not uploaded.
- Repository metadata reports admin/maintain/push permissions for the current connection; the dedicated collaborator-permission endpoint returned 403, so that endpoint did not independently verify access.
- Creation attempt through the required visible Chrome route (`https://github.com/new`) failed after CUA reset with `nodeRepl.fetch request failed`; no browser tab became available, so no form was submitted.

## Publication gate

Stage 1 reviewed allowlist was supplied by Main. Before the publisher created the separate local publication repository, its turn stopped on the account usage limit. Main read-only verification found the proposed publication directory absent; there are no local publication commits and no remote upload. Stage 2 awaits final independent review closure. If a new repository is later created, inspect its state: an empty repository has no HEAD and needs an initial commit; a repository initialized with a README has a HEAD which must be preserved. Do not import the old repository history.

Final status update by Main after the publisher stopped; Main did not perform Git publication operations.

## Recovery conditions

Resume only after the exact new repository URL/slug is confirmed and a GitHub write-capable connector or standard Git credential path is available. Do not create or upload to `local-agentic-rag`, the historical `WenqiZheng2004` account, or the old origin.

Minimum user action: create the private repository under `wenqizheng26` (candidate name `signal-formula-rag-takeover`) and provide its URL, or reconnect an authorized connector for that account. Then the publisher can verify the new repository HEAD and await the explicit upload allowlist.
