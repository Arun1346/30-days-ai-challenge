# FastAPI App

## Quickstart

1. Create a virtual environment (optional but recommended):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   python3 -m pip install --upgrade pip
   python3 -m pip install -r requirements.txt
   ```

3. Run the server:
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000 --reload
   ```

4. Open in the browser:
   - Home: http://127.0.0.1:8000/
   - About: http://127.0.0.1:8000/about
   - Docs: http://127.0.0.1:8000/docs