# src/pipeline/__init__.py
# The pipeline package orchestrates the ETL process:
#   Extract  → src/pipeline/extract.py   (calls ingestion)
#   Transform → src/pipeline/transform.py (clean + validate)
#   Load     → src/pipeline/load.py      (write to database)
#   Schedule → src/pipeline/scheduler.py (runs it on a timer)
