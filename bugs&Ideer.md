### Fejl ###
1. Kendt fejl at ved ændring af status i Rediger, bliver kommentaren aktuelt slettet. (Ligner en fejl i opdater_tabel i gui.py) FIXED, setrow øverst i if statement i funktionen kaldte tabel og ikke tabel_arkiv ved arkivsidens opbygning. [FIXED]

2. Redigering af medarbejdere bliver ikke ændret i JSON filerne.  Medarbejder Dialog når medarbejder blev valgt satte ikke kommentarens indhold i dialog boksen og blev derfor tom. [FIXED]

3. Status-ændring ved brug af knappen bliver ikke ændret i JSON filerne. Ved metoden skift_status blev kun tabellen gemt, men ingen opdatering gemt i filen. [FIXED]

4. 

### Ideer ###
1. Arkiv interface, skal vise hvilke brugere der er arkiveret. [LAVET]

2. Faner med forskellige sider i programmet, så man kan vælge imellem arkiv, aktiv eller Dashboard. [LAVET]

3. Dashboard skal vise både arkivside og aktive. [LAVET]

4. Timet/Dynamisk dashboard opdatering [LAVET]

5. Flere visuelle udvidelser til dashboardet. 

