from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from app.parser import parse_schedule, generate_excel

app = FastAPI()


@app.get("/")
def export_to_excel(meeting_id: str = Query(..., description="Equipe API endpoint")):
    """
    Export the schedule for a meeting ID to Excel.
    No authentication required.
    """
    starts = parse_schedule(meeting_id)
    file_path = generate_excel(starts)
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="equipe_"+meeting_id+".xlsx"
    )
