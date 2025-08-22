import requests

def get_json(url):
    response = requests.get(url)

    try:
        data = response.json()
        # print(f"[DEBUG] Fetched class_section {class_section_id}:")
        # print(data)
        return data
    except Exception as e:
        print(f"[ERROR] Failed to parse JSON for class_section {class_section_id}")
        print(f"Raw response: {response.text}")
        raise e


    if response.status_code == 200:
        print("Class section: ", url)
        return response.json()
    else:
        print(f"Warning: could not fetch class_section {class_section_id}")
        return None

def parse_schedule(meeting_id):
    competitions = []
    meeting_url = f"https://online.equipe.com/api/v1/meetings/{meeting_id}/schedule"
    schedule = get_json(meeting_url)

    # print("Schedule received:", schedule)
    # print("Type of schedule:", type(schedule))

    # Hvis det er en string ved en fejl (fx JSON i string-format), så prøv at parse det
    if isinstance(schedule, str):
        import json
        try:
            schedule = json.loads(schedule)
        except json.JSONDecodeError:
            raise ValueError("Ugyldig JSON returneret fra get_meeting_schedule")

    competitions_data = schedule.get("meeting_classes")
    if not isinstance(competitions_data, list):
        raise ValueError(f"Uventet format: 'meeting_classes' mangler eller er ikke en liste: {schedule}")


    competitions = []

    for comp in schedule:
        if not isinstance(comp, dict):
            continue  # spring strings eller andet skrald over


    for comp in competitions_data:
        comp_info = {
            "competition_name": comp.get("name"),
            "start_time": comp.get("start_at"),
            "class_no": comp.get("class_no"),
        }

        for section in comp.get("class_sections", []):
            class_section_id = section.get("id")

            class_section_url = f"https://online.equipe.com/api/v1/class_sections/{class_section_id}"
            section_details = get_json(class_section_url)

            if section_details and section_details.get("starts"):
                for start in section_details["starts"]:
                    #print(f"Competitions: {start}")
                    enriched_row = {
                        **comp_info,
                        "class_section_id": class_section_id,
                        "class_section_state": section.get("state"),
                        "placed": section.get("placed"),
                        "results_available": True,
                        **start # <-- her får vi alt rider/hest/points/etc. med
                    }
                    competitions.append(enriched_row)  # tilføj kopi for hver section med resultater
                

    #print(f"Competitions: {competitions}")
   #print(f"Type: {type(competitions)}")

    return competitions


def generate_excel(data: list[dict]) -> str:

    import pandas as pd
    import uuid

    preferred_columns = [
    "competition_name",
    "start_time",
    "class_no",
    "rider_name",
    "horse_name",
    "club_name",
    "start_no",
    "start_at",
    "result_at",
    "percent",
    "rank",
    "placed",
    "class_section_id",
    "class_section_state",
    ]


    if not data:
        print("❌ Data is empty!")

    # Convert list of dicts into a DataFrame
    df = pd.DataFrame(data)
    # print("🔍 DataFrame preview:")
    # print(df.head())

    # Rearrange columns: preferred ones first, then the rest
    preferred = [col for col in preferred_columns if col in df.columns]
    others = [col for col in df.columns if col not in preferred]
    df = df[preferred + others]

    # Optionally, expand 'points' array to separate columns
    if "points" in df.columns and not df["points"].isnull().all():
        points_df = df["points"].apply(pd.Series)
        points_df.columns = [f"point_{i+1}" for i in points_df.columns]
        df = pd.concat([df.drop(columns=["points"]), points_df], axis=1)

    # Generate filename
    filename = f"/tmp/equipe_{uuid.uuid4()}.xlsx"

    # Export to Excel
    df.to_excel(filename, index=False)

    return filename