from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/graph", response_class=HTMLResponse)
async def graph_menu(request: Request):
    return templates.TemplateResponse("graph.html", {"request": request})

@app.get("/graph/term", response_class=HTMLResponse)
async def graph_term(request: Request):
    return templates.TemplateResponse("graph_term.html", {"request": request})

@app.get("/graph/month", response_class=HTMLResponse)
async def graph_month(request: Request):
    return templates.TemplateResponse("graph_month.html", {"request": request})