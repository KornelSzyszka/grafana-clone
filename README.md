# Grafana Clone

Projekt kursowy oparty o `Django + PostgreSQL`, którego celem jest:

* generowanie danych i kontrolowanego ruchu aplikacyjnego,
* zbieranie statystyk z PostgreSQL,
* analiza heurystyczna problemów wydajnościowych,
* porównywanie snapshotów before/after dla eksperymentów optymalizacyjnych.

Repo jest dziś w stanie "foundation + comparison": fundament domeny, seedowanie, workload, monitoring, analiza i porównanie snapshotów są już gotowe. Główny kolejny krok to pełna walidacja end-to-end na żywym PostgreSQL.

## Co już mamy

W repo działa już:

* aplikacja `shop` z modelami `Category`, `Product`, `Order`, `OrderItem`, `Review`,
* endpointy JSON dla katalogu, szczegółu produktu, historii zamówień i raportu sprzedaży,
* aplikacja `load_simulator` z komendami `seed_data`, `clear_demo_data`, `simulate_load`,
* aplikacja `db_monitor` z modelami snapshotów, kolektorem statystyk, heurystykami i komendami:
  `collect_stats`, `analyze_stats`, `compare_snapshots`,
* PostgreSQL-first konfiguracja aplikacji,
* `docker-compose` z PostgreSQL i `pg_stat_statements`,
* kontrolowane problemy wydajnościowe do eksperymentów before/after,
* testy dla warstwy monitoringu, analizy i porównania snapshotów.

## Co musimy mieć

Minimalne wymagania do pracy developerskiej:

* Python `3.11+`,
* wirtualne środowisko z zależnościami z [`requirements/base.txt`](/C:/Users/kszys/Desktop/PWr/INFORMATYKA%20TECHNICZNA/Bazy%20Danych/grafana-clone/requirements/base.txt),
* PostgreSQL z włączonym `pg_stat_statements` do właściwego flow monitoringu,
* opcjonalnie Docker Desktop / Docker Engine do uruchomienia lokalnej bazy przez `docker compose`.

Aktualne zależności Pythona:

* `django==5.2.12`
* `faker==40.11.1`
* `psycopg[binary]==3.2.12`

## Architektura

Projekt jest podzielony na 3 główne obszary:

* `shop`
  warstwa domenowa i endpointy JSON; tu znajdują się modele biznesowe oraz kontrolowane problemy wydajnościowe.
* `load_simulator`
  seedowanie danych demonstracyjnych i generowanie powtarzalnego workloadu.
* `db_monitor`
  zapis snapshotów statystyk PostgreSQL, analiza heurystyczna i porównanie dwóch uruchomień.

Zależność między modułami jest celowo prosta:

1. `shop` dostarcza zapytania i endpointy.
2. `load_simulator` obciąża `shop`.
3. `db_monitor` zbiera i analizuje skutki tego obciążenia w PostgreSQL.

## Struktura repo

Najważniejsze katalogi:

```text
grafana-clone/
|-- config/                    # konfiguracja Django
|-- shop/                      # modele domenowe, endpointy, logika zapytań
|-- load_simulator/            # seedowanie i workload
|-- db_monitor/                # snapshoty, kolektory, heurystyki, compare
|-- docker/
|   `-- postgres/init/         # inicjalizacja pg_stat_statements
|-- docs/                      # dokumentacja domenowa i controlled issues
|-- requirements/              # zależności Pythona
|-- agents/                    # stan projektu: done/todo dla kolejnych iteracji
|-- docker-compose.yml         # lokalny PostgreSQL baseline
|-- manage.py
`-- .env.example
```

Najważniejsze pliki wejściowe:

* [`config/settings.py`](/C:/Users/kszys/Desktop/PWr/INFORMATYKA%20TECHNICZNA/Bazy%20Danych/grafana-clone/config/settings.py)
* [`docker-compose.yml`](/C:/Users/kszys/Desktop/PWr/INFORMATYKA%20TECHNICZNA/Bazy%20Danych/grafana-clone/docker-compose.yml)
* [`docs/controlled_performance_issues.md`](/C:/Users/kszys/Desktop/PWr/INFORMATYKA%20TECHNICZNA/Bazy%20Danych/grafana-clone/docs/controlled_performance_issues.md)
* [`agents/README.md`](/C:/Users/kszys/Desktop/PWr/INFORMATYKA%20TECHNICZNA/Bazy%20Danych/grafana-clone/agents/README.md)

## Endpointy API

Aktualnie dostępne endpointy:

* `GET /`
* `GET /api/products/`
* `GET /api/products/<slug>/`
* `GET /api/users/<user_id>/orders/`
* `GET /api/reports/sales/`

Routing jest zdefiniowany w:

* [`config/urls.py`](/C:/Users/kszys/Desktop/PWr/INFORMATYKA%20TECHNICZNA/Bazy%20Danych/grafana-clone/config/urls.py)
* [`shop/urls.py`](/C:/Users/kszys/Desktop/PWr/INFORMATYKA%20TECHNICZNA/Bazy%20Danych/grafana-clone/shop/urls.py)

## Controlled Performance Issues

Projekt celowo zawiera problemy wydajnościowe potrzebne do eksperymentów:

* `N+1` w historii zamówień,
* brak indeksu dla ścieżki filtrowania po `Product.created_at`,
* kosztowne wyszukiwanie tekstowe po `name` i `description`,
* kandydat na nieużywany indeks `shop_product_stock_idx`.

Opis znajduje się w [`docs/controlled_performance_issues.md`](/C:/Users/kszys/Desktop/PWr/INFORMATYKA%20TECHNICZNA/Bazy%20Danych/grafana-clone/docs/controlled_performance_issues.md).

Mechanizm jest sterowany flagą:

* `ENABLE_CONTROLLED_PERFORMANCE_ISSUES=true|false`

Ważne: tych problemów nie usuwamy z kodu "na sztywno". Flow before/after ma działać przez zmianę flagi środowiskowej, nie przez ręczne cofanie implementacji.

## Zmienne środowiskowe

Przykładowe wartości są w [`.env.example`](/C:/Users/kszys/Desktop/PWr/INFORMATYKA%20TECHNICZNA/Bazy%20Danych/grafana-clone/.env.example).

Najważniejsze zmienne:

* `DJANGO_DEBUG=true|false`
* `DJANGO_SECRET_KEY=...`
* `DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost`
* `APP_TIME_ZONE=Europe/Warsaw`
* `ENABLE_CONTROLLED_PERFORMANCE_ISSUES=true|false`
* `DB_ENGINE=postgresql|sqlite`
* `DB_NAME=...`
* `DB_USER=...`
* `DB_PASSWORD=...`
* `DB_HOST=...`
* `DB_PORT=...`

Domyślny i zalecany tryb pracy to:

* `DB_ENGINE=postgresql`
* `DB_HOST=127.0.0.1`
* `DB_PORT=5432`
* `ENABLE_CONTROLLED_PERFORMANCE_ISSUES=true`

## Jak postawić środowisko

### 1. Python i zależności

Na Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements/base.txt
```

### 2. Konfiguracja środowiska

Skopiuj wartości z `.env.example` do własnego środowiska albo ustaw zmienne ręcznie.

Minimalny zestaw pod PostgreSQL:

```powershell
$env:DB_ENGINE="postgresql"
$env:DB_NAME="grafana_clone"
$env:DB_USER="postgres"
$env:DB_PASSWORD="postgres"
$env:DB_HOST="127.0.0.1"
$env:DB_PORT="5432"
$env:ENABLE_CONTROLLED_PERFORMANCE_ISSUES="true"
```

### 3. PostgreSQL przez Docker

Najprostsza ścieżka lokalna:

```powershell
docker compose up -d postgres
docker compose ps
```

Konfiguracja Dockera:

* używa obrazu `postgres:17`,
* wystawia port `5432`,
* ładuje `shared_preload_libraries=pg_stat_statements`,
* tworzy rozszerzenie przez [`01_enable_pg_stat_statements.sql`](/C:/Users/kszys/Desktop/PWr/INFORMATYKA%20TECHNICZNA/Bazy%20Danych/grafana-clone/docker/postgres/init/01_enable_pg_stat_statements.sql).

Jeśli nie używasz Dockera, możesz wskazać zewnętrzny PostgreSQL, ale musi on mieć włączone `pg_stat_statements`.

### 4. Migracje i dane

Po uruchomieniu bazy:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_data --size=small
```

### 5. Start aplikacji

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

API będzie dostępne lokalnie pod adresem `http://127.0.0.1:8000/`.

## Komendy management

### Seedowanie i czyszczenie

```powershell
.\.venv\Scripts\python.exe manage.py seed_data --size=small
.\.venv\Scripts\python.exe manage.py seed_data --size=medium
.\.venv\Scripts\python.exe manage.py clear_demo_data
```

### Symulacja ruchu

```powershell
.\.venv\Scripts\python.exe manage.py simulate_load --scenario=default --duration=30
.\.venv\Scripts\python.exe manage.py simulate_load --scenario=catalog --iterations=500
```

Dostępne scenariusze:

* `default`
* `catalog`
* `details`
* `order_history`
* `reporting`

### Monitoring i analiza

```powershell
.\.venv\Scripts\python.exe manage.py collect_stats --label=baseline --environment=local
.\.venv\Scripts\python.exe manage.py analyze_stats --label=baseline
.\.venv\Scripts\python.exe manage.py compare_snapshots before after
```

Przydatne opcje:

* `collect_stats --query-limit=200 --activity-limit=50 --skip-activity`
* `analyze_stats --snapshot-id=<id>`
* `compare_snapshots <snapshot_a> <snapshot_b> --top=5 --format=text|json`

## Zalecany flow before/after

Pełny eksperyment powinien wyglądać tak:

1. Uruchomić PostgreSQL.
2. Wykonać `migrate`.
3. Wykonać `seed_data --size=medium`.
4. Z `ENABLE_CONTROLLED_PERFORMANCE_ISSUES=true` uruchomić workload.
5. Zebrać snapshot `before` i uruchomić `analyze_stats`.
6. Przełączyć tylko flagę `ENABLE_CONTROLLED_PERFORMANCE_ISSUES=false`.
7. Uruchomić workload ponownie.
8. Zebrać snapshot `after` i uruchomić `analyze_stats`.
9. Porównać wyniki przez `compare_snapshots before after`.

Przykład:

```powershell
.\.venv\Scripts\python.exe manage.py simulate_load --scenario=default --iterations=500
.\.venv\Scripts\python.exe manage.py collect_stats --label=before --environment=controlled-issues
.\.venv\Scripts\python.exe manage.py analyze_stats --label=before

$env:ENABLE_CONTROLLED_PERFORMANCE_ISSUES="false"

.\.venv\Scripts\python.exe manage.py simulate_load --scenario=default --iterations=500
.\.venv\Scripts\python.exe manage.py collect_stats --label=after --environment=issues-disabled
.\.venv\Scripts\python.exe manage.py analyze_stats --label=after
.\.venv\Scripts\python.exe manage.py compare_snapshots before after
```

## Co jeszcze nie jest skończone

Na dziś otwarte pozostają głównie:

* pełna walidacja end-to-end na żywym PostgreSQL,
* zapis wyników pierwszego realnego eksperymentu before/after,
* dashboard lub warstwa reportingowa nad zebranymi snapshotami i findings.

Aktualny stan planu i postępu prac jest utrzymywany w katalogu [`agents/`](/C:/Users/kszys/Desktop/PWr/INFORMATYKA%20TECHNICZNA/Bazy%20Danych/grafana-clone/agents/).

## Uwagi o SQLite

SQLite nadal może być użyte jako awaryjny fallback do części prostych prac lokalnych i testów:

```powershell
$env:DB_ENGINE="sqlite"
.\.venv\Scripts\python.exe manage.py test db_monitor
```

To nie jest jednak docelowy runtime dla monitoringu i analizy. Właściwy tor projektu to PostgreSQL.
