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
GET  /                                           — Stævne-genvej: bogmærke-siden (se #Bogmærke), hvis meeting_id udelades
GET  /?meeting_id=<id>                          — download stævnet som Excel
GET  /meetings/<id>                              — rytter-tjekliste (synker fra Equipe ved hvert kald)
POST /meetings/<id>/riders/<rider_id>/seen       — marker (eller genmarker) en rytter som "set"
GET  /meetings/<id>/export                       — samme Excel-download som GET /, linket fra tjeklisten
GET  /calendar/<CALENDAR_TOKEN>.ics              — kalender-feed, ét stævne per synkroniseret meeting (se #Kalender)
GET  /settings                                   — indstillinger (pt. Excel-kolonnerækkefølge), se #Excel-kolonner

#Auth
Alle almindelige endpoints kræver HTTP Basic Auth. Sæt disse env vars før programmet startes (både lokalt og i docker):
AUTH_USERNAME
AUTH_PASSWORD

#Bogmærke
Forsiden (/ uden meeting_id) viser altid "Stævne-genvej" — bogmærket der springer fra et stævne på
online.equipe.com direkte til rytter-tjeklisten her. Selvhostet, så det altid kan hentes igen, hvis
det mistes fra browserens bogmærkelinje. Bruger samme PUBLIC_BASE_URL som kalender-feedet (se
#Kalender) til at vide hvilket domæne bogmærket skal pege på.

#Kalender
Kalender-feedet (/calendar/<token>.ics) bruger IKKE Basic Auth — de fleste kalender-apps kan ikke abonnere
på et feed bag Basic Auth. I stedet er selve tokenet hemmeligheden. Sæt env var:
CALENDAR_TOKEN — et langt tilfældigt token, fx genereret med: openssl rand -hex 32
Uden CALENDAR_TOKEN sat giver endpointet 404 (kalender-feedet er altså slået fra som standard).

Sæt evt. også PUBLIC_BASE_URL (fx https://equipe.svejdaltech.dk) så links i kalenderen peger rigtigt —
uden den bruges request'ens eget host, hvilket kan blive forkert bag en reverse proxy.

Abonnér på feedet fra jeres kalender-app:
https://equipe.svejdaltech.dk/calendar/<CALENDAR_TOKEN>.ics
— Google Calendar: "Andre kalendere" → "Fra URL"
— Apple Calendar: Arkiv → "Nyt kalenderabonnement"
— Outlook: "Tilføj kalender" → "Abonnér fra web"
Stævner dukker automatisk op i feedet, første gang nogen besøger /meetings/<id> (fx via bookmarkleten).

#Database
Tjeklisten (ryttere/starter/"set"-status) gemmes i en SQLite-fil. Sti sættes via env var DATABASE_URL,
default er sqlite:///./equipe.db lokalt. I docker-compose peger den på et navngivet volume (/data),
så data ikke forsvinder når containeren genskabes.

#Excel-kolonner
Kolonnerækkefølgen i Excel-eksporten styres fra selve appen, ikke .env — gå til /settings (kræver
Basic Auth, samme login som resten), og indtast en kommasepareret liste af kolonnenavne, fx:
rider_name,horse_name,club_name,start_no,start_at
Kolonner der ikke er nævnt, kommer efter i deres oprindelige rækkefølge. Ændringer gælder med det
samme på næste eksport — ingen genstart af containeren nødvendig. Tom værdi = standard-rækkefølgen
(competition_name, start_time, class_no, rider_name, horse_name, ...).

#Kør programmet
Kør programmet lokalt (ikke i docker):
export AUTH_USERNAME=... AUTH_PASSWORD=...
uvicorn app.main:app --reload

Byg til docker:
sudo docker build -t equipe-exporter .
sudo docker run -it --rm -p 8000:80 -e AUTH_USERNAME=... -e AUTH_PASSWORD=... equipe-exporter

Kør med docker-compose (læser AUTH_USERNAME/AUTH_PASSWORD/CALENDAR_TOKEN m.fl. fra en lokal .env fil, som ikke er tjekket ind i git):
docker compose up

#Deploy til produktion
Produktion (equipe.svejdaltech.dk) kører på en anden server end udvikling, direkte via docker/docker-compose
(ikke Azure Container Registry — den er ikke længere i brug). På serveren:
git pull
docker compose up -d --build
Husk at .env på serveren skal indeholde AUTH_USERNAME/AUTH_PASSWORD, og CALENDAR_TOKEN/PUBLIC_BASE_URL hvis
kalender-feedet skal bruges (se #Kalender).
