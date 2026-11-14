# BPI USD rate page

A GitHub Actions job fetches BPI's indicative USD buying/selling rate every weekday
(9:30 AM and 4:45 PM Manila time), saves it to `docs/rates.json`, and rebuilds
`docs/index.html`. GitHub Pages serves that page.

## Files

- `update_rate.py` - fetches the rate, keeps the history, builds the page
- `.github/workflows/bpi-rate.yml` - the schedule
- `docs/` - created by the first run (`index.html`, `rates.json`)

## Setup

1. Repo must be **public** (GitHub Pages on a free account needs a public repo).
2. Settings -> Pages -> Build and deployment -> Source: **Deploy from a branch**,
   Branch: **main**, Folder: **/docs** -> Save.
3. Actions tab -> "Update BPI USD rate page" -> Run workflow.
4. After it turns green, open `https://<your-username>.github.io/<repo-name>/`.
