<p align="center">
  <img src="docs/images/logo.svg" width="96" height="96" alt="Logo de Steward for Immich">
</p>

<h1 align="center">Steward for Immich</h1>

<p align="center">
  Remettez vos photos sans GPS sur la carte — plusieurs indices indépendants, une seule carte, à vous de choisir.
</p>

<p align="center">
  <a href="https://github.com/Ivamic/immich-steward/releases"><img src="https://img.shields.io/github/v/release/Ivamic/immich-steward?include_prereleases&sort=semver" alt="Version"></a>
  <a href="https://github.com/Ivamic/immich-steward/actions/workflows/ci.yml"><img src="https://github.com/Ivamic/immich-steward/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/Ivamic/immich-steward" alt="Licence : AGPL-3.0"></a>
  <img src="https://img.shields.io/badge/self--hosted-Docker%20Compose-2496ED?logo=docker&logoColor=white" alt="Auto-hébergé avec Docker Compose">
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.de.md">Deutsch</a> · <b>Français</b> · <a href="README.it.md">Italiano</a> · <a href="README.ru.md">Русский</a>
</p>

<p align="center">
  <img src="docs/images/time-neighbors-route.png" alt="Fiche photo : le trajet entre les photos prises juste avant et juste après, avec trois lieux proposés sur la carte et dans la liste">
</p>

> Ceci est une traduction, réalisée avec l'aide de l'IA, du [README anglais](README.md), qui fait
> foi. La documentation et la partie pour les développeurs ne sont pour l'instant qu'en anglais.
> Les corrections de la traduction sont les bienvenues.

> [!IMPORTANT]
> **Passer à la 0.6 depuis la 0.5 ou plus ancienne : une étape à la main, une seule fois.**
>
> **Pourquoi.** Jusqu'à la 0.5, `compose.yaml` indiquait la version exacte de l'application,
> donc chaque mise à jour demandait aussi `git pull`. À partir de la 0.6, `compose.yaml` suit la
> version majeure et lit tous les réglages dans `.env` : il ne change plus, et chaque mise à jour
> se résume à `docker compose pull` et `docker compose up -d`.
>
> **Comment.** Dans le dossier de l'application ; votre `.env` et vos données restent tels quels.
>
> Sans le worker :
>
> ```sh
> curl -L -o compose.yaml https://github.com/Ivamic/immich-steward/releases/latest/download/compose.yaml
> docker compose pull
> docker compose up -d
> ```
>
> Avec le worker sur le serveur :
>
> ```sh
> curl -L -o compose.yaml https://github.com/Ivamic/immich-steward/releases/latest/download/compose.yaml
> docker compose --profile worker pull
> docker compose --profile worker up -d
> ```
>
> Si `.env` contient une ligne `STEWARD_VERSION=…`, supprimez-la d'abord : elle garderait l'ancienne version. [Détails](docs/updating.md#coming-from-05-or-older) (en anglais).

> **Statut : en développement actif.** Une première version : la revue des photos sans lieu, les
> suggestions tirées des photos proches dans le temps, GeoCLIP et les photos similaires de votre
> propre photothèque fonctionnent déjà ; les autres modules sont encore à venir. Attendez-vous à
> des bugs et à des changements entre les versions, et faites une sauvegarde de votre photothèque
> Immich avant d'y écrire des lieux.

Une application compagnon auto-hébergée pour [Immich](https://immich.app). Pour chaque photo sans
lieu, plusieurs modules — les photos prises peu avant et peu après, le réseau neuronal GeoCLIP
et les photos similaires du même endroit dans votre propre photothèque — proposent où elle a
été prise, tous sur une seule carte. Vous choisissez d'un clic ou d'une touche, ou indiquez le
lieu de nombreuses photos d'un coup. Rien n'est écrit dans Immich avant que vous ne le fassiez,
et chaque modification peut être annulée.

Cas typique : des archives photo familiales avec des tirages numérisés, de vieux appareils
numériques sans GPS ou des photos reçues par messagerie qui ont perdu leurs métadonnées.

## Le principe

L'application réunit plusieurs **modules de localisation** indépendants. Chaque module propose un
ou plusieurs lieux possibles, et toutes les propositions sont affichées ensemble sur une carte,
avec une couleur par module et un numéro selon leur rang. Vous les examinez, en choisissez une
ou placez un point à la main.

Modules disponibles :

- **Voisines dans le temps** — les photos prises juste avant et juste après qui ont déjà un lieu.
  Le trajet entre elles est tracé sur la carte, coloré selon le temps ; les appareils dont
  l'horloge est fausse peuvent être exclus, ou seul l'appareil de la photo gardé.
- **GeoCLIP** *(worker facultatif)* — géolocalisation d'images dans le monde entier par un réseau
  de neurones, en local sur le processeur du serveur ou sur la carte graphique d'un autre
  ordinateur. Affiché avec un niveau de confiance, avec un filtre de galerie pour ses estimations
  sûres. Il peut aussi n'examiner qu'une partie de la photo : un bâtiment derrière une foule, une
  enseigne, une montagne à l'horizon.
- **Photos similaires** *(worker facultatif)* — des photos du même endroit dans votre propre
  photothèque, avec un lieu : la même rue, la même maison, la même vue ou la même pièce, sous un
  autre angle ou à une autre saison. Utilise [MegaLoc](https://github.com/gmberton/MegaLoc), un
  modèle conçu pour reconnaître les lieux ; sur une vraie photothèque familiale, environ la
  moitié de ses suggestions sont justes à 1 km près, et plus de huit sur dix de ses suggestions
  sûres. La recherche tient toujours compte des lieux que vous avez définis entre-temps.

Une photo peut être pivotée dans l'application pour mieux la voir ; les modules travaillent sur
la photo pivotée, et la rotation peut être enregistrée dans Immich.

Pour vérifier un lieu de ses propres yeux, des images satellite peuvent être affichées sous la
carte : Sentinel-2 d'EOX (sans clé), Esri World Imagery ou MapTiler Satellite (avec votre propre
clé). Toutes sont désactivées tant que vous n'en activez pas une.

Prévu :

- **Panoramas au niveau de la rue** sur la carte, pour vérifier un lieu de ses propres yeux.
- **Vérification géométrique** des photos similaires (concordance des détails, pas seulement de
  l'aspect général), et reconnaissance des photos qui ne montrent aucun lieu : portraits en gros
  plan, animaux, plantes, objets.
- **Raisonnement par LLM** (dans l'esprit d'Img2Loc) — un modèle vision-langage raisonne sur la
  photo et sur les indices rassemblés par les autres modules.
- **Services externes** — des services de reconnaissance en ligne facultatifs, un module par
  service.

De nouveaux modules pourront être ajoutés plus tard sous forme d'extensions.

## Captures d'écran

<table>
  <tr>
    <td width="50%"><img src="docs/images/geoclip-confident.png" alt="GeoCLIP propose les bouches de Kotor avec 78 % de confiance, en thème sombre"></td>
    <td width="50%"><img src="docs/images/geoclip-and-time-neighbors.png" alt="Suggestions de trois modules sur une même carte : une zone GeoCLIP, une voisine dans le temps prise par un autre appareil et des photos similaires"></td>
  </tr>
  <tr>
    <td>GeoCLIP reconnaît le lieu à partir de l'image seule : une estimation sûre pour un appareil sans GPS (thème sombre).</td>
    <td>Plusieurs modules à la fois : la zone GeoCLIP, une photo de téléphone prise deux heures plus tard et des photos similaires s'accordent sur la ville.</td>
  </tr>
  <tr>
    <td colspan="2"><img src="docs/images/gallery.png" alt="Galerie des photos sans lieu, filtrée sur les estimations GeoCLIP sûres, avec les filtres en pastilles et la frise"></td>
  </tr>
  <tr>
    <td colspan="2">La galerie : des filtres en pastilles, un badge sur chaque photo qui a un lieu ou une estimation sûre, la frise chronologique à droite.</td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/images/processing.png" alt="Page Traitement : chiffres de la photothèque, workers et avancement de chaque module"></td>
    <td>Traitement : la photothèque et sa synchronisation, les workers et ce qu'ils font, l'avancement et les échecs de chaque module, avec une pause pour les traitements en arrière-plan.</td>
  </tr>
</table>

## Principes

- **Rien n'est écrit automatiquement dans Immich.** Les coordonnées ne sont envoyées qu'après
  que vous avez confirmé un lieu. Toute modification peut être annulée.
- **Le local d'abord.** Les modules par défaut fonctionnent sur votre propre matériel. Les modules
  qui envoient des images à des services tiers ne sont jamais lancés automatiquement — seulement
  sur demande explicite, avec un avertissement clair sur ce qui est envoyé et où.
- **Recherche sur une zone.** Si l'image entière est trompeuse (par exemple une foule devant un
  monument), sélectionnez une partie de l'image et lancez la détection sur cette zone seulement.
- **Marque « Lieu sans objet ».** Marquez les photos pour lesquelles un lieu n'a pas de sens, afin
  qu'elles ne réapparaissent plus jamais dans votre liste à traiter.

## Installation

Steward fonctionne avec Docker Compose à côté de votre serveur Immich (Immich v3.x) :

```sh
mkdir immich-steward && cd immich-steward
curl -L -o compose.yaml https://github.com/Ivamic/immich-steward/releases/latest/download/compose.yaml
curl -L -o example.env https://github.com/Ivamic/immich-steward/releases/latest/download/example.env
cp example.env .env      # définir STEWARD_IMMICH_URL, STEWARD_SECRET_KEY et DB_PASSWORD
docker compose up -d
```

Les images sont téléchargées depuis GitHub Container Registry
(`ghcr.io/ivamic/immich-steward-core`, `amd64` et `arm64`) ; on peut aussi les
[construire à partir des sources](docs/updating.md#building-the-images-from-source). Mettre à
jour : `docker compose pull && docker compose up -d`.

Ouvrez ensuite `http://<votre-serveur>:8780` et connectez-vous avec votre compte Immich.

GeoCLIP et les photos similaires tournent dans un conteneur worker facultatif (2 à 4 Go de RAM
avec les deux modèles chargés) : définissez `STEWARD_WORKER_TOKEN` dans `.env` et lancez
`docker compose --profile worker up -d`.
Les workers peuvent aussi tourner sur d'autres ordinateurs de votre réseau
([comment](docs/workers.md#a-worker-on-another-computer)).

La [documentation](docs/README.md) (en anglais) explique tout pas à pas :
[installation](docs/install.md), [utilisation](docs/usage.md), [workers](docs/workers.md),
[configuration](docs/configuration.md), [mise à jour](docs/updating.md),
[confidentialité](docs/privacy.md) et [dépannage](docs/troubleshooting.md).

## Retours et contributions

- **Bugs** — ouvrez une [issue](https://github.com/Ivamic/immich-steward/issues) en indiquant les
  versions de Steward et d'Immich et les étapes pour reproduire le problème.
- **Idées et questions** — lancez une discussion dans
  [Discussions](https://github.com/Ivamic/immich-steward/discussions). Les récits sur votre façon
  d'utiliser l'application et sur les photos où elle échoue sont aussi les bienvenus.
- **Les pull requests** sont les bienvenues. Pour tout ce qui dépasse une petite correction,
  parlez-en d'abord dans une issue ou une discussion, afin que votre travail s'inscrive dans les
  projets du dépôt.
- **Problèmes de sécurité** — merci de les signaler en privé, voir [SECURITY.md](SECURITY.md).

Écrivez de préférence en anglais ; si c'est difficile, le français convient aussi.

## Soutenir le projet

Steward est gratuit et développé sur le temps libre. S'il vous a épargné des heures de
classement à la main, vous pouvez soutenir son développement par un don en cryptomonnaie. Une
étoile sur le dépôt, des rapports de bugs et parler du projet autour de vous aident aussi.

| Monnaie | Réseau | Adresse |
|---|---|---|
| USDT | TRON (TRC-20) | `TAqGEvmDTw2ro4BKQmcPPtqK5xEMfNaiSX` |
| ETH, USDT et autres jetons | Ethereum et réseaux EVM (Base, Polygon, Arbitrum…) | `0x783C192d69fE5E9DAfa1dC2c41FeE272122AE031` |
| SOL | Solana | `38gidbL2ocv5c6CK7zP7c3QWVHisYyqhnrMV3tuaYpgp` |
| BTC | Bitcoin | `bc1qsdys5hvx7vlxp25mz77hfgz2l35x8klc8z2npx` |

Vérifiez bien le réseau avant l'envoi : des fonds envoyés sur un autre réseau peuvent être
perdus.

## Licence

Copyright (C) 2026 Ivamic.

[GNU Affero General Public License v3.0 ou ultérieure](LICENSE) (`AGPL-3.0-or-later`).

**Nom et logo.** Le nom « Steward for Immich » et son logo ne sont pas placés sous l'AGPL ; tous
les droits sont réservés à l'auteur, détails dans le [README anglais](README.md#license). Vous
pouvez les utiliser pour faire référence à ce projet. Les forks et les versions modifiées doivent
utiliser un autre nom et un autre logo.

## Assistance de l'IA

Ce projet est développé avec l'aide d'outils d'IA (Claude d'Anthropic). Tout le code est relu et
maintenu par un auteur humain.

## Avertissement

Ceci est un projet communautaire indépendant. Il n'est ni affilié au projet Immich ou à FUTO, ni
approuvé par eux.
