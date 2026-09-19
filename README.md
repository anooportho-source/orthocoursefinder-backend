# OrthoCourseFinder backend

FastAPI aggregator for public orthopaedic education listings.

## Run locally
```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Then open `/api/courses`.

The collector currently includes adapters for BOFAS, BOA, BASK, British Hip Society, BESS, BSCOS, BSSH, EFAS, AOFAS, EFORT and AO Foundation. It normalises each record with specialty, course type, audience, dates, location, organiser and official URL.

For production, schedule refreshes server-side, log parser failures per source, and add an admin verification queue before surfacing newly discovered records to users.
