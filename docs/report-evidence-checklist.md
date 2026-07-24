# Report Evidence Checklist

The assignment requires evidence from the genuine final Docker/Hadoop run.
Do not use the deterministic fixture as submission evidence.

Capture the following after `scripts/run_final_data.sh` succeeds:

- `01-containers.png`: `docker compose ps` showing Nginx and all backends
  healthy.
- `02-nginx-request.png`: a successful `curl` request through port 8080 with
  request ID, country, and scenario headers.
- `03-nginx-log.png`: the matching line from
  `data/nginx/nginx_access.log`.
- `04-service-log.png`: the correlated line from the matching backend log.
- `05-traffic-generator.png`: the 100,000-request generator summary.
- `06-hadoop-streaming.png`: successful completion of all five jobs.
- `07-intermediate-output.png`: representative Job 2, Job 3, and Job 4 CSV
  rows.
- `08-final-summary.png`: `outputs/final/summary.json`.

Store these images under `docs/evidence/` using the names above. Re-run:

```bash
python scripts/build_report.py
```

The report builder includes available evidence images and clearly identifies
any missing evidence. Before submission, verify that the PDF contains all
eight images and that the cover identifies both group members.
