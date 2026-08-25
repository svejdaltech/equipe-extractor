#Defination af API
Overblik over hele begivenheden
https://online.equipe.com/shows/69835
JSON for denne
https://online.equipe.com/api/v1/meetings/69835/schedule

meeting_classes beskriver disciplinerne (volte, trav etc)
meeting_classes -> [] -> score_sheets -> [] -> sheet_items

Hver enkelt "class_section" / "startliste" kan findes i ovenstående JSON under
meeting_classes -> [] -> class_sections -> [] -> id
Denne id bruges til at navigere hver enkelt "startliste" / "class_section"

"Startliste" / "class_section"
https://online.equipe.com/startlists/1071479
JSON for denne
https://online.equipe.com/api/v1/class_sections/1071479



Yderligere information fra begivenheden
https://online.equipe.com/api/v1/meetings/69835/horses
https://online.equipe.com/api/v1/meetings/69835/riders

#Endpoints
GET  /?meeting_id=<id>                          — download stævnet som Excel
GET  /meetings/<id>                              — rytter-tjekliste (synker fra Equipe ved hvert kald)
POST /meetings/<id>/riders/<rider_id>/seen       — marker (eller genmarker) en rytter som "set"
GET  /meetings/<id>/export                       — samme Excel-download som GET /, linket fra tjeklisten

#Auth
Alle endpoints kræver HTTP Basic Auth. Sæt disse env vars før programmet startes (både lokalt og i docker):
AUTH_USERNAME
AUTH_PASSWORD

#Database
Tjeklisten (ryttere/starter/"set"-status) gemmes i en SQLite-fil. Sti sættes via env var DATABASE_URL,
default er sqlite:///./equipe.db lokalt. I docker-compose peger den på et navngivet volume (/data),
så data ikke forsvinder når containeren genskabes.

#Kør programmet
Kør programmet lokalt (ikke i docker):
export AUTH_USERNAME=... AUTH_PASSWORD=...
uvicorn app.main:app --reload

Byg til docker:
sudo docker build -t equipe-exporter .
sudo docker run -it --rm -p 8000:80 -e AUTH_USERNAME=... -e AUTH_PASSWORD=... equipe-exporter

Kør med docker-compose (læser AUTH_USERNAME/AUTH_PASSWORD fra en lokal .env fil, som ikke er tjekket ind i git):
docker compose up


Byg til Azure Container registry
az acr build --registry svejdaltech --image equipe-extractor .
