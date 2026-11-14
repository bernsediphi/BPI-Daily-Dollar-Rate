# BPI USD rate bot

Fetches BPI's indicative USD buying/selling rate every weekday at 9:30 AM Manila time using GitHub Actions. The rate always appears in the run's log and Summary page. It can also be sent to Teams and/or email.

## Setup

1. Create a **private** GitHub repo and upload everything in this folder, keeping the paths:
   - `bpi_rate.py`
   - `requirements.txt`
   - `.github/workflows/bpi-rate.yml`
2. Add secrets under **Settings -> Secrets and variables -> Actions -> New repository secret**. All are optional; add only what you want.

   | Secret | Purpose |
   |---|---|
   | `TEAMS_WEBHOOK_URL` | Teams Workflows / Power Automate HTTP URL |
   | `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO` | Email delivery (`EMAIL_TO` can be comma-separated) |
   | `SMTP_PORT`, `EMAIL_FROM` | Optional (default port 587) |

   Gmail example: `SMTP_HOST=smtp.gmail.com`, `SMTP_USER=you@gmail.com`, `SMTP_PASSWORD=<16-character app password>` (needs 2-step verification turned on).
3. Open the **Actions** tab -> **BPI USD rate** -> **Run workflow**. This manual run works on any day. Check the log for the rate.

## Notes

- GitHub cron uses UTC. `30 1 * * 1-5` = 9:30 AM Manila, Mon-Fri. Runs can start 5-30 minutes late.
- GitHub disables scheduled workflows after 60 days without repo activity. Re-enable it in the Actions tab if that happens.
- If BPI blocks GitHub's servers, the run fails with a 403 or "USD row not found" error in the log.
