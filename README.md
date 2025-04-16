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

#Kør programmet
Kør programmet lokalt (ikke i docker):
uvicorn app.main:app --reload

Byg til docker:
sudo docker build -t equipe-exporter .
sudo docker run -it --rm -p 8000:80 equipe-exporter
