from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Define all your routes here ---

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("templates/index.html", "r") as f:
        return f.read()

@app.get("/about", response_class=HTMLResponse)
def read_about():
    with open("templates/about.html", "r") as f:
        return f.read()

# --- Put the server runner at the very end ---

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)