import os
import secrets

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from app.parser import parse_schedule, generate_excel

app = FastAPI()

security = HTTPBasic()

try:
    AUTH_USERNAME = os.environ["AUTH_USERNAME"]
    AUTH_PASSWORD = os.environ["AUTH_PASSWORD"]
except KeyError as e:
    raise RuntimeError(f"Missing required environment variable: {e.args[0]}") from e


def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, AUTH_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, AUTH_PASSWORD)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )


@app.get("/")
def export_to_excel(
    meeting_id: str = Query(..., description="Equipe API endpoint"),
    _auth: None = Depends(require_auth),
):
    """
    Export the schedule for a meeting ID to Excel.
    """
    starts = parse_schedule(meeting_id)
    file_path = generate_excel(starts)
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="equipe_"+meeting_id+".xlsx"
    )
