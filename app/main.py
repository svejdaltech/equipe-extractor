from fastapi import FastAPI, Query, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.parser import parse_schedule, generate_excel
from app.auth import router as auth_router, verify_token, COOKIE_NAME

app = FastAPI()
app.include_router(auth_router)

templates = Jinja2Templates(directory="app/templates")

def get_current_user(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    username = verify_token(token) if token else None
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return username

@app.get("/", response_class=RedirectResponse)
def root(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    username = verify_token(token) if token else None
    if not username:
        return RedirectResponse(url="/login")
    else:
        return templates.TemplateResponse("dashboard.html", {"request": request, "username": username})

@app.get("/export")
def export_to_excel(
    meeting_id: str = Query(..., description="Equipe API endpoint"),
    user: str = Depends(get_current_user)  # Only logged-in users can access
):
    starts = parse_schedule(meeting_id)
    file_path = generate_excel(starts)
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="equipe_export.xlsx"
    )
