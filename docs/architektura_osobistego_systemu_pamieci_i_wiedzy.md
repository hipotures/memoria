# Architektura osobistego systemu pamięci, wiedzy i działania

## Status dokumentu

- Status: draft roboczy
- Cel: dokument założycielski projektu
- Zakres: architektura logiczna i operacyjna systemu
- Język implementacji rdzenia: rekomendowany Python
- Model integracji: polyglot connectors + monoglot core

---

# 1. Cel systemu

System ma być **osobistym centrum pamięci, wyszukiwania, syntezy i działania**.

Nie jest to klasyczna „wiki” w sensie produktu końcowego. Warstwa wikiopodobna jest tylko jedną z projekcji wiedzy. Rzeczywistym celem systemu jest:

1. **zbieranie danych z wielu źródeł**,
2. **ujednolicanie ich do wspólnego modelu kanonicznego**,
3. **przetwarzanie ich przez pipeline ekstrakcji i interpretacji**,
4. **budowanie trwałej warstwy wiedzy ponad źródłami**,
5. **umożliwienie wyszukiwania, odtwarzania pamięci, syntezy i proponowania działań**,
6. **zamknięcie pętli wejście → wiedza → działanie → nowe wejście**.

System ma umożliwiać zarówno:

- proste odnalezienie konkretnego artefaktu,
- jak i syntezę wieloźródłową,
- jak i generowanie działań wyjściowych z zatwierdzeniem użytkownika.

---

# 2. Problem, który system rozwiązuje

Użytkownik posiada wiele rozproszonych źródeł danych:

- screenshoty,
- maile,
- SMS-y i komunikatory,
- PDF-y i dokumenty,
- pliki lokalne,
- historię przeglądania,
- bookmarki,
- komentarze w serwisach społecznościowych,
- zdjęcia i obrazy,
- inne archiwa cyfrowe.

Bez wspólnego systemu:

- każde źródło ma osobny interfejs,
- każde źródło ma inną strukturę,
- wiedza pozostaje rozproszona,
- te same osoby, sprawy i tematy pojawiają się w wielu miejscach bez scalania,
- odpowiedzi trzeba odtwarzać od zera,
- przeszukiwanie jest słabe lub zbyt zależne od pamiętania dokładnych słów.

System ma zamienić tę sytuację w model, w którym:

- źródła są przechowywane oddzielnie i zachowują proveniencję,
- relacje między nimi są wykrywane i przechowywane,
- wiedza jest konsolidowana nad źródłami,
- użytkownik pracuje głównie z poziomu asystenta i warstwy wiedzy, a nie z poziomu pojedynczych skrzynek, katalogów i aplikacji.

---

# 3. Założenia projektowe

## 3.1. Zasady ogólne

1. **Źródła są niezmienne.**
   System nie modyfikuje danych źródłowych.

2. **Core ma jeden wspólny model kanoniczny.**
   Niezależnie od typu źródła, każdy obiekt wchodzi do systemu przez wspólny envelope.

3. **Connectory mogą być polyglot.**
   Mogą być pisane w Pythonie, JavaScripcie lub innym języku, o ile emitują zgodny kontrakt.

4. **Rdzeń systemu powinien być monolityczny językowo.**
   Rekomendacja: Python dla rdzenia i pipeline'ów.

5. **Warstwa wiedzy nie jest kopią źródeł.**
   Jest ich interpretacją, konsolidacją i projekcją.

6. **System musi wspierać dwa tryby ingestu:**
   - `index_only`
   - `absorb`

7. **Relacje i tożsamość są pierwszorzędne.**
   Relacje między źródłami, identyfikacja tych samych osób i scalanie bytów nie są dodatkiem — są rdzeniem.

8. **System jest inkrementalny.**
   Nowe źródła nie tworzą nowego świata od zera. Aktualizują istniejący model wiedzy.

9. **Wiedza ma lifecycle.**
   Claims mogą być wzmacniane, osłabiane, supersedowane i deprioritizowane.

10. **Finalnym interfejsem użytkownika nie są pliki markdown.**
    Markdown może być projekcją. Głównym interfejsem ma być warstwa asystencka, wyszukiwarka i widoki wiedzy.

---

# 4. Model wysokopoziomowy

System składa się z siedmiu warstw:

1. **Source Connectors**
2. **Ingress / Connector Gateway**
3. **Canonical Store**
4. **Processing & Enrichment Pipelines**
5. **Identity, Relations & Knowledge Core**
6. **Retrieval & Assistant Layer**
7. **Sink / Action Connectors**

## 4.1. Skrót przepływu

```text
Źródło -> Connector -> Canonical Envelope -> Ingress -> Canonical Store
       -> Extract / Interpret / Relate / Resolve Identity
       -> Retrieval Projection + Knowledge Projection
       -> Query / Recall / Synthesis / Actions
       -> Sink Connector
       -> Nowe źródło lub nowy stan systemu
```

---

# 5. Warstwa 1: Source Connectors

## 5.1. Rola konektorów

Konektor odpowiada za:

- odnalezienie danych w zewnętrznym systemie,
- odczyt danych,
- zmapowanie ich do wspólnego envelope,
- przekazanie ich do core,
- przekazanie znanych natywnie relacji źródłowych,
- zadeklarowanie profilu źródła i typów emitowanych artefaktów.

Konektor **nie odpowiada** za główną logikę przetwarzania wiedzy.

## 5.2. Typy konektorów

### Konektory wejściowe
Przykłady:
- screenshoty,
- email,
- SMS / chat,
- browser history,
- bookmarks,
- PDF / file import,
- social comments,
- zdjęcia,
- eksporty archiwów.

### Konektory wyjściowe
Przykłady:
- email sink,
- SMS/chat sink,
- task/calendar sink,
- export sink,
- webhook/automation sink.

## 5.3. Minimalny kontrakt logiczny konektora

Każdy konektor powinien implementować logicznie cztery kroki:

1. `discover()` — znajdź kandydatów do importu,
2. `fetch()` — pobierz surowy obiekt,
3. `normalize_to_envelope()` — zmapuj do wspólnego schematu,
4. `emit()` — wyślij do ingressu.

## 5.4. Connector Manifest

Każdy konektor powinien posiadać manifest opisujący:

- `connector_id`
- `connector_type`
- `source_family`
- `schema_version`
- `connector_version`
- emitowane typy artefaktów,
- wspierane relacje źródłowe,
- domyślny tryb (`index_only` / `absorb`),
- sugerowany profil processingu,
- opcjonalne override'y.

Manifest ma być deklaratywny, nie proceduralny.

---

# 6. Warstwa 2: Ingress / Connector Gateway

Ingress jest jedynym stabilnym punktem wejścia do rdzenia systemu.

## 6.1. Odpowiedzialności ingressu

- walidacja envelope względem JSON Schema,
- wersjonowanie schematu,
- idempotencja,
- dedup wstępny,
- zapis blobów i artefaktów,
- utworzenie rekordu `source_item`,
- zapis payloadów źródłowych,
- rejestracja relacji źródłowych zadeklarowanych przez konektor,
- wygenerowanie zdarzenia `source_ingested`.

## 6.2. Zalecane interfejsy ingressu

### Startowo
- HTTP API
- batch import przez NDJSON / JSONL

### Później
- kolejka lub event bus

## 6.3. Dlaczego ingress musi być centralny

Bez wspólnego ingressu connectory zaczęłyby pisać bezpośrednio do wewnętrznych tabel rdzenia, co zniszczyłoby:

- spójność,
- wersjonowanie,
- walidację,
- audyt,
- możliwość przepinania konektorów między językami.

---

# 7. Warstwa 3: Canonical Store

Canonical Store przechowuje:

- uniwersalny rekord źródła,
- payload źródłowy,
- artefakty,
- fragmenty treści,
- relacje źródłowe,
- historię pipeline'ów.

To jest warstwa autorytatywna operacyjnie.

## 7.1. Główne grupy danych

### `source_items`
Minimalny wspólny rekord niezależny od typu źródła.

Pola przykładowe:
- `id`
- `source_type`
- `source_family`
- `connector_instance_id`
- `external_id`
- `dedup_key`
- `mode`
- `status`
- `source_created_at`
- `source_observed_at`
- `ingested_at`
- `raw_ref`

### `source_payloads_*`
Tabele specyficzne dla typu źródła.

Przykłady:
- `source_payloads_email`
- `source_payloads_screenshot`
- `source_payloads_social`
- `source_payloads_pdf`

### `blobs`
Przechowują fizyczne artefakty lub ich referencje.

### `content_fragments`
Fragmenty treści ujednolicone między źródłami.

Przykłady typów:
- `plain_text`
- `ocr_text`
- `subject`
- `body_text`
- `title`
- `caption`
- `html_text`
- `alt_text`
- `scene_description`

### `source_relations`
Relacje techniczne i proveniencyjne między źródłami.

Przykłady:
- `attached_to`
- `downloaded_from`
- `same_blob_as`
- `same_thread_as`
- `reply_to`
- `derived_from`

### `pipeline_runs` / `stage_results`
Historia przetwarzania i stan etapów pipeline'u.

---

# 8. Canonical Envelope

Canonical Envelope jest wspólnym kontraktem wejściowym dla wszystkich konektorów.

## 8.1. Funkcja envelope

Ma opisywać:
- skąd obiekt pochodzi,
- kiedy powstał,
- czym jest w najogólniejszym sensie,
- jakie ma artefakty,
- jakie ma payloady specyficzne,
- jakie relacje źródłowe są już znane,
- jaki jest domyślny tryb przetwarzania.

## 8.2. Envelope nie jest pełnym modelem semantycznym

Nie powinien zawierać docelowej wiedzy ani złożonej interpretacji. To przychodzi później.

## 8.3. Konsekwencja architektoniczna

Nowy konektor powinien być dodawalny przez:

1. napisanie adaptera źródła,
2. zmapowanie do envelope,
3. zadeklarowanie manifestu,
4. opcjonalne dodanie payloadu specyficznego.

Bez modyfikacji całego rdzenia.

---

# 9. Warstwa 4: Processing & Enrichment Pipelines

Pipeline odpowiada za przekształcenie danych kanonicznych w interpretacje, relacje i projekcje.

## 9.1. Zasada architektoniczna

Konektor **nie definiuje proceduralnie** całego processingu. Konektor deklaruje:

- typy danych,
- profil źródła,
- ewentualne override'y.

Core składa plan przetwarzania przez **policy engine**.

## 9.2. Typy procesorów

### Procesory ekstrakcji
- OCR,
- PDF text extract,
- HTML cleanup,
- metadata extraction,
- EXIF parsing,
- thread parsing,
- attachment discovery.

### Procesory interpretacji
- klasyfikacja tekstu,
- klasyfikacja dokumentu,
- VLM description / scene description,
- entity extraction,
- topic extraction,
- action candidate extraction,
- sentiment / tone if needed,
- summary generation.

### Procesory relacyjne
- attachment linking,
- thread reconstruction,
- dedup content linking,
- same-document / same-blob detection,
- sequence grouping.

### Procesory tożsamości
- identifier extraction,
- identity matching,
- alias merging,
- candidate match scoring.

## 9.3. Policy Engine

Policy engine buduje plan przetwarzania na podstawie:

- typu artefaktu,
- `source_family`,
- `connector_type`,
- `connector_instance_id`,
- trybu `index_only` / `absorb`,
- profilu przetwarzania,
- budżetu przetwarzania,
- override'ów.

## 9.4. Processing profiles

Przykładowe profile:
- `screenshots_heavy`
- `email_standard`
- `social_mixed`
- `document_standard`
- `photo_archive_light`

## 9.5. Poziomy agresywności processingu

- `minimal`
- `standard`
- `deep`

Pozwala to ograniczać koszt i złożoność dla różnych typów źródeł.

## 9.6. Routing

Po interpretacji obiekt powinien być skierowany do jednego z trybów:

- `index_only`
- `absorb`
- `review`
- `skip`

---

# 10. Warstwa 5A: Identity Layer

Identity Layer odpowiada za łączenie różnych identyfikatorów i obserwacji w spójne byty.

## 10.1. Problem

Ta sama osoba może pojawić się jako:
- email,
- numer telefonu,
- handle społecznościowy,
- podpis w wiadomości,
- wpis w kontaktach,
- imię i nazwisko w PDF-ie,
- wzmianka w screenshotach.

System musi umieć rozstrzygać, czy to ten sam byt.

## 10.2. Główne elementy

### `entities`
Byty bazowe, np. osoba, organizacja, konto, miejsce.

### `entity_identifiers`
Identyfikatory należące do bytów:
- email,
- phone,
- handle,
- alias,
- full name,
- username,
- external account id.

### `entity_matches`
Proponowane lub zatwierdzone scalenia.

Statusy:
- `auto_merged`
- `pending_review`
- `rejected`
- `confirmed`

## 10.3. Zasada bezpieczeństwa

Nie wszystkie merge'e powinny być automatyczne. Dla wyników średniej pewności system powinien proponować kandydatów do review.

---

# 11. Warstwa 5B: Relations Layer

Relations Layer przechowuje relacje, które nie są czystą tożsamością ani jeszcze gotową wiedzą domenową.

## 11.1. Typy relacji

### Relacje źródłowe
- `attached_to`
- `downloaded_from`
- `reply_to`
- `same_thread_as`
- `derived_from`
- `references_url`

### Relacje bytów
- `has_email`
- `has_phone`
- `has_handle`
- `same_as`
- `likely_same_as`

### Relacje semantyczne wstępne
- `mentions_person`
- `mentions_project`
- `related_to_topic`
- `part_of_conversation`

## 11.2. Rola relacji

Warstwa relacji jest pomostem między źródłami a knowledge layer. To tu źródła zaczynają tworzyć wspólną sieć znaczeń.

---

# 12. Warstwa 5C: Knowledge Core

Knowledge Core to serce systemu. To nie jest kopia źródeł, tylko skonsolidowana warstwa wiedzy.

## 12.1. Knowledge Objects

Przykładowe typy:
- `person`
- `topic`
- `project`
- `task`
- `thread`
- `conversation`
- `relationship`
- `decision`
- `document_cluster`
- `place`
- `event`
- `pattern`
- `claim_digest`

## 12.2. Knowledge Claims

Pojedyncze twierdzenia wiedzy.

Przykłady:
- „Kontakt z Alicją w ostatnim kwartale dotyczył głównie wyjazdu do Berlina.”
- „Ten PDF jest załącznikiem do wiadomości w sprawie faktury.”
- „Istnieje otwarty task: kupić bilet.”

Claims nie powinny być bezkontekstowe.

## 12.3. Evidence Links

Każdy claim powinien być powiązany z dowodami:
- source item,
- fragment treści,
- interpretacja,
- confidence,
- support type.

## 12.4. Knowledge Relations

Relacje między obiektami wiedzy:
- `involves_person`
- `belongs_to_topic`
- `supports_claim`
- `caused_task`
- `supersedes`
- `contradicts`
- `depends_on`
- `part_of`

---

# 13. Lifecycle wiedzy

Warstwa wiedzy musi uwzględniać, że wiedza ma czas życia.

## 13.1. Confidence scoring

Każdy claim powinien mieć:
- `confidence_score`
- `support_count`
- `contradiction_count`
- `last_confirmed_at`
- `first_seen_at`
- `source_authority_hint`

## 13.2. Supersession

Nowy claim może:
- osłabić stary,
- uzupełnić stary,
- zastąpić stary,
- explicite go supersedować.

Stary claim nie musi być usuwany, ale powinien być oznaczany jako:
- `active`
- `uncertain`
- `stale`
- `superseded`

## 13.3. Forgetting / deprioritization

Nie wszystko powinno być równie widoczne zawsze.

Należy przewidzieć:
- decay score,
- retention profile,
- access-based reinforcement,
- domain-specific decay.

Przykład:
- transient bug: szybki decay,
- trwała relacja z osobą: wolny decay,
- architektura projektu: bardzo wolny decay.

## 13.4. Consolidation tiers

Wiedza powinna przechodzić przez poziomy:

### Working memory
Świeże obserwacje i interpretacje.

### Episodic memory
Podsumowania sesji, dni, wątków, rozmów.

### Semantic memory
Utrwalone byty, relacje, fakty i modele świata.

### Procedural memory
Playbooki, workflowy, wzorce działania i reakcji.

---

# 14. Retrieval Layer

Retrieval odpowiada za odnajdywanie dowodów i kandydatów do syntezy.

## 14.1. Trzy kanały retrievalu

### 1. Keyword / BM25 / FTS
Do dokładnych trafień tekstowych i wyszukiwania po słowach.

### 2. Graph traversal
Do pytań strukturalnych i odkrywania powiązań.

### 3. Vector / semantic search
Opcjonalnie później, jeśli będzie potrzebny.

## 14.2. Rekomendacja etapowa

### MVP
- SQLite FTS
- filtry po metadanych
- traversal po relacjach i knowledge graph

### Później
- embeddings i fusion retrieval

## 14.3. Cel retrievalu

Nie tylko „znajdź rekord”, ale:
- znajdź dowód,
- znajdź temat,
- znajdź wątek,
- znajdź rozproszony ślad pamięciowy,
- znajdź candidate set do syntezy.

---

# 15. Assistant Layer

Assistant Layer jest głównym interfejsem użytkownika.

Nie zakładamy, że użytkownik będzie głównie chodził po stronach wiki.

## 15.1. Główne tryby pracy

### Retrieval mode
„Znajdź konkretną rzecz.”

### Synthesis mode
„Powiedz mi, co wiem o sprawie / osobie / temacie.”

### Recall mode
„Przypomnij mi, co może być niedomknięte, zapomniane, istotne.”

### Action mode
„Na podstawie tego, co wiesz, przygotuj działanie.”

## 15.2. Query pipeline

1. zrozum pytanie,
2. wyznacz kandydatów po retrieval layer,
3. pobierz knowledge objects,
4. pobierz evidence,
5. syntetyzuj odpowiedź,
6. pokaż dowody lub przypisy na żądanie,
7. opcjonalnie zapisz wynik jako nowy digest / crystallization output.

---

# 16. Sink / Action Layer

System ma wspierać działania wyjściowe.

## 16.1. Przykłady akcji

- draft email,
- draft SMS / wiadomości,
- follow-up,
- utworzenie taska,
- event kalendarza,
- eksport notatki,
- webhook do innego systemu,
- komentarz lub odpowiedź w systemie źródłowym.

## 16.2. Zasada bezpieczeństwa

Domyślnie system działa w modelu:
- propose,
- show reasoning/evidence,
- wait for approval,
- execute.

## 16.3. Pętla systemu

Wysłana wiadomość lub wykonana akcja może wrócić do systemu jako nowe źródło.

To zamyka pętlę:

```text
source -> knowledge -> action -> new source
```

---

# 17. Projekcje i widoki wiedzy

Markdown pages nie są rdzeniem systemu, ale mogą być przydatną projekcją.

## 17.1. Możliwe projekcje

- markdown page,
- HTML view,
- JSON export,
- timeline,
- comparison table,
- dependency graph,
- slide deck,
- structured brief,
- daily digest,
- person summary,
- topic summary.

## 17.2. Rola markdownu

Markdown jest dobry jako:
- snapshot wiedzy,
- eksport,
- materiał do czytania,
- wygodna reprezentacja projekcji.

Nie powinien być głównym magazynem indeksów ani jedynym interfejsem użytkownika.

---

# 18. Event-driven architecture

System powinien być oparty na zdarzeniach.

## 18.1. Kluczowe eventy

- `source_ingested`
- `blob_persisted`
- `content_extracted`
- `interpretation_completed`
- `identity_match_proposed`
- `identity_match_confirmed`
- `knowledge_updated`
- `claim_superseded`
- `query_completed`
- `crystallization_created`
- `action_proposed`
- `action_approved`
- `action_executed`
- `retention_tick`
- `lint_tick`

## 18.2. Korzyści

- łatwiejsza automatyzacja,
- mniejsze sprzężenie,
- prostsze dodawanie workflowów,
- możliwość schedulera i reakcji automatycznych.

---

# 19. Quality Layer i self-healing

System nie może bez końca akumulować niskiej jakości wiedzy.

## 19.1. Co powinno być oceniane

- jakość interpretacji,
- jakość claimów,
- spójność obiektów wiedzy,
- obecność evidence,
- osierocone obiekty,
- konflikty z nowszą wiedzą,
- puste lub zbyt cienkie obiekty wiedzy.

## 19.2. Self-healing

System powinien umieć automatycznie:
- oznaczać stale claims,
- naprawiać broken links w projekcjach,
- flagować osierocone obiekty,
- scalać lub proponować scalenie duplikatów,
- przebudowywać projekcje po zmianach.

---

# 20. Privacy, governance, audit

System będzie przetwarzał dane bardzo wrażliwe.

## 20.1. Ochrona prywatności

Na ingest należy przewidzieć:
- wykrywanie secrets,
- redaction lub maskowanie,
- sensitivity tagging,
- private/shared scope.

## 20.2. Audit trail

Każda istotna operacja powinna być logowana:
- kto / co wykonało operację,
- kiedy,
- na jakich obiektach,
- jaki był wynik,
- jaki claim został zmieniony,
- jaka była przyczyna.

## 20.3. Bulk ops

Operacje masowe powinny być:
- audytowalne,
- odwracalne,
- wersjonowane.

---

# 21. Crystallization

Crystallization to mechanizm zamiany zakończonego łańcucha pracy lub eksploracji w trwały digest wiedzy.

## 21.1. Przykłady wejścia

- długa sesja pytania i odpowiedzi,
- śledztwo po archiwum,
- debugging thread,
- research thread,
- analiza osoby / tematu / sprawy.

## 21.2. Wynik crystallization

- structured digest,
- nowe claims,
- powiązane evidence,
- summary page / view,
- lessons learned,
- feed do semantic/procedural memory.

To jest kluczowy mechanizm zamiany eksploracji w narastający kapitał wiedzy.

---

# 22. Schema / AGENTS.md jako rzeczywisty produkt

Najważniejszym artefaktem sterującym systemem nie jest kod konektorów, tylko centralny dokument polityk i domeny.

Powinien on opisywać:

- typy źródeł,
- typy artefaktów,
- typy encji,
- typy relacji,
- processing profiles,
- polityki routingowe,
- reguły merge,
- poziomy confidence,
- zasady supersession,
- retention,
- privacy scopes,
- quality gates,
- action policies,
- kiedy tworzyć nowe knowledge objects,
- kiedy aktualizować istniejące.

To właśnie ten dokument czyni system konsekwentnym.

---

# 23. Proponowany stack technologiczny

## 23.1. Rdzeń

- Python
- FastAPI
- SQLAlchemy
- Alembic
- SQLite na start
- blob storage na filesystemie

## 23.2. Retrieval

- SQLite FTS w MVP
- ewentualnie dodatkowa warstwa search później

## 23.3. Konektory

- dowolny język
- komunikacja przez HTTP API lub batch NDJSON
- walidacja przez JSON Schema

## 23.4. Scheduler / Eventing

### MVP
- prosta kolejka i worker w Pythonie
- scheduler okresowy

### Później
- event bus / stream system

---

# 24. Etapowanie projektu

## V1 — fundament

Celem V1 jest dowiezienie spójnego, działającego rdzenia.

### Zakres
- screenshot connector,
- email connector,
- ingress API,
- canonical store,
- content extraction,
- minimalny processing policy engine,
- FTS retrieval,
- minimalny identity layer,
- minimalne knowledge objects:
  - person,
  - topic,
  - task,
  - thread,
- query assistant,
- draft email action sink,
- audit podstawowy.

### Cel V1
Udowodnić, że:
- różne źródła da się znormalizować,
- da się po nich wyszukiwać,
- da się tworzyć wiedzę ponad źródłami,
- da się generować akcje z zatwierdzeniem.

## V2 — konsolidacja i jakość

### Zakres
- lifecycle claimów,
- supersession,
- retention,
- quality scoring,
- cleanup / self-healing,
- crystallization,
- lepsze identity resolution,
- więcej source relations,
- więcej sink connectors.

### Cel V2
Sprawić, że system nie tylko działa, ale zaczyna utrzymywać zdrową wiedzę w czasie.

## V3 — skala i automatyzacja

### Zakres
- event-driven architecture pełniej,
- consolidation tiers,
- graph traversal queries,
- optional vector search,
- większa automatyzacja,
- bardziej rozbudowane policy engine,
- privacy scopes i bulk governance,
- collaboration / multi-agent jeśli będzie potrzebne.

### Cel V3
Przekształcić system w dojrzały runtime pamięci i działania.

---

# 25. Co nie jest celem MVP

Na start nie należy wdrażać wszystkiego.

Nie są celem V1:
- pełna wektorowa semantyczna wyszukiwarka,
- pełna automatyzacja wyjściowa bez zatwierdzenia,
- multi-agent mesh sync,
- doskonały UX końcowy,
- obsługa wszystkich źródeł naraz,
- pełna ontologia świata.

MVP ma udowodnić architekturę, nie zamknąć wszystkie tematy.

---

# 26. Kluczowe decyzje architektoniczne

## Decyzja 1
Connectory są polyglot, ale emitują wspólny envelope.

## Decyzja 2
Konektor nie steruje proceduralnie processingiem; robi to centralny policy engine.

## Decyzja 3
Payload źródłowy jest source-specific, ale envelope i fragmenty treści są wspólne.

## Decyzja 4
System rozróżnia:
- source relations,
- identity resolution,
- knowledge relations.

## Decyzja 5
Warstwa wiedzy jest utrzymywana nad źródłami; nie jest ich płaską kopią.

## Decyzja 6
Markdown i strony są projekcją, nie rdzeniem.

## Decyzja 7
Assistant layer jest głównym interfejsem użytkownika.

## Decyzja 8
System wspiera `index_only` i `absorb` jako podstawowe tryby ingestu.

## Decyzja 9
Wiedza ma lifecycle: confidence, supersession, retention.

## Decyzja 10
Architektura jest event-driven i przygotowana na pętlę source -> knowledge -> action -> source.

---

# 27. Otwarta lista pytań projektowych

1. Jak dokładnie modelować `knowledge_object` vs `claim`?
2. Jak agresywnie scalać encje automatycznie?
3. Jak mierzyć confidence i decay w MVP, zanim pojawi się pełny model lifecycle?
4. Jak rozdzielić treść prywatną i współdzieloną, jeśli system kiedyś urośnie?
5. Jaką granularność mają mieć `content_fragments`?
6. Jakie source relations są obowiązkowe w MVP?
7. Czy projekcje markdown mają być generowane synchronicznie czy asynchronicznie?
8. Kiedy query result powinien automatycznie przechodzić w crystallization?
9. Jakie actions są bezpieczne w pierwszej wersji?
10. Jaką część review zostawić użytkownikowi, a jaką w pełni zautomatyzować?

---

# 28. Podsumowanie

Ten system nie jest klasyczną wiki i nie jest tylko wyszukiwarką dokumentów.

Jest:

- warstwą ingestu wielu źródeł,
- systemem ujednolicania danych,
- silnikiem ekstrakcji, interpretacji i relacji,
- grafem tożsamości i wiedzy,
- warstwą retrievalu,
- asystentem pamięci i działania,
- oraz pętlą, w której nowe działania stają się nowymi źródłami.

Najkrótsza definicja projektu:

> Polyglot source-and-sink connector system feeding a canonical evidence store, processed by a monoglot knowledge core that builds retrieval, identity, memory, and action capabilities over personal data.

To jest zalążek projektu, który może rosnąć modułowo: od screenshotów, przez maile, po pełne osobiste centrum pamięci i działania.

