<p align="center">
  <img src="docs/images/logo.svg" width="96" height="96" alt="Logo di Steward for Immich">
</p>

<h1 align="center">Steward for Immich</h1>

<p align="center">
  Rimetti sulla mappa le tue foto senza GPS — più indizi indipendenti, una sola mappa, scegli tu.
</p>

<p align="center">
  <a href="https://github.com/Ivamic/immich-steward/releases"><img src="https://img.shields.io/github/v/release/Ivamic/immich-steward?include_prereleases&sort=semver" alt="Versione"></a>
  <a href="https://github.com/Ivamic/immich-steward/actions/workflows/ci.yml"><img src="https://github.com/Ivamic/immich-steward/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/Ivamic/immich-steward" alt="Licenza: AGPL-3.0"></a>
  <img src="https://img.shields.io/badge/self--hosted-Docker%20Compose-2496ED?logo=docker&logoColor=white" alt="Self-hosted con Docker Compose">
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.de.md">Deutsch</a> · <a href="README.fr.md">Français</a> · <b>Italiano</b> · <a href="README.ru.md">Русский</a>
</p>

<p align="center">
  <img src="docs/images/time-neighbors-route.png" alt="Scheda della foto: il tragitto tra le foto scattate poco prima e poco dopo, con tre luoghi suggeriti sulla mappa e nell'elenco">
</p>

> Questa è una traduzione, realizzata con l'aiuto dell'IA, del [README inglese](README.md), che
> resta il testo di riferimento. La documentazione e la parte per gli sviluppatori per ora sono
> solo in inglese. Le correzioni alla traduzione sono molto gradite.

> [!IMPORTANT]
> **Aggiornare alla 0.6 dalla 0.5 o precedente: un passo a mano, una volta sola.**
>
> **Perché.** Fino alla 0.5, `compose.yaml` indicava la versione esatta dell'app, quindi ogni
> aggiornamento richiedeva anche `git pull`. Dalla 0.6, `compose.yaml` segue la versione
> principale e legge tutte le impostazioni da `.env`: resta uguale, e ogni aggiornamento
> successivo è solo `docker compose pull` e `docker compose up -d`.
>
> **Come.** Nella cartella dell'app; il tuo `.env` e i tuoi dati restano come sono.
>
> Senza il worker:
>
> ```sh
> curl -L -o compose.yaml https://github.com/Ivamic/immich-steward/releases/latest/download/compose.yaml
> docker compose pull
> docker compose up -d
> ```
>
> Con il worker sul server:
>
> ```sh
> curl -L -o compose.yaml https://github.com/Ivamic/immich-steward/releases/latest/download/compose.yaml
> docker compose --profile worker pull
> docker compose --profile worker up -d
> ```
>
> Se `.env` ha una riga `STEWARD_VERSION=…`, toglila prima: terrebbe la versione vecchia. [Dettagli](docs/updating.md#coming-from-05-or-older) (in inglese).

> **Stato: in sviluppo attivo.** Una prima versione: la revisione delle foto senza posizione, i
> suggerimenti dalle foto vicine nel tempo, GeoCLIP e le foto simili della tua libreria
> funzionano già; gli altri moduli arriveranno. Aspettati bug e cambiamenti tra una versione e
> l'altra, e fai un backup della tua libreria Immich prima di scriverci delle posizioni.

Un'app di supporto self-hosted per [Immich](https://immich.app). Per ogni foto senza posizione, più
moduli — le foto scattate poco prima e poco dopo, la rete neurale GeoCLIP e le foto simili
dello stesso luogo nella tua libreria — suggeriscono dove è stata scattata, tutti su una sola
mappa. Scegli con un clic o un tasto, oppure imposti la posizione di molte foto in una volta.
In Immich non viene scritto nulla finché non lo fai tu, e ogni modifica si può annullare.

Caso tipico: un archivio fotografico di famiglia con stampe scansionate, vecchie fotocamere
digitali senza GPS o foto scaricate dalle app di messaggistica che hanno perso i metadati.

## L'idea

L'app unisce diversi **moduli di localizzazione** indipendenti. Ogni modulo propone uno o più
luoghi possibili, e tutte le proposte vengono mostrate insieme su una mappa, con un colore per
modulo e un numero secondo il loro rango. Tu le esamini, ne scegli una o metti un punto a mano.

Moduli disponibili:

- **Vicine nel tempo** — le foto scattate poco prima e poco dopo che hanno già una posizione. Il
  tragitto tra di esse è disegnato sulla mappa, colorato in base al tempo; le fotocamere con
  l'orologio sbagliato possono essere escluse, oppure si può tenere solo la fotocamera della
  foto.
- **GeoCLIP** *(worker facoltativo)* — geolocalizzazione delle immagini in tutto il mondo con una
  rete neurale, in locale sulla CPU del server o sulla GPU di un altro computer. Mostrato con la
  sua affidabilità, con un filtro della galleria per le stime affidabili. Può anche guardare solo
  una parte della foto: un edificio dietro la folla, un'insegna, una montagna all'orizzonte.
- **Foto simili** *(worker facoltativo)* — foto dello stesso luogo nella tua libreria, con una
  posizione: la stessa strada, casa, veduta o stanza, da un'altra angolazione o in un'altra
  stagione. Usa [MegaLoc](https://github.com/gmberton/MegaLoc), un modello fatto per riconoscere
  i luoghi; su una vera libreria di famiglia circa metà dei suoi suggerimenti sono giusti entro
  1 km, e più di otto su dieci di quelli affidabili. La ricerca tiene sempre conto delle
  posizioni che hai impostato nel frattempo.

Una foto può essere ruotata nell'app per vederla meglio; i moduli lavorano sulla foto ruotata, e
la rotazione può essere salvata in Immich.

Per controllare un luogo con i propri occhi, sotto la mappa si possono mostrare immagini
satellitari: Sentinel-2 di EOX (senza chiave), Esri World Imagery o MapTiler Satellite (con la
tua chiave). Sono tutte disattivate finché non ne attivi una.

In programma:

- **Panorami a livello della strada** sulla mappa, per controllare un luogo con i propri occhi.
- **Verifica geometrica** delle foto simili (corrispondenza dei dettagli, non solo dell'aspetto
  generale), e riconoscimento delle foto che non mostrano alcun luogo: primi piani, animali,
  piante, oggetti.
- **Ragionamento con un LLM** (sul modello di Img2Loc) — un modello visione-linguaggio ragiona
  sulla foto e sugli indizi raccolti dagli altri moduli.
- **Servizi esterni** — riconoscimento facoltativo nel cloud, un modulo per servizio.

In futuro si potranno aggiungere nuovi moduli come plugin.

## Screenshot

<table>
  <tr>
    <td width="50%"><img src="docs/images/geoclip-confident.png" alt="GeoCLIP suggerisce le Bocche di Cattaro con un'affidabilità del 78%, nel tema scuro"></td>
    <td width="50%"><img src="docs/images/geoclip-and-time-neighbors.png" alt="Suggerimenti di tre moduli sulla stessa mappa: una zona di GeoCLIP, una foto vicina nel tempo di un'altra fotocamera e foto simili"></td>
  </tr>
  <tr>
    <td>GeoCLIP riconosce il luogo dalla sola immagine: una stima affidabile per una fotocamera senza GPS (tema scuro).</td>
    <td>Più moduli insieme: la zona di GeoCLIP, una foto del telefono scattata due ore dopo e le foto simili concordano sulla città.</td>
  </tr>
  <tr>
    <td colspan="2"><img src="docs/images/gallery.png" alt="Galleria delle foto senza posizione, filtrata sulle stime affidabili di GeoCLIP, con i filtri a pillola e la linea del tempo"></td>
  </tr>
  <tr>
    <td colspan="2">La galleria: filtri a pillola, un badge su ogni foto con una posizione o una stima affidabile, la linea del tempo a destra.</td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/images/processing.png" alt="Pagina Elaborazione: numeri della libreria, worker e avanzamento di ogni modulo"></td>
    <td>Elaborazione: la libreria e la sua sincronizzazione, i worker e che cosa fanno, l'avanzamento e gli errori di ogni modulo, con una pausa per le esecuzioni in background.</td>
  </tr>
</table>

## Principi

- **Niente viene scritto in Immich automaticamente.** Le coordinate vengono inviate solo dopo che
  hai confermato una posizione. Ogni modifica si può annullare.
- **Prima il locale.** I moduli predefiniti girano sul tuo hardware. I moduli che inviano
  immagini a servizi di terze parti non vengono mai eseguiti automaticamente — solo su richiesta
  esplicita, con un avviso chiaro su che cosa viene inviato e dove.
- **Ricerca su una zona.** Se l'immagine intera trae in inganno (per esempio una folla davanti a
  un monumento), seleziona una parte dell'immagine ed esegui il riconoscimento solo su di essa.
- **Contrassegno «Posizione non pertinente».** Segna le foto per cui una posizione non ha senso,
  così non compariranno mai più nel tuo elenco da fare.

## Installazione

Steward gira con Docker Compose accanto al tuo server Immich (Immich v3.x):

```sh
mkdir immich-steward && cd immich-steward
curl -L -o compose.yaml https://github.com/Ivamic/immich-steward/releases/latest/download/compose.yaml
curl -L -o example.env https://github.com/Ivamic/immich-steward/releases/latest/download/example.env
cp example.env .env      # imposta STEWARD_IMMICH_URL, STEWARD_SECRET_KEY e DB_PASSWORD
docker compose up -d
```

Le immagini vengono scaricate da GitHub Container Registry (`ghcr.io/ivamic/immich-steward-core`,
`amd64` e `arm64`); si possono anche
[costruire dai sorgenti](docs/updating.md#building-the-images-from-source). Per aggiornare:
`docker compose pull && docker compose up -d`.

Poi apri `http://<il-tuo-server>:8780` e accedi con il tuo account Immich.

GeoCLIP e le foto simili girano in un container worker facoltativo (da 2 a 4 GB di RAM con
entrambi i modelli caricati): imposta `STEWARD_WORKER_TOKEN` in `.env` e avvia con
`docker compose --profile worker up -d`.
I worker possono girare anche su altri computer della tua rete
([come](docs/workers.md#a-worker-on-another-computer)).

La [documentazione](docs/README.md) (in inglese) spiega tutto passo per passo:
[installazione](docs/install.md), [uso dell'app](docs/usage.md), [worker](docs/workers.md),
[configurazione](docs/configuration.md), [aggiornamento](docs/updating.md),
[privacy](docs/privacy.md) e [risoluzione dei problemi](docs/troubleshooting.md).

## Segnalazioni e contributi

- **Bug** — apri una [issue](https://github.com/Ivamic/immich-steward/issues) con le versioni di
  Steward e di Immich e i passi per riprodurre il problema.
- **Idee e domande** — apri una discussione in
  [Discussions](https://github.com/Ivamic/immich-steward/discussions). Sono benvenuti anche i
  racconti di come usi l'app e delle foto su cui sbaglia.
- **Le pull request** sono benvenute. Per tutto ciò che va oltre una piccola correzione,
  parlane prima in una issue o in una discussione, così il tuo lavoro si accorda con i piani del
  progetto.
- **Problemi di sicurezza** — segnalali in privato, vedi [SECURITY.md](SECURITY.md).

Scrivi preferibilmente in inglese; se è difficile, va bene anche l'italiano.

## Sostieni il progetto

Steward è gratuito e sviluppato nel tempo libero. Se ti ha risparmiato ore di catalogazione a
mano, puoi sostenerne lo sviluppo con una donazione in criptovaluta. Anche una stella al
repository, le segnalazioni di bug e il passaparola aiutano.

| Valuta | Rete | Indirizzo |
|---|---|---|
| USDT | TRON (TRC-20) | `TAqGEvmDTw2ro4BKQmcPPtqK5xEMfNaiSX` |
| ETH, USDT e altri token | Ethereum e reti EVM (Base, Polygon, Arbitrum…) | `0x783C192d69fE5E9DAfa1dC2c41FeE272122AE031` |
| SOL | Solana | `38gidbL2ocv5c6CK7zP7c3QWVHisYyqhnrMV3tuaYpgp` |
| BTC | Bitcoin | `bc1qsdys5hvx7vlxp25mz77hfgz2l35x8klc8z2npx` |

Controlla bene la rete prima dell'invio: i fondi inviati su un'altra rete possono andare persi.

## Licenza

Copyright (C) 2026 Ivamic.

[GNU Affero General Public License v3.0 o successiva](LICENSE) (`AGPL-3.0-or-later`).

**Nome e logo.** Il nome «Steward for Immich» e il suo logo non sono concessi in licenza con
l'AGPL; tutti i diritti sono riservati all'autore, dettagli nel [README inglese](README.md#license).
Puoi usarli per fare riferimento a questo progetto. I fork e le versioni modificate devono usare
un altro nome e un altro logo.

## Assistenza dell'IA

Questo progetto è sviluppato con l'aiuto di strumenti di IA (Claude di Anthropic). Tutto il
codice è revisionato e mantenuto da un autore umano.

## Avvertenza

Questo è un progetto indipendente della comunità. Non è affiliato al progetto Immich o a FUTO,
né approvato da loro.
