# Development notes

Working documents behind this fork. They are kept in the repository so the
reasoning is reviewable next to the code, not only in someone's notes.

| File | What it is |
| --- | --- |
| `spec.md` | The plan the fork was built from: current-state analysis, the full feature checklist with acceptance criteria, the phase order, and the verification evidence (what was measured on real data). Written in Chinese, with concrete numbers and file references. |
| `recon-polewire.md` | Reconnaissance of the offline pole/wire pre-annotation tool and of labelCloud's internals: API surface, the exact label JSON schema with real examples, the integration seams (file:line), and the learned-model inventory. |
| `research-assist-features.md` | Survey of what comparable annotation tools do — SUSTechPOINTS' keyframe interpolation, upstream labelCloud PR #181, TerraScan's power-line tools, Open3D/PCL/PDAL geometry recipes — with source links and an honest list of what could not be verified. |
| `pr181-review.md` | A line-by-line review of upstream PR #181 (`ch-sa/labelCloud`), with an adopt/reject verdict per feature and the reasons (including a constant it changes that would make a thin wire unrepresentable). |

Notes:

* these documents were written while the work was in progress, so they describe
  both what was built and what was deliberately left out;
* absolute paths in them (`/home/tyy/...`) are the machine the work happened on;
* the Chinese text is the original; the code and its comments are English, so the
  repository stays consistent for outside readers.
