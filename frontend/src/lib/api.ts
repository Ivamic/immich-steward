// SPDX-License-Identifier: AGPL-3.0-or-later
// Typed client for the core API. Mirrors the Pydantic models in core/src/steward/api.

/** Error returned by the core: a machine-readable code plus parameters for the message. */
export class ApiError extends Error {
	constructor(
		readonly status: number,
		readonly code: string,
		readonly params: Record<string, unknown> = {}
	) {
		super(code);
	}
}

let onSignedOut: (() => void) | null = null;

/** What to do when the core says the session is over (expired, or signed out elsewhere). */
export function whenSignedOut(handler: () => void) {
	onSignedOut = handler;
}

async function request<T>(
	method: string,
	path: string,
	body?: unknown,
	// Lets the request outlive the page (used when the tab is closed during a pending save).
	keepalive = false
): Promise<T> {
	let response: Response;
	try {
		response = await fetch(path, {
			method,
			headers: body === undefined ? {} : { 'content-type': 'application/json' },
			body: body === undefined ? undefined : JSON.stringify(body),
			keepalive
		});
	} catch {
		throw new ApiError(0, 'core_unreachable');
	}
	if (response.status === 204) return undefined as T;
	const data = await response.json().catch(() => null);
	if (!response.ok) {
		if (response.status === 401 && data?.code === 'not_authenticated') onSignedOut?.();
		throw new ApiError(response.status, data?.code ?? 'unexpected_error', data?.params ?? {});
	}
	return data as T;
}

export interface DatabaseHealth {
	ok: boolean;
	server_version: string | null;
	pgvector_version: string | null;
	/** Machine-readable error code; translated by the UI. */
	error: string | null;
}

export interface ImmichHealth {
	configured: boolean;
	reachable: boolean;
	version: string | null;
	supported: boolean | null;
}

export interface Health {
	status: 'ok' | 'degraded';
	version: string;
	database: DatabaseHealth;
	immich: ImmichHealth;
}

export interface Me {
	id: string;
	name: string;
	email: string;
}

export interface Job {
	id: string;
	kind: string;
	status: 'queued' | 'running' | 'done' | 'failed';
	progress: Record<string, unknown>;
	/** Error code, translated by the UI. */
	error: string | null;
	created_at: string;
	started_at: string | null;
	finished_at: string | null;
}

export interface Library {
	assets: number;
	videos: number;
	with_gps: number;
	without_gps: number;
	albums: number;
	synced_at: string | null;
	full_synced_at: string | null;
	/** When the automatic syncs are due (checked once a minute); null: they are off. */
	next_sync_at: string | null;
	next_full_sync_at: string | null;
	sync_job: Job | null;
	/** The badge "similar with a location": its last full pass, and the latest pass. */
	similar_hints_at: string | null;
	similar_hints_job: Job | null;
}

export const isActive = (job: Job | null) =>
	job !== null && (job.status === 'queued' || job.status === 'running');

/** Disjoint groups of photos; the gallery shows any combination of them. */
export type ShowCategory = 'todo' | 'with' | 'skipped' | 'not_applicable';
export const SHOW_CATEGORIES: readonly ShowCategory[] = [
	'todo',
	'with',
	'skipped',
	'not_applicable'
];
export type ReviewStatus = 'new' | 'skipped' | 'not_applicable';

/** A category of photos in the filter: left out, shown with the timeline, or shown alone. "only"
 * on the archive or the locked folder hides the timeline; each that is not off adds its photos. */
export type Inclusion = 'off' | 'with' | 'only';

/** In the address: "true" for "with", as older links say. */
export const inclusionParam = (value: Inclusion): string | null =>
	value === 'off' ? null : value === 'with' ? 'true' : 'only';

export const inclusionOf = (value: string | null): Inclusion =>
	value === 'true' || value === 'with' ? 'with' : value === 'only' ? 'only' : 'off';

export interface GalleryFilter {
	/** Groups to show; empty means all of them. */
	show: ShowCategory[];
	type: 'all' | 'image' | 'video';
	camera: string | null;
	album: string | null;
	date_from: string | null;
	date_to: string | null;
	/** The archive: left out, with the timeline, or alone (without the timeline). */
	archived: Inclusion;
	/** The Immich locked folder (while it is open), the same way. */
	locked_folder: Inclusion;
	/** Only photos without a location that GeoCLIP places confidently. */
	geoclip_confident: boolean;
	/** Only photos without a location with a confidently similar located one. */
	similar_confident: boolean;
	/** Only photos without a location that share enough details with a located one. */
	details_confirmed: boolean;
	/** Only photos without a location with a located one taken close in time. */
	nearby: boolean;
	/** Only photos whose latest run of this module failed... */
	failed_module: string | null;
	/** ...for this reason (a failure code); null: any reason. */
	failure: string | null;
	/** How the gallery lists the photos: the newest or the oldest first (D-233). */
	order: GalleryOrder;
}

export type GalleryOrder = 'newest' | 'oldest';

export interface MonthBucket {
	month: string; // YYYY-MM
	count: number;
	/** Photos of each day of the month that has any, in the gallery order (cores before 0.7.0:
	 * none). */
	days?: number[];
}

export interface AssetItem {
	id: string;
	local_taken_at: string;
	type: 'IMAGE' | 'VIDEO' | string;
	file_name: string;
	has_location: boolean;
	/** No location yet, but GeoCLIP places the photo confidently. */
	geoclip_confident: boolean;
	/** No location yet, but a photo with one is confidently similar. */
	similar_confident: boolean;
	/** No location yet, but a photo with one shares enough details with it. */
	details_confirmed?: boolean;
	/** No location yet, but a photo taken close in time has one: by the same camera or another. */
	nearby: NearbyLevel | null;
	width: number | null;
	height: number | null;
	camera_make: string | null;
	camera_model: string | null;
	/** Changes with the thumbnails (photo rotated or edited in Immich). */
	version: string | null;
	/** In the Immich locked folder (shown only while it is open; absent: older core). */
	locked?: boolean;
}

export type NearbyLevel = 'same_camera' | 'other_camera';

export interface FilterOptions {
	cameras: { value: string; make: string; model: string; count: number }[];
	albums: { id: string; name: string; count: number }[];
	/** Modules whose failed runs the gallery can show (also ANY_MODULE). */
	failed_modules: string[];
	/** How close in time a located photo makes another one "nearby". */
	nearby_minutes: number;
}

/** `failed_module` of the gallery filter: the latest run of any module failed. */
export const ANY_MODULE = 'any';

/** Query string for the gallery filter; default values are left out. */
export function filterQuery(filter: GalleryFilter, extra: Record<string, string> = {}): string {
	const params = new URLSearchParams(extra);
	for (const category of filter.show) params.append('show', category);
	if (filter.type !== 'all') params.set('type', filter.type);
	if (filter.camera !== null) params.set('camera', filter.camera);
	if (filter.album) params.set('album', filter.album);
	if (filter.date_from) params.set('date_from', filter.date_from);
	if (filter.date_to) params.set('date_to', filter.date_to);
	for (const key of ['archived', 'locked_folder'] as const) {
		const value = inclusionParam(filter[key]);
		if (value) params.set(key, value);
	}
	if (filter.geoclip_confident) params.set('geoclip_confident', 'true');
	if (filter.similar_confident) params.set('similar_confident', 'true');
	if (filter.details_confirmed) params.set('details_confirmed', 'true');
	if (filter.nearby) params.set('nearby', 'true');
	if (filter.failed_module) {
		params.set('failed_module', filter.failed_module);
		if (filter.failure) params.set('failure', filter.failure);
	}
	if (filter.order === 'oldest') params.set('order', 'oldest');
	const query = params.toString();
	return query ? `?${query}` : '';
}

/** Clockwise, in degrees: how the user turned the photo in the app (Immich is not changed). */
export type Turn = 0 | 90 | 180 | 270;

/** The address changes with the thumbnails (`version`), so that the browser never keeps old ones. */
export const thumbnailUrl = (
	id: string,
	size: 'thumbnail' | 'preview' | 'fullsize' = 'thumbnail',
	turn: Turn = 0,
	version: string | null = null
) =>
	`/api/assets/${id}/thumbnail?size=${size}${turn ? `&turn=${turn}` : ''}` +
	(version ? `&v=${encodeURIComponent(version)}` : '');

/** The video as Immich plays it, through the app; the browser seeks with byte ranges. */
export const videoUrl = (id: string) => `/api/assets/${id}/video`;

export const getMonths = (filter: GalleryFilter) =>
	request<MonthBucket[]>('GET', `/api/assets/months${filterQuery(filter)}`);
export const getMonthAssets = (month: string, filter: GalleryFilter) =>
	request<AssetItem[]>('GET', `/api/assets${filterQuery(filter, { month })}`);
export const getFilterOptions = () => request<FilterOptions>('GET', '/api/assets/filter-options');

export interface LocationChange {
	id: string;
	created_at: string;
	latitude: number;
	longitude: number;
	prev_latitude: number | null;
	prev_longitude: number | null;
	/** "manual" or the id of a location module. */
	source: string;
	status: 'applied' | 'undone';
}

/** Which way the camera looked (D-245), kept in the app: degrees clockwise from true north,
 * give or take `accuracy`. */
export interface Direction {
	heading: number;
	accuracy: number;
	/** street: a street-level image the point was put on; street_match: matched with one. */
	source: string;
	/** The image, "mapillary:123". */
	source_ref: string | null;
}

export interface AssetDetail {
	/** Which way the camera looked, if known. Absent: an older core. */
	direction?: Direction | null;
	id: string;
	type: string;
	file_name: string;
	local_taken_at: string;
	taken_at: string | null;
	time_zone: string | null;
	camera_make: string | null;
	camera_model: string | null;
	lens_model: string | null;
	width: number | null;
	height: number | null;
	latitude: number | null;
	longitude: number | null;
	city: string | null;
	state: string | null;
	country: string | null;
	review_status: ReviewStatus;
	/** The albums the photo is in; `can_change_photos`: it can be taken out of it here. */
	albums: { id: string; name: string; can_change_photos: boolean }[];
	/** Newest first. */
	location_history: LocationChange[];
	/** The last write replaced earlier coordinates, so it can be undone. */
	can_undo: boolean;
	previous_id: string | null;
	next_id: string | null;
	/** The photo in the Immich web UI. */
	immich_url: string | null;
	/** Changes with the thumbnails (photo rotated or edited in Immich). */
	version: string | null;
	/** In the Immich locked folder (absent: older core). */
	locked?: boolean;
}

export interface MapConfig {
	style_url: string;
	/** For the dark theme; null (or absent, older core): `style_url`, dimmed. */
	style_url_dark?: string | null;
	geocoder_enabled: boolean;
	/** Satellite imagery sources (absent: older core). */
	sources?: MapSourceConfig[];
	auto?: MapAuto;
}

/** What the provider thinks of the key: refused, or the access closed (the limit, most likely). */
export type MapKeyProblem = 'invalid' | 'exhausted';
export type MapSourceStatus = 'ok' | 'no_key' | MapKeyProblem;

export interface MapVariant {
	/** A year of EOX; "default" for the others. */
	id: string;
	/** With the account's key; null while the source is off. */
	tiles: string | null;
	/** HTML; `{copyright}` stands for the provider's copyright text. */
	attribution: string;
}

export interface MapSourceConfig {
	id: string;
	name: string;
	enabled: boolean;
	status: MapSourceStatus;
	/** The first is the default. */
	variants: MapVariant[];
	tile_size: number;
	max_zoom: number;
	logo_url: string | null;
	copyright: string | null;
	/** JSON with `copyrightText`, read by the browser (Esri). */
	copyright_url: string | null;
}

/** Sources the map takes far out and close up when switching by itself; null: the plain map. */
export interface MapAuto {
	far: string | null;
	near: string | null;
	switch_zoom: number;
}

export interface ProviderUsage {
	used: number | null;
	/** The provider's estimate for the whole period. */
	estimated: number | null;
	since: string | null;
	until: string | null;
	fetched_at: string;
	error: 'token_invalid' | 'unreachable' | null;
}

/** A source in the settings; keys come only masked. */
export interface MapSourceItem {
	id: string;
	name: string;
	needs_key: boolean;
	enabled: boolean;
	status: MapSourceStatus;
	key: string | null;
	key_problem_at: string | null;
	usage_token_supported: boolean;
	usage_token: string | null;
	provider_usage: ProviderUsage | null;
	/** Tiles loaded by this account since `counted_since` (the own count). */
	tiles: number;
	counted_since: string;
	reset_day: number | null;
	/** Free tiles a month today. */
	free_quota: number | null;
	/** The next change of the free plan, when one is known; absent from older cores. */
	free_quota_next?: { starts: string; quota: number } | null;
	noncommercial: boolean;
	years: number[];
	terms_url: string;
	site_url: string;
	key_url: string | null;
	/** The provider's page with its own count of the usage and the limits. */
	usage_url: string | null;
	/** After a save or a check: "unreachable" when the provider could not be asked. */
	key_check: 'unreachable' | null;
}

export interface MapSourceUpdate {
	enabled?: boolean;
	/** Empty or null deletes the key. */
	api_key?: string | null;
	usage_token?: string | null;
	reset_day?: number | null;
}

export const getMapSources = () =>
	request<{ sources: MapSourceItem[]; auto: MapAuto }>('GET', '/api/map-sources');
export const updateMapSource = (id: string, update: MapSourceUpdate) =>
	request<MapSourceItem>('PUT', `/api/map-sources/${id}`, update);
export const checkMapKey = (id: string) =>
	request<MapSourceItem>('POST', `/api/map-sources/${id}/check`);
export const resetMapCount = (id: string) =>
	request<MapSourceItem>('POST', `/api/map-sources/${id}/reset-count`);
export const refreshMapUsage = (id: string) =>
	request<MapSourceItem>('POST', `/api/map-sources/${id}/refresh-usage`);
export const setMapAuto = (auto: MapAuto) => request<MapAuto>('PUT', '/api/map-sources/auto', auto);
export const reportMapTiles = (
	tiles: Record<string, number>,
	problems: Record<string, MapKeyProblem>,
	keepalive = false
) => request<void>('POST', '/api/map-sources/report', { tiles, problems }, keepalive);

export interface Place {
	name: string;
	label: string;
	latitude: number;
	longitude: number;
	kind: string | null;
}

export interface NeighborEvidence {
	asset_id: string;
	file_name: string;
	/** Seconds from the photo; negative means before it. */
	delta_s: number;
	/** Time neighbors only. */
	same_camera?: boolean;
	/** The neighbor's location was written by this app, not recorded by a camera. */
	estimated: boolean;
	/** Changes with the neighbor's thumbnails (absent in results stored by older versions). */
	version?: string | null;
	/** A photo of the locked folder while it is closed: no name, a lock instead of its preview. */
	locked?: boolean;
	/** Similar photos only: 0..1, and when the photo was taken (local time). */
	similarity?: number;
	/** Similar photos only: the details the photo shares with this one (`details` module);
	 * null when the two were not compared. */
	details?: number | null;
	/** Suggestions for several chosen photos: the chosen photo it is a neighbor of. */
	photo_id?: string;
	local_taken_at?: string;
}

export interface Candidate {
	/** 1-based rank within the module. */
	rank: number;
	latitude: number;
	longitude: number;
	/** 0..1, comparable only within one module. */
	score: number;
	radius_m: number | null;
	kind: string;
	evidence: {
		neighbors?: NeighborEvidence[];
		share?: number;
		/** Similar photos (M3): how far apart the most similar photos lie, km (D-200). */
		spread_km?: number | null;
		spread?: 'point' | 'apart' | 'wide' | null;
		/** Similar photos: the photo shares enough details with the first neighbor (D-225). */
		confirmed?: boolean;
	} & Record<string, unknown>;
	/** weak: shown folded ("probably only the region is right"); confident: marked as such. */
	tier: 'weak' | 'normal' | 'confident';
}

export interface TrackPoint extends NeighborEvidence {
	latitude: number;
	longitude: number;
	local_taken_at: string;
	/** Camera as shown to the user ("" when unknown). */
	camera: string;
	role: 'before' | 'after' | null;
}

export interface CameraCount {
	/** Camera filter value (make + separator + model). */
	value: string;
	label: string;
	count: number;
	same_camera: boolean;
	excluded: boolean;
}

export interface ModuleSuggestions {
	module: string;
	version: string;
	color: string;
	shape: string;
	candidates: Candidate[];
	track: TrackPoint[];
	/** Cameras of the photos the module looked at; the user may exclude some. */
	cameras: CameraCount[];
	/** Why there are no candidates (e.g. "scanner"). */
	note: string | null;
	/** ready: computed now (core modules); the others describe the latest run of a worker module. */
	status: ModuleStatus;
	/** Run by workers: can be started (again) from the card. */
	runnable: boolean;
	/** A worker running this module has contacted the core recently. */
	worker_available: boolean;
	error: string | null;
	/** Why the latest run failed (see FAILURE_CODES). */
	error_code: string | null;
	finished_at: string | null;
	/** Queued runs: jobs of the module a worker takes before this one. */
	queue_position: number | null;
	/** Background runs of the module are paused; a run started from the card still goes. */
	paused: boolean;
	/** A worker of the module is downloading or loading its model: the next run takes longer. */
	worker_loading: boolean;
	/** Tells the blocks apart: the module id, or "<module>:region" for its run on a part. */
	key: string;
	/** The part of the photo of a run on a part (FR-35). */
	region: Region | null;
	/** The run was on the photo turned this way. */
	turn: Turn;
	/** The account hides the module in the card (Settings page); the module still runs. */
	hidden: boolean;
	/** Similar photos, on the whole photo: the comparison of details that confirms its
	 * suggestions. */
	details?: {
		status: 'not_run' | 'queued' | 'running' | 'done' | 'failed';
		worker_available: boolean;
		/** Queued: comparisons a worker takes before this one. */
		queue_position?: number | null;
		/** Queued by hand: ahead of the comparisons the app queued itself. */
		urgent?: boolean;
	} | null;
}

/** A module in the order of the photo card, and whether it is shown there. */
export interface ModuleDisplay {
	module: string;
	hidden: boolean;
}

export const getModuleDisplay = () =>
	request<ModuleDisplay[]>('GET', '/api/library/module-display');
export const setModuleDisplay = (displays: ModuleDisplay[]) =>
	request<ModuleDisplay[]>('PUT', '/api/library/module-display', displays);

/** A part of the photo as shares of its width and height (of the photo as shown). */
export interface Region {
	x: number;
	y: number;
	w: number;
	h: number;
}

export type ModuleStatus = 'ready' | 'not_run' | 'queued' | 'running' | 'done' | 'failed';

export const isPending = (module: ModuleSuggestions) =>
	module.status === 'queued' || module.status === 'running';

/** The photo is being compared with its similar photos point by point, or waits for it. */
export const isComparing = (module: ModuleSuggestions) =>
	module.details?.status === 'queued' || module.details?.status === 'running';

/** How two photos match point by point (`details` module). */
export interface DetailPair {
	matches: number;
	inliers: number;
	/** x, y in the photo and x, y in the other one, 0..1 of the sides of the previews. */
	lines: [number, number, number, number][];
}

export const getDetailPair = (assetId: string, otherId: string) =>
	request<DetailPair>('GET', `/api/assets/${assetId}/details/${otherId}`);

export interface WorkerInfo {
	id: string;
	name: string;
	device: string;
	modules: string[];
	/** Of `modules`, those turned off for it: it gets no jobs of them. */
	disabled_modules: string[];
	version: string;
	last_seen_at: string;
	active: boolean;
	/** What it says it is doing, while connected; null for older workers. */
	state: WorkerState | null;
	state_module: string | null;
	state_since: string | null;
	/** When it gets background jobs: 7 days (Monday first) of 24 hour bits; null: always.
	 * Absent: an older core. */
	schedule?: number[] | null;
	/** The schedule lets it take background jobs now; and when that changes next. */
	in_hours?: boolean;
	hours_change_at?: string | null;
}

/** The clock schedules go by: the time zone of the server (`TZ`). */
export interface ServerClock {
	/** IANA name; null when `TZ` is not set (then usually UTC). */
	zone: string | null;
	utc_offset_min: number;
}

export type WorkerState = 'idle' | 'busy' | 'downloading' | 'loading' | 'working';

/** A worker the core did not take because one side is too old for the other. */
export interface RefusedWorker {
	name: string;
	version: string;
	reason: 'worker_too_old' | 'core_too_old';
	at: string;
}

export interface WorkersOverview {
	workers: WorkerInfo[];
	/** Workers refused lately: update the worker, or the app on the server. */
	refused: RefusedWorker[];
	/** Version of the app: the one to install when a worker is offered an update. */
	core_version: string;
	/** A worker older than this is offered an update (not every release changes the worker). */
	worker_recommended: string;
	/** Queued jobs of locked photos: they wait until the folder is opened (absent: older core). */
	locked_waiting?: number;
	/** Every module workers can run, in the order to show them. */
	modules: { id: string; color: string; shape: string }[];
	/** Module -> status of the latest run -> number of photos. */
	runs: Record<string, Partial<Record<ModuleStatus, number>>>;
	/** Module -> failure code -> photos whose latest run failed so. */
	failures: Record<string, Record<string, number>>;
	auto_modules: string[];
	/** Indexing module -> photos with a location in its search index, of those it indexes. */
	index: Record<string, { indexed: number; located: number }>;
	pause: Pause;
	/** Absent: an older core. */
	clock?: ServerClock | null;
}

/** Paused background runs, for the whole installation: of every module, or of these. */
export interface Pause {
	all: boolean;
	modules: string[];
	/** When the pause of all modules ends by itself; null: until resumed. */
	all_until: string | null;
	/** Module -> when its pause ends by itself (absent: until resumed). */
	until: Record<string, string>;
}

/** Whether a newer release of the app is out; the check is for the whole installation. */
export interface Updates {
	enabled: boolean;
	current: string;
	latest: string | null;
	newer: boolean;
	/** Release notes of the latest release. */
	url: string | null;
	checked_at: string | null;
	/** Why the last check failed: "unreachable", "http_<status>" or "bad_answer". */
	error: string | null;
}

export const getUpdates = () => request<Updates>('GET', '/api/updates');
/** Turns the automatic check on (it checks at once, if due) or off. */
export const setUpdates = (enabled: boolean) =>
	request<Updates>('PUT', '/api/updates', { enabled });
/** Checks now, also while the automatic check is off. */
export const checkUpdates = () => request<Updates>('POST', '/api/updates/check');

/**
 * Where the photos with a location are: latitude, longitude and number of photos per cell, of
 * about 100 m (`coarse`) or 11 m (`fine`, for a close look).
 */
/** The page "Map" (D-207): photos with a location gathered into cells of the zoom. */
export interface MapCellsAnswer {
	cells: {
		latitude: number;
		longitude: number;
		photos: number;
		bounds: { south: number; west: number; north: number; east: number };
		asset_id: string | null;
		cover_id: string;
		cover_version: string | null;
	}[];
	photos: number;
}
type Bounds = { south: number; west: number; north: number; east: number };
const boundsQuery = (b: Bounds) => ({
	south: String(b.south),
	west: String(b.west),
	north: String(b.north),
	east: String(b.east)
});
export const getMapCells = (bounds: Bounds, zoom: number, filter: GalleryFilter) =>
	request<MapCellsAnswer>(
		'GET',
		`/api/assets/map/cells${filterQuery(filter, { ...boundsQuery(bounds), zoom: String(zoom) })}`
	);
/** The photos of a place of the map (a cell), newest first. */
export const getMapPhotos = (
	bounds: Bounds,
	offset: number,
	limit: number,
	filter: GalleryFilter
) =>
	request<{ total: number; photos: AssetItem[] }>(
		'GET',
		`/api/assets/map/photos${filterQuery(filter, {
			...boundsQuery(bounds),
			offset: String(offset),
			limit: String(limit)
		})}`
	);
export const getHeatmap = (level: 'coarse' | 'fine') =>
	request<number[]>('GET', `/api/assets/heatmap?level=${level}`);

/** Personal settings of the signed-in account. */
export interface AccountSettings {
	/** Its own tooltip over a gallery tile (name, time taken, camera, size). */
	gallery_tooltip: boolean;
	/** A video shown large on a long press plays with its sound. */
	video_sound: boolean;
	/** Groups of photos: photos at least this similar are close. */
	groups_similarity: number;
	/** Groups of photos: close photos a photo needs to link groups. */
	groups_core_neighbors: number;
	/** Groups of photos: close only when each photo keeps the other among its neighbors. */
	groups_mutual: boolean;
	/** The app marks a photo with "no sign of a place" when so many photos the user marked are
	 * among its neighbors, at least so alike (D-200). */
	trash_auto: boolean;
	trash_auto_marks: number;
	trash_auto_similarity: number;
	/** Matching details (D-225): shared details that confirm a suggestion of similar photos. */
	details_confirmed_from: number;
	/** A confirmed suggestion goes before the others. */
	details_first: boolean;
	/** Photos a photo is compared with: by itself, and when started by hand. */
	details_candidates_auto: number;
	details_candidates_manual: number;
	/** Street-level images near the point in the photo card (D-244). */
	street_shown: boolean;
}

export const DETAILS_MODULE = 'details';

export const getAccountSettings = () => request<AccountSettings>('GET', '/api/settings');
/** Only the settings given change. */
export const setAccountSettings = (change: Partial<AccountSettings>) =>
	request<AccountSettings>('PUT', '/api/settings', change);

export const getWorkers = () => request<WorkersOverview>('GET', '/api/library/workers');
/** Removes a worker that is not connected from the list. */
export const forgetWorker = (id: string) => request<void>('DELETE', `/api/library/workers/${id}`);
/** What the commands of "Add a device" need; the token only for an administrator of Immich. */
export interface WorkerSetup {
	admin: boolean;
	token: string | null;
	/** A worker token is set on the server (without one, workers are refused). */
	token_set: boolean;
	version: string;
}

export const getWorkerSetup = () => request<WorkerSetup>('GET', '/api/library/worker-setup');

/** Turns a module of a worker on or off; off, it gets no jobs of it. */
export const switchWorkerModule = (id: string, module: string, enabled: boolean) =>
	request<void>('PUT', `/api/library/workers/${id}/modules`, { module, enabled });
/** The hours a worker gets background jobs (`schedule.ts`); every hour on is kept as "always". */
export const setWorkerSchedule = (id: string, schedule: number[]) =>
	request<void>('PUT', `/api/library/workers/${id}/schedule`, { schedule });

export const getPause = () => request<Pause>('GET', '/api/library/pause');
/** Pauses (for `minutes`, or until resumed) or resumes a module; `null`: all modules. */
export const setPause = (module: string | null, paused: boolean, minutes: number | null = null) =>
	request<Pause>('PUT', '/api/library/pause', { module, paused, minutes });
/** Resumes every module, paused one by one or all together. */
export const resumeAll = () => request<Pause>('DELETE', '/api/library/pause');

/** Runs the module again on the photos whose latest run failed (for this reason). */
export const rerunFailed = (module: string, code: string | null) =>
	request<{ queued: number }>('POST', `/api/library/modules/${module}/rerun-failed`, { code });

/** A location saved a moment ago and not sent yet (it can still be cancelled). */
export interface PendingPoint {
	assetId: string;
	point: { lat: number; lon: number };
}

function cameraQuery(
	excludeCameras: string[],
	sameCameraOnly = false,
	pending: PendingPoint[] = []
): string {
	const params = new URLSearchParams(excludeCameras.map((value) => ['exclude_camera', value]));
	if (sameCameraOnly) params.set('same_camera_only', 'true');
	for (const { assetId, point } of pending) {
		params.append('pending', `${assetId},${point.lat},${point.lon}`);
	}
	return params.size ? `?${params}` : '';
}

/** `pending`: locations saved a moment ago; the time neighbors take them at once. */
export const getSuggestions = (
	id: string,
	excludeCameras: string[] = [],
	sameCameraOnly = false,
	pending: PendingPoint[] = []
) =>
	request<ModuleSuggestions[]>(
		'GET',
		`/api/assets/${id}/suggestions${cameraQuery(excludeCameras, sameCameraOnly, pending)}`
	);

/** Queues a worker module for the photo, or a part of it, ahead of the background runs. */
export const runModule = (
	id: string,
	module: string,
	excludeCameras: string[] = [],
	region: Region | null = null,
	sameCameraOnly = false,
	turn: Turn = 0
) =>
	request<ModuleSuggestions[]>(
		'POST',
		`/api/assets/${id}/modules/${module}/run${cameraQuery(excludeCameras, sameCameraOnly)}`,
		{ turn, ...(region ? { region } : {}) }
	);
export const getAsset = (id: string, filter: GalleryFilter) =>
	request<AssetDetail>('GET', `/api/assets/${id}${filterQuery(filter)}`);
export const setReview = (id: string, status: ReviewStatus, filter: GalleryFilter) =>
	request<AssetDetail>('PUT', `/api/assets/${id}/review${filterQuery(filter)}`, { status });
export const setLocation = (
	id: string,
	point: { lat: number; lon: number },
	filter: GalleryFilter | null = null,
	keepalive = false,
	direction: Direction | null = null
) =>
	request<AssetDetail>(
		'PUT',
		`/api/assets/${id}/location${filter ? filterQuery(filter) : ''}`,
		{ latitude: point.lat, longitude: point.lon, ...(direction ? { direction } : {}) },
		keepalive
	);
/** Keeps which way the camera looked (in the app only), the place as it is. */
export const setDirection = (id: string, direction: Direction, filter: GalleryFilter) =>
	request<AssetDetail>('PUT', `/api/assets/${id}/direction${filterQuery(filter)}`, direction);
/** Forgets which way the camera looked (kept in the app only). */
export const forgetDirection = (id: string, filter: GalleryFilter) =>
	request<AssetDetail>('DELETE', `/api/assets/${id}/direction${filterQuery(filter)}`);
/** Saves the photo rotated in Immich, on top of how it is shown now (an Immich edit). */
export const rotateInImmich = (id: string, turn: Turn, filter: GalleryFilter) =>
	request<AssetDetail>('POST', `/api/assets/${id}/rotate${filterQuery(filter)}`, { turn });

export const undoLocation = (id: string, filter: GalleryFilter | null = null) =>
	request<AssetDetail>(
		'POST',
		`/api/assets/${id}/location/undo${filter ? filterQuery(filter) : ''}`
	);
/** How many photos one request takes (the API's limit): more are sent in batches. */
export const MAX_IDS = 2000;

/** Sends the photos `MAX_IDS` at a time, one batch after another; the answers in order. */
async function inBatches<T>(ids: string[], send: (part: string[]) => Promise<T>): Promise<T[]> {
	const answers: T[] = [];
	for (let i = 0; i < ids.length; i += MAX_IDS) answers.push(await send(ids.slice(i, i + MAX_IDS)));
	return answers;
}

/** A change of all the batches; the answer to the last one, which tells the state after. */
async function lastOfBatches<T>(ids: string[], send: (part: string[]) => Promise<T>): Promise<T> {
	const answers = await inBatches(ids, send);
	return answers.length ? answers[answers.length - 1] : send(ids);
}

const sum = <T>(answers: T[], count: (answer: T) => number) =>
	answers.reduce((total, answer) => total + count(answer), 0);

/** At most `MAX_IDS` of the photos, spread evenly over them (they come in the gallery's order). */
export function spreadSample(ids: string[]): string[] {
	if (ids.length <= MAX_IDS) return ids;
	return Array.from({ length: MAX_IDS }, (_, i) => ids[Math.floor((i * ids.length) / MAX_IDS)]);
}

/** Several photos chosen in the gallery (D-149). */
export interface SelectionWritten {
	/** What to undo: one per batch that wrote something (none when all had a location). */
	batch_ids: string[];
	written: number;
	skipped_located: number;
}

export interface SelectionUndone {
	undone: number;
	/** Changed since the write (in Immich or here): left as they are. */
	changed: number;
	failed: number;
}

/** Suggestions from what is already known for the photos; nothing is run. Past `MAX_IDS`, from
 * an even sample of them: the places and their shares stay much the same.
 * `groupId`: the group the photos were chosen in, whose places are suggested too. */
export const getSelectionSuggestions = (
	ids: string[],
	groupId: string | null = null,
	folderId: string | null = null
) =>
	request<ModuleSuggestions[]>('POST', '/api/selection/suggestions', {
		ids: spreadSample(ids),
		group_id: groupId,
		folder_id: folderId
	});
export async function setSelectionLocation(
	ids: string[],
	point: { lat: number; lon: number },
	overwrite: boolean,
	keepalive = false
): Promise<SelectionWritten> {
	const answers = await inBatches(ids, (part) =>
		request<{ batch_id: string | null; written: number; skipped_located: number }>(
			'POST',
			'/api/selection/location',
			{ ids: part, latitude: point.lat, longitude: point.lon, overwrite },
			keepalive
		)
	);
	return {
		batch_ids: answers.flatMap((a) => (a.batch_id ? [a.batch_id] : [])),
		written: sum(answers, (a) => a.written),
		skipped_located: sum(answers, (a) => a.skipped_located)
	};
}
/** Undoes the writes of all the batches of one save. */
export async function undoSelectionLocation(batchIds: string[]): Promise<SelectionUndone> {
	const answers: SelectionUndone[] = [];
	for (const batchId of batchIds) {
		answers.push(
			await request<SelectionUndone>('POST', '/api/selection/location/undo', {
				batch_id: batchId
			})
		);
	}
	return {
		undone: sum(answers, (a) => a.undone),
		changed: sum(answers, (a) => a.changed),
		failed: sum(answers, (a) => a.failed)
	};
}
export async function setSelectionReview(ids: string[], status: ReviewStatus) {
	const answers = await inBatches(ids, (part) =>
		request<{ changed: number }>('PUT', '/api/selection/review', { ids: part, status })
	);
	return { changed: sum(answers, (a) => a.changed) };
}
/** Turns the photos in Immich in the background: a job per batch, which tells its progress.
 * Photos already being turned are left out. `turned`: from the list of turned photos, where a
 * photo is turned only while the list still offers it so. */
export const rotateSelection = (ids: string[], turn: Exclude<Turn, 0>, turned = false) =>
	inBatches(ids, (part) =>
		request<Job>('POST', '/api/selection/rotate', { ids: part, turn, turned })
	);
export const getSelectionJob = (id: string) => request<Job>('GET', `/api/selection/jobs/${id}`);

/** Photos that look turned the same way (D-237). */
export interface TurnedGroup {
	/** Quarter turns counter-clockwise the photos have now: 1 lies on its left side, 2 upside down,
	 * 3 on its right side. */
	turn: 1 | 2 | 3;
	/** Degrees clockwise that turn them right: what `rotateSelection` takes. */
	fix: Exclude<Turn, 0>;
	total: number;
	/** A page of them, the surest first, with how sure the module is of each. */
	photos: AssetItem[];
	scores: number[];
}

export interface TurnedPhotos {
	groups: TurnedGroup[];
	/** Photos the module has looked at: none yet means no worker runs it. */
	checked: number;
	/** Photos kept as they are ("Not turned"). Absent: an older core. */
	kept?: number;
}

/** How many photos the orientation module would look at again after a reset. */
export const getTurnedReset = (keepKept: boolean) =>
	request<{ photos: number }>('GET', `/api/groups/candidates/turned/reset?keep_kept=${keepKept}`);
/** Forgets the turns found: the module looks at the photos again by itself. */
export const resetTurned = (keepKept: boolean) =>
	request<{ photos: number }>('POST', '/api/groups/candidates/turned/reset', {
		keep_kept: keepKept
	});

/** The photos kept as they are, newest first. */
export const getKeptTurned = (offset = 0, limit = 200) =>
	request<{ total: number; photos: AssetItem[] }>(
		'GET',
		`/api/groups/candidates/turned/kept?offset=${offset}&limit=${limit}`
	);

export function getTurned(turn: number | null = null, offset = 0, limit = 200) {
	const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
	if (turn) params.set('turn', String(turn));
	return request<TurnedPhotos>('GET', `/api/groups/candidates/turned?${params}`);
}
/** Right as they are: they leave the list (until their image changes); `kept` false: back. */
export async function keepTurned(ids: string[], kept = true) {
	const answers = await inBatches(ids, (part) =>
		request<{ changed: number }>('POST', '/api/groups/candidates/turned/keep', {
			ids: part,
			kept
		})
	);
	return { changed: sum(answers, (a) => a.changed) };
}

/** An album of Immich: the account's own or one shared with it (D-233). */
export interface Album {
	id: string;
	immich_id: string;
	name: string;
	/** Photos in the album as Immich counts them (in a shared album, other users' too). */
	count: number;
	/** Of them, photos of this library: what the gallery shows with the album filter. */
	own_count: number;
	shared: boolean;
	role: 'owner' | 'editor' | 'viewer';
	can_change_photos: boolean;
	owned: boolean;
	has_cover: boolean;
	start_date: string | null;
	end_date: string | null;
	updated_at: string;
}

export type AlbumAction = 'add' | 'remove' | 'create' | 'rename' | 'delete';

export interface AlbumList {
	albums: Album[];
	/** What the Immich API key allows. */
	allowed: Record<AlbumAction, boolean>;
	/** The Immich permission each action needs. */
	permissions: Record<AlbumAction, string>;
	/** Immich in the browser: albums are at `/albums/{immich_id}` there. */
	immich_url: string | null;
}

export interface AlbumAdded {
	album: Album;
	/** The photos put into the album now: what an undo takes out again. */
	added: string[];
	already: number;
	skipped_locked: number;
	failed: number;
	/** The album was made by this change: undoing it deletes the album. */
	created: boolean;
}

export const getAlbums = () => request<AlbumList>('GET', '/api/albums');
/** Album id -> how many of the photos are in it already (albums with none left out). */
export async function albumsContaining(ids: string[]) {
	const answers = await inBatches(ids, (part) =>
		request<{ counts: Record<string, number> }>('POST', '/api/albums/contains', { ids: part })
	);
	const counts: Record<string, number> = {};
	for (const answer of answers) {
		for (const [album, count] of Object.entries(answer.counts)) {
			counts[album] = (counts[album] ?? 0) + count;
		}
	}
	return { counts };
}

/** The answers of all the batches as one; `created` as the first one tells. */
function addedTogether(answers: AlbumAdded[]): AlbumAdded {
	return {
		album: answers[answers.length - 1].album,
		added: answers.flatMap((a) => a.added),
		already: sum(answers, (a) => a.already),
		skipped_locked: sum(answers, (a) => a.skipped_locked),
		failed: sum(answers, (a) => a.failed),
		created: answers[0].created
	};
}

const addBatch = (albumId: string, ids: string[]) =>
	request<AlbumAdded>('PUT', `/api/albums/${albumId}/assets`, { ids });

/** A new album with the photos; past the first batch they are added to it. */
export async function createAlbum(name: string, ids: string[] = []) {
	const first = await request<AlbumAdded>('POST', '/api/albums', {
		name,
		ids: ids.slice(0, MAX_IDS)
	});
	const rest = await inBatches(ids.slice(MAX_IDS), (part) => addBatch(first.album.id, part));
	return addedTogether([first, ...rest]);
}

export async function addToAlbum(albumId: string, ids: string[]) {
	const answers = await inBatches(ids, (part) => addBatch(albumId, part));
	return answers.length ? addedTogether(answers) : addBatch(albumId, ids);
}

export interface AlbumRemoved {
	album: Album;
	removed: number;
	/** The photos taken out now: what an undo puts back. */
	removed_ids: string[];
	failed: number;
}

export async function removeFromAlbum(albumId: string, ids: string[]): Promise<AlbumRemoved> {
	const send = (part: string[]) =>
		request<AlbumRemoved>('POST', `/api/albums/${albumId}/assets/remove`, { ids: part });
	const answers = await inBatches(ids, send);
	if (!answers.length) return send(ids);
	return {
		album: answers[answers.length - 1].album,
		removed: sum(answers, (a) => a.removed),
		removed_ids: answers.flatMap((a) => a.removed_ids),
		failed: sum(answers, (a) => a.failed)
	};
}
export const renameAlbum = (albumId: string, name: string) =>
	request<Album>('PATCH', `/api/albums/${albumId}`, { name });
export const deleteAlbum = (albumId: string) => request<void>('DELETE', `/api/albums/${albumId}`);
export const albumCoverUrl = (album: Album) =>
	`/api/albums/${album.id}/cover?v=${encodeURIComponent(album.updated_at)}`;

export const getMapConfig = () => request<MapConfig>('GET', '/api/config/map');
export function geocode(q: string, lang: string, near: { lat: number; lon: number } | null) {
	const params = new URLSearchParams({ q, lang });
	if (near) {
		params.set('lat', String(near.lat));
		params.set('lon', String(near.lon));
	}
	return request<Place[]>('GET', `/api/geocode?${params}`);
}

export const getHealth = () => request<Health>('GET', '/api/health');
export const getLibrary = () => request<Library>('GET', '/api/library');
export const startSync = (full: boolean | null = null) =>
	request<Job>('POST', '/api/library/sync', { full });
/** Computes the badge "similar with a location" for all photos now, as the daily pass does. */
export const startSimilarHints = () => request<Job>('POST', '/api/library/similar-hints');

/** What the list of groups shows: all but the trash, a part of them, or the trash. */
export type GroupView =
	'all' | 'ready' | 'no_location' | 'with_location' | 'spread' | 'trash' | 'dissolved';

export interface GroupOut {
	id: string;
	/** Given by the user. */
	name: string | null;
	trash: boolean;
	photos: number;
	without_location: number;
	with_location: number;
	/** The photos with a location lie more than 1 km apart. */
	spread: boolean;
	/** How close the photos are to each other; null until the next rebuild. */
	similarity: number | null;
	/** Where most of the photos with a location lie; null with too few of them. */
	spot: { latitude: number; longitude: number; photos: number } | null;
	/** Photos with it, marked as showing nothing of the place. */
	marked: number;
	/** Most of the photos with a location lie in the spot. */
	main_spot: boolean;
	/** The photos without a location can get the place of the spot. */
	ready: boolean;
	cover: { id: string; version: string | null } | null;
	/** The folder it is in (D-201). */
	folder: FolderRef | null;
}

export interface FolderRef {
	id: string;
	name: string;
}

/** A folder in the list: of the groups of the view in it. */
export interface FolderOut {
	id: string;
	name: string;
	groups: number;
	photos: number;
	without_location: number;
	with_location: number;
	/** Its groups marked as showing no sign of a place. */
	trash: number;
	covers: { id: string; version: string | null }[];
}

export interface FolderPoint extends GroupPoint {
	group_id: string;
}

export interface FolderDetail {
	folder: FolderRef;
	groups: GroupOut[];
	photos: AssetItem[];
	/** Photo -> its group. */
	group_of: Record<string, string>;
	points: FolderPoint[];
	spot: { latitude: number; longitude: number; photos: number } | null;
	main_spot: boolean;
	ready: boolean;
}

/** A group that may show the same scene. */
export interface CloseGroup {
	group: GroupOut;
	similarity: number;
	/** Between the main spots, when both have one. */
	distance_km: number | null;
}

export interface GroupList {
	status: {
		/** Photos with a vector, and those already compared with the others. */
		vectors: number;
		searched: number;
		rebuilt_at: string | null;
		job: Job | null;
	};
	counts: Record<GroupView, number>;
	groups: GroupOut[];
	/** The groups of this list (out of the folders unless flat), for the pages. */
	total: number;
	/** The folders with groups of the view, on the first page (none when flat). */
	folders: FolderOut[];
}

export interface GroupPoint {
	id: string;
	latitude: number;
	longitude: number;
	/** The number of its spot in the group: 0 for the largest. */
	spot: number;
	/** The location was written by this app. */
	set_in_app: boolean;
}

export interface GroupDetail {
	group: GroupOut;
	photos: AssetItem[];
	/** The photos with a location, for the map. */
	points: GroupPoint[];
	/** Showing nothing of the place: out of the photos of the group, but with it. */
	marked: AssetItem[];
	/** Taken out by the user. */
	excluded: AssetItem[];
	/** Per photo: how close it is to the others of the group. */
	closeness: Record<string, number>;
	/** The photos closest to the rest of the group: what it holds on to. */
	center: string[];
}

export const getGroups = (view: GroupView, offset: number, limit: number, flat = false) =>
	request<GroupList>(
		'GET',
		`/api/groups?view=${view}&offset=${offset}&limit=${limit}${flat ? '&flat=true' : ''}`
	);
export const getFolders = () => request<FolderRef[]>('GET', '/api/groups/folders');
export const getFolder = (id: string) => request<FolderDetail>('GET', `/api/groups/folders/${id}`);
/** Only what is given changes; `trash` marks all the groups of the folder, or none. */
export const updateFolder = (id: string, change: { name?: string; trash?: boolean }) =>
	request<FolderDetail>('PATCH', `/api/groups/folders/${id}`, change);
/** The folder goes; its groups stay. */
export const deleteFolder = (id: string) => request<void>('DELETE', `/api/groups/folders/${id}`);
/** Into a folder (`folder_id`), a new one (`name`), or out of any (neither). */
export const setGroupFolder = (id: string, to: { folder_id?: string; name?: string }) =>
	request<GroupDetail>('PUT', `/api/groups/${id}/folder`, to);
/** Groups that may show the same scene, the most alike first. */
export const getCloseGroups = (id: string) =>
	request<CloseGroup[]>('GET', `/api/groups/${id}/close`);
export const getGroup = (id: string) => request<GroupDetail>('GET', `/api/groups/${id}`);
/** Only what is given changes; an empty name takes the name away. */
export const updateGroup = (id: string, change: { name?: string; trash?: boolean }) =>
	request<GroupDetail>('PATCH', `/api/groups/${id}`, change);
export const getGroupNear = (id: string) => request<AssetItem[]>('GET', `/api/groups/${id}/near`);
/** What the groups say about a photo: its group, and whether it shows nothing of the place. */
export const getPhotoGroup = (id: string) =>
	request<{
		group: { id: string; name: string | null } | null;
		no_sign: boolean;
		/** Marked by the app, not by the user. */
		no_sign_auto: boolean;
		/** Marked by itself, not only with its whole group: the mark can be taken off here. */
		no_sign_self: boolean;
	}>('GET', `/api/groups/of-photo/${id}`);
/** Other groups in the main spot of a group: other sides of one place. */
export const getGroupSameSpot = (id: string) =>
	request<GroupOut[]>('GET', `/api/groups/${id}/same-spot`);
/** The scenes inside a group: the higher the level, the stricter. */
export const getGroupParts = (id: string, level: number) =>
	request<{ similarity: number; parts: string[][] }>(
		'GET',
		`/api/groups/${id}/parts?level=${level}`
	);
/** Photos that show nothing of the place: out of the suggestions and of the groups. */
export const trashPhotos = (id: string, ids: string[]) =>
	lastOfBatches(ids, (part) =>
		request<GroupDetail>('POST', `/api/groups/${id}/trash`, { ids: part })
	);
/** Who set a mark "no sign of a place": the user or the app. */
export type MarkSource = 'user' | 'auto';
export interface TrashedPhotos {
	/** Marked by themselves: all, by the user, by the app. */
	total: number;
	user: number;
	auto: number;
	/** A page of them (of one source when asked), those marked last first. */
	photos: AssetItem[];
	/** Those of the page the app marked. */
	auto_ids: string[];
	/** Photos marked with their whole group, not counted above. */
	in_groups: number;
}
export const getTrashedPhotos = (offset: number, limit: number, source?: MarkSource) =>
	request<TrashedPhotos>(
		'GET',
		`/api/groups/trash-photos?offset=${offset}&limit=${limit}${source ? `&source=${source}` : ''}`
	);
/** Marks photos from anywhere: out of the suggestions and of the groups. */
export const markPhotos = (ids: string[]) =>
	lastOfBatches(ids, (part) =>
		request<TrashedPhotos>('POST', '/api/groups/trash-photos', { ids: part })
	);
/** Photos that may show no sign of a place (A1.3). */
export interface Candidates {
	photos: AssetItem[];
}
/** Found by a description through the smart search of Immich (only the text goes there). */
export const getDescribedCandidates = (query: string, language?: string) =>
	request<Candidates>(
		'GET',
		`/api/groups/candidates/described?query=${encodeURIComponent(query)}${
			language ? `&language=${encodeURIComponent(language)}` : ''
		}`
	);
/** Alike photos with a location that lie far apart: a view seen in many places. */
export const getScatteredCandidates = () =>
	request<Candidates>('GET', '/api/groups/candidates/scattered');
/** Marks the app set become the user's own. */
export const confirmPhotos = (ids: string[]) =>
	lastOfBatches(ids, (part) =>
		request<TrashedPhotos>('POST', '/api/groups/trash-photos/confirm', { ids: part })
	);
export const restorePhotos = (ids: string[]) =>
	lastOfBatches(ids, (part) =>
		request<TrashedPhotos>('POST', '/api/groups/trash-photos/restore', { ids: part })
	);
/** All of them, also those no page has shown. */
export const restoreAllPhotos = () =>
	request<TrashedPhotos>('POST', '/api/groups/trash-photos/restore-all');
/** Takes the group apart; the rule builds it no more. */
export const dissolveGroup = (id: string) => request<Job>('POST', `/api/groups/${id}/dissolve`);
export const bringBackGroup = (id: string) => request<Job>('POST', `/api/groups/${id}/bring-back`);
export const excludeFromGroup = (id: string, ids: string[]) =>
	lastOfBatches(ids, (part) =>
		request<GroupDetail>('POST', `/api/groups/${id}/exclude`, { ids: part })
	);
export const includeInGroup = (id: string, ids: string[]) =>
	lastOfBatches(ids, (part) =>
		request<GroupDetail>('POST', `/api/groups/${id}/include`, { ids: part })
	);
export const refreshGroups = () => request<Job>('POST', '/api/groups/refresh');
/** Drops the groups with their names and all that was done to them, and builds them anew. */
export const resetGroups = () => request<Job>('POST', '/api/groups/reset');
export const login = (apiKey: string) =>
	request<Me>('POST', '/api/auth/login', { api_key: apiKey });
export const loginWithPassword = (email: string, password: string) =>
	request<Me>('POST', '/api/auth/login/password', { email, password });
export const logout = () => request<void>('POST', '/api/auth/logout');
export const getMe = () => request<Me>('GET', '/api/auth/me');

/** The Immich locked folder of the account (D-216): connected once with the password. */
export interface LockedState {
	connected: boolean;
	connected_at: string | null;
	open: boolean;
	/** Minutes without a click or key press that close the folder. */
	idle_minutes: number;
	/** Too many wrong PIN codes: no new try before this. */
	blocked_until: string | null;
}
export const getLocked = () => request<LockedState>('GET', '/api/locked');
export const connectLocked = (password: string) =>
	request<LockedState & { has_pin: boolean }>('POST', '/api/locked/connect', { password });
export const disconnectLocked = () => request<LockedState>('DELETE', '/api/locked');
/** The PIN code goes to Immich through the app, which neither stores nor logs it. */
export const openLocked = (pinCode: string) =>
	request<LockedState>('POST', '/api/locked/open', { pin_code: pinCode });
export const closeLocked = () => request<LockedState>('POST', '/api/locked/close');
/** A click or key press: keeps an open folder open (sent at most once a minute). */
export const lockedActivity = () => request<LockedState>('POST', '/api/locked/activity');

/** A source of street-level images as the account set it up (D-244). */
export interface StreetSource {
	id: 'panoramax' | 'mapillary';
	name: string;
	enabled: boolean;
	needs_key: boolean;
	has_key: boolean;
	/** "invalid": the provider refused the token. */
	key_problem: string | null;
	site_url: string;
	terms_url: string;
	key_url: string | null;
}

export const getStreetSources = () => request<StreetSource[]>('GET', '/api/street/sources');
/** Only what is given changes; an empty token deletes it (a new one is checked at once). */
export const updateStreetSource = (id: string, change: { enabled?: boolean; api_key?: string }) =>
	request<StreetSource>('PUT', `/api/street/sources/${id}`, change);

/** A street-level image near the point. */
export interface StreetImage {
	source: 'panoramax' | 'mapillary';
	id: string;
	latitude: number;
	longitude: number;
	distance_m: number;
	/** Degrees clockwise from north the camera looked; null: unknown. */
	heading: number | null;
	/** A 360-degree panorama. */
	pano: boolean;
	taken_at: string | null;
	author: string | null;
	license: string | null;
	license_url: string | null;
	page_url: string;
}

export interface StreetNear {
	images: StreetImage[];
	/** How each switched-on source answered: ok, no_key, invalid_key or unavailable. */
	sources: { id: string; status: 'ok' | 'no_key' | 'invalid_key' | 'unavailable'; count: number }[];
}

/** The images of the switched-on sources around the point, nearest first: the point goes to them. */
export const getStreetNear = (lat: number, lon: number, radius = 100, source?: string) =>
	request<StreetNear>(
		'GET',
		`/api/street/near?lat=${lat}&lon=${lon}&radius=${radius}` +
			(source ? `&source=${encodeURIComponent(source)}` : '')
	);

/** A preview of a street-level image, through the core. */
export const streetImageUrl = (image: StreetImage, size: 'thumb' | 'large' = 'thumb') =>
	`/api/street/image/${image.source}/${encodeURIComponent(image.id)}?size=${size}`;

/** How a street-level image matches the photo (the `street` module of a worker, D-244). */
export interface StreetMatch {
	/** "mapillary:123". */
	key: string;
	/** How alike they look (MegaLoc), -1..1. */
	similarity: number | null;
	/** Matched point by point (the most alike ones only). */
	checked: boolean;
	matches: number;
	inliers: number;
	/** x, y in the photo and x, y in the image, 0..1 of their sides. */
	lines: [number, number, number, number][];
	/** The view of a panorama that matched. */
	view: number | null;
	/** Degrees the photo looks to the right of the image, and how far the points spread. */
	offset: number | null;
	spread: number | null;
	/** The width of view of the photo found from the points; absent from older workers. */
	fov?: number | null;
}

export interface StreetComparison {
	status: 'none' | 'queued' | 'running' | 'done' | 'failed';
	error_code: string | null;
	/** Active workers that run the module: none, and the comparison waits. */
	workers: number;
	results: StreetMatch[];
}

/** Compares the photo with the street-level images of the strip, on a worker. */
export const compareStreet = (assetId: string, images: string[]) =>
	request<StreetComparison>('POST', `/api/street/compare/${assetId}`, { images });
export const getStreetComparison = (assetId: string) =>
	request<StreetComparison>('GET', `/api/street/compare/${assetId}`);
