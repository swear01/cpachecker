# Submitting this artifact to Zenodo (to obtain the DOI)

The course requires a **DOI** for the reproduction artifact. Zenodo mints a permanent,
public DOI; that upload must be done from **your** Zenodo account. Everything is prepared
below — you only need to log in and upload.

## Option A — Web upload (simplest, ~5 clicks)

1. Log in at <https://zenodo.org> (you can sign in with GitHub/ORCID).
2. Click **New upload**.
3. Drag in the prepared archive **`vguide-artifact-v2.zip`** (built via
   `bash scripts/vguided-cegar/build_artifact_zip.sh` at the repository root).
4. Fill the metadata using the values below (or they auto-fill if you connect the GitHub
   repo, which carries `.zenodo.json`):
   - **Title:** From Predicates to Ranking Functions: LLM-Proposed, Engine-Validated Candidates
     for CEGAR-Based Software Verification (Artifact)
   - **Upload type:** Software
   - **Authors:** Huang, Ssu-Wei — National Taiwan University
   - **License:** Apache-2.0
   - **Keywords:** software verification; CEGAR; predicate abstraction; termination; ranking
     functions; large language models; CPAchecker; SV-COMP
   - **Description:** (copy the abstract / `.zenodo.json` description)
5. Click **Publish**. Zenodo shows the **DOI** (e.g. `10.5281/zenodo.XXXXXXX`).
6. Put that DOI in the report and submit the DOI as the artifact deliverable.

> Tip: reserve a DOI before publishing (the "Reserve DOI" button) if you want to cite the
> DOI inside the report PDF before the upload is final.

## Option B — Connect GitHub release (auto-DOI on each release)

1. Push this repository to GitHub.
2. In Zenodo, enable the repository under **Settings → GitHub**.
3. Create a **GitHub release** (a tagged version). Zenodo reads `.zenodo.json` from the repo
   root and mints a DOI for that release automatically.

## Option C — API draft (if you give an assistant a token; review before publish)

If you provide a Zenodo **personal access token** (Zenodo → Applications → Personal access
tokens, scope `deposit:write`), a draft deposition can be created via the REST API and the
zip uploaded, leaving it **unpublished** for you to review and click *Publish*. Publishing is
never done automatically, because the DOI is permanent and public.

```bash
# illustration only — creates a DRAFT, does not publish
curl -s -X POST "https://zenodo.org/api/deposit/depositions?access_token=$ZENODO_TOKEN" \
     -H "Content-Type: application/json" -d '{}'
# then upload vguide-artifact.zip to the returned bucket URL, and PUT the metadata.
```

## Before you upload — two one-line edits

- **Pin the commit:** after committing the VGuide source, put the hash in `README.md` §5 and
  in the report (e.g. via `git rev-parse HEAD`).
- **Confirm your name romanisation** ("Ssu-Wei Huang") matches your official English name.
